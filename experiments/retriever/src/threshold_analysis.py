# src/threshold_analysis.py
import numpy as np
from typing import List, Dict
from collections import defaultdict
from .metrics import RetrievalMetrics, RankedResult

def _stats(scores: List[float]) -> Dict:
    if not scores: return {"count": 0}
    return {
        "count": len(scores), "mean": round(np.mean(scores), 4),
        "std": round(np.std(scores), 4),
        "p25": round(np.percentile(scores, 25), 4),
        "p50": round(np.percentile(scores, 50), 4),
        "p75": round(np.percentile(scores, 75), 4)
    }

def run_threshold_analysis(ranked_results: List[RankedResult], cfg: Dict) -> List[Dict]:
    groups = defaultdict(list)
    for r in ranked_results: groups[(r.app_id, r.mode)].append(r)

    results = []
    target_recall = cfg.get("target_recall")
    min_precision = cfg.get("min_precision")

    for (app_id, mode), group_res in groups.items():
        rel_scores = [r.score for r in group_res if r.is_relevant]
        irr_scores = [r.score for r in group_res if not r.is_relevant]
        dist = {"relevant": _stats(rel_scores), "irrelevant": _stats(irr_scores)}

        unique_scores = sorted(list(set(r.score for r in group_res)), reverse=True)
        candidates = []
        best = {"score_threshold": None, "k": None, "f1": 0.0}

        for thresh in unique_scores:
            filtered = [r for r in group_res if r.score >= thresh]
            if not filtered: continue

            q_filtered = defaultdict(list)
            for r in filtered: q_filtered[r.query_id].append(r)

            recalls, precs = [], []
            for qid, res in q_filtered.items():
                all_q_res = [r for r in group_res if r.query_id == qid]
                relevant = {r.doc_id for r in all_q_res if r.is_relevant}
                if relevant:
                    retrieved = [r.doc_id for r in sorted(res, key=lambda x: x.rank)]
                    recalls.append(RetrievalMetrics.recall_at_k(retrieved, relevant, len(retrieved)))
                    precs.append(RetrievalMetrics.precision_at_k(retrieved, relevant, len(retrieved)))

            if not recalls: continue
            avg_rec, avg_prec = np.mean(recalls), np.mean(precs)
            if target_recall and avg_rec < target_recall: continue
            if min_precision and avg_prec < min_precision: continue

            f1 = 2 * (avg_prec * avg_rec) / (avg_prec + avg_rec) if (avg_prec + avg_rec) > 0 else 0
            k_val = max(r.rank for r in filtered)
            cand = {"score_threshold": round(thresh, 4), "k": k_val, "recall": round(avg_rec, 4), "precision": round(avg_prec, 4), "f1": round(f1, 4)}
            candidates.append(cand)
            if f1 > best["f1"]: best = cand

        results.append({
            "app_id": app_id, "mode": mode,
            "optimal_threshold": best,
            "top_candidates": sorted(candidates, key=lambda x: -x["f1"])[:5],
            "score_distribution": dist,
            "num_results": len(group_res)
        })

    return results