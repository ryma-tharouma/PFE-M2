#!/usr/bin/env python
import os
import json
import csv
import argparse
import numpy as np
import re
from typing import List, Dict
from evaluate import load as load_metric

_bleu      = load_metric("bleu")
_rouge     = load_metric("rouge")
_bertscore = load_metric("bertscore")


# ══════════════════════════════════════════════════════════════════════════════
# Text cleaning
# ══════════════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```.*?```',          '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`',            '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*',     r'\1', text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
# Core metric computation
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    cleaned_preds = [clean_text(p) for p in predictions]
    cleaned_refs  = [clean_text(r) for r in references]

    bleu_score = _bleu.compute(
        predictions=cleaned_preds,
        references=[[r] for r in cleaned_refs],
    )
    rouge_results = _rouge.compute(
        predictions=cleaned_preds,
        references=cleaned_refs,
        use_aggregator=False,
    )
    rougeL = sum(rouge_results["rougeL"]) / len(rouge_results["rougeL"])

    bertscore_result = _bertscore.compute(
        predictions=cleaned_preds,
        references=cleaned_refs,
        lang="fr",
    )

    return {
        "bleu":         round(bleu_score["bleu"], 6),
        "rougeL":       round(rougeL, 6),
        "bertscore_f1": round(sum(bertscore_result["f1"]) / len(bertscore_result["f1"]), 6),
    }


def _timing_stats(times: List[float], prefix: str) -> Dict:
    if not times:
        return {}
    return {
        f"{prefix}_mean_sec": round(float(np.mean(times)),              4),
        f"{prefix}_min_sec":  round(float(min(times)),                  4),
        f"{prefix}_max_sec":  round(float(max(times)),                  4),
        f"{prefix}_q1_sec":   round(float(np.percentile(times, 25)),    4),
        f"{prefix}_median_sec": round(float(np.percentile(times, 50)),  4),
        f"{prefix}_q3_sec":   round(float(np.percentile(times, 75)),    4),
    }


def _group_metrics(records: List[Dict]) -> Dict:
    if not records:
        return {"count": 0}
    result = compute_metrics(
        [r["prediction"] for r in records],
        [r["reference"]  for r in records],
    )
    result["count"] = len(records)
    result.update(_timing_stats([r["gen_time"] for r in records], "generation_time"))
    result.update(_timing_stats([r["ttft"]     for r in records], "ttft"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Data loading — all routing labels
# ══════════════════════════════════════════════════════════════════════════════

def load_records(jsonl_path: str) -> List[Dict]:
    """Load all valid (non-failed) records regardless of routing_label."""
    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if (
                    not rec.get("failed")
                    and rec.get("generated")
                    and rec.get("ground_truth")
                ):
                    records.append({
                        "prediction":    rec["generated"],
                        "reference":     rec["ground_truth"],
                        "routing_label": rec.get("routing_label", "unknown"),
                        "query_quality": rec.get("query_quality"),
                        "isfollow_up":   rec.get("isfollow_up", False),
                        "gen_time":      rec.get("generation_time_sec") or 0.0,
                        "ttft":          rec.get("ttft_sec") or 0.0,
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return records


# ══════════════════════════════════════════════════════════════════════════════
# Breakdown helpers
# ══════════════════════════════════════════════════════════════════════════════

def compute_breakdowns(records: List[Dict]) -> Dict[str, Dict]:
    """
    Returns a flat dict of group_name → metrics dict, covering:
      - overall
      - per routing_label
      - (rag only) by query_quality
      - (rag only) by isfollow_up
      - (rag only) by quality x follow_up
    """
    groups: Dict[str, List[Dict]] = {}

    # overall
    groups["overall"] = records

    # per routing label
    for rec in records:
        key = f"routing_{rec['routing_label']}"
        groups.setdefault(key, []).append(rec)

    # RAG-only breakdowns
    rag_records = [r for r in records if r["routing_label"] == "rag"]

    for rec in rag_records:
        quality = str(rec["query_quality"]) if rec["query_quality"] is not None else "unknown"
        groups.setdefault(f"rag_quality_{quality}", []).append(rec)

    for rec in rag_records:
        fu = "follow_up" if rec["isfollow_up"] else "standalone"
        groups.setdefault(f"rag_{fu}", []).append(rec)

    for rec in rag_records:
        quality = str(rec["query_quality"]) if rec["query_quality"] is not None else "unknown"
        fu      = "follow_up" if rec["isfollow_up"] else "standalone"
        groups.setdefault(f"rag_{quality}_{fu}", []).append(rec)

    return {name: _group_metrics(recs) for name, recs in groups.items()}


# ══════════════════════════════════════════════════════════════════════════════
# CSV writing
# ══════════════════════════════════════════════════════════════════════════════

# All columns that may appear in a row, in display order
_COLUMNS = [
    "config_id",
    "group",
    "count",
    "bleu",
    "rougeL",
    "bertscore_f1",
    "generation_time_mean_sec",
    "generation_time_min_sec",
    "generation_time_max_sec",
    "generation_time_q1_sec",
    "generation_time_median_sec",
    "generation_time_q3_sec",
    "ttft_mean_sec",
    "ttft_min_sec",
    "ttft_max_sec",
    "ttft_q1_sec",
    "ttft_median_sec",
    "ttft_q3_sec",
]


def write_csv(rows: List[Dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Compute metrics from generation outputs")
    parser.add_argument("--input",      type=str, required=True,
                        help="Path to .jsonl generation file (combined rag+ood)")
    parser.add_argument("--output-dir", type=str, default="outputs/metrics")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    config_id = os.path.splitext(os.path.basename(args.input))[0]

    print(f"Loading generations from: {args.input}")
    records = load_records(args.input)

    label_counts = {}
    for r in records:
        label_counts[r["routing_label"]] = label_counts.get(r["routing_label"], 0) + 1
    print(f"Loaded {len(records)} valid records: {label_counts}")

    if not records:
        print("No valid records found, exiting.")
        return

    print("Computing metrics per group (BERTScore may take a while)...")
    breakdowns = compute_breakdowns(records)

    # Build CSV rows
    rows = []
    for group_name, metrics in breakdowns.items():
        if metrics.get("count", 0) == 0:
            continue
        row = {"config_id": config_id, "group": group_name}
        row.update(metrics)
        rows.append(row)

    # Sort: overall first, then routing_, then rag breakdowns
    def _sort_key(r):
        g = r["group"]
        if g == "overall":        return (0, g)
        if g.startswith("routing_"): return (1, g)
        return (2, g)

    rows.sort(key=_sort_key)

    csv_path = os.path.join(args.output_dir, f"{config_id}_metrics.csv")
    write_csv(rows, csv_path)
    print(f"\nMetrics CSV saved to: {csv_path}")

    # ── Console summary ───────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"{'group':<35} {'n':>5}  {'BLEU':>7}  {'RougeL':>7}  {'BERT F1':>8}")
    print(f"{'─'*70}")
    for row in rows:
        print(
            f"{row['group']:<35} "
            f"{row.get('count', 0):>5}  "
            f"{row.get('bleu', 0):>7.4f}  "
            f"{row.get('rougeL', 0):>7.4f}  "
            f"{row.get('bertscore_f1', 0):>8.4f}"
        )
    print(f"{'─'*70}")


if __name__ == "__main__":
    main()

# python compute_metrics.py \
#     --input      outputs/generated/my_config.jsonl \
#     --output-dir outputs/metrics
#python compute_metrics.py --input  data/outputs/generated/qwen3.5_4b_gguf_original_l2_rerank20DenseMean_prompt1.jsonl --output-dir data/outputs/metrics