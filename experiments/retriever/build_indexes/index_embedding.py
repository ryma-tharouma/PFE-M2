import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings

from utils import iter_jsonl, build_section_text, normalize, Timer


EMBEDDERS = {
    "bge": "BAAI/bge-m3",
    "qwen": "Qwen/Qwen3-Embedding-8B",
    "mistral": "intfloat/e5-mistral-7b-instruct",
}


def iter_apps(apps_root: Path):
    for app_dir in apps_root.iterdir():
        if app_dir.is_dir():
            sections = app_dir / "sections.jsonl"
            if sections.exists():
                yield app_dir.name, sections


class Embedder:
    def encode_docs(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str, device: Optional[str], max_seq_length: int):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device=device)
        self.model.max_seq_length = max_seq_length

    def encode_docs(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()


class BGEFlagEmbedder(Embedder):
    def __init__(self, model_name: str, use_fp16: bool, max_seq_length: int):
        from FlagEmbedding import BGEM3FlagModel

        self.model = BGEM3FlagModel(model_name, use_fp16=use_fp16)
        self.model.max_seq_length = max_seq_length

    def encode_docs(self, texts: List[str]) -> List[List[float]]:
        output = self.model.encode(
            texts,
            batch_size=32,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense = output["dense_vecs"]
        return [normalize(vec) for vec in dense]


def build_index_for_app(
    app_id: str,
    sections_path: Path,
    persist_root: Path,
    embedder_key: str,
    embedder: Embedder,
    batch_size: int,
):
    persist_dir = persist_root / embedder_key / app_id
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(allow_reset=True),
    )
    collection = client.get_or_create_collection(
        name=f"{app_id}__{embedder_key}",
        metadata={"app_id": app_id, "embedder": embedder_key},
    )

    ids = []
    docs = []
    metadatas = []

    with Timer() as total_timer:
        for section in iter_jsonl(sections_path):
            section_id = str(section.get("section_id") or section.get("id"))
            if not section_id:
                continue

            text = build_section_text(section)
            if not text.strip():
                continue

            ids.append(section_id)
            docs.append(text)
            metadatas.append({"section_id": section_id})

            if len(docs) >= batch_size:
                embeddings = embedder.encode_docs(docs)
                collection.add(
                    ids=ids,
                    documents=docs,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                ids, docs, metadatas = [], [], []

        if docs:
            embeddings = embedder.encode_docs(docs)
            collection.add(
                ids=ids,
                documents=docs,
                embeddings=embeddings,
                metadatas=metadatas,
            )

    return round(total_timer.ms, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps-root", default="data/apps", help="root containing app folders")
    ap.add_argument("--persist-root", default="experiments/retriever/data/chroma")
    ap.add_argument("--embedder", choices=EMBEDDERS.keys(), required=True)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--index-times", default="experiments/retriever/data/index_times.csv")
    ap.add_argument("--device", default=None, help="e.g. cuda, cuda:0, cpu")
    ap.add_argument("--max-seq-length", type=int, default=4000)

    # BGE backend selection
    ap.add_argument("--bge-backend", choices=["sentence", "flag"], default="sentence")
    ap.add_argument("--bge-use-fp16", action="store_true", help="FlagEmbedding fp16")

    args = ap.parse_args()

    apps_root = Path(args.apps_root)
    persist_root = Path(args.persist_root)
    index_times_path = Path(args.index_times)
    index_times_path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not index_times_path.exists()

    embedder_name = EMBEDDERS[args.embedder]

    # build embedder instance
    if args.embedder == "bge" and args.bge_backend == "flag":
        embedder = BGEFlagEmbedder(
            model_name=embedder_name,
            use_fp16=args.bge_use_fp16,
            max_seq_length=args.max_seq_length,
        )
    else:
        embedder = SentenceTransformerEmbedder(
            model_name=embedder_name,
            device=args.device,
            max_seq_length=args.max_seq_length,
        )

    with index_times_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["app_id", "embedder", "model_name", "n_sections", "total_ms"],
        )
        if write_header:
            writer.writeheader()

        for app_id, sections_path in iter_apps(apps_root):
            total_ms = build_index_for_app(
                app_id=app_id,
                sections_path=sections_path,
                persist_root=persist_root,
                embedder_key=args.embedder,
                embedder=embedder,
                batch_size=args.batch_size,
            )

            n_sections = sum(1 for _ in iter_jsonl(sections_path))

            writer.writerow({
                "app_id": app_id,
                "embedder": args.embedder,
                "model_name": embedder_name,
                "n_sections": n_sections,
                "total_ms": total_ms,
            })


if __name__ == "__main__":
    main()