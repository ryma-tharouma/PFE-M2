# pipeline.py
from embedder import Embedder
from vector_store import VectorDB
from retriever import Retriever
from generator import Generator
from rag import RAG
from assistant import Assistant
from section_store import SectionStore
from indexer import Indexer
from support import SupportHandler


def build_pipeline(
    embedder_model: str,
    generator_model: str,
    prompt_file: str,
    db_path: str = None,
    db_host: str = None,
    db_port: int = 6333,
    db_api_key: str = None,
    apps_dir: str = "data/apps",
    collection_template: str = "{app_id}_dense_qdrant_flat",
    verbose: bool = False,
    log_dir: str = "logs",
):
    """
    Build and return the full pipeline.

    Returns:
        assistant       : Assistant instance for handling user queries
        support_handler : SupportHandler instance for resolving support tickets
    """
    # Embedder
    embedder = Embedder(model_name=embedder_model, device="cuda")

    # Vector DB — server if host provided, local file otherwise
    if db_host:
        db = VectorDB(host=db_host, port=db_port, api_key=db_api_key)
    else:
        db = VectorDB(path=db_path)

    # Retriever
    retriever = Retriever(
        db=db,
        embedder=embedder,
        search_top_k=50,
        rerank=True,
        rerank_top_k=20,
        sections_top_k=3,
    )

    # Generator
    generator = Generator(
        model_name=generator_model,
        prompt_file=prompt_file,
        torch_dtype="float16",
        device_map="auto",
        generation_kwargs={
            "max_new_tokens": 512,
            "do_sample": False,
            "repetition_penalty": 1.1,
        },
    )

    # Section store — single source of truth for section JSON files
    section_store = SectionStore(apps_dir=apps_dir)

    # Indexer — embeds and upserts new sections into Qdrant
    indexer = Indexer(db=db, embedder=embedder)

    # Support handler — ties section store + indexer together
    support_handler = SupportHandler(
        section_store=section_store,
        indexer=indexer,
        collection_template=collection_template,
    )

    # RAG pipeline
    rag = RAG(
        retriever=retriever,
        generator=generator,
        section_store=section_store,
    )

    # Assistant — manages sessions and delegates to RAG
    assistant = Assistant(
        rag=rag,
        max_turns=1,
        verbose=verbose,
        log_dir=log_dir,
    )

    return assistant, support_handler