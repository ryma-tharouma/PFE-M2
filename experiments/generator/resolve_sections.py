#!/usr/bin/env python
"""
resolve_sections.py — Pre-processing step for the RAG pipeline.

Reads raw conversations (with section IDs) and resolves each section ID
to its actual text from the apps directory, producing an enriched JSONL
where every turn already contains the full context + history as strings.

The output JSONL can then be fed directly into generate.py (or any other
evaluation / inspection tool) without needing access to the apps directory.

Output record fields
--------------------
conversation_id   str
app_id            str
turn_id           int
routing_label     str       ("rag" | "ood")
query             str
query_quality     str | None
isfollow_up       bool
ground_truth      str       (original answer, or OOD_GROUND_TRUTH for ood turns)
history           str       (formatted last HISTORY_N turns, empty if first turn)
context           str       (resolved section texts joined by ---, may be empty)
context_sections  list[str] (original section IDs, for traceability)
missing_sections  list[str] (IDs that could not be resolved)

Usage
-----
python resolve_sections.py \
    --conversations data/conversations.jsonl \
    --apps-dir      data/apps \
    --output        data/resolved_turns.jsonl \
    [--skip-empty-context]      # drop turns where no section resolved
"""

import os
import json
import argparse
import functools
from typing import List, Dict, Optional


# ══════════════════════════════════════════════════════════════════════════════
# Global configuration  ← edit these as needed
# ══════════════════════════════════════════════════════════════════════════════

# Number of previous turns to include as history (0 = no history).
# History is tracked across ALL labels, not just rag/ood.
HISTORY_N: int = 1

# Section sort order inside the resolved context.
# The input list is already ordered by score (best first).
#   False → keep the original score order (default)
#   True  → re-sort alphabetically by section_id (stable, so equal IDs keep
#            their relative score order)
SORT_PRIORITY_ALPHA: bool = True

# Fixed answer injected as ground_truth for every OOD turn.
OOD_GROUND_TRUTH: str = (
    "Je ne peux pas répondre à cette question avec les informations disponibles."
)

# Only turns whose routing_label is in this set produce output records.
# History tracking is always label-agnostic (all turns feed the history window).
OUTPUT_LABELS: List[str] = ["rag", "ood"]


# ══════════════════════════════════════════════════════════════════════════════
# Section loading  (same logic as generate.py — keep in sync)
# ══════════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=256)
def _load_app_sections(app_path: str) -> List[Dict]:
    with open(app_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_section_text(apps_dir: str, app_id: str, section_id: str) -> str:
    """Return the resolved text for a section, or empty string if not found."""
    app_path = os.path.join(apps_dir, f"{app_id}.json")
    if not os.path.exists(app_path):
        return ""
    for sec in _load_app_sections(app_path):
        if str(sec.get("section_id")) == str(section_id):
            source_type = sec.get("source_type", "manuel")
            if source_type == "faq":
                return sec.get("full_text", sec.get("answer", ""))
            breadcrumb = sec.get("breadcrumb", "")
            content    = sec.get("content", "")
            return f"{breadcrumb} : {content}".strip()
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# History helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_history_text(history_window: List[Dict]) -> str:
    """Format the last HISTORY_N turns into a single string."""
    if not history_window:
        return ""
    lines = []
    for entry in history_window[-HISTORY_N:]:
        lines.append(f"Utilisateur: {entry['query']}")
        lines.append(f"Assistant: {entry['answer']}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Core resolution logic
# ══════════════════════════════════════════════════════════════════════════════

def resolve_turn(
    conv: Dict,
    turn: Dict,
    history_text: str,
    apps_dir: str,
) -> Dict:
    """Resolve section IDs to text and build the enriched record.

    The input section_ids list is assumed to be already sorted by score
    (best first).  When SORT_PRIORITY_ALPHA is True we do a stable
    alphabetical re-sort, which preserves relative score order for ties.
    """
    section_ids = turn.get("relevant_sections", [])
    label       = turn.get("routing_label", "rag")

    # ---------- resolve ----------
    resolved = []   # list of (section_id, text) in original score order
    missing  = []

    for sec_id in section_ids:
        text = load_section_text(apps_dir, conv["app_id"], sec_id)
        if text:
            resolved.append((str(sec_id), text))
        else:
            missing.append(str(sec_id))

    # ---------- optional alpha re-sort (stable → score order preserved) ----------
    if SORT_PRIORITY_ALPHA:
        resolved.sort(key=lambda t: t[0])

    context = "\n\n---\n\n".join(text for _, text in resolved)

    # ---------- ground truth ----------
    if label == "ood":
        ground_truth = OOD_GROUND_TRUTH
    else:
        ground_truth = turn.get("answer", "")

    return {
        "conversation_id":  conv["conversation_id"],
        "app_id":           conv["app_id"],
        "turn_id":          turn["turn_id"],
        "routing_label":    label,
        "query":            turn.get("user_query", ""),
        "query_quality":    turn.get("query_quality", None),
        "isfollow_up":      bool(turn.get("isfollow_up", False)),
        "ground_truth":     ground_truth,
        "history":          history_text,
        "context":          context,          # may be empty string — that is fine
        "context_sections": [str(s) for s in section_ids],
        "missing_sections": missing,
    }


def process_conversations(
    conv_path: str,
    apps_dir: str,
    output_path: str,
    skip_empty_context: bool,
) -> Dict:
    stats = {
        "total_conversations": 0,
        "total_turns_seen":    0,
        "total_turns_written": 0,
        "total_missing":       0,
        "skipped_empty":       0,
        "label_counts":        {},
    }

    with (
        open(conv_path,   "r", encoding="utf-8") as in_f,
        open(output_path, "w", encoding="utf-8") as out_f,
    ):
        for raw_line in in_f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            conv = json.loads(raw_line)
            stats["total_conversations"] += 1

            # Rolling history window — tracks ALL turns regardless of label
            history_window: List[Dict] = []

            for turn in conv.get("turns", []):
                stats["total_turns_seen"] += 1
                label = turn.get("routing_label", "rag")

                # Build history text from the current window BEFORE this turn
                history_text = build_history_text(history_window)

                # Only write records for OUTPUT_LABELS; history is always updated
                if label in OUTPUT_LABELS:
                    record = resolve_turn(conv, turn, history_text, apps_dir)

                    # Optionally skip turns with no resolved context
                    if skip_empty_context and not record["context"]:
                        stats["skipped_empty"] += 1
                    else:
                        out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        stats["total_turns_written"] += 1
                        stats["total_missing"]       += len(record["missing_sections"])
                        stats["label_counts"][label]  = (
                            stats["label_counts"].get(label, 0) + 1
                        )

                        if record["missing_sections"]:
                            print(
                                f"[WARN] {conv['conversation_id']} turn {turn['turn_id']} "
                                f"(app={conv['app_id']}): missing sections "
                                f"{record['missing_sections']}"
                            )

                # Always push this turn onto the history window (all labels)
                history_window.append({
                    "query":  turn.get("user_query", ""),
                    "answer": turn.get("answer", ""),
                })
                # Keep only the last HISTORY_N entries to bound memory
                if len(history_window) > HISTORY_N:
                    history_window = history_window[-HISTORY_N:]

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resolve section IDs → text and produce enriched JSONL turns. "
            f"Only {OUTPUT_LABELS} labels are written; history tracks all labels."
        )
    )
    parser.add_argument("--conversations",      type=str, required=True,
                        help="Input JSONL file with raw conversations")
    parser.add_argument("--apps-dir",           type=str, required=True,
                        help="Directory containing <app_id>.json section files")
    parser.add_argument("--output",             type=str, required=True,
                        help="Output JSONL file path")
    parser.add_argument("--skip-empty-context", action="store_true",
                        help="Drop turns where no section could be resolved")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    print(f"Resolving sections...")
    print(f"  Input       : {args.conversations}")
    print(f"  Apps        : {args.apps_dir}")
    print(f"  Output      : {args.output}")
    print(f"  HISTORY_N   : {HISTORY_N}")
    print(f"  SORT_ALPHA  : {SORT_PRIORITY_ALPHA}")
    print(f"  Out labels  : {OUTPUT_LABELS}")

    stats = process_conversations(
        conv_path=args.conversations,
        apps_dir=args.apps_dir,
        output_path=args.output,
        skip_empty_context=args.skip_empty_context,
    )

    print(f"\nDone.")
    print(f"  Conversations : {stats['total_conversations']}")
    print(f"  Turns seen    : {stats['total_turns_seen']}")
    print(f"  Turns written : {stats['total_turns_written']}")
    print(f"  Missing secs  : {stats['total_missing']}")
    if stats["skipped_empty"]:
        print(f"  Skipped empty : {stats['skipped_empty']}")
    print(f"  By label      : {stats['label_counts']}")


if __name__ == "__main__":
    main()