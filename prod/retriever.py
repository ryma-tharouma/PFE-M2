# retriever.py
import logging
import time
import torch
from typing import List, Optional, Tuple, Dict, Any
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from embedder import Embedder
from chunker import Aggregator
from vector_store import VectorDB

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Reranker
# ----------------------------------------------------------------------

class Reranker:
    """
    BGE cross-encoder reranker. Scores (query, doc) pairs and reorders
    retrieved chunks by relevance.

    Configuration (top‑level "reranker" section):
        - enabled (bool)              # whether to use reranking
        - model_name (str)            # default "BAAI/bge-reranker-v2-m3"
        - batch_size (int)            # default 32
        - top_k_rerank (int)          # number of chunks to rerank, default 20
    """

    def __init__(self, config: Dict[str, Any]):
        rerank_cfg = config.get("reranker", {})
        self.model_name = rerank_cfg.get("model_name", "BAAI/bge-reranker-v2-m3")
        self.batch_size = rerank_cfg.get("batch_size", 32)
        self.top_k_rerank = rerank_cfg.get("top_k_rerank", 20)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
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
                    max_length=1024,
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
    ) -> Tuple[List[str], List[float], List[str]]:
        """Rerank top_k_rerank chunks, keep others at original ranking."""
        if not chunk_ids:
            return [], [], []

        k = min(self.top_k_rerank, len(chunk_ids))
        if k == 0:
            return chunk_ids, chunk_scores, chunk_texts

        rerank_scores = self._score(query, chunk_texts[:k])
        top = sorted(
            zip(chunk_ids[:k], rerank_scores, chunk_texts[:k]),
            key=lambda x: x[1],
            reverse=True,
        )
        reordered_ids = [t[0] for t in top] + chunk_ids[k:]
        reordered_scores = [t[1] for t in top] + chunk_scores[k:]
        reordered_texts = [t[2] for t in top] + chunk_texts[k:]
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
    End‑to‑end retrieval pipeline: embed → vector search → (optional rerank) → aggregate.

    Configuration (top‑level "retriever" section):
        - search_top_k (int)       # number of chunks to retrieve from vector DB, default 20
        - sections_top_k (int)     # number of final sections after aggregation, default 5

    Reranking is controlled by the top‑level "reranker" section (see Reranker docstring).
    """

    def __init__(self, config: Dict[str, Any], db: VectorDB, embedder: Embedder):
        self.db = db
        self.embedder = embedder

        ret_cfg = config.get("retriever", {})
        self.search_top_k = ret_cfg.get("search_top_k", 20)
        self.sections_top_k = ret_cfg.get("sections_top_k", 5)

        # Reranker – enabled only if reranker.enabled = True
        rerank_cfg = config.get("reranker", {})
        self.reranker: Optional[Reranker] = None
        if rerank_cfg.get("enabled", False):
            self.reranker = Reranker(config)

        # Aggregator uses its own section (already adapted to config)
        self.aggregator = Aggregator(config)

    def retrieve(
        self,
        query: str,
        app_id: str,
    ) -> Tuple[List[str], List[float], List[dict], float, float]:
        """
        Run the full retrieval pipeline.

        Returns:
            (section_ids, scores, metadatas, embed_sec, search_sec)
        """
        # 1. Embed query
        t0 = time.perf_counter()
        query_vector = self.embedder.encode_one(query)
        embed_sec = time.perf_counter() - t0

        # 2. Vector search → chunks
        t1 = time.perf_counter()
        chunk_ids, chunk_scores, chunk_payloads = self.db.search(
            name=app_id,
            query_vector=query_vector,
            top_k=self.search_top_k,
        )

        if not chunk_ids:
            return [], [], [], embed_sec, time.perf_counter() - t1

        # 3. Optional rerank
        if self.reranker:
            chunk_texts = [p.get("embed_text", "") for p in chunk_payloads]
            chunk_ids, chunk_scores, _ = self.reranker.rerank(
                query, chunk_ids, chunk_texts, chunk_scores
            )

        # 4. Aggregate chunks → sections (uses aggregator.top_k = sections_top_k)
        chunk_results = [
            {"id": cid, "score": sc, "payload": pl}
            for cid, sc, pl in zip(chunk_ids, chunk_scores, chunk_payloads)
        ]
        sections = self.aggregator.aggregate(chunk_results)
        search_sec = time.perf_counter() - t1

        ids = [s["section_id"] for s in sections]
        scores = [s["score"] for s in sections]
        metadatas = [s["metadata"] for s in sections]
        return ids, scores, metadatas, embed_sec, search_sec

    def cleanup(self):
        self.embedder.cleanup()
        if self.reranker:
            self.reranker.cleanup()