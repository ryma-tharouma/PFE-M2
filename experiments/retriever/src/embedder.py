# src/embedder.py
import os
import json
import re
import numpy as np
from typing import List, Dict, Any, Optional

def _simple_tokenize(text: str) -> List[str]:
    return re.split(r"[\s\n]+", text.lower().strip())


class BM25TermFrequency:
    def __init__(self):
        self.vocab: Dict[str, int] = {}

    def fit(self, corpus: List[str]) -> "BM25TermFrequency":
        for doc in corpus:
            for tok in _simple_tokenize(doc):
                if tok not in self.vocab:
                    self.vocab[tok] = len(self.vocab)
        return self

    def get_sparse_vector(self, text: str) -> Dict[int, float]:
        tokens = _simple_tokenize(text)
        freq: Dict[str, int] = {}
        for tok in tokens:
            freq[tok] = freq.get(tok, 0) + 1
        return {self.vocab[tok]: float(count) for tok, count in freq.items() if tok in self.vocab}

    def save_vocab(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)

    def load_vocab(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            self.vocab = json.load(f)


class BGEEmbedder:
    _model_cache = {}

    @classmethod
    def clear_cache(cls):
        cls._model_cache.clear()

    def __init__(self, mode: str, cfg: dict):
        self.mode = mode
        model_cfg = cfg.get("model", {})
        indexing_cfg = cfg.get("indexing", {})
        self.device = model_cfg.get("device", "cpu")
        self.batch_size = indexing_cfg.get("batch_size", 16)

        self.needs_dense = mode in {"dense", "hybrid", "finetuned_dense", "finetuned_hybrid"}
        self.needs_sparse = mode in {"sparse", "hybrid", "finetuned_hybrid"}

        if self.needs_dense:
            from sentence_transformers import SentenceTransformer
            is_finetuned = mode.startswith("finetuned_")
            if is_finetuned:
                model_path = model_cfg.get("finetuned_path")
                if not model_path or not os.path.exists(model_path):
                    raise FileNotFoundError(f"Finetuned model not found: {model_path}")
            else:
                model_path = model_cfg.get("base_name", "BAAI/bge-m3")
            cache_key = (model_path, self.device)
            if cache_key not in BGEEmbedder._model_cache:
                BGEEmbedder._model_cache[cache_key] = SentenceTransformer(model_path, device=self.device, trust_remote_code=True)
            self.st_model = BGEEmbedder._model_cache[cache_key]
        else:
            self.st_model = None

        # ----  a registry of BM25 instances, one per app ----
        self._bm25_registry: Dict[str, BM25TermFrequency] = {} if self.needs_sparse else None

    # ------------------------------------------------------------------
    # BM25 per-app handling
    # ------------------------------------------------------------------
    def _get_bm25(self, app: str) -> BM25TermFrequency:
        """Return the BM25 instance for `app`, creating one if absent."""
        if self._bm25_registry is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        if app not in self._bm25_registry:
            self._bm25_registry[app] = BM25TermFrequency()
        return self._bm25_registry[app]

    def fit_bm25(self, app: str, corpus: List[str]) -> "BGEEmbedder":
        """Fit BM25 for a specific app on its corpus."""
        self._get_bm25(app).fit(corpus)
        return self

    def save_bm25_vocab(self, app: str, path: str):
        self._get_bm25(app).save_vocab(path)

    def load_bm25_vocab(self, app: str, path: str):
        bm25 = BM25TermFrequency()
        bm25.load_vocab(path)
        if self._bm25_registry is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        self._bm25_registry[app] = bm25

    def drop_bm25(self, app: str):
        """Remove the BM25 vocab for a deleted app."""
        if self._bm25_registry and app in self._bm25_registry:
            del self._bm25_registry[app]

    # ------------------------------------------------------------------
    # Dense encoding (unchanged)
    # ------------------------------------------------------------------
    def _l2_normalize(self, vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def encode_dense(self, texts: List[str]) -> np.ndarray:
        if not self.needs_dense or self.st_model is None:
            return np.empty((len(texts), 0))
        vecs = self.st_model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return self._l2_normalize(np.array(vecs))

    # ------------------------------------------------------------------
    # Sparse encoding — now requires app name
    # ------------------------------------------------------------------
    def encode_sparse(self, texts: List[str], app: str) -> List[Dict[int, float]]:
        if not self.needs_sparse:
            return [{} for _ in texts]
        bm25 = self._get_bm25(app)
        return [bm25.get_sparse_vector(t) for t in texts]

    # ------------------------------------------------------------------
    # Batch encoding — now requires app name
    # ------------------------------------------------------------------
    def encode_batch(self, texts: List[str], app: str) -> Dict[str, Any]:
        out = {}
        if self.needs_dense:
            out["dense"] = self.encode_dense(texts)
        if self.needs_sparse:
            out["sparse"] = self.encode_sparse(texts, app)
        return out

    def cleanup(self):
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except ImportError:
                pass