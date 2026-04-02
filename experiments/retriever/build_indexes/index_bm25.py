import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import bm25s

from utils import iter_jsonl, build_section_text, Timer


def iter_apps(apps_root: Path):
    for app_dir in apps_root.iterdir():
        if app_dir.is_dir():
            sections = app_dir / "sections.jsonl"
            if sections.exists():
                yield app_dir.name, sections


def build_docs(sections_path: Path) -> List[str]:
    docs = []
    for section in iter_jsonl(sections_path):
        section_id = str(section.get("section_id") or section.get("id"))
        if not section_id:
            continue

        text = build_section_text(section).strip()
        if not text:
            continue

        # Prefix ID so we can recover it after retrieval
        docs.append(f"{section_id}\t{text}")
    return docs


def build_bm25_for_app(
    app_id: str,
    sections_path: Path,
    persist_root: Path,
    method: str,
):
    persist_dir = persist_root / app_id
    persist_dir.mkdir(parents=True, exist_ok=True)

    docs = build_docs(sections_path)
    corpus_tokens = bm25s.tokenize(docs)  # official tokenizer
    retriever = bm25s.BM25(corpus=docs, method=method)
    retriever.index(corpus_tokens)

    # cache index to disk
    retriever.save(str(persist_dir))

    return len(docs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps-root", default="data/apps")
    ap.add_argument("--persist-root", default="experiments/retriever/data/bm25")
    ap.add_argument("--method", default="robertson",
                    help="bm25s method: robertson | atire | bm25l | bm25+ | lucene")
    ap.add_argument("--index-times", default="experiments/retriever/data/index_times.csv")
    args = ap.parse_args()

    apps_root = Path(args.apps_root)
    persist_root = Path(args.persist_root)
    index_times_path = Path(args.index_times)
    index_times_path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not index_times_path.exists()

    with index_times_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["app_id", "bm25_method", "n_sections", "total_ms", "built_at"],
        )
        if write_header:
            writer.writeheader()

        for app_id, sections_path in iter_apps(apps_root):
            with Timer() as t:
                n_sections = build_bm25_for_app(
                    app_id=app_id,
                    sections_path=sections_path,
                    persist_root=persist_root,
                    method=args.method,
                )

            writer.writerow({
                "app_id": app_id,
                "bm25_method": args.method,
                "n_sections": n_sections,
                "total_ms": round(t.ms, 3),
                "built_at": datetime.utcnow().isoformat(),
            })


if __name__ == "__main__":
    main()