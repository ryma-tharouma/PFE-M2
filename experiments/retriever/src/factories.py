# src/factories.py
from typing import Dict, Any
from .embedder import BGEEmbedder
from .vector_db import BaseVectorDB, get_vector_db
from .chunker import AdaptiveChunker
from .aggregator import ChunkAggregator
from .context_manager import ContextManager

def get_embedder(mode: str, cfg: Dict[str, Any]) -> BGEEmbedder:
    """Initializes the BGE-M3 embedder for a specific mode (dense/sparse/hybrid/finetuned_*)."""
    return BGEEmbedder(mode=mode, cfg=cfg)

def get_vector_database(cfg: Dict[str, Any]) -> BaseVectorDB:
    """Instantiates the configured vector DB (Qdrant or Milvus) with connection params."""
    return get_vector_db(cfg)

def get_chunker(cfg: Dict[str, Any]) -> AdaptiveChunker:
    """Creates the adaptive text chunker respecting 8192-token limits and parent mapping."""
    return AdaptiveChunker(cfg=cfg)

def get_aggregator(cfg: Dict[str, Any]) -> ChunkAggregator:
    """Creates the chunk-to-section score aggregator (max/mean/rrf)."""
    return ChunkAggregator(cfg=cfg)

def get_context_manager(cfg: Dict[str, Any]) -> ContextManager:
    """Creates the multi-turn history manager with smart 8000-token truncation."""
    return ContextManager(cfg=cfg)