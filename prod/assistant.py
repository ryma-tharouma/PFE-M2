# assistant.py
import json
import logging
import logging.handlers
import os
from typing import Dict, Generator, List, Any, Optional

# Import all components needed to build the pipeline
from vector_store import get_vector_db, VectorDB
from embedder import Embedder
from retriever import Retriever
from generator import Generator
from rag import RAG


# ----------------------------------------------------------------------
# Per-date file logging setup (unchanged)
# ----------------------------------------------------------------------

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


# ----------------------------------------------------------------------
# Session store (unchanged)
# ----------------------------------------------------------------------

class Session:
    def __init__(self, session_id: str, max_turns: int = 1):
        self.session_id = session_id
        self.max_turns = max_turns
        self.history: List[Dict] = []

    def get_history_text(self) -> str:
        if not self.history:
            return ""
        return "\n".join(
            f"Utilisateur: {t['query']}\nAssistant: {t['answer']}"
            for t in self.history
        )

    def add_turn(self, query: str, answer: str) -> None:
        self.history.append({"query": query, "answer": answer})
        if len(self.history) > self.max_turns:
            self.history.pop(0)

    def reset(self) -> None:
        self.history.clear()


# ----------------------------------------------------------------------
# Assistant - now optionally reuses db and embedder
# ----------------------------------------------------------------------

class Assistant:
    """
    Stateful assistant that builds the full RAG pipeline from config and manages sessions.

    Configuration (top-level sections required):
        - vector_db
        - embedder
        - retriever
        - reranker (optional)
        - generator
        - rag
        - assistant (for its own settings)

    Args:
        config   : complete configuration dictionary (loaded from config.yaml)
        db       : optional existing VectorDB instance (reused if provided)
        embedder : optional existing Embedder instance (reused if provided)
    """

    def __init__(self, config: Dict[str, Any], db: Optional[VectorDB] = None, embedder: Optional[Embedder] = None):
        self.config = config

        # 1. Vector DB – reuse if provided, otherwise create new
        self.vector_db = db if db is not None else get_vector_db(config)

        # 2. Embedder – reuse if provided, otherwise create new
        self.embedder = embedder if embedder is not None else Embedder(config)

        # 3. Retriever (needs db and embedder)
        self.retriever = Retriever(config, db=self.vector_db, embedder=self.embedder)

        # 4. Generator
        self.generator = Generator(config)

        # 5. RAG pipeline
        self.rag = RAG(config, retriever=self.retriever, generator=self.generator)

        # 6. Assistant's own settings
        asst_cfg = config.get("assistant", {})
        self.max_turns = asst_cfg.get("max_turns", 1)
        self.verbose = asst_cfg.get("verbose", False)
        log_dir = asst_cfg.get("log_dir", "logs")

        self.logger = _setup_logger(log_dir)
        self._sessions: Dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Session management (unchanged)
    # ------------------------------------------------------------------

    def _get_or_create_session(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id, self.max_turns)
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
    # Main chat interface (unchanged)
    # ------------------------------------------------------------------

    def chat(self, session_id: str, query: str, app_id: str) -> Generator:
        session = self._get_or_create_session(session_id)
        history = session.get_history_text()

        if self.verbose:
            self.logger.info(
                "Query received | session_id=%s | app_id=%s | history_turns=%d | query=%r",
                session_id, app_id, len(session.history), query,
            )

        answer_tokens: List[str] = []
        sentinel: Dict | None = None

        for item in self.rag.chat(
            query=query,
            app_id=app_id,
            history=history,
            verbose=self.verbose,
        ):
            if isinstance(item, dict) and item.get("done"):
                sentinel = item
            else:
                answer_tokens.append(item)
                yield item

        full_answer = "".join(answer_tokens)
        session.add_turn(query, full_answer)

        if self.verbose and sentinel:
            # Log response metrics + a truncated version of the full answer to allow
            # later admin inspection (avoid extremely large log lines).
            try:
                answer_preview = full_answer if len(full_answer) <= 4000 else full_answer[:4000] + "..."
            except Exception:
                answer_preview = ""

            self.logger.info(
                "Response complete | session_id=%s | app_id=%s | tokens=%d | "
                "embed=%.3fs | search=%.3fs | ttft=%.3fs | total=%.3fs | sources=%s | answer=%s",
                session_id, app_id, len(answer_tokens),
                sentinel.get("embed_sec") or 0.0,
                sentinel.get("search_sec") or 0.0,
                sentinel.get("ttft_sec") or 0.0,
                sentinel.get("total_sec") or 0.0,
                json.dumps(sentinel.get("sources", [])),
                answer_preview,
            )

        if sentinel:
            yield sentinel
        else:
            if self.verbose:
                self.logger.warning(
                    "No sentinel received | session_id=%s | app_id=%s",
                    session_id, app_id,
                )
            yield {"done": True, "sources": []}

    # ------------------------------------------------------------------
    # Cleanup (optional, for graceful shutdown)
    # ------------------------------------------------------------------

    def cleanup(self):
        """Clean up resources (models, caches)."""
        if hasattr(self, 'generator'):
            self.generator.cleanup()
        if hasattr(self, 'retriever'):
            self.retriever.cleanup()
        if hasattr(self, 'embedder'):
            self.embedder.cleanup()