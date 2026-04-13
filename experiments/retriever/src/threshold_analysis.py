# src/threshold_analysis.py
from typing import List, Dict, Any

def optimize_thresholds(
    all_results: List[Dict[str, Any]],
    modes: List[str]
) -> Dict[str, Dict[str, float]]:
    """
    Computes mode-specific routing thresholds using query-level top scores:
      - T_rag: Optimized for F1 (balances recall/precision for context gathering)
      - T_faq: Optimized for Precision@1 (ensures top result is highly reliable)
    Routing logic: 
      score >= T_faq → FAQ
      T_rag <= score < T_faq → RAG
      score < T_rag → OOD (bypass LLM)
    """
    thresholds = {}
    
    for mode in modes:
        mode_results = [r for r in all_results if r["mode"] == mode]
        if not mode_results:
            continue
            
        # Extract TOP SCORE per query + ground truth relevance
        query_scores = []
        query_is_relevant = []
        
        for r in mode_results:
            # Use highest section score as query confidence
            top_score = max(r["search_scores"]) if r["search_scores"] else 0.0
            # Check if the top retrieved section is actually relevant
            top_is_rel = 1 if (r["retrieved_section_ids"] and 
                               r["retrieved_section_ids"][0] in r["relevant_ids"]) else 0
                               
            query_scores.append(top_score)
            query_is_relevant.append(top_is_rel)
            
        if not query_scores:
            thresholds[mode] = {"T_faq": 0.0, "T_rag": 0.0}
            continue
            
        unique_scores = sorted(set(query_scores))
        
        # --- Optimize T_rag (Maximize F1) ---
        best_f1, best_t_rag = 0.0, 0.0
        for t in unique_scores:
            tp = sum(1 for s, rel in zip(query_scores, query_is_relevant) if s >= t and rel == 1)
            fp = sum(1 for s, rel in zip(query_scores, query_is_relevant) if s >= t and rel == 0)
            fn = sum(1 for s, rel in zip(query_scores, query_is_relevant) if s < t and rel == 1)
            
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * rec / (p + rec) if (p + rec) > 0 else 0.0
            
            if f1 > best_f1:
                best_f1, best_t_rag = f1, t
                
        # --- Optimize T_faq (Maximize Precision@1) ---
        best_p1, best_t_faq = 0.0, 0.0
        for t in unique_scores:
            correct = sum(1 for s, rel in zip(query_scores, query_is_relevant) if s >= t and rel == 1)
            predicted = sum(1 for s in query_scores if s >= t)
            p1 = correct / predicted if predicted > 0 else 0.0
            if p1 > best_p1:
                best_p1, best_t_faq = p1, t
                
        # Enforce strict ordering: FAQ must be harder to trigger than RAG
        T_faq_final = max(best_t_faq, best_t_rag + 0.01)
        T_rag_final = best_t_rag
        
        thresholds[mode] = {
            "T_faq": round(T_faq_final, 4),
            "T_rag": round(T_rag_final, 4),
            "faq_precision": round(best_p1, 4),
            "rag_f1": round(best_f1, 4)
        }
        
    return thresholds