# src/metrics.py
import math
from typing import List, Dict, Set

def recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    """Computes Recall@K: fraction of relevant items retrieved in top K."""
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)

def precision_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    """Computes Precision@K: fraction of top K items that are relevant."""
    if k == 0:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / k

def reciprocal_rank(retrieved: List[str], relevant: Set[str]) -> float:
    """Computes Reciprocal Rank: 1/rank of the first relevant document."""
    for i, doc in enumerate(retrieved, 1):
        if doc in relevant:
            return 1.0 / i
    return 0.0

def ndcg_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    """Computes NDCG@K with binary relevance and standard log2 discounting."""
    rels = [1.0 if doc in relevant else 0.0 for doc in retrieved[:k]]
    if not any(rels):
        return 0.0

    dcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
    ideal_rels = sorted(rels, reverse=True)
    idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(ideal_rels))

    return dcg / idcg if idcg > 0 else 0.0

def compute_query_metrics(
    section_ids: List[str],
    relevant_ids: Set[str],
    eval_ks: List[int]
) -> Dict[str, any]:
    """
    Computes standard retrieval metrics for a single query at multiple K values.
    Returns dict with recall, precision, mrr, and ndcg.
    """

    return {
        "recall": {k: round(recall_at_k(section_ids, relevant_ids, k), 4) for k in eval_ks},
        "precision": {k: round(precision_at_k(section_ids, relevant_ids, k), 4) for k in eval_ks},
        "mrr": round(reciprocal_rank(section_ids, relevant_ids), 4),
        "ndcg": {k: round(ndcg_at_k(section_ids, relevant_ids, k), 4) for k in eval_ks}
    }