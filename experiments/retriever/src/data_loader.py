# src/data_loader.py
import json
from pathlib import Path
from typing import Dict, List, Set

def load_app_sections(apps_dir: str) -> Dict[str, List[dict]]:
    """
    Loads sections from JSON/JSONL files. Each app file contains an array of section objects.
    Extracts section_id, concatenates breadcrumb + content for embedding, and preserves metadata.
    """
    app_sections = {}
    
    for filepath in sorted(Path(apps_dir).glob("*.json")) + sorted(Path(apps_dir).glob("*.jsonl")):
        app_id = filepath.stem
        sections = []
        
        with open(filepath, "r", encoding="utf-8") as f:
            if filepath.suffix == ".jsonl":
                data = [json.loads(line) for line in f if line.strip()]
            else:
                raw = json.load(f)
                data = raw if isinstance(raw, list) else [raw]
                
        for idx, item in enumerate(data):
            section_id = item.get("section_id", item.get("doc_id", f"sec_{app_id}_{idx}"))
            breadcrumb = str(item.get("breadcrumb", "")).strip()
            content = str(item.get("content", "")).strip()
            
            # Text to embed: breadcrumb + content
            embed_text = f"{breadcrumb} {content}".strip()
            if not embed_text:
                continue
                
            # Metadata for Milvus (lightweight, queryable, display-ready)
            metadata = {
                "title": item.get("title", ""),
                "global_title": item.get("global_title", ""),
                "parent": item.get("parent", ""),
                "level": int(item.get("level", 0)),
                "page": int(item.get("page", -1)),
                "source_pdf": item.get("source_pdf", ""),
                "section_id": section_id  # Keep for evaluation matching
            }
            
            sections.append({
                "section_id": section_id,
                "embed_text": embed_text,
                "metadata": metadata
            })
            
        if sections:
            app_sections[app_id] = sections
            print(f"📦 Loaded {len(sections)} sections for app: {app_id}")
            
    return app_sections

def load_queries(queries_path: str) -> List[dict]:
    """
    Loads evaluation queries. Supports single or multiple relevant section_ids.
    Expected: {"id": "q1", "app_id": "app_A", "query": "...", "relevant_doc_ids": ["sec_1", "sec_2"]}
    """
    queries = []
    with open(queries_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            entry = json.loads(line)
            
            # Normalize to list format
            if "relevant_doc_ids" in entry:
                ids = entry["relevant_doc_ids"]
                entry["relevant_doc_ids"] = ids if isinstance(ids, list) else [ids]
            elif "relevant_doc_id" in entry:
                val = entry.pop("relevant_doc_id")
                entry["relevant_doc_ids"] = val if isinstance(val, list) else [val]
            else:
                continue
                
            queries.append(entry)
    print(f"🔍 Loaded {len(queries)} evaluation queries")
    return queries

def build_qrels(queries: List[dict]) -> Dict[str, Set[str]]:
    """Creates ground-truth lookup: {query_id: {relevant_section_id_1, ...}}"""
    return {q["id"]: set(q["relevant_doc_ids"]) for q in queries}