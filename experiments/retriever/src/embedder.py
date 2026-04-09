# src/embedder.py
import os
import torch
import numpy as np
from typing import List, Dict, Any

class BGEEmbedder:
    """
    Unified wrapper for BGE-M3 (base or finetuned).
    Supports: dense, sparse, hybrid, finetuned_dense, finetuned_sparse, finetuned_hybrid
    All finetuned modes share the same checkpoint but compute different output branches.
    """
    def __init__(self, mode: str, cfg: dict):
        self.mode = mode
        model_cfg = cfg.get("model", {})
        self.device = model_cfg.get("device", "cpu")
        self.use_fp16 = model_cfg.get("use_fp16", False) and self.device == "cuda"
        self.batch_size = model_cfg.get("batch_size", 32)
        
        is_finetuned = mode.startswith("finetuned_")
        
        if is_finetuned:
            ft_paths = model_cfg.get("finetuned_paths", {})
            ft_type = mode.replace("finetuned_", "")
            # Try mode-specific path first, fallback to generic finetuned_path
            model_path = ft_paths.get(ft_type) or model_cfg.get("finetuned_path")
            if not model_path or not os.path.exists(model_path):
                raise FileNotFoundError(f"Finetuned model not found for '{mode}' at: {model_path}")
        else:
            model_path = model_cfg.get("base_name", "BAAI/bge-m3")
            
        from FlagEmbedding import BGEM3FlagModel
        self.model = BGEM3FlagModel(model_path, use_fp16=self.use_fp16, device=self.device)
        
        # Route outputs based on mode
        self.needs_dense = mode in ["dense", "hybrid", "finetuned_dense", "finetuned_hybrid"]
        self.needs_sparse = mode in ["sparse", "hybrid", "finetuned_sparse", "finetuned_hybrid"]

    def _process_sparse(self, sparse_dicts):
        """Convert string keys to integers for Qdrant compatibility."""
        return [{int(k): float(v) for k, v in d.items()} for d in sparse_dicts]

    def encode_dense(self, texts: List[str]) -> np.ndarray:
        if not self.needs_dense:
            return np.empty((len(texts), 0))
        raw = self.model.encode(texts, return_dense=True)["dense_vecs"]
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        return raw / np.where(norms == 0, 1, norms)

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        if not self.needs_sparse:
            return [{} for _ in texts]
        res = self.model.encode(texts, return_sparse=True)
        return self._process_sparse(res["lexical_weights"])

    def encode_batch(self, texts: List[str]) -> Dict[str, Any]:
        out = {}
        # Optimized: single forward pass when both branches are needed
        if self.needs_dense and self.needs_sparse:
            res = self.model.encode(texts, return_dense=True, return_sparse=True, batch_size=self.batch_size)
            out["dense"] = res["dense_vecs"]
            out["sparse"] = self._process_sparse(res["lexical_weights"])
        else:
            if self.needs_dense: out["dense"] = self.encode_dense(texts)
            if self.needs_sparse: out["sparse"] = self.encode_sparse(texts)
            
        # Ensure L2 normalization for dense
        if "dense" in out:
            norms = np.linalg.norm(out["dense"], axis=1, keepdims=True)
            out["dense"] = out["dense"] / np.where(norms == 0, 1, norms)
            
        return out

    def cleanup(self):
        if self.device == "cuda":
            torch.cuda.empty_cache()