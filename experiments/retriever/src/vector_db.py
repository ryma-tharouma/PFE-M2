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
    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], 
               top_k: int, alpha: float, index_type: str) -> Tuple[List[str], List[float]]: pass
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
        from qdrant_client.models import VectorParams, SparseVectorParams, SparseIndexParams, Distance
        vectors_cfg = {}
        sparse_cfg = {}
        if mode in ["dense", "hybrid", "finetuned"]:
            vectors_cfg["dense"] = VectorParams(size=dim, distance=Distance.COSINE)
        if mode in ["sparse", "hybrid", "finetuned"]:
            sparse_cfg["sparse"] = SparseVectorParams(index=SparseIndexParams(on_disk=False))
        self.client.create_collection(name, vectors_config=vectors_cfg or None, sparse_vectors_config=sparse_cfg or None)

    def upsert(self, name: str, records: List[dict]):
        from qdrant_client.models import PointStruct, SparseVector
        points = []
        for r in records:
            point_id = self._to_point_id(r["id"])
            vec = {}
            if "dense" in r: vec["dense"] = r["dense"]
            if "sparse" in r: 
                s = r["sparse"]
                vec["sparse"] = SparseVector(indices=[int(k) for k in s.keys()], values=[float(v) for v in s.values()])
            payload = r.get("payload", {}).copy()
            payload["original_id"] = str(r["id"])
            points.append(PointStruct(id=point_id, vector=vec, payload=payload))
        self.client.upsert(name, points, wait=True)

    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], top_k: int, alpha: float, index_type: str):
        from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector
        prefetches = []
        if q_dense is not None: prefetches.append(Prefetch(query=q_dense.tolist(), using="dense", limit=top_k))
        if q_sparse is not None: 
            vec = {"indices": [int(k) for k in q_sparse.keys()], "values": [float(v) for v in q_sparse.values()]}
            prefetches.append(Prefetch(query=vec, using="sparse", limit=top_k))

        # Qdrant exact/flat search
        search_params = {"exact": True} if index_type == "flat" else None

        if len(prefetches) > 1:
            query = FusionQuery(fusion=Fusion.RRF)
            res = self.client.query_points(name, prefetch=prefetches, query=query, limit=top_k, with_payload=["original_id"], search_params=search_params)
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

    def create_collection(self, name: str, dim: int, mode: str, index_type: str):
        self.client.create_collection(name, dimension=dim, metric_type="IP", enable_dynamic_field=True)
        if mode in ["dense", "hybrid", "finetuned"]:
            if index_type == "flat":
                idx = {"metric_type": "IP", "index_type": "FLAT", "params": {}}
            else:
                idx = {"metric_type": "IP", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 100}}
            self.client.create_index(name, "dense_vector", idx)
        if mode in ["sparse", "hybrid", "finetuned"]:
            self.client.create_index(name, "sparse_vector", {"metric_type": "IP", "index_type": "SPARSE_INVERTED_INDEX", "params": {"drop_ratio_build": 0.0}})
        self.client.load(name)

    def upsert(self, name: str, records: List[dict]):
        self.client.insert(name, records)

    def search(self, name: str, q_dense: Optional[np.ndarray], q_sparse: Optional[dict], top_k: int, alpha: float, index_type: str):
        from pymilvus import AnnSearchRequest, WeightedRanker
        reqs = []
        if q_dense is not None:
            params = {"metric_type": "IP", "params": {"ef": 64}} if index_type == "hnsw" else {"metric_type": "IP"}
            reqs.append(AnnSearchRequest([q_dense.tolist()], "dense_vector", params))
        if q_sparse is not None:
            reqs.append(AnnSearchRequest([q_sparse], "sparse_vector", {"metric_type": "IP"}))
            
        rerank = WeightedRanker(alpha, 1.0 - alpha) if len(reqs) > 1 else None
        res = self.client.hybrid_search(name, reqs=reqs, rerank=rerank, limit=top_k, output_fields=["id"])
        ids = [r["entity"]["id"] for r in res[0]]
        scores = [r["distance"] for r in res[0]]
        return ids, scores

    def collection_exists(self, name: str) -> bool: return self.client.has_collection(name)
    def drop_collection(self, name: str): self.client.drop_collection(name)
    def flush(self): 
        try:
            cols = self.client.list_collections()
            if cols: self.client.flush(cols)
        except: pass

def get_vector_db(cfg: dict) -> BaseVectorDB:
    db_type = cfg["database"]["type"].lower()
    path = cfg["database"]["path"]
    if db_type == "qdrant": return QdrantDB(path)
    elif db_type == "milvus": return MilvusDB(path)
    raise ValueError(f"Unsupported DB type: {db_type}")