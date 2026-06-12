# vector_store.py
import uuid
import time
import numpy as np
from typing import List, Tuple, Optional, Dict, Any


class VectorDB:
    """
    Qdrant-backed vector store (dense embeddings, HNSW index).
    """

    def __init__(
        self,
        path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 100,
        hnsw_ef: int = 128,
    ):
        from qdrant_client import QdrantClient
        if host:
            if port is None:
                raise ValueError("port must be specified when host is provided")
            self.client = QdrantClient(host=host, port=port, api_key=api_key)
        elif path:
            self.client = QdrantClient(path=path)
        else:
            raise ValueError("Either host or path must be provided")

        self.hnsw_m            = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct
        self.hnsw_ef           = hnsw_ef

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, name: str, dim: int) -> None:
        from qdrant_client.models import (
            VectorParams, Distance, HnswConfigDiff, OptimizersConfigDiff
        )
        if self.collection_exists(name):
            raise ValueError(f"Collection '{name}' already exists.")
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=dim,
                distance=Distance.DOT,
                hnsw_config=HnswConfigDiff(
                    m=self.hnsw_m,
                    ef_construct=self.hnsw_ef_construct,
                ),
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=0,
            ),
        )
        while True:
            info   = self.client.get_collection(name)
            status = str(info.status).lower()
            if "green" in status or "ok" in status:
                break
            time.sleep(0.5)

    def collection_exists(self, name: str) -> bool:
        return self.client.collection_exists(name)

    def list_collections(self) -> List[str]:
        """Retourne la liste des noms de toutes les collections Qdrant."""
        return [c.name for c in self.client.get_collections().collections]

    def collection_point_count(self, name: str) -> int:
        """Retourne le nombre réel de points stockés dans une collection."""
        try:
            result = self.client.count(collection_name=name, exact=True)
            return int(getattr(result, "count", 0) or 0)
        except Exception:
            return 0

    def drop_collection(self, name: str) -> None:
        self.client.delete_collection(name)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert(self, name: str, records: List[Dict[str, Any]]) -> None:
        from qdrant_client.models import PointStruct
        points = []
        for r in records:
            payload = r.get("payload", {}).copy()
            payload["original_id"] = str(r["id"])
            points.append(
                PointStruct(
                    id=self._to_point_id(r["id"]),
                    vector=self._to_list(r["dense"]),
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=name, points=points, wait=True)

    def insert_one(self, name: str, record: Dict[str, Any]) -> None:
        self.upsert(name, [record])

    def delete(self, name: str, ids: List[str]) -> None:
        from qdrant_client.models import PointIdsList
        point_ids = [self._to_point_id(i) for i in ids]
        self.client.delete(
            collection_name=name,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )

    def delete_one(self, name: str, original_id: str) -> None:
        self.delete(name, [original_id])

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def search(
        self,
        name: str,
        query_vector: np.ndarray,
        top_k: int = 20,
    ) -> Tuple[List[str], List[float], List[Dict[str, Any]]]:
        from qdrant_client.models import SearchParams
        results = self.client.query_points(
            collection_name=name,
            query=self._to_list(query_vector),
            limit=top_k,
            with_payload=True,
            search_params=SearchParams(
                hnsw_ef=self.hnsw_ef,
                exact=False,
            ),
        )
        ids      = [p.payload.get("original_id", p.id) for p in results.points]
        scores   = [p.score for p in results.points]
        payloads = [p.payload for p in results.points]
        return ids, scores, payloads

    def close(self):
        self.client.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_point_id(original_id) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(original_id)))

    @staticmethod
    def _to_list(vector) -> list:
        if isinstance(vector, np.ndarray):
            return vector.tolist()
        return list(vector)


def get_vector_db(cfg: Dict[str, Any]) -> VectorDB:
    vdb_cfg = cfg.get("vector_db", {})
    host    = vdb_cfg.get("host")

    hnsw_m            = vdb_cfg.get("hnsw_m", 16)
    hnsw_ef_construct = vdb_cfg.get("hnsw_ef_construct", 100)
    hnsw_ef           = vdb_cfg.get("hnsw_ef", 128)

    if host:
        return VectorDB(
            host=host,
            port=vdb_cfg.get("port", 6333),
            api_key=vdb_cfg.get("api_key"),
            hnsw_m=hnsw_m,
            hnsw_ef_construct=hnsw_ef_construct,
            hnsw_ef=hnsw_ef,
        )
    else:
        return VectorDB(
            path=vdb_cfg.get("path", "data/vector_db/"),
            hnsw_m=hnsw_m,
            hnsw_ef_construct=hnsw_ef_construct,
            hnsw_ef=hnsw_ef,
        )