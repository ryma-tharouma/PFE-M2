# rag.py
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from retriever import Retriever
from generator import Generator
from rewriter import Rewriter

logger = logging.getLogger(__name__)


# =============================================================================
# Routing
# =============================================================================

def _determine_routing(
    section_ids: List[str],
    scores: List[float],
    threshold_1: float,
    threshold_2: float,
) -> str:
    """Return 'fast_path' when top score exceeds threshold_1
    and the gap between top two scores exceeds threshold_2."""
    if not section_ids:
        return "rag"
    if len(scores) == 1:
        return "fast_path" if scores[0] > threshold_1 else "rag"
    return (
        "fast_path"
        if scores[0] > threshold_1 and (scores[0] - scores[1]) > threshold_2
        else "rag"
    )


# =============================================================================
# Section helpers
# =============================================================================

def _section_text(sec: Dict) -> str:
    if sec.get("source_type") == "faq":
        return (
            f"Problem: {sec.get('problem', '')}\n"
            f"Solution: {sec.get('answer', '')}"
        ).strip()
    return (
        f"[{sec.get('breadcrumb', '')}]\n"
        f"{sec.get('content', '')}"
    ).strip()


def _section_source(sec: Dict) -> Dict:
    if sec.get("source_type") == "faq":
        return {"source": sec.get("source", "")}
    return {
        "source_pdf": sec.get("source_pdf", ""),
        "breadcrumb": sec.get("breadcrumb", ""),
    }


# =============================================================================
# RAG pipeline
# =============================================================================

class RAG:
    """
    Full retrieval-augmented generation pipeline.

    Query-context modes  (config section "query_context"):
        none    – retrieval uses the raw current query
        concat  – prepends the previous *original* user query via a template
        rewrite – a separate model rewrites the current query; the rewritten
                  form is stored and used as prev_query on the next turn
                  (always chaining from the last resolved phrasing)

    Sentinel dict (always the last item yielded by chat()):
        {
            "done"            : True,
            "sources"         : List[Dict],
            "retrieval_query" : str,        # echoed back for session storage
            # verbose only:
            "rewrite_sec"     : float,
            "embed_sec"       : float,
            "search_sec"      : float,
            "ttft_sec"        : float,
            "total_sec"       : float,
        }
    """

    def __init__(
        self,
        config: Dict[str, Any],
        retriever: Retriever,
        generator: Generator,
    ):
        rag_cfg = config.get("rag", {})
        self.routing_threshold_1 = float(rag_cfg.get("routing_threshold_1", 0.72))
        self.routing_threshold_2 = float(rag_cfg.get("routing_threshold_2", 0.13))

        qc_cfg = config.get("query_context", {})
        self.qc_mode: str = qc_cfg.get("mode", "none")
        self.qc_concat_template: str = qc_cfg.get(
            "concat_template",
            "requete precedente: {prev_query}. requete courante: {current_query}",
        )

        self.retriever = retriever
        self.generator = generator
        self._rewriter: Optional[Rewriter] = (
            Rewriter(config) if self.qc_mode == "rewrite" else None
        )

    # ------------------------------------------------------------------
    # Query context
    # ------------------------------------------------------------------

    def _build_retrieval_query(
        self,
        current_query: str,
        prev_original_query: str,
        prev_retrieval_query: str,
    ) -> Tuple[str, float]:
        """
        Build the query sent to the vector store.

        concat  uses prev_original_query  – raw user wording from the last turn
        rewrite uses prev_retrieval_query – already-resolved form from the last turn

        Returns (retrieval_query, rewrite_sec).
        """
        if self.qc_mode == "none":
            return current_query, 0.0

        if self.qc_mode == "concat":
            if not prev_original_query:          # first turn
                return current_query, 0.0
            q = self.qc_concat_template.format(
                prev_query=prev_original_query,
                current_query=current_query,
            )
            return q, 0.0

        if self.qc_mode == "rewrite":
            if not prev_retrieval_query:         # first turn
                return current_query, 0.0
            return self._rewriter.rewrite(
                prev_query=prev_retrieval_query,
                current_query=current_query,
            )

        logger.warning(
            "Unknown query_context.mode %r – using raw query.", self.qc_mode
        )
        return current_query, 0.0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def chat(
        self,
        query: str,
        app_id: str,
        history: str = "",
        prev_original_query: str = "",
        prev_retrieval_query: str = "",
        verbose: bool = False,
    ):
        """
        Run one RAG turn. Yields str tokens then a sentinel dict.

        Args:
            query                : raw user input this turn
            app_id               : Qdrant collection identifier
            history              : formatted history for the generator
            prev_original_query  : raw user query from the previous turn
                                   (concat mode; empty on first turn)
            prev_retrieval_query : rewritten retrieval query from the previous turn
                                   (rewrite mode; empty on first turn)
            verbose              : include timing fields in the sentinel
        """
        retrieval_query, rewrite_sec = self._build_retrieval_query(
            query, prev_original_query, prev_retrieval_query
        )

        section_ids, scores, metadatas, embed_sec, search_sec = self.retriever.retrieve(
            retrieval_query, app_id
        )

        if not section_ids:
            yield self._make_sentinel(
                sources=[], retrieval_query=retrieval_query, verbose=verbose,
                rewrite_sec=rewrite_sec, embed_sec=embed_sec, search_sec=search_sec,
            )
            return

        routing  = _determine_routing(
            section_ids, scores, self.routing_threshold_1, self.routing_threshold_2
        )
        sections = metadatas

        if routing == "fast_path":
            yield from self._faq_path(
                sections, retrieval_query,
                embed_sec, search_sec, rewrite_sec, verbose,
            )
        else:
            yield from self._rag_path(
                query, sections, scores, retrieval_query,
                history, verbose, embed_sec, search_sec, rewrite_sec,
            )

    # ------------------------------------------------------------------
    # FAQ / fast path
    # ------------------------------------------------------------------

    def _faq_path(
        self,
        sections: List[Dict],
        retrieval_query: str,
        embed_sec: float,
        search_sec: float,
        rewrite_sec: float,
        verbose: bool,
    ):
        top_sec = sections[0]
        answer  = top_sec.get("answer", top_sec.get("full_text", top_sec.get("content", "")))
        if answer:
            yield answer
        yield self._make_sentinel(
            sources=[_section_source(top_sec)],
            retrieval_query=retrieval_query,
            verbose=verbose,
            rewrite_sec=rewrite_sec,
            embed_sec=embed_sec,
            search_sec=search_sec,
        )

    # ------------------------------------------------------------------
    # Full RAG path
    # ------------------------------------------------------------------

    def _rag_path(
        self,
        query: str,
        sections: List[Dict],
        scores: List[float],
        retrieval_query: str,
        history: str,
        verbose: bool,
        embed_sec: float,
        search_sec: float,
        rewrite_sec: float,
    ):
        sources = [_section_source(sec) for sec in sections if sec]

        # Sort sections by retrieval score descending — most relevant first in context.
        # This matters because LLMs attend more strongly to content at the start.
        sorted_sections = [
            sec for _, sec in sorted(
                (
                    (score, sec)
                    for score, sec in zip(scores, sections)
                    if sec
                ),
                key=lambda x: x[0],
                reverse=True,           # highest score first
            )
        ]
        section_texts = [_section_text(sec) for sec in sorted_sections]

        ttft_sec  = None
        total_sec = None

        # Always pass the original user query to the generator — retrieval has
        # already benefited from the enriched / rewritten form.
        for item in self.generator.generate(
            query=query,
            section_texts=section_texts,
            history=history,
            verbose=verbose,
        ):
            if isinstance(item, dict):
                ttft_sec  = item.get("ttft_sec")
                total_sec = item.get("total_sec")
            else:
                yield item

        yield self._make_sentinel(
            sources=sources,
            retrieval_query=retrieval_query,
            verbose=verbose,
            rewrite_sec=rewrite_sec,
            embed_sec=embed_sec,
            search_sec=search_sec,
            ttft_sec=ttft_sec,
            total_sec=total_sec,
        )

    # ------------------------------------------------------------------
    # Sentinel builder
    # ------------------------------------------------------------------

    @staticmethod
    def _make_sentinel(
        *,
        sources: List[Dict],
        retrieval_query: str,
        verbose: bool,
        rewrite_sec: float = 0.0,
        embed_sec: float   = 0.0,
        search_sec: float  = 0.0,
        ttft_sec:  Optional[float] = None,
        total_sec: Optional[float] = None,
    ) -> Dict:
        sentinel: Dict = {
            "done":            True,
            "sources":         sources,
            "retrieval_query": retrieval_query,
        }
        if verbose:
            sentinel["rewrite_sec"] = rewrite_sec
            sentinel["embed_sec"]   = embed_sec
            sentinel["search_sec"]  = search_sec
            sentinel["ttft_sec"]    = ttft_sec
            sentinel["total_sec"]   = total_sec
        return sentinel

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        if self._rewriter is not None:
            self._rewriter.cleanup()