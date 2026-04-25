# generator.py
import time
import logging
import threading
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class Generator:
    """
    Unified generator:
      - CPU  → llama-cpp-python (GGUF, quantized, fast)
      - GPU  → HuggingFace transformers (fp16, streamed)

    Configuration (top‑level "generator" section):
        - device (str)                  # "cpu" or "cuda", default "cpu"
        - prompt_file (str)             # path to system prompt template file (required)
        - generation_kwargs (dict)      # extra kwargs passed to generate()
        # CPU‑specific:
        - gguf_path (str)               # required if device="cpu"
        - n_ctx (int)                   # context size, default 4000
        - n_threads (int)               # number of CPU threads, default 4
        - n_batch (int)                 # batch size for prompt processing, default 1024
        # GPU‑specific:
        - hf_model_name (str)           # required if device="cuda"
        - torch_dtype (str)             # "float16", "bfloat16", "float32", default "float16"
        # Default generation parameters (can be overridden by generation_kwargs):
        - max_tokens (int)              # default 1024 (CPU) or 256 (GPU)
        - temperature (float)           # default 0.1
        - top_p (float)                 # default 0.8
        - top_k (int)                   # default 20
        - min_p (float)                 # CPU only, default 0.0
        - presence_penalty (float)      # CPU only, default 1.5
        - repeat_penalty (float)        # CPU: 1.1, GPU: repetition_penalty 1.1
    """

    def __init__(self, config: Dict[str, Any]):
        gen_cfg = config.get("generator", {})
        self.device = gen_cfg.get("device", "cpu")

        # Prompt template
        prompt_file = gen_cfg.get("prompt_file")
        if not prompt_file:
            raise ValueError("generator.prompt_file is required")
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

        self.generation_kwargs = gen_cfg.get("generation_kwargs", {})

        if self.device == "cpu":
            self._init_cpu(gen_cfg)
        elif self.device == "cuda":
            self._init_gpu(gen_cfg)
        else:
            raise ValueError(f"Unsupported device: {self.device}")

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_cpu(self, cfg: Dict[str, Any]):
        gguf_path = cfg.get("gguf_path")
        if not gguf_path:
            raise ValueError("generator.gguf_path is required when device='cpu'")

        from llama_cpp import Llama
        self.model = Llama(
            model_path=gguf_path,
            n_ctx=cfg.get("n_ctx", 4000),
            n_threads=cfg.get("n_threads", 4),
            n_batch=cfg.get("n_batch", 1024),
            mmap=True,
            verbose=False,
        )
        # Default generation parameters for CPU (llama.cpp)
        self._defaults = {
            "max_tokens": cfg.get("max_tokens", 1024),
            "temperature": cfg.get("temperature", 0.1),
            "top_p": cfg.get("top_p", 0.8),
            "top_k": cfg.get("top_k", 20),
            "min_p": cfg.get("min_p", 0.0),
            "presence_penalty": cfg.get("presence_penalty", 1.5),
            "repeat_penalty": cfg.get("repeat_penalty", 1.1),
        }

    def _init_gpu(self, cfg: Dict[str, Any]):
        hf_model_name = cfg.get("hf_model_name")
        if not hf_model_name:
            raise ValueError("generator.hf_model_name is required when device='cuda'")

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dtype_map = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }
        torch_dtype = cfg.get("torch_dtype", "float16")
        self.tokenizer = AutoTokenizer.from_pretrained(hf_model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.hf_model = AutoModelForCausalLM.from_pretrained(
            hf_model_name,
            torch_dtype=dtype_map.get(torch_dtype, torch.float16),
            device_map="cuda",
        )
        self.hf_model.eval()
        self.max_model_len = getattr(self.hf_model.config, "max_position_embeddings", 2048)

        # Default generation parameters for GPU (HuggingFace)
        self._defaults = {
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "use_cache": True,
            "max_new_tokens": cfg.get("max_tokens", 256),
            "do_sample": cfg.get("do_sample", True),
            "temperature": cfg.get("temperature", 0.1),
            "top_p": cfg.get("top_p", 0.8),
            "top_k": cfg.get("top_k", 20),
            "repetition_penalty": cfg.get("repeat_penalty", 1.1),
        }

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self,
        query: str,
        section_texts: List[str],
        history: str = "",
        verbose: bool = False,
    ):
        context = "\n\n---\n\n".join(t for t in section_texts if t)

        if self.device == "cpu":
            yield from self._stream_cpu(query, context, history, verbose)
        else:
            yield from self._stream_gpu(query, context, history, verbose)

    # ------------------------------------------------------------------
    # CPU streaming (llama-cpp)
    # ------------------------------------------------------------------

    def _stream_cpu(self, query: str, context: str, history: str, verbose: bool):
        system = self.prompt_template.format(history=history or "", context=context)

        # Pre-fill with empty <think> block to disable Qwen3 thinking mode
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{query}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n"
        )

        kwargs = {**self._defaults, **self.generation_kwargs}
        start = time.time()
        ttft = None
        tokens = self.model.tokenize(prompt.encode("utf-8"))
        logger.info("CPU actual prompt tokens: %d", len(tokens))
        for chunk in self.model(prompt, stream=True, **kwargs):
            token = chunk["choices"][0]["text"]
            if token:
                if ttft is None:
                    ttft = round(time.time() - start, 4)
                yield token

        if verbose:
            yield {
                "done": True,
                "ttft_sec": ttft or 0.0,
                "total_sec": round(time.time() - start, 4),
            }

    # ------------------------------------------------------------------
    # GPU streaming (HuggingFace)
    # ------------------------------------------------------------------

    def _stream_gpu(self, query: str, context: str, history: str, verbose: bool):
        from transformers import TextIteratorStreamer

        system_content = self.prompt_template.format(history=history or "", context=context)
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        # enable_thinking=False via chat template kwargs (transformers >= 4.51)
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                chat_template_kwargs={"enable_thinking": False},
            )
        except TypeError:
            # fallback for older transformers — pre-fill empty think block
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            prompt += "<|im_start|>assistant\n<think>\n\n</think>\n"

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_model_len,
        ).to("cuda")

        logger.info("Prompt tokens: %d", inputs["input_ids"].shape[1])

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        kwargs = {**inputs, **self._defaults, **self.generation_kwargs, "streamer": streamer}
        thread = threading.Thread(target=self.hf_model.generate, kwargs=kwargs, daemon=True)

        start = time.time()
        thread.start()
        ttft = None

        for token in streamer:
            if token:
                if ttft is None:
                    ttft = round(time.time() - start, 4)
                yield token

        thread.join()

        if verbose:
            yield {
                "done": True,
                "ttft_sec": ttft or 0.0,
                "total_sec": round(time.time() - start, 4),
            }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        if self.device == "cpu":
            del self.model
        else:
            import torch
            del self.hf_model, self.tokenizer
            torch.cuda.empty_cache()