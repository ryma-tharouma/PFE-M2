# assistant.py
import json
import logging
import logging.handlers
import os
from typing import Any, Dict, Generator, List, Optional

from vector_store import get_vector_db, VectorDB
from embedder import Embedder
from retriever import Retriever
from generator import Generator
from rag import RAG


# =============================================================================
# Logging
# =============================================================================

def _setup_logger(log_dir: str = "logs") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("assistant")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, "assistant.log"),
            when="midnight",
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)

    return logger


# =============================================================================
# Session
# =============================================================================

class Session:
    """
    Holds conversation history and the per-turn query forms needed for the two
    query-context modes:

        concat  – needs the previous *original* user query
                  → read from history[-1]["query"]

        rewrite – needs the previous *rewritten* retrieval query
                  → stored separately in last_retrieval_query

    The assistant answer stored in history is truncated to answer_truncate_words
    words so that the history text passed to the generator stays compact.
    """

    def __init__(
        self,
        session_id: str,
        max_turns: int = 1,
        answer_truncate_words: int = 50,
    ):
        self.session_id            = session_id
        self.max_turns             = max_turns
        self.answer_truncate_words = answer_truncate_words
        self.history:               List[Dict] = []
        self.last_retrieval_query:  str        = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _truncate(self, text: str) -> str:
        words = text.split()
        if len(words) <= self.answer_truncate_words:
            return text
        return " ".join(words[:self.answer_truncate_words]) + "…"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_history_text(self) -> str:
        """Formatted history block for the generator (answers are truncated)."""
        if not self.history:
            return ""
        return "\n".join(
            f"Utilisateur: {t['query']}\nAssistant: {self._truncate(t['answer'])}"
            for t in self.history
        )

    def get_last_original_query(self) -> str:
        """Raw user query from the previous turn (used by concat mode)."""
        return self.history[-1]["query"] if self.history else ""

    def get_last_retrieval_query(self) -> str:
        """Rewritten retrieval query from the previous turn (used by rewrite mode)."""
        return self.last_retrieval_query

    def add_turn(self, query: str, answer: str, retrieval_query: str) -> None:
        """
        Record a completed turn.

        Args:
            query           : original user query (stored verbatim)
            answer          : full assistant answer (truncated when building history)
            retrieval_query : actual query sent to the vector store this turn
        """
        self.history.append({"query": query, "answer": answer})
        if len(self.history) > self.max_turns:
            self.history.pop(0)
        self.last_retrieval_query = retrieval_query

    def reset(self) -> None:
        self.history.clear()
        self.last_retrieval_query = ""


# =============================================================================
# Assistant
# =============================================================================

class Assistant:
    """
    Stateful assistant that builds the full RAG pipeline from config and
    manages per-session conversation history.

    Config sections consumed:
        vector_db, embedder, retriever, reranker, generator,
        rewriter, query_context, rag, assistant.

    Args:
        config   : full configuration dictionary (from config.yaml)
        db       : optional existing VectorDB instance (reused if provided)
        embedder : optional existing Embedder instance (reused if provided)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        db: Optional[VectorDB]   = None,
        embedder: Optional[Embedder] = None,
    ):
        self.config = config

        self.vector_db  = db       if db       is not None else get_vector_db(config)
        self.embedder   = embedder if embedder is not None else Embedder(config)
        self.retriever  = Retriever(config, db=self.vector_db, embedder=self.embedder)
        self.generator  = Generator(config)
        self.rag        = RAG(config, retriever=self.retriever, generator=self.generator)

        asst_cfg = config.get("assistant", {})
        self.max_turns             = asst_cfg.get("max_turns", 1)
        self.answer_truncate_words = asst_cfg.get("answer_truncate_words", 50)
        self.verbose               = asst_cfg.get("verbose", False)

        self.logger    = _setup_logger(asst_cfg.get("log_dir", "logs"))
        self._sessions: Dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_or_create_session(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id,
                self.max_turns,
                self.answer_truncate_words,
            )
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].reset()
            if self.verbose:
                self.logger.info("Session reset | session_id=%s", session_id)

    def delete_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            if self.verbose:
                self.logger.info("Session deleted | session_id=%s", session_id)

    # ------------------------------------------------------------------
    # Main chat interface
    # ------------------------------------------------------------------

    def chat(self, session_id: str, query: str, app_id: str) -> Generator:
        """
        Process one user turn.  Yields str tokens then a sentinel dict.

        The sentinel always contains "done", "sources", and "retrieval_query".
        When verbose=True it also contains timing fields.
        """
        session = self._get_or_create_session(session_id)

        history              = session.get_history_text()
        prev_original_query  = session.get_last_original_query()   # for concat
        prev_retrieval_query = session.get_last_retrieval_query()   # for rewrite

        if self.verbose:
            self.logger.info(
                "Query received | session_id=%s | app_id=%s | turns=%d | "
                "query=%r | prev_original=%r | prev_retrieval=%r",
                session_id, app_id, len(session.history),
                query, prev_original_query, prev_retrieval_query,
            )

        answer_tokens:   List[str]      = []
        sentinel:        Optional[Dict] = None
        retrieval_query: str            = query   # overwritten by sentinel

        for item in self.rag.chat(
            query=query,
            app_id=app_id,
            history=history,
            prev_original_query=prev_original_query,
            prev_retrieval_query=prev_retrieval_query,
            verbose=self.verbose,
        ):
            if isinstance(item, dict) and item.get("done"):
                sentinel        = item
                retrieval_query = sentinel.get("retrieval_query", query)
            else:
                answer_tokens.append(item)
                yield item

        full_answer = "".join(answer_tokens)
        session.add_turn(query, full_answer, retrieval_query)

        if self.verbose and sentinel:
            self.logger.info(
                "Response complete | session_id=%s | app_id=%s | tokens=%d | "
                "rewrite=%.3fs | embed=%.3fs | search=%.3fs | "
                "ttft=%.3fs | total=%.3fs | retrieval_query=%r | sources=%s",
                session_id, app_id, len(answer_tokens),
                sentinel.get("rewrite_sec") or 0.0,
                sentinel.get("embed_sec")   or 0.0,
                sentinel.get("search_sec")  or 0.0,
                sentinel.get("ttft_sec")    or 0.0,
                sentinel.get("total_sec")   or 0.0,
                retrieval_query,
                json.dumps(sentinel.get("sources", [])),
            )

        if sentinel:
            yield sentinel
        else:
            if self.verbose:
                self.logger.warning(
                    "No sentinel received | session_id=%s | app_id=%s",
                    session_id, app_id,
                )
            yield {"done": True, "sources": [], "retrieval_query": query}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        for attr in ("generator", "retriever", "embedder"):
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, "cleanup"):
                obj.cleanup()
        # Rewriter lives inside RAG
        if hasattr(self, "rag") and hasattr(self.rag, "cleanup"):
            self.rag.cleanup()