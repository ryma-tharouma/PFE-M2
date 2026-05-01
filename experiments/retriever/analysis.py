import os
import json
import csv
import yaml
import numpy as np
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Set, Any, Tuple

from src.metrics import recall_at_k, precision_at_k, ndcg_at_k, reciprocal_rank


# ---------------------------------------------------------------------------
# Config path — change this if your config lives elsewhere
# ---------------------------------------------------------------------------

CONFIG_PATH = "config.yaml"


# ---------------------------------------------------------------------------
# Variant filename helpers
# ---------------------------------------------------------------------------

VARIANT_KEYS = ["level", "clean", "aggregation", "mode", "rerank", "k_rerank", "chunk_max", "embed_model"]


def parse_variant_filename(filename: str) -> Dict[str, Any]:
    """
    Parse a variant CSV filename into its hyperparam components.
    Expected format: level__clean__agg__mode__rerank__krerank__chunk__embed.csv
    Any field set to 'null' is stored as None.
    """
    stem  = filename.replace(".csv", "")
    parts = stem.split("__")

    if len(parts) != len(VARIANT_KEYS):
        raise ValueError(
            f"Filename '{filename}' has {len(parts)} parts, expected {len(VARIANT_KEYS)}. "
            f"Expected format: level__clean__agg__mode__rerank__krerank__chunk__embed.csv"
        )

    parsed = {}
    for key, val in zip(VARIANT_KEYS, parts):
        if val.lower() == "null":
            parsed[key] = None
        elif key == "clean":
            parsed[key] = val.lower() == "true"
        elif key in ("k_rerank", "chunk_max"):
            parsed[key] = int(val) if val.lower() != "null" else None
        else:
            parsed[key] = val

    return parsed


def variant_prefix_row(config: str, variant: str, hyperparams: Dict[str, Any]) -> Dict[str, Any]:
    """Build the common prefix columns shared by all global CSV rows for this run."""
    row = {"config": config, "variant": variant}
    row.update({k: hyperparams.get(k) for k in VARIANT_KEYS})
    return row


# ---------------------------------------------------------------------------
# Global CSV helpers
# ---------------------------------------------------------------------------

GLOBAL_DIR = "global"


def _get_global_path(results_root: str, filename: str) -> str:
    global_dir = os.path.join(results_root, GLOBAL_DIR)
    os.makedirs(global_dir, exist_ok=True)
    return os.path.join(global_dir, filename)


def append_to_global_csv(results_root: str,
                         filename: str,
                         new_rows: List[Dict[str, Any]],
                         config: str,
                         variant: str) -> None:
    """
    Append rows to a global CSV, overwriting any existing rows for the same
    config + variant combination first.
    """
    if not new_rows:
        return

    path = _get_global_path(results_root, filename)

    if os.path.exists(path):
        existing = pd.read_csv(path, dtype=str)
        mask     = ~((existing["config"] == config) & (existing["variant"] == variant))
        existing = existing[mask]
    else:
        existing = pd.DataFrame()

    new_df   = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# Row builders — one per global CSV
# ---------------------------------------------------------------------------

def build_general_rows(prefix: Dict, metrics: Dict, k_values: List[int]) -> List[Dict]:
    rows = []
    for k in k_values:
        row = dict(prefix)
        row["k"]               = k
        row["precision"]       = metrics["precision"].get(str(k))
        row["recall"]          = metrics["recall"].get(str(k))
        row["ndcg"]            = metrics["ndcg"].get(str(k))
        row["mrr"]             = metrics["mrr"]
        row["query_count"]     = metrics["query_count"]
        lat = metrics.get("latency_stats", {})
        row["latency_min_ms"]  = lat.get("min_ms")
        row["latency_q1_ms"]   = lat.get("q1_ms")
        row["latency_q2_ms"] = lat.get("q2_ms")
        row["latency_q3_ms"]   = lat.get("q3_ms")
        row["latency_max_ms"]  = lat.get("max_ms")
        row["latency_mean_ms"] = lat.get("mean_ms")
        rows.append(row)
    return rows


def build_per_app_rows(prefix: Dict, per_app_metrics: Dict, k_values: List[int]) -> List[Dict]:
    rows = []
    for app_id, metrics in per_app_metrics.items():
        for k in k_values:
            row = dict(prefix)
            row["app_id"]      = app_id
            row["k"]           = k
            row["precision"]   = metrics["precision"].get(str(k))
            row["recall"]      = metrics["recall"].get(str(k))
            row["ndcg"]        = metrics["ndcg"].get(str(k))
            row["mrr"]         = metrics["mrr"]
            row["query_count"] = metrics["query_count"]
            rows.append(row)
    return rows


def build_failure_rows(prefix: Dict, failure_metrics: Dict, k_values: List[int]) -> List[Dict]:
    rows = []
    for group_name, metrics in failure_metrics.items():
        for k in k_values:
            row = dict(prefix)
            row["group"]       = group_name
            row["k"]           = k
            row["precision"]   = metrics["precision"].get(str(k))
            row["recall"]      = metrics["recall"].get(str(k))
            row["ndcg"]        = metrics["ndcg"].get(str(k))
            row["mrr"]         = metrics["mrr"]
            row["query_count"] = metrics["query_count"]
            rows.append(row)
    return rows


def build_routing_rows(prefix: Dict, routing_metrics: Dict) -> List[Dict]:
    rows = []
    for routing_label, stats in routing_metrics.items():
        row = dict(prefix)
        row["routing_label"]    = routing_label
        row["query_count"]      = stats.get("query_count")
        row["total_retrieved"]  = stats.get("total_retrieved_docs")
        # OOD fields
        row["min_score"]        = stats.get("min_score")
        row["max_score"]        = stats.get("max_score")
        row["mean_score"]       = stats.get("mean_score")
        row["p75_score"]        = stats.get("p75_score")
        row["p95_score"]        = stats.get("p95_score")
        # Non-OOD fields
        row["wrong_retrievals"] = stats.get("wrong_retrievals")
        row["min_score_wrong"]  = stats.get("min_score_wrong")
        row["max_score_wrong"]  = stats.get("max_score_wrong")
        row["mean_score_wrong"] = stats.get("mean_score_wrong")
        row["p75_score_wrong"]  = stats.get("p75_score_wrong")
        row["p95_score_wrong"]  = stats.get("p95_score_wrong")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Original data-loading helpers (unchanged)
# ---------------------------------------------------------------------------

def load_conversation_data_from_files(query_sources: List[Dict]) -> Tuple[Dict[str, Set[str]], Dict[str, Any]]:
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
        total_weight   = sum(app_weights)
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
    app_groups = defaultdict(list)
    for qid, data in queries.items():
        app_groups[data["app_id"]].append(qid)
    return dict(app_groups)


def group_by_routing(queries: Dict[str, Any]) -> Dict[str, List[str]]:
    routing_groups = defaultdict(list)
    for qid, data in queries.items():
        routing_groups[data["routing_label"]].append(qid)
    return dict(routing_groups)


def analyze_routing_thresholds(queries: Dict[str, Any],
                               relevant_mapping: Dict[str, Set[str]]) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(cfg: dict):
    """
    Main analysis pipeline.
    Reads results_dir from config (supports {experiment_name} template).
    Generates 4 JSON files per config (unchanged) plus appends to 4 global CSVs:
      data/results/global/general_metrics.csv
      data/results/global/per_app_metrics.csv
      data/results/global/failure_analysis.csv
      data/results/global/routing_analysis.csv
    """
    max_k_list = cfg.get("retrieval", {}).get("eval_k_sections", list(range(1, 11)))
    print(f"Using k values from config: {max_k_list}")

    # Resolve results_dir — supports {experiment_name} template
    experiment      = cfg.get("experiment", {})
    experiment_name = experiment.get("name") or cfg.get("name") or cfg.get("experiment_name")
    paths           = cfg.get("paths", {})

    raw_results_dir = (
        experiment.get("results_dir")
        or paths.get("resolved_results")
        or paths.get("results_dir")
        or paths.get("output_dir")
    )

    if raw_results_dir and experiment_name:
        results_dir = raw_results_dir.replace("{experiment_name}", experiment_name)
    elif experiment_name:
        results_dir = os.path.join("data", "results", experiment_name)
    elif raw_results_dir:
        results_dir = raw_results_dir
    else:
        raise ValueError("Could not determine results directory from config.")

    if not os.path.exists(results_dir):
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    # results_root is the parent of the config folder (i.e. data/results/)
    results_root = os.path.dirname(os.path.abspath(results_dir))
    config_name  = os.path.basename(os.path.abspath(results_dir))

    print(f"Config:      {config_name}")
    print(f"Results dir: {results_dir}")
    print(f"Global CSVs: {os.path.join(results_root, GLOBAL_DIR)}/")

    # Resolve query sources
    query_sources = cfg.get("evaluation", {}).get("query_sources", [])
    if not query_sources:
        conversations_dir = paths.get("conversations_dir", "data/conversations/")
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

    apps_dir           = paths.get("apps_dir", "data/apps/")
    app_section_counts = get_app_section_counts(apps_dir)
    print(f"Loaded app section counts: {app_section_counts}")

    csv_files = sorted(f for f in os.listdir(results_dir) if f.endswith(".csv"))
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

        # Parse hyperparams from filename
        try:
            hyperparams = parse_variant_filename(csv_file)
        except ValueError as e:
            print(f"  ✗ Skipping {csv_file}: {e}")
            continue

        variant_name = csv_file.replace(".csv", "")
        prefix       = variant_prefix_row(config_name, variant_name, hyperparams)

        queries = load_csv_data(csv_path, relevant_mapping, query_metadata)
        if not queries:
            print(f"  ✗ No valid queries in {csv_file}")
            continue

        config_key = variant_name
        print(f"  ✓ Loaded {len(queries)} queries | hyperparams: {hyperparams}")

        # --- General metrics ---
        general[config_key] = compute_metrics_for_queries(
            queries, relevant_mapping, app_section_counts, max_k_list
        )
        print(f"    General metrics computed")

        non_ood_queries = {
            qid: data for qid, data in queries.items()
            if data["routing_label"] != "ood"
        }

        # --- Failure analysis ---
        failure_groups      = group_by_failure(non_ood_queries)
        failure[config_key] = {}
        for group_name, qid_list in failure_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: non_ood_queries[qid] for qid in qid_list}
            failure[config_key][group_name] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Failure analysis computed ({len(failure[config_key])} groups)")

        # --- Per-app metrics ---
        app_groups          = group_by_app(non_ood_queries)
        per_app[config_key] = {}
        for app_id, qid_list in app_groups.items():
            if not qid_list:
                continue
            group_queries = {qid: non_ood_queries[qid] for qid in qid_list}
            per_app[config_key][app_id] = compute_metrics_for_queries(
                group_queries, relevant_mapping, app_section_counts, max_k_list
            )
        print(f"    Per-app metrics computed ({len(per_app[config_key])} apps)")

        # --- Routing analysis ---
        routing[config_key] = analyze_routing_thresholds(queries, relevant_mapping)
        print(f"    Routing analysis computed ({len(routing[config_key])} routing labels)")

        # --- Append to global CSVs ---
        append_to_global_csv(
            results_root, "general_metrics.csv",
            build_general_rows(prefix, general[config_key], max_k_list),
            config_name, variant_name,
        )
        append_to_global_csv(
            results_root, "per_app_metrics.csv",
            build_per_app_rows(prefix, per_app[config_key], max_k_list),
            config_name, variant_name,
        )
        append_to_global_csv(
            results_root, "failure_analysis.csv",
            build_failure_rows(prefix, failure[config_key], max_k_list),
            config_name, variant_name,
        )
        append_to_global_csv(
            results_root, "routing_analysis.csv",
            build_routing_rows(prefix, routing[config_key]),
            config_name, variant_name,
        )
        print(f"    Global CSVs updated")

    # --- Save per-config JSONs (unchanged) ---
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
    print(f"\nGlobal CSVs updated at {os.path.join(results_root, GLOBAL_DIR)}/")


if __name__ == "__main__":
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)

    analyze(cfg)