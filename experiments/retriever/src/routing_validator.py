# src/routing_validator.py
import os
import json
import csv
from typing import Dict, List, Any
from collections import defaultdict

def load_ground_truth_labels(ground_truth_path: str) -> Dict[str, str]:
    """Maps query_id -> routing_label from test JSONL."""
    labels = {}
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        for line in f:
            conv = json.loads(line)
            for turn in conv["turns"]:
                qid = f"{conv['conversation_id']}_t{turn['turn_id']}"
                labels[qid] = turn.get("routing_label", "ood")
    return labels

def predict_route(score: float, thresholds: Dict[str, Any], mode: str) -> str:
    """Applies mode-specific thresholds to determine routing decision."""
    mode_thresh = thresholds.get(mode, thresholds.get("default", {}))
    T_faq = mode_thresh.get("T_faq", 0.0)
    T_rag = mode_thresh.get("T_rag", 0.0)

    if score >= T_faq:
        return "faq"
    elif score >= T_rag:
        return "rag"
    else:
        return "ood"

def compute_routing_metrics(true: List[str], pred: List[str], labels: List[str] = ["faq", "rag", "ood"]) -> Dict:
    """Computes routing accuracy, confusion matrix, and per-label P/R/F1."""
    cm = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(true, pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1

    metrics = {}
    total_correct = sum(1 for t, p in zip(true, pred) if t == p)
    total = len(true)

    for label in labels:
        tp = cm[label][label]
        fp = sum(cm[other][label] for other in labels if other != label)
        fn = sum(cm[label][other] for other in labels if other != label)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        metrics[label] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": sum(cm[label].values())
        }

    return {
        "accuracy": round(total_correct / total, 4) if total > 0 else 0.0,
        "confusion_matrix": cm,
        "per_label": metrics
    }

def run_routing_validation(
    detailed_csv_path: str,
    ground_truth_path: str,
    thresholds: Dict[str, Any],
    output_dir: str
) -> Dict[str, Any]:
    """
    Validates routing decisions against ground truth.
    Expects: detailed CSV from evaluator, test JSONL with 'routing_label', learned thresholds.
    """
    true_labels = load_ground_truth_labels(ground_truth_path)

    query_data = {}
    with open(detailed_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["rank"]) == 1:
                query_data[row["query_id"]] = {
                    "mode": row["mode"],
                    "score": float(row["score"])
                }

    true_list, pred_list, mode = [], [], None
    for qid, data in query_data.items():
        if qid not in true_labels:
            continue
        mode = data["mode"]
        true_list.append(true_labels[qid])
        pred_list.append(predict_route(data["score"], thresholds, mode))

    report = compute_routing_metrics(true_list, pred_list)
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"routing_report_{mode}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Routing validation for {mode} complete. Accuracy: {report['accuracy']}")
    print(f"Report saved to {report_path}")
    return report