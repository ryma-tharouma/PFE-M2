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
from evaluate import load as load_metric


# ----------------------------------------------------------------------
# Config / prompt loading
# ----------------------------------------------------------------------

def load_configs(config_path: str) -> List[Dict]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["configs"]


def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# ----------------------------------------------------------------------
# Conversation loading
# ----------------------------------------------------------------------

def load_conversations_with_history(conv_path: str) -> List[Dict]:
    """
    Returns ALL turns (rag + ood).
    History contains the previous turn's query and answer ONLY if:
      - There is a previous turn
      - That previous turn's routing_label is 'faq' or 'rag' (not 'ood')
    History format: "Utilisateur: {prev_query}\\nAssistant: {prev_answer}"
    OOD breaks the history chain; faq/rag carry it forward.
    Each turn includes 'routing_label', 'query_quality', and 'needs_rewrite'.
    """
    all_turns = []
    with open(conv_path, "r", encoding="utf-8") as f:
        for line in f:
            conv = json.loads(line)
            prev_turn_data = None
            for turn in conv["turns"]:
                current_label = turn.get("routing_label", "rag")
                current_query = turn.get("user_query", "")
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
                        "needs_rewrite":     bool(turn.get("rewritten_query", "")),
                    })

                if current_label != "ood":
                    prev_turn_data = {"query": current_query, "answer": current_answer}
                else:
                    prev_turn_data = None

    return all_turns


# ----------------------------------------------------------------------
# Section / context helpers
# ----------------------------------------------------------------------

@functools.lru_cache(maxsize=128)
def _load_app_sections(app_path: str) -> List[Dict]:
    with open(app_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_section_text(apps_dir: str, app_id: str, section_id: str) -> str:
    """Load the text for a section."""
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
    missing = []
    for idx, sec_id in enumerate(turn["relevant_sections"], 1):
        text = load_section_text(apps_dir, turn["app_id"], sec_id)
        if text:
            contexts.append(f"{text}")
        else:
            missing.append(sec_id)
    if missing:
        print(f"[WARN] Missing sections for turn {turn['turn_id']} (app={turn['app_id']}): {missing}")
    if not contexts:
        return ""
    return "\n\n---\n\n".join(contexts)


def build_messages(query: str, context: str, history: str, system_prompt_template: str) -> List[Dict]:
    """
    Inject context and history into the system prompt template,
    and pass the query as the user message.
    """
    system_content = system_prompt_template.format(
        history=history or "",
        context=context,
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": query},
    ]


# ----------------------------------------------------------------------
# Model loading
# ----------------------------------------------------------------------

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


# ----------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------

class FirstTokenTimeCriteria(StoppingCriteria):
    """Records wall-clock time when the first new token is generated."""

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

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    if input_len > max_model_len:
        print(f"[WARN] Prompt length ({input_len} tokens) exceeds model max ({max_model_len} tokens). Truncating.")
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_model_len,
        ).to(model.device)
        input_len = inputs["input_ids"].shape[1]

    criteria = FirstTokenTimeCriteria(prompt_len=input_len)
    criteria.set_generation_start(time.time())

    local_kwargs = {
        **generation_kwargs,
        "stopping_criteria": StoppingCriteriaList([criteria]),
    }

    start_total = time.time()
    outputs = model.generate(**inputs, **local_kwargs)
    total_time = time.time() - start_total

    ttft = (criteria.first_token_time - criteria.generation_start
            if criteria.first_token_time is not None else total_time)

    answer = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
    return answer, total_time, ttft


# ----------------------------------------------------------------------
# Text cleaning for metrics
# ----------------------------------------------------------------------

def clean_text(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

_bleu      = load_metric("bleu")
_rouge     = load_metric("rouge")
_bertscore = load_metric("bertscore")


def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    cleaned_preds = [clean_text(p) for p in predictions]
    cleaned_refs  = [clean_text(r) for r in references]

    refs_for_bleu = [[r] for r in cleaned_refs]
    bleu_score = _bleu.compute(predictions=cleaned_preds, references=refs_for_bleu)

    rouge_results = _rouge.compute(
        predictions=cleaned_preds,
        references=cleaned_refs,
        use_aggregator=False,
    )
    rougeL = sum(rouge_results["rougeL"]) / len(rouge_results["rougeL"])

    bertscore_score = _bertscore.compute(
        predictions=cleaned_preds, references=cleaned_refs, lang="fr"
    )

    return {
        "bleu":         bleu_score["bleu"],
        "rougeL":       rougeL,
        "bertscore_f1": sum(bertscore_score["f1"]) / len(bertscore_score["f1"]),
    }


def _timing_stats(times: List[float], prefix: str) -> Dict:
    if not times:
        return {}
    return {
        f"{prefix}_mean_sec": round(np.mean(times), 4),
        f"{prefix}_min_sec":  round(min(times), 4),
        f"{prefix}_max_sec":  round(max(times), 4),
        f"{prefix}_q1_sec":   round(np.percentile(times, 25), 4),
        f"{prefix}_q2_sec":   round(np.percentile(times, 50), 4),
        f"{prefix}_q3_sec":   round(np.percentile(times, 75), 4),
    }


def compute_breakdown_metrics(rag_records: List[Dict]) -> Dict:
    """
    Compute metrics grouped by query_quality and needs_rewrite.
    Each rag_record has: prediction, reference, query_quality, needs_rewrite,
                         gen_time, ttft.
    """
    def _group_metrics(records: List[Dict]) -> Dict:
        if not records:
            return {"count": 0}
        preds = [r["prediction"] for r in records]
        refs  = [r["reference"]  for r in records]
        result = compute_metrics(preds, refs)
        result["count"] = len(records)
        result.update(_timing_stats([r["gen_time"] for r in records], "generation_time"))
        result.update(_timing_stats([r["ttft"]     for r in records], "ttft"))
        return result

    # --- by_query_quality ---
    quality_groups: Dict[str, List[Dict]] = {}
    for rec in rag_records:
        key = str(rec["query_quality"]) if rec["query_quality"] is not None else "unknown"
        quality_groups.setdefault(key, []).append(rec)

    by_quality = {k: _group_metrics(v) for k, v in quality_groups.items()}

    # --- by_needs_rewrite ---
    rewrite_groups: Dict[str, List[Dict]] = {"true": [], "false": []}
    for rec in rag_records:
        rewrite_groups["true" if rec["needs_rewrite"] else "false"].append(rec)

    by_rewrite = {k: _group_metrics(v) for k, v in rewrite_groups.items()}

    return {
        "by_query_quality": by_quality,
        "by_needs_rewrite": by_rewrite,
    }


# ----------------------------------------------------------------------
# Resume helpers
# ----------------------------------------------------------------------

def load_existing_results(rag_out_path: str) -> Tuple[set, List[Dict]]:
    """
    Load already processed RAG turn IDs and their richer records
    (prediction, reference, query_quality, needs_rewrite, gen_time, ttft).
    """
    processed_ids: set      = set()
    rag_records: List[Dict] = []

    if not os.path.exists(rag_out_path):
        return processed_ids, rag_records

    with open(rag_out_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = f"{rec['conversation_id']}_{rec['turn_id']}"
                processed_ids.add(key)
                if (
                    not rec.get("failed")
                    and rec.get("generated")
                    and rec.get("ground_truth")
                    and rec.get("routing_label") == "rag"
                ):
                    rag_records.append({
                        "prediction":    rec["generated"],
                        "reference":     rec["ground_truth"],
                        "query_quality": rec.get("query_quality"),
                        "needs_rewrite": rec.get("needs_rewrite", False),
                        "gen_time":      rec.get("generation_time_sec", 0.0),
                        "ttft":          rec.get("ttft_sec", 0.0),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    return processed_ids, rag_records


def load_existing_ood_ids(ood_path: str) -> set:
    """Load already processed OOD turn IDs from the OOD output file."""
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


# ----------------------------------------------------------------------
# Main generation loop
# ----------------------------------------------------------------------

def run_generation(config: Dict, turns: List[Dict], apps_dir: str, output_dir: str):
    config_id = config["id"]
    print(f"\n{'='*60}")
    print(f"Config: {config_id}")
    print(f"Model:  {config['model_name']}")
    print(f"{'='*60}")

    prompt_template = load_prompt(config["prompt_file"])
    print(f"Using prompt file: {config['prompt_file']}")

    tokenizer, model = load_model(config["model_name"], config.get("model_kwargs", {}))
    max_model_len = getattr(model.config, "max_position_embeddings", 2048)

    generation_kwargs = config.get("generation_kwargs", {}).copy()
    generation_kwargs.setdefault("pad_token_id", tokenizer.eos_token_id)
    generation_kwargs.setdefault("eos_token_id", tokenizer.eos_token_id)

    chat_template_kwargs = config.get("chat_template_kwargs", {})

    out_dir      = os.path.join(output_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    rag_out_path = os.path.join(out_dir, f"{config_id}.jsonl")
    ood_out_path = os.path.join(out_dir, f"{config_id}_ood.jsonl")

    # Resume support
    processed_rag_ids, rag_records = load_existing_results(rag_out_path)
    processed_ood_ids              = load_existing_ood_ids(ood_out_path)
    processed_ids                  = processed_rag_ids | processed_ood_ids

    failed_count = 0
    for path in (rag_out_path, ood_out_path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        if json.loads(line).get("failed"):
                            failed_count += 1
                    except:
                        pass

    if processed_ids:
        print(f"Resuming: {len(processed_ids)} turns already processed.")
    else:
        print("No previous results found. Starting fresh.")

    rag_turns = [t for t in turns if t["routing_label"] == "rag"]
    ood_turns = [t for t in turns if t["routing_label"] == "ood"]

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

            record = {
                "conversation_id":     turn["conversation_id"],
                "turn_id":             turn["turn_id"],
                "routing_label":       turn["routing_label"],
                "query":               turn["query"],
                "query_quality":       turn["query_quality"],
                "needs_rewrite":       turn["needs_rewrite"],
                "ground_truth":        turn["ground_truth"],
                "generated":           generated,
                "context_sections":    turn["relevant_sections"],
                "history":             turn["history"],
                "config_id":           config_id,
                "prompt_file":         config.get("prompt_file"),
                "generation_time_sec": round(total_time, 4) if not failed else None,
                "ttft_sec":            round(ttft, 4) if not failed else None,
                "failed":              failed,
            }

            if turn["routing_label"] == "rag":
                rag_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                rag_file.flush()
                if not failed:
                    rag_records.append({
                        "prediction":    generated,
                        "reference":     turn["ground_truth"],
                        "query_quality": turn["query_quality"],
                        "needs_rewrite": turn["needs_rewrite"],
                        "gen_time":      total_time,
                        "ttft":          ttft,
                    })
                else:
                    failed_count += 1
            else:
                ood_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                ood_file.flush()
                if failed:
                    failed_count += 1

    # Summary
    successful_count = len(rag_records)
    total_rag        = len(rag_turns)
    total_ood        = len(ood_turns)
    print(f"\n{'─'*60}")
    print(f"Config {config_id} finished.")
    print(f"  RAG turns: {total_rag}  |  OOD turns: {total_ood}")
    print(f"  RAG successful: {successful_count}  |  Failed (all): {failed_count}")
    if total_rag:
        print(f"  RAG success rate: {successful_count / total_rag * 100:.1f}%")
    print(f"{'─'*60}")

    metrics_dir = os.path.join(output_dir, "metrics")
    os.makedirs(metrics_dir, exist_ok=True)

    # --- Overall metrics (RAG only) ---
    if successful_count > 0:
        predictions = [r["prediction"] for r in rag_records]
        references  = [r["reference"]  for r in rag_records]
        gen_times   = [r["gen_time"]   for r in rag_records]
        ttft_times  = [r["ttft"]       for r in rag_records]

        metrics = compute_metrics(predictions, references)
        metrics["total_rag_turns"]            = total_rag
        metrics["total_ood_turns"]            = total_ood
        metrics["successful_rag_generations"] = successful_count
        metrics["failed_generations"]         = failed_count
        metrics.update(_timing_stats(gen_times,  "generation_time"))
        metrics.update(_timing_stats(ttft_times, "ttft"))
    else:
        metrics = {
            "error":              "No successful RAG generations",
            "total_rag_turns":    total_rag,
            "total_ood_turns":    total_ood,
            "failed_generations": failed_count,
        }

    metrics_path = os.path.join(metrics_dir, f"{config_id}.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    # --- Breakdown metrics (by query_quality and needs_rewrite) ---
    if successful_count > 0:
        breakdown      = compute_breakdown_metrics(rag_records)
        breakdown_path = os.path.join(metrics_dir, f"{config_id}_breakdown.json")
        with open(breakdown_path, "w", encoding="utf-8") as f:
            json.dump(breakdown, f, indent=2, ensure_ascii=False)
        print(f"Breakdown metrics saved to: {breakdown_path}")

    print(f"Overall metrics saved to:  {metrics_path}")
    print(f"RAG outputs saved to:      {rag_out_path}")
    print(f"OOD outputs saved to:      {ood_out_path}")
    if successful_count > 0:
        print(f"  BLEU:          {metrics.get('bleu', 0.0):.4f}")
        print(f"  RougeL:        {metrics.get('rougeL', 0.0):.4f}")
        print(f"  BERTScore F1:  {metrics.get('bertscore_f1', 0.0):.4f}")
        if "generation_time_mean_sec" in metrics:
            print(f"  Avg gen time:  {metrics['generation_time_mean_sec']:.2f}s")
            print(f"  Avg TTFT:      {metrics['ttft_mean_sec']:.2f}s")

    del model
    torch.cuda.empty_cache()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generation evaluation for RAG pipeline"
    )
    parser.add_argument("--config",        type=str, default="configs.yaml",
                        help="Path to configs YAML")
    parser.add_argument("--config-id",     type=str, default=None,
                        help="Run only this config ID")
    parser.add_argument("--conversations", type=str, required=True,
                        help="Path to conversations JSONL")
    parser.add_argument("--apps-dir",      type=str, required=True,
                        help="Directory containing app JSON files")
    parser.add_argument("--output-dir",    type=str, default="outputs",
                        help="Root output directory")
    args = parser.parse_args()

    all_configs = load_configs(args.config)
    if args.config_id:
        all_configs = [c for c in all_configs if c["id"] == args.config_id]
        if not all_configs:
            raise ValueError(f"Config ID '{args.config_id}' not found")

    turns = load_conversations_with_history(args.conversations)
    rag_count = sum(1 for t in turns if t["routing_label"] == "rag")
    ood_count = sum(1 for t in turns if t["routing_label"] == "ood")
    print(f"Loaded {len(turns)} turns — RAG: {rag_count}, OOD: {ood_count}")

    for cfg in all_configs:
        run_generation(cfg, turns, args.apps_dir, args.output_dir)

    print("\nAll configs processed. Done.")


if __name__ == "__main__":
    main()