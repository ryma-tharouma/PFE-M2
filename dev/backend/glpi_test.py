"""
=============================================================================
GLPI API - Fichier de test & debug complet
=============================================================================
Tester chaque étape de la connexion avant intégration dans le chatbot.
Lancer : uvicorn glpi_test:app --reload --port 8001
Accéder : http://localhost:8001/docs  (Swagger UI)
=============================================================================
"""

import base64
import json
import socket
import time
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# =============================================================================
# CONFIGURATION GLPI
# =============================================================================
GLPI_BASE_URL   = "http://10.118.2.100/glpi/apirest.php"
APP_TOKEN       = "gZsG9kWd8ZKdaPnDhk35mgIBGlIVDrOjYIuvCp8Y"
USER_TOKEN      = "iUZkULz7CtJmFs1c0qcqCw1EF3utKUQ2GCaRiNYL"
GLPI_USER       = "chatbot"
GLPI_PASSWORD   = "iUZkULz7CtJmFs1c0qcqCw1EF3utKUQ2GCaRiNYL"  # mdp = api token selon admin
GLPI_IP         = "10.118.2.100"
GLPI_DNS        = "10.118.2.100"   # ← remplacer par le DNS si disponible

TIMEOUT         = 10  # secondes

# =============================================================================
app = FastAPI(
    title="GLPI Connection Tester",
    description="Debug complet de la connexion GLPI REST API",
    version="1.0.0"
)

# =============================================================================
# HELPERS
# =============================================================================

def ok(step: str, detail: Any) -> dict:
    return {"status": "✅ OK", "step": step, "detail": detail}

def fail(step: str, detail: Any) -> dict:
    return {"status": "❌ FAIL", "step": step, "detail": detail}

def warn(step: str, detail: Any) -> dict:
    return {"status": "⚠️  WARN", "step": step, "detail": detail}


def base64_credentials(user: str, password: str) -> str:
    raw = f"{user}:{password}"
    return base64.b64encode(raw.encode()).decode()


# =============================================================================
# ÉTAPE 1 — RÉSOLUTION DNS / PING
# =============================================================================
@app.get("/test/1-network", tags=["Tests"], summary="Étape 1 · Réseau & DNS")
def test_network():
    """
    Vérifie :
    - la résolution DNS du serveur GLPI
    - que le port 80 est joignable (TCP connect)
    - le temps de réponse HTTP de base
    """
    results = []

    # 1a — résolution DNS
    try:
        ip = socket.gethostbyname(GLPI_IP)
        results.append(ok("DNS résolution", {"hostname": GLPI_IP, "resolved_ip": ip}))
    except socket.gaierror as e:
        results.append(fail("DNS résolution", str(e)))

    # 1b — TCP connect sur port 80
    try:
        start = time.time()
        sock = socket.create_connection((GLPI_IP, 80), timeout=TIMEOUT)
        sock.close()
        ms = round((time.time() - start) * 1000, 2)
        results.append(ok("TCP port 80", {"latency_ms": ms}))
    except Exception as e:
        results.append(fail("TCP port 80", str(e)))

    # 1c — GET HTTP basique sur l'URL racine
    try:
        start = time.time()
        r = httpx.get(f"http://{GLPI_IP}/glpi/", timeout=TIMEOUT, follow_redirects=True)
        ms = round((time.time() - start) * 1000, 2)
        results.append(ok("HTTP GET /glpi/", {
            "status_code": r.status_code,
            "latency_ms": ms,
            "server_header": r.headers.get("server", "—"),
        }))
    except Exception as e:
        results.append(fail("HTTP GET /glpi/", str(e)))

    status = 200 if all(r["status"].startswith("✅") for r in results) else 207
    return JSONResponse(status_code=status, content={"results": results})


# =============================================================================
# ÉTAPE 2 — INIT SESSION (méthode user_token)
# =============================================================================
@app.get("/test/2-init-session-token", tags=["Tests"], summary="Étape 2a · initSession via user_token")
def test_init_session_token():
    """
    Authentification GLPI recommandée :
    Authorization: user_token XXXX
    App-Token: XXXX
    """
    headers = {
        "Authorization": f"user_token {USER_TOKEN}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        r = httpx.get(f"{GLPI_BASE_URL}/initSession", headers=headers, timeout=TIMEOUT)
        body = _safe_json(r)
        if r.status_code == 200 and "session_token" in body:
            return JSONResponse(content={
                "results": [ok("initSession (user_token)", {
                    "session_token": body["session_token"],
                    "http_status": r.status_code,
                    "raw_response": body,
                })]
            })
        else:
            return JSONResponse(status_code=207, content={
                "results": [fail("initSession (user_token)", {
                    "http_status": r.status_code,
                    "raw_response": body,
                    "hint": _glpi_error_hint(r.status_code, body),
                })]
            })
    except Exception as e:
        return JSONResponse(status_code=500, content={"results": [fail("initSession (user_token)", str(e))]})


# =============================================================================
# ÉTAPE 3 — INIT SESSION (méthode Basic Auth)
# =============================================================================
@app.get("/test/3-init-session-basic", tags=["Tests"], summary="Étape 2b · initSession via Basic Auth")
def test_init_session_basic():
    """
    Alternative : Basic Auth base64(user:password)
    Utile si le user_token n'est pas activé sur le compte.
    """
    credentials = base64_credentials(GLPI_USER, GLPI_PASSWORD)
    headers = {
        "Authorization": f"Basic {credentials}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        r = httpx.get(f"{GLPI_BASE_URL}/initSession", headers=headers, timeout=TIMEOUT)
        body = _safe_json(r)
        if r.status_code == 200 and "session_token" in body:
            return JSONResponse(content={
                "results": [ok("initSession (Basic Auth)", {
                    "session_token": body["session_token"],
                    "http_status": r.status_code,
                    "raw_response": body,
                    "credentials_used": f"{GLPI_USER}:***",
                })]
            })
        else:
            return JSONResponse(status_code=207, content={
                "results": [fail("initSession (Basic Auth)", {
                    "http_status": r.status_code,
                    "raw_response": body,
                    "hint": _glpi_error_hint(r.status_code, body),
                })]
            })
    except Exception as e:
        return JSONResponse(status_code=500, content={"results": [fail("initSession (Basic Auth)", str(e))]})


# =============================================================================
# ÉTAPE 4 — FETCH DONNÉES (tickets, utilisateurs, etc.)
# =============================================================================
@app.get("/test/4-fetch-data", tags=["Tests"], summary="Étape 3 · Fetch données GLPI")
def test_fetch_data():
    """
    Une fois la session ouverte, récupère :
    - /Ticket       → liste des tickets
    - /User         → liste des utilisateurs
    - /getMyProfiles → profils du compte chatbot
    """
    session_token = _get_session_token()
    if session_token is None:
        return JSONResponse(status_code=401, content={
            "results": [fail("Fetch data", "Impossible d'ouvrir une session — voir étapes 2 et 3")]
        })

    results = []
    base_headers = {
        "Session-Token": session_token,
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }

    endpoints = [
        ("getMyProfiles",  f"{GLPI_BASE_URL}/getMyProfiles"),
        ("getActiveProfile", f"{GLPI_BASE_URL}/getActiveProfile"),
        ("Ticket (5 derniers)", f"{GLPI_BASE_URL}/Ticket?range=0-4&sort=id&order=DESC"),
        ("User (5 premiers)", f"{GLPI_BASE_URL}/User?range=0-4"),
    ]

    for name, url in endpoints:
        try:
            r = httpx.get(url, headers=base_headers, timeout=TIMEOUT)
            body = _safe_json(r)
            if r.status_code in (200, 206):
                results.append(ok(f"GET {name}", {
                    "http_status": r.status_code,
                    "count": len(body) if isinstance(body, list) else "—",
                    "sample": body[:2] if isinstance(body, list) else body,
                }))
            else:
                results.append(fail(f"GET {name}", {
                    "http_status": r.status_code,
                    "raw_response": body,
                    "hint": _glpi_error_hint(r.status_code, body),
                }))
        except Exception as e:
            results.append(fail(f"GET {name}", str(e)))

    _kill_session(session_token)
    status = 200 if all(r["status"].startswith("✅") for r in results) else 207
    return JSONResponse(status_code=status, content={"results": results, "session_token_used": session_token})


# =============================================================================
# ÉTAPE 5 — CRÉER UN TICKET DE TEST
# =============================================================================
@app.post("/test/5-create-ticket", tags=["Tests"], summary="Étape 4 · Créer un ticket de test")
def test_create_ticket():
    """
    Crée un ticket de test dans GLPI pour valider les droits en écriture.
    Le ticket sera tagué [CHATBOT-TEST] pour pouvoir le retrouver / supprimer.
    """
    session_token = _get_session_token()
    if session_token is None:
        return JSONResponse(status_code=401, content={
            "results": [fail("Create ticket", "Impossible d'ouvrir une session")]
        })

    headers = {
        "Session-Token": session_token,
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }

    payload = {
        "input": {
            "name": "[CHATBOT-TEST] Ticket de connexion automatique",
            "content": (
                "Ce ticket a été créé automatiquement par le script de test "
                "de connexion du chatbot RAG.\n\n"
                f"Timestamp : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "Vous pouvez supprimer ce ticket."
            ),
            "type": 1,          # 1 = Incident, 2 = Demande
            "urgency": 1,       # 1 = Très basse
            "impact": 1,
            "priority": 1,
            "status": 1,        # 1 = Nouveau
        }
    }

    try:
        r = httpx.post(
            f"{GLPI_BASE_URL}/Ticket",
            headers=headers,
            json=payload,
            timeout=TIMEOUT,
        )
        body = _safe_json(r)
        if r.status_code in (200, 201) and "id" in body:
            result = ok("Création ticket", {
                "ticket_id": body["id"],
                "http_status": r.status_code,
                "raw_response": body,
                "message": f"Ticket #{body['id']} créé avec succès !",
            })
        else:
            result = fail("Création ticket", {
                "http_status": r.status_code,
                "raw_response": body,
                "hint": _glpi_error_hint(r.status_code, body),
            })
    except Exception as e:
        result = fail("Création ticket", str(e))

    _kill_session(session_token)
    return JSONResponse(content={"results": [result]})


# =============================================================================
# ÉTAPE 6 — RECHERCHE TICKET PAR MOT-CLÉ (simulation chatbot)
# =============================================================================
@app.get("/test/6-search-ticket", tags=["Tests"], summary="Étape 5 · Rechercher un ticket (simulation chatbot)")
def test_search_ticket(keyword: str = "imprimante"):
    """
    Simule ce que fera le chatbot : chercher un ticket GLPI par mot-clé.
    Paramètre : keyword (défaut = 'imprimante')
    """
    session_token = _get_session_token()
    if session_token is None:
        return JSONResponse(status_code=401, content={
            "results": [fail("Search ticket", "Impossible d'ouvrir une session")]
        })

    headers = {
        "Session-Token": session_token,
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }

    # GLPI search criteria
    params = {
        "criteria[0][field]": 1,           # field 1 = Titre
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]": keyword,
        "criteria[1][link]": "OR",
        "criteria[1][field]": 21,          # field 21 = Description
        "criteria[1][searchtype]": "contains",
        "criteria[1][value]": keyword,
        "range": "0-9",
        "forcedisplay[0]": 1,              # Titre
        "forcedisplay[1]": 21,             # Description
        "forcedisplay[2]": 12,             # Statut
        "forcedisplay[3]": 19,             # Date de création
    }

    try:
        r = httpx.get(
            f"{GLPI_BASE_URL}/search/Ticket",
            headers=headers,
            params=params,
            timeout=TIMEOUT,
        )
        body = _safe_json(r)
        if r.status_code in (200, 206):
            count = body.get("totalcount", 0)
            result = ok("Recherche ticket", {
                "keyword": keyword,
                "total_found": count,
                "http_status": r.status_code,
                "results_sample": body.get("data", [])[:3],
            })
        else:
            result = fail("Recherche ticket", {
                "http_status": r.status_code,
                "raw_response": body,
                "hint": _glpi_error_hint(r.status_code, body),
            })
    except Exception as e:
        result = fail("Recherche ticket", str(e))

    _kill_session(session_token)
    return JSONResponse(content={"results": [result]})


# =============================================================================
# ROUTE MASTER — tous les tests d'un coup
# =============================================================================
@app.get("/test/all", tags=["Master"], summary="🚀 Lancer TOUS les tests")
def run_all_tests():
    """
    Lance les étapes 1 → 5 en séquence et retourne un rapport complet.
    C'est la route principale à utiliser pour le debug initial.
    """
    report = {}

    # Étape 1 — réseau
    report["etape_1_reseau"] = _call_internal(test_network)

    # Étape 2a — init session user_token
    report["etape_2a_init_token"] = _call_internal(test_init_session_token)

    # Étape 2b — init session basic auth
    report["etape_2b_init_basic"] = _call_internal(test_init_session_basic)

    # Étape 3 — fetch données
    report["etape_3_fetch"] = _call_internal(test_fetch_data)

    # Étape 4 — créer ticket
    report["etape_4_create_ticket"] = _call_internal(test_create_ticket)

    # Étape 5 — recherche
    report["etape_5_search"] = _call_internal(lambda: test_search_ticket("test"))

    # Résumé
    all_ok = all(
        any(r.get("status", "").startswith("✅") for r in v.get("results", []))
        for v in report.values()
        if isinstance(v, dict) and "results" in v
    )
    report["__summary__"] = {
        "global": "✅ Tout est OK — prêt pour l'intégration !" if all_ok
                  else "❌ Des erreurs détectées — voir les étapes ci-dessus",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return JSONResponse(content=report)


# =============================================================================
# UTILITAIRES INTERNES
# =============================================================================

def _safe_json(response: httpx.Response) -> Any:
    """Parse JSON proprement, retourne le texte brut si échec."""
    try:
        return response.json()
    except Exception:
        return {"raw_text": response.text[:500]}


def _get_session_token() -> str | None:
    """
    Essaie user_token d'abord, puis Basic Auth.
    Retourne le session_token ou None.
    """
    # Tentative 1 — user_token
    try:
        headers = {
            "Authorization": f"user_token {USER_TOKEN}",
            "App-Token": APP_TOKEN,
            "Content-Type": "application/json",
        }
        r = httpx.get(f"{GLPI_BASE_URL}/initSession", headers=headers, timeout=TIMEOUT)
        body = _safe_json(r)
        if r.status_code == 200 and "session_token" in body:
            return body["session_token"]
    except Exception:
        pass

    # Tentative 2 — Basic Auth
    try:
        credentials = base64_credentials(GLPI_USER, GLPI_PASSWORD)
        headers = {
            "Authorization": f"Basic {credentials}",
            "App-Token": APP_TOKEN,
            "Content-Type": "application/json",
        }
        r = httpx.get(f"{GLPI_BASE_URL}/initSession", headers=headers, timeout=TIMEOUT)
        body = _safe_json(r)
        if r.status_code == 200 and "session_token" in body:
            return body["session_token"]
    except Exception:
        pass

    return None


def _kill_session(session_token: str) -> None:
    """Ferme proprement la session GLPI."""
    try:
        httpx.get(
            f"{GLPI_BASE_URL}/killSession",
            headers={
                "Session-Token": session_token,
                "App-Token": APP_TOKEN,
            },
            timeout=5,
        )
    except Exception:
        pass


def _glpi_error_hint(status_code: int, body: Any) -> str:
    """Donne un hint lisible selon le code d'erreur GLPI."""
    hints = {
        400: "Requête malformée — vérifier les headers ou le payload JSON.",
        401: "Non autorisé — user_token ou app_token invalide / expiré.",
        403: "Accès refusé — le compte 'chatbot' n'a pas les droits suffisants dans GLPI.",
        404: "Endpoint introuvable — vérifier l'URL de base GLPI.",
        405: "Méthode HTTP non autorisée.",
        500: "Erreur serveur GLPI — vérifier les logs PHP de GLPI.",
        0:   "Pas de réponse — serveur inaccessible ou timeout réseau.",
    }
    # Erreurs spécifiques GLPI dans le body
    if isinstance(body, list) and len(body) == 2:
        code, msg = body[0], body[1]
        glpi_hints = {
            "ERROR_APP_TOKEN_PARAMETERS_MISSING": "App-Token manquant dans les headers.",
            "ERROR_WRONG_APP_TOKEN_PARAMETER":    "App-Token incorrect.",
            "ERROR_LOGIN_PARAMETERS_MISSING":     "user_token ou credentials manquants.",
            "ERROR_LOGIN_WITH_CREDENTIALS_DISABLED": "Auth par login/mdp désactivée dans GLPI → utiliser user_token.",
            "ERROR_GLPI_LOGIN":                   "Login GLPI échoué — mauvais user/mdp.",
            "ERROR_SESSION_TOKEN_INVALID":        "Session token invalide ou expiré.",
            "ERROR_RIGHT_MISSING":                "Droits insuffisants pour cette action.",
            "ERROR_ITEM_NOT_FOUND":               "Ressource introuvable.",
        }
        if code in glpi_hints:
            return f"[GLPI {code}] {glpi_hints[code]}"
        return f"[GLPI {code}] {msg}"

    return hints.get(status_code, f"HTTP {status_code} — consulter la doc GLPI REST API.")


def _call_internal(fn) -> dict:
    """Appelle une fonction de test et retourne son contenu JSON."""
    try:
        response = fn()
        return json.loads(response.body)
    except Exception as e:
        return {"results": [fail("internal_call", str(e))]}


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("glpi_test:app", host="0.0.0.0", port=8001, reload=True)