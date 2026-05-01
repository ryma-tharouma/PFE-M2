#!/usr/bin/env python
"""
qwen_cache.py — Test prefix caching performance with Qwen GGUF.
Static system prompt, dynamic history/context in user message.
No thinking mode, no file output, just console timing.
"""

import os
import json
import time
import argparse
from typing import List, Dict, Tuple

# Static system prompt (no placeholders)
SYSTEM_PROMPT = """Tu es un assistant technique. Réponds en FRANÇAIS en utilisant UNIQUEMENT le contexte et l'historique.

Règles :
- Cite le contexte textuellement si possible. Pas d'introduction.
- Respecte l'ordre et toutes les étapes.
- Si l'utilisateur signale un problème (ne marche pas, erreur, mauvais choix), cherche la solution de correction dans le contexte.
- Si l'utilisateur dit "aussi" ou "pareil", vérifie le sujet actuel. Ne répète pas la réponse précédente si le contexte a changé.
- Si l'information n'est PAS dans le contexte, réponds STRICTEMENT : "Je ne peux pas répondre à cette question avec les informations disponibles." SANS ajouter d'explication ni de commentaire."""

# Model configuration (adjust paths as needed)
CONFIG = {
    "gguf_path": "models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",  
    "n_ctx": 16384,
    "n_gpu_layers": 0,        # set >0 for GPU offload
    "n_threads": 4,
    "n_batch": 1024,
    "generation_kwargs": {
        "max_tokens": 1024,     # short generation for speed test
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
    }
}

def load_resolved_turns(turns_path: str) -> List[Dict]:
    """Load first N turns from JSONL."""
    turns = []
    with open(turns_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 4:  # only first 4 turns
                break
            line = line.strip()
            if line:
                turns.append(json.loads(line))
    return turns

def load_gguf_model(config: Dict):
    from llama_cpp import Llama
    return Llama(
        model_path=config["gguf_path"],
        n_ctx=config.get("n_ctx", 16384),
        n_threads=config.get("n_threads", 4),
        n_batch=config.get("n_batch", 1024),
        n_gpu_layers=config.get("n_gpu_layers", 0),
        mmap=True,
        verbose=True,   # enables detailed timing logs from llama.cpp
    )

def build_prompt(history: str, context: str, user_query: str) -> str:
    """Static system + dynamic user message (history+context+query). No thinking tags."""
    user_content = f"Historique : {history}\n\nContexte : {context}\n\nQuestion : {user_query}"
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

def generate(model, prompt: str, gen_kwargs: Dict) -> Tuple[str, float, float]:
    """Stream generation, return (text, total_time, ttft)."""
    kwargs = {
        "max_tokens": 1024,
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "stream": True,
        **gen_kwargs,
    }
    start = time.time()
    ttft = None
    tokens = []
    for chunk in model(prompt, **kwargs):
        tok = chunk["choices"][0]["text"]
        if tok:
            if ttft is None:
                ttft = time.time() - start
            tokens.append(tok)
    total = time.time() - start
    return "".join(tokens).strip(), total, ttft

def main():
    parser = argparse.ArgumentParser(description="Test prefix caching with Qwen GGUF")
    parser.add_argument("--turns", required=True, help="Resolved turns JSONL file")
    args = parser.parse_args()

    print("="*60)
    print("Qwen Prefix Caching Performance Test")
    print(f"Model: {CONFIG['gguf_path']}")
    print("="*60)

    # Load first 4 turns
    turns = load_resolved_turns(args.turns)
    if len(turns) < 4:
        print(f"Warning: only {len(turns)} turns found, using them all.")
    
    print(f"\nLoaded {len(turns)} turns.\n")
    
    # Load model (verbose enabled)
    print("Loading model...")
    model = load_gguf_model(CONFIG)
    gen_kwargs = CONFIG.get("generation_kwargs", {})
    print("Model ready.\n")

    # Process each turn
    for idx, turn in enumerate(turns, 1):
        conv_id = turn.get("conversation_id", "?")
        turn_id = turn.get("turn_id", "?")
        history = turn.get("history", "")
        context = turn.get("context", "")
        query = turn.get("query", "")
        
        print(f"\n--- Turn {idx}: {conv_id}_{turn_id} ---")
        print(f"Query: {query[:80]}...")
        print(f"History length: {len(history)} chars")
        print(f"Context length: {len(context)} chars")
        
        prompt = build_prompt(history, context, query)
        # Rough token estimate
        print(f"Total prompt chars: {len(prompt)} (~{len(prompt)//4} tokens)")
        
        print("Generating... (verbose timing from llama.cpp follows)")
        response, total_time, ttft = generate(model, prompt, gen_kwargs)
        
        print(f"\n--- Performance ---")
        print(f"Time to first token (TTFT): {ttft:.3f}s")
        print(f"Total generation time: {total_time:.3f}s")
        print(f"Output length: {len(response)} chars")
        print(f"Response preview: {response[:150]}...")
        print("-"*40)

    print("\nAll turns processed. Check llama.cpp logs above for prompt eval times and cache info.")

if __name__ == "__main__":
    main()