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
    """Legacy – kept for compatibility but not used with chat templates."""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# ----------------------------------------------------------------------
# Conversation loading
# ----------------------------------------------------------------------

def load_conversations_with_history(conv_path: str) -> List[Dict]:
    """
    Returns a list of RAG turns (routing_label == 'rag').
    History contains the previous turn's query and answer ONLY if:
      - There is a previous turn
      - That previous turn's routing_label is 'faq' or 'rag' (not 'ood')
    History format: "User: {prev_query}\\nAssistant: {prev_answer}"
    Turns without routing_label default to 'rag'.
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

                if current_label == "rag":
                    history_text = ""
                    if prev_turn_data is not None:
                        history_text = (
                            f"User: {prev_turn_data['query']}\n"
                            f"Assistant: {prev_turn_data['answer']}"
                        )
                    all_turns.append({
                        "conversation_id": conv["conversation_id"],
                        "app_id":          conv["app_id"],
                        "turn_id":         turn["turn_id"],
                        "query":           current_query,
                        "relevant_sections": turn.get("relevant_sections", []),
                        "ground_truth":    current_answer,
                        "history":         history_text,
                    })

                # OOD breaks the history chain; faq/rag carry it forward
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
    """Load the embedding text for a section (same text used during indexing)."""
    app_path = os.path.join(apps_dir, f"{app_id}.json")
    if not os.path.exists(app_path):
        return ""
    for sec in _load_app_sections(app_path):
        if str(sec.get("section_id")) == str(section_id):
            source_type = sec.get("source_type", "manuel")
            if source_type == "faq":
                return sec.get("full_text", sec.get("problem", ""))
            title      = sec.get("title", "")
            breadcrumb = sec.get("breadcrumb", "")
            content    = sec.get("content", "")
            return f"{title} {breadcrumb} {content}".strip()
    return ""


def build_context(turn: Dict, apps_dir: str) -> str:
    contexts = []
    missing = []
    for idx, sec_id in enumerate(turn["relevant_sections"], 1):
        text = load_section_text(apps_dir, turn["app_id"], sec_id)
        if text:
            contexts.append(f"[Document {idx}]\n{text}")
        else:
            missing.append(sec_id)
    if missing:
        print(f"[WARN] Missing sections for turn {turn['turn_id']} (app={turn['app_id']}): {missing}")
    if not contexts:
        return "Aucune information disponible."
    return "\n\n---\n\n".join(contexts)


def build_user_message(query: str, context: str, history: str) -> str:
    """Construct the user message that includes context, history, and query."""
    message = ""
    if history:
        message += f"Historique :\n{history}\n\n"
    message += f"Contexte documentaire :\n{context}\n\n"
    message += f"Question de l'utilisateur : {query}"
    return message


# ----------------------------------------------------------------------
# Model loading
# ----------------------------------------------------------------------

def load_model(model_name: str, model_kwargs: Dict) -> Tuple:
    # Convert dtype strings to actual torch dtypes
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
        self.prompt_len        = prompt_len
        self.first_token_time  = None
        self.generation_start  = None

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
    """
    Generate an answer using the model's chat template.
    messages: list of dicts with 'role' and 'content'.
    """
    # Apply chat template
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
    """
    Normalize text for metric calculation:
      - Remove markdown formatting and think tags
      - Lowercase
      - Replace newlines and extra spaces with single spaces
    """
    # Remove think tags and their content
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove markdown code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # Remove inline code
    text = re.sub(r'`[^`]*`', '', text)
    # Remove bold and italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Lowercase everything
    text = text.lower()
    # Collapse all whitespace (including newlines) to single spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

_bleu      = load_metric("bleu")
_rouge     = load_metric("rouge")
_bertscore = load_metric("bertscore")

def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    # Clean predictions and references
    cleaned_preds = [clean_text(p) for p in predictions]
    cleaned_refs  = [clean_text(r) for r in references]

    refs_for_bleu = [[r] for r in cleaned_refs]
    bleu_score = _bleu.compute(predictions=cleaned_preds, references=refs_for_bleu)

    # Force deterministic ROUGE by disabling aggregator and manually averaging
    rouge_results = _rouge.compute(
        predictions=cleaned_preds,
        references=cleaned_refs,
        use_aggregator=False   # returns per-example scores
    )
    rougeL = sum(rouge_results["rougeL"]) / len(rouge_results["rougeL"])

    bertscore_score = _bertscore.compute(
        predictions=cleaned_preds, references=cleaned_refs, lang="fr"
    )

    return {
        "bleu":          bleu_score["bleu"],
        "rougeL":        rougeL,
        "bertscore_f1":  sum(bertscore_score["f1"]) / len(bertscore_score["f1"]),
    }


# ----------------------------------------------------------------------
# Resume helpers (extended to load timing data)
# ----------------------------------------------------------------------

def load_existing_results(out_path: str) -> Tuple[set, List[str], List[str], List[float], List[float]]:
    """
    Load already processed turn IDs, predictions, references, generation times, and TTFTs.
    Returns:
        processed_ids, predictions, references, generation_times, ttft_times
    """
    processed_ids = set()
    predictions: List[str] = []
    references:  List[str] = []
    generation_times: List[float] = []
    ttft_times: List[float] = []

    if not os.path.exists(out_path):
        return processed_ids, predictions, references, generation_times, ttft_times

    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = f"{rec['conversation_id']}_{rec['turn_id']}"
                processed_ids.add(key)
                if not rec.get("failed") and rec.get("generated") and rec.get("ground_truth"):
                    predictions.append(rec["generated"])
                    references.append(rec["ground_truth"])
                    if rec.get("generation_time_sec") is not None:
                        generation_times.append(rec["generation_time_sec"])
                    if rec.get("ttft_sec") is not None:
                        ttft_times.append(rec["ttft_sec"])
            except (json.JSONDecodeError, KeyError):
                continue

    return processed_ids, predictions, references, generation_times, ttft_times


# ----------------------------------------------------------------------
# Main generation loop
# ----------------------------------------------------------------------

def run_generation(config: Dict, turns: List[Dict], apps_dir: str, output_dir: str):
    config_id = config["id"]
    print(f"\n{'='*60}")
    print(f"Config: {config_id}")
    print(f"Model:  {config['model_name']}")
    print(f"{'='*60}")

    tokenizer, model = load_model(config["model_name"], config.get("model_kwargs", {}))
    max_model_len = getattr(model.config, "max_position_embeddings", 2048)

    generation_kwargs = config.get("generation_kwargs", {}).copy()
    generation_kwargs.setdefault("pad_token_id", tokenizer.eos_token_id)
    generation_kwargs.setdefault("eos_token_id", tokenizer.eos_token_id)

    chat_template_kwargs = config.get("chat_template_kwargs", {})

    out_dir  = os.path.join(output_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{config_id}.jsonl")

    # Load existing results including timing data
    processed_ids, predictions, references, generation_times, ttft_times = load_existing_results(out_path)

    failed_count = 0
    # Count failed turns from existing records
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("failed"):
                        failed_count += 1
                except:
                    pass

    if processed_ids:
        print(f"Resuming from previous run: {len(processed_ids)} turns already processed.")
    else:
        print("No previous results found. Starting fresh.")

    with open(out_path, "a", encoding="utf-8") as out_file:
        for turn in tqdm(turns, desc=f"Generating ({config_id})", unit="turn"):
            turn_key = f"{turn['conversation_id']}_{turn['turn_id']}"
            if turn_key in processed_ids:
                continue

            tqdm.write(f"Processing {turn_key}...")

            context = build_context(turn, apps_dir)
            user_message = build_user_message(turn["query"], context, turn["history"])

            # Build conversation messages (only user for now)
            messages = [{"role": "user", "content": user_message}]

            failed = False
            generated = ""
            total_time = 0.0
            ttft = 0.0
            try:
                generated, total_time, ttft = generate_answer(
                    tokenizer, model, messages, generation_kwargs, max_model_len, chat_template_kwargs
                )
                tqdm.write(f"  -> Generated in {total_time:.2f}s (TTFT: {ttft:.2f}s)")
            except Exception as e:
                generated = f"[ERROR: {e}]"
                failed = True
                tqdm.write(f"  -> FAILED: {e}")

            record = {
                "conversation_id":    turn["conversation_id"],
                "turn_id":            turn["turn_id"],
                "query":              turn["query"],
                "ground_truth":       turn["ground_truth"],
                "generated":          generated,
                "context_sections":   turn["relevant_sections"],
                "history":            turn["history"],
                "config_id":          config_id,
                "generation_time_sec": round(total_time, 4) if not failed else None,
                "ttft_sec":           round(ttft, 4) if not failed else None,
                "failed":             failed,
            }
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()

            if not failed:
                predictions.append(generated)
                references.append(turn["ground_truth"])
                generation_times.append(total_time)
                ttft_times.append(ttft)
            else:
                failed_count += 1

    successful_count = len(predictions)
    total_turns = len(turns)
    print(f"\n{'─'*60}")
    print(f"Config {config_id} finished.")
    print(f"  Total RAG turns: {total_turns}")
    print(f"  Successful: {successful_count}  |  Failed: {failed_count}")
    print(f"  Success rate: {successful_count/total_turns*100:.1f}%")
    print(f"{'─'*60}")

    if successful_count > 0:
        metrics = compute_metrics(predictions, references)
        metrics["total_rag_turns"] = total_turns
        metrics["successful_generations"] = successful_count
        metrics["failed_generations"] = failed_count

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

        if generation_times:
            metrics.update(_timing_stats(generation_times, "generation_time"))
        if ttft_times:
            metrics.update(_timing_stats(ttft_times, "ttft"))
    else:
        metrics = {
            "error": "No successful generations",
            "total_rag_turns": total_turns,
            "failed_generations": failed_count,
        }

    os.makedirs(os.path.join(output_dir, "metrics"), exist_ok=True)
    metrics_path = os.path.join(output_dir, "metrics", f"{config_id}.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"Metrics saved to: {metrics_path}")
    print(f"Generated outputs saved to: {out_path}")
    if successful_count > 0:
        print(f"  BLEU: {metrics.get('bleu', 0.0):.4f}")
        print(f"  RougeL: {metrics.get('rougeL', 0.0):.4f}")
        print(f"  BERTScore F1: {metrics.get('bertscore_f1', 0.0):.4f}")
        if "generation_time_mean_sec" in metrics:
            print(f"  Avg generation time: {metrics['generation_time_mean_sec']:.2f}s")
            print(f"  Avg TTFT: {metrics['ttft_mean_sec']:.2f}s")

    del model
    torch.cuda.empty_cache()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generation evaluation for RAG pipeline (RAG turns only)"
    )
    parser.add_argument("--config", type=str, default="configs.yaml",
                        help="Path to configs YAML")
    parser.add_argument("--config-id", type=str, default=None,
                        help="Run only this config ID")
    parser.add_argument("--conversations", type=str, required=True,
                        help="Path to conversations JSONL")
    parser.add_argument("--apps-dir", type=str, required=True,
                        help="Directory containing app JSON files")
    parser.add_argument("--output-dir", type=str, default="outputs",
                        help="Root output directory")
    args = parser.parse_args()

    all_configs = load_configs(args.config)
    if args.config_id:
        all_configs = [c for c in all_configs if c["id"] == args.config_id]
        if not all_configs:
            raise ValueError(f"Config ID '{args.config_id}' not found")

    turns = load_conversations_with_history(args.conversations)
    print(f"Loaded {len(turns)} RAG turns (with conversation history)")

    for cfg in all_configs:
        run_generation(cfg, turns, args.apps_dir, args.output_dir)

    print("\nAll configs processed. Done.")


if __name__ == "__main__":
    main()