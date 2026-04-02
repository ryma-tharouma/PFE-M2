"""
generator.py

Minimal experiment-ready generator using llama-cpp-python.
- Init with model name, prompt file, and model params (**kwargs).
- Generate with (query, history, context) or batch.
- verbose=True logs timing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from llama_cpp import Llama


PROMPTS_DIR = Path("prompts")
MODELS_DIR = Path("models")

MODEL_PATHS = {
    "llama-8b": f"{MODELS_DIR}/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "ministral-3b": f"{MODELS_DIR}/Ministral-3-3B-Instruct-2512-Q8_0.gguf",
    "qwen3.5-4b": f"{MODELS_DIR}/Qwen3.5-4B-Q4_K_M.gguf",
}


@dataclass
class GenParams:
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None


@dataclass
class Sample:
    query: str
    history: str = ""
    context: str = ""


def load_prompt(prompt_file: Union[str, Path]) -> str:
    path = PROMPTS_DIR / prompt_file
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_prompt(model_name: str, template: str, query: str, history: str, context: str) -> str:
    """
    Model-specific prompt builder hook.
    Template should include {query}, {history}, {context}.
    """
    prompt = template.format(
        query=query.strip(),
        history=history.strip(),
        context=context.strip(),
    )
    # Add model-specific formatting here if needed later
    if model_name in ("llama-8b", "mistral-7b", "qwen3.5-4b"):
        return prompt
    return prompt


class Generator:
    def __init__(self, model_name: str, prompt: Union[str, Path], **model_kwargs):
        if model_name not in MODEL_PATHS:
            raise ValueError(f"Unknown model '{model_name}'. Available: {list(MODEL_PATHS)}")

        self.model_name = model_name
        self.prompt_file = prompt
        self.template = load_prompt(prompt)
        self.llm = Llama(model_path=MODEL_PATHS[model_name], verbose=False, **model_kwargs)

    def _infer_one(self, sample: Sample, gen_params: GenParams) -> str:
        prompt = build_prompt(
            model_name=self.model_name,
            template=self.template,
            query=sample.query,
            history=sample.history,
            context=sample.context,
        )
        out = self.llm(
            prompt,
            max_tokens=gen_params.max_tokens,
            temperature=gen_params.temperature,
            top_p=gen_params.top_p,
            repeat_penalty=gen_params.repeat_penalty,
            stop=gen_params.stop,
        )
        return out["choices"][0]["text"]

    def generate(
        self,
        data: Union[Sample, Dict, Iterable[Union[Sample, Dict]]],
        gen_params: Optional[GenParams] = None,
        batch: bool = False,
        verbose: bool = False,
    ) -> Union[str, List[str]]:
        """
        data:
          - Sample or dict with keys: query, history, context (single)
          - iterable of Sample/dict (batch)
        batch:
          - if True, expects iterable and returns list
        verbose:
          - logs timing per item and total
        """
        gen_params = gen_params or GenParams()

        def to_sample(x) -> Sample:
            if isinstance(x, Sample):
                return x
            return Sample(**x)

        if not batch:
            sample = to_sample(data)  # type: ignore[arg-type]
            t0 = time.time()
            result = self._infer_one(sample, gen_params)
            if verbose:
                print(f"[generate] 1 item in {time.time()-t0:.3f}s")
            return result

        items = [to_sample(x) for x in data]  # type: ignore[arg-type]
        outputs: List[str] = []
        t_start = time.time()
        for i, sample in enumerate(items, 1):
            t0 = time.time()
            outputs.append(self._infer_one(sample, gen_params))
            if verbose:
                print(f"[generate] item {i}/{len(items)} in {time.time()-t0:.3f}s")
        if verbose:
            print(f"[generate] total {len(items)} items in {time.time()-t_start:.3f}s")
        return outputs


if __name__ == "__main__":
    # Example
    stop_tokens_per_model = {
        "llama-8b": ["<|eot_id|>"],
        "ministral-3b": ["</s>"],
        "qwen3.5-4b": ["<|im_end|>"],
    }
    prompt_per_model = {
        "llama-8b": "l.txt",
        "ministral-3b": "m.txt",
        "qwen3.5-4b": "q.txt",
    }

    for model, stop in stop_tokens_per_model.items():
        gen_kwargs = dict(
            model_name=model,
            prompt=prompt_per_model[model],
            n_ctx=40960,
            n_threads=8,
            n_gpu_layers=20,
        )
        if model == "qwen3.5-4b":
            gen_kwargs["chat_template_kwargs"] = {"enable_thinking": False}

        gen = Generator(**gen_kwargs)
        print(gen.model_name, gen.prompt_file)

        single = gen.generate(
            {
                "query": "comment lui modifier",
                "history": (
                    "user : comment cree un utilisateur\n"
                    "assistant : pour creer un utilisateur, allez dans Administration > Utilisateurs, "
                    "puis cliquez sur \"Nouveau\". Renseignez les champs requis et validez."
                ),
                "context": (
                    "Pour modifier un utilisateur : ouvrez Administration > Utilisateurs, "
                    "sélectionnez l’utilisateur, puis cliquez sur \"Modifier\". "
                    "Mettez à jour les champs et enregistrez.\n\n"
                    "Pour supprimer un utilisateur : dans Administration > Utilisateurs, "
                    "sélectionnez l’utilisateur, cliquez sur \"Supprimer\", puis confirmez."
                ),
            },
            GenParams(max_tokens=200, stop=stop),
            batch=False,
            verbose=True,
        )
        print(single)