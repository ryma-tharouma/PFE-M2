import time
import threading
import logging
import torch
from typing import List, Dict, Optional
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Generator
# ----------------------------------------------------------------------

class Generator:
    """
    Loads a causal LM and streams answers from pre-resolved context texts.

    Args:
        model_name        : HuggingFace model name or local path
        prompt_file       : path to system prompt template file
                            (must contain {context} and {history} placeholders)
        torch_dtype       : "float16", "bfloat16", or "float32"
        device_map        : passed directly to from_pretrained (e.g. "auto")
        generation_kwargs : overrides for model.generate() defaults
    """

    def __init__(
        self,
        model_name: str,
        prompt_file: str,
        torch_dtype: str = "bfloat16",
        device_map: str = "auto",
        generation_kwargs: Optional[Dict] = None,
    ):
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

        dtype_map = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
            "float32":  torch.float32,
        }
        dtype = dtype_map.get(torch_dtype, torch.bfloat16)

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map=device_map,
        )
        self.model.eval()

        self.max_model_len = getattr(self.model.config, "max_position_embeddings", 2048)

        self.generation_kwargs = {
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            **(generation_kwargs or {}),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        query: str,
        section_texts: List[str],
        history: str = "",
        verbose: bool = False,
    ):
        """
        Stream an answer token by token given pre-resolved section texts.

        Args:
            query         : user query string
            section_texts : section texts already resolved and ordered by caller
            history       : previous turn as "Utilisateur: ...\\nAssistant: ..."
            verbose       : if True, final yielded item is a timing sentinel dict:
                            {"done": True, "ttft_sec": float, "total_sec": float}

        Yields:
            str tokens during generation, then optionally the timing sentinel.
        """
        context  = "\n\n---\n\n".join(t for t in section_texts if t)
        messages = self._build_messages(query, context, history)
        yield from self._stream(messages, verbose)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, query: str, context: str, history: str) -> List[Dict]:
        system_content = self.prompt_template.format(
            history=history or "",
            context=context,
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": query},
        ]

    def _stream(self, messages: List[Dict], verbose: bool):
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_model_len,
        ).to(self.model.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        thread = threading.Thread(
            target=self.model.generate,
            kwargs={**inputs, **self.generation_kwargs, "streamer": streamer},
            daemon=True,
        )

        start_total = time.time()
        thread.start()

        ttft = None
        for token in streamer:
            if token:
                if ttft is None:
                    ttft = round(time.time() - start_total, 4)
                yield token

        thread.join()
        total = round(time.time() - start_total, 4)

        if verbose:
            yield {"done": True, "ttft_sec": ttft or total, "total_sec": total}

    def cleanup(self):
        del self.model, self.tokenizer
        torch.cuda.empty_cache()