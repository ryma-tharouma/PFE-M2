import json
import os
import sys
import glob
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from dotenv import load_dotenv
import asyncio
import threading

PROJECT_ROOT     = Path(__file__).resolve().parents[2]
PROD_DIR         = PROJECT_ROOT / "prod"
EXTRACT_JSON_DIR = PROJECT_ROOT / "extract" / "app" / "json"
QDRANT_DATA_PATH = PROD_DIR / "qdrant_data"
EXTRACT_FAQ_DIR  = PROJECT_ROOT / "extract" / "app" / "faq"
CONFIG_PATH      = PROD_DIR / "config.yaml"

sys.path.insert(0, str(PROD_DIR))

from assistant    import Assistant
from chunker      import Chunker
from embedder     import Embedder
from vector_store import get_vector_db

load_dotenv()


def _normalize_prod_paths(config: dict) -> dict:
    config = config.copy()
    gen = config.get("generator", {}).copy()
    if gen.get("prompt_file"):
        gen["prompt_file"] = str((PROD_DIR / gen["prompt_file"]).resolve())
    if gen.get("gguf_path"):
        gen["gguf_path"] = str((PROD_DIR / gen["gguf_path"]).resolve())
    config["generator"] = gen
    vdb = config.get("vector_db", {}).copy()
    vdb["path"] = str(QDRANT_DATA_PATH)
    config["vector_db"] = vdb
    return config


class RAGManager:
    def __init__(self):
        self.config      = None
        self.embedder    = None
        self.vector_db   = None
        self.assistant   = None
        self.initialized = False
        self.error_msg   = ""

    def initialize(self) -> bool:
        try:
            import yaml
            print("🔄 Config...")
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.config = _normalize_prod_paths(yaml.safe_load(f))
            print("📦 Embedder...")
            self.embedder  = Embedder(self.config)
            print("🗄️  Qdrant...")
            self.vector_db = get_vector_db(self.config)
            print("🤖 Assistant...")
            self.assistant = Assistant(self.config, db=self.vector_db, embedder=self.embedder)
            self._load_json_collections()
            self.initialized = True
            print("✅ RAG prêt!")
            return True
        except Exception as e:
            self.error_msg = str(e)
            import traceback; traceback.print_exc()
            return False

    def _load_json_collections(self):
        # ── Manuels ───────────────────────────────────────────────────
        if EXTRACT_JSON_DIR.exists():
            json_files = sorted(
                glob.glob(os.path.join(str(EXTRACT_JSON_DIR), "*_2levels_cleaned.json"))
            )
            if json_files:
                print(f"   📂 {len(json_files)} manuel(s) _2levels_cleaned.json trouvé(s)")
            for jf in json_files:
                try:
                    cname = Path(jf).stem.replace(" ", "_").replace("-", "_")
                    with open(jf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sections = data["sections"] if isinstance(data, dict) and "sections" in data else data
                    if not isinstance(sections, list):
                        print(f"   ⚠️  {cname}: format inattendu")
                        continue
                    existing    = self.vector_db.collection_exists(cname)
                    point_count = self.vector_db.collection_point_count(cname) if existing else 0
                    if existing and point_count > 0:
                        print(f"   ✅ Manuel {cname} (déjà indexé: {point_count} points)")
                    else:
                        if existing and point_count == 0:
                            try: self.vector_db.drop_collection(cname)
                            except Exception: pass
                        print(f"   🔄 Indexation manuel {cname}...")
                        self._index_collection(cname, sections)
                        print(f"   ✅ Manuel {cname} indexé")
                except Exception as e:
                    print(f"   ❌ Erreur manuel {jf}: {e}")
        else:
            print(f"   ⚠️  Dossier JSON manuels introuvable: {EXTRACT_JSON_DIR}")

        # ── FAQ ───────────────────────────────────────────────────────
        if EXTRACT_FAQ_DIR.exists():
            faq_files = sorted(EXTRACT_FAQ_DIR.glob("*.json"))
            if faq_files:
                print(f"   📂 {len(faq_files)} FAQ trouvée(s)")
            for faq_file in faq_files:
                try:
                    app_slug = faq_file.stem

                    with open(faq_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    items = data.get("items") if isinstance(data, dict) else data
                    items = items if isinstance(items, list) else []

                    if not items:
                        print(f"   ⚠️  FAQ {app_slug}: aucun item")
                        continue

                    # Au démarrage on utilise _resolve_faq_collection car on n'a
                    # pas accès à la BDD Laravel depuis Python.
                    collection_name = _resolve_faq_collection(app_slug, self.vector_db)
                    merged = collection_name != app_slug

                    sections = _faq_items_to_sections(app_slug, items)

                    if merged:
                        print(f"   🔗 FAQ {app_slug} → merge dans '{collection_name}'")
                        self._upsert_faq_into_collection(collection_name, sections)
                        print(f"   ✅ FAQ {app_slug} mergée dans '{collection_name}'")
                    else:
                        existing    = self.vector_db.collection_exists(collection_name)
                        point_count = self.vector_db.collection_point_count(collection_name) if existing else 0
                        if existing and point_count > 0:
                            print(f"   ✅ FAQ {app_slug} (déjà indexée: {point_count} points dans '{collection_name}')")
                        else:
                            if existing and point_count == 0:
                                try: self.vector_db.drop_collection(collection_name)
                                except Exception: pass
                            print(f"   🔄 Indexation FAQ {app_slug} → '{collection_name}'...")
                            self._index_collection(collection_name, sections)
                            print(f"   ✅ FAQ {app_slug} indexée dans '{collection_name}' ({len(sections)} items)")

                except Exception as e:
                    print(f"   ❌ Erreur FAQ {faq_file}: {e}")
        else:
            print(f"   ℹ️  Dossier FAQ introuvable: {EXTRACT_FAQ_DIR}")

    def _index_collection(self, name: str, sections: list, force_recreate: bool = False):
        """Crée et indexe une collection Qdrant depuis zéro."""
        chunker    = Chunker(self.config)
        chunks     = chunker.process_sections(sections)
        if not chunks:
            raise ValueError(f"Aucun chunk généré pour {name}")
        texts      = [c["embed_text"] for c in chunks]
        embeddings = self.embedder.encode(texts)
        records    = [{"id": c["id"], "dense": vec, "payload": c.copy()} for c, vec in zip(chunks, embeddings)]
        if force_recreate and self.vector_db.collection_exists(name):
            self.vector_db.drop_collection(name)
        if not self.vector_db.collection_exists(name):
            self.vector_db.create_collection(name=name, dim=1024)
        self.vector_db.upsert(name=name, records=records)

    def _upsert_faq_into_collection(self, collection_name: str, sections: list):
        """
        Ajoute/met à jour les items FAQ dans une collection existante
        sans vider son contenu (upsert par ID).
        """
        chunker    = Chunker(self.config)
        chunks     = chunker.process_sections(sections)
        if not chunks:
            raise ValueError(f"Aucun chunk FAQ généré pour '{collection_name}'")
        texts      = [c["embed_text"] for c in chunks]
        embeddings = self.embedder.encode(texts)
        records    = [{"id": c["id"], "dense": vec, "payload": c.copy()} for c, vec in zip(chunks, embeddings)]
        self.vector_db.upsert(name=collection_name, records=records)

    def get_available_collections(self) -> list:
        if not self.initialized or not self.vector_db:
            return []
        try:
            return self.vector_db.list_collections()
        except Exception:
            return []

    def resolve_collection(self, requested: str) -> str | None:
        """
        Résout le nom de collection pour le chat WebSocket/HTTP.
        Le nom reçu est application->qdrant_collection côté Laravel,
        donc il doit correspondre exactement à une collection existante.
        """
        available = self.get_available_collections()
        if not available:
            return None

        # Correspondance exacte (cas normal : Laravel envoie le bon nom)
        if requested in available:
            return requested

        # Normalisation casse/tirets (fallback)
        req_norm = requested.lower().replace("-", "_").replace(" ", "_")
        for col in available:
            if col.lower().replace("-", "_") == req_norm:
                return col

        # Dernier recours : cherche une collection _2levels_cleaned qui contient le slug
        for col in available:
            if col.endswith("_2levels_cleaned") and req_norm in col:
                return col

        return None


# ─────────────────────────────────────────────────────────────────────
# Helpers globaux
# ─────────────────────────────────────────────────────────────────────

def _resolve_faq_collection(app_slug: str, vector_db) -> str:
    """
    Résolution au DÉMARRAGE uniquement (on n'a pas la BDD Laravel).

    Cherche une collection manuel qui CONTIENT le slug (gère les préfixes
    comme "manuel_" ajoutés par l'extracteur).

    Priorité :
      1. Toute collection *_2levels_cleaned dont le nom contient app_slug
      2. {app_slug} existe déjà → réutilise
      3. Sinon → nouvelle collection {app_slug}
    """
    try:
        available = vector_db.list_collections()
    except Exception:
        return app_slug

    # Priorité 1 : collection manuel qui contient le slug
    # ex: "manuel_parc_auto_2levels_cleaned" contient "parc_auto"
    for col in available:
        if col.endswith("_2levels_cleaned") and app_slug in col:
            return col

    # Priorité 2 : collection FAQ déjà existante
    if app_slug in available:
        return app_slug

    # Priorité 3 : nouvelle collection
    return app_slug


def _faq_items_to_sections(app_slug: str, items: list) -> list:
    """Convertit une liste d'items FAQ en sections pour le Chunker."""
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

        sections.append({
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
        })
    return sections


# ─────────────────────────────────────────────────────────────────────
# Initialisation
# ─────────────────────────────────────────────────────────────────────

rag_manager = RAGManager()

try:
    from faq_manager import FAQManager
    faq_manager = FAQManager(PROJECT_ROOT, rag_manager)
except Exception as e:
    print(f"⚠️  FAQManager non disponible: {e}")
    faq_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Démarrage...")
    await asyncio.get_event_loop().run_in_executor(None, rag_manager.initialize)
    yield
    print("🛑 Arrêt.")


app = FastAPI(title="Chatbot RAG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# WebSocket streaming
# ─────────────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    try:
        init = await asyncio.wait_for(websocket.receive_json(), timeout=30)
    except Exception:
        await websocket.close(code=1003)
        return

    user_id              = init.get("user_id", "anonymous")
    message              = (init.get("message") or "").strip()
    requested_collection = init.get("collection", "")
    collection_version   = str(init.get("collection_version") or "")
    max_turns            = int(init.get("max_turns", 1))

    if not message:
        await websocket.send_json({"type": "error", "error": "Message vide"})
        await websocket.close()
        return

    if not rag_manager.initialized:
        await websocket.send_json({"type": "error", "error": f"RAG non prêt: {rag_manager.error_msg}"})
        await websocket.close()
        return

    collection = rag_manager.resolve_collection(requested_collection)
    if collection is None:
        available = rag_manager.get_available_collections()
        await websocket.send_json({
            "type":  "error",
            "error": f"Collection '{requested_collection}' introuvable. Disponibles: {available}",
        })
        await websocket.close()
        return

    if collection != requested_collection:
        print(f"   ℹ️  Collection résolue: '{requested_collection}' → '{collection}'")

    await websocket.send_json({"type": "typing", "status": True})

    loop  = asyncio.get_event_loop()
    queue = asyncio.Queue()

    def run_assistant():
        try:
            version_suffix = f":{collection_version}" if collection_version else ""
            session_id = f"{user_id}:{collection}{version_suffix}:session"
            rag_manager.assistant.config.setdefault("assistant", {})["max_turns"] = max_turns
            for item in rag_manager.assistant.chat(
                session_id=session_id,
                query=message,
                app_id=collection,
            ):
                asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(queue.put({"__error__": str(e)}), loop)

    threading.Thread(target=run_assistant, daemon=True).start()

    try:
        while True:
            item = await queue.get()
            if item is None:
                await websocket.send_json({"type": "done", "sources": []})
                break
            if isinstance(item, dict) and "__error__" in item:
                await websocket.send_json({"type": "error", "error": item["__error__"]})
                break
            if isinstance(item, dict) and item.get("done"):
                await websocket.send_json({"type": "done", "sources": item.get("sources", [])})
                break
            token = item if isinstance(item, str) else str(item)
            if token:
                await websocket.send_json({"type": "token", "text": token})
    except WebSocketDisconnect:
        return
    except Exception as e:
        try: await websocket.send_json({"type": "error", "error": str(e)})
        except Exception: pass
    finally:
        try: await websocket.send_json({"type": "typing", "status": False})
        except Exception: pass
        try: await websocket.close()
        except Exception: pass


# ─────────────────────────────────────────────────────────────────────
# REST — Health & Collections
# ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":      "ok" if rag_manager.initialized else "initializing",
        "error":       rag_manager.error_msg or None,
        "collections": rag_manager.get_available_collections(),
    }


@app.get("/api/collections")
def api_collections():
    return {"collections": rag_manager.get_available_collections()}


# ─────────────────────────────────────────────────────────────────────
# REST — Indexation manuels
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/index")
async def api_index(request: Request):
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    json_path  = (data.get("json_path")  or "").strip()
    collection = (data.get("collection") or "").strip()
    force_reindex = bool(data.get("force_reindex", False)) or bool(data.get("force", False))

    if not json_path or not collection:
        return JSONResponse(status_code=400, content={"error": "json_path et collection requis"})

    p = Path(json_path)
    if not p.name.endswith("_2levels_cleaned.json"):
        return JSONResponse(status_code=422, content={
            "error": f"Nom de fichier invalide : '{p.name}'. Doit se terminer par '_2levels_cleaned.json'."
        })

    expected_collection = p.stem.replace(" ", "_").replace("-", "_")
    if collection != expected_collection:
        return JSONResponse(status_code=422, content={
            "error": f"Collection incohérente : reçu '{collection}', attendu '{expected_collection}'."
        })

    if not p.is_file():
        return JSONResponse(status_code=404, content={"error": f"Fichier introuvable : {json_path}"})

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        sections = raw["sections"] if isinstance(raw, dict) and "sections" in raw else raw
        if not isinstance(sections, list):
            return JSONResponse(status_code=422, content={"error": "Format JSON inattendu (pas une liste)"})

        if rag_manager.vector_db.collection_exists(collection) and not force_reindex:
            return {"success": True, "collection": collection, "status": "already_exists"}

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, rag_manager._index_collection, collection, sections, force_reindex)

        return {"success": True, "collection": collection, "status": "indexed"}

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────────────────
# REST — FAQ
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/admin/faq/sync")
async def api_admin_faq_sync():
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    try:
        return faq_manager.reindex_all_faqs()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/faq/index")
async def api_faq_index(request: Request):
    """
    Indexe une FAQ dans la collection EXACTE spécifiée.

    Le champ "collection" reçu est application->qdrant_collection depuis Laravel
    (ex: "manuel_parc_auto_2levels_cleaned").

    On délègue à faq_manager.index_faq_into_collection() qui fait un upsert
    direct dans cette collection sans recalculer de slug.
    """
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    collection = (data.get("collection") or "").strip()
    items      = data.get("items") or []

    if not collection:
        return JSONResponse(status_code=400, content={"error": "Champ 'collection' requis"})
    if not items:
        return JSONResponse(status_code=400, content={"error": "Champ 'items' vide"})

    # Sauvegarder sur disque avec le slug extrait
    app_slug = faq_manager._collection_to_slug(collection)
    faq_manager.save_faq_json(app_slug, {"items": items})

    loop   = asyncio.get_event_loop()
    # Upsert dans la collection EXACTE — pas de recalcul de slug
    result = await loop.run_in_executor(
        None, faq_manager.index_faq_into_collection, collection, items
    )
    return result


def _collection_to_slug(collection_name: str) -> str:
    """
    Extrait un slug lisible depuis un nom de collection.
    ex: "manuel_parc_auto_2levels_cleaned" → "parc_auto"
        "parc_auto" → "parc_auto"
    """
    slug = collection_name
    # Enlever le préfixe "manuel_" s'il existe
    if slug.startswith("manuel_"):
        slug = slug[len("manuel_"):]
    # Enlever le suffixe "_2levels_cleaned" s'il existe
    if slug.endswith("_2levels_cleaned"):
        slug = slug[: -len("_2levels_cleaned")]
    return slug.strip("_") or collection_name


def _index_faq_into_exact_collection(
    collection_name: str,
    items: list,
    rag: RAGManager
) -> dict:
    """
    Indexe les items FAQ dans la collection EXACTE spécifiée.
    - Si la collection existe → upsert (ne vide pas le contenu existant)
    - Si elle n'existe pas → crée puis indexe
    """
    app_slug = _collection_to_slug(collection_name)
    sections = _faq_items_to_sections(app_slug, items)

    if not sections:
        return {"success": False, "error": "Aucune section valide générée depuis les items FAQ"}

    try:
        collection_exists = rag.vector_db.collection_exists(collection_name)

        if collection_exists:
            # Upsert dans la collection existante (manuel ou FAQ existante)
            rag._upsert_faq_into_collection(collection_name, sections)
            print(f"[FAQ Index] Upsert dans '{collection_name}' ({len(sections)} items)")
        else:
            # Créer et indexer une nouvelle collection FAQ dédiée
            rag._index_collection(collection_name, sections)
            print(f"[FAQ Index] Nouvelle collection '{collection_name}' créée ({len(sections)} items)")

        return {
            "success":    True,
            "collection": collection_name,
            "items":      len(sections),
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"success": False, "error": str(e), "collection": collection_name}


@app.post("/api/admin/faq/upload")
async def api_admin_faq_upload(request: Request):
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    app_slug = (data.get("app") or "").strip()
    if not app_slug:
        return JSONResponse(status_code=400, content={"error": "Champ 'app' requis"})

    try:
        faq_manager.save_faq_json(app_slug, data.get("items") or data.get("faq") or data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, faq_manager.index_faq, app_slug)
    return result


@app.get("/api/admin/faq/{app_slug}")
def api_admin_faq_get(app_slug: str):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    data = faq_manager.load_faq_json(app_slug)
    if data is None:
        return JSONResponse(status_code=404, content={"error": "FAQ introuvable"})
    return {"app": app_slug, "faq": data}


@app.put("/api/admin/faq/{app_slug}")
async def api_admin_faq_put(app_slug: str, request: Request):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    items = data.get("items") or data.get("faq") or data
    try:
        faq_manager.save_faq_json(app_slug, items)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    if rag_manager.initialized:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, faq_manager.index_faq, app_slug)
        return result

    return {"success": True, "collection": app_slug, "reindexed": False}


@app.delete("/api/admin/faq/{app_slug}")
async def api_admin_faq_delete(app_slug: str):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    try:
        deleted = faq_manager.delete_faq_json(app_slug)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "FAQ introuvable"})

        if rag_manager.initialized:
            try:
                collection_name = _resolve_faq_collection(app_slug, rag_manager.vector_db)
                merged = collection_name != app_slug

                if merged:
                    print(f"[FAQ] ⚠️  FAQ '{app_slug}' mergée dans '{collection_name}' "
                          f"(manuel) — collection conservée, points FAQ orphelins.")
                else:
                    if rag_manager.vector_db.collection_exists(collection_name):
                        rag_manager.vector_db.drop_collection(collection_name)
                        print(f"[FAQ] Collection dédiée '{collection_name}' supprimée de Qdrant")
            except Exception as e:
                print(f"[FAQ] Warning suppression collection '{app_slug}': {e}")

        return {"success": True, "deleted": True, "collection": app_slug}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/admin/faq/{app_slug}/index")
async def api_admin_faq_index(app_slug: str):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, faq_manager.index_faq, app_slug)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────────────────
# REST — Chats anonymisés
# ─────────────────────────────────────────────────────────────────────

@app.get("/api/admin/chats/{app_slug}")
def api_admin_chats(app_slug: str, limit: int = 50):
    logs_dir = Path(__file__).resolve().parent / "logs"
    pattern  = str(logs_dir / "assistant.log*")
    files    = sorted(glob.glob(pattern))
    if not files:
        return {"chats": []}

    import re
    queries   = {}
    responses = {}

    q_re = re.compile(r"Query received \| session_id=(?P<session>[^|]+) \| app_id=(?P<app>[^|]+) .* \| query=(?P<query>.*)$")
    r_re = re.compile(r"Response complete \| session_id=(?P<session>[^|]+) \| app_id=(?P<app>[^|]+) .* \| sources=(?P<sources>\[.*\]) \| answer=(?P<answer>.*)$")

    for fp in reversed(files):
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if "Query received" in line:
                        m = q_re.search(line)
                        if not m or m.group("app") != app_slug:
                            continue
                        session = m.group("session")
                        queries[session] = {"query": m.group("query").strip(), "ts": line.split(" | ")[0]}
                    elif "Response complete" in line:
                        m = r_re.search(line)
                        if not m or m.group("app") != app_slug:
                            continue
                        session = m.group("session")
                        sources = []
                        try: sources = json.loads(m.group("sources"))
                        except Exception: pass
                        responses[session] = {
                            "answer":  m.group("answer").strip(),
                            "sources": sources,
                            "ts":      line.split(" | ")[0],
                        }
        except Exception:
            continue

    pairs = []
    for session, q in queries.items():
        if session in responses:
            r = responses[session]
            pairs.append({
                "ts":       q.get("ts") or r.get("ts"),
                "question": q.get("query"),
                "answer":   r.get("answer"),
                "sources":  r.get("sources", []),
            })
            if len(pairs) >= limit:
                break

    return {"chats": pairs}


# ─────────────────────────────────────────────────────────────────────
# REST — Chat HTTP classique
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def api_chat(request: Request):
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    message              = (data.get("message") or "").strip()
    requested_collection = data.get("collection", "")
    user_id              = data.get("user_id", "anonymous")
    max_turns            = int(data.get("max_turns", 1))

    if not message:
        return JSONResponse(status_code=400, content={"error": "Message vide"})

    collection = rag_manager.resolve_collection(requested_collection)
    if collection is None:
        return JSONResponse(status_code=404, content={
            "error":     f"Collection '{requested_collection}' introuvable.",
            "available": rag_manager.get_available_collections(),
        })

    session_id    = f"{user_id}:{collection}:session"
    response_text = ""
    sources       = []

    for item in rag_manager.assistant.chat(session_id=session_id, query=message, app_id=collection):
        if isinstance(item, dict) and item.get("done"):
            sources = item.get("sources", [])
        else:
            response_text += str(item)

    return {
        "success":    True,
        "response":   response_text,
        "sources":    sources,
        "collection": collection,
    }


# ─────────────────────────────────────────────────────────────────────
# REST — Suppression de collection manuelle
# ─────────────────────────────────────────────────────────────────────

@app.delete("/api/collections/{collection_name}")
async def api_delete_collection(collection_name: str):
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})

    if not collection_name.endswith("_2levels_cleaned"):
        return JSONResponse(status_code=422, content={
            "error": f"Nom de collection invalide : '{collection_name}'. Doit se terminer par '_2levels_cleaned'."
        })

    available = rag_manager.get_available_collections()
    if collection_name not in available:
        return JSONResponse(status_code=404, content={
            "error":     f"Collection '{collection_name}' introuvable.",
            "available": available,
        })

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, rag_manager.vector_db.delete_collection, collection_name)
        return {"success": True, "collection": collection_name, "status": "deleted"}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/admin/reload")
async def api_admin_reload():
    """Force la réinitialisation du RAG manager (recharge configuration,
    réinitialise le vector_db et l'assistant). Utilisé après suppression
    physique d'une collection pour s'assurer que le backend ne conserve
    pas d'état obsolète en mémoire.
    """
    try:
        loop = asyncio.get_event_loop()
        # Re-initialize synchronously in executor to avoid blocking event loop
        result = await loop.run_in_executor(None, rag_manager.initialize)
        return {"success": bool(result)}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────────────────
# Gestionnaires d'erreurs
# ─────────────────────────────────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exc(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

@app.exception_handler(Exception)
async def generic_exc(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")