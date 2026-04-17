# src/reranker.py
import torch
from typing import List, Tuple, Optional
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import numpy as np

class BGEReranker:
    """
    BGE cross-encoder reranker. Scores query-document pairs and returns
    relevance scores. Typically used to reorder retrieved documents.
    """
    def __init__(self, cfg: dict):
        rerank_cfg = cfg.get("reranker", {})
        self.model_name = rerank_cfg.get("model_name", "BAAI/bge-reranker-v2-m3")
        self.device = rerank_cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = rerank_cfg.get("batch_size", 16)
        self.top_k_rerank = rerank_cfg.get("top_k_rerank", 20)  # number of docs to rerank
        self.use_fp16 = rerank_cfg.get("use_fp16", False)

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self.model.to(self.device)
        if self.use_fp16 and self.device == "cuda":
            self.model.half()
        self.model.eval()

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """
        Compute relevance scores for each (query, doc) pair.
        Returns list of scores in same order as input documents.
        """
        pairs = [(query, doc) for doc in documents]
        scores = []
        with torch.no_grad():
            for i in range(0, len(pairs), self.batch_size):
                batch = pairs[i:i+self.batch_size]
                inputs = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt"
                ).to(self.device)
                outputs = self.model(**inputs)
                batch_scores = outputs.logits.squeeze(-1).float().cpu().tolist()
                if isinstance(batch_scores, float):
                    batch_scores = [batch_scores]
                scores.extend(batch_scores)
        return scores

    def rerank_and_reorder(self, query: str, doc_ids: List[str], doc_texts: List[str],
                           original_scores: List[float]) -> Tuple[List[str], List[float]]:
        """
        Rerank the retrieved documents and return reordered ids and scores.
        Only reranks top_k_rerank documents; leaves the rest in original order.
        """
        if not doc_ids:
            return [], []

        # Take only top_k_rerank for reranking
        k = min(self.top_k_rerank, len(doc_ids))
        rerank_ids = doc_ids[:k]
        rerank_texts = doc_texts[:k]

        # Get reranker scores
        rerank_scores = self.rerank(query, rerank_texts)

        # Pair and sort by rerank score descending
        paired = list(zip(rerank_ids, rerank_scores, original_scores[:k]))
        paired.sort(key=lambda x: x[1], reverse=True)

        new_ids = [p[0] for p in paired]
        new_scores = [p[1] for p in paired]

        # Append remaining documents (not reranked) in original order
        if len(doc_ids) > k:
            remaining_ids = doc_ids[k:]
            remaining_scores = original_scores[k:]
            new_ids.extend(remaining_ids)
            new_scores.extend(remaining_scores)

        return new_ids, new_scores

    def cleanup(self):
        """Free resources."""
        del self.model
        del self.tokenizer
        if self.device == "cuda":
            torch.cuda.empty_cache()