# src/components/rewriter_ollama.py
import time
from typing import List, Dict, Optional, Union
import ollama

MODEL_NAME = "ministral-3:8b"
MAX_HISTORY = 6
# max history as args?
def _build_prompt(query: str, history: List[Dict], verbose: bool) -> str:
        trimmed = history[-MAX_HISTORY:] if history else []

        hist_lines = []
        for turn in trimmed:
            role = "Utilisateur" if turn.get("role") == "user" else "Assistant"
            hist_lines.append(f"{role}: {turn.get('content','')}")
        hist_text = "\n".join(hist_lines) if hist_lines else "Aucun historique."

        if verbose:
            output_format = (
                "Ligne 1: requête reformulée\n"
                "Ligne 2+: courte explication"
            )
        else:
            output_format = "Une seule ligne contenant uniquement la requête reformulée."

        return f"""
        Tu es un réécrivain de requêtes pour un système RAG.

        OBJECTIF:
        Transformer la requête utilisateur en une question claire, complète et autonome en utilisant l’historique.

        RÈGLES STRICTES:
        - Tu DOIS résoudre toutes les références vagues: "ça", "et après", "c'est quoi", etc.
        - Tu DOIS inclure le contexte précis (action, objet, tâche)
        - La question doit être compréhensible SANS l’historique
        - UNE seule phrase
        - NE PAS répondre à la question
        - NE PAS inventer d'information

        ---

        EXEMPLES:

        Conversation:
        Utilisateur: je configure le wifi
        Assistant: allez dans paramètres réseau
        Utilisateur: il demande un truc, c'est quoi ?

        Requête reformulée:
        Que signifie la demande affichée lors de la configuration du Wi-Fi ?

        ---

        Conversation:
        Utilisateur: comment accéder à l'application ?
        Assistant: utilisez votre identifiant et mot de passe
        Utilisateur: et après ?

        Requête reformulée:
        Quelles sont les étapes après s’être connecté à l’application ?

        ---

        HISTORIQUE:
        {hist_text}

        REQUÊTE ACTUELLE:
        {query}

        FORMAT DE SORTIE:
        {output_format}

        REQUISE:
        Requête reformulée :
        """.strip()


class OllamaRewriter:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        # Test connection
        ollama.chat(model=model_name, messages=[{"role": "user", "content": "test"}], think=False)

    def rewrite(self, query: str, history: Optional[List[Dict]] = None, verbose: bool = False) -> Union[str, Dict]:
        history = history or []
        prompt = _build_prompt(query, history, verbose)
        
        start_time = time.time()
        response = ollama.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 256},
            think=False
        )
        elapsed = time.time() - start_time
        
        text = response['message']['content'].strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        
        if not lines:
            return "" if not verbose else {"rewritten": "", "explanation": "", "time_s": elapsed}
        
        if verbose:
            return {"rewritten": lines[0], "explanation": " ".join(lines[1:]), "time_s": elapsed}
        
        return lines[0]


if __name__ == "__main__":
    rewriter = OllamaRewriter()
    history = [
        {"role": "user", "content": "je veux créer un nouvel utilisateur"},
        {"role": "assistant", "content": "Allez dans Administration > Utilisateurs, puis cliquez sur 'Ajouter'."},

        {"role": "user", "content": "ok j'y suis"},
        {"role": "assistant", "content": "Parfait. Remplissez les champs obligatoires comme nom et email."},

        {"role": "user", "content": "et pour le rôle ?"},
        {"role": "assistant", "content": "Vous pouvez choisir entre Admin, Manager ou Utilisateur standard."},

        {"role": "user", "content": "je dois mettre quoi si c'est quelqu'un du support ?"},
        {"role": "assistant", "content": "Dans ce cas, choisissez généralement 'Manager' ou un rôle personnalisé si disponible."},
    ]
    query = "et après ?"
    print("Simple:", rewriter.rewrite(query, history, verbose=False))
    print("Verbose:", rewriter.rewrite(query, history, verbose=True))