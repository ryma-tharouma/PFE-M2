# src/components/rag_pipeline.py
from typing import List, Dict, Optional, Union
from concurrent.futures import ThreadPoolExecutor, Future
from vector_store import VectorStore
from embedder import Embedder
from rewriter import OllamaRewriter
from generator import Generator


class RAG:
    """
    Optimized RAG pipeline with parallel retrieval:

    1. Rewrite query
    2. Run FAQ + Manual retrieval in parallel
    3. If FAQ ≥ threshold → return immediately
    4. Else use manual results → generate
    5. Else → return none
    """

    def __init__(
        self,
        generator_model: str,
        rewriter_model: str,
        embedder_model: str,
        faq_threshold: float = 0.75,
        rag_threshold: float = 0.6,
        topK: int = 3,
        generate_or_stream: str = "generate",
        persist_dir: str = "db/chroma",
        rewrite_history_turns: int = 6,
        generator_history_turns: int = 6,
        max_workers: int = 2,
    ):
        self.faq_threshold = faq_threshold
        self.rag_threshold = rag_threshold
        self.topK = topK
        self.generate_or_stream = generate_or_stream
        self.rewrite_history_turns = rewrite_history_turns
        self.generator_history_turns = generator_history_turns

        self.embedder = Embedder(embedder_model)
        self.vstore = VectorStore(persist_dir=persist_dir, embedder=self.embedder)
        self.rewriter = OllamaRewriter(model_name=rewriter_model)
        self.generator = Generator()
        self.generator_model = generator_model

        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    # ==================== QUERY REWRITE ====================
    def rewrite_query(self, query: str, history: Optional[List[Dict]] = None) -> str:
        history = history or []
        rewrite_history = history[-self.rewrite_history_turns:]
        return self.rewriter.rewrite(query, history=rewrite_history)

    # ==================== FAQ ====================
    def _retrieve_faq(self, query: str, app_name: str) -> Optional[Dict]:
        faq = self.vstore.retrieve_faq(query, app_name)
        if faq and faq["score"] >= self.faq_threshold:
            return {
                "answer": faq["answer"],
                "sources": [faq],
                "used": "faq"
            }
        return None

    # ==================== MANUAL ====================
    def _retrieve_manual(self, query: str, app_name: str) -> List[Dict]:
        return self.vstore.retrieve_manual(query, app_name, top_k=self.topK)

    def _generate_from_manual(
        self,
        query: str,
        manual_docs: List[Dict],
        history: List[Dict],
    ) -> Optional[Dict]:

        if not manual_docs:
            return None

        min_score = min(d["score"] for d in manual_docs)
        if min_score < self.rag_threshold:
            return None

        gen_history = history[-self.generator_history_turns:]

        if self.generate_or_stream == "stream":
            answer = self.generator.stream(
                model_name=self.generator_model,
                query=query,
                context_docs=manual_docs,
                history=gen_history
            )
        else:
            answer = self.generator.generate(
                model_name=self.generator_model,
                query=query,
                context_docs=manual_docs,
                history=gen_history
            )

        return {
            "answer": answer,
            "sources": manual_docs,
            "used": "rag"
        }

    # ==================== MAIN ====================
    def answer(
        self,
        query: str,
        app_name: str,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Union[str, List[Dict]]]:

        history = history or []

        # 1. Rewrite
        rewritten = self.rewrite_query(query, history)

        # 2. Launch parallel retrieval
        faq_future: Future = self.executor.submit(self._retrieve_faq, rewritten, app_name)
        manual_future: Future = self.executor.submit(self._retrieve_manual, rewritten, app_name)

        # 3. Check FAQ FIRST (blocking but fast)
        faq_result = faq_future.result()
        if faq_result:
            # Optional: cancel manual if still running (best-effort)
            manual_future.cancel()
            return faq_result

        # 4. FAQ failed → use manual (already running!)
        manual_docs = manual_future.result()

        rag_result = self._generate_from_manual(rewritten, manual_docs, history)
        if rag_result:
            return rag_result

        # 5. Nothing found
        return {
            "answer": None,
            "sources": [],
            "used": "none"
        }