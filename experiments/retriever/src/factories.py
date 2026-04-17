# src/factories.py
from typing import Dict, Any
from .embedder import BGEEmbedder
from .vector_db import BaseVectorDB, get_vector_db
from .chunker import AdaptiveChunker
from .aggregator import ChunkAggregator
from .context_manager import ContextManager
from .reranker import BGEReranker   # new import

def get_embedder(mode: str, cfg: Dict[str, Any]) -> BGEEmbedder:
    VALID_MODES = {"dense", "sparse", "hybrid", "finetuned_dense", "finetuned_hybrid"}
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown embedder mode: {mode}. Valid: {VALID_MODES}")
    return BGEEmbedder(mode=mode, cfg=cfg)

def get_vector_database(cfg: Dict[str, Any]) -> BaseVectorDB:
    return get_vector_db(cfg)

def get_chunker(cfg: Dict[str, Any]) -> AdaptiveChunker:
    return AdaptiveChunker(cfg=cfg)

def get_aggregator(cfg: Dict[str, Any]) -> ChunkAggregator:
    return ChunkAggregator(cfg=cfg)

def get_context_manager(cfg: Dict[str, Any]) -> ContextManager:
    return ContextManager(cfg=cfg)

def get_reranker(cfg: Dict[str, Any]):
    """Return reranker instance if enabled, else None."""
    if cfg.get("reranker", {}).get("enabled", False):
        return BGEReranker(cfg)
    return None