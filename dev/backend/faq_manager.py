import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FAQManager:
    """
    Manager FAQ — indexation dans la collection Qdrant appropriée.

    Convention de résolution de collection (par priorité) :
      1. Une collection qui CONTIENT le slug ET finit par _2levels_cleaned
         ex: "manuel_parc_auto_2levels_cleaned" pour slug "parc_auto"
      2. Une collection {slug} existe déjà  → on la réutilise
      3. Aucune collection existante        → on crée {slug}
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
        return path.stem

    # ----------------------------------------------------------------
    # Résolution du nom de collection Qdrant
    # ----------------------------------------------------------------

    def resolve_collection_for_faq(self, app_slug: str) -> str:
        """
        Résout la collection Qdrant cible pour une FAQ.

        CORRECTION : cherche toute collection *_2levels_cleaned dont le nom
        CONTIENT le slug (gère les préfixes comme "manuel_" ajoutés par
        l'extracteur).

        ex: slug="parc_auto" → trouve "manuel_parc_auto_2levels_cleaned" ✅
            avant → cherchait "parc_auto_2levels_cleaned" (introuvable) ❌
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return app_slug

        try:
            available = self.rag_manager.vector_db.list_collections()
        except Exception:
            return app_slug

        # Priorité 1 : toute collection _2levels_cleaned qui contient le slug
        # Couvre "manuel_parc_auto_2levels_cleaned", "parc_auto_2levels_cleaned", etc.
        for col in available:
            if col.endswith("_2levels_cleaned") and app_slug in col:
                return col

        # Priorité 2 : collection FAQ déjà existante avec le slug exact
        if app_slug in available:
            return app_slug

        # Priorité 3 : nouvelle collection
        return app_slug

    def resolve_collection_exact(self, collection_name: str) -> str:
        """
        Quand Laravel envoie directement le nom exact de collection
        (depuis application->qdrant_collection), on vérifie qu'elle existe
        et on la retourne telle quelle.
        Si elle n'existe pas encore, on la retourne quand même (sera créée).
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return collection_name

        try:
            available = self.rag_manager.vector_db.list_collections()
        except Exception:
            return collection_name

        # Correspondance exacte (cas normal)
        if collection_name in available:
            return collection_name

        # Normalisation casse (fallback)
        norm = collection_name.lower().replace("-", "_")
        for col in available:
            if col.lower().replace("-", "_") == norm:
                return col

        # N'existe pas encore → sera créée à l'indexation
        return collection_name

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
    # Indexation d'une seule application — par slug (sync pipeline)
    # ----------------------------------------------------------------

    def index_faq(self, app_slug: str) -> Dict[str, Any]:
        """
        Indexe le fichier JSON d'une application depuis son slug.
        Utilisé par ProcessFaqPipeline (sync périodique).

        La collection est résolue via resolve_collection_for_faq() qui
        cherche toute collection _2levels_cleaned contenant le slug.
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return {"success": False, "error": "rag not ready"}

        data = self.load_faq_json(app_slug)
        if data is None:
            return {"success": False, "error": f"Fichier FAQ introuvable pour '{app_slug}'"}

        sections = self._to_sections(app_slug, data)
        if not sections:
            return {"success": False, "error": f"Aucun item valide dans la FAQ '{app_slug}'"}

        collection_name    = self.resolve_collection_for_faq(app_slug)
        merged_into_manual = collection_name != app_slug

        return self._do_index(collection_name, sections, app_slug, merged_into_manual)

    # ----------------------------------------------------------------
    # Indexation dans une collection EXACTE (depuis Laravel via API)
    # ----------------------------------------------------------------

    def index_faq_into_collection(self, collection_name: str, items: list) -> Dict[str, Any]:
        """
        Indexe des items FAQ directement dans la collection EXACTE spécifiée.
        Utilisé par /api/faq/index quand Laravel envoie application->qdrant_collection.

        On ne recalcule PAS de slug : on upsert dans collection_name tel quel.
        """
        if not self.rag_manager or not getattr(self.rag_manager, "vector_db", None):
            return {"success": False, "error": "rag not ready"}

        if not items:
            return {"success": False, "error": "items vide"}

        # Extraire un slug pour nommer les sections (cosmétique uniquement)
        app_slug = self._collection_to_slug(collection_name)
        sections = self._to_sections(app_slug, {"items": items})

        if not sections:
            return {"success": False, "error": "Aucune section valide générée"}

        # Résoudre le nom exact (au cas où casse différente, etc.)
        resolved = self.resolve_collection_exact(collection_name)
        merged_into_manual = resolved.endswith("_2levels_cleaned")

        return self._do_index(resolved, sections, app_slug, merged_into_manual)

    # ----------------------------------------------------------------
    # Logique d'indexation commune
    # ----------------------------------------------------------------

    def _do_index(
        self,
        collection_name: str,
        sections: list,
        app_slug: str,
        merged_into_manual: bool
    ) -> Dict[str, Any]:
        try:
            collection_exists = self.rag_manager.vector_db.collection_exists(collection_name)

            if merged_into_manual or collection_exists:
                # Upsert sans vider : préserve le contenu du manuel
                print(f"[FAQ] 🔗 Upsert FAQ '{app_slug}' → '{collection_name}' ({len(sections)} items)")
                self._upsert_into_collection(collection_name, sections)
            else:
                # Nouvelle collection FAQ dédiée
                print(f"[FAQ] 📥 Création collection '{collection_name}' pour FAQ '{app_slug}'")
                self.rag_manager._index_collection(collection_name, sections)

            print(f"[FAQ] ✅ '{app_slug}' indexé dans '{collection_name}' ({len(sections)} items)")
            return {
                "success":            True,
                "collection":         collection_name,
                "count":              len(sections),
                "merged_into_manual": merged_into_manual,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "collection": collection_name}

    def _upsert_into_collection(self, collection_name: str, sections: list):
        """Upsert des sections dans une collection existante sans la vider."""
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
        self.rag_manager.vector_db.upsert(name=collection_name, records=records)

    @staticmethod
    def _collection_to_slug(collection_name: str) -> str:
        """
        Extrait un slug depuis un nom de collection.
        ex: "manuel_parc_auto_2levels_cleaned" → "parc_auto"
            "parc_auto" → "parc_auto"
        """
        slug = collection_name
        if slug.startswith("manuel_"):
            slug = slug[len("manuel_"):]
        if slug.endswith("_2levels_cleaned"):
            slug = slug[: -len("_2levels_cleaned")]
        return slug.strip("_") or collection_name

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
                "app":                app_slug,
                "collection":         result.get("collection", app_slug),
                "count":              result.get("count", 0),
                "success":            result.get("success", False),
                "merged_into_manual": result.get("merged_into_manual", False),
                "error":              result.get("error"),
            })
            if result.get("success"):
                total_items += result.get("count", 0)
            else:
                total_errors += 1
                print(f"[FAQ] ❌ Erreur pour '{app_slug}': {result.get('error')}")

        print(f"[FAQ] Sync terminé: {len(faq_files)} app(s), {total_items} items, {total_errors} erreur(s)")

        return {
            "success":     total_errors == 0,
            "collections": [r["collection"] for r in results if r["success"]],
            "results":     results,
            "total_items": total_items,
            "total_errors":total_errors,
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