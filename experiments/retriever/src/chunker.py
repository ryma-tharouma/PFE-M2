# src/chunker.py
import math
from typing import List, Dict, Any
from transformers import AutoTokenizer

class AdaptiveChunker:
    """
    Splits sections into chunks based on token limits.
    Strategy: 'adaptive' → embed full section if ≤8192 tokens, else split with overlap.
    Maintains parent_section_id for post-retrieval aggregation.
    """
    def __init__(self, cfg: dict):
        self.max_tokens = cfg.get("chunking", {}).get("max_tokens", 8192)
        self.overlap = cfg.get("chunking", {}).get("overlap_tokens", 0)
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        
        # Ensure overlap doesn't exceed chunk size
        if self.overlap >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens")

    def process_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converts raw section dicts into chunk records ready for embedding.
        Returns list of dicts with identical metadata + chunking flags.
        """
        chunked_sections = []
        
        for sec in sections:
            content = str(sec.get("content", "")).strip()
            breadcrumb = str(sec.get("breadcrumb", "")).strip()
            sec_id = str(sec.get("section_id", ""))
            
            # Prepare full text for tokenization
            full_text = f"{breadcrumb} {content}".strip()
            tokens = self.tokenizer.encode(full_text, add_special_tokens=False)
            
            if len(tokens) <= self.max_tokens:
                # Fits entirely: keep as single unit
                chunk = sec.copy()
                chunk["embed_text"] = full_text
                chunk["parent_section_id"] = sec_id
                chunk["is_chunk"] = False
                chunk["chunk_index"] = 0
                chunked_sections.append(chunk)
            else:
                # Split with stride
                stride = self.max_tokens - self.overlap
                for start_idx in range(0, len(tokens), stride):
                    chunk_tokens = tokens[start_idx : start_idx + self.max_tokens]
                    chunk_text = self.tokenizer.decode(chunk_tokens)
                    
                    chunk = sec.copy()
                    chunk["embed_text"] = chunk_text.strip()
                    chunk["parent_section_id"] = sec_id
                    chunk["is_chunk"] = True
                    chunk["chunk_index"] = start_idx // stride
                    chunked_sections.append(chunk)
                    
        return chunked_sections