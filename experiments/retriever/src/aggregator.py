# src/aggregator.py
from typing import List, Dict, Any, Optional

class ChunkAggregator:
    """
    Aggregates chunk-level retrieval scores into section-level rankings.
    Supports: max, mean, rrf (Reciprocal Rank Fusion).
    Respects retrieval.max_retrieve_sections from config.
    """
    def __init__(self, cfg: dict):
        self.method = cfg.get("retrieval", {}).get("aggregation_method", "max")
        VALID_METHODS = {"max", "mean", "rrf"}
        if self.method not in VALID_METHODS:
            raise ValueError(f"Unknown aggregation method: {self.method}. Valid: {VALID_METHODS}")
        self.top_k_sections = cfg.get("retrieval", {}).get("max_retrieve_sections", 10)
        self.rrf_k = 60  # Standard constant for RRF

    def aggregate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Input: List of dicts from DB search, each containing:
               {"id": str, "score": float, "payload": dict with at least "parent_section_id"}
        Output: Top-K sections with aggregated scores.
        """
        if not results:
            return []

        # 1. Group chunks by parent section ID
        grouped: Dict[str, Dict[str, Any]] = {}
        
        for rank, item in enumerate(results, 1):
            payload = item.get("payload", {})
            # Prefer parent_section_id, fallback to chunk id (if no parent)
            parent_id = payload.get("parent_section_id")
            if not parent_id:
                parent_id = item.get("id", "")
            
            if parent_id not in grouped:
                grouped[parent_id] = {
                    "scores": [],
                    "ranks": [],
                    "top_chunk_score": 0.0,
                    "metadata": payload.copy()  # Store first chunk's metadata
                }
                
            grouped[parent_id]["scores"].append(item["score"])
            grouped[parent_id]["ranks"].append(rank)
            # Update top chunk score
            if item["score"] > grouped[parent_id]["top_chunk_score"]:
                grouped[parent_id]["top_chunk_score"] = item["score"]

        # 2. Compute aggregated score per section
        sections = []
        for sec_id, data in grouped.items():
            if self.method == "max":
                agg_score = data["top_chunk_score"]
            elif self.method == "mean":
                agg_score = sum(data["scores"]) / len(data["scores"])
            elif self.method == "rrf":
                # RRF: sum(1 / (k + rank)) for each chunk belonging to this section
                agg_score = sum(1.0 / (self.rrf_k + r) for r in data["ranks"])
            else:
                agg_score = data["top_chunk_score"]  # Fallback to max
                
            sections.append({
                "section_id": sec_id,
                "score": agg_score,
                "chunk_count": len(data["scores"]),
                "metadata": data["metadata"]
            })

        # 3. Sort descending by score (and chunk_count as tie-breaker)
        sections.sort(key=lambda x: (x["score"], x["chunk_count"]), reverse=True)
        
        # 4. Return top K
        return sections[:self.top_k_sections]