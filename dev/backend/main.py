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
        """
        Charge UNIQUEMENT les fichiers *_2levels_cleaned.json depuis extract/app/json/.
        Chaque fichier = une collection Qdrant. Pas de doublons.
        Naming convention :
            extract        →  {slug}_2level.json
            après cleaning →  {slug}_2levels_cleaned.json   ← seul fichier indexé
            collection     →  {slug}_2levels_cleaned
        """
        if not EXTRACT_JSON_DIR.exists():
            print(f"   ⚠️  Dossier JSON introuvable: {EXTRACT_JSON_DIR}")
            return

        # ✅ Uniquement les fichiers *_2levels_cleaned.json
        json_files = sorted(
            glob.glob(os.path.join(str(EXTRACT_JSON_DIR), "*_2levels_cleaned.json"))
        )

        if not json_files:
            print(f"   ⚠️  Aucun fichier *_2levels_cleaned.json trouvé dans {EXTRACT_JSON_DIR}")
            return

        print(f"   📂 {len(json_files)} fichier(s) _2levels_cleaned.json trouvé(s)")

        for jf in json_files:
            try:
                # Nom de collection = stem du fichier, espaces/tirets → _
                # ex: mon_app_2levels_cleaned.json → collection "mon_app_2levels_cleaned"
                cname = Path(jf).stem.replace(" ", "_").replace("-", "_")

                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                sections = data["sections"] if isinstance(data, dict) and "sections" in data else data
                if not isinstance(sections, list):
                    print(f"   ⚠️  {cname}: format inattendu (pas une liste)")
                    continue

                existing = self.vector_db.collection_exists(cname)
                point_count = self.vector_db.collection_point_count(cname) if existing else 0

                if existing and point_count > 0:
                    print(f"   ✅ {cname} (déjà indexé: {point_count} point(s))")
                else:
                    if existing and point_count == 0:
                        print(f"   ⚠️  {cname} existe mais est vide → réindexation")
                        try:
                            self.vector_db.drop_collection(cname)
                        except Exception:
                            pass
                    print(f"   🔄 Indexation de {cname}...")
                    self._index_collection(cname, sections)
                    print(f"   ✅ {cname} indexé")

            except Exception as e:
                print(f"   ❌ Erreur sur {jf}: {e}")

    def _index_collection(self, name: str, sections: list):
        chunker    = Chunker(self.config)
        chunks     = chunker.process_sections(sections)
        if not chunks:
            raise ValueError(f"Aucun chunk généré pour {name}")
        texts      = [c["embed_text"] for c in chunks]
        embeddings = self.embedder.encode(texts)
        records    = [{"id": c["id"], "dense": vec, "payload": c.copy()} for c, vec in zip(chunks, embeddings)]
        if not self.vector_db.collection_exists(name):
            # Stocké dans : qdrant_data/collection/{name}
            self.vector_db.create_collection(name=name, dim=1024)
        self.vector_db.upsert(name=name, records=records)

    def get_available_collections(self) -> list:
        """Retourne la liste des collections disponibles dans Qdrant."""
        if not self.initialized or not self.vector_db:
            return []
        try:
            return self.vector_db.list_collections()
        except Exception:
            return []

    def resolve_collection(self, requested: str) -> str | None:
        """
        Résout le nom de collection demandé.
        Retourne le nom exact si trouvé, sinon None.
        """
        available = self.get_available_collections()
        if not available:
            return None

        # Correspondance exacte
        if requested in available:
            return requested

        # Correspondance insensible à la casse + normalisation
        req_norm = requested.lower().replace("-", "_").replace(" ", "_")
        for col in available:
            if col.lower().replace("-", "_") == req_norm:
                return col

        # Fallback : cherche si le nom demandé est un préfixe d'une collection _2levels_cleaned
        for col in available:
            if col.endswith("_2levels_cleaned") and col.startswith(req_norm):
                return col

        return None


rag_manager = RAGManager()

# FAQ manager (lazy import to avoid circular imports)
try:
    from faq_manager import FAQManager
    faq_manager = FAQManager(PROJECT_ROOT, rag_manager)
except Exception:
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
    max_turns            = int(init.get("max_turns", 1))

    if not message:
        await websocket.send_json({"type": "error", "error": "Message vide"})
        await websocket.close()
        return

    if not rag_manager.initialized:
        await websocket.send_json({"type": "error", "error": f"RAG non prêt: {rag_manager.error_msg}"})
        await websocket.close()
        return

    # ── Résolution de la collection ───────────────────────────────────
    collection = rag_manager.resolve_collection(requested_collection)
    if collection is None:
        available = rag_manager.get_available_collections()
        await websocket.send_json({
            "type": "error",
            "error": f"Collection '{requested_collection}' introuvable. Disponibles: {available}"
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
            session_id = f"{user_id}:{collection}:session"
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
# REST endpoints
# ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":      "ok" if rag_manager.initialized else "initializing",
        "error":       rag_manager.error_msg or None,
        "collections": rag_manager.get_available_collections(),
    }


@app.post("/api/admin/faq/upload")
async def api_admin_faq_upload(request: Request):
    """Upload d'un JSON FAQ pour une application puis indexation automatique.
    Body JSON: { "app": "app_slug", "items": [ {"question":"...","answer":"..."}, ... ] }
    """
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

    # Sauvegarde
    try:
        faq_path = faq_manager.save_faq_json(app_slug, data.get("items") or data.get("faq") or data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # Indexation en arrière-plan
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, faq_manager.index_faq, app_slug)

    return {"success": True, "path": str(faq_path)}


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
    try:
        faq_manager.save_faq_json(app_slug, data.get("items") or data.get("faq") or data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/admin/faq/{app_slug}")
async def api_admin_faq_delete(app_slug: str):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})

    try:
        deleted = faq_manager.delete_faq_json(app_slug)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "FAQ introuvable"})

        sync_result = faq_manager.reindex_all_faqs() if rag_manager.initialized else {"success": True}
        return {"success": True, "deleted": True, "sync": sync_result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # Optionnel: relancer l'indexation
    qs = dict(request.query_params)
    if qs.get("reindex", "false").lower() in ("1", "true", "yes"):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, faq_manager.index_faq, app_slug)

    return {"success": True}


@app.post("/api/admin/faq/{app_slug}/index")
async def api_admin_faq_index(app_slug: str):
    if faq_manager is None:
        return JSONResponse(status_code=500, content={"error": "FAQ manager non disponible"})
    loop = asyncio.get_event_loop()
    try:
        res = await loop.run_in_executor(None, faq_manager.index_faq, app_slug)
        return res
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/admin/chats/{app_slug}")
def api_admin_chats(app_slug: str, limit: int = 50):
    """Retourne les derniers chats anonymisés pour une application.
    Lit les fichiers de logs 'assistant.log*' dans dev/backend/logs/.
    """
    # Recherche des fichiers de logs (rotated)
    logs_dir = Path(__file__).resolve().parent / "logs"
    pattern = str(logs_dir / "assistant.log*")
    files = sorted(glob.glob(pattern))
    if not files:
        return {"chats": []}

    entries = []
    import re

    # Simple parser: collecte Query received et Response complete et les associe par session_id
    queries = {}
    responses = {}

    q_re = re.compile(r"Query received \| session_id=(?P<session>[^|]+) \| app_id=(?P<app>[^|]+) .* \| query=(?P<query>.*)$")
    r_re = re.compile(r"Response complete \| session_id=(?P<session>[^|]+) \| app_id=(?P<app>[^|]+) .* \| sources=(?P<sources>\[.*\]) \| answer=(?P<answer>.*)$")

    # Read files newest first
    for fp in reversed(files):
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if "Query received" in line:
                        m = q_re.search(line)
                        if not m:
                            continue
                        if m.group("app") != app_slug:
                            continue
                        session = m.group("session")
                        query = m.group("query").strip()
                        queries[session] = {"query": query, "ts": line.split(" | ")[0]}
                    elif "Response complete" in line:
                        m = r_re.search(line)
                        if not m:
                            continue
                        if m.group("app") != app_slug:
                            continue
                        session = m.group("session")
                        sources = []
                        try:
                            sources = json.loads(m.group("sources"))
                        except Exception:
                            sources = []
                        answer = m.group("answer").strip()
                        responses[session] = {"answer": answer, "sources": sources, "ts": line.split(" | ")[0]}
        except Exception:
            continue

    # Build anonymized pairs
    pairs = []
    for session, q in queries.items():
        if session in responses:
            r = responses[session]
            pairs.append({
                "ts": q.get("ts") or r.get("ts"),
                "question": q.get("query"),
                "answer": r.get("answer"),
                "sources": r.get("sources", []),
            })
            if len(pairs) >= limit:
                break

    return {"chats": pairs}


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
            "error": f"Collection '{requested_collection}' introuvable.",
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


@app.get("/api/collections")
def api_collections():
    return {"collections": rag_manager.get_available_collections()}


@app.post("/api/index")
async def api_index(request: Request):
    """
    Appelé par ProcessManualPipeline (Laravel) après le cleaning.
    Body JSON : {
        "json_path":   "/chemin/absolu/xxx_2levels_cleaned.json",
        "collection":  "xxx_2levels_cleaned"
    }
    Convention de nommage obligatoire :
        - fichier extrait  →  {slug}_2level.json
        - fichier nettoyé  →  {slug}_2levels_cleaned.json   ← c'est ce fichier qui est indexé
        - collection Qdrant →  {slug}_2levels_cleaned        (= stem du fichier nettoyé)
    """
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})

    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON requis"})

    json_path  = (data.get("json_path") or "").strip()
    collection = (data.get("collection") or "").strip()

    if not json_path or not collection:
        return JSONResponse(status_code=400, content={"error": "json_path et collection requis"})

    # ── Validation de la convention de nommage ────────────────────────
    p = Path(json_path)
    if not p.name.endswith("_2levels_cleaned.json"):
        return JSONResponse(status_code=422, content={
            "error": (
                f"Nom de fichier invalide : '{p.name}'. "
                "Le fichier nettoyé doit se terminer par '_2levels_cleaned.json'."
            )
        })

    expected_collection = p.stem.replace(" ", "_").replace("-", "_")
    if collection != expected_collection:
        return JSONResponse(status_code=422, content={
            "error": (
                f"Nom de collection incohérent : reçu '{collection}', "
                f"attendu '{expected_collection}' (déduit du nom de fichier)."
            )
        })

    if not p.is_file():
        return JSONResponse(status_code=404, content={"error": f"Fichier introuvable : {json_path}"})

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        sections = raw["sections"] if isinstance(raw, dict) and "sections" in raw else raw

        if not isinstance(sections, list):
            return JSONResponse(status_code=422, content={"error": "Format JSON inattendu (pas une liste)"})

        if rag_manager.vector_db.collection_exists(collection):
            return {"success": True, "collection": collection, "status": "already_exists"}

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            rag_manager._index_collection,
            collection,
            sections,
        )

        return {"success": True, "collection": collection, "status": "indexed"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/collections/{collection_name}")
async def api_delete_collection(collection_name: str):
    """
    Supprime une collection Qdrant (qdrant_data/collection/{collection_name}).
    Le nom doit respecter la convention : se terminer par '_2levels_cleaned'.
    """
    if not rag_manager.initialized:
        return JSONResponse(status_code=503, content={"error": "RAG non prêt"})

    if not collection_name.endswith("_2levels_cleaned"):
        return JSONResponse(status_code=422, content={
            "error": (
                f"Nom de collection invalide : '{collection_name}'. "
                "Doit se terminer par '_2levels_cleaned'."
            )
        })

    available = rag_manager.get_available_collections()
    if collection_name not in available:
        return JSONResponse(status_code=404, content={
            "error": f"Collection '{collection_name}' introuvable.",
            "available": available,
        })

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            rag_manager.vector_db.delete_collection,
            collection_name,
        )
        return {"success": True, "collection": collection_name, "status": "deleted"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


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