# src/embedder.py
import os
import torch
import numpy as np
from typing import List, Dict, Optional
from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import SentenceTransformer

class BGEEmbedder:
    """
    Unified embedder for BGE-M3 in 4 modes:
      - "dense": semantic vector only (1024-dim)
      - "sparse": lexical weights only (learned sparse)
      - "hybrid": both dense + sparse
      - "finetuned": custom dense encoder (French-domain adapted)
    
    P40 Optimizations:
      - use_fp16=True reduces VRAM by 50%
      - explicit cleanup() method for VRAM management between modes
    """
    
    def __init__(self, mode: str, cfg: dict):
        self.mode = mode
        self.device = cfg.get("device", "cuda")
        self.use_fp16 = cfg.get("use_fp16", True)
        
        if mode == "finetuned":
            ft_path = cfg.get("finetuned_path")
            if not ft_path or not os.path.exists(ft_path):
                raise ValueError(f"Finetuned model path not found: {ft_path}")
            self.dense_model = SentenceTransformer(ft_path, device=self.device)
            self.is_finetuned = True
            self._dim = self.dense_model.get_sentence_embedding_dimension() or 768
            self.base_model = None  # No sparse head for finetuned
        else:
            self.base_model = BGEM3FlagModel(
                cfg["base_name"], 
                use_fp16=self.use_fp16, 
                device=self.device
            )
            self.is_finetuned = False
            self._dim = 1024  # BGE-M3 dense output dimension

    @property
    def dim(self) -> int:
        return self._dim

    def encode_dense(self, texts: List[str]) -> np.ndarray:
        """Returns L2-normalized dense vectors for IP metric compatibility."""
        if self.is_finetuned:
            # SentenceTransformers can normalize directly
            return self.dense_model.encode(
                texts, 
                convert_to_numpy=True, 
                normalize_embeddings=True,
                batch_size=16,  # P40-friendly
                show_progress_bar=False
            )
        
        # BGE-M3: get raw vectors, then normalize
        raw = self.base_model.encode(texts, return_dense=True)["dense_vecs"]
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        # Avoid division by zero
        normalized = raw / np.where(norms == 0, 1, norms)
        return normalized

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Returns sparse vectors in Milvus format: {token_index: weight}.
        For finetuned mode, returns uniform fallback (replace with BM25 if needed).
        """
        if self.is_finetuned:
            # Fallback: uniform weights (or integrate bm25s here if needed)
            return [{i: 1.0 for i in range(min(100, len(t)//4))} for t in texts]
        
        result = self.base_model.encode(texts, return_sparse=True)
        return result["lexical_weights"]

    def cleanup(self):
        """Explicitly free VRAM on P40 between modes."""
        if self.base_model:
            del self.base_model
        if hasattr(self, "dense_model"):
            del self.dense_model
        torch.cuda.empty_cache()