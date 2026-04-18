# src/generate_topk_conversation.py
import json
import csv
from collections import defaultdict
from typing import Dict, List


def load_conversation(conv_path: str) -> Dict[str, dict]:
    """Load conversation file and map qid -> (conversation_copy, turn)"""
    turns_by_qid = {}
    with open(conv_path, "r", encoding="utf-8") as f:
        for line in f:
            conv = json.loads(line)
            conv_id = conv["conversation_id"]
            for turn in conv["turns"]:
                turn_id = turn["turn_id"]
                qid = f"{conv_id}_t{turn_id}"
                turns_by_qid[qid] = {
                    "conv": conv,
                    "turn": turn,
                    "turn_id": turn_id,
                    "conv_id": conv_id
                }
    return turns_by_qid


def load_top_k_retrieved(csv_path: str, k: int) -> Dict[str, List[str]]:
    """
    From CSV, for each query_id:
        - take the first k rows (by rank/order in CSV, which is already sorted by score desc)
        - extract their doc_id
        - sort those doc_ids alphabetically
        - return as list
    """
    query_docs = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row["query_id"]
            doc_id = row["doc_id"]
            # CSV rows are already ordered by rank (score desc)
            query_docs[qid].append(doc_id)
    
    top_k_sorted = {}
    for qid, docs in query_docs.items():
        # Take first k (preserve original order from CSV)
        first_k = docs[:k]
        # Then sort that list by doc_id alphabetically
        first_k.sort()
        top_k_sorted[qid] = first_k
    return top_k_sorted


def generate_topk_conversation(conv_path: str, csv_path: str, k: int, output_path: str):
    # Load original data
    turns_by_qid = load_conversation(conv_path)
    top_k_map = load_top_k_retrieved(csv_path, k)

    # Group conversations to reconstruct full JSON objects
    convs = {}
    for qid, info in turns_by_qid.items():
        conv_id = info["conv_id"]
        if conv_id not in convs:
            # Deep copy the original conversation
            convs[conv_id] = json.loads(json.dumps(info["conv"]))

    # Replace relevant_sections in each turn
    for qid, info in turns_by_qid.items():
        conv_id = info["conv_id"]
        turn_id = info["turn_id"]
        new_relevant = top_k_map.get(qid, [])
        for turn in convs[conv_id]["turns"]:
            if turn["turn_id"] == turn_id:
                turn["relevant_sections"] = new_relevant
                break

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for conv in convs.values():
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    print(f"Generated {output_path} with relevant_sections = top-{k} retrieved documents (sorted by doc_id).")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--conv", required=True, help="Original conversation JSONL file")
    parser.add_argument("--csv", required=True, help="CSV with retrieval results (query_id, doc_id, score) – assumed already sorted by rank")
    parser.add_argument("--k", type=int, required=True, help="Number of top retrieved documents to use as new relevant_sections")
    parser.add_argument("--output", required=True, help="Output conversation JSONL file")
    args = parser.parse_args()

    generate_topk_conversation(args.conv, args.csv, args.k, args.output)