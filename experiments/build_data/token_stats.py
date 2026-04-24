#!/usr/bin/env python3
"""
Compute token statistics (min, Q1, Q2, Q3, max, mean) for breadcrumb + content fields
in a JSON array of sections, using a Qwen tokenizer.
"""

import json
import sys
import argparse
import numpy as np
from transformers import AutoTokenizer

def main():
    parser = argparse.ArgumentParser(description="Token statistics for section texts")
    parser.add_argument("input_file", help="JSON file containing a list of section objects")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B",
                        help="Qwen model name (default: Qwen/Qwen3.5-0.8B). Use any Qwen model/tokenizer.")
    args = parser.parse_args()

    # Load sections
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            sections = json.load(f)
    except Exception as e:
        print(f"Error reading {args.input_file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(sections, list):
        print("Error: JSON root must be an array of sections", file=sys.stderr)
        sys.exit(1)

    if not sections:
        print("No sections found in JSON file.", file=sys.stderr)
        sys.exit(1)

    # Load tokenizer
    print(f"Loading tokenizer: {args.model}", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    # Compute token counts
    token_counts = []
    for sec in sections:
        breadcrumb = sec.get("breadcrumb", "")
        content = sec.get("content", "")
        text = f"{breadcrumb} {content}".strip()
        if not text:
            continue
        tokens = tokenizer.encode(text, add_special_tokens=False)
        token_counts.append(len(tokens))

    if not token_counts:
        print("No valid text found in any section (breadcrumb+content empty).", file=sys.stderr)
        sys.exit(1)

    # Statistics
    counts = np.array(token_counts)
    stats = {
        "min": int(np.min(counts)),
        "q1": float(np.percentile(counts, 25)),
        "q2": float(np.percentile(counts, 50)),  # median
        "q3": float(np.percentile(counts, 75)),
        "max": int(np.max(counts)),
        "mean": float(np.mean(counts)),
    }

    # Print results (JSON format)
    print(json.dumps(stats, indent=2))

    # Also print a human-readable summary
    print("\n=== Summary ===", file=sys.stderr)
    for k, v in stats.items():
        print(f"{k.upper()}: {v}", file=sys.stderr)

if __name__ == "__main__":
    main()