# src/context_manager.py
from typing import List, Dict, Optional
from transformers import AutoTokenizer

class ContextManager:
    """
    Manages conversational context for retrieval.
    Supports: none (single-turn), weighted_concat (history + current query).
    Enforces token budget with assistant-first truncation to preserve query intent.
    """
    def __init__(self, cfg: dict):
        mt_cfg = cfg.get("multi_turn", {})
        self.enabled = mt_cfg.get("enabled", False)
        self.strategy = mt_cfg.get("strategy", "none")
        self.window_size = mt_cfg.get("window_size", 2)

        trunc_cfg = mt_cfg.get("context_truncation", {})
        self.truncation_enabled = trunc_cfg.get("enabled", True)
        self.max_tokens = trunc_cfg.get("max_total_tokens", 8000)

        # Single tokenizer instance per process
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")

    def build_context(self, history: List[Dict], current_query: str, turn_id: Optional[str] = None) -> str:
        """
        Returns formatted context string ready for embedding.
        If disabled/strategy='none', returns current_query unchanged.
        """
        if not self.enabled or self.strategy == "none":
            return current_query

        if self.strategy == "weighted_concat":
            return self._build_concat(history, current_query)

        return current_query

    def _build_concat(self, history: List[Dict], current_query: str) -> str:
        # Grab last N turns
        recent = history[-self.window_size:] if self.window_size > 0 and history else []

        if not self.truncation_enabled:
            parts = [f"Utilisateur: {h.get('user_query', '')}\nAssistant: {h.get('assistant_response', '')}" for h in recent]
            parts.append(f"requete recente: {current_query}")
            return "\n---\n".join(parts)

        # Token budget enforcement
        current_toks = self.tokenizer.encode(current_query, add_special_tokens=False)
        # Reserve buffer for separators & ensure query always fits
        query_buffer = 100
        if len(current_toks) >= self.max_tokens - query_buffer:
            current_query = self.tokenizer.decode(current_toks[:self.max_tokens - query_buffer - 3]) + " [...]"
            current_toks = current_toks[:self.max_tokens - query_buffer]

        target_budget = self.max_tokens - len(current_toks) - query_buffer
        used_tokens = 0
        history_parts = []

        # Process oldest → newest to maintain chronological flow
        for turn in recent:
            u = str(turn.get("user_query", ""))
            a = str(turn.get("assistant_response", ""))

            u_toks = len(self.tokenizer.encode(u, add_special_tokens=False))
            a_toks = len(self.tokenizer.encode(a, add_special_tokens=False))

            if used_tokens + u_toks + a_toks <= target_budget:
                history_parts.append({"u": u, "a": a})
                used_tokens += u_toks + a_toks
            else:
                # Budget exceeded: truncate assistant first, then user
                remaining = target_budget - used_tokens
                if u_toks < remaining:
                    a_rem = max(0, remaining - u_toks)
                    truncated_a = self.tokenizer.decode(self.tokenizer.encode(a, add_special_tokens=False)[:a_rem]) + " [...]"
                    history_parts.append({"u": u, "a": truncated_a})
                else:
                    truncated_u = self.tokenizer.decode(self.tokenizer.encode(u, add_special_tokens=False)[:max(0, remaining)]) + " [...]"
                    history_parts.append({"u": truncated_u, "a": "[...]"})
                break  # Budget exhausted

        parts = [f"Utilisateur: {p['u']}\nAssistant: {p['a']}" for p in history_parts]
        parts.append(f"requete recente: {current_query}")
        return "\n---\n".join(parts)