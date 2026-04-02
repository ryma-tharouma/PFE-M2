from typing import List, Literal, Optional, Dict, Callable
import logging
import numpy as np
import torch
import time
import threading
import os

# imports with availability flags
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

try:
    from llama_cpp import Llama
    LLAMACPP_AVAILABLE = True
except ImportError:
    LLAMACPP_AVAILABLE = False


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

LLAMACPP_MODEL_MAP = {
    "bge": "BAAI/bge-m3-gguf/bge-m3-Q4_K_M.gguf",
    "qwen": "Qwen/Qwen3-Embedding-8B-GGUF/qwen3-embedding-8b-q4_k_m.gguf",
    "mistral": "lmstudio-community/e5-mistral-7b-instruct-GGUF/e5-mistral-7b-instruct-q4_k_m.gguf",
}

EMBED_DIM_MAP = {
    "bge": 1024,
    "qwen": 4096,
    "mistral": 1024,
}

DEFAULT_QUERY_PREFIX: Dict[str, Callable[[str], str]] = {
    "bge": lambda t: t,
    "qwen": lambda t: f"Instruction: Given a query, retrieve relevant passages\nQuery: {t}",
    "mistral": lambda t: f"Instruction: Retrieve relevant passages to answer the question\nQuery: {t}",
}


# ==================== EMBEDDER ====================

class Embedder:
    """Thread-safe embedder supporting vLLM, Ollama, and llama.cpp backends."""

    _instances: Dict[tuple, "Embedder"] = {}
    _lock = threading.Lock()

    def __new__(
        cls,
        model_name: str = "bge",
        backend: Literal["vllm", "ollama", "llamacpp"] = "ollama",
        thread_local: bool = False,
        **kwargs
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
        backend: Literal["vllm", "ollama", "llamacpp"] = "ollama",
        embed_dim: Optional[int] = None,
        ollama_quant: Optional[str] = None,
        llamacpp_kwargs: Optional[Dict] = None,
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
        self._requested_backend = backend  # Store original request for logging
        self.backend = backend
        self.embed_dim = embed_dim or EMBED_DIM_MAP[model_name]
        self.ollama_quant = ollama_quant
        self.llamacpp_kwargs = llamacpp_kwargs or {}
        self.verbose = verbose
        self._query_prefix = query_prefix or DEFAULT_QUERY_PREFIX.get(model_name, lambda t: t)

        self._setup_logger()  # Logger uses _requested_backend
        self._load_model()    # May change self.backend on fallback

        self.logger.info(
            f"Initialized | requested={self._requested_backend} | active={self.backend} | model={self.model_id} | dim={self.embed_dim}"
        )

    # ==================== LOGGER ====================

    def _setup_logger(self):
        os.makedirs("logs/embedder", exist_ok=True)
        
        # Timestamp for unique log files per run
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # Use REQUESTED backend in filename (not the fallback)
        log_file = f"logs/embedder/{self.model_name}_{self._requested_backend}_{timestamp}.log"
        
        # Unique logger name includes timestamp to avoid handler conflicts
        logger_name = f"embedder.{self.model_name}.{self._requested_backend}.{timestamp}"
        self.logger = logging.getLogger(logger_name)
        
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            
            fh = logging.FileHandler(log_file, encoding="utf-8")
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
        # Try vLLM first if requested
        if self.backend == "vllm" and VLLM_AVAILABLE and torch.cuda.is_available():
            try:
                self.model_id = HF_MODEL_MAP[self.model_name]
                self.logger.info(f"Loading vLLM: {self.model_id}")
                start = time.time()
                self._model = LLM(
                    model=self.model_id,
                    task="embed",
                    enforce_eager=True,
                    max_model_len=4000,
                )
                probe = self._model.embed(["test"])
                self.embed_dim = len(probe[0].outputs.embedding)
                self.logger.info(f"Loaded vLLM in {time.time() - start:.2f}s")
                return
            except Exception as e:
                self.logger.warning(f"vLLM failed: {e} → fallback")

        # Try llama.cpp if requested
        if self.backend == "llamacpp" and LLAMACPP_AVAILABLE:
            try:
                self.model_id = LLAMACPP_MODEL_MAP[self.model_name]
                self.logger.info(f"Loading llama.cpp: {self.model_id}")
                start = time.time()
                
                default_kwargs = {
                    "n_ctx": 4096,
                    "n_gpu_layers": -1 if torch.cuda.is_available() else 0,
                    "verbose": False,
                    "embedding": True,
                }
                default_kwargs.update(self.llamacpp_kwargs)
                
                self._model = Llama(model_path=self.model_id, **default_kwargs)
                
                # Probe to detect dimension if not set
                if not self.embed_dim:
                    probe = self._model.embed("test")
                    self.embed_dim = len(probe)
                
                self.logger.info(f"Loaded llama.cpp in {time.time() - start:.2f}s")
                return
            except Exception as e:
                self.logger.warning(f"llama.cpp failed: {e} → fallback")

        # Fallback to Ollama (always available as last resort)
        if not OLLAMA_AVAILABLE:
            raise ImportError("Install at least one backend: ollama, vllm, or llama-cpp-python")

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

            elif self.backend == "llamacpp":
                all_embeddings = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    for text in batch:
                        emb = self._model.embed(text)
                        all_embeddings.append(emb)
                arr = np.array(all_embeddings)

            else:  # ollama
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
        elapsed = time.time() - start_total
        self.logger.info(
            f"Embedded {len(texts)} texts in {elapsed:.2f}s | backend={self.backend}"
        )
        return arr.tolist()

    # ==================== UTILS ====================

    def get_dimension(self) -> int:
        return self.embed_dim

    def close(self):
        """Release backend-specific resources."""
        if not hasattr(self, "_model"):
            return
        if self.backend == "vllm":
            del self._model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        elif self.backend == "llamacpp":
            if hasattr(self._model, "close"):
                self._model.close()
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
            for inst in list(cls._instances.values()):
                inst.close()
            cls._instances.clear()


# ==================== TEST ====================
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)

    print("🚀 Embedder test | backend=llamacpp (fallback to ollama)\n")

    embedder = None
    try:
        embedder = Embedder(model_name="bge", backend="llamacpp", verbose=True)

        query = "Comment créer un utilisateur ?"
        query_emb = embedder.embed([query], input_type="query")[0]

        documents = [
            "Pour créer un utilisateur, allez dans paramètres puis cliquez sur ajouter.",
            "Suppression d'un utilisateur dans le système.",
            "Création du réseau interne",
            "Ajouter un nouvel utilisateur dans la base de données"
        ]
        doc_embs = embedder.embed(documents, input_type="document")

        print("\n📊 Similarities:\n")
        for i, doc in enumerate(documents):
            score = np.dot(query_emb, doc_embs[i])
            print(f"{i+1}. {score:.4f} | {doc}")

    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if embedder:
            embedder.close()
        print("\n✅ Done!")