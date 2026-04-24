# assistant.py
import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Dict, Generator, List

from rag import RAG


# ----------------------------------------------------------------------
# Per-date file logging setup
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
# Session store
# ----------------------------------------------------------------------

class Session:
    def __init__(self, session_id: str, max_turns: int = 1):
        self.session_id = session_id
        self.max_turns  = max_turns
        self.history: List[Dict] = []   # [{"query": str, "answer": str}, ...]

    def get_history_text(self) -> str:
        """
        Format the last `max_turns` turns as a history string for the RAG pipeline.
        Returns empty string if no history yet.
        """
        if not self.history:
            return ""
        return "\n".join(
            f"Utilisateur: {t['query']}\nAssistant: {t['answer']}"
            for t in self.history   # already capped to max_turns by add_turn
        )

    def add_turn(self, query: str, answer: str) -> None:
        self.history.append({"query": query, "answer": answer})
        if len(self.history) > self.max_turns:
            self.history.pop(0)

    def reset(self) -> None:
        self.history.clear()


# ----------------------------------------------------------------------
# Assistant
# ----------------------------------------------------------------------

class Assistant:
    """
    Stateful assistant that manages sessions and delegates to RAG.

    Args:
        rag       : configured RAG instance
        max_turns : how many previous turns to keep and pass as history (default 1)
        verbose   : if True, logs timing info and includes it in responses
        log_dir   : directory for rotating log files
    """

    def __init__(
        self,
        rag: RAG,
        max_turns: int = 1,
        verbose: bool = False,
        log_dir: str = "logs",
    ):
        self.rag       = rag
        self.max_turns = max_turns
        self.verbose   = verbose
        self.logger    = _setup_logger(log_dir)
        self._sessions: Dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_or_create_session(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id, self.max_turns)
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        if session_id in self._sessions:
            self._sessions[session_id].reset()
            if self.verbose:
                self.logger.info("Session reset | session_id=%s", session_id)

    def delete_session(self, session_id: str) -> None:
        """Remove session entirely."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            if self.verbose:
                self.logger.info("Session deleted | session_id=%s", session_id)

    # ------------------------------------------------------------------
    # Main chat interface
    # ------------------------------------------------------------------

    def chat(
        self,
        session_id: str,
        query: str,
        app_id: str,
    ) -> Generator:
        """
        Stream a response for the given query.

        Yields str tokens, then a final sentinel dict:
            {
                "done"    : True,
                "sources" : List[Dict],
                # if verbose=True:
                "embed_sec"   : float,
                "search_sec"  : float,
                "ttft_sec"    : float,
                "total_sec"   : float,
            }

        Args:
            session_id : unique identifier for the conversation session
            query      : user query string
            app_id     : application identifier chosen by the user in frontend
        """
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
            self.logger.info(
                "Response complete | session_id=%s | app_id=%s | "
                "tokens=%d | embed=%.3fs | search=%.3fs | ttft=%.3fs | total=%.3fs | sources=%s",
                session_id,
                app_id,
                len(answer_tokens),
                sentinel.get("embed_sec")  or 0.0,
                sentinel.get("search_sec") or 0.0,
                sentinel.get("ttft_sec")   or 0.0,
                sentinel.get("total_sec")  or 0.0,
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
            yield {"done": True, "sources": []}


'''
backend usage:

assistant = Assistant(rag=rag, max_turns=3, verbose=True, log_dir="logs")

# in your route handler:
for item in assistant.chat(session_id="abc123", query="...", app_id="manuel_parc_auto"):
    if isinstance(item, dict) and item["done"]:
        sources     = item["sources"]
        embed_sec   = item.get("embed_sec")
        search_sec  = item.get("search_sec")
    else:
        stream_to_frontend(item)  # send token
'''