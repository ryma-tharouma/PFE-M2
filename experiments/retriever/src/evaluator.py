# src/evaluator.py
import os
import csv
import json
import time
import gc
from typing import Set, List, Dict, Any, Tuple

from src.factories import get_vector_database, get_embedder, get_aggregator, get_context_manager, get_reranker


def get_processed_query_ids(csv_path: str) -> Set[str]:
    """
    Read existing CSV file and return the set of query_ids already processed.
    Assumes CSV has header and first column is 'query_id'.
    """
    if not os.path.exists(csv_path):
        return set()
    processed = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)  # skip header
        except StopIteration:
            return set()
        # Find index of 'query_id' column (should be first, but be safe)
        try:
            qid_idx = header.index("query_id")
        except ValueError:
            qid_idx = 0
        for row in reader:
            if row and len(row) > qid_idx:
                processed.add(row[qid_idx])
    return processed


def run_evaluate(cfg: dict):
    resolved_results = cfg["paths"]["resolved_results"]
    query_sources = cfg.get("evaluation", {}).get("query_sources", [])
    mt_strategies = cfg.get("multi_turn", {}).get("strategies", ["none"])
    max_retrieve = cfg.get("retrieval", {}).get("max_retrieve_sections", 10)
    modes = cfg["indexing"]["modes"]
    db_types = cfg["indexing"].get("db_types", [cfg["database"]["type"]])
    index_types = cfg["indexing"]["index_types"]

    raw_agg = cfg["retrieval"].get("aggregation_method", "max")
    agg_methods = [raw_agg] if isinstance(raw_agg, str) else list(raw_agg)

    # Load all turns
    all_turns = []
    for src in query_sources:
        path = src["path"]
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for conv_line in f:
                conv = json.loads(conv_line)
                conv_id, app_id = conv["conversation_id"], conv.get("app_id", "manual_bdm")
                history = []
                for turn in conv["turns"]:
                    rewritten = turn.get("rewritten_query")
                    is_rewritten = bool(rewritten and rewritten.strip())
                    all_turns.append({
                        "query_id": f"{conv_id}_t{turn['turn_id']}",
                        "query": turn["user_query"],
                        "history": list(history),
                        "relevant_ids": set(turn.get("relevant_sections", [])),
                        "app_id": app_id,
                        "query_quality": turn.get("query_quality", "unknown"),
                        "is_rewritten": is_rewritten,
                    })
                    history.append(turn)
                    if len(history) > cfg["multi_turn"].get("window_size", 2) + 2:
                        history.pop(0)

    if not all_turns:
        print("No queries found to evaluate.")
        return

    print(f"Loaded {len(all_turns)} evaluation turns.")
    unique_app_ids = set(t["app_id"] for t in all_turns)

    os.makedirs(resolved_results, exist_ok=True)

    for strategy in mt_strategies:
        print(f"\nStrategy: {strategy}")
        cfg["multi_turn"]["strategy"] = strategy
        ctx_mgr = get_context_manager(cfg)

        for db_type in db_types:
            cfg["database"]["type"] = db_type
            try:
                db = get_vector_database(cfg)
            except Exception as e:
                print(f"Failed to init DB {db_type}: {e}")
                continue
            print(f"  Connected to {db_type}")

            for mode in modes:
                embedder = get_embedder(mode=mode, cfg=cfg)
                reranker = get_reranker(cfg)  # None if disabled

                # Pre‑load BM25 vocabularies if needed
                if mode in ["sparse", "hybrid", "finetuned_hybrid"]:
                    for app_id in unique_app_ids:
                        vocab_path = os.path.join(resolved_results, "vocab", f"{app_id}_{mode}.json")
                        if os.path.exists(vocab_path):
                            embedder.load_bm25_vocab(app_id, vocab_path)
                            print(f"    Loaded BM25 vocab for app '{app_id}'")
                        else:
                            print(f"    Warning: BM25 vocab not found for app '{app_id}' mode '{mode}'")

                for idx_type in index_types:
                    for agg_method in agg_methods:
                        cfg["retrieval"]["aggregation_method"] = agg_method
                        agg = get_aggregator(cfg)

                        # Output CSV file for this configuration
                        csv_filename = f"{db_type}_{mode}_{idx_type}_{agg_method}_{strategy}_detailed.csv"
                        csv_path = os.path.join(resolved_results, csv_filename)
                        csv_fields = ["query_id", "mode", "db_type", "idx_type", "strategy", "aggregation",
                                      "rank", "doc_id", "score", "is_relevant", "query_quality", "is_rewritten",
                                      "latency_ms"]

                        # Load already processed query IDs from existing CSV
                        processed_qids = get_processed_query_ids(csv_path)
                        if processed_qids:
                            print(f"    Resume: {len(processed_qids)} query IDs already processed in {csv_filename}")

                        # Write header if file is new (empty or doesn't exist)
                        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
                            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                                csv.writer(f).writerow(csv_fields)

                        print(f"  Processing {csv_filename}")

                        # Process each turn, skip if already done
                        for turn in all_turns:
                            if turn["query_id"] in processed_qids:
                                continue

                            app_id = turn["app_id"]

                            # Skip if BM25 required but vocab missing
                            if mode in ["sparse", "hybrid", "finetuned_hybrid"]:
                                if app_id not in embedder._bm25_registry:
                                    print(f"    No BM25 vocab for app '{app_id}', skipping turn {turn['query_id']}")
                                    continue

                            context_str = ctx_mgr.build_context(turn["history"], turn["query"])

                            q_dense = None
                            q_sparse = None
                            if mode != "sparse":
                                q_dense = embedder.encode_dense([context_str])[0]
                            if mode != "dense":
                                q_sparse = embedder.encode_sparse([context_str], app_id)[0]

                            coll_name = f"{app_id}_{mode}_{db_type}_{idx_type}"
                            if not db.collection_exists(coll_name):
                                print(f"    Collection {coll_name} does not exist, skipping turn {turn['query_id']}")
                                continue

                            # Measure retrieval + reranking time
                            start_time = time.time()
                            try:
                                # Expects search to return (ids, scores, payloads)
                                chunk_ids, chunk_scores, chunk_payloads = db.search(
                                    name=coll_name,
                                    q_dense=q_dense,
                                    q_sparse=q_sparse,
                                    top_k=max_retrieve,
                                    alpha=cfg["retrieval"].get("alpha", 0.7),
                                    index_type=idx_type
                                )
                            except Exception as e:
                                print(f"    Search failed for {coll_name}: {e}")
                                continue
                            latency_ms = (time.time() - start_time) * 1000

                            # ------------------------------------------------------------
                            # Rerank chunks (if enabled)
                            # ------------------------------------------------------------
                            if reranker and chunk_ids:
                                k_rerank = min(reranker.top_k_rerank, len(chunk_ids))
                                top_chunk_ids = chunk_ids[:k_rerank]
                                top_chunk_scores = chunk_scores[:k_rerank]
                                top_chunk_payloads = chunk_payloads[:k_rerank]

                                # Extract chunk text from payload
                                chunk_texts = [p.get("chunk_text", "") for p in top_chunk_payloads]

                                # Rerank
                                reranked_ids, reranked_scores = reranker.rerank_and_reorder(
                                    query=context_str,
                                    doc_ids=top_chunk_ids,
                                    doc_texts=chunk_texts,
                                    original_scores=top_chunk_scores
                                )

                                # Build final chunk list: reranked top + remaining (unchanged order)
                                final_chunk_ids = list(reranked_ids)
                                final_chunk_scores = list(reranked_scores)
                                final_chunk_payloads = []
                                payload_map = {cid: p for cid, p in zip(top_chunk_ids, top_chunk_payloads)}
                                for cid in reranked_ids:
                                    final_chunk_payloads.append(payload_map[cid])
                                if len(chunk_ids) > k_rerank:
                                    final_chunk_ids.extend(chunk_ids[k_rerank:])
                                    final_chunk_scores.extend(chunk_scores[k_rerank:])
                                    final_chunk_payloads.extend(chunk_payloads[k_rerank:])
                            else:
                                final_chunk_ids = chunk_ids
                                final_chunk_scores = chunk_scores
                                final_chunk_payloads = chunk_payloads

                            # ------------------------------------------------------------
                            # Aggregate chunks to sections (same as before)
                            # ------------------------------------------------------------
                            chunk_results = []
                            for cid, sc, payload in zip(final_chunk_ids, final_chunk_scores, final_chunk_payloads):
                                chunk_results.append({
                                    "id": cid,
                                    "score": sc,
                                    "payload": payload
                                })

                            sections = agg.aggregate(chunk_results)
                            section_ids = [s["section_id"] for s in sections]
                            section_scores = {s["section_id"]: s["score"] for s in sections}

                            # Write CSV (section level)
                            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                                writer = csv.writer(f)
                                for rank, sec_id in enumerate(section_ids, 1):
                                    is_relevant = 1 if sec_id in turn["relevant_ids"] else 0
                                    writer.writerow([
                                        turn["query_id"], mode, db_type, idx_type, strategy, agg_method,
                                        rank, sec_id, section_scores.get(sec_id, 0.0), is_relevant,
                                        turn["query_quality"], turn["is_rewritten"],
                                        round(latency_ms, 2)
                                    ])

                            processed_qids.add(turn["query_id"])

                embedder.cleanup()
                if reranker:
                    reranker.cleanup()
                del embedder
                gc.collect()

            if db:
                del db
                gc.collect()

    print(f"\nDetailed CSV files saved to {resolved_results}")