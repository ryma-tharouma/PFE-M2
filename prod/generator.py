# generator.py
import time
import logging
import threading
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Generator:
    """
    Unified generator:
      - CPU  → llama-cpp-python (GGUF, quantized, fast)
      - GPU  → HuggingFace transformers (fp16, streamed)
    """

    def __init__(
        self,
        prompt_file: str,
        # --- shared ---
        device: str = "cpu",
        generation_kwargs: Optional[Dict] = None,
        # --- CPU / llama-cpp ---
        gguf_path: str = None,
        n_ctx: int = 8000,
        n_threads: int = 4,
        # --- GPU / HuggingFace ---
        hf_model_name: str = None,
        torch_dtype: str = "float16",
    ):
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

        self.device = device
        self.generation_kwargs = generation_kwargs or {}

        if device == "cpu":
            self._init_cpu(gguf_path, n_ctx, n_threads)
        else:
            self._init_gpu(hf_model_name, torch_dtype)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_cpu(self, gguf_path: str, n_ctx: int, n_threads: int):
        if not gguf_path:
            raise ValueError("gguf_path is required when device='cpu'")
        from llama_cpp import Llama
        self.model = Llama(
            model_path=gguf_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
        )
        # Instruct mode (no thinking) for general tasks per Qwen3 docs
        self._defaults = {
            "max_tokens": 512,
            "temperature": 0.1,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.1,
        }

    def _init_gpu(self, hf_model_name: str, torch_dtype: str):
        if not hf_model_name:
            raise ValueError("hf_model_name is required when device='cuda'")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dtype_map = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
            "float32":  torch.float32,
        }
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
        self._defaults = {
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "use_cache": True,
            "max_new_tokens": 256,
            "do_sample": True,
            "temperature": 0.1,
            "top_p": 0.8,
            "top_k": 20,
            "repetition_penalty": 1.1,
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

        # Pre-fill with empty <think> block — the correct Python-side way to
        # disable Qwen3 thinking mode (equivalent to --chat-template-kwargs
        # '{"enable_thinking": false}' in llama-cli, which is a CLI-only flag
        # not exposed in the Python API yet).
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{query}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n"
        )

        kwargs = {**self._defaults, **self.generation_kwargs}
        start  = time.time()
        ttft   = None

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
            {"role": "user",   "content": query},
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
        ttft  = None

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