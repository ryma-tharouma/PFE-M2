#!/usr/bin/env python3
# compute_metrics.py — CORRECTED VERSION
import pandas as pd
import numpy as np
import json
from collections import defaultdict

def recall_at_k(retrieved, relevant, k):
    if not relevant: return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)

def precision_at_k(retrieved, relevant, k):
    if k == 0: return 0.0
    return len(set(retrieved[:k]) & relevant) / k

def reciprocal_rank(retrieved, relevant):
    for i, doc in enumerate(retrieved, 1):
        if doc in relevant: return 1.0 / i
    return 0.0

def ndcg_at_k(retrieved, relevant, k):
    rels = [1.0 if d in relevant else 0.0 for d in retrieved[:k]]
    ideal = sorted(rels, reverse=True)
    def dcg(scores): return sum((2**s - 1) / np.log2(i+2) for i, s in enumerate(scores))
    idcg = dcg(ideal)
    return dcg(rels) / idcg if idcg > 0 else 0.0

# Load detailed results
df = pd.read_csv("data/results/detailed_results.csv")

# 🔧 FIX: Group by (query_id, mode) instead of just query_id
by_query_mode = defaultdict(list)
for _, row in df.iterrows():
    key = (row["query_id"], row["mode"])
    by_query_mode[key].append(row)

# Compute metrics per (query, mode) pair
results = []
k_values = [1, 3, 5, 10]
for (qid, mode), rows in by_query_mode.items():
    sorted_rows = sorted(rows, key=lambda x: x["rank"])
    retrieved = [r["doc_id"] for r in sorted_rows]
    relevant = {r["doc_id"] for r in sorted_rows if r["is_relevant"]}
    app_id = sorted_rows[0]["app_id"]
    
    metrics = {"query_id": qid, "app_id": app_id, "mode": mode}
    for k in k_values:
        metrics[f"recall@{k}"] = recall_at_k(retrieved, relevant, k)
        metrics[f"precision@{k}"] = precision_at_k(retrieved, relevant, k)
    metrics["rr"] = reciprocal_rank(retrieved, relevant)
    metrics["ndcg@10"] = ndcg_at_k(retrieved, relevant, 10)
    results.append(metrics)

# Aggregate by mode
summary = {}
for mode in df["mode"].unique():
    mode_res = [r for r in results if r["mode"] == mode]
    if not mode_res: continue  # Skip empty modes
    
    agg = {"mode": mode, "num_queries": len(mode_res)}
    for k in k_values:
        agg[f"recall@{k}"] = round(np.mean([r[f"recall@{k}"] for r in mode_res]), 4)
        agg[f"precision@{k}"] = round(np.mean([r[f"precision@{k}"] for r in mode_res]), 4)
    agg["mrr"] = round(np.mean([r["rr"] for r in mode_res]), 4)
    agg["ndcg@10"] = round(np.mean([r["ndcg@10"] for r in mode_res]), 4)
    summary[mode] = agg

# Print nice table
print("\n📊 AGGREGATED METRICS")
print("="*70)
for mode, m in sorted(summary.items()):
    print(f"\n{mode.upper()}")
    print(f"  Queries: {m['num_queries']}")
    for k in k_values:
        print(f"  Recall@{k}:    {m[f'recall@{k}']:.3f} | Precision@{k}: {m[f'precision@{k}']:.3f}")
    print(f"  MRR:         {m['mrr']:.3f} | NDCG@10: {m['ndcg@10']:.3f}")

# Export
with open("data/results/metrics_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(f"\n✅ Metrics saved to data/results/metrics_summary.json")