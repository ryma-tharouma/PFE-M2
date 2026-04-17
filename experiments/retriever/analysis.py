# src/analysis.py
import os
import json
import csv
import yaml
import numpy as np
from collections import defaultdict
from typing import Dict, List, Set, Any, Tuple

from src.metrics import recall_at_k, precision_at_k, ndcg_at_k, reciprocal_rank


def load_conversation_data_from_files(query_sources: List[Dict]) -> Tuple[Dict[str, Set[str]], Dict[str, Any]]:
    """Load ground truth and metadata from a list of query source dicts."""
    relevant = {}
    query_metadata = {}
    for src in query_sources:
        path = src["path"]
        if not os.path.exists(path):
            print(f"Warning: Conversation file not found: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                conv = json.loads(line)
                conv_id = conv["conversation_id"]
                app_id = conv.get("app_id", "unknown")
                for turn in conv["turns"]:
                    turn_id = turn["turn_id"]
                    qid = f"{conv_id}_t{turn_id}"
                    relevant[qid] = set(turn.get("relevant_sections", []))
                    
                    # Check if rewritten_query exists (has value)
                    rewritten_query = turn.get("rewritten_query")
                    has_rewrite = rewritten_query is not None and str(rewritten_query).strip() != ""
                    
                    query_metadata[qid] = {
                        "app_id": app_id,
                        "query_quality": turn.get("query_quality", "unknown"),
                        "routing_label": turn.get("routing_label", "unknown"),
                        "user_query": turn.get("user_query", ""),
                        "rewritten_query": rewritten_query,
                        "has_rewrite": has_rewrite,  # Ground truth: rewrite exists
                    }
    return relevant, query_metadata


def load_conversation_data_from_single_file(conv_path: str) -> Tuple[Dict[str, Set[str]], Dict[str, Any]]:
    """Load ground truth from a single conversation JSONL file."""
    relevant = {}
    query_metadata = {}
    if not os.path.exists(conv_path):
        print(f"Error: Conversation file not found: {conv_path}")
        return relevant, query_metadata
    with open(conv_path, "r", encoding="utf-8") as f:
        for line in f:
            conv = json.loads(line)
            conv_id = conv["conversation_id"]
            app_id = conv.get("app_id", "unknown")
            for turn in conv["turns"]:
                turn_id = turn["turn_id"]
                qid = f"{conv_id}_t{turn_id}"
                relevant[qid] = set(turn.get("relevant_sections", []))
                
                # Check if rewritten_query exists (has value)
                rewritten_query = turn.get("rewritten_query")
                has_rewrite = rewritten_query is not None and str(rewritten_query).strip() != ""
                
                query_metadata[qid] = {
                    "app_id": app_id,
                    "query_quality": turn.get("query_quality", "unknown"),
                    "routing_label": turn.get("routing_label", "unknown"),
                    "user_query": turn.get("user_query", ""),
                    "rewritten_query": rewritten_query,
                    "has_rewrite": has_rewrite,  # Ground truth: rewrite exists
                }
    return relevant, query_metadata


def load_csv_data(csv_path: str,
                  relevant_mapping: Dict[str, Set[str]],
                  query_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Load one CSV file and return per-query data with scores."""
    queries = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row["query_id"]
            
            # Skip if query not in ground truth
            if qid not in relevant_mapping:
                continue
            
            # Get metadata from conversation file
            metadata = query_metadata.get(qid, {})
            
            # Initialize query entry on first row
            if qid not in queries:
                # Get is_rewritten from CSV (system used rewrite)
                is_rewritten = row.get("is_rewritten", "False").lower() == "true"
                
                queries[qid] = {
                    "retrieved": [],
                    "scores": [],
                    "relevance": [],
                    "latency_ms": float(row.get("latency_ms", 0.0)),
                    "query_quality": metadata.get("query_quality", "unknown"),
                    "routing_label": metadata.get("routing_label", "unknown"),
                    "app_id": metadata.get("app_id", "unknown"),
                    "has_rewrite": metadata.get("has_rewrite", False),  # Ground truth: rewrite exists
                    "is_rewritten": is_rewritten,  # System: was rewrite used?
                }
            
            # Append retrieved document info
            doc_id = row["doc_id"]
            score = float(row.get("score", 0.0))
            is_relevant = int(row.get("is_relevant", 0))
            
            queries[qid]["retrieved"].append(doc_id)
            queries[qid]["scores"].append(score)
            queries[qid]["relevance"].append(is_relevant)
    
    return queries


def get_app_section_counts(apps_dir: str) -> Dict[str, int]:
    """Load RAG articles and count sections per app."""
    app_counts = {}
    rag_final_dir = os.path.join(apps_dir, "rag_final")
    
    if not os.path.exists(rag_final_dir):
        print(f"Warning: rag_final directory not found at {rag_final_dir}")
        return app_counts
    
    for json_file in os.listdir(rag_final_dir):
        if json_file.endswith(".json"):
            app_name = json_file.replace(".json", "")
            json_path = os.path.join(rag_final_dir, json_file)
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                    app_counts[app_name] = len(articles)
            except Exception as e:
                print(f"Warning: Could not load {json_file}: {e}")
    
    return app_counts


def compute_metrics_for_queries(queries: Dict[str, Any],
                                relevant_mapping: Dict[str, Set[str]],
                                app_section_counts: Dict[str, int],
                                k_values: List[int]) -> Dict[str, Any]:
    """
    Compute weighted metrics over a set of queries.
    Weighted by app section count.
    """
    prec = {k: [] for k in k_values}
    rec = {k: [] for k in k_values}
    ndcg = {k: [] for k in k_values}
    mrr_vals = []
    latencies = []
    app_weights = []  # Track weights for each query

    for qid, data in queries.items():
        retrieved = data["retrieved"]
        relevant_set = relevant_mapping.get(qid, set())
        app_id = data.get("app_id", "unknown")
        
        # Get weight (section count for this app)
        weight = app_section_counts.get(app_id, 1)
        
        if not relevant_set:
            continue
        
        latencies.append(data["latency_ms"])
        app_weights.append(weight)

        for k in k_values:
            rec_val = recall_at_k(retrieved, relevant_set, k)
            prec_val = precision_at_k(retrieved, relevant_set, k)
            ndcg_val = ndcg_at_k(retrieved, relevant_set, k)
            rec[k].append(rec_val)
            prec[k].append(prec_val)
            ndcg[k].append(ndcg_val)

        mrr_vals.append(reciprocal_rank(retrieved, relevant_set))

    # Compute weighted averages
    if app_weights:
        total_weight = sum(app_weights)
        prec_weighted = {}
        rec_weighted = {}
        ndcg_weighted = {}
        
        for k in k_values:
            if prec[k]:
                prec_weighted[k] = round(
                    sum(p * w for p, w in zip(prec[k], app_weights)) / total_weight, 4
                )
            if rec[k]:
                rec_weighted[k] = round(
                    sum(r * w for r, w in zip(rec[k], app_weights)) / total_weight, 4
                )
            if ndcg[k]:
                ndcg_weighted[k] = round(
                    sum(n * w for n, w in zip(ndcg[k], app_weights)) / total_weight, 4
                )
    else:
        prec_weighted = rec_weighted = ndcg_weighted = {}

    # Compute weighted MRR
    mrr_weighted = round(np.mean(mrr_vals), 4) if mrr_vals else 0.0

    return {
        "precision": {str(k): prec_weighted.get(k, 0.0) for k in k_values},
        "recall": {str(k): rec_weighted.get(k, 0.0) for k in k_values},
        "ndcg": {str(k): ndcg_weighted.get(k, 0.0) for k in k_values},
        "mrr": mrr_weighted,
        "latency_stats": {
            "min_ms": round(min(latencies), 2),
            "q1_ms": round(np.percentile(latencies, 25), 2),
            "q2_ms": round(np.percentile(latencies, 50), 2),
            "q3_ms": round(np.percentile(latencies, 75), 2),
            "max_ms": round(max(latencies), 2),
            "mean_ms": round(np.mean(latencies), 2),
        } if latencies else {},
        "query_count": len(queries),
    }


def group_by_failure(queries: Dict[str, Any]) -> Dict[str, List[str]]:
    """Group queries by quality and rewrite status."""
    groups = {
        # By query quality
        "all_well_written": [],
        "all_poorly_written": [],
        "all_ambiguous": [],
        
        # Ground truth: rewrite exists?
        "all_has_rewrite": [],
        "all_no_rewrite": [],
        
        # System: rewrite was used?
        "all_rewritten": [],
        "all_not_rewritten": [],
        
        # Combinations: Ground truth vs System
        "has_rewrite_and_rewritten": [],      # ✓ Correct
        "has_rewrite_not_rewritten": [],      # ✗ False negative
        "no_rewrite_and_rewritten": [],       # ✗ False positive
        "no_rewrite_not_rewritten": [],       # ✓ Correct
        
        # Quality + has_rewrite
        "well_written_has_rewrite": [],
        "well_written_no_rewrite": [],
        "poorly_written_has_rewrite": [],
        "poorly_written_no_rewrite": [],
        "ambiguous_has_rewrite": [],
        "ambiguous_no_rewrite": [],
    }
    
    for qid, data in queries.items():
        qq = data["query_quality"]
        has_rw = data["has_rewrite"]  # Ground truth: rewrite exists
        is_rw = data["is_rewritten"]  # System: rewrite was used
        
        # By quality
        if qq == "well_written":
            groups["all_well_written"].append(qid)
        elif qq == "poorly_written":
            groups["all_poorly_written"].append(qid)
        elif qq == "ambiguous":
            groups["all_ambiguous"].append(qid)
        
        # By ground truth rewrite existence
        if has_rw:
            groups["all_has_rewrite"].append(qid)
        else:
            groups["all_no_rewrite"].append(qid)
        
        # By system rewrite usage
        if is_rw:
            groups["all_rewritten"].append(qid)
        else:
            groups["all_not_rewritten"].append(qid)
        
        # Combinations: ground truth vs system
        if has_rw and is_rw:
            groups["has_rewrite_and_rewritten"].append(qid)  # ✓
        elif has_rw and not is_rw:
            groups["has_rewrite_not_rewritten"].append(qid)  # ✗
        elif not has_rw and is_rw:
            groups["no_rewrite_and_rewritten"].append(qid)  # ✗
        elif not has_rw and not is_rw:
            groups["no_rewrite_not_rewritten"].append(qid)  # ✓
        
        # Quality + has_rewrite
        if qq == "well_written" and has_rw:
            groups["well_written_has_rewrite"].append(qid)
        elif qq == "well_written" and not has_rw:
            groups["well_written_no_rewrite"].append(qid)
        elif qq == "poorly_written" and has_rw:
            groups["poorly_written_has_rewrite"].append(qid)
        elif qq == "poorly_written" and not has_rw:
            groups["poorly_written_no_rewrite"].append(qid)
        elif qq == "ambiguous" and has_rw:
            groups["ambiguous_has_rewrite"].append(qid)
        elif qq == "ambiguous" and not has_rw:
            groups["ambiguous_no_rewrite"].append(qid)
    
    return groups


def group_by_app(queries: Dict[str, Any]) -> Dict[str, List[str]]:
    """Group queries by application."""
    app_groups = defaultdict(list)
    for qid, data in queries.items():
        app_groups[data["app_id"]].append(qid)
    return dict(app_groups)


def group_by_routing(queries: Dict[str, Any]) -> Dict[str, List[str]]:
    """Group queries by routing label."""
    routing_groups = defaultdict(list)
    for qid, data in queries.items():
        routing_groups[data["routing_label"]].append(qid)
    return dict(routing_groups)


def analyze_routing_thresholds(queries: Dict[str, Any],
                               relevant_mapping: Dict[str, Set[str]]) -> Dict[str, Any]:
    """
    Analyze routing performance, especially for OOD queries.
    Find max score when wrong document is retrieved.
    """
    analysis = {}
    routing_groups = group_by_routing(queries)
    
    for routing_label, qid_list in routing_groups.items():
        if not qid_list:
            continue
        
        max_scores_false_positives = []
        all_scores = []
        false_positive_count = 0
        total_ood_queries = 0
        
        for qid in qid_list:
            relevant_set = relevant_mapping.get(qid, set())
            data = queries[qid]
            scores = data.get("scores", [])
            retrieved = data.get("retrieved", [])
            
            if routing_label == "ood":
                total_ood_queries += 1
                # For OOD queries, relevant_set should be empty
                if not relevant_set and retrieved and scores:
                    # All retrieved docs are false positives
                    false_positive_count += 1
                    max_scores_false_positives.append(max(scores))
                    all_scores.extend(scores)
            else:
                # For FAQ/RAG, track wrong retrievals
                if relevant_set and retrieved and scores:
                    for doc_id, score in zip(retrieved, scores):
                        if doc_id not in relevant_set:
                            all_scores.append(score)
        
        analysis[routing_label] = {
            "total_queries": len(qid_list),
            "query_count": len(qid_list),
        }
        
        if routing_label == "ood":
            analysis[routing_label].update({
                "has_retrieved_docs": false_positive_count,
                "false_positive_rate": round(false_positive_count / total_ood_queries, 4) if total_ood_queries > 0 else 0.0,
                "max_score_when_wrong": round(max(max_scores_false_positives), 4) if max_scores_false_positives else 0.0,
                "min_score_when_wrong": round(min(max_scores_false_positives), 4) if max_scores_false_positives else 0.0,
                "mean_score_when_wrong": round(np.mean(max_scores_false_positives), 4) if max_scores_false_positives else 0.0,
                "p75_score_when_wrong": round(np.percentile(max_scores_false_positives, 75), 4) if max_scores_false_positives else 0.0,
                "p95_score_when_wrong": round(np.percentile(max_scores_false_positives, 95), 4) if max_scores_false_positives else 0.0,
                "suggested_threshold": round(np.percentile(max_scores_false_positives, 75), 4) if max_scores_false_positives else 0.0,
            })
        else:
            if all_scores:
                analysis[routing_label].update({
                    "wrong_retrievals": len(all_scores),
                    "max_score_wrong": round(max(all_scores), 4),
                    "min_score_wrong": round(min(all_scores), 4),
                    "mean_score_wrong": round(np.mean(all_scores), 4),
                    "p75_score_wrong": round(np.percentile(all_scores, 75), 4),
                    "p95_score_wrong": round(np.percentile(all_scores, 95), 4),
                    "suggested_threshold": round(np.percentile(all_scores, 75), 4),
                })
    
    return analysis


def analyze(cfg: dict, results_dir: str = None, conv_file: str = None):
    """
    Main analysis pipeline.
    Generates 4 separate result files:
    1. general_metrics.json - weighted by app section count
    2. per_app_metrics.json - per application
    3. failure_analysis.json - by query quality/rewrite status, weighted by group count
    4. routing_analysis.json - OOD detection and threshold analysis
    """
    
    # Get max_k from config
    max_k_list = cfg.get("retrieval", {}).get("eval_k_sections", list(range(1, 11)))
    print(f"Using k values from config: {max_k_list}")
    
    # Determine results directory
    if results_dir is None:
        experiment_name = cfg.get("experiment", {}).get("name")
        if not experiment_name:
            experiment_name = cfg.get("name") or cfg.get("experiment_name")
        if experiment_name:
            results_dir = os.path.join("data", "results", experiment_name)
        else:
            paths = cfg.get("paths", {})
            results_dir = paths.get("resolved_results") or paths.get("results_dir") or paths.get("output_dir")
            if not results_dir:
                raise ValueError("Could not determine results directory.")
    
    if not os.path.exists(results_dir):
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    # Load ground truth
    if conv_file:
        relevant_mapping, query_metadata = load_conversation_data_from_single_file(conv_file)
    else:
        query_sources = cfg.get("evaluation", {}).get("query_sources", [])
        if not query_sources:
            conversations_dir = cfg.get("paths", {}).get("conversations_dir", "data/conversations/")
            default_path = os.path.join(conversations_dir, "original_turns.jsonl")
            if os.path.exists(default_path):
                relevant_mapping, query_metadata = load_conversation_data_from_single_file(default_path)
            else:
                relevant_mapping, query_metadata = {}, {}
        else:
            relevant_mapping, query_metadata = load_conversation_data_from_files(query_sources)
    
    print(f"Loaded {len(relevant_mapping)} queries with ground truth.")

    if not relevant_mapping:
        print("No ground truth queries loaded.")
        return

    # Load app section counts
    apps_dir = cfg.get("paths", {}).get("apps_dir", "data/apps/")
    app_section_counts = get_app_section_counts(apps_dir)
    print(f"Loaded app section counts: {app_section_counts}")

    # Find all CSV files
    csv_files = [f for f in os.listdir(results_dir) if f.endswith(".csv")]
    if not csv_files:
        print("No CSV files found.")
        return

    general = {}
    per_app = {}
    failure = {}
    routing = {}

    for csv_file in csv_files:
        csv_path = os.path.join(results_dir, csv_file)
        
        print(f"\nProcessing {csv_file}...")
        
        queries = load_csv_data(csv_path, relevant_mapping, query_metadata)
        
        if not queries:
            print(f"  ✗ No valid queries in {csv_file}")
            continue

        # Extract config key from filename
        config_key = csv_file.replace(".csv", "")

        print(f"  ✓ Loaded {len(queries)} queries")

        # === GENERAL METRICS (weighted by app section count) ===
        general[config_key] = compute_metrics_for_queries(
            queries, relevant_mapping, app_section_counts, max_k_list
        )
        print(f"    General metrics computed")

        # === FAILURE ANALYSIS (weighted by group size) ===
        failure_groups = group_by_failure(queries)
        failure[config_key] = {}
        
        for group_name, qid_list in failure_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: queries[qid] for qid in qid_list}
            failure[config_key][group_name] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Failure analysis computed ({len(failure[config_key])} groups)")

        # === PER-APP METRICS ===
        app_groups = group_by_app(queries)
        per_app[config_key] = {}
        
        for app_id, qid_list in app_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: queries[qid] for qid in qid_list}
            per_app[config_key][app_id] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Per-app metrics computed ({len(per_app[config_key])} apps)")

        # === ROUTING ANALYSIS ===
        routing[config_key] = analyze_routing_thresholds(queries, relevant_mapping)
        print(f"    Routing analysis computed ({len(routing[config_key])} routing labels)")

    # Save outputs
    general_path = os.path.join(results_dir, "general_metrics.json")
    with open(general_path, "w", encoding="utf-8") as f:
        json.dump(general, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved: {general_path}")

    per_app_path = os.path.join(results_dir, "per_app_metrics.json")
    with open(per_app_path, "w", encoding="utf-8") as f:
        json.dump(per_app, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {per_app_path}")

    failure_path = os.path.join(results_dir, "failure_analysis.json")
    with open(failure_path, "w", encoding="utf-8") as f:
        json.dump(failure, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {failure_path}")

    routing_path = os.path.join(results_dir, "routing_analysis.json")
    with open(routing_path, "w", encoding="utf-8") as f:
        json.dump(routing, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {routing_path}")

    print(f"\n✅ Analysis complete! Results saved to {results_dir}/")
    print(f"  📊 general_metrics.json (weighted by app section count)")
    print(f"  📊 per_app_metrics.json (per application)")
    print(f"  📊 failure_analysis.json (by query quality/rewrite, weighted by group size)")
    print(f"  📊 routing_analysis.json (OOD detection & thresholds)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to config YAML")
    parser.add_argument("--results_dir", type=str, default=None, help="Override results directory")
    parser.add_argument("--conv_file", type=str, default=None, help="Path to conversation JSONL file")
    
    args = parser.parse_args()
    
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)
    
    analyze(cfg, results_dir=args.results_dir, conv_file=args.conv_file)