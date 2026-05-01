#!/usr/bin/env python
"""
generate.py — Batch RAG generation with HuggingFace (GPU) or llama-cpp (CPU/GGUF) backends.

Supports optional prefix caching (enable_prefix_cache: true) for GGUF backend.
When caching is enabled, the prompt file must contain ONLY the static system instructions
(no {history} or {context} placeholders). History and context are moved to the user message.
"""

import os
import json
import time
import yaml
import argparse
import threading
import logging
from typing import List, Dict, Tuple, Optional

from tqdm import tqdm

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Config + resolved turns loading
# ══════════════════════════════════════════════════════════════════════════════

def load_configs(config_path: str) -> List[Dict]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["configs"]


def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_resolved_turns(turns_path: str) -> List[Dict]:
    turns = []
    with open(turns_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                turns.append(json.loads(line))
    return turns


def load_existing_results(path: str) -> set:
    ids: set = set()
    if not os.path.exists(path):
        return ids
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                ids.add(f"{rec['conversation_id']}_{rec['turn_id']}")
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


# ══════════════════════════════════════════════════════════════════════════════
# Prompt building
# ══════════════════════════════════════════════════════════════════════════════

def _build_messages(query: str, context: str, history: str, system_template: str) -> List[Dict]:
    """Legacy: system prompt includes history and context via placeholders."""
    system_content = system_template.format(history=history or "", context=context)
    return [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": query},
    ]


def _build_cached_gguf_prompt_qwen(system_prompt: str, history: str, context: str, query: str) -> str:
    """Qwen (ChatML) format for prefix caching."""
    user_content = f"Historique : {history}\n\nContexte : {context}\n\nQuestion : {query}"
    return (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def _build_cached_gguf_prompt_ministral(system_prompt: str, history: str, context: str, query: str) -> str:
    """Ministral/Mixtral format for prefix caching.
    Uses two-turn structure: static system as first instruction, then user message.
    """
    user_content = f"Historique : {history}\n\nContexte : {context}\n\nQuestion : {query}"
    # Some Mistral variants use <s> before the first INST, but not always required.
    # We'll use the standard style without extra <s> as it's often added by llama.cpp.
    return (
        f"[INST] {system_prompt} [/INST]</s>\n"
        f"[INST] {user_content} [/INST]"
    )


def _build_cached_gguf_prompt_llama(system_prompt: str, history: str, context: str, query: str) -> str:
    """LLaMA format for prefix caching (if needed)."""
    user_content = f"Historique : {history}\n\nContexte : {context}\n\nQuestion : {query}"
    return (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_prompt}<|eot_id|>\n"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_content}<|eot_id|>\n"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _detect_model_family(model_path: str) -> str:
    """Detect model family from path string."""
    path_lower = model_path.lower()
    if "qwen" in path_lower:
        return "qwen"
    elif "ministral" in path_lower or "mixtral" in path_lower or "mistral" in path_lower:
        return "ministral"
    elif "llama" in path_lower:
        return "llama"
    else:
        # Default to qwen-like format
        return "qwen"


def _build_gguf_prompt(messages: List[Dict], model_name_hint: str) -> str:
    """Legacy: build prompt from messages list (system+user)."""
    hint = model_name_hint.lower()
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

    if "llama" in hint or "meta-llama" in hint:
        return (
            "<|begin_of_text|>"
            "<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_msg}<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_msg}<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    elif "ministral" in hint or "mixtral" in hint:
        return f"[INST] {system_msg}\n\n{user_msg} [/INST]"
    else:
        # Qwen / ChatML
        return (
            f"<|im_start|>system\n{system_msg}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )


# ══════════════════════════════════════════════════════════════════════════════
# HuggingFace backend
# ══════════════════════════════════════════════════════════════════════════════

def _load_hf_model(model_name: str, model_kwargs: Dict):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    mk = model_kwargs.copy()
    if "torch_dtype" in mk:
        mk["torch_dtype"] = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
        }.get(mk["torch_dtype"], torch.float32)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name, **mk)
    model.eval()
    return tokenizer, model


def _apply_chat_template_hf(tokenizer, messages: List[Dict], chat_template_kwargs: Dict) -> str:
    try:
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, **chat_template_kwargs,
        )
    except (TypeError, Exception):
        pass
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if "qwen" in getattr(tokenizer, "name_or_path", "").lower():
        prompt += "<think>\n\n</think>\n"
    return prompt


def _generate_hf(
    tokenizer, model, messages: List[Dict],
    generation_kwargs: Dict, max_model_len: int,
    chat_template_kwargs: Optional[Dict] = None,
) -> Tuple[str, float, float]:
    import torch
    from transformers import TextIteratorStreamer

    prompt = _apply_chat_template_hf(tokenizer, messages, chat_template_kwargs or {})
    inputs = tokenizer(
        prompt, return_tensors="pt", truncation=True, max_length=max_model_len,
    ).to(model.device)

    gen_kwargs = {
        "pad_token_id": tokenizer.eos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
        **generation_kwargs,
    }

    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    thread = threading.Thread(
        target=model.generate,
        kwargs={**inputs, **gen_kwargs, "streamer": streamer},
        daemon=True,
    )

    start, ttft, tokens = time.time(), None, []
    thread.start()
    for tok in streamer:
        if tok:
            if ttft is None:
                ttft = time.time() - start
            tokens.append(tok)
    thread.join()

    total = time.time() - start
    return "".join(tokens).strip(), total, ttft or total


# ══════════════════════════════════════════════════════════════════════════════
# llama-cpp / GGUF backend
# ══════════════════════════════════════════════════════════════════════════════

def _load_gguf_model(config: Dict):
    from llama_cpp import Llama

    gguf_path = config.get("gguf_path")
    if not gguf_path:
        raise ValueError("gguf_path is required when backend='gguf'")

    return Llama(
        model_path=gguf_path,
        n_ctx=config.get("n_ctx", 16384),
        n_threads=config.get("n_threads", 4),
        n_batch=config.get("n_batch", 1024),
        n_gpu_layers=config.get("n_gpu_layers", 0),
        mmap=True,
        verbose=True,  # set to True for detailed caching logs
    )


def _generate_gguf_legacy(
    model, messages: List[Dict], generation_kwargs: Dict, model_name_hint: str,
) -> Tuple[str, float, float]:
    """Legacy generation: system prompt includes history and context."""
    prompt = _build_gguf_prompt(messages, model_name_hint)
    kwargs = {
        "max_tokens":       2048,
        "temperature":      0.1,
        "top_p":            0.8,
        "top_k":            20,
        "min_p":            0.0,
        "repeat_penalty":   1.1,
        "presence_penalty": 0.0,
        "stream":           True,
        **generation_kwargs,
    }

    start, ttft, tokens = time.time(), None, []
    for chunk in model(prompt, **kwargs):
        tok = chunk["choices"][0]["text"]
        if tok:
            if ttft is None:
                ttft = time.time() - start
            tokens.append(tok)

    total = time.time() - start
    return "".join(tokens).strip(), total, ttft or total


def _generate_gguf_cached(
    model, system_prompt: str, history: str, context: str, query: str,
    generation_kwargs: Dict, model_family: str,
) -> Tuple[str, float, float]:
    """Cached generation using appropriate format for the model family."""
    if model_family == "qwen":
        prompt = _build_cached_gguf_prompt_qwen(system_prompt, history, context, query)
    elif model_family == "ministral":
        prompt = _build_cached_gguf_prompt_ministral(system_prompt, history, context, query)
    elif model_family == "llama":
        prompt = _build_cached_gguf_prompt_llama(system_prompt, history, context, query)
    else:
        # fallback to qwen
        prompt = _build_cached_gguf_prompt_qwen(system_prompt, history, context, query)

    kwargs = {
        "max_tokens":       2048,
        "temperature":      0.1,
        "top_p":            0.8,
        "top_k":            20,
        "min_p":            0.0,
        "repeat_penalty":   1.1,
        "presence_penalty": 0.0,
        "stream":           True,
        **generation_kwargs,
    }

    start, ttft, tokens = time.time(), None, []
    for chunk in model(prompt, **kwargs):
        tok = chunk["choices"][0]["text"]
        if tok:
            if ttft is None:
                ttft = time.time() - start
            tokens.append(tok)

    total = time.time() - start
    return "".join(tokens).strip(), total, ttft or total


# ══════════════════════════════════════════════════════════════════════════════
# Main generation loop
# ══════════════════════════════════════════════════════════════════════════════

def run_generation(config: Dict, turns: List[Dict], output_dir: str):
    config_id = config["id"]
    backend = config.get("backend", "hf").lower()
    enable_cache = config.get("enable_prefix_cache", False)
    # optionally, user can specify model_family override
    model_family_override = config.get("model_family", None)

    print(f"\n{'='*60}")
    print(f"Config  : {config_id}")
    print(f"Backend : {backend.upper()}")
    print(f"Model   : {config.get('model_name') or config.get('gguf_path')}")
    print(f"Prefix caching: {'ENABLED' if enable_cache else 'DISABLED'}")
    if enable_cache and backend == "gguf":
        print(f"Model family for caching: {model_family_override or 'auto-detect'}")
    print(f"{'='*60}")

    prompt_template = load_prompt(config["prompt_file"])
    generation_kwargs = config.get("generation_kwargs", {}).copy()

    if backend == "hf":
        tokenizer, model = _load_hf_model(config["model_name"], config.get("model_kwargs", {}))
        max_model_len = getattr(model.config, "max_position_embeddings", 4096)
        chat_template_kwargs = config.get("chat_template_kwargs", {})
        model_name_hint = config["model_name"]
    elif backend == "gguf":
        gguf_model = _load_gguf_model(config)
        model_path = config.get("gguf_path", "")
        model_name_hint = model_path

        if enable_cache:
            # Determine model family
            if model_family_override:
                model_family = model_family_override
            else:
                model_family = _detect_model_family(model_path)
            print(f"Using {model_family} cached prompt format")
            # Check that prompt file does NOT contain placeholders (best effort warning)
            if "{history}" in prompt_template or "{context}" in prompt_template:
                print("WARNING: enable_prefix_cache=True but prompt file contains {history} or {context}. Caching may not work.")
            static_system = prompt_template
        else:
            static_system = None
            model_family = None
    else:
        raise ValueError(f"Unknown backend '{backend}'. Choose 'hf' or 'gguf'.")

    out_dir = os.path.join(output_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{config_id}.jsonl")
    processed_ids = load_existing_results(out_path)

    if processed_ids:
        print(f"Resuming: {len(processed_ids)} turns already processed.")

    rag_count = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count = sum(1 for t in turns if t["routing_label"] == "ood")
    failed_count = 0

    with open(out_path, "a", encoding="utf-8") as out_file:
        for turn in tqdm(turns, desc=f"Generating ({config_id})", unit="turn"):
            turn_key = f"{turn['conversation_id']}_{turn['turn_id']}"
            if turn_key in processed_ids:
                continue

            tqdm.write(f"  turn {turn_key} [{turn['routing_label']}]")

            context = turn.get("context", "")
            history = turn.get("history", "")
            query = turn["query"]

            generated, total_time, ttft, failed = "", 0.0, 0.0, False

            try:
                if backend == "hf":
                    messages = _build_messages(query, context, history, prompt_template)
                    generated, total_time, ttft = _generate_hf(
                        tokenizer, model, messages,
                        generation_kwargs, max_model_len, chat_template_kwargs,
                    )
                else:  # gguf
                    if enable_cache:
                        generated, total_time, ttft = _generate_gguf_cached(
                            gguf_model, static_system, history, context, query,
                            generation_kwargs, model_family
                        )
                    else:
                        messages = _build_messages(query, context, history, prompt_template)
                        generated, total_time, ttft = _generate_gguf_legacy(
                            gguf_model, messages, generation_kwargs, model_name_hint
                        )
                tqdm.write(f"    → {total_time:.2f}s (TTFT {ttft:.2f}s)")

            except Exception as exc:
                generated = f"[ERROR: {exc}]"
                failed = True
                failed_count += 1
                tqdm.write(f"    → FAILED: {exc}")

            record = {
                "conversation_id": turn["conversation_id"],
                "app_id": turn["app_id"],
                "turn_id": turn["turn_id"],
                "routing_label": turn["routing_label"],
                "query_quality": turn.get("query_quality"),
                "isfollow_up": turn.get("isfollow_up", False),
                "query": query,
                "history": history,
                "context": context,
                "context_sections": turn.get("context_sections", []),
                "missing_sections": turn.get("missing_sections", []),
                "ground_truth": turn["ground_truth"],
                "generated": generated,
                "config_id": config_id,
                "backend": backend,
                "prompt_file": config.get("prompt_file"),
                "enable_prefix_cache": enable_cache,
                "generation_time_sec": round(total_time, 4) if not failed else None,
                "ttft_sec": round(ttft, 4) if not failed else None,
                "failed": failed,
            }
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()

    if backend == "hf":
        import torch
        del model, tokenizer
        torch.cuda.empty_cache()
    else:
        del gguf_model

    print(f"\n{'─'*60}")
    print(f"Config {config_id} done.")
    print(f"  RAG: {rag_count}  |  OOD: {ood_count}  |  Failed: {failed_count}")
    print(f"  Output → {out_path}")
    print(f"{'─'*60}")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Batch RAG generation (HF + GGUF)")
    parser.add_argument("--config", type=str, default="configs.yaml")
    parser.add_argument("--config-id", type=str, default=None)
    parser.add_argument("--turns", type=str, required=True,
                        help="Pre-resolved turns JSONL from resolve_sections.py")
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()

    all_configs = load_configs(args.config)
    if args.config_id:
        all_configs = [c for c in all_configs if c["id"] == args.config_id]
        if not all_configs:
            raise ValueError(f"Config ID '{args.config_id}' not found")

    turns = load_resolved_turns(args.turns)
    rag_count = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count = sum(1 for t in turns if t["routing_label"] == "ood")
    print(f"Loaded {len(turns)} turns — RAG: {rag_count}, OOD: {ood_count}")

    for cfg in all_configs:
        run_generation(cfg, turns, args.output_dir)

    print("\nAll configs processed. Done.")


if __name__ == "__main__":
    main()