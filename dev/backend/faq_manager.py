import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FAQManager:
    """
    Manager FAQ — indexation dans la collection Qdrant appropriée.

    Convention de résolution de collection (par priorité) :
      1. Une collection {slug}_2levels_cleaned existe  → on l'utilise (même app, manuel)
      2. Une collection {slug} existe déjà             → on la réutilise
      3. Aucune collection existante                   → on crée {slug} dans qdrant_data
         (PAS de sous-dossier faq, directement à la racine de qdrant_data)
    """

    def __init__(self, project_root: Path, rag_manager):
        self.project_root = Path(project_root)
        self.rag_manager  = rag_manager
        self.faq_dir      = self.project_root / "extract" / "app" / "faq"
        os.makedirs(self.faq_dir, exist_ok=True)

    # ----------------------------------------------------------------
    # Helpers chemins
    # ----------------------------------------------------------------

    def _faq_path(self, app_slug: str) -> Path:
        safe = app_slug.replace("/", "_").replace(" ", "_")
        return self.faq_dir / f"{safe}.json"

    def _slug_from_path(self, path: Path) -> str:
        return path.stem  # ex: "excel", "parc_auto"

    # ----------------------------------------------------------------
    # Résolution du nom de collection Qdrant
    # ----------------------------------------------------------------

    def resolve_collection_for_faq(self, app_slug: str) -> str:
        """
        Résout la collection Qdrant cible pour une FAQ :
          1. {slug}_2levels_cleaned existe  → on y merge la FAQ
          2. {slug} existe déjà             → on la réutilise
          3. Sinon                          → on crée {slug}
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return app_slug

        try:
            available = self.rag_manager.vector_db.list_collections()
        except Exception:
            return app_slug

        # Priorité 1 : collection manuel du même nom
        manual_collection = f"{app_slug}_2levels_cleaned"
        if manual_collection in available:
            return manual_collection

        # Priorité 2 : collection FAQ déjà existante
        if app_slug in available:
            return app_slug

        # Priorité 3 : nouvelle collection portant le slug
        return app_slug

    # ----------------------------------------------------------------
    # CRUD fichiers JSON
    # ----------------------------------------------------------------

    def save_faq_json(self, app_slug: str, data: Any) -> Path:
        p = self._faq_path(app_slug)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return p

    def load_faq_json(self, app_slug: str) -> Optional[Any]:
        p = self._faq_path(app_slug)
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def delete_faq_json(self, app_slug: str) -> bool:
        p = self._faq_path(app_slug)
        if p.is_file():
            p.unlink()
            return True
        return False

    def list_faq_files(self) -> List[Path]:
        if not self.faq_dir.exists():
            return []
        return sorted(self.faq_dir.glob("*.json"))

    # ----------------------------------------------------------------
    # Conversion items → sections (format attendu par Chunker)
    # ----------------------------------------------------------------

    def _to_sections(self, app_slug: str, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        sections = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            problem = (
                item.get("problem")
                or item.get("question")
                or item.get("q")
                or ""
            )
            answer = (
                item.get("answer")
                or item.get("a")
                or item.get("content")
                or ""
            )

            if not problem or not answer:
                continue

            section_id = (
                item.get("section_id")
                or item.get("id")
                or f"faq_{app_slug}_{i}"
            )

            full_text = item.get("full_text") or f"problem: {problem}\nanswer: {answer}"

            section = {
                "id":          section_id,
                "section_id":  section_id,
                "problem":     problem,
                "content":     answer,
                "full_text":   full_text,
                "embed_text":  full_text,
                "source_type": "faq",
                "source":      item.get("source") or "",
                "title":       item.get("title") or "",
                "applies_to":  item.get("applies_to") or "",
                "app":         app_slug,
            }
            sections.append(section)

        return sections

    # ----------------------------------------------------------------
    # Indexation d'une seule application
    # ----------------------------------------------------------------

    def index_faq(self, app_slug: str) -> Dict[str, Any]:
        """
        Indexe le fichier JSON d'une application.

        Résolution de la collection cible (par priorité) :
          1. {slug}_2levels_cleaned existe  → merge dans la collection manuel
          2. {slug} existe                  → réutilise
          3. Sinon                          → crée {slug} directement dans qdrant_data
             (pas de sous-dossier faq)
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return {"success": False, "error": "rag not ready"}

        data = self.load_faq_json(app_slug)
        if data is None:
            return {"success": False, "error": f"Fichier FAQ introuvable pour '{app_slug}'"}

        sections = self._to_sections(app_slug, data)
        if not sections:
            return {"success": False, "error": f"Aucun item valide dans la FAQ '{app_slug}'"}

        # Résoudre la collection cible
        collection_name = self.resolve_collection_for_faq(app_slug)
        merged_into_manual = collection_name.endswith("_2levels_cleaned")

        try:
            if merged_into_manual:
                # On AJOUTE les items FAQ à la collection manuel existante (upsert)
                # sans vider la collection pour ne pas perdre le contenu du manuel
                print(f"[FAQ] 🔗 Merge FAQ '{app_slug}' → collection manuel '{collection_name}'")
                self._upsert_into_collection(collection_name, sections)
            else:
                # Collection FAQ dédiée : on recrée proprement
                if self.rag_manager.vector_db.collection_exists(collection_name):
                    self.rag_manager.vector_db.drop_collection(collection_name)
                print(f"[FAQ] 📥 Indexation FAQ '{app_slug}' → nouvelle collection '{collection_name}'")
                self.rag_manager._index_collection(collection_name, sections)

            print(f"[FAQ] ✅ '{app_slug}' indexé dans '{collection_name}' ({len(sections)} items)")
            return {
                "success":             True,
                "collection":          collection_name,
                "count":               len(sections),
                "merged_into_manual":  merged_into_manual,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _upsert_into_collection(self, collection_name: str, sections: list):
        """
        Ajoute/met à jour des sections dans une collection existante
        sans la vider (pour le merge FAQ dans la collection manuel).
        """
        from chunker import Chunker
        chunker    = Chunker(self.rag_manager.config)
        chunks     = chunker.process_sections(sections)
        if not chunks:
            raise ValueError(f"Aucun chunk généré pour '{collection_name}'")
        texts      = [c["embed_text"] for c in chunks]
        embeddings = self.rag_manager.embedder.encode(texts)
        records    = [
            {"id": c["id"], "dense": vec, "payload": c.copy()}
            for c, vec in zip(chunks, embeddings)
        ]
        # La collection existe déjà, on fait juste un upsert
        self.rag_manager.vector_db.upsert(name=collection_name, records=records)

    # ----------------------------------------------------------------
    # Réindexation de toutes les applications
    # ----------------------------------------------------------------

    def reindex_all_faqs(self) -> Dict[str, Any]:
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return {"success": False, "error": "rag not ready"}

        faq_files = self.list_faq_files()
        if not faq_files:
            return {"success": True, "collections": [], "total_items": 0}

        results      = []
        total_items  = 0
        total_errors = 0

        for faq_file in faq_files:
            app_slug = self._slug_from_path(faq_file)
            result   = self.index_faq(app_slug)
            results.append({
                "app":                 app_slug,
                "collection":          result.get("collection", app_slug),
                "count":               result.get("count", 0),
                "success":             result.get("success", False),
                "merged_into_manual":  result.get("merged_into_manual", False),
                "error":               result.get("error"),
            })
            if result.get("success"):
                total_items += result.get("count", 0)
            else:
                total_errors += 1
                print(f"[FAQ] ❌ Erreur pour '{app_slug}': {result.get('error')}")

        print(f"[FAQ] Sync terminé: {len(faq_files)} app(s), {total_items} items, {total_errors} erreur(s)")

        return {
            "success":      total_errors == 0,
            "collections":  [r["collection"] for r in results if r["success"]],
            "results":      results,
            "total_items":  total_items,
            "total_errors": total_errors,
        }

    # ----------------------------------------------------------------
    # Chargement de tous les items (lecture seule)
    # ----------------------------------------------------------------

    def load_all_faq_items(self) -> List[Dict[str, Any]]:
        all_items = []
        for faq_file in self.list_faq_files():
            try:
                with open(faq_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items    = data.get("items") if isinstance(data, dict) else data
                items    = items if isinstance(items, list) else []
                app_slug = self._slug_from_path(faq_file)
                for item in items:
                    if isinstance(item, dict):
                        copied = dict(item)
                        copied.setdefault("app", app_slug)
                        all_items.append(copied)
            except Exception:
                continue
        return all_items