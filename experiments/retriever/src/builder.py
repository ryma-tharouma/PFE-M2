# src/builder.py
import os, time, json, gc, torch
from pathlib import Path
from .data_loader import load_app_sections
from .embedder import BGEEmbedder
from .vector_db import get_vector_db

def run_build(cfg: dict):
    apps_dir = cfg["paths"]["apps_dir"]
    results_dir = cfg["paths"]["results_dir"]
    db_types = cfg["phases"]["build"]["db_types"]
    index_types = cfg["phases"]["build"]["index_types"]
    modes = cfg["phases"]["build"]["modes"]
    batch_size = cfg["phases"]["build"]["batch_size"]
    drop_existing = cfg["phases"]["build"]["drop_existing"]
    
    os.makedirs(results_dir, exist_ok=True)
    app_sections = load_app_sections(apps_dir)
    build_metrics = []

    for db_type in db_types:
        cfg["database"]["type"] = db_type
        db = get_vector_db(cfg)
        
        for index_type in index_types:
            for mode in modes:
                print(f"\n🔧 Building: db={db_type} | idx={index_type} | mode={mode}")
                embedder = BGEEmbedder(mode=mode, cfg=cfg["model"])
                
                for app_id, sections in app_sections.items():
                    coll_name = f"{app_id}_{mode}_{db_type}_{index_type}"
                    if db.collection_exists(coll_name):
                        if drop_existing: db.drop_collection(coll_name)
                        else: print(f"⏩ Skipping: {coll_name}"); continue
                    
                    db.create_collection(coll_name, embedder.dim, mode, index_type)
                    section_ids = [s["section_id"] for s in sections]
                    texts = [s["embed_text"] for s in sections]
                    metadatas = [s["metadata"] for s in sections]
                    
                    start_time = time.time()
                    total = len(texts)
                    for i in range(0, total, batch_size):
                        batch_ids = section_ids[i:i+batch_size]
                        batch_texts = texts[i:i+batch_size]
                        batch_meta = metadatas[i:i+batch_size]
                        
                        dense_vecs = embedder.encode_dense(batch_texts) if mode in ["dense","hybrid","finetuned"] else None
                        sparse_vecs = embedder.encode_sparse(batch_texts) if mode in ["sparse","hybrid","finetuned"] else None
                        
                        records = []
                        for j, sid in enumerate(batch_ids):
                            rec = {"id": sid, "payload": {"text": batch_texts[j], **batch_meta[j]}}
                            if dense_vecs is not None: rec["dense"] = dense_vecs[j].tolist()
                            if sparse_vecs is not None: rec["sparse"] = sparse_vecs[j]
                            records.append(rec)
                        if records: db.upsert(coll_name, records)
                        
                    db.flush()
                    build_time = time.time() - start_time
                    build_metrics.append({
                        "mode": mode, "db_type": db_type, "index_type": index_type, "app_id": app_id, 
                        "collection": coll_name, "build_time_sec": round(build_time, 3),
                        "docs_indexed": total, "docs_per_sec": round(total/build_time, 1) if build_time>0 else 0
                    })
                    print(f"✅ {coll_name}: {total} sections | {build_time:.2f}s")
                    
                embedder.cleanup(); torch.cuda.empty_cache(); gc.collect()

    out_path = os.path.join(results_dir, "build_metrics.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for m in build_metrics: f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"\n📊 Build metrics saved to {out_path}")