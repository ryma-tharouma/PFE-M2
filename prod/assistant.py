from typing import Dict, Optional, List
from rag import RAG


class Assistant:
    def __init__(self, rag: RAG):
        self.rag = rag
        self.user_states: Dict[str, Dict] = {}

    # ==================== STATE ====================
    def _get_state(self, user_id: str) -> Dict:
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "waiting_ticket": False,
                "last_question": None,
            }
        return self.user_states[user_id]

    def _reset_state(self, user_id: str):
        self.user_states[user_id] = {
            "waiting_ticket": False,
            "last_question": None,
        }

    # ==================== MAIN ====================
    def handle(
        self,
        user_id: str,
        query: Optional[str] = None,
        action: Optional[str] = None,
        app_name: str = "",
        history: Optional[List[Dict]] = None,
    ) -> Dict:

        history = history or []
        state = self._get_state(user_id)

        # =========================
        # CASE 1: Button clicked
        # =========================
        if action:

            if state["waiting_ticket"]:

                if action == "confirm_ticket":
                    question = state["last_question"]
                    self._reset_state(user_id)

                    return {
                        "answer": "Je vais créer un ticket avec votre demande.",
                        "used": "none",
                        "action": "create_ticket",
                        "sources": [],
                        "data": {
                            "question": question
                        }
                    }

                elif action == "deny_ticket":
                    self._reset_state(user_id)

                    return {
                        "answer": "D'accord, pas de ticket créé 👍",
                        "used": "none",
                        "action": "none",
                        "sources": []
                    }

            # Unknown action fallback
            return {
                "answer": "",
                "used": "none",
                "action": "none",
                "sources": []
            }

        # =========================
        # CASE 2: User typed message
        # =========================
        if query:

            # If user was in ticket flow but typed → reset
            if state["waiting_ticket"]:
                self._reset_state(user_id)

            # Run RAG
            rag_result = self.rag.answer(query, app_name, history)
            used = rag_result.get("used", "none")
            sources = rag_result.get("sources", [])

            # =========================
            # RAG SUCCESS
            # =========================
            if used != "none":
                return {
                    "answer": rag_result["answer"],
                    "used": used,
                    "action": "none",
                    "sources": sources
                }

            # =========================
            # RAG FAILED → ask for ticket
            # =========================
            self.user_states[user_id] = {
                "waiting_ticket": True,
                "last_question": query,
            }

            return {
                "answer": "Je n'ai pas trouvé d'information. Voulez-vous créer un ticket ?",
                "used": "none",
                "action": "ask_ticket_confirmation",
                "sources": [],
                "buttons": [
                    {"label": "Oui", "value": "confirm_ticket"},
                    {"label": "Non", "value": "deny_ticket"},
                ]
            }

        # =========================
        # Fallback
        # =========================
        return {
            "answer": "",
            "used": "none",
            "action": "none",
            "sources": []
        }