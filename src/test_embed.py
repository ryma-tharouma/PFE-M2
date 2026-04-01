#!/usr/bin/env python3
import logging
import sys
import time
import numpy as np

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
    force=True
)

from embedder import Embedder

def test_ollama_embedding(model: str = "bge-m3"):
    """Test Ollama embedding endpoint (works for embedding-only models)."""
    import ollama
    try:
        start = time.time()
        result = ollama.embed(model=model, input="connection test")
        dim = len(result["embeddings"][0])
        logging.info(f"✓ Ollama embedding OK | model={model} | dim={dim} | {time.time()-start:.2f}s")
        return True
    except Exception as e:
        logging.error(f"✗ Ollama embedding failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting embedder test...", flush=True)
    
    # Step 1: Verify Ollama embedding endpoint
    if not test_ollama_embedding("bge-m3"):
        print("\n💡 Fixes:", flush=True)
        print("  1. Start server:  ollama serve", flush=True)
        print("  2. Pull model:    ollama pull bge-m3", flush=True)
        print("  3. Verify:        curl http://localhost:11434/api/tags", flush=True)
        sys.exit(1)
    
    try:
        # Step 2: Initialize embedder
        print("🔧 Initializing embedder...", flush=True)
        embedder = Embedder(model_name="bge", backend="ollama", verbose=True)
        print("✓ Embedder initialized", flush=True)
        
        # Step 3: Embed query
        print("📥 Embedding query...", flush=True)
        query_emb = embedder.embed(
            ["Quelle est la politique de remboursement ?"], 
            input_type="query"
        )
        print(f"✓ Query embedded | shape: {np.array(query_emb).shape}", flush=True)
        
        # Step 4: Embed document
        print("📥 Embedding document...", flush=True)
        doc_emb = embedder.embed(
            ["Notre politique de remboursement est la suivante..."], 
            input_type="document"
        )
        print(f"✓ Document embedded | shape: {np.array(doc_emb).shape}", flush=True)
        
        # Step 5: Compute similarity (embeddings are L2-normalized)
        similarity = np.dot(query_emb[0], doc_emb[0])
        print(f"🎯 Cosine similarity: {similarity:.4f}", flush=True)
        
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted", flush=True)
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        embedder.close()
        print("🔚 Done", flush=True)