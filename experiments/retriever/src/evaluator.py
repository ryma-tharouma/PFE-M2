# src/evaluator.py
import os
import csv
import json
import time
import math
import gc
import numpy as np
from collections import defaultdict
from typing import List, Dict, Any

from src.factories import get_vector_database, get_embedder, get_aggregator, get_context_manager

def _recall_at_k(retrieved, relevant, k):
    if not relevant: return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)

def _precision_at_k(retrieved, relevant, k):
    if k == 0: return 0.0
    return len(set(retrieved[:k]) & relevant) / k

def _rr(retrieved, relevant):
    for i, doc in enumerate(retrieved, 1):
        if doc in relevant: return 1.0 / i
    return 0.0

def _ndcg_at_k(retrieved, relevant, k):
    rels = [1.0 if d in relevant else 0.0 for d in retrieved[:k]]
    ideal = sorted(rels, reverse=True)
    dcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
    idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0

def compute_query_metrics(section_ids, relevant_ids, eval_ks):
    return {
        "recall": {k: round(_recall_at_k(section_ids, relevant_ids, k), 4) for k in eval_ks},
        "precision": {k: round(_precision_at_k(section_ids, relevant_ids, k), 4) for k in eval_ks},
        "mrr": round(_rr(section_ids, relevant_ids), 4),
        "ndcg_10": round(_ndcg_at_k(section_ids, relevant_ids, min(10, len(section_ids))), 4)
    }

def optimize_thresholds(all_results, modes):
    thresholds = {}
    for mode in modes:
        mode_res = [r for r in all_results if r["mode"] == mode]
        if not mode_res: continue
        scores, relevances = [], []
        for r in mode_res:
            scores.extend(r["search_scores"])
            relevances.extend([1 if sid in r["relevant_ids"] else 0 for sid in r["retrieved_section_ids"]])
        best_f1, best_t = 0.0, 0.0
        for t in sorted(list(set(scores))):
            tp = sum(1 for s, rel in zip(scores, relevances) if s >= t and rel == 1)
            fp = sum(1 for s, rel in zip(scores, relevances) if s >= t and rel == 0)
            fn = sum(1 for s, rel in zip(scores, relevances) if s < t and rel == 1)
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1: best_f1, best_t = f1, t
        thresholds[mode] = {"T_low": round(best_t * 0.85, 4), "T_high": round(best_t, 4), "f1": round(best_f1, 4)}
    return thresholds

def run_evaluate(cfg: dict):
    resolved_results = cfg["paths"]["resolved_results"]
    query_sources = cfg.get("evaluation", {}).get("query_sources", [])
    mt_strategies = cfg.get("multi_turn", {}).get("strategies", ["none"])
    eval_ks = cfg.get("retrieval", {}).get("eval_k_sections", [1, 2, 3, 5, 10])
    max_retrieve = cfg.get("retrieval", {}).get("max_retrieve_sections", 10)
    modes = cfg["indexing"]["modes"]
    db_types = cfg["indexing"].get("db_types", [cfg["database"]["type"]])
    index_types = cfg["indexing"]["index_types"]
    auto_opt = cfg.get("routing", {}).get("auto_optimize", False)
    checkpoint_interval = cfg.get("evaluation", {}).get("checkpoint_every", 50)
    
    all_turns = []
    for src in query_sources:
        path = src["path"]
        if not os.path.exists(path): continue
        with open(path, "r", encoding="utf-8") as f:
            for conv_line in f:
                conv = json.loads(conv_line)
                conv_id, app_id = conv["conversation_id"], conv.get("app_id", "manual_bdm")
                history = []
                for turn in conv["turns"]:
                    all_turns.append({
                        "query_id": f"{conv_id}_t{turn['turn_id']}",
                        "query": turn["user_query"],
                        "history": list(history),
                        "relevant_ids": set(turn.get("relevant_sections", [])),
                        "metadata": turn, "app_id": app_id
                    })
                    history.append(turn)
                    if len(history) > cfg["multi_turn"].get("window_size", 2) + 2: history.pop(0)
                        
    if not all_turns:
        print("⚠️  No queries found to evaluate.")
        return

    print(f"📋 Loaded {len(all_turns)} evaluation turns.")
    all_results = []

    # 🔥 FIX: No global cache. Mode-specific encoding prevents leakage.
    for strategy in mt_strategies:
        print(f"\n🔍 Strategy: {strategy}")
        cfg["multi_turn"]["strategy"] = strategy
        ctx_mgr = get_context_manager(cfg)
        agg = get_aggregator(cfg)
        
        for db_type in db_types:
            cfg["database"]["type"] = db_type
            db = None
            try: db = get_vector_database(cfg)
            except Exception as e:
                print(f"❌ Failed to init DB {db_type}: {e}")
                continue
            print(f"  🗄️ Connected to {db_type}")

            for mode in modes:
                embedder = get_embedder(mode=mode, cfg=cfg)
                
                for idx_type in index_types:
                    config_key = f"{db_type}_{mode}_{idx_type}_{strategy}"
                    detailed_path = os.path.join(resolved_results, f"{config_key}_detailed.csv")
                    csv_fields = ["query_id", "mode", "db_type", "idx_type", "strategy", "top_k", "doc_id", "score", "is_relevant"]
                    if not os.path.exists(detailed_path):
                        with open(detailed_path, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(csv_fields)
                    print(f"  ▶ {config_key}")
                    
                    # Per-mode checkpoint
                    ckpt_path = os.path.join(resolved_results, f"eval_progress_{strategy}_{mode}.jsonl")
                    processed_ids = set()
                    if os.path.exists(ckpt_path):
                        with open(ckpt_path, "r") as f:
                            for line in f: processed_ids.add(json.loads(line)["query_id"])
                        if processed_ids: print(f"    🔄 Resuming {mode} from checkpoint. Skipping {len(processed_ids)} turns.")
                    
                    for i, turn in enumerate(all_turns):
                        if turn["query_id"] in processed_ids: continue
                        
                        context_str = ctx_mgr.build_context(turn["history"], turn["query"])
                        
                        # 🔥 FIX: Strict isolation. Encode fresh per mode. No cross-contamination.
                        q_dense = embedder.encode_dense([context_str])[0] if mode != "sparse" else None
                        q_sparse = embedder.encode_sparse([context_str])[0] if mode != "dense" else None
                        
                        start = time.time()
                        try:
                            coll_name = f"{turn.get('app_id', 'manual_bdm')}_{mode}_{db_type}_{idx_type}"
                            ids, scores = db.search(name=coll_name, q_dense=q_dense, q_sparse=q_sparse, 
                                                    top_k=max_retrieve, alpha=cfg["retrieval"].get("alpha", 0.7), index_type=idx_type)
                        except Exception as e:
                            print(f"    ❌ Search failed for {coll_name}: {e}")
                            ids, scores = [], []
                        latency = (time.time() - start) * 1000
                        
                        chunk_results = [{"id": sid, "score": sc, "payload": {"parent_section_id": sid.rsplit("_c", 1)[0]}} 
                                         for sid, sc in zip(ids, scores)]
                        sections = agg.aggregate(chunk_results)
                        section_ids = [s["section_id"] for s in sections]
                        section_scores = {s["section_id"]: s["score"] for s in sections}
                        
                        metrics = compute_query_metrics(section_ids, turn["relevant_ids"], eval_ks)
                        all_results.append({
                            "query_id": turn["query_id"], "mode": mode, "db_type": db_type,
                            "idx_type": idx_type, "strategy": strategy, "metrics": metrics,
                            "latency_ms": round(latency, 2), "retrieved_section_ids": section_ids,
                            "relevant_ids": list(turn["relevant_ids"]), "search_scores": scores
                        })
                        
                        with open(detailed_path, "a", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            if len(section_ids) == 0:
                                writer.writerow([turn["query_id"], mode, db_type, idx_type, strategy, 1, "NO_RESULTS", 0.0, 0])
                            else:
                                for k in eval_ks:
                                    for rank, sid in enumerate(section_ids[:k], 1):
                                        writer.writerow([turn["query_id"], mode, db_type, idx_type, strategy, k, sid, section_scores.get(sid, 0.0), 1 if sid in turn["relevant_ids"] else 0])
                        
                        processed_ids.add(turn["query_id"])
                        if len(processed_ids) % checkpoint_interval == 0:
                            with open(ckpt_path, "a") as cf: cf.write(json.dumps({"query_id": turn["query_id"]}) + "\n")
                                
                    embedder.cleanup(); del embedder; gc.collect()
            
            if db: del db; gc.collect()
            print(f"  🔒 DB lock released for {db_type}")

    # Thresholds & Summary
    final_thresholds = optimize_thresholds(all_results, modes) if auto_opt else {}
    if auto_opt: print(f"\n🎯 Optimized Thresholds: {json.dumps(final_thresholds, indent=2)}")
        
    grouped = defaultdict(list)
    for r in all_results: grouped[f"{r['db_type']}_{r['mode']}_{r['idx_type']}_{r['strategy']}"].append(r)
    summary = {}
    for key, res_list in grouped.items():
        valid = [r for r in res_list if r["retrieved_section_ids"]]
        if not valid: continue
        summary[key] = {
            "recall": {k: round(np.mean([r["metrics"]["recall"][k] for r in valid]), 4) for k in eval_ks},
            "precision": {k: round(np.mean([r["metrics"]["precision"][k] for r in valid]), 4) for k in eval_ks},
            "mrr": round(np.mean([r["metrics"]["mrr"] for r in valid]), 4),
            "ndcg@10": round(np.mean([r["metrics"]["ndcg_10"] for r in valid]), 4),
            "mean_latency_ms": round(np.mean([r["latency_ms"] for r in valid]), 2)
        }
    with open(os.path.join(resolved_results, "summary_results.json"), "w", encoding="utf-8") as f:
        json.dump({"metrics": summary, "optimized_thresholds": final_thresholds}, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Evaluation complete. Results saved to {resolved_results}/")