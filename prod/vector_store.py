import uuid
import numpy as np
from typing import List, Tuple, Optional


class VectorDB:
    """
    Qdrant-backed vector store (dense embeddings, flat/exact index).
    """

    def __init__(self, path: str):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(path=path)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, name: str, dim: int) -> None:
        """Create a new collection. Raises if it already exists."""
        from qdrant_client.models import VectorParams, Distance

        if self.collection_exists(name):
            raise ValueError(f"Collection '{name}' already exists.")

        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=dim,
                distance=Distance.DOT,
            ),
        )

    def collection_exists(self, name: str) -> bool:
        return self.client.collection_exists(name)

    def drop_collection(self, name: str) -> None:
        self.client.delete_collection(name)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert(self, name: str, records: List[dict]) -> None:
        """
        Insert or update a batch of records.

        Each record must have:
            - "id"     : str | int  — your domain ID
            - "dense"  : list[float] | np.ndarray — embedding vector
            - "payload": dict (optional) — arbitrary metadata
        """
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

    def insert_one(self, name: str, record: dict) -> None:
        """
        Convenience wrapper — insert or update a single record.

        Same schema as :meth:`upsert` records.
        """
        self.upsert(name, [record])

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def search(
        self,
        name: str,
        query_vector: np.ndarray,
        top_k: int = 10,
    ) -> Tuple[List[str], List[float], List[dict]]:
        """
        Exact (flat) nearest-neighbour search.

        Returns:
            ids      – original domain IDs from payload
            scores   – dot-product scores (descending)
            payloads – full payload dicts
        """
        results = self.client.query_points(
            collection_name=name,
            query=self._to_list(query_vector),
            limit=top_k,
            with_payload=True,
            search_params={"exact": True},  # flat index
        )

        ids = [p.payload.get("original_id", p.id) for p in results.points]
        scores = [p.score for p in results.points]
        payloads = [p.payload for p in results.points]
        return ids, scores, payloads

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_point_id(original_id) -> str:
        """Deterministically map any domain ID to a UUID."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(original_id)))

    @staticmethod
    def _to_list(vector) -> list:
        """Normalise ndarray or list to a plain Python list."""
        if isinstance(vector, np.ndarray):
            return vector.tolist()
        return list(vector)


def get_vector_db(cfg: dict) -> VectorDB:
    path = cfg.get("database", {}).get("path", "data/vector_db/")
    return VectorDB(path)