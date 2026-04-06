from src.embedder import BGEEmbedder
from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector

cfg = {"device": "cpu", "use_fp16": False, "model": {"base_name": "BAAI/bge-m3"}}
embedder = BGEEmbedder(mode="sparse", cfg=cfg)
client = QdrantClient(path="data/vector_db/")

# Test query from your mock data
q = "CB"
sparse = embedder.encode_sparse([q])[0]
print(f"🔍 Query: '{q}' → Tokens: {sparse}")

vec = SparseVector(indices=[int(k) for k in sparse.keys()], values=[float(v) for v in sparse.values()])

res = client.query_points(
    collection_name="manual_bdm_sparse_qdrant_flat",
    query=vec,
    using="sparse",
    limit=3,
    with_payload=["original_id"]
)
print(f"✅ Found {len(res.points)} results:")
for p in res.points:
    print(f"  {p.payload.get('original_id')}: score={p.score}")