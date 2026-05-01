#!/usr/bin/env python
"""
generate.py — Batch RAG generation with HuggingFace (GPU) or llama-cpp (CPU/GGUF) backends.

Expects pre-resolved turns from resolve_sections.py — no apps-dir needed here.
All turns (rag + ood) are written to a single output file, with routing_label
and all metadata fields preserved for downstream filtering/evaluation.

Config YAML structure
---------------------
configs:
  - id: my_run
    backend: hf          # "hf" | "gguf"   (required)
    prompt_file: prompt.txt

    # ── HuggingFace (backend: hf) ─────────────────────────────────────
    model_name: Qwen/Qwen3-8B-Instruct
    model_kwargs:
      torch_dtype: bfloat16
      device_map: cuda
    chat_template_kwargs:
      enable_thinking: false

    # ── llama-cpp / GGUF (backend: gguf) ─────────────────────────────
    gguf_path: /models/mistral-3b-q4_k_m.gguf
    n_ctx: 16384
    n_threads: 8
    n_batch: 512
    n_gpu_layers: 0

    # ── Generation kwargs (both backends) ────────────────────────────
    generation_kwargs:
      max_new_tokens: 1024   # HF
      # max_tokens: 1024     # GGUF
      temperature: 0.1
      top_p: 0.8
      top_k: 20
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
    """
    Load pre-resolved turns produced by resolve_sections.py.
    Each line is a JSON record with: query, context, history, ground_truth, etc.
    """
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
    system_content = system_template.format(history=history or "", context=context)
    return [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": query},
    ]


def _build_gguf_prompt(messages: List[Dict], model_name_hint: str) -> str:
    hint       = model_name_hint.lower()
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg   = next((m["content"] for m in messages if m["role"] == "user"),   "")

    if "llama" in hint or "meta-llama" in hint:
        return (
            "<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_msg}<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_msg}<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    elif "ministral" in hint or "mixtral" in hint:
        return f"[INST] {system_msg}\n\n{user_msg} [/INST]"
    else:
        # Qwen / ChatML — pre-fill empty <think> to disable thinking mode
        return (
            f"<|im_start|>system\n{system_msg}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n"
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
    thread   = threading.Thread(
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
        verbose=False,
    )


def _generate_gguf(
    model, messages: List[Dict], generation_kwargs: Dict, model_name_hint: str,
) -> Tuple[str, float, float]:
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


# ══════════════════════════════════════════════════════════════════════════════
# Main generation loop
# ══════════════════════════════════════════════════════════════════════════════

def run_generation(config: Dict, turns: List[Dict], output_dir: str):
    config_id = config["id"]
    backend   = config.get("backend", "hf").lower()

    print(f"\n{'='*60}")
    print(f"Config  : {config_id}")
    print(f"Backend : {backend.upper()}")
    print(f"Model   : {config.get('model_name') or config.get('gguf_path')}")
    print(f"{'='*60}")

    prompt_template   = load_prompt(config["prompt_file"])
    generation_kwargs = config.get("generation_kwargs", {}).copy()

    if backend == "hf":
        tokenizer, model     = _load_hf_model(config["model_name"], config.get("model_kwargs", {}))
        max_model_len        = getattr(model.config, "max_position_embeddings", 4096)
        chat_template_kwargs = config.get("chat_template_kwargs", {})
        model_name_hint      = config["model_name"]
    elif backend == "gguf":
        gguf_model      = _load_gguf_model(config)
        model_name_hint = config.get("gguf_path", "")
    else:
        raise ValueError(f"Unknown backend '{backend}'. Choose 'hf' or 'gguf'.")

    out_dir  = os.path.join(output_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{config_id}.jsonl")
    processed_ids = load_existing_results(out_path)

    if processed_ids:
        print(f"Resuming: {len(processed_ids)} turns already processed.")

    rag_count    = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count    = sum(1 for t in turns if t["routing_label"] == "ood")
    failed_count = 0

    with open(out_path, "a", encoding="utf-8") as out_file:
        for turn in tqdm(turns, desc=f"Generating ({config_id})", unit="turn"):
            turn_key = f"{turn['conversation_id']}_{turn['turn_id']}"
            if turn_key in processed_ids:
                continue

            tqdm.write(f"  turn {turn_key} [{turn['routing_label']}]")

            context  = turn.get("context", "")
            history  = turn.get("history", "")
            messages = _build_messages(turn["query"], context, history, prompt_template)

            generated, total_time, ttft, failed = "", 0.0, 0.0, False

            try:
                if backend == "hf":
                    generated, total_time, ttft = _generate_hf(
                        tokenizer, model, messages,
                        generation_kwargs, max_model_len, chat_template_kwargs,
                    )
                else:
                    generated, total_time, ttft = _generate_gguf(
                        gguf_model, messages, generation_kwargs, model_name_hint,
                    )
                tqdm.write(f"    → {total_time:.2f}s (TTFT {ttft:.2f}s)")

            except Exception as exc:
                generated = f"[ERROR: {exc}]"
                failed    = True
                failed_count += 1
                tqdm.write(f"    → FAILED: {exc}")

            record = {
                # ── identity ──────────────────────────────────────────
                "conversation_id":  turn["conversation_id"],
                "app_id":           turn["app_id"],
                "turn_id":          turn["turn_id"],
                # ── labels & metadata ─────────────────────────────────
                "routing_label":    turn["routing_label"],
                "query_quality":    turn.get("query_quality"),
                "isfollow_up":      turn.get("isfollow_up", False),
                # ── input ─────────────────────────────────────────────
                "query":            turn["query"],
                "history":          history,
                "context":          context,
                "context_sections": turn.get("context_sections", []),
                "missing_sections": turn.get("missing_sections", []),
                # ── ground truth ──────────────────────────────────────
                "ground_truth":     turn["ground_truth"],
                # ── generation output ─────────────────────────────────
                "generated":        generated,
                # ── run metadata ──────────────────────────────────────
                "config_id":        config_id,
                "backend":          backend,
                "prompt_file":      config.get("prompt_file"),
                "generation_time_sec": round(total_time, 4) if not failed else None,
                "ttft_sec":            round(ttft, 4)       if not failed else None,
                "failed":              failed,
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
    parser.add_argument("--config",     type=str, default="configs.yaml")
    parser.add_argument("--config-id",  type=str, default=None)
    parser.add_argument("--turns",      type=str, required=True,
                        help="Pre-resolved turns JSONL from resolve_sections.py")
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()

    all_configs = load_configs(args.config)
    if args.config_id:
        all_configs = [c for c in all_configs if c["id"] == args.config_id]
        if not all_configs:
            raise ValueError(f"Config ID '{args.config_id}' not found")

    turns     = load_resolved_turns(args.turns)
    rag_count = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count = sum(1 for t in turns if t["routing_label"] == "ood")
    print(f"Loaded {len(turns)} turns — RAG: {rag_count}, OOD: {ood_count}")

    for cfg in all_configs:
        run_generation(cfg, turns, args.output_dir)

    print("\nAll configs processed. Done.")


if __name__ == "__main__":
    main()

# python generate.py \
#     --config     configs.yaml \
#     --turns      data/resolved_turns.jsonl \
#     --output-dir outputs/