# src/chunker.py
import math
from typing import List, Dict, Any
from transformers import AutoTokenizer

class AdaptiveChunker:
    """
    Splits sections into chunks based on token limits.
    Supports different embedding text per source_type:
    - "manuel" (or default): title + breadcrumb + content
    - "faq": problem field only
    """
    def __init__(self, cfg: dict):
        self.max_tokens = cfg.get("chunking", {}).get("max_tokens", 8000)
        self.overlap = cfg.get("chunking", {}).get("overlap_tokens", 0)
        
        # Load tokenizer once (could be made class-level cache, but fine here)
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        
        if self.overlap >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens")
        if self.overlap < 0:
            raise ValueError("overlap_tokens must be >= 0")

    def _build_embed_text(self, sec: Dict[str, Any]) -> str:
        """Construct the text to be embedded based on source_type."""
        source_type = sec.get("source_type", "")
        
        if source_type == "faq":
            # FAQ: embed only the problem field
            problem = str(sec.get("problem", "")).strip()
            return problem
        else:
            # Manual / default: embed title + breadcrumb + content
            title = str(sec.get("title", "")).strip()
            breadcrumb = str(sec.get("breadcrumb", "")).strip()
            content = str(sec.get("content", "")).strip()
            # Join with spaces, avoid multiple spaces if some fields empty
            parts = [p for p in [title, breadcrumb, content] if p]
            return " ".join(parts)

    def process_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converts raw section dicts into chunk records ready for embedding.
        Returns list of dicts with original metadata + chunking flags.
        """
        chunked_sections = []
        
        for sec in sections:
            embed_text = self._build_embed_text(sec)
            if not embed_text:
                embed_text = "" 
                print(f"⚠️ Warning: Section {sec.get('section_id', '')} has no text to embed after processing.")
                pass
            
            tokens = self.tokenizer.encode(embed_text, add_special_tokens=False)
            sec_id = str(sec.get("section_id", ""))
            
            if len(tokens) <= self.max_tokens:
                chunk = sec.copy()
                chunk["embed_text"] = embed_text
                chunk["parent_section_id"] = sec_id
                chunk["is_chunk"] = False
                chunk["chunk_index"] = 0
                chunk["id"] = sec.get("id", sec_id)
                chunked_sections.append(chunk)
            else:
                stride = self.max_tokens - self.overlap
                chunk_index = 0
                for start_idx in range(0, len(tokens), stride):
                    chunk_tokens = tokens[start_idx : start_idx + self.max_tokens]
                    chunk_text = self.tokenizer.decode(chunk_tokens)
                    
                    chunk = sec.copy()
                    chunk["embed_text"] = chunk_text.strip()
                    chunk["parent_section_id"] = sec_id
                    chunk["is_chunk"] = True
                    chunk["chunk_index"] = chunk_index
                    chunk["id"] = f"{sec_id}_c{chunk_index}"
                    chunked_sections.append(chunk)
                    chunk_index += 1
                    
        return chunked_sections