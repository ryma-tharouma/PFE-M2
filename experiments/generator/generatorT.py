from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TextIteratorStreamer,
)

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"

MODEL_NAMES = {
    "llama-8b": "meta-llama/Llama-3.1-8B",
    "ministral-8b": "mistralai/Ministral-3-8B-Instruct-2512",
    "qwen3.5-4b": "Qwen/Qwen3.5-4B",
}


@dataclass
class GenParams:
    max_tokens: int = 256
    temperature: float = 0.2
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None


@dataclass
class Sample:
    query: str
    history: str = ""
    context: str = ""


def load_prompt(prompt_file: Union[str, Path], prompt_dir: Union[str, Path] = PROMPTS_DIR) -> str:
    path = Path(prompt_dir) / prompt_file
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_prompt(template: str, query: str, history: str, context: str) -> str:
    return template.format(
        query=(query or "").strip(),
        history=(history or "").strip(),
        context=(context or "").strip(),
    )


class Generator:
    def __init__(
        self,
        model_name: str,
        prompt: Union[str, Path],
        prompt_dir: Union[str, Path] = PROMPTS_DIR,
        device: str = "cuda",
        torch_dtype: Optional[torch.dtype] = torch.float16,
        device_map: str = "auto",
        **model_kwargs,
    ):
        if model_name not in MODEL_NAMES:
            raise ValueError(f"Unknown model '{model_name}'. Available: {list(MODEL_NAMES)}")
        self.model_name = model_name
        self.prompt_file = prompt
        self.prompt_dir = Path(prompt_dir)
        self.template = load_prompt(prompt, self.prompt_dir)

        hf_name = MODEL_NAMES[model_name]

        self.tokenizer = AutoTokenizer.from_pretrained(hf_name, use_fast=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        self.model = AutoModelForCausalLM.from_pretrained(
            hf_name,
            torch_dtype=torch_dtype,
            device_map=device_map,
            **model_kwargs,
        )
        self.device = device

    def generate_one(self, sample: Sample, gen: GenParams, stream: bool = True):
        prompt = build_prompt(self.template, sample.query, sample.history, sample.context)

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        t0 = time.perf_counter()

        if stream:
            streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
            generation_kwargs = dict(
                **inputs,
                max_new_tokens=gen.max_tokens,
                temperature=gen.temperature,
                top_p=gen.top_p,
                repetition_penalty=gen.repeat_penalty,
                streamer=streamer,
            )
            if gen.stop:
                # basic stop support: rely on eos_token; for custom stop,
                # post-process the stream externally
                pass

            # run generation in a background thread
            import threading
            thread = threading.Thread(target=self.model.generate, kwargs=generation_kwargs)
            thread.start()

            ttft = None
            chunks = []
            for token_text in streamer:
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                chunks.append(token_text)

            text = "".join(chunks)
            total = (time.perf_counter() - t0) * 1000
            return text, ttft or 0.0, total

        # non-streaming
        output = self.model.generate(
            **inputs,
            max_new_tokens=gen.max_tokens,
            temperature=gen.temperature,
            top_p=gen.top_p,
            repetition_penalty=gen.repeat_penalty,
        )
        text = self.tokenizer.decode(output[0], skip_special_tokens=True)
        total = (time.perf_counter() - t0) * 1000
        return text, 0.0, total