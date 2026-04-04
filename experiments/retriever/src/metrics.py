# src/metrics.py
from dataclasses import dataclass
import numpy as np
from typing import List, Dict, Set
from collections import defaultdict

@dataclass
class RankedResult:
    query_id: str
    app_id: str
    mode: str
    rank: int
    db_type: str       
    index_type: str       
    doc_id: str
    score: float
    is_relevant: bool
    latency_ms: float

class RetrievalMetrics:
    @staticmethod
    def recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
        if not relevant: return 1.0
        return len(set(retrieved[:k]) & relevant) / len(relevant)

    @staticmethod
    def precision_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
        if k == 0: return 0.0
        return len(set(retrieved[:k]) & relevant) / k

    @staticmethod
    def reciprocal_rank(retrieved: List[str], relevant: Set[str]) -> float:
        for i, doc in enumerate(retrieved, 1):
            if doc in relevant: return 1.0 / i
        return 0.0

    @staticmethod
    def ndcg_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
        rels = [1.0 if d in relevant else 0.0 for d in retrieved[:k]]
        ideal = sorted(rels, reverse=True)
        def dcg(scores): return sum((2**s - 1) / np.log2(i+2) for i, s in enumerate(scores))
        idcg = dcg(ideal)
        return dcg(rels) / idcg if idcg > 0 else 0.0

    @staticmethod
    def evaluate_query_detailed(
        qid: str, app_id: str, mode: str, retrieved_ids: List[str],
        scores: List[float], relevant_set: Set[str], qrel: Dict,
        max_k: int, latency: float
    ) -> List[RankedResult]:
        return [
            RankedResult(
                query_id=qid, app_id=app_id, mode=mode,
                rank=rank, doc_id=retrieved_ids[rank-1],
                score=round(scores[rank-1], 6),
                is_relevant=retrieved_ids[rank-1] in relevant_set,
                latency_ms=round(latency, 2)
            )
            for rank in range(1, min(len(retrieved_ids), max_k) + 1)
        ]

    @staticmethod
    def compute_curves(ranked_results: List[RankedResult], max_k: int = 50) -> Dict:
        by_query = defaultdict(list)
        for r in ranked_results: by_query[r.query_id].append(r)

        recall_curve, precision_curve = [], []
        for k in range(1, max_k + 1):
            recalls, precs = [], []
            for qid, results in by_query.items():
                sorted_res = sorted(results, key=lambda x: x.rank)
                retrieved = [r.doc_id for r in sorted_res if r.rank <= k]
                relevant = {r.doc_id for r in sorted_res if r.is_relevant}
                if relevant:
                    recalls.append(RetrievalMetrics.recall_at_k(retrieved, relevant, k))
                    precs.append(RetrievalMetrics.precision_at_k(retrieved, relevant, k))
            if recalls:
                recall_curve.append({"k": k, "recall": round(np.mean(recalls), 4)})
                precision_curve.append({"k": k, "precision": round(np.mean(precs), 4)})
        return {"recall_curve": recall_curve, "precision_curve": precision_curve}

    @staticmethod
    def aggregate_detailed(ranked_results: List[RankedResult], max_k: int = 50) -> Dict:
        curves = RetrievalMetrics.compute_curves(ranked_results, max_k)
        by_query = defaultdict(list)
        for r in ranked_results: by_query[r.query_id].append(r)

        std_metrics = {"k_values": [1, 3, 5, 10, 20, max_k]}
        for k in std_metrics["k_values"]:
            recalls, precs, rrs, ndcgs = [], [], [], []
            for qid, results in by_query.items():
                sorted_res = sorted(results, key=lambda x: x.rank)
                retrieved = [r.doc_id for r in sorted_res if r.rank <= k]
                relevant = {r.doc_id for r in sorted_res if r.is_relevant}
                if relevant or retrieved:
                    recalls.append(RetrievalMetrics.recall_at_k(retrieved, relevant, k))
                    precs.append(RetrievalMetrics.precision_at_k(retrieved, relevant, k))
                    rrs.append(RetrievalMetrics.reciprocal_rank(retrieved, relevant))
                    ndcgs.append(RetrievalMetrics.ndcg_at_k(retrieved, relevant, k))
            
            std_metrics[f"recall@{k}"] = round(np.mean(recalls), 4) if recalls else 0.0
            std_metrics[f"precision@{k}"] = round(np.mean(precs), 4) if precs else 0.0
            std_metrics[f"mrr@{k}"] = round(np.mean(rrs), 4) if rrs else 0.0
            std_metrics[f"ndcg@{k}"] = round(np.mean(ndcgs), 4) if ndcgs else 0.0

        return {"curves": curves, "standard_metrics": std_metrics}