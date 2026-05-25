import json
import os
from pathlib import Path
from typing import Any, Dict, List


class FAQManager:
    """Manager pour sauvegarder/charger des fichiers FAQ et lancer l'indexation via
    une instance RAGManager fournie.
    """

    def __init__(self, project_root: Path, rag_manager):
        self.project_root = Path(project_root)
        self.rag_manager = rag_manager
        self.extract_faq_dir = self.project_root / "extract" / "app" / "faq"
        os.makedirs(self.extract_faq_dir, exist_ok=True)

    def _faq_path(self, app_slug: str) -> Path:
        safe = app_slug.replace("/", "_").replace(" ", "_")
        return self.extract_faq_dir / f"{safe}.json"

    def save_faq_json(self, app_slug: str, data: Any) -> Path:
        p = self._faq_path(app_slug)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return p

    def load_faq_json(self, app_slug: str) -> Any:
        p = self._faq_path(app_slug)

        # Priorité 1: Fichier dans extract/app/faq/
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)

        # Priorité 2: Fichier dans extract/app/json/ (manuels convertis)
        json_dir = self.project_root / "extract" / "app" / "json"
        json_paths = [
            json_dir / f"{app_slug}_2levels_cleaned.json",
            json_dir / f"{app_slug}_2levels.json",
            json_dir / f"{app_slug}.json",
        ]

        for json_path in json_paths:
            if json_path.is_file():
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)

        return None

    def delete_faq_json(self, app_slug: str) -> bool:
        p = self._faq_path(app_slug)
        if p.is_file():
            p.unlink()
            return True
        return False

    def list_faq_files(self) -> List[Path]:
        if not self.extract_faq_dir.exists():
            return []
        return sorted(self.extract_faq_dir.glob("*.json"))

    def load_all_faq_items(self) -> List[Dict[str, Any]]:
        """Charge toutes les FAQ locales pour reconstruire la collection partagée."""
        all_items: List[Dict[str, Any]] = []
        for faq_file in self.list_faq_files():
            try:
                with open(faq_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("items") if isinstance(data, dict) else data
                items = items if isinstance(items, list) else []
                app_slug = faq_file.stem
                for item in items:
                    if isinstance(item, dict):
                        copied = dict(item)
                        copied.setdefault("app", app_slug)
                        copied.setdefault("faq_file", faq_file.name)
                        all_items.append(copied)
            except Exception:
                continue
        return all_items

    def _to_sections(self, app_slug: str, data: Any) -> List[Dict[str, Any]]:
        """Convertit la JSON FAQ en sections attendues par Chunker.

        Expected input format (MVP): list of entries
        [ { "id"?: "..", "question": "..", "answer": "..", "meta"?: {} }, ... ]
        """
        sections = []
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Accept key->value pairs
            items = []
            for k, v in data.items():
                if isinstance(v, dict) and ("question" in v or "answer" in v):
                    items.append(v)
        else:
            items = []

        for i, it in enumerate(items):
            q = it.get("question") or it.get("q") or it.get("problem") or ""
            a = it.get("answer") or it.get("a") or it.get("content") or ""
            entry_id = it.get("id") or f"faq_{app_slug}_{i}"
            section = {
                "id": entry_id,
                "section_id": entry_id,
                "problem": q,
                "content": a,
                "source_type": "faq",
                "app": app_slug,
            }
            # include optional metadata
            if isinstance(it, dict):
                meta = {k: v for k, v in it.items() if k not in ("question", "q", "answer", "a", "content", "id")}
                if meta:
                    section["meta"] = meta
            sections.append(section)

        return sections

    def index_faq(self, app_slug: str) -> Dict[str, Any]:
        """Compatibilité: réindexe toute la collection FAQ partagée."""
        return self.reindex_all_faqs()

    def reindex_all_faqs(self) -> Dict[str, Any]:
        """Reconstruit la collection Qdrant partagée `faq` à partir de tous les JSON locaux."""
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return {"success": False, "error": "rag not ready"}

        all_items = self.load_all_faq_items()
        if not all_items:
            try:
                if self.rag_manager.vector_db.collection_exists("faq"):
                    self.rag_manager.vector_db.drop_collection("faq")
            except Exception:
                pass
            return {"success": True, "collection": "faq", "count": 0}

        sections: List[Dict[str, Any]] = []
        for item in all_items:
            app_slug = str(item.get("app") or "faq")
            q = item.get("question") or item.get("q") or item.get("problem") or ""
            a = item.get("answer") or item.get("a") or item.get("content") or ""
            entry_id = item.get("id") or f"faq_{app_slug}_{len(sections)}"
            section = {
                "id": entry_id,
                "section_id": entry_id,
                "problem": q,
                "content": a,
                "source_type": "faq",
                "app": app_slug,
                "meta": {k: v for k, v in item.items() if k not in {"question", "q", "answer", "a", "content", "id"}},
            }
            sections.append(section)

        collection_name = "faq"
        try:
            if self.rag_manager.vector_db.collection_exists(collection_name):
                self.rag_manager.vector_db.drop_collection(collection_name)
        except Exception:
            pass

        self.rag_manager._index_collection(collection_name, sections)
        return {"success": True, "collection": collection_name, "count": len(sections)}

