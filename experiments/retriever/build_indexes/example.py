from sentence_transformers import SentenceTransformer
import numpy as np


# ===============================
# Data (French, app manual style)
# ===============================
queries = [
    "Comment réinitialiser mon mot de passe ?",
    "Où trouver l’historique des paiements dans l’application ?",
    "L’application se bloque au démarrage, que faire ?",
]

documents = [
    "Pour réinitialiser votre mot de passe, ouvrez Paramètres > Compte > Mot de passe.",
    "Vous pouvez consulter l’historique des paiements dans Facturation > Historique.",
    "Si l’application se bloque, essayez de la mettre à jour ou de la réinstaller.",
    "Les notifications peuvent être activées dans Paramètres > Notifications.",
]

# Prompt for queries (Qwen + Mistral only)
QUERY_PROMPT = "Instructions: pour répondre à la question, trouvez les sections pertinentes dans le manuel de l’application. Voici la question : "


def cosine_sim_matrix(a, b):
    # a: (n, d), b: (m, d)
    a = a / np.linalg.norm(a, axis=1, keepdims=True)
    b = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a @ b.T


# ===============================
# 1) BGE (no prompt)
# ===============================
bge = SentenceTransformer("BAAI/bge-m3")
bge.max_seq_length = 4000

bge_q = bge.encode(queries, normalize_embeddings=True)
bge_d = bge.encode(documents, normalize_embeddings=True)
bge_scores = cosine_sim_matrix(bge_q, bge_d)

print("\n[BGE] cosine similarity:")
print(bge_scores)


# ===============================
# 2) Qwen (prompt queries)
# ===============================
qwen = SentenceTransformer("Qwen/Qwen3-Embedding-8B")
qwen.max_seq_length = 4000

qwen_queries = [QUERY_PROMPT + q for q in queries]
qwen_q = qwen.encode(qwen_queries, normalize_embeddings=True)
qwen_d = qwen.encode(documents, normalize_embeddings=True)
qwen_scores = cosine_sim_matrix(qwen_q, qwen_d)

print("\n[Qwen] cosine similarity:")
print(qwen_scores)


# ===============================
# 3) Mistral (prompt queries)
# ===============================
mistral = SentenceTransformer("intfloat/e5-mistral-7b-instruct")
mistral.max_seq_length = 4000

mistral_queries = [QUERY_PROMPT + q for q in queries]
mistral_q = mistral.encode(mistral_queries, normalize_embeddings=True)
mistral_d = mistral.encode(documents, normalize_embeddings=True)
mistral_scores = cosine_sim_matrix(mistral_q, mistral_d)

print("\n[Mistral] cosine similarity:")
print(mistral_scores)