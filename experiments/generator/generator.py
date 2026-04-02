from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from llama_cpp import Llama

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
MODELS_DIR = BASE_DIR / "models"

MODEL_PATHS = {
    "llama-8b": f"{MODELS_DIR}/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "ministral-3b": f"{MODELS_DIR}/Ministral-3-3B-Instruct-2512-Q8_0.gguf",
    "qwen3.5-4b": f"{MODELS_DIR}/Qwen3.5-4B-Q4_K_M.gguf",
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
    def __init__(self, model_name: str, prompt: Union[str, Path], prompt_dir: Union[str, Path] = PROMPTS_DIR, **model_kwargs):
        if model_name not in MODEL_PATHS:
            raise ValueError(f"Unknown model '{model_name}'. Available: {list(MODEL_PATHS)}")
        self.model_name = model_name
        self.prompt_file = prompt
        self.prompt_dir = Path(prompt_dir)
        self.template = load_prompt(prompt, self.prompt_dir)
        self.llm = Llama(model_path=MODEL_PATHS[model_name], verbose=False, **model_kwargs)

    def generate_one(self, sample: Sample, gen: GenParams, stream: bool = True):
        prompt = build_prompt(self.template, sample.query, sample.history, sample.context)

        t0 = time.perf_counter()

        if stream:
            ttft = None
            out_chunks = []
            for chunk in self.llm(
                prompt,
                max_tokens=gen.max_tokens,
                temperature=gen.temperature,
                top_p=gen.top_p,
                repeat_penalty=gen.repeat_penalty,
                stop=gen.stop,
                stream=True,
            ):
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                out_chunks.append(chunk["choices"][0]["text"])
            text = "".join(out_chunks)
            total = (time.perf_counter() - t0) * 1000
            return text, ttft or 0.0, total

        output = self.llm(
            prompt,
            max_tokens=gen.max_tokens,
            temperature=gen.temperature,
            top_p=gen.top_p,
            repeat_penalty=gen.repeat_penalty,
            stop=gen.stop,
            stream=False,
        )
        text = output["choices"][0]["text"]
        total = (time.perf_counter() - t0) * 1000
        return text, 0.0, total