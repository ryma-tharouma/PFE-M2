# rag.py
import logging
from typing import List, Dict, Any

from retriever import Retriever
from generator import Generator

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Routing
# ----------------------------------------------------------------------

def _determine_routing(
    section_ids: List[str],
    scores: List[float],
    metadatas: List[Dict],
    threshold: float,
) -> str:
    """
    Decide whether to answer via FAQ (direct lookup) or RAG (generation).

    Returns "faq" if:
        - there is at least one section, and
        - the top score exceeds the second best score by at least `threshold`.

    Otherwise returns "rag".

    Args:
        section_ids: list of section IDs (may be empty)
        scores: corresponding relevance scores
        metadatas: corresponding metadata dicts
        threshold: required gap between first and second score (e.g., 3.0)
    """
    if not section_ids:
        return "rag"
    if len(scores) == 1:
        # Only one section retrieved – treat as FAQ only if score is high?
        # Original code would have returned "faq" because second score considered 0.
        # We keep that logic: if only one, then top > threshold+0 -> true.
        return "faq" if scores[0] > threshold else "rag"
    # scores[0] > threshold + second_best
    if scores[0] > threshold + scores[1]:
        return "faq"
    return "rag"


# ----------------------------------------------------------------------
# Section helpers
# ----------------------------------------------------------------------

def _section_text(sec: Dict) -> str:
    if sec.get("source_type") == "faq":
        return sec.get("full_text", sec.get("answer", ""))
    breadcrumb = sec.get("breadcrumb", "")
    content = sec.get("content", "")
    return f"{breadcrumb} : {content}".strip()


def _section_source(sec: Dict) -> Dict:
    if sec.get("source_type") == "faq":
        return {"source": sec.get("source", "")}
    return {
        "source_pdf": sec.get("source_pdf", ""),
        "breadcrumb": sec.get("breadcrumb", ""),
    }


# ----------------------------------------------------------------------
# RAG pipeline
# ----------------------------------------------------------------------

class RAG:
    """
    Full retrieval-augmented generation pipeline.

    Configuration (top‑level "rag" section):
        - routing_threshold (float)   # difference between top and second score to trigger FAQ path (default 3.0)

    chat() always returns a generator with a consistent interface:
        - yields str tokens (one at a time for RAG, one shot for FAQ)
        - final item is always a sentinel dict:
            {
                "done"       : True,
                "sources"    : List[Dict],
                # only when verbose=True:
                "embed_sec"  : float,
                "search_sec" : float,
                "ttft_sec"   : float,
                "total_sec"  : float,
            }

    Args:
        config    : configuration dictionary (may contain "rag" subsection)
        retriever : configured Retriever instance
        generator : configured Generator instance
    """

    def __init__(self, config: Dict[str, Any], retriever: Retriever, generator: Generator):
        rag_cfg = config.get("rag", {})
        self.routing_threshold = float(rag_cfg.get("routing_threshold", 3.0))
        self.retriever = retriever
        self.generator = generator

    def chat(
        self,
        query: str,
        app_id: str,
        history: str = "",
        verbose: bool = False,
    ):
        # 1. Retrieve → section_ids, scores, metadatas, and timing
        section_ids, scores, metadatas, embed_sec, search_sec = self.retriever.retrieve(
            query, app_id
        )

        if not section_ids:
            sentinel = {"done": True, "sources": []}
            if verbose:
                sentinel["embed_sec"] = embed_sec
                sentinel["search_sec"] = search_sec
            yield sentinel
            return

        # 2. Route
        routing = _determine_routing(section_ids, scores, metadatas, self.routing_threshold)

        # 3. Sections are the metadatas themselves
        sections = metadatas

        if routing == "faq":
            yield from self._faq_path(sections, scores, embed_sec, search_sec, verbose)
        else:
            yield from self._rag_path(
                query, sections, section_ids, scores,
                history, verbose, embed_sec, search_sec,
            )

    # ------------------------------------------------------------------
    # FAQ path
    # ------------------------------------------------------------------

    def _faq_path(
        self,
        sections: List[Dict],
        scores: List[float],
        embed_sec: float,
        search_sec: float,
        verbose: bool,
    ):
        top_sec = sections[0]
        answer = top_sec.get("answer", top_sec.get("full_text", ""))
        if answer:
            yield answer

        sentinel = {"done": True, "sources": [_section_source(top_sec)]}
        if verbose:
            sentinel["embed_sec"] = embed_sec
            sentinel["search_sec"] = search_sec
        yield sentinel

    # ------------------------------------------------------------------
    # RAG path
    # ------------------------------------------------------------------

    def _rag_path(
        self,
        query: str,
        sections: List[Dict],
        section_ids: List[str],
        scores: List[float],
        history: str,
        verbose: bool,
        embed_sec: float,
        search_sec: float,
    ):
        sources = [_section_source(sec) for sec in sections if sec]

        # Sort sections by section_id for consistent generator input
        sorted_pairs = sorted(
            ((sid, sec) for sid, sec in zip(section_ids, sections) if sec),
            key=lambda x: x[0],
        )
        section_texts = [_section_text(sec) for _, sec in sorted_pairs]

        ttft_sec = None
        total_sec = None

        for item in self.generator.generate(
            query=query,
            section_texts=section_texts,
            history=history,
            verbose=verbose,
        ):
            if isinstance(item, dict):
                ttft_sec = item.get("ttft_sec")
                total_sec = item.get("total_sec")
            else:
                yield item

        sentinel: Dict = {"done": True, "sources": sources}
        if verbose:
            sentinel["embed_sec"] = embed_sec
            sentinel["search_sec"] = search_sec
            sentinel["ttft_sec"] = ttft_sec
            sentinel["total_sec"] = total_sec
        yield sentinel