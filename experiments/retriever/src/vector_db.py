# src/vector_db.py
import uuid
import numpy as np
from typing import List, Dict, Tuple, Optional
from abc import ABC, abstractmethod

class BaseVectorDB(ABC):
    @abstractmethod
    def create_collection(self, name: str, dim: int, mode: str, index_type: str): pass
    @abstractmethod
    def upsert(self, name: str, records: List[dict]): pass
    @abstractmethod
    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], top_k: int, alpha: float, index_type: str) -> Tuple[List[str], List[float]]: pass
    @abstractmethod
    def collection_exists(self, name: str) -> bool: pass
    @abstractmethod
    def drop_collection(self, name: str): pass
    @abstractmethod
    def flush(self): pass

class QdrantDB(BaseVectorDB):
    def __init__(self, path: str):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(path=path)

    def _to_point_id(self, original_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(original_id)))

    def create_collection(self, name: str, dim: int, mode: str, index_type: str):
        from qdrant_client.models import VectorParams, SparseVectorParams, SparseIndexParams, Distance, HnswConfigDiff
        vectors_cfg, sparse_cfg = {}, {}
        if mode in ["dense", "hybrid", "finetuned_dense", "finetuned_hybrid"]:
            hnsw_cfg = HnswConfigDiff(m=16, ef_construct=100, on_disk=False) if index_type == "hnsw" else None
            vectors_cfg["dense"] = VectorParams(size=dim, distance=Distance.DOT, hnsw_config=hnsw_cfg)
        if mode in ["sparse", "hybrid", "finetuned_hybrid"]:
            sparse_cfg["sparse"] = SparseVectorParams(index=SparseIndexParams(on_disk=False))
        self.client.create_collection(name, vectors_config=vectors_cfg or None, sparse_vectors_config=sparse_cfg or None)

    def upsert(self, name: str, records: List[dict]):
        from qdrant_client.models import PointStruct, SparseVector
        points = []
        for r in records:
            pid = self._to_point_id(r["id"])
            vec = {}
            if "dense" in r: vec["dense"] = r["dense"]
            if "sparse" in r: 
                s = r["sparse"]
                vec["sparse"] = SparseVector(indices=[int(k) for k in s.keys()], values=[float(v) for v in s.values()])
            payload = r.get("payload", {}).copy()
            payload["original_id"] = str(r["id"])
            points.append(PointStruct(id=pid, vector=vec, payload=payload))
        self.client.upsert(name, points, wait=True)

    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], top_k: int, alpha: float, index_type: str):
        from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector
        prefetches = []
        if q_dense is not None: prefetches.append(Prefetch(query=q_dense.tolist(), using="dense", limit=top_k))
        if q_sparse is not None: 
            vec = {"indices": [int(k) for k in q_sparse.keys()], "values": [float(v) for v in q_sparse.values()]}
            prefetches.append(Prefetch(query=vec, using="sparse", limit=top_k))

        search_params = {"exact": True} if index_type == "flat" else None

        if len(prefetches) > 1:
            res = self.client.query_points(name, prefetch=prefetches, query=FusionQuery(fusion=Fusion.RRF), limit=top_k, with_payload=["original_id"], search_params=search_params)
        elif len(prefetches) == 1:
            res = self.client.query_points(name, query=prefetches[0].query, using=prefetches[0].using, limit=top_k, with_payload=["original_id"], search_params=search_params)
        else:
            return [], []
        return [p.payload.get("original_id", str(p.id)) for p in res.points], [p.score for p in res.points]

    def collection_exists(self, name: str) -> bool: return self.client.collection_exists(name)
    def drop_collection(self, name: str): self.client.delete_collection(name)
    def flush(self): pass

class MilvusDB(BaseVectorDB):
    def __init__(self, uri: str):
        from pymilvus import MilvusClient
        self.client = MilvusClient(uri=uri)
    def create_collection(self, name: str, dim: int, mode: str, index_type: str): pass
    def upsert(self, name: str, records: List[dict]): pass
    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], top_k: int, alpha: float, index_type: str): return [], []
    def collection_exists(self, name: str) -> bool: return False
    def drop_collection(self, name: str): pass
    def flush(self): pass

def get_vector_db(cfg: dict) -> BaseVectorDB:
    db_type = cfg.get("database", {}).get("type", "qdrant").lower()
    path = cfg.get("database", {}).get("path", "data/vector_db/")
    if db_type == "qdrant": return QdrantDB(path)
    elif db_type == "milvus": return MilvusDB(path)
    raise ValueError(f"Unsupported DB type: {db_type}")