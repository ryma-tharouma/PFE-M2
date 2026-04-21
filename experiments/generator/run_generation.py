#!/usr/bin/env python
import os
import json
import yaml
import argparse
import functools
import time
import re
import numpy as np
import torch
from typing import List, Dict, Tuple, Optional
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    StoppingCriteria,
    StoppingCriteriaList,
)
from tqdm import tqdm


def load_configs(config_path: str) -> List[Dict]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["configs"]


def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_conversations_with_history(conv_path: str) -> List[Dict]:
    all_turns = []
    with open(conv_path, "r", encoding="utf-8") as f:
        for line in f:
            conv = json.loads(line)
            prev_turn_data = None
            for turn in conv["turns"]:
                current_label  = turn.get("routing_label", "rag")
                current_query  = turn.get("user_query", "")
                current_answer = turn.get("answer", "")

                if current_label in ("rag", "ood"):
                    history_text = ""
                    if prev_turn_data is not None:
                        history_text = (
                            f"Utilisateur: {prev_turn_data['query']}\n"
                            f"Assistant: {prev_turn_data['answer']}"
                        )
                    all_turns.append({
                        "conversation_id":   conv["conversation_id"],
                        "app_id":            conv["app_id"],
                        "turn_id":           turn["turn_id"],
                        "routing_label":     current_label,
                        "query":             current_query,
                        "relevant_sections": turn.get("relevant_sections", []),
                        "ground_truth":      current_answer,
                        "history":           history_text,
                        "query_quality":     turn.get("query_quality", None),
                        "isfollow_up":      bool(turn.get("isfollow_up", False)),
                    })

                if current_label != "ood":
                    prev_turn_data = {"query": current_query, "answer": current_answer}
                else:
                    prev_turn_data = None

    return all_turns


@functools.lru_cache(maxsize=128)
def _load_app_sections(app_path: str) -> List[Dict]:
    with open(app_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_section_text(apps_dir: str, app_id: str, section_id: str) -> str:
    app_path = os.path.join(apps_dir, f"{app_id}.json")
    if not os.path.exists(app_path):
        return ""
    for sec in _load_app_sections(app_path):
        if str(sec.get("section_id")) == str(section_id):
            source_type = sec.get("source_type", "manuel")
            if source_type == "faq":
                return sec.get("full_text", sec.get("answer", ""))
            breadcrumb = sec.get("breadcrumb", "")
            content    = sec.get("content", "")
            return f"{breadcrumb} : {content}".strip()
    return ""


def build_context(turn: Dict, apps_dir: str) -> str:
    contexts = []
    missing  = []
    for sec_id in turn["relevant_sections"]:
        text = load_section_text(apps_dir, turn["app_id"], sec_id)
        if text:
            contexts.append(text)
        else:
            missing.append(sec_id)
    if missing:
        print(f"[WARN] Missing sections for turn {turn['turn_id']} (app={turn['app_id']}): {missing}")
    if not contexts:
        return ""
    return "\n\n---\n\n".join(contexts)


def build_messages(query: str, context: str, history: str, system_prompt_template: str) -> List[Dict]:
    system_content = system_prompt_template.format(
        history=history or "",
        context=context,
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": query},
    ]


def load_model(model_name: str, model_kwargs: Dict) -> Tuple:
    if "torch_dtype" in model_kwargs:
        dtype_str = model_kwargs["torch_dtype"]
        model_kwargs["torch_dtype"] = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
        }.get(dtype_str, torch.float32)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    return tokenizer, model


class FirstTokenTimeCriteria(StoppingCriteria):
    def __init__(self, prompt_len: int):
        self.prompt_len       = prompt_len
        self.first_token_time = None
        self.generation_start = None

    def set_generation_start(self, start_time: float):
        self.generation_start = start_time

    def __call__(self, input_ids, scores, **kwargs):
        if self.first_token_time is None and input_ids.shape[1] > self.prompt_len:
            self.first_token_time = time.time()
        return False


def generate_answer(
    tokenizer,
    model,
    messages: List[Dict],
    generation_kwargs: Dict,
    max_model_len: int,
    chat_template_kwargs: Optional[Dict] = None,
) -> Tuple[str, float, float]:
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        **chat_template_kwargs or {}
    )

    inputs    = tokenizer(prompt, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    if input_len > max_model_len:
        print(f"[WARN] Prompt length ({input_len} tokens) exceeds model max ({max_model_len}). Truncating.")
        inputs    = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_model_len).to(model.device)
        input_len = inputs["input_ids"].shape[1]

    criteria = FirstTokenTimeCriteria(prompt_len=input_len)
    criteria.set_generation_start(time.time())

    local_kwargs = {**generation_kwargs, "stopping_criteria": StoppingCriteriaList([criteria])}

    start_total = time.time()
    outputs     = model.generate(**inputs, **local_kwargs)
    total_time  = time.time() - start_total

    ttft = (criteria.first_token_time - criteria.generation_start
            if criteria.first_token_time is not None else total_time)

    answer = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
    return answer, total_time, ttft


def load_existing_results(rag_out_path: str) -> Tuple[set, List[Dict]]:
    processed_ids: set      = set()

    if not os.path.exists(rag_out_path):
        return processed_ids

    with open(rag_out_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = f"{rec['conversation_id']}_{rec['turn_id']}"
                processed_ids.add(key)
            except (json.JSONDecodeError, KeyError):
                continue

    return processed_ids


def load_existing_ood_ids(ood_path: str) -> set:
    processed_ids: set = set()
    if not os.path.exists(ood_path):
        return processed_ids
    with open(ood_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = f"{rec['conversation_id']}_{rec['turn_id']}"
                processed_ids.add(key)
            except (json.JSONDecodeError, KeyError):
                continue
    return processed_ids


def run_generation(config: Dict, turns: List[Dict], apps_dir: str, output_dir: str):
    config_id = config["id"]
    print(f"\n{'='*60}")
    print(f"Config: {config_id}")
    print(f"Model:  {config['model_name']}")
    print(f"{'='*60}")

    prompt_template  = load_prompt(config["prompt_file"])
    tokenizer, model = load_model(config["model_name"], config.get("model_kwargs", {}))
    max_model_len    = getattr(model.config, "max_position_embeddings", 2048)

    generation_kwargs = config.get("generation_kwargs", {}).copy()
    generation_kwargs.setdefault("pad_token_id", tokenizer.eos_token_id)
    generation_kwargs.setdefault("eos_token_id", tokenizer.eos_token_id)

    chat_template_kwargs = config.get("chat_template_kwargs", {})

    out_dir      = os.path.join(output_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    rag_out_path = os.path.join(out_dir, f"{config_id}.jsonl")
    ood_out_path = os.path.join(out_dir, f"{config_id}_ood.jsonl")

    processed_rag_ids = load_existing_results(rag_out_path)
    processed_ood_ids = load_existing_ood_ids(ood_out_path)
    processed_ids     = processed_rag_ids | processed_ood_ids

    if processed_ids:
        print(f"Resuming: {len(processed_ids)} turns already processed.")

    rag_turns    = [t for t in turns if t["routing_label"] == "rag"]
    ood_turns    = [t for t in turns if t["routing_label"] == "ood"]
    failed_count = 0

    with (
        open(rag_out_path, "a", encoding="utf-8") as rag_file,
        open(ood_out_path, "a", encoding="utf-8") as ood_file,
    ):
        for turn in tqdm(turns, desc=f"Generating ({config_id})", unit="turn"):
            turn_key = f"{turn['conversation_id']}_{turn['turn_id']}"
            if turn_key in processed_ids:
                continue

            tqdm.write(f"Processing {turn_key} [{turn['routing_label']}]...")

            context  = build_context(turn, apps_dir)
            messages = build_messages(turn["query"], context, turn["history"], prompt_template)

            failed     = False
            generated  = ""
            total_time = 0.0
            ttft       = 0.0
            try:
                generated, total_time, ttft = generate_answer(
                    tokenizer, model, messages, generation_kwargs, max_model_len, chat_template_kwargs
                )
                tqdm.write(f"  -> Generated in {total_time:.2f}s (TTFT: {ttft:.2f}s)")
            except Exception as e:
                generated = f"[ERROR: {e}]"
                failed    = True
                tqdm.write(f"  -> FAILED: {e}")
                failed_count += 1

            record = {
                "conversation_id":     turn["conversation_id"],
                "turn_id":             turn["turn_id"],
                "routing_label":       turn["routing_label"],
                "query":               turn["query"],
                "query_quality":       turn["query_quality"],
                "isfollow_up":        turn["isfollow_up"],
                "ground_truth":        turn["ground_truth"],
                "generated":           generated,
                "context_sections":    turn["relevant_sections"],
                "history":             turn["history"],
                "config_id":           config_id,
                "prompt_file":         config.get("prompt_file"),
                "generation_time_sec": round(total_time, 4) if not failed else None,
                "ttft_sec":            round(ttft, 4)       if not failed else None,
                "failed":              failed,
            }

            if turn["routing_label"] == "rag":
                rag_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                rag_file.flush()
            else:
                ood_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                ood_file.flush()

    print(f"\n{'─'*60}")
    print(f"Config {config_id} finished.")
    print(f"  RAG turns : {len(rag_turns)}  |  OOD turns: {len(ood_turns)}")
    print(f"  Failed    : {failed_count}")
    print(f"  RAG outputs saved to: {rag_out_path}")
    print(f"  OOD outputs saved to: {ood_out_path}")
    print(f"{'─'*60}")

    del model
    torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description="Generation for RAG pipeline")
    parser.add_argument("--config",        type=str, default="configs.yaml")
    parser.add_argument("--config-id",     type=str, default=None)
    parser.add_argument("--conversations", type=str, required=True)
    parser.add_argument("--apps-dir",      type=str, required=True)
    parser.add_argument("--output-dir",    type=str, default="outputs")
    args = parser.parse_args()

    all_configs = load_configs(args.config)
    if args.config_id:
        all_configs = [c for c in all_configs if c["id"] == args.config_id]
        if not all_configs:
            raise ValueError(f"Config ID '{args.config_id}' not found")

    turns     = load_conversations_with_history(args.conversations)
    rag_count = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count = sum(1 for t in turns if t["routing_label"] == "ood")
    print(f"Loaded {len(turns)} turns — RAG: {rag_count}, OOD: {ood_count}")

    for cfg in all_configs:
        run_generation(cfg, turns, args.apps_dir, args.output_dir)

    print("\nAll configs processed. Done.")


if __name__ == "__main__":
    main()