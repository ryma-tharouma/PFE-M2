# src/embedder.py
import os
import re
import json
import numpy as np
from typing import List, Dict, Any, Optional

def _simple_tokenize(text: str) -> List[str]:
    """Lowercase and split on whitespace / newlines."""
    return re.split(r"[\s\n]+", text.lower().strip())


class BM25TermFrequency:
    """
    Converts text to {token_id: term_frequency} for Qdrant sparse vectors.
    Qdrant will apply IDF and BM25 scoring server-side when modifier=IDF is set.
    Vocabulary can be saved and loaded to disk.
    """
    def __init__(self):
        self.vocab: Dict[str, int] = {}

    def fit(self, corpus: List[str]) -> "BM25TermFrequency":
        """Build token -> id mapping from corpus."""
        for doc in corpus:
            for tok in _simple_tokenize(doc):
                if tok not in self.vocab:
                    self.vocab[tok] = len(self.vocab)
        return self

    def get_sparse_vector(self, text: str) -> Dict[int, float]:
        """Return {token_id: term_frequency}."""
        tokens = _simple_tokenize(text)
        freq: Dict[str, int] = {}
        for tok in tokens:
            freq[tok] = freq.get(tok, 0) + 1
        return {self.vocab[tok]: float(count) for tok, count in freq.items() if tok in self.vocab}

    def save_vocab(self, path: str):
        """Save vocabulary to JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)

    def load_vocab(self, path: str):
        """Load vocabulary from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            self.vocab = json.load(f)


class BGEEmbedder:
    """
    Unified wrapper for BGE dense (via sentence-transformers) + BM25 sparse (raw term frequencies).

    Supported modes
    ---------------
    dense            — base BGE, dense only
    sparse           — BM25 sparse only (raw term frequencies)
    hybrid           — base BGE dense + BM25 sparse
    finetuned_dense  — finetuned BGE dense only
    finetuned_hybrid — finetuned BGE dense + BM25 sparse

    For sparse: either call fit_bm25(corpus) or load_bm25_vocab(path) before encoding.
    """

    def __init__(self, mode: str, cfg: dict):
        self.mode = mode
        model_cfg = cfg.get("model", {})
        indexing_cfg = cfg.get("indexing", {})
        self.device = model_cfg.get("device", "cpu")
        self.batch_size = indexing_cfg.get("batch_size", 16)

        self.needs_dense = mode in {
            "dense", "hybrid", "finetuned_dense", "finetuned_hybrid"
        }
        self.needs_sparse = mode in {"sparse", "hybrid", "finetuned_hybrid"}

        # Dense encoder
        if self.needs_dense:
            from sentence_transformers import SentenceTransformer
            is_finetuned = mode.startswith("finetuned_")
            if is_finetuned:
                model_path = model_cfg.get("finetuned_path")
                if not model_path or not os.path.exists(model_path):
                    raise FileNotFoundError(f"Finetuned model not found for '{mode}' at: {model_path}")
            else:
                model_path = model_cfg.get("base_name", "BAAI/bge-m3")
            self.st_model = SentenceTransformer(model_path, device=self.device)
        else:
            self.st_model = None

        # Sparse encoder
        self.bm25: Optional[BM25TermFrequency] = BM25TermFrequency() if self.needs_sparse else None

    # BM25 corpus fitting and loading
    def fit_bm25(self, corpus: List[str]) -> "BGEEmbedder":
        if self.bm25 is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        self.bm25.fit(corpus)
        return self

    def save_bm25_vocab(self, path: str):
        if self.bm25 is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        self.bm25.save_vocab(path)

    def load_bm25_vocab(self, path: str):
        if self.bm25 is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        self.bm25.load_vocab(path)

    # Dense helpers
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

    def encode_sparse(self, texts: List[str]) -> List[Dict[int, float]]:
        if not self.needs_sparse or self.bm25 is None:
            return [{} for _ in texts]
        return [self.bm25.get_sparse_vector(t) for t in texts]

    def encode_batch(self, texts: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.needs_dense:
            out["dense"] = self.encode_dense(texts)
        if self.needs_sparse:
            out["sparse"] = self.encode_sparse(texts)
        return out

    def cleanup(self):
        if self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except ImportError:
                pass
        if self.st_model is not None:
            del self.st_model