#!/usr/bin/env python
"""
debug_qwen.py — Debug Qwen GGUF with thinking mode for specific failing turns.
Writes output incrementally turn by turn.
"""

import os
import json
import time
import argparse
from typing import List, Dict, Tuple
from tqdm import tqdm

# Specific turns to debug (from error analysis)
# Format: conversation_id_turn_id (turn_id is integer)
SPECIFIC_TURNS = [
    "conv_2_13",   # "jai choisis le mauvais véhicule" - Refus de répondre
    "conv_4_3",    # "tjrs le mm prblm" - Refus (référence contextuelle)
    "conv_5_11",   # "ajouter plusieurs photos ?" - Refus (prudence excessive)
    "conv_6_8",    # "import chauffeurs même manière?" - A dit NON alors que OUI
    "conv_7_6",    # "c'est quoi Compte analytique ?" - Refus
    "conv_9_6",    # "je veux aussi pour categorie" - Contexte non actualisé
    "conv_9_12",   # "est ce que cbn" - Question inintelligible
    "conv_11_9",   # "comment vérifier que l'élément est bien ajouté" - Réponse trop complexe
    "conv_12_12",  # "zéros téléphone disparaissent" - Refus (info disponible)
    "conv_13_9",   # "alternative à désunir cellules fusionnées" - A donné la solution à éviter
    "conv_14_10",  # "OneDrive - partage sans connexion" - Réponse incomplète
]

# Mapping for easier reference
TURN_DESCRIPTIONS = {
    "conv_2_13": "jai choisis le mauvais véhicule - Refus de répondre",
    "conv_4_3": "tjrs le mm prblm - Refus (référence contextuelle)",
    "conv_5_11": "ajouter plusieurs photos ? - Refus (prudence excessive)",
    "conv_6_8": "import chauffeurs même manière? - A dit NON alors que OUI",
    "conv_7_6": "c'est quoi Compte analytique ? - Refus",
    "conv_9_6": "je veux aussi pour categorie - Contexte non actualisé",
    "conv_9_12": "est ce que cbn - Question inintelligible",
    "conv_11_9": "comment vérifier que l'élément est bien ajouté - Réponse trop complexe",
    "conv_12_12": "zéros téléphone disparaissent - Refus (info disponible)",
    "conv_13_9": "alternative à désunir cellules fusionnées - A donné la solution à éviter",
    "conv_14_10": "OneDrive - partage sans connexion - Réponse incomplète",
}

# Qwen 3.5 4B GGUF config
CONFIG = {
    "id": "qwen3.5_4b_gguf_original_l2_prompt2",
    "gguf_path": "models/Qwen3.5-4B-Q4_K_S.gguf",
    "prompt_file": "prompts/prompt_2_think.txt",
    "n_ctx": 16384,
    "n_gpu_layers": 0,
    "generation_kwargs": {
        "max_tokens": 2048,
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "repeat_penalty": 1.1,
    }
}


# ══════════════════════════════════════════════════════════════════════════════
# Config loading
# ══════════════════════════════════════════════════════════════════════════════

def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_resolved_turns(turns_path: str) -> Dict[str, Dict]:
    """Load turns and index by conversation_id_turn_id"""
    turns_dict = {}
    with open(turns_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                turn = json.loads(line)
                # Create key: conv_X_Y where Y is turn_id (integer)
                key = f"{turn['conversation_id']}_{turn['turn_id']}"
                turns_dict[key] = turn
    return turns_dict


# ══════════════════════════════════════════════════════════════════════════════
# Qwen GGUF with thinking mode
# ══════════════════════════════════════════════════════════════════════════════

def _build_qwen_prompt(system_msg: str, user_msg: str) -> str:
    """Build Qwen prompt that keeps thinking mode enabled"""
    return (
        f"<|im_start|>system\n{system_msg}<|im_end|>\n"
        f"<|im_start|>user\n{user_msg}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def load_gguf_model(config: Dict):
    from llama_cpp import Llama
    
    return Llama(
        model_path=config["gguf_path"],
        n_ctx=config.get("n_ctx", 16384),
        n_threads=config.get("n_threads", 8),
        n_batch=config.get("n_batch", 512),
        n_gpu_layers=config.get("n_gpu_layers", 0),
        mmap=True,
        chat_template_kwargs={"enable_thinking": True}
    )


def generate_qwen_gguf(
    model, system_msg: str, user_msg: str, generation_kwargs: Dict,
) -> Tuple[str, float, float]:
    """Generate with Qwen GGUF, preserving thinking output"""
    
    prompt = _build_qwen_prompt(system_msg, user_msg)
    
    kwargs = {
        "max_tokens": 2048,
        "temperature": 1.0,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "repeat_penalty": 1.1,
        "stream": True,
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
# Incremental Markdown Writer
# ══════════════════════════════════════════════════════════════════════════════

class IncrementalMarkdownWriter:
    """Writes markdown incrementally, flushing after each turn"""
    
    def __init__(self, output_path: str):
        self.output_path = output_path
        self.turn_count = 0
        self._write_header()
    
    def _write_header(self):
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write("# Qwen GGUF Debug - Thinking Mode Analysis\n\n")
            f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Model:** Qwen3.5-4B-Q4_K_S.gguf\n\n")
            f.write(f"**Config:** qwen3.5_4b_gguf_original_l2_prompt2\n\n")
            f.write("## Debug Targets (11 failing cases)\n\n")
            f.write("| Turn | Error Type | Query |\n")
            f.write("|------|------------|-------|\n")
    
    def add_summary_row(self, turn_key: str, error_type: str, query_preview: str):
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(f"| {turn_key} | {error_type} | {query_preview} |\n")
    
    def add_turn(self, turn: Dict, turn_num: int):
        self.turn_count += 1
        key = f"{turn['conversation_id']}_{turn['turn_id']}"
        desc = TURN_DESCRIPTIONS.get(key, "Unknown")
        error_type = desc.split(" - ")[1] if " - " in desc else desc
        
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(f"\n---\n\n")
            f.write(f"## Turn {turn_num}: {key}\n\n")
            f.write(f"**Error Type:** `{error_type}`\n\n")
            f.write(f"**Query Quality:** {turn.get('query_quality', 'N/A')}\n\n")
            f.write(f"**Is Follow-up:** {turn.get('isfollow_up', False)}\n\n")
            
            # Original query
            f.write("### 📝 Original Query\n\n")
            f.write(f"```\n{turn['query']}\n```\n\n")
            
            # Conversation history (if any)
            if turn.get('history'):
                f.write("### 📜 Conversation History\n\n")
                f.write(f"```\n{turn['history']}\n```\n\n")
            
            # Retrieved context
            f.write("### 📚 Retrieved Context\n\n")
            f.write(f"```\n{turn.get('context', 'N/A')}\n```\n\n")
            
            # Context sections info
            if turn.get('context_sections'):
                f.write("**Context Sections:** " + ", ".join(turn['context_sections']) + "\n\n")
            
            # Ground truth (expected answer)
            f.write("### ✅ Expected Answer (Ground Truth)\n\n")
            f.write(f"```\n{turn['ground_truth']}\n```\n\n")
            
            # THINKING PROCESS
            f.write("### 🤔 Qwen Thinking Process\n\n")
            if turn.get('thinking'):
                f.write("```\n")
                f.write(turn['thinking'])
                f.write("\n```\n\n")
            else:
                f.write("*No explicit thinking tags found - showing beginning of response as reasoning:*\n\n")
                preview = turn['answer'][:500] if len(turn['answer']) > 500 else turn['answer']
                f.write(f"```\n{preview}\n```\n\n")
            
            # Final answer
            f.write("### 💬 Qwen Final Answer\n\n")
            f.write(f"```\n{turn['answer']}\n```\n\n")
            
            # Analysis section
            f.write("### 🔍 Error Analysis\n\n")
            f.write("<details>\n<summary>Click to see detailed analysis</summary>\n\n")
            f.write("**What went wrong:**\n")
            f.write(f"- {error_type}\n\n")
            f.write("**Observation:**\n")
            f.write("- Compare thinking process with expected answer\n")
            f.write("- Check if context was properly utilized\n")
            f.write("- Verify if reasoning matches ground truth\n\n")
            f.write("**Root cause:**\n")
            f.write("- To be determined after analysis\n\n")
            f.write("**Suggested fix:**\n")
            f.write("- To be determined after analysis\n\n")
            f.write("</details>\n\n")
            
            # Raw output
            f.write("### 📄 Raw Model Output\n\n")
            f.write("<details>\n<summary>Click to see raw output</summary>\n\n")
            f.write(f"```\n{turn['full_response']}\n```\n\n")
            f.write("</details>\n\n")
            
            # Metrics
            f.write("### ⏱️ Performance\n\n")
            f.write(f"- **Total time:** {turn.get('generation_time_sec', 'N/A')}s\n")
            f.write(f"- **Time to first token:** {turn.get('ttft_sec', 'N/A')}s\n")
            f.write(f"- **Failed:** {turn.get('failed', False)}\n\n")
        
        # Flush to disk immediately
        if hasattr(self, '_flush'):
            pass  # File already flushed with each write
    
    def finish(self):
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write("\n---\n\n")
            f.write("## Summary\n\n")
            f.write(f"**Total turns processed:** {self.turn_count}\n")


class IncrementalJSONWriter:
    """Writes JSON incrementally, appending each turn"""
    
    def __init__(self, output_path: str):
        self.output_path = output_path
        # Initialize as empty list in JSON
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("[\n")
        self.first_turn = True
    
    def add_turn(self, turn: Dict):
        with open(self.output_path, "a", encoding="utf-8") as f:
            if not self.first_turn:
                f.write(",\n")
            json.dump(turn, f, ensure_ascii=False, indent=2)
            self.first_turn = False
            f.flush()
    
    def finish(self):
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write("\n]\n")


# ══════════════════════════════════════════════════════════════════════════════
# Main debug loop
# ══════════════════════════════════════════════════════════════════════════════

def run_debug(config: Dict, turns_dict: Dict[str, Dict], output_dir: str):
    config_id = config["id"]
    
    print(f"\n{'='*60}")
    print(f"🐧 Qwen GGUF Debug Mode - Analyzing {len(SPECIFIC_TURNS)} failing cases")
    print(f"Config: {config_id}")
    print(f"Model: {config['gguf_path']}")
    print(f"{'='*60}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize incremental writers
    markdown_writer = IncrementalMarkdownWriter(os.path.join(output_dir, "debug_qwen.md"))
    json_writer = IncrementalJSONWriter(os.path.join(output_dir, "debug_qwen_data.json"))
    
    # Load prompt template
    print(f"Loading prompt from: {config['prompt_file']}")
    prompt_template = load_prompt(config["prompt_file"])
    print(f"Prompt length: {len(prompt_template)} characters")
    
    # Load model once
    print("Loading model...")
    model = load_gguf_model(config)
    generation_kwargs = config.get("generation_kwargs", {})
    print("Model loaded.\n")
    
    # First, add summary rows for all available turns
    print("Adding summary table...")
    for turn_key in SPECIFIC_TURNS:
        if turn_key in turns_dict:
            turn = turns_dict[turn_key]
            desc = TURN_DESCRIPTIONS.get(turn_key, "Unknown")
            error_type = desc.split(" - ")[1] if " - " in desc else desc
            query_preview = turn['query'][:50] + "..." if len(turn['query']) > 50 else turn['query']
            markdown_writer.add_summary_row(turn_key, error_type, query_preview)
    
    # Process turns one by one
    debug_turns = []
    turn_num = 0
    
    for turn_key in SPECIFIC_TURNS:
        if turn_key not in turns_dict:
            print(f"⚠️  Turn {turn_key} not found in resolved turns file!")
            continue
        
        turn_num += 1
        turn = turns_dict[turn_key]
        desc = TURN_DESCRIPTIONS.get(turn_key, "Unknown")
        error_type = desc.split(" - ")[1] if " - " in desc else desc
        
        print(f"\n{'─'*50}")
        print(f"📝 Turn {turn_num}/11: {turn_key}")
        print(f"   Error: {error_type}")
        print(f"   Query: {turn['query'][:80]}...")
        print(f"   Query Quality: {turn.get('query_quality', 'N/A')}")
        print(f"   Is Follow-up: {turn.get('isfollow_up', False)}")
        
        # Build messages
        context = turn.get("context", "")
        history = turn.get("history", "")
        system_msg = prompt_template.format(history=history or "", context=context)
        user_msg = turn["query"]
        
        # Generate
        full_response, total_time, ttft = "", 0.0, 0.0
        failed = False
        
        try:
            print("   Generating...")
            full_response, total_time, ttft = generate_qwen_gguf(
                model, system_msg, user_msg, generation_kwargs
            )
            
            # Extract thinking and answer
            thinking = ""
            answer = full_response
            
            # Try to extract thinking if it exists
            lines = full_response.split('\n')
            if len(lines) > 2:
                first_para = lines[0].strip()
                if any(word in first_para.lower() for word in ['think', 'reason', 'because', 'since', 'based on']):
                    answer_start = 1
                    for i, line in enumerate(lines[1:], 1):
                        if len(line.strip()) > 20 and not line.strip().startswith(('```', '#')):
                            answer_start = i
                            break
                    thinking = '\n'.join(lines[:answer_start]).strip()
                    answer = '\n'.join(lines[answer_start:]).strip()
            
            # Look for explicit thinking tags
            if "<|im_start|>think" in full_response:
                start = full_response.find("<|im_start|>think")
                end = full_response.find("<|im_end|>", start)
                if end != -1:
                    thinking = full_response[start:end].replace("<|im_start|>think", "").strip()
                    answer = full_response.replace(f"<|im_start|>think{thinking}<|im_end|>", "").strip()
            
            print(f"   ✅ Generated in {total_time:.2f}s | TTFT {ttft:.2f}s")
            if thinking:
                preview = thinking[:150].replace('\n', ' ')
                print(f"   💭 Thinking: {preview}...")
            else:
                print(f"   💭 No explicit reasoning detected")
            print(f"   💬 Answer: {answer[:100]}...")
                
        except Exception as exc:
            full_response = f"[ERROR: {exc}]"
            thinking = ""
            answer = f"[ERROR: {exc}]"
            failed = True
            print(f"   ❌ FAILED: {exc}")
        
        # Create turn data
        turn_data = {
            "conversation_id": turn["conversation_id"],
            "app_id": turn.get("app_id", ""),
            "turn_id": turn["turn_id"],
            "routing_label": turn.get("routing_label", "rag"),
            "query_quality": turn.get("query_quality"),
            "isfollow_up": turn.get("isfollow_up", False),
            "query": turn["query"],
            "history": history,
            "context": context,
            "context_sections": turn.get("context_sections", []),
            "missing_sections": turn.get("missing_sections", []),
            "ground_truth": turn.get("ground_truth", ""),
            "full_response": full_response,
            "thinking": thinking,
            "answer": answer,
            "generation_time_sec": round(total_time, 4) if not failed else None,
            "ttft_sec": round(ttft, 4) if not failed else None,
            "failed": failed,
            "error_type": error_type,
        }
        
        debug_turns.append(turn_data)
        
        # Write turn immediately to both files
        print("   💾 Saving to output files...")
        markdown_writer.add_turn(turn_data, turn_num)
        json_writer.add_turn(turn_data)
        print("   💾 Saved and flushed to disk")
    
    # Finalize files
    markdown_writer.finish()
    json_writer.finish()
    
    print(f"\n{'='*60}")
    print(f"✅ Debug complete! Processed {len(debug_turns)} turns")
    print(f"📄 Markdown output: {os.path.join(output_dir, 'debug_qwen.md')}")
    print(f"📊 JSON output: {os.path.join(output_dir, 'debug_qwen_data.json')}")
    print(f"{'='*60}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Debug Qwen GGUF for specific failing turns")
    parser.add_argument("--turns", type=str, required=True, 
                        help="Resolved turns JSONL file (e.g., data/resolved_turns.jsonl)")
    parser.add_argument("--output-dir", type=str, default="outputs/debug_qwen",
                        help="Output directory (default: outputs/debug_qwen)")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"🐧 Qwen Debug Script - Incremental Output Mode")
    print(f"Model: Qwen3.5-4B-Q4_K_S.gguf")
    print(f"Config: qwen3.5_4b_gguf_original_l2_prompt2")
    print(f"{'='*60}\n")
    
    # Load all turns
    print(f"Loading turns from: {args.turns}")
    turns_dict = load_resolved_turns(args.turns)
    print(f"Loaded {len(turns_dict)} total turns")
    
    # Show sample keys for verification
    sample_keys = list(turns_dict.keys())[:5]
    print(f"Sample turn keys: {sample_keys}")
    
    # Check which specific turns are available
    available_turns = [t for t in SPECIFIC_TURNS if t in turns_dict]
    missing_turns = [t for t in SPECIFIC_TURNS if t not in turns_dict]
    
    print(f"\n🎯 Target turns: {len(SPECIFIC_TURNS)}")
    print(f"✅ Available: {len(available_turns)}")
    if missing_turns:
        print(f"⚠️ Missing: {', '.join(missing_turns)}")
        print("   (These conversations might not be in your resolved turns file)")
    
    if not available_turns:
        raise ValueError("None of the specific turns found in the resolved turns file!")
    
    # Run debug with hardcoded config
    run_debug(CONFIG, turns_dict, args.output_dir)


if __name__ == "__main__":
    main()