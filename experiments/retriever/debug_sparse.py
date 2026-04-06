# debug_sparse.py
from src.embedder import BGEEmbedder

cfg = {"device": "cpu", "use_fp16": False, "model": {"base_name": "BAAI/bge-m3"}}
embedder = BGEEmbedder(mode="sparse", cfg=cfg)

test_queries = [
    "Comment créer un compte?",
    "mot de passe oublié",
    "CB",
    "remboursement"
]

for q in test_queries:
    sparse = embedder.encode_sparse([q])[0]
    print(f"Query: '{q}' → Sparse tokens: {len(sparse)} | Sample: {dict(list(sparse.items())[:3]) if sparse else 'EMPTY'}")