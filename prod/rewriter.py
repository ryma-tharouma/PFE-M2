# rewriter.py
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


REWRITE_SYSTEM_PROMPT = (
    """
Résous les pronoms et ellipses de la question actuelle en utilisant la question précédente.
Si la question est déjà claire, retourne-la mot pour mot.
Retourne uniquement la question, sans explication.

Exemples :
"Comment créer un utilisateur ?" / "Comment lui modifier ses infos ?" → "Comment modifier les informations d'un utilisateur ?"
"Comment supprimer un utilisateur ?" / "Est-ce que c'est définitif ?" → "Est-ce que la suppression d'un utilisateur est définitive ?"
"Comment assigner un rôle ?" / "et pour le retirer ?" → "Comment retirer un rôle ?"
"Comment créer un utilisateur ?" / "Comment supprimer un utilisateur ?" → "Comment supprimer un utilisateur ?"
"""
)


class Rewriter:
    """
    Standalone query-rewriting model.

    Supports CPU inference via llama-cpp or GPU inference via HuggingFace
    Transformers. The model is loaded lazily on the first rewrite() call.

    Config section: "rewriter"
        device         (str)   – "cpu" or "cuda"                   (default "cpu")
        max_new_tokens (int)   – tokens to generate                 (default 128)
        temperature    (float) – sampling temperature               (default 0.1)

        # CPU (llama-cpp)
        gguf_path      (str)   – path to GGUF file                  (required for cpu)
        n_ctx          (int)   – context window                     (default 2048)
        n_threads      (int)   – CPU threads                        (default 4)
        n_batch        (int)   – batch size                         (default 512)

        # GPU (HuggingFace)
        hf_model_name  (str)   – HuggingFace model id               (required for cuda)
        torch_dtype    (str)   – "float16" / "bfloat16" / "float32" (default "float16")
    """

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("rewriter", {})

        self.device         = cfg.get("device", "cpu")
        self.max_new_tokens = int(cfg.get("max_new_tokens", 128))
        self.temperature    = float(cfg.get("temperature", 0.1))

        # CPU
        self.gguf_path = cfg.get("gguf_path", "")
        self.n_ctx     = int(cfg.get("n_ctx", 2048))
        self.n_threads = int(cfg.get("n_threads", 4))
        self.n_batch   = int(cfg.get("n_batch", 512))

        # GPU
        self.hf_model_name = cfg.get("hf_model_name", "")
        self.torch_dtype   = cfg.get("torch_dtype", "float16")

        self._llm:       Any = None
        self._hf_model:  Any = None
        self._tokenizer: Any = None

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def _load_cpu(self) -> None:
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is required for the CPU rewriter."
            ) from exc
        if not self.gguf_path:
            raise ValueError(
                "rewriter.gguf_path must be set in config.yaml when rewriter.device=cpu."
            )
        logger.info("Loading CPU rewriter from %s …", self.gguf_path)
        self._llm = Llama(
            model_path=self.gguf_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_batch=self.n_batch,
            verbose=False,
        )
        logger.info("CPU rewriter loaded.")

    def _load_gpu(self) -> None:
        if self._hf_model is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except ImportError as exc:
            raise RuntimeError(
                "torch and transformers are required for the GPU rewriter."
            ) from exc
        if not self.hf_model_name:
            raise ValueError(
                "rewriter.hf_model_name must be set in config.yaml when rewriter.device=cuda."
            )
        import torch
        dtype_map = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
            "float32":  torch.float32,
        }
        dtype = dtype_map.get(self.torch_dtype, torch.float16)

        logger.info("Loading GPU rewriter %s …", self.hf_model_name)
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self._tokenizer = AutoTokenizer.from_pretrained(self.hf_model_name)
        self._hf_model  = AutoModelForCausalLM.from_pretrained(
            self.hf_model_name,
            torch_dtype=dtype,
            device_map="auto",
        )
        self._hf_model.eval()
        logger.info("GPU rewriter loaded.")

    # ------------------------------------------------------------------
    # Inference helpers
    # ------------------------------------------------------------------

    def _build_messages(self, prev_query: str, current_query: str) -> List[Dict]:
        return [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question précédente: {prev_query}\n"
                    f"Question actuelle: {current_query}\n"
                    "Question reformulée:"
                ),
            },
            # Disable Qwen3 thinking mode by pre-filling an empty <think> block.
            # Has no effect on non-Qwen3 models.
            {"role": "assistant", "content": "<think>\n\n</think>\n"},
        ]

    def _infer_cpu(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        self._load_cpu()
        t0 = time.time()
        response = self._llm.create_chat_completion(
            messages=self._build_messages(prev_query, current_query),
            max_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=1.0,
            top_k=1,
            stream=False,
        )
        elapsed = time.time() - t0
        return response["choices"][0]["message"]["content"].strip(), elapsed

    def _infer_gpu(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        import torch
        self._load_gpu()

        inputs = self._tokenizer.apply_chat_template(
            self._build_messages(prev_query, current_query),
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self._hf_model.device)
        input_len = inputs.shape[1]

        terminators = [self._tokenizer.eos_token_id]
        im_end_id   = self._tokenizer.convert_tokens_to_ids("<|im_end|>")
        if im_end_id and im_end_id != self._tokenizer.eos_token_id:
            terminators.append(im_end_id)

        t0 = time.time()
        with torch.no_grad():
            outputs = self._hf_model.generate(
                input_ids=inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=self.temperature if self.temperature > 0 else 1.0,
                pad_token_id=self._tokenizer.eos_token_id,
                eos_token_id=terminators,
            )
        elapsed   = time.time() - t0
        rewritten = self._tokenizer.decode(
            outputs[0][input_len:], skip_special_tokens=True
        ).strip()

        logger.debug("Raw GPU rewriter output: %r", rewritten)
        return rewritten, elapsed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rewrite(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        """
        Rewrite current_query into a standalone question.

        Args:
            prev_query    : last rewritten retrieval query (chained form)
            current_query : raw user input for this turn

        Returns:
            (rewritten_query, elapsed_seconds)
        """
        if self.device == "cuda":
            rewritten, elapsed = self._infer_gpu(prev_query, current_query)
        else:
            rewritten, elapsed = self._infer_cpu(prev_query, current_query)

        logger.debug(
            "Query rewritten in %.3fs | %r → %r", elapsed, current_query, rewritten
        )
        return rewritten, elapsed

    def cleanup(self) -> None:
        if self._llm is not None:
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None
        self._hf_model  = None
        self._tokenizer = None