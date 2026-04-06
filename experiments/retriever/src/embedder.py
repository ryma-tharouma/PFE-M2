# src/embedder.py
import os
import torch
import numpy as np
from typing import List, Dict, Any
from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import SentenceTransformer

class BGEEmbedder:
    """
    Unified wrapper for BGE-M3 embedding modes.
    Supports: dense, sparse, hybrid, finetuned_dense, finetuned_hybrid
    Optimized for CPU evaluation (configurable for GPU).
    """
    
    def __init__(self, mode: str, cfg: dict):
        self.mode = mode
        self.device = cfg.get("device", "cpu")
        # Disable FP16 on CPU to avoid warnings/overhead
        self.use_fp16 = cfg.get("use_fp16", False) and self.device == "cuda"
        
        self.is_finetuned = mode.startswith("finetuned_")
        ft_type = mode.split("_")[1] if self.is_finetuned else None
        
        # Initialize base BGE-M3 for sparse (and dense if not finetuned)
        if not self.is_finetuned:
            self.base_model = BGEM3FlagModel(
                cfg["model"]["base_name"],
                use_fp16=self.use_fp16,
                device=self.device
            )
            self.ft_model = None
        else:
            # Load fine-tuned model for dense embeddings
            ft_paths = cfg["model"].get("finetuned_paths", {})
            ft_path = ft_paths.get(ft_type)
            if not ft_path or not os.path.exists(ft_path):
                raise FileNotFoundError(f"Finetuned model for '{ft_type}' not found at: {ft_path}")
                
            self.ft_model = SentenceTransformer(ft_path, device=self.device)
            
            # For finetuned_hybrid, keep base model for sparse lexical weights
            if ft_type == "hybrid":
                self.base_model = BGEM3FlagModel(cfg["model"]["base_name"], use_fp16=self.use_fp16, device=self.device)
            else:
                self.base_model = None

    def encode_dense(self, texts: List[str]) -> np.ndarray:
        """Returns L2-normalized dense vectors (1024-dim for BGE-M3)."""
        if self.is_finetuned:
            raw = self.ft_model.encode(texts, convert_to_numpy=True, normalize_embeddings=False, batch_size=32)
        else:
            raw = self.base_model.encode(texts, return_dense=True)["dense_vecs"]
            
        # Explicit L2 normalization for Cosine/IP compatibility
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        return raw / np.where(norms == 0, 1, norms)

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        """Returns BGE-M3 learned lexical weights: {token_id: weight} with INTEGER keys."""
        if self.base_model is None:
            return [{} for _ in texts]
            
        result = self.base_model.encode(texts, return_sparse=True)
        # Convert string keys to integers for Qdrant compatibility
        return [{int(k): float(v) for k, v in sparse.items()} for sparse in result["lexical_weights"]]

    def encode_batch(self, texts: List[str]) -> Dict[str, Any]:
        """
        Returns dict with requested vector types based on mode.
        Keys: "dense" (np.ndarray), "sparse" (List[Dict])
        """
        out = {}
        
        needs_dense = self.mode in ["dense", "hybrid", "finetuned_dense", "finetuned_hybrid"]
        needs_sparse = self.mode in ["sparse", "hybrid", "finetuned_hybrid"]
        
        if needs_dense:
            out["dense"] = self.encode_dense(texts)
        if needs_sparse:
            out["sparse"] = self.encode_sparse(texts)
            
        return out

    def cleanup(self):
        """Frees VRAM if running on GPU. Safe to call on CPU (no-op)."""
        if self.device == "cuda":
            torch.cuda.empty_cache()