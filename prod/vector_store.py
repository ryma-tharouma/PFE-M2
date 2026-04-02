# src/components/vector_store.py
from typing import List, Dict, Optional, Literal
import chromadb


class VectorStore:
    """
    Persistent vector store for hierarchical RAG (FAQ + Manual).
    Uses dot product similarity with normalized embeddings.
    """

    def __init__(self, persist_dir: str = "db/chroma", embedder=None):
        self.persist_dir = persist_dir
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=persist_dir)
        self._collections: Dict[str, chromadb.Collection] = {}

        if self.embedder is None:
            raise ValueError("Embedder must be provided.")

    # ==================== COLLECTION MANAGEMENT ====================

    def create_collection(self, name: str, index_type: Literal["hnsw"] = "hnsw") -> chromadb.Collection:
        if name in self._collections:
            return self._collections[name]

        metadata = {
            "hnsw:space": "ip",           # dot product
            "hnsw:M": 32,
            "hnsw:construction_ef": 200
        }

        col = self.client.get_or_create_collection(
            name=name,
            metadata=metadata
        )
        self._collections[name] = col
        return col

    def get_collection(self, name: str) -> Optional[chromadb.Collection]:
        if name in self._collections:
            return self._collections[name]
        try:
            col = self.client.get_collection(name)
            self._collections[name] = col
            return col
        except Exception:
            return None

    def delete_collection(self, name: str) -> bool:
        try:
            self.client.delete_collection(name)
            self._collections.pop(name, None)
            return True
        except Exception:
            return False

    def list_collections(self) -> List[str]:
        return [col.name for col in self.client.list_collections()]

    # ==================== EMBEDDING ====================

    def _embed_docs(self, texts: List[str]) -> List[List[float]]:
        return self.embedder.embed(texts, input_type="document")

    def embed_query(self, query: str) -> List[float]:
        return self.embedder.embed([query], input_type="query")[0]

    # ==================== INGESTION ====================

    def add_faq_entries(
        self,
        app_name: str,
        questions: List[str],
        answers: List[str],
        ids: Optional[List[str]] = None
    ) -> int:
        if len(questions) != len(answers):
            raise ValueError("questions and answers must have same length.")

        collection_name = f"{app_name}_faq"
        col = self.create_collection(collection_name)

        if ids is None:
            start = col.count()
            ids = [f"{collection_name}_{start + i}" for i in range(len(questions))]

        embeddings = self._embed_docs(questions)

        metadata = [{"type": "faq", "answer": a} for a in answers] #remove type

        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=questions,
            metadatas=metadata
        )
        return len(ids)

    def add_manual_chunks(
        self,
        app_name: str,
        chunks: List[str],
        ids: Optional[List[str]] = None,
        meta: Optional[List[Dict]] = None
    ) -> int:
        collection_name = f"{app_name}_manual"
        col = self.create_collection(collection_name)

        if ids is None:
            start = col.count()
            ids = [f"{collection_name}_{start + i}" for i in range(len(chunks))]

        embeddings = self._embed_docs(chunks)

        metadata = meta or [{"type": "manual"} for _ in chunks]

        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadata
        )
        return len(ids)

    # ==================== RETRIEVAL ====================

    def retrieve_faq(
        self,
        query: str,
        app_name: str
    ) -> Optional[Dict]:
        """
        Retrieve best FAQ match (top-1).
        """
        collection_name = f"{app_name}_faq"
        col = self.get_collection(collection_name)
        if not col:
            return None

        query_emb = self.embed_query(query)

        results = col.query(
            query_embeddings=[query_emb],
            n_results=1,
            include=["documents", "distances", "metadatas", "ids"]
        )

        if not results["documents"][0]:
            return None

        distance = float(results["distances"][0][0])
        similarity = -distance  

        return {
            "answer": results["metadatas"][0][0].get("answer", ""),
            "question": results["documents"][0][0],
            "score": similarity,
            "id": results["ids"][0][0],
            "source": "faq"
        }

    def retrieve_manual(
        self,
        query: str,
        app_name: str,
        top_k: int = 3
    ) -> List[Dict]:
        """
        Retrieve top-k manual chunks.
        """
        collection_name = f"{app_name}_manual"
        col = self.get_collection(collection_name)
        if not col:
            return []

        query_emb = self.embed_query(query)

        results = col.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            include=["documents", "distances", "metadatas", "ids"]
        )

        if not results["documents"][0]:
            return []

        return [
            {
                "chunk": results["documents"][0][i],
                "score": -float(results["distances"][0][i]),
                "id": results["ids"][0][i],
                "metadata": results["metadatas"][0][i],
                "source": "manual"
            }
            for i in range(len(results["documents"][0]))
        ]

    def retrieve(
        self,
        query: str,
        app_name: str,
        source: Literal["faq", "manual"],
        top_k: int = 3
    ):
        """
        Unified retrieval interface.
        """
        if source == "faq":
            return self.retrieve_faq(query, app_name)
        elif source == "manual":
            return self.retrieve_manual(query, app_name, top_k)
        else:
            raise ValueError("Invalid source")

    # ==================== UTILITIES ====================

    def count(self, collection_name: str) -> int:
        col = self.get_collection(collection_name)
        return col.count() if col else 0

    def clear_all(self) -> int:
        names = self.list_collections()
        for name in names:
            self.delete_collection(name)
        return len(names)