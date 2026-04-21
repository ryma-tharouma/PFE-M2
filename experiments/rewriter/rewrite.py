#!/usr/bin/env python
import os
import json
import argparse
import time
import torch
from typing import Optional
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm


# ----------------------------------------------------------------------
# Model loading
# ----------------------------------------------------------------------

def load_model(model_name: str, device: str = "auto"):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device,
    )
    model.eval()
    return tokenizer, model


# ----------------------------------------------------------------------
# Rewrite logic
# ----------------------------------------------------------------------

REWRITE_SYSTEM_PROMPT = """Reformule la question actuelle pour qu'elle soit autonome, sauf si elle l'est déjà. Conserve les formules (code, maths). Réponds uniquement avec la question reformulée."""

def build_rewrite_messages(prev_query: str, current_query: str):
    user_content = f"Question précédente: {prev_query}\nQuestion actuelle: {current_query}\nQuestion reformulée:"
    return [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


def rewrite_query(
    tokenizer,
    model,
    prev_query: str,
    current_query: str,
    max_new_tokens: int = 128,
) -> tuple[str, float]:
    messages = build_rewrite_messages(prev_query, current_query)

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    inputs    = tokenizer(prompt, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    start = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.time() - start

    rewritten = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
    return rewritten, elapsed


# ----------------------------------------------------------------------
# Resume helpers
# ----------------------------------------------------------------------

def load_existing_output(output_path: str) -> set:
    """Return set of already rewritten conversation IDs."""
    done = set()
    if not os.path.exists(output_path):
        return done
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                conv = json.loads(line)
                done.add(conv["conversation_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def load_existing_timings(timings_path: str) -> list:
    if not os.path.exists(timings_path):
        return []
    with open(timings_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


# ----------------------------------------------------------------------
# Main rewrite loop
# ----------------------------------------------------------------------

def rewrite_conversations(
    conv_path: str,
    model_name: str,
    output_dir: str,
    device: str = "auto",
    max_new_tokens: int = 128,
):
    # Output paths
    os.makedirs(output_dir, exist_ok=True)
    safe_model_name = model_name.replace("/", "_")
    output_path  = os.path.join(output_dir, f"rewritten_{safe_model_name}.jsonl")
    timings_path = os.path.join(output_dir, f"rewrite_timings_{safe_model_name}.json")

    # Resume support
    done_ids = load_existing_output(output_path)
    timings  = load_existing_timings(timings_path)
    if done_ids:
        print(f"Resuming: {len(done_ids)} conversations already rewritten.")

    # Load all conversations
    conversations = []
    with open(conv_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                conversations.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"Loaded {len(conversations)} conversations.")

    # Load model
    print(f"Loading model: {model_name}")
    tokenizer, model = load_model(model_name, device)
    print("Model loaded.")

    with open(output_path, "a", encoding="utf-8") as out_f:
        for conv in tqdm(conversations, desc="Rewriting", unit="conv"):
            conv_id = conv["conversation_id"]

            if conv_id in done_ids:
                continue

            # Deep copy so we don't mutate the original
            new_conv   = json.loads(json.dumps(conv))
            prev_query = None

            for turn in new_conv["turns"]:
                current_query = turn.get("user_query", "")
                # Rewrite ALL turns EXCEPT the first one (prev_query is None)
                if prev_query is not None:
                    try:
                        rewritten, elapsed = rewrite_query(
                            tokenizer, model,
                            prev_query, current_query,
                            max_new_tokens=max_new_tokens,
                        )
                        timings.append({
                            "conversation_id": conv_id,
                            "turn_id":         turn["turn_id"],
                            "original_query":  current_query,
                            "rewritten_query": rewritten,
                            "time_sec":        round(elapsed, 4),
                        })
                        # Replace query in turn
                        turn["user_query"] = rewritten

                        tqdm.write(
                            f"  [{conv_id} t{turn['turn_id']}] "
                            f"{current_query!r} -> {rewritten!r} ({elapsed:.2f}s)"
                        )
                        # *** KEY CHANGE: Use the rewritten query as the previous query for the next turn ***
                        prev_query = rewritten
                    except Exception as e:
                        tqdm.write(f"  [WARN] Failed to rewrite turn {turn['turn_id']} in {conv_id}: {e}")
                        # On failure, fall back to original current_query for context
                        prev_query = current_query
                else:
                    # First turn: no rewrite, but set prev_query to the original query
                    prev_query = current_query

            out_f.write(json.dumps(new_conv, ensure_ascii=False) + "\n")
            out_f.flush()
            done_ids.add(conv_id)

            # Save timings after each conversation
            with open(timings_path, "w", encoding="utf-8") as tf:
                json.dump(timings, tf, indent=2, ensure_ascii=False)

    # Final timing summary
    if timings:
        times = [t["time_sec"] for t in timings]
        print(f"\nRewrite timing summary ({len(times)} rewrites):")
        print(f"  Mean : {sum(times)/len(times):.3f}s")
        print(f"  Min  : {min(times):.3f}s")
        print(f"  Max  : {max(times):.3f}s")

    print(f"\nOutput saved to : {output_path}")
    print(f"Timings saved to: {timings_path}")

    del model
    torch.cuda.empty_cache()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rewrite all but the first query, using the last rewritten query as context")
    parser.add_argument("--conv",           type=str, required=True,  help="Input conversation JSONL")
    parser.add_argument("--model",          type=str, required=True,  help="HuggingFace model name or path")
    parser.add_argument("--output-dir",     type=str, default="outputs/rewritten", help="Output directory")
    parser.add_argument("--device",         type=str, default="auto", help="Device: auto, cpu, cuda")
    parser.add_argument("--max-new-tokens", type=int, default=128,    help="Max tokens for rewritten query")
    args = parser.parse_args()

    rewrite_conversations(
        conv_path      = args.conv,
        model_name     = args.model,
        output_dir     = args.output_dir,
        device         = args.device,
        max_new_tokens = args.max_new_tokens,
    )


if __name__ == "__main__":
    main()