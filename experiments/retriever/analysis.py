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
                conv    = json.loads(line)
                conv_id = conv["conversation_id"]
                app_id  = conv.get("app_id", "unknown")
                for turn in conv["turns"]:
                    turn_id = turn["turn_id"]
                    qid     = f"{conv_id}_t{turn_id}"
                    relevant[qid] = set(turn.get("relevant_sections", []))
                    query_metadata[qid] = {
                        "app_id":        app_id,
                        "query_quality": turn.get("query_quality", "unknown"),
                        "routing_label": turn.get("routing_label", "unknown"),
                        "user_query":    turn.get("user_query", ""),
                        "isfollow_up":  bool(turn.get("isfollow_up", False)),
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
            if qid not in relevant_mapping:
                continue
            metadata = query_metadata.get(qid, {})
            if qid not in queries:
                queries[qid] = {
                    "retrieved":     [],
                    "scores":        [],
                    "relevance":     [],
                    "latency_ms":    float(row.get("latency_ms", 0.0)),
                    "query_quality": metadata.get("query_quality", "unknown"),
                    "routing_label": metadata.get("routing_label", "unknown"),
                    "app_id":        metadata.get("app_id", "unknown"),
                    "isfollow_up":  metadata.get("isfollow_up", False),
                }
            queries[qid]["retrieved"].append(row["doc_id"])
            queries[qid]["scores"].append(float(row.get("score", 0.0)))
            queries[qid]["relevance"].append(int(row.get("is_relevant", 0)))
    return queries


def get_app_section_counts(apps_dir: str) -> Dict[str, int]:
    """Load RAG articles from apps_dir (each JSON file = one app, list of sections)."""
    app_counts = {}
    if not os.path.exists(apps_dir):
        print(f"Warning: apps directory not found: {apps_dir}")
        return app_counts

    for json_file in os.listdir(apps_dir):
        if json_file.endswith(".json"):
            app_name  = json_file.replace(".json", "")
            json_path = os.path.join(apps_dir, json_file)
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
    OOD queries (empty relevant_set) are ignored entirely.
    """
    prec     = {k: [] for k in k_values}
    rec      = {k: [] for k in k_values}
    ndcg     = {k: [] for k in k_values}
    mrr_vals = []
    latencies   = []
    app_weights = []

    for qid, data in queries.items():
        retrieved    = data["retrieved"]
        relevant_set = relevant_mapping.get(qid, set())
        app_id       = data.get("app_id", "unknown")
        weight       = app_section_counts.get(app_id, 1)

        if not relevant_set:
            continue

        latencies.append(data["latency_ms"])
        app_weights.append(weight)

        for k in k_values:
            rec[k].append(recall_at_k(retrieved, relevant_set, k))
            prec[k].append(precision_at_k(retrieved, relevant_set, k))
            ndcg[k].append(ndcg_at_k(retrieved, relevant_set, k))

        mrr_vals.append(reciprocal_rank(retrieved, relevant_set))

    if app_weights:
        total_weight = sum(app_weights)
        prec_weighted  = {}
        rec_weighted   = {}
        ndcg_weighted  = {}

        for k in k_values:
            prec_weighted[k] = round(
                sum(p * w for p, w in zip(prec[k], app_weights)) / total_weight, 4
            )
            rec_weighted[k] = round(
                sum(r * w for r, w in zip(rec[k], app_weights)) / total_weight, 4
            )
            ndcg_weighted[k] = round(
                sum(n * w for n, w in zip(ndcg[k], app_weights)) / total_weight, 4
            )

        weighted_mrr = round(
            sum(mrr * w for mrr, w in zip(mrr_vals, app_weights)) / total_weight, 4
        )
    else:
        prec_weighted  = {k: 0.0 for k in k_values}
        rec_weighted   = {k: 0.0 for k in k_values}
        ndcg_weighted  = {k: 0.0 for k in k_values}
        weighted_mrr   = 0.0

    return {
        "precision": {str(k): prec_weighted[k] for k in k_values},
        "recall":    {str(k): rec_weighted[k]  for k in k_values},
        "ndcg":      {str(k): ndcg_weighted[k] for k in k_values},
        "mrr":       weighted_mrr,
        "latency_stats": {
            "min_ms":  round(min(latencies), 2),
            "q1_ms":   round(np.percentile(latencies, 25), 2),
            "q2_ms":   round(np.percentile(latencies, 50), 2),
            "q3_ms":   round(np.percentile(latencies, 75), 2),
            "max_ms":  round(max(latencies), 2),
            "mean_ms": round(np.mean(latencies), 2),
        } if latencies else {},
        "query_count": len(app_weights),
    }


def group_by_failure(queries: Dict[str, Any]) -> Dict[str, List[str]]:
    """Group queries by quality and follow-up status."""
    groups = {
        "well_written":                  [],
        "poorly_written":                [],
        "isfollow_up":                  [],
        "not_follow_up":                 [],
        "well_written_follow_up":        [],
        "well_written_not_follow_up":    [],
        "poorly_written_follow_up":      [],
        "poorly_written_not_follow_up":  [],
    }

    for qid, data in queries.items():
        qq        = data["query_quality"]
        is_follow = data["isfollow_up"]

        if qq == "well_written":
            groups["well_written"].append(qid)
        elif qq == "poorly_written":
            groups["poorly_written"].append(qid)

        if is_follow:
            groups["isfollow_up"].append(qid)
        else:
            groups["not_follow_up"].append(qid)

        if qq == "well_written" and is_follow:
            groups["well_written_follow_up"].append(qid)
        elif qq == "well_written" and not is_follow:
            groups["well_written_not_follow_up"].append(qid)
        elif qq == "poorly_written" and is_follow:
            groups["poorly_written_follow_up"].append(qid)
        elif qq == "poorly_written" and not is_follow:
            groups["poorly_written_not_follow_up"].append(qid)

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
    For OOD: collects all scores of retrieved documents (all are false positives).
    For FAQ/RAG: collects scores of non-relevant retrieved documents.
    """
    analysis       = {}
    routing_groups = group_by_routing(queries)

    for routing_label, qid_list in routing_groups.items():
        if not qid_list:
            continue

        all_scores            = []
        total_retrieved       = 0
        wrong_retrieval_count = 0

        for qid in qid_list:
            data   = queries[qid]
            scores = data.get("scores", [])

            if routing_label == "ood":
                all_scores.extend(scores)
                total_retrieved += len(scores)
            else:
                relevant_set = relevant_mapping.get(qid, set())
                retrieved    = data.get("retrieved", [])
                for doc_id, score in zip(retrieved, scores):
                    if doc_id not in relevant_set:
                        all_scores.append(score)
                        wrong_retrieval_count += 1
                total_retrieved += len(scores)

        analysis[routing_label] = {
            "query_count":          len(qid_list),
            "total_retrieved_docs": total_retrieved,
        }

        if routing_label == "ood":
            if all_scores:
                analysis[routing_label].update({
                    "min_score":  round(min(all_scores), 4),
                    "max_score":  round(max(all_scores), 4),
                    "mean_score": round(np.mean(all_scores), 4),
                    "p75_score":  round(np.percentile(all_scores, 75), 4),
                    "p95_score":  round(np.percentile(all_scores, 95), 4),
                })
        else:
            if all_scores:
                analysis[routing_label].update({
                    "wrong_retrievals":   wrong_retrieval_count,
                    "min_score_wrong":    round(min(all_scores), 4),
                    "max_score_wrong":    round(max(all_scores), 4),
                    "mean_score_wrong":   round(np.mean(all_scores), 4),
                    "p75_score_wrong":    round(np.percentile(all_scores, 75), 4),
                    "p95_score_wrong":    round(np.percentile(all_scores, 95), 4),
                })

    return analysis


def analyze(cfg: dict, results_dir: str = None, conv_file: str = None):
    """
    Main analysis pipeline.
    Generates 4 separate result files:
    1. general_metrics.json  - weighted by app section count
    2. per_app_metrics.json  - per application
    3. failure_analysis.json - by query quality/follow-up status, weighted by app section count
    4. routing_analysis.json - OOD score statistics & wrong retrievals
    """
    max_k_list = cfg.get("retrieval", {}).get("eval_k_sections", list(range(1, 11)))
    print(f"Using k values from config: {max_k_list}")

    if results_dir is None:
        experiment_name = cfg.get("experiment", {}).get("name")
        if not experiment_name:
            experiment_name = cfg.get("name") or cfg.get("experiment_name")
        if experiment_name:
            results_dir = os.path.join("data", "results", experiment_name)
        else:
            paths       = cfg.get("paths", {})
            results_dir = paths.get("resolved_results") or paths.get("results_dir") or paths.get("output_dir")
            if not results_dir:
                raise ValueError("Could not determine results directory.")

    if not os.path.exists(results_dir):
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    query_sources = cfg.get("evaluation", {}).get("query_sources", [])
    if not query_sources and conv_file:
        query_sources = [{"path": conv_file}]
    elif not query_sources:
        conversations_dir = cfg.get("paths", {}).get("conversations_dir", "data/conversations/")
        default_path      = os.path.join(conversations_dir, "original_turns.jsonl")
        if os.path.exists(default_path):
            query_sources = [{"path": default_path}]

    if not query_sources:
        print("No query sources found.")
        return

    relevant_mapping, query_metadata = load_conversation_data_from_files(query_sources)
    print(f"Loaded {len(relevant_mapping)} queries with ground truth.")

    if not relevant_mapping:
        print("No ground truth queries loaded.")
        return

    apps_dir          = cfg.get("paths", {}).get("apps_dir", "data/apps/")
    app_section_counts = get_app_section_counts(apps_dir)
    print(f"Loaded app section counts: {app_section_counts}")

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

        config_key = csv_file.replace(".csv", "")
        print(f"  ✓ Loaded {len(queries)} queries")

        general[config_key] = compute_metrics_for_queries(
            queries, relevant_mapping, app_section_counts, max_k_list
        )
        print(f"    General metrics computed")

        non_ood_queries = {
            qid: data for qid, data in queries.items()
            if data["routing_label"] != "ood"
        }

        failure_groups = group_by_failure(non_ood_queries)
        failure[config_key] = {}
        for group_name, qid_list in failure_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: non_ood_queries[qid] for qid in qid_list}
            failure[config_key][group_name] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Failure analysis computed ({len(failure[config_key])} groups)")

        app_groups     = group_by_app(non_ood_queries)
        per_app[config_key] = {}
        for app_id, qid_list in app_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: non_ood_queries[qid] for qid in qid_list}
            per_app[config_key][app_id] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Per-app metrics computed ({len(per_app[config_key])} apps)")

        routing[config_key] = analyze_routing_thresholds(queries, relevant_mapping)
        print(f"    Routing analysis computed ({len(routing[config_key])} routing labels)")

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

    print(f"\nAnalysis complete! Results saved to {results_dir}/")
    print(f"  general_metrics.json  (weighted by app section count)")
    print(f"  per_app_metrics.json  (per application)")
    print(f"  failure_analysis.json (by query quality/follow-up, weighted by app section count)")
    print(f"  routing_analysis.json (OOD score statistics & wrong retrievals)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config",      type=str, required=True, help="Path to config YAML")
    parser.add_argument("--results_dir", type=str, default=None,  help="Override results directory")
    parser.add_argument("--conv_file",   type=str, default=None,  help="Path to conversation JSONL file")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    analyze(cfg, results_dir=args.results_dir, conv_file=args.conv_file)