from typing import List, Literal, Optional, Dict, Callable
import logging
import numpy as np
import torch
import time
import threading
import os

try:
    from vllm import LLM
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


# ==================== MODEL CONFIG ====================

HF_MODEL_MAP = {
    "bge": "BAAI/bge-m3",
    "qwen": "Qwen/Qwen3-Embedding-8B",
    "mistral": "intfloat/e5-mistral-7b-instruct",
}

OLLAMA_MODEL_MAP = {
    "bge": "bge-m3",
    "qwen": "dengcao/Qwen3-Embedding-8B:Q4_K_M",
    "mistral": "hellord/e5-mistral-7b-instruct:Q4_0",
}

EMBED_DIM_MAP = {
    "bge": 1024,
    "qwen": 4096,
    "mistral": 1024,
}

DEFAULT_QUERY_PREFIX: Dict[str, Callable[[str], str]] = {
    "bge": lambda t: t,
    "qwen": lambda t: f"Instruction: Étant donné une requête, retrouve les passages pertinents\nRequête:{t}",
    "mistral": lambda t: f"Instruction: Récupère les passages pertinents pour répondre à la question\nRequête:{t}",
}


# ==================== EMBEDDER ====================

class Embedder:
    """Thread-safe embedder with vLLM/Ollama backend support."""

    _instances: Dict[tuple, "Embedder"] = {}
    _lock = threading.Lock()

    def __new__(
        cls,
        model_name: str = "bge",
        backend: Literal["vllm", "ollama"] = "ollama",
        thread_local: bool = False
    ):
        key = (model_name, backend, thread_local)
        with cls._lock:
            if thread_local:
                key = (*key, threading.current_thread().ident)
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[key] = instance
            return cls._instances[key]

    def __init__(
        self,
        model_name: str = "bge",
        backend: Literal["vllm", "ollama"] = "ollama",
        embed_dim: Optional[int] = None,
        ollama_quant: Optional[str] = None,
        query_prefix: Optional[Callable[[str], str]] = None,
        verbose: bool = False,
        thread_local: bool = False
    ):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        if model_name not in HF_MODEL_MAP:
            raise ValueError(f"Available models: {list(HF_MODEL_MAP.keys())}")

        self.model_name = model_name
        self.backend = backend
        self.ollama_quant = ollama_quant
        self.verbose = verbose
        self._query_prefix = query_prefix or DEFAULT_QUERY_PREFIX.get(model_name, lambda t: t)

        self._setup_logger()
        self.model_id = self._get_ollama_name() if backend == "ollama" else HF_MODEL_MAP[model_name]
        self.embed_dim = embed_dim or EMBED_DIM_MAP[model_name]
        self._load_model()

        self.logger.info(
            f"Initialized | backend={self.backend} | model={self.model_id} | dim={self.embed_dim}"
        )

    # ==================== LOGGER ====================

    def _setup_logger(self):
        os.makedirs("logs/embedder", exist_ok=True)
        log_file = f"logs/embedder/{self.model_name}_{self.backend}.log"
        self.logger = logging.getLogger(f"embedder.{self.model_name}.{self.backend}")

        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)
            if self.verbose:
                ch = logging.StreamHandler()
                ch.setFormatter(formatter)
                self.logger.addHandler(ch)

    # ==================== LOAD ====================

    def _get_ollama_name(self) -> str:
        base = OLLAMA_MODEL_MAP[self.model_name]
        if self.ollama_quant:
            base_name = base.split(":")[0] if ":" in base else base
            return f"{base_name}:{self.ollama_quant}"
        return base

    def _load_model(self):
        if self.backend == "vllm" and VLLM_AVAILABLE:
            try:
                self.logger.info(f"Loading vLLM: {self.model_id}")
                start = time.time()
                self._model = LLM(
                    model=self.model_id,
                    task="embed",
                    enforce_eager=True,
                    max_model_len=4000,
                    gpu_memory_utilization=0.9
                )
                # Probe to detect actual dimension
                probe = self._model.embed(["test"])
                self.embed_dim = len(probe[0].outputs.embedding)
                self.logger.info(f"Loaded vLLM in {time.time() - start:.2f}s")
                return
            except Exception as e:
                self.logger.warning(f"vLLM load failed: {e} → fallback to Ollama")

        # Ollama backend (or fallback)
        if not OLLAMA_AVAILABLE:
            raise ImportError("Install ollama: pip install ollama")

        self.backend = "ollama"
        self.model_id = self._get_ollama_name()
        self.logger.info(f"Using Ollama: {self.model_id}")

        try:
            ollama.embed(model=self.model_id, input="test")
        except Exception as e:
            self.logger.error(f"Ollama probe failed: {e}")
            raise

        self._model = self.model_id

    # ==================== EMBEDDING ====================

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(arr, axis=1, keepdims=True)
        norm[norm == 0] = 1e-10
        return arr / norm

    def embed(
        self,
        texts: List[str],
        input_type: Literal["query", "document"] = "document",
        batch_size: int = 32
    ) -> List[List[float]]:
        if not texts:
            return []

        if input_type == "query":
            texts = [self._query_prefix(t) for t in texts]

        start_total = time.time()

        try:
            if self.backend == "vllm":
                outputs = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    outputs.extend(self._model.embed(batch))
                arr = np.vstack([np.array(o.outputs.embedding) for o in outputs])
            else:
                all_embeddings = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    response = ollama.embed(model=self._model, input=batch)
                    all_embeddings.extend(response["embeddings"])
                arr = np.array(all_embeddings)
        except Exception as e:
            self.logger.error(f"Embedding failed: {e}")
            raise

        arr = self._normalize(arr)
        self.logger.info(
            f"Embedded {len(texts)} texts in {time.time() - start_total:.2f}s"
        )
        return arr.tolist()

    # ==================== UTILS ====================

    def get_dimension(self) -> int:
        return self.embed_dim

    def close(self):
        """Release resources (GPU memory for vLLM)."""
        if self.backend == "vllm" and hasattr(self, "_model"):
            del self._model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        # Ollama is stateless HTTP → no cleanup needed

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @classmethod
    def clear_cache(cls):
        """Close and clear all cached instances."""
        with cls._lock:
            for inst in cls._instances.values():
                inst.close()
            cls._instances.clear()

