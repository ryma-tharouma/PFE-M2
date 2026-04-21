import logging
import torch
import numpy as np
from typing import List, Optional
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from embedder import Embedder
from chunker import Aggregator
from vector_db import VectorDB

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Reranker
# ----------------------------------------------------------------------

class Reranker:
    """
    BGE cross-encoder reranker. Scores (query, doc) pairs and reorders
    retrieved chunks by relevance.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        batch_size: int = 16,
        top_k_rerank: int = 20,
    ):
        self.batch_size = batch_size
        self.top_k_rerank = top_k_rerank
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

    def _score(self, query: str, documents: List[str]) -> List[float]:
        pairs = [(query, doc) for doc in documents]
        scores = []
        with torch.no_grad():
            for i in range(0, len(pairs), self.batch_size):
                batch = pairs[i : i + self.batch_size]
                inputs = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)
                logits = self.model(**inputs).logits.squeeze(-1).float().cpu().tolist()
                scores.extend([logits] if isinstance(logits, float) else logits)
        return scores

    def rerank(
        self,
        query: str,
        chunk_ids: List[str],
        chunk_texts: List[str],
        chunk_scores: List[float],
    ) -> tuple[List[str], List[float], List[str]]:
        """
        Rerank top_k_rerank chunks and leave the rest untouched.

        Returns reordered (chunk_ids, chunk_scores, chunk_texts).
        """
        if not chunk_ids:
            return [], [], []

        k = min(self.top_k_rerank, len(chunk_ids))
        rerank_scores = self._score(query, chunk_texts[:k])

        top = sorted(
            zip(chunk_ids[:k], rerank_scores, chunk_texts[:k]),
            key=lambda x: x[1],
            reverse=True,
        )
        reordered_ids    = [t[0] for t in top] + chunk_ids[k:]
        reordered_scores = [t[1] for t in top] + chunk_scores[k:]
        reordered_texts  = [t[2] for t in top] + chunk_texts[k:]
        return reordered_ids, reordered_scores, reordered_texts

    def cleanup(self):
        del self.model, self.tokenizer
        if self.device == "cuda":
            torch.cuda.empty_cache()


# ----------------------------------------------------------------------
# Retriever
# ----------------------------------------------------------------------

class Retriever:
    """
    End-to-end retrieval pipeline:
        query → embed → vector search → (rerank) → aggregate → section IDs
    """

    def __init__(
        self,
        db: VectorDB,
        embedder: Embedder,
        search_top_k: int = 50,
        rerank: bool = False,
        rerank_top_k: int = 20,
        sections_top_k: int = 10,
        reranker_batch_size: int = 16,
    ):
        self.db = db
        self.embedder = embedder
        self.search_top_k = search_top_k
        self.sections_top_k = sections_top_k

        self.reranker: Optional[Reranker] = (
            Reranker(batch_size=reranker_batch_size, top_k_rerank=rerank_top_k)
            if rerank
            else None
        )
        self.aggregator = Aggregator(top_k=sections_top_k)

    def retrieve(self, query: str, app_id: str) -> tuple[List[str], List[float], List[dict]]:
        """
        Run the full retrieval pipeline.

        Args:
            query  : raw query string
            app_id : collection name in the vector DB

        Returns:
            (section_ids, scores, metadatas) — all sorted best-first.
            section_ids : list of section ID strings
            scores      : corresponding aggregated scores
            metadatas   : corresponding payload dicts (source_type, source_pdf, etc.)
        """
        # 1. Embed query
        query_vector = self.embedder.encode_one(query)

        # 2. Vector search → chunks
        chunk_ids, chunk_scores, chunk_payloads = self.db.search(
            name=app_id,
            query_vector=query_vector,
            top_k=self.search_top_k,
        )

        if not chunk_ids:
            return [], [], []

        # 3. Optional rerank
        if self.reranker:
            chunk_texts = [p.get("chunk_text", "") for p in chunk_payloads]
            chunk_ids, chunk_scores, _ = self.reranker.rerank(
                query, chunk_ids, chunk_texts, chunk_scores
            )

        # 4. Aggregate chunks → sections
        chunk_results = [
            {"id": cid, "score": sc, "payload": pl}
            for cid, sc, pl in zip(chunk_ids, chunk_scores, chunk_payloads)
        ]
        sections = self.aggregator.aggregate(chunk_results)

        ids       = [s["section_id"] for s in sections]
        scores    = [s["score"]      for s in sections]
        metadatas = [s["metadata"]   for s in sections]
        return ids, scores, metadatas

    def cleanup(self):
        self.embedder.cleanup()
        if self.reranker:
            self.reranker.cleanup()