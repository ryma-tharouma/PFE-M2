# app.py
import gc
import json
import os

import streamlit as st
import yaml

from assistant import Assistant
from chunker import Chunker
from embedder import Embedder
from vector_store import get_vector_db


# ----------------------------------------------------------------------
# Load config (cached globally)
# ----------------------------------------------------------------------

@st.cache_resource
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

CONFIG = load_config()
VECTOR_SIZE = 1024  # BGE-M3 output dimension
CHUNKER_CFG = CONFIG.get("chunker", {})
ASSISTANT_CFG = CONFIG.get("assistant", {})


# ----------------------------------------------------------------------
# Indexing
# ----------------------------------------------------------------------

def index_sections(db, embedder, sections, collection_name, max_tokens, overlap):
    chunker = Chunker(CONFIG)
    chunks = chunker.process_sections(sections)
    if not chunks:
        raise ValueError("No chunks produced — check section content.")
    texts = [c["embed_text"] for c in chunks]
    embeddings = embedder.encode(texts)
    records = [
        {"id": c["id"], "dense": vec, "payload": c.copy()}
        for c, vec in zip(chunks, embeddings)
    ]
    db.upsert(name=collection_name, records=records)


# ----------------------------------------------------------------------
# Build assistant
# ----------------------------------------------------------------------

def build_assistant(
    app_id: str,
    sections_json: str,
    force_reindex: bool,
    max_turns: int,
    db_path: str = "qdrant_data",
) -> Assistant:
    sections = json.loads(sections_json)

    # Use a copy of config to set DB path
    temp_config = CONFIG.copy()
    temp_config["vector_db"] = CONFIG.get("vector_db", {}).copy()
    temp_config["vector_db"]["path"] = db_path

    # Open a single DB client for the lifetime of this assistant
    db = get_vector_db(temp_config)

    embedder = Embedder(CONFIG)

    if db.collection_exists(app_id) and not force_reindex:
        st.info(f"Collection '{app_id}' already exists. Enable 'Force re-index' to overwrite.")
    else:
        if db.collection_exists(app_id):
            db.drop_collection(app_id)
        db.create_collection(name=app_id, dim=VECTOR_SIZE)
        with st.spinner("Chunking and embedding sections…"):
            index_sections(
                db=db,
                embedder=embedder,
                sections=sections,
                collection_name=app_id,
                max_tokens=CHUNKER_CFG.get("max_tokens", 1024),
                overlap=CHUNKER_CFG.get("overlap", 10),
            )
        st.success("Indexing complete!")

    # Prepare assistant config with user's max_turns
    assistant_config = CONFIG.copy()
    assistant_config["assistant"] = assistant_config.get("assistant", {}).copy()
    assistant_config["assistant"]["max_turns"] = max_turns

    return Assistant(assistant_config, db=db, embedder=embedder)


# ----------------------------------------------------------------------
# Helper: tear down the current assistant and release the DB file lock
# ----------------------------------------------------------------------

def _close_current_assistant() -> None:
    """
    Closes the existing assistant's DB client, deletes the reference, and
    forces a GC cycle so Qdrant releases its __db.lock file before we try
    to open a new client pointing at the same path.
    """
    if "assistant" not in st.session_state:
        return

    old: Assistant = st.session_state.pop("assistant")

    # Close the vector DB connection (releases the file lock)
    try:
        if hasattr(old, "vector_db") and old.vector_db is not None:
            old.vector_db.close()
    except Exception:
        pass

    # Run any additional cleanup (generator / retriever / embedder)
    try:
        old.cleanup()
    except Exception:
        pass

    # Drop the reference and force CPython to finalise the Qdrant client
    # object — this is what actually releases the OS-level file lock.
    del old
    gc.collect()


# ----------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------

st.set_page_config(page_title="RAG Chat", layout="wide")
st.title("📄 RAG Chat – Upload & Ask")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("1. Upload JSON")
    uploaded_file = st.file_uploader("Select a JSON file (list of sections)", type=["json"])

    if uploaded_file:
        raw_bytes = uploaded_file.read()
        try:
            sections = json.loads(raw_bytes)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
            st.stop()

        st.success(f"Loaded {len(sections)} sections")

        base_name = os.path.splitext(uploaded_file.name)[0]
        app_id = base_name.replace(" ", "_").replace("-", "_")
        max_turns = st.slider("History turns", min_value=1, max_value=5, value=ASSISTANT_CFG.get("max_turns", 1))
        st.info("Reranking is configured in `config.yaml` (`reranker.enabled`).")
        force_reindex = st.checkbox("Force re-index (overwrite existing data)", value=False)

        if st.button("🚀 Index & Start Chat"):
            # ── CRITICAL: close the old client BEFORE opening a new one ──
            # Qdrant uses a file lock on the db path. If the old client is
            # still alive when get_vector_db() is called, it throws:
            #   "Storage folder already accessed by another instance"
            # _close_current_assistant() closes, deletes, and gc-collects
            # the old client so the lock is released first.
            _close_current_assistant()

            try:
                assistant = build_assistant(
                    app_id=app_id,
                    sections_json=json.dumps(sections),
                    force_reindex=force_reindex,
                    max_turns=max_turns,
                    db_path="qdrant_data",
                )
                st.session_state["assistant"] = assistant
                st.session_state["app_id"] = app_id
                st.session_state["messages"] = []
                st.success("Ready! Start chatting below.")
                st.balloons()
            except Exception as e:
                st.error(f"Failed to build assistant: {e}")

# ---------- Chat area ----------
if "assistant" not in st.session_state:
    st.info("👈 Upload a JSON file and click 'Index & Start Chat' to begin.")
    st.stop()

assistant: Assistant = st.session_state["assistant"]
app_id: str = st.session_state["app_id"]

st.header(f"💬 Chat with **{app_id}**")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about the manual…"):
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        sources = []

        for item in assistant.chat(
            session_id="streamlit_session",
            query=prompt,
            app_id=app_id,
        ):
            if isinstance(item, dict) and item.get("done"):
                sources = item.get("sources", [])
            else:
                full_response += item
                placeholder.markdown(full_response + "▌")

        placeholder.markdown(full_response)

        if sources:
            with st.expander("📚 Sources"):
                for src in sources:
                    if "breadcrumb" in src:
                        st.write(f"- {src['breadcrumb']} (PDF: {src.get('source_pdf', '?')})")
                    else:
                        st.write(f"- {src.get('source', '?')}")

    st.session_state["messages"].append({"role": "assistant", "content": full_response})