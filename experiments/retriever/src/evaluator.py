# src/evaluator.py
import os, time, json, gc, numpy as np, csv
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from .data_loader import load_queries, build_qrels
from .embedder import BGEEmbedder
from .metrics import RetrievalMetrics
from .vector_db import get_vector_db

@dataclass
class RankedResult:
    query_id: str; app_id: str; mode: str; db_type: str; index_type: str
    rank: int; doc_id: str; score: float; is_relevant: bool; latency_ms: float

def run_evaluate(cfg: dict):
    queries_path = cfg["paths"]["queries_path"]
    results_dir = cfg["paths"]["results_dir"]
    db_types = cfg["phases"]["evaluate"]["db_types"]
    index_types = cfg["phases"]["evaluate"]["index_types"]
    modes = cfg["phases"]["evaluate"]["modes"]
    max_k = cfg["phases"]["evaluate"].get("max_k", 50)
    alpha = cfg["phases"]["evaluate"].get("alpha", 0.7)
    
    queries = load_queries(queries_path)
    qrels = build_qrels(queries)
    detailed_path = os.path.join(results_dir, "detailed_results.csv")
    all_ranked = []

    fieldnames = list(RankedResult.__dataclass_fields__.keys())
    with open(detailed_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    for db_type in db_types:
        cfg["database"]["type"] = db_type
        db = get_vector_db(cfg)
        
        for index_type in index_types:
            for mode in modes:
                print(f"\n🔎 Evaluating: db={db_type} | idx={index_type} | mode={mode}")
                embedder = BGEEmbedder(mode=mode, cfg=cfg["model"])
                
                for q in queries:
                    qid, app_id, q_text = q["id"], q["app_id"], q["query"]
                    coll_name = f"{app_id}_{mode}_{db_type}_{index_type}"
                    if not db.collection_exists(coll_name): continue
                    
                    q_dense = embedder.encode_dense([q_text])[0] if mode != "sparse" else None
                    q_sparse = embedder.encode_sparse([q_text])[0] if mode != "dense" else None
                    
                    start = time.time()
                    retrieved_ids, scores = db.search(coll_name, q_dense, q_sparse, max_k, alpha, index_type)
                    latency_ms = (time.time() - start) * 1000
                    
                    rel_set = qrels.get(qid, set())
                    detailed = RetrievalMetrics.evaluate_query_detailed(
                        qid, app_id, mode, retrieved_ids, scores, rel_set, {}, max_k, latency_ms
                    )
                    # Inject DB/Index tracking
                    for r in detailed:
                        r.db_type = db_type; r.index_type = index_type
                    
                    all_ranked.extend(detailed)
                    # Append to CSV incrementally
                    with open(detailed_path, "a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writerows([asdict(r) for r in detailed])
                        
                print(f"   ✅ {mode} evaluated")
                embedder.cleanup(); gc.collect()

    # Threshold Analysis
    if all_ranked:
        from .threshold_analysis import run_threshold_analysis
        threshold_results = run_threshold_analysis(all_ranked, cfg.get("threshold_analysis", {}))
        t_path = os.path.join(results_dir, "threshold_analysis.jsonl")
        with open(t_path, "w", encoding="utf-8") as f:
            for res in threshold_results: f.write(json.dumps(res, ensure_ascii=False) + "\n")
        print(f"🎯 Threshold analysis saved to {t_path}")

    # Summary Metrics
    summary = {}
    build_stats = {}
    bm_path = os.path.join(results_dir, "build_metrics.jsonl")
    if os.path.exists(bm_path):
        with open(bm_path, "r") as f:
            for line in f:
                m = json.loads(line)
                build_stats.setdefault(m["mode"], {}).setdefault(f"{m['db_type']}_{m['index_type']}", []).append(m["build_time_sec"])
                
    def stats(vals):
        if not vals: return {"min":0,"q1":0,"q2":0,"q3":0,"max":0,"mean":0}
        a = np.array(vals); return {k: round(float(v), 3) for k, v in {"min":np.min(a),"q1":np.percentile(a,25),"q2":np.percentile(a,50),"q3":np.percentile(a,75),"max":np.max(a),"mean":np.mean(a)}.items()}

    for db_type in db_types:
        for index_type in index_types:
            for mode in modes:
                key = f"{mode}_{db_type}_{index_type}"
                res = [r for r in all_ranked if r.mode==mode and r.db_type==db_type and r.index_type==index_type]
                agg = RetrievalMetrics.aggregate_detailed(res, max_k)
                std = agg.get("standard_metrics", {})
                latencies = [r.latency_ms for r in res]
                
                summary[key] = {
                    "mode": mode, "db_type": db_type, "index_type": index_type,
                    "metrics": {k: std.get(k, 0.0) for k in ["recall@1","precision@1","recall@3","precision@3","mrr@10","ndcg@10"]},
                    "latency": {"index": stats(build_stats.get(mode, {}).get(f"{db_type}_{index_type}", [])), "search": stats(latencies)}
                }
                
    s_path = os.path.join(results_dir, "summary_results.json")
    with open(s_path, "w", encoding="utf-8") as f: json.dump(summary, f, indent=2)
    print(f"\n📊 Summary saved to {s_path}")