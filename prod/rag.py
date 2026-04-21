import os
import json
import functools
import logging
from typing import List, Dict, Tuple

from retriever import Retriever
from generator import Generator

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Section store — loads and caches app JSON files
# ----------------------------------------------------------------------

@functools.lru_cache(maxsize=128)
def _load_sections(app_path: str) -> List[Dict]:
    with open(app_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_section(apps_dir: str, app_id: str, section_id: str) -> Dict:
    """Return the raw section dict, or {} if not found."""
    app_path = os.path.join(apps_dir, f"{app_id}.json")
    if not os.path.exists(app_path):
        logger.warning("App file not found: %s", app_path)
        return {}
    for sec in _load_sections(app_path):
        if str(sec.get("section_id")) == str(section_id):
            return sec
    logger.warning("Section '%s' not found in app '%s'.", section_id, app_id)
    return {}


def _section_text(sec: Dict) -> str:
    """Extract the text to pass to the generator for a section."""
    if sec.get("source_type") == "faq":
        return sec.get("full_text", sec.get("answer", ""))
    breadcrumb = sec.get("breadcrumb", "")
    content    = sec.get("content", "")
    return f"{breadcrumb} : {content}".strip()


def _section_source(sec: Dict) -> Dict:
    """Build the source object returned to the caller."""
    if sec.get("source_type") == "faq":
        return {"source": sec.get("source", "")}
    return {
        "source_pdf": sec.get("source_pdf", ""),
        "breadcrumb": sec.get("breadcrumb", ""),
    }


# ----------------------------------------------------------------------
# Routing
# ----------------------------------------------------------------------

def _determine_routing(
    section_ids: List[str],
    scores: List[float],
    metadatas: List[Dict],
) -> str:
    """
    Decide whether to answer via FAQ (direct lookup) or RAG (generation).
    Returns "faq" or "rag".

    TODO: fill in real routing logic.
    """
    return "rag"


# ----------------------------------------------------------------------
# RAG pipeline
# ----------------------------------------------------------------------

class RAG:
    """
    Full retrieval-augmented generation pipeline.

    chat() always returns a generator with a consistent interface:
        - yields str tokens (one at a time for RAG, one shot for FAQ)
        - final item is always a sentinel dict:
            {
                "done"    : True,
                "sources" : List[Dict],          # in score order
                # only when verbose=True:
                "ttft_sec"  : float,
                "total_sec" : float,
            }

    Args:
        retriever : configured Retriever instance
        generator : configured Generator instance
        apps_dir  : directory containing per-app JSON section files
    """

    def __init__(self, retriever: Retriever, generator: Generator, apps_dir: str):
        self.retriever = retriever
        self.generator = generator
        self.apps_dir  = apps_dir

    def chat(
        self,
        query: str,
        app_id: str,
        history: str = "",
        verbose: bool = False,
    ):
        """
        Run the full pipeline and stream the response.

        Args:
            query   : user query string
            app_id  : identifies which app/collection to search
            history : previous turn as "Utilisateur: ...\\nAssistant: ..."
            verbose : if True, sentinel includes ttft_sec and total_sec

        Yields:
            str tokens, then a final sentinel dict (see class docstring).
        """
        # 1. Retrieve
        section_ids, scores, metadatas = self.retriever.retrieve(query, app_id)

        if not section_ids:
            yield {"done": True, "sources": []}
            return

        # 2. Route
        routing = _determine_routing(section_ids, scores, metadatas)

        # 3. Load section dicts (needed for both paths)
        sections = [
            _get_section(self.apps_dir, app_id, sid)
            for sid in section_ids
        ]

        if routing == "faq":
            yield from self._faq_path(sections, scores)
        else:
            yield from self._rag_path(query, sections, section_ids, scores, history, verbose)

    # ------------------------------------------------------------------
    # FAQ path
    # ------------------------------------------------------------------

    def _faq_path(self, sections: List[Dict], scores: List[float]):
        # Return the top-scored section's answer directly
        top_sec = sections[0]
        answer  = top_sec.get("answer", top_sec.get("full_text", ""))
        if answer:
            yield answer

        yield {"done": True, "sources": [_section_source(top_sec)]}

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
    ):
        # Build sources in score order (before generation)
        sources = [_section_source(sec) for sec in sections if sec]

        # Sort section texts alphabetically by section_id for the generator
        sorted_pairs = sorted(
            ((sid, sec) for sid, sec in zip(section_ids, sections) if sec),
            key=lambda x: x[0],
        )
        section_texts = [_section_text(sec) for _, sec in sorted_pairs]

        # Stream tokens from generator
        ttft_sec  = None
        total_sec = None

        for item in self.generator.generate(
            query=query,
            section_texts=section_texts,
            history=history,
            verbose=verbose,
        ):
            if isinstance(item, dict):
                # timing sentinel from generator
                ttft_sec  = item.get("ttft_sec")
                total_sec = item.get("total_sec")
            else:
                yield item

        # Final sentinel — always includes sources
        sentinel: Dict = {"done": True, "sources": sources}
        if verbose:
            sentinel["ttft_sec"]  = ttft_sec
            sentinel["total_sec"] = total_sec
        yield sentinel