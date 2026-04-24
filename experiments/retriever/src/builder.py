# src/builder.py
import os
import glob
import time
import json
import gc
import torch
from pathlib import Path
from typing import List, Dict

from src.factories import get_embedder, get_vector_database, get_chunker

def run_build(cfg: dict):
    apps_dir      = cfg["paths"]["apps_dir"]
    results_dir   = cfg["paths"]["resolved_results"]
    db_types      = cfg["indexing"].get("db_types", [cfg["database"]["type"]])
    modes         = cfg["indexing"]["modes"]
    index_types   = cfg["indexing"]["index_types"]
    batch_size    = cfg["indexing"].get("batch_size", 32)
    drop_existing = cfg["indexing"].get("drop_existing", True)

    os.makedirs(results_dir, exist_ok=True)
    metrics_out = os.path.join(results_dir, "build_metrics.jsonl")

    with open(metrics_out, "w", encoding="utf-8") as f:
        pass

    app_files = glob.glob(os.path.join(apps_dir, "*.json"))
    if not app_files:
        print(f"No JSON files found in {apps_dir}")
        return

    print(f"Found {len(app_files)} application definitions.")

    chunker = get_chunker(cfg)

    for db_type in db_types:
        original_db_type        = cfg["database"]["type"]
        cfg["database"]["type"] = db_type

        try:
            db = get_vector_database(cfg)
            print(f"\nInitialized Database: {db_type}")

            for mode in modes:
                embedder = get_embedder(mode=mode, cfg=cfg)
                print(f"  Mode: {mode}")

                for idx_type in index_types:
                    print(f"    Index Type: {idx_type}")

                    for app_path in app_files:
                        with open(app_path, "r", encoding="utf-8") as f:
                            sections = json.load(f)

                        app_id    = Path(app_path).stem
                        coll_name = f"{app_id}_{mode}_{db_type}_{idx_type}"

                        if db.collection_exists(coll_name):
                            if drop_existing:
                                db.drop_collection(coll_name)
                                print(f"      Dropped: {coll_name}")
                            else:
                                print(f"      Skipping: {coll_name}")
                                continue

                        dim = cfg.get("model", {}).get("embedding_dim", 1024)
                        db.create_collection(coll_name, dim=dim, mode=mode, index_type=idx_type)

                        processed_chunks = chunker.process_sections(sections)
                        total_chunks     = len(processed_chunks)
                        print(f"      {app_id}: {len(sections)} sections -> {total_chunks} chunks")

                        vocab_dir  = os.path.join(cfg["paths"]["resolved_results"], "vocab")
                        os.makedirs(vocab_dir, exist_ok=True)
                        vocab_path = os.path.join(vocab_dir, f"{app_id}_{mode}.json")

                        if mode in ["sparse", "hybrid", "finetuned_hybrid"]:
                            all_texts = [c["embed_text"] for c in processed_chunks]
                            embedder.fit_bm25(app=app_id, corpus=all_texts)
                            embedder.save_bm25_vocab(app=app_id, path=vocab_path)
                            print(f"      Saved BM25 vocab to {vocab_path}")

                        start_time = time.time()

                        for i in range(0, total_chunks, batch_size):
                            batch_chunks = processed_chunks[i : i + batch_size]
                            texts        = [c["embed_text"] for c in batch_chunks]
                            vectors      = embedder.encode_batch(texts, app=app_id, is_query=False)

                            records = []
                            for j, chunk in enumerate(batch_chunks):
                                payload = {k: v for k, v in chunk.items() if k not in ["embed_text", "id"]}
                                payload["chunk_text"] = chunk["embed_text"]
                                rec = {
                                    "id": chunk.get("id", f"{chunk['parent_section_id']}_c{chunk.get('chunk_index', 0)}"),
                                    "payload": payload
                                }
                                if "dense" in vectors:
                                    rec["dense"] = vectors["dense"][j].tolist()
                                if "sparse" in vectors:
                                    rec["sparse"] = vectors["sparse"][j]
                                records.append(rec)

                            if records:
                                db.upsert(coll_name, records)

                        db.flush()

                        build_time = time.time() - start_time
                        speed      = round(total_chunks / build_time, 1) if build_time > 0 else 0

                        metric = {
                            "app_id":          app_id,
                            "mode":            mode,
                            "db_type":         db_type,
                            "index_type":      idx_type,
                            "chunks_indexed":  total_chunks,
                            "build_time_sec":  round(build_time, 2),
                            "speed":           speed,
                        }
                        with open(metrics_out, "a", encoding="utf-8") as f:
                            f.write(json.dumps(metric) + "\n")

                        print(f"      Indexed {total_chunks} chunks in {build_time:.1f}s ({speed} chunks/s)")

                embedder.cleanup()
                if cfg.get("model", {}).get("device") == "cuda":
                    torch.cuda.empty_cache()
                gc.collect()

        finally:
            cfg["database"]["type"] = original_db_type

    print(f"\nBuild metrics saved to {metrics_out}")