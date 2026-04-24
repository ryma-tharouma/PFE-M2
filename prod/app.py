# app.py
import json
import os

import streamlit as st
import torch

from assistant import Assistant
from chunker import Chunker
from embedder import Embedder
from generator import Generator
from rag import RAG
from retriever import Retriever
from vector_store import VectorDB


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

VECTOR_SIZE   = 1024          # BGE-M3 output dimension
DEFAULT_PROMPT = """\
You are a technical assistant. Use the provided context to answer the user's question.

Context:
{context}

Conversation history:
{history}
"""


# ----------------------------------------------------------------------
# Indexing
# ----------------------------------------------------------------------

def index_sections(
    db: VectorDB,
    embedder: Embedder,
    sections: list,
    collection_name: str,
    max_tokens: int = 8000,
    overlap: int = 10,
) -> None:
    chunker = Chunker(max_tokens=max_tokens, overlap=overlap)
    chunks  = chunker.process_sections(sections)

    if not chunks:
        raise ValueError("No chunks produced — check section content.")

    texts      = [c["embed_text"] for c in chunks]
    embeddings = embedder.encode(texts)

    records = [
        {"id": c["id"], "dense": vec, "payload": c.copy()}
        for c, vec in zip(chunks, embeddings)
    ]
    db.upsert(name=collection_name, records=records)


# ----------------------------------------------------------------------
# Build assistant (cached so it survives Streamlit reruns)
# ----------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def build_assistant(
    app_id: str,
    sections_json: str,          # serialised so st.cache_resource can hash it
    embedder_cfg: str,           # serialised
    use_rerank: bool,
    force_reindex: bool,
    prompt_file: str = "prompt_1.txt",
    db_path: str = "./qdrant_data",
    max_turns: int = 1,
) -> Assistant:
    sections     = json.loads(sections_json)
    embedder_cfg = json.loads(embedder_cfg)

    # 1. Embedder
    embedder = Embedder(cfg=embedder_cfg)

    # 2. Vector DB
    db = VectorDB(path=db_path)
    collection_exists = db.collection_exists(app_id)

    # 3. Index if needed
    if collection_exists and not force_reindex:
        st.info(
            f"Collection '{app_id}' already exists. "
            "Enable 'Force re-index' in the sidebar to overwrite."
        )
    else:
        if collection_exists:
            db.drop_collection(app_id)
        db.create_collection(name=app_id, dim=VECTOR_SIZE)

        with st.spinner("Chunking and embedding sections…"):
            index_sections(db, embedder, sections, app_id)
        st.success("Indexing complete!")

    # 4. Retriever
    retriever = Retriever(
        db=db,
        embedder=embedder,
        search_top_k=5,
        rerank=use_rerank,
        rerank_top_k=5 if use_rerank else 0,
        sections_top_k=3,
    )

    # 5. Prompt file — create default if missing
    if not os.path.exists(prompt_file):
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROMPT)

    # 6. Generator — CPU or GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = Generator(
        prompt_file=prompt_file,
        device=device,
        gguf_path="models/Qwen3.5-4B-Q4_K_S.gguf",
        n_ctx=4000,
        n_threads=4,
        hf_model_name="Qwen/Qwen3.5-4B",
        torch_dtype="float16",
        generation_kwargs=(
            {"max_tokens": 512} if device == "cpu" else {"max_new_tokens": 512}
        ),
    )

    # 7. RAG + Assistant
    rag = RAG(retriever=retriever, generator=generator)
    return Assistant(rag=rag, max_turns=max_turns, verbose=True, log_dir="logs")


# ----------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------

st.set_page_config(page_title="RAG Chat", layout="wide")
st.title("📄 RAG Chat – Upload & Ask")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("1. Upload JSON")
    uploaded_file = st.file_uploader(
        "Select a JSON file (list of sections)", type=["json"]
    )

    if uploaded_file:
        raw_bytes = uploaded_file.read()
        try:
            sections = json.loads(raw_bytes)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
            st.stop()

        st.success(f"Loaded {len(sections)} sections")

        base_name  = os.path.splitext(uploaded_file.name)[0]
        app_id     = base_name.replace(" ", "_").replace("-", "_")
        max_turns  = st.slider("History turns", min_value=1, max_value=5, value=1)
        use_rerank = st.checkbox("Enable reranking (slower, more accurate)", value=False)
        force_reindex = st.checkbox("Force re-index (overwrite existing data)", value=False)

        if st.button("🚀 Index & Start Chat"):
            embedder_cfg = json.dumps({
                "model":    {"base_name": "BAAI/bge-m3", "device": "cpu"},
                "indexing": {"batch_size": 16},
            })

            try:
                assistant = build_assistant(
                    app_id        = app_id,
                    sections_json = json.dumps(sections),
                    embedder_cfg  = embedder_cfg,
                    use_rerank    = use_rerank,
                    force_reindex = force_reindex,
                    max_turns     = max_turns,
                )
                st.session_state["assistant"] = assistant
                st.session_state["app_id"]    = app_id
                # Reset chat history whenever a new file is indexed
                st.session_state["messages"]  = []
                st.success("Ready! Start chatting below.")
                st.balloons()
            except Exception as e:
                st.error(f"Failed to build assistant: {e}")

# ---------- Chat area ----------
if "assistant" not in st.session_state:
    st.info("👈 Upload a JSON file and click 'Index & Start Chat' to begin.")
    st.stop()

assistant : Assistant = st.session_state["assistant"]
app_id    : str       = st.session_state["app_id"]

st.header(f"💬 Chat with **{app_id}**")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Render previous messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# New user input
if prompt := st.chat_input("Ask about the manual…"):
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder   = st.empty()
        full_response = ""
        sources       = []

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