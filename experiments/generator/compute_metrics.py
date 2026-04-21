#!/usr/bin/env python
import os
import json
import argparse
import numpy as np
import re
from typing import List, Dict
from evaluate import load as load_metric

_bleu      = load_metric("bleu")
_rouge     = load_metric("rouge")
_bertscore = load_metric("bertscore")


def clean_text(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    cleaned_preds = [clean_text(p) for p in predictions]
    cleaned_refs  = [clean_text(r) for r in references]

    bleu_score = _bleu.compute(
        predictions=cleaned_preds,
        references=[[r] for r in cleaned_refs]
    )
    rouge_results = _rouge.compute(
        predictions=cleaned_preds,
        references=cleaned_refs,
        use_aggregator=False,
    )
    rougeL = sum(rouge_results["rougeL"]) / len(rouge_results["rougeL"])

    bertscore_score = _bertscore.compute(
        predictions=cleaned_preds, references=cleaned_refs, lang="fr"
    )

    return {
        "bleu":         bleu_score["bleu"],
        "rougeL":       rougeL,
        "bertscore_f1": sum(bertscore_score["f1"]) / len(bertscore_score["f1"]),
    }


def _timing_stats(times: List[float], prefix: str) -> Dict:
    if not times:
        return {}
    return {
        f"{prefix}_mean_sec": round(np.mean(times), 4),
        f"{prefix}_min_sec":  round(min(times), 4),
        f"{prefix}_max_sec":  round(max(times), 4),
        f"{prefix}_q1_sec":   round(np.percentile(times, 25), 4),
        f"{prefix}_q2_sec":   round(np.percentile(times, 50), 4),
        f"{prefix}_q3_sec":   round(np.percentile(times, 75), 4),
    }


def _group_metrics(records: List[Dict]) -> Dict:
    if not records:
        return {"count": 0}
    result = compute_metrics(
        [r["prediction"] for r in records],
        [r["reference"]  for r in records]
    )
    result["count"] = len(records)
    result.update(_timing_stats([r["gen_time"] for r in records], "generation_time"))
    result.update(_timing_stats([r["ttft"]     for r in records], "ttft"))
    return result


def compute_breakdown_metrics(rag_records: List[Dict]) -> Dict:
    # by query_quality: well_written / poorly_written
    quality_groups: Dict[str, List[Dict]] = {}
    for rec in rag_records:
        key = str(rec["query_quality"]) if rec["query_quality"] is not None else "unknown"
        quality_groups.setdefault(key, []).append(rec)

    # by isfollow_up: true / false
    follow_up_groups: Dict[str, List[Dict]] = {"true": [], "false": []}
    for rec in rag_records:
        follow_up_groups["true" if rec["isfollow_up"] else "false"].append(rec)

    # cross breakdown: quality x follow_up
    cross_groups: Dict[str, List[Dict]] = {}
    for rec in rag_records:
        quality = str(rec["query_quality"]) if rec["query_quality"] is not None else "unknown"
        follow  = "follow_up" if rec["isfollow_up"] else "standalone"
        key     = f"{quality}_{follow}"
        cross_groups.setdefault(key, []).append(rec)

    return {
        "by_query_quality": {k: _group_metrics(v) for k, v in quality_groups.items()},
        "by_follow_up":     {k: _group_metrics(v) for k, v in follow_up_groups.items()},
        "by_quality_x_follow_up": {k: _group_metrics(v) for k, v in cross_groups.items()},
    }


def load_rag_records(jsonl_path: str) -> List[Dict]:
    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if (
                    not rec.get("failed")
                    and rec.get("generated")
                    and rec.get("ground_truth")
                    and rec.get("routing_label") == "rag"
                ):
                    records.append({
                        "prediction":    rec["generated"],
                        "reference":     rec["ground_truth"],
                        "query_quality": rec.get("query_quality"),
                        "isfollow_up":  rec.get("isfollow_up", False),
                        "gen_time":      rec.get("generation_time_sec", 0.0),
                        "ttft":          rec.get("ttft_sec", 0.0),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return records


def main():
    parser = argparse.ArgumentParser(description="Compute metrics from generation outputs")
    parser.add_argument("--input",      type=str, required=True, help="Path to .jsonl generation file")
    parser.add_argument("--output-dir", type=str, default="outputs/metrics")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    config_id = os.path.splitext(os.path.basename(args.input))[0]

    print(f"Loading generations from: {args.input}")
    rag_records = load_rag_records(args.input)
    print(f"Found {len(rag_records)} valid RAG records")

    if not rag_records:
        print("No valid records found, exiting.")
        return

    print("Computing overall metrics (BERTScore may take a while)...")
    metrics = compute_metrics(
        [r["prediction"] for r in rag_records],
        [r["reference"]  for r in rag_records]
    )
    metrics["count"] = len(rag_records)
    metrics.update(_timing_stats([r["gen_time"] for r in rag_records], "generation_time"))
    metrics.update(_timing_stats([r["ttft"]     for r in rag_records], "ttft"))

    metrics_path = os.path.join(args.output_dir, f"{config_id}.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print("Computing breakdown metrics...")
    breakdown      = compute_breakdown_metrics(rag_records)
    breakdown_path = os.path.join(args.output_dir, f"{config_id}_breakdown.json")
    with open(breakdown_path, "w", encoding="utf-8") as f:
        json.dump(breakdown, f, indent=2, ensure_ascii=False)

    print(f"\nMetrics saved to:   {metrics_path}")
    print(f"Breakdown saved to: {breakdown_path}")
    print(f"\n  Overall ({metrics['count']} turns):")
    print(f"    BLEU:         {metrics['bleu']:.4f}")
    print(f"    RougeL:       {metrics['rougeL']:.4f}")
    print(f"    BERTScore F1: {metrics['bertscore_f1']:.4f}")
    if "generation_time_mean_sec" in metrics:
        print(f"    Avg gen time: {metrics['generation_time_mean_sec']:.2f}s")
        print(f"    Avg TTFT:     {metrics['ttft_mean_sec']:.2f}s")

    print(f"\n  By query quality:")
    for k, v in breakdown["by_query_quality"].items():
        if v.get("count", 0) > 0:
            print(f"    [{k}] n={v['count']}  BLEU={v.get('bleu',0):.4f}  RougeL={v.get('rougeL',0):.4f}  BERTScore={v.get('bertscore_f1',0):.4f}")

    print(f"\n  By follow-up:")
    for k, v in breakdown["by_follow_up"].items():
        if v.get("count", 0) > 0:
            print(f"    [{k}] n={v['count']}  BLEU={v.get('bleu',0):.4f}  RougeL={v.get('rougeL',0):.4f}  BERTScore={v.get('bertscore_f1',0):.4f}")

    print(f"\n  By quality x follow-up:")
    for k, v in breakdown["by_quality_x_follow_up"].items():
        if v.get("count", 0) > 0:
            print(f"    [{k}] n={v['count']}  BLEU={v.get('bleu',0):.4f}  RougeL={v.get('rougeL',0):.4f}  BERTScore={v.get('bertscore_f1',0):.4f}")


if __name__ == "__main__":
    main()