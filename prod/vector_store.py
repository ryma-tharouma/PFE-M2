# vector_store.py
import uuid
import numpy as np
from typing import List, Tuple, Optional, Dict, Any


class VectorDB:
    """
    Qdrant-backed vector store (dense embeddings, flat/exact index).
    """

    def __init__(
        self,
        path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
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

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, name: str, dim: int) -> None:
        from qdrant_client.models import VectorParams, Distance
        if self.collection_exists(name):
            raise ValueError(f"Collection '{name}' already exists.")
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.DOT),
        )

    def collection_exists(self, name: str) -> bool:
        return self.client.collection_exists(name)

    def list_collections(self) -> List[str]:
        """
        Retourne la liste des noms de toutes les collections Qdrant.
        Appelée par main.py → get_available_collections() → /api/collections
        et aussi par resolve_collection() pour valider le nom envoyé par Laravel.
        Sans cette méthode, /api/collections retourne toujours [].
        """
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

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def search(
        self,
        name: str,
        query_vector: np.ndarray,
        top_k: int = 20,
    ) -> Tuple[List[str], List[float], List[Dict[str, Any]]]:
        results = self.client.query_points(
            collection_name=name,
            query=self._to_list(query_vector),
            limit=top_k,
            with_payload=True,
            search_params={"exact": True},
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
    """
    Crée une instance VectorDB depuis la configuration.

    Structure attendue dans config.yaml :
        vector_db:
            host: "localhost"        # optionnel, si absent → mode local
            port: 6333               # requis si host est fourni
            api_key: "your-key"      # optionnel
            path: "data/vector_db/"  # utilisé si host absent
    """
    vdb_cfg = cfg.get("vector_db", {})
    host    = vdb_cfg.get("host")

    if host:
        return VectorDB(
            host=host,
            port=vdb_cfg.get("port", 6333),
            api_key=vdb_cfg.get("api_key"),
        )
    else:
        path = vdb_cfg.get("path", "data/vector_db/")
        return VectorDB(path=path)