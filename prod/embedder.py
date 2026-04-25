# embedder.py
import os
import numpy as np
from typing import List, Dict, Any


class Embedder:
    """
    Sentence-Transformer embedder with L2 normalisation.
    Model is cached at the class level to avoid reloading across instances.
    """

    _model_cache: dict = {}

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: dictionary containing an "embedder" section with keys:
                - model_name (str, default "BAAI/bge-m3")
                - device (str, default "cpu")
                - batch_size (int, default 32)
        """
        embedder_cfg = config.get("embedder", {})
        self.model_name = embedder_cfg.get("model_name", "BAAI/bge-m3")
        self.device = embedder_cfg.get("device", "cpu")
        self.batch_size = embedder_cfg.get("batch_size", 32)

        cache_key = (self.model_name, self.device)
        if cache_key not in Embedder._model_cache:
            from sentence_transformers import SentenceTransformer
            Embedder._model_cache[cache_key] = SentenceTransformer(
                self.model_name, device=self.device
            )
        self.model = Embedder._model_cache[cache_key]

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------

    def encode(self, texts: List[str]) -> np.ndarray:
        """
        Encode a list of texts into L2-normalised dense vectors.

        Returns:
            np.ndarray of shape (len(texts), dim)
        """
        vecs = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return self._l2_normalize(np.array(vecs))

    def encode_one(self, text: str) -> np.ndarray:
        """
        Encode a single string. Returns a 1-D vector of shape (dim,).
        """
        return self.encode([text])[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _l2_normalize(vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def cleanup(self):
        """Free GPU memory if running on CUDA."""
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except ImportError:
                pass

    @classmethod
    def clear_cache(cls):
        """Evict all cached models (useful in tests)."""
        cls._model_cache.clear()