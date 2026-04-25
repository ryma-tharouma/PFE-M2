# chunker.py
import logging
from typing import List, Dict, Any
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


class Chunker:
    """
    Splits sections into token-bounded chunks ready for embedding.

    Embedding text is built per source_type:
      - "faq"            : problem field only (fallback to full_text)
      - "manuel"/default : title + breadcrumb + content
    """

    _tokenizer_cache: dict = {}

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: dictionary containing a "chunker" section with keys:
                - max_tokens (int, default 1024)
                - overlap (int, default 10)
                - tokenizer_model (str, default "BAAI/bge-m3")
        """
        chunker_cfg = config.get("chunker", {})
        self.max_tokens = chunker_cfg.get("max_tokens", 1024)
        self.overlap = chunker_cfg.get("overlap", 10)
        tokenizer_model = chunker_cfg.get("tokenizer_model", "BAAI/bge-m3")

        if self.overlap < 0:
            raise ValueError("overlap must be >= 0")
        if self.overlap >= self.max_tokens:
            raise ValueError("overlap must be less than max_tokens")

        if tokenizer_model not in Chunker._tokenizer_cache:
            Chunker._tokenizer_cache[tokenizer_model] = AutoTokenizer.from_pretrained(tokenizer_model)
        self.tokenizer = Chunker._tokenizer_cache[tokenizer_model]

    def process_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert raw section dicts into chunk records ready for embedding.

        Each output record is a copy of the input section enriched with:
            embed_text        – text to be embedded
            parent_section_id – ID of the originating section
            is_chunk          – True when the section was split
            chunk_index       – 0-based position within the section
            id                – unique record ID (f"{sec_id}_c{i}" when split)
        """
        chunks = []
        for sec in sections:
            chunks.extend(self._chunk_section(sec))
        return chunks

    def _build_embed_text(self, sec: Dict[str, Any]) -> str:
        if sec.get("source_type") == "faq":
            return str(sec.get("problem", sec.get("full_text", "")))  # fallback to full_text
        parts = [
            str(sec.get("title", "")),
            str(sec.get("breadcrumb", "")),
            str(sec.get("content", "")),
        ]
        return " ".join(p for p in parts if p)

    def _chunk_section(self, sec: Dict[str, Any]) -> List[Dict[str, Any]]:
        sec_id = str(sec.get("section_id", sec.get("id", "")))
        embed_text = self._build_embed_text(sec)

        if not embed_text:
            logger.warning("Section '%s' produced no embed text — skipping.", sec_id)
            return []

        tokens = self.tokenizer.encode(embed_text, add_special_tokens=False)

        if len(tokens) <= self.max_tokens:
            return [self._make_record(sec, embed_text, sec_id, is_chunk=False, index=0)]

        stride = self.max_tokens - self.overlap
        return [
            self._make_record(
                sec,
                self.tokenizer.decode(tokens[start : start + self.max_tokens]).strip(),
                sec_id,
                is_chunk=True,
                index=i,
            )
            for i, start in enumerate(range(0, len(tokens), stride))
        ]

    @staticmethod
    def _make_record(
        sec: Dict[str, Any],
        embed_text: str,
        sec_id: str,
        is_chunk: bool,
        index: int,
    ) -> Dict[str, Any]:
        record = sec.copy()
        record["embed_text"] = embed_text
        record["parent_section_id"] = sec_id
        record["is_chunk"] = is_chunk
        record["chunk_index"] = index
        record["id"] = f"{sec_id}_c{index}" if is_chunk else sec.get("id", sec_id)
        return record


class Aggregator:
    """
    Aggregates chunk-level retrieval results into section-level rankings
    using max-score aggregation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: dictionary containing an "aggregator" section with key:
                - top_k (int, default 10)
        """
        agg_cfg = config.get("aggregator", {})
        self.top_k = agg_cfg.get("top_k", 10)

    def aggregate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Collapse chunk-level results into section-level results.

        Args:
            results: list of dicts — each must contain:
                        "score"   : float
                        "payload" : dict with "parent_section_id" (falls back to "id")

        Returns:
            Top-K sections sorted by their best chunk score (descending).
            Each entry:
                section_id  – parent section ID
                score       – max chunk score
                chunk_count – number of retrieved chunks for this section
                metadata    – payload of the highest-scoring chunk
        """
        if not results:
            return []

        sections: Dict[str, Dict[str, Any]] = {}

        for item in results:
            payload = item.get("payload", {})
            sec_id = payload.get("parent_section_id") or item.get("id", "")
            score = item["score"]

            if sec_id not in sections:
                sections[sec_id] = {
                    "score": score,
                    "chunk_count": 1,
                    "metadata": payload.copy(),
                }
            else:
                entry = sections[sec_id]
                entry["chunk_count"] += 1
                if score > entry["score"]:
                    entry["score"] = score
                    entry["metadata"] = payload.copy()

        ranked = [
            {
                "section_id": sec_id,
                "score": data["score"],
                "chunk_count": data["chunk_count"],
                "metadata": data["metadata"],
            }
            for sec_id, data in sections.items()
        ]

        ranked.sort(key=lambda x: (x["score"], x["chunk_count"]), reverse=True)
        return ranked[: self.top_k]