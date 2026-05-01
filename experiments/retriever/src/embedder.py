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


def _is_qwen_embedding(model_path: str) -> bool:
    name = model_path.lower()
    return "qwen" in name and ("embed" in name or "embedding" in name)


class QwenEmbedder:
    """
    Handles Qwen embedding models (e.g. Qwen/Qwen3-Embedding-*).
    Uses AutoModel + last token pooling as required by Qwen embedding models.
    """

    def __init__(self, model_path: str, device: str, batch_size: int):
        import torch
        from transformers import AutoTokenizer, AutoModel

        self.device     = device
        self.batch_size = batch_size
        self.torch      = torch

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, padding_side="left")
        self.model     = AutoModel.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if device != "cpu" else torch.float32,
        ).to(device)
        self.model.eval()

        # Task instruction prefix used by Qwen embedding models
        self.query_instruction = "Instruct: Given a user query, retrieve relevant documents\nQuery: "
        self.doc_instruction   = ""  # documents are encoded without instruction

    def _last_token_pool(self, last_hidden_states, attention_mask):
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size       = last_hidden_states.shape[0]
            return last_hidden_states[
                self.torch.arange(batch_size, device=last_hidden_states.device),
                sequence_lengths
            ]

    def _encode(self, texts: List[str], instruction: str) -> np.ndarray:
        import torch
        prefixed  = [instruction + t for t in texts]
        all_vecs  = []

        with torch.no_grad():
            for i in range(0, len(prefixed), self.batch_size):
                batch  = prefixed[i : i + self.batch_size]
                inputs = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=8192,
                    return_tensors="pt",
                ).to(self.device)

                outputs = self.model(**inputs)
                vecs    = self._last_token_pool(outputs.last_hidden_state, inputs["attention_mask"])

                # L2 normalize
                norms = vecs.norm(dim=1, keepdim=True)
                vecs  = vecs / norms.clamp(min=1e-8)
                all_vecs.append(vecs.cpu().float().numpy())

        return np.vstack(all_vecs)

    def encode_queries(self, texts: List[str]) -> np.ndarray:
        return self._encode(texts, self.query_instruction)

    def encode_documents(self, texts: List[str]) -> np.ndarray:
        return self._encode(texts, self.doc_instruction)

    def cleanup(self):
        import torch
        del self.model
        if self.device != "cpu":
            torch.cuda.empty_cache()


class BGEEmbedder:
    _model_cache  = {}
    _qwen_cache   = {}

    @classmethod
    def clear_cache(cls):
        cls._model_cache.clear()
        cls._qwen_cache.clear()

    def __init__(self, mode: str, cfg: dict):
        self.mode        = mode
        model_cfg        = cfg.get("model", {})
        indexing_cfg     = cfg.get("indexing", {})
        self.device      = model_cfg.get("device", "cpu")
        self.batch_size  = indexing_cfg.get("batch_size", 32)

        self.needs_dense  = mode in {"dense", "hybrid", "finetuned_dense", "finetuned_hybrid"}
        self.needs_sparse = mode in {"sparse", "hybrid", "finetuned_hybrid"}

        self.qwen_embedder = None
        self.st_model      = None

        if self.needs_dense:
            is_finetuned = mode.startswith("finetuned_")
            if is_finetuned:
                model_path = model_cfg.get("finetuned_path")
                if not model_path or not os.path.exists(model_path):
                    raise FileNotFoundError(f"Finetuned model not found: {model_path}")
            else:
                model_path = model_cfg.get("base_name", "BAAI/bge-m3")

            if _is_qwen_embedding(model_path):
                # Qwen embedding path
                cache_key = (model_path, self.device)
                if cache_key not in BGEEmbedder._qwen_cache:
                    BGEEmbedder._qwen_cache[cache_key] = QwenEmbedder(
                        model_path, self.device, self.batch_size
                    )
                self.qwen_embedder = BGEEmbedder._qwen_cache[cache_key]
            else:
                # Standard SentenceTransformer path (BGE, CamemBERT, etc.)
                from sentence_transformers import SentenceTransformer
                cache_key = (model_path, self.device)
                if cache_key not in BGEEmbedder._model_cache:
                    BGEEmbedder._model_cache[cache_key] = SentenceTransformer(
                        model_path, device=self.device, trust_remote_code=True
                    )
                self.st_model = BGEEmbedder._model_cache[cache_key]

        self._bm25_registry: Dict[str, BM25TermFrequency] = {} if self.needs_sparse else None

    # ------------------------------------------------------------------
    # BM25 per-app handling
    # ------------------------------------------------------------------

    def _get_bm25(self, app: str) -> BM25TermFrequency:
        if self._bm25_registry is None:
            raise RuntimeError(f"Mode '{self.mode}' does not use BM25.")
        if app not in self._bm25_registry:
            self._bm25_registry[app] = BM25TermFrequency()
        return self._bm25_registry[app]

    def fit_bm25(self, app: str, corpus: List[str]) -> "BGEEmbedder":
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
        if self._bm25_registry and app in self._bm25_registry:
            del self._bm25_registry[app]

    # ------------------------------------------------------------------
    # Dense encoding — dispatches to Qwen or SentenceTransformer
    # ------------------------------------------------------------------

    def _l2_normalize(self, vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def encode_dense(self, texts: List[str], is_query: bool = True) -> np.ndarray:
        """
        is_query=True  → use query instruction (for retrieval queries)
        is_query=False → use document instruction (for indexing)
        """
        if not self.needs_dense:
            return np.empty((len(texts), 0))

        if self.qwen_embedder is not None:
            if is_query:
                return self.qwen_embedder.encode_queries(texts)
            else:
                return self.qwen_embedder.encode_documents(texts)

        # SentenceTransformer path
        vecs = self.st_model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return self._l2_normalize(np.array(vecs))

    # ------------------------------------------------------------------
    # Sparse encoding
    # ------------------------------------------------------------------

    def encode_sparse(self, texts: List[str], app: str) -> List[Dict[int, float]]:
        if not self.needs_sparse:
            return [{} for _ in texts]
        bm25 = self._get_bm25(app)
        return [bm25.get_sparse_vector(t) for t in texts]

    # ------------------------------------------------------------------
    # Batch encoding
    # ------------------------------------------------------------------

    def encode_batch(self, texts: List[str], app: str, is_query: bool = False) -> Dict[str, Any]:
        """is_query=False for indexing (documents), True for retrieval queries."""
        out = {}
        if self.needs_dense:
            out["dense"] = self.encode_dense(texts, is_query=is_query)
        if self.needs_sparse:
            out["sparse"] = self.encode_sparse(texts, app)
        return out

    def cleanup(self):
        if self.qwen_embedder is not None:
            self.qwen_embedder.cleanup()
        elif self.device == "cuda":
            try:
                import torch
                torch.cuda.empty_cache()
            except ImportError:
                pass