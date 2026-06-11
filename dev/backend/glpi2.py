"""
=============================================================================
GLPI API — Tests complets (version corrigée)
=============================================================================
Lance : uvicorn glpi_test_v2:app --reload --port 8001
Accède : http://localhost:8001/docs

CORRECTIONS vs version originale :
  1. verify=False  → accepte les certificats auto-signés
  2. follow_redirects=False sur le premier appel → on détecte le redirect
     HTTP→HTTPS et on suit manuellement avec le bon URL
  3. HTTPS testé en priorité
  4. Timeout augmenté à 15s
  5. Meilleure gestion des erreurs SSL
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

# =============================================================================
# CONFIGURATION
# =============================================================================
GLPI_IP       = "10.118.2.100"
APP_TOKEN     = "gZsG9kWd8ZKdaPnDhk35mgIBGlIVDrOjYIuvCp8Y"
USER_TOKEN    = "iUZkULz7CtJmFs1c0qcqCw1EF3utKUQ2GCaRiNYL"
GLPI_USER     = "chatbot"
GLPI_PASSWORD = "iUZkULz7CtJmFs1c0qcqCw1EF3utKUQ2GCaRiNYL"
TIMEOUT       = 15

# IMPORTANT : on tente HTTPS en priorité (cause principale du SSL timeout)
# Si GLPI est en HTTP pur sans redirect, changer GLPI_BASE_URL en http://
GLPI_BASE_URL = f"https://{GLPI_IP}/glpi/apirest.php"
GLPI_HTTP_URL = f"http://{GLPI_IP}/glpi/apirest.php"
# =============================================================================

app = FastAPI(
    title="GLPI Connection Tester v2",
    description="Debug complet GLPI REST API — SSL corrigé",
    version="2.0.0"
)


# =============================================================================
# HELPERS
# =============================================================================

def ok(step: str, detail: Any) -> dict:
    return {"status": "✅ OK", "step": step, "detail": detail}

def fail(step: str, detail: Any) -> dict:
    return {"status": "❌ FAIL", "step": step, "detail": detail}


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw_text": r.text[:500]}


def _b64(user: str, pwd: str) -> str:
    return base64.b64encode(f"{user}:{pwd}".encode()).decode()


def _glpi_hint(status: int, body: Any) -> str:
    if isinstance(body, list) and len(body) == 2:
        code = body[0]
        hints = {
            "ERROR_APP_TOKEN_PARAMETERS_MISSING":    "App-Token manquant dans les headers.",
            "ERROR_WRONG_APP_TOKEN_PARAMETER":       "App-Token incorrect.",
            "ERROR_LOGIN_PARAMETERS_MISSING":        "user_token ou credentials manquants.",
            "ERROR_LOGIN_WITH_CREDENTIALS_DISABLED": "Auth par login/mdp désactivée dans GLPI → utiliser user_token.",
            "ERROR_GLPI_LOGIN":                      "Login GLPI échoué — mauvais user/mdp.",
            "ERROR_SESSION_TOKEN_INVALID":           "Session token invalide ou expiré.",
            "ERROR_RIGHT_MISSING":                   "Droits insuffisants.",
            "ERROR_ITEM_NOT_FOUND":                  "Ressource introuvable.",
        }
        return hints.get(code, f"[GLPI {code}] {body[1]}")
    return {
        400: "Requête malformée.",
        401: "Non autorisé — token invalide ou expiré.",
        403: "Accès refusé — droits insuffisants.",
        404: "URL introuvable — vérifie le chemin GLPI.",
        500: "Erreur serveur GLPI.",
    }.get(status, f"HTTP {status}")


def _get_client() -> httpx.Client:
    """Client httpx configuré : verify=False pour les certs auto-signés."""
    return httpx.Client(verify=False, timeout=TIMEOUT, follow_redirects=True)


def _get_session_token() -> tuple[str | None, str]:
    """
    Retourne (session_token, base_url_qui_a_marché).
    Essaie user_token sur HTTPS puis HTTP.
    Tombe en Basic Auth si user_token échoue.
    """
    with _get_client() as client:
        for base_url in [GLPI_BASE_URL, GLPI_HTTP_URL]:
            for auth_headers in [
                {"Authorization": f"user_token {USER_TOKEN}", "App-Token": APP_TOKEN, "Content-Type": "application/json"},
                {"Authorization": f"Basic {_b64(GLPI_USER, GLPI_PASSWORD)}", "App-Token": APP_TOKEN, "Content-Type": "application/json"},
            ]:
                try:
                    r = client.get(f"{base_url}/initSession", headers=auth_headers)
                    body = _safe_json(r)
                    if r.status_code == 200 and isinstance(body, dict) and "session_token" in body:
                        return body["session_token"], base_url
                except Exception:
                    pass
    return None, ""


def _kill_session(session_token: str, base_url: str) -> None:
    try:
        with _get_client() as client:
            client.get(
                f"{base_url}/killSession",
                headers={"Session-Token": session_token, "App-Token": APP_TOKEN},
            )
    except Exception:
        pass


# =============================================================================
# ÉTAPE 1 — RÉSEAU
# =============================================================================
@app.get("/test/1-network", tags=["Tests"], summary="Étape 1 · Réseau (HTTP + HTTPS)")
def test_network():
    """Vérifie DNS, TCP port 80 et 443, et GET HTTP/HTTPS de base."""
    results = []

    # DNS
    try:
        ip = socket.gethostbyname(GLPI_IP)
        results.append(ok("DNS résolution", {"hostname": GLPI_IP, "resolved_ip": ip}))
    except socket.gaierror as e:
        results.append(fail("DNS résolution", str(e)))

    # TCP port 80 + 443
    for port in [80, 443]:
        try:
            start = time.time()
            s = socket.create_connection((GLPI_IP, port), timeout=5)
            s.close()
            ms = round((time.time() - start) * 1000, 2)
            results.append(ok(f"TCP port {port}", {"latency_ms": ms}))
        except Exception as e:
            results.append(fail(f"TCP port {port}", str(e)))

    # GET HTTP (sans redirect pour voir si redirect vers HTTPS)
    try:
        with _get_client() as client:
            r = client.get(f"http://{GLPI_IP}/glpi/", follow_redirects=False)
            detail = {
                "status_code": r.status_code,
                "location": r.headers.get("location", "—"),
                "server": r.headers.get("server", "—"),
            }
            if r.status_code in (301, 302, 307, 308):
                detail["info"] = "⚠️ Redirect HTTP→HTTPS détecté — cause probable du SSL timeout"
            results.append(ok("HTTP GET /glpi/ (sans redirect)", detail))
    except Exception as e:
        results.append(fail("HTTP GET /glpi/", str(e)))

    # GET HTTPS (verify=False)
    try:
        with _get_client() as client:
            r = client.get(f"https://{GLPI_IP}/glpi/", follow_redirects=True)
            results.append(ok("HTTPS GET /glpi/ (cert auto-signé accepté)", {
                "status_code": r.status_code,
                "server": r.headers.get("server", "—"),
            }))
    except Exception as e:
        results.append(fail("HTTPS GET /glpi/", str(e)))

    status = 200 if all(r["status"].startswith("✅") for r in results) else 207
    return JSONResponse(status_code=status, content={"results": results})


# =============================================================================
# ÉTAPE 2 — INIT SESSION user_token
# =============================================================================
@app.get("/test/2-init-session-token", tags=["Tests"], summary="Étape 2a · initSession user_token")
def test_init_session_token():
    """Teste initSession avec user_token sur HTTPS puis HTTP."""
    headers = {
        "Authorization": f"user_token {USER_TOKEN}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    results = []
    with _get_client() as client:
        for base_url in [GLPI_BASE_URL, GLPI_HTTP_URL]:
            try:
                r = client.get(f"{base_url}/initSession", headers=headers)
                body = _safe_json(r)
                if r.status_code == 200 and isinstance(body, dict) and "session_token" in body:
                    results.append(ok(f"initSession user_token ({base_url})", {
                        "session_token": body["session_token"],
                        "http_status": r.status_code,
                        "url_finale": str(r.url),  # URL après redirect éventuel
                    }))
                    _kill_session(body["session_token"], base_url)
                else:
                    results.append(fail(f"initSession user_token ({base_url})", {
                        "http_status": r.status_code,
                        "body": body,
                        "hint": _glpi_hint(r.status_code, body),
                    }))
            except httpx.SSLError as e:
                results.append(fail(f"initSession user_token ({base_url})", {
                    "erreur": "SSLError",
                    "detail": str(e),
                    "conseil": "Le cert est invalide même avec verify=False — contacter l'admin GLPI.",
                }))
            except Exception as e:
                results.append(fail(f"initSession user_token ({base_url})", str(e)))

    any_ok = any(r["status"].startswith("✅") for r in results)
    return JSONResponse(status_code=200 if any_ok else 207, content={"results": results})


# =============================================================================
# ÉTAPE 3 — INIT SESSION Basic Auth
# =============================================================================
@app.get("/test/3-init-session-basic", tags=["Tests"], summary="Étape 2b · initSession Basic Auth")
def test_init_session_basic():
    """Teste initSession avec Basic Auth sur HTTPS puis HTTP."""
    headers = {
        "Authorization": f"Basic {_b64(GLPI_USER, GLPI_PASSWORD)}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    results = []
    with _get_client() as client:
        for base_url in [GLPI_BASE_URL, GLPI_HTTP_URL]:
            try:
                r = client.get(f"{base_url}/initSession", headers=headers)
                body = _safe_json(r)
                if r.status_code == 200 and isinstance(body, dict) and "session_token" in body:
                    results.append(ok(f"initSession Basic ({base_url})", {
                        "session_token": body["session_token"],
                        "http_status": r.status_code,
                    }))
                    _kill_session(body["session_token"], base_url)
                else:
                    results.append(fail(f"initSession Basic ({base_url})", {
                        "http_status": r.status_code,
                        "body": body,
                        "hint": _glpi_hint(r.status_code, body),
                    }))
            except Exception as e:
                results.append(fail(f"initSession Basic ({base_url})", str(e)))

    any_ok = any(r["status"].startswith("✅") for r in results)
    return JSONResponse(status_code=200 if any_ok else 207, content={"results": results})


# =============================================================================
# ÉTAPE 4 — FETCH DONNÉES
# =============================================================================
@app.get("/test/4-fetch-data", tags=["Tests"], summary="Étape 3 · Fetch données GLPI")
def test_fetch_data():
    """Récupère profils, tickets et utilisateurs une fois la session ouverte."""
    session_token, base_url = _get_session_token()
    if not session_token:
        return JSONResponse(status_code=401, content={
            "results": [fail("Fetch data", "Impossible d'ouvrir une session — voir étapes 2 et 3")]
        })

    results = []
    headers = {"Session-Token": session_token, "App-Token": APP_TOKEN, "Content-Type": "application/json"}

    endpoints = [
        ("getMyProfiles",       f"{base_url}/getMyProfiles"),
        ("getActiveProfile",    f"{base_url}/getActiveProfile"),
        ("Ticket (5 derniers)", f"{base_url}/Ticket?range=0-4&sort=id&order=DESC"),
        ("User (5 premiers)",   f"{base_url}/User?range=0-4"),
    ]

    with _get_client() as client:
        for name, url in endpoints:
            try:
                r = client.get(url, headers=headers)
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
                        "body": body,
                        "hint": _glpi_hint(r.status_code, body),
                    }))
            except Exception as e:
                results.append(fail(f"GET {name}", str(e)))

    _kill_session(session_token, base_url)
    status = 200 if all(r["status"].startswith("✅") for r in results) else 207
    return JSONResponse(status_code=status, content={"results": results, "base_url_utilisée": base_url})


# =============================================================================
# ÉTAPE 5 — CRÉER UN TICKET DE TEST
# =============================================================================
@app.post("/test/5-create-ticket", tags=["Tests"], summary="Étape 4 · Créer un ticket de test")
def test_create_ticket():
    """Crée un ticket [CHATBOT-TEST] pour valider les droits en écriture."""
    session_token, base_url = _get_session_token()
    if not session_token:
        return JSONResponse(status_code=401, content={
            "results": [fail("Create ticket", "Impossible d'ouvrir une session")]
        })

    headers = {"Session-Token": session_token, "App-Token": APP_TOKEN, "Content-Type": "application/json"}
    payload = {
        "input": {
            "name": "[CHATBOT-TEST] Ticket de connexion automatique",
            "content": (
                f"Ticket créé par le script de test chatbot.\n"
                f"Timestamp : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "Vous pouvez supprimer ce ticket."
            ),
            "type": 1, "urgency": 1, "impact": 1, "priority": 1, "status": 1,
        }
    }

    try:
        with _get_client() as client:
            r = client.post(f"{base_url}/Ticket", headers=headers, json=payload)
        body = _safe_json(r)
        if r.status_code in (200, 201) and "id" in body:
            result = ok("Création ticket", {"ticket_id": body["id"], "http_status": r.status_code})
        else:
            result = fail("Création ticket", {"http_status": r.status_code, "body": body, "hint": _glpi_hint(r.status_code, body)})
    except Exception as e:
        result = fail("Création ticket", str(e))

    _kill_session(session_token, base_url)
    return JSONResponse(content={"results": [result]})


# =============================================================================
# ÉTAPE 6 — RECHERCHE TICKET
# =============================================================================
@app.get("/test/6-search-ticket", tags=["Tests"], summary="Étape 5 · Rechercher un ticket")
def test_search_ticket(keyword: str = "imprimante"):
    """Simule une recherche de ticket par mot-clé (titre + description)."""
    session_token, base_url = _get_session_token()
    if not session_token:
        return JSONResponse(status_code=401, content={
            "results": [fail("Search ticket", "Impossible d'ouvrir une session")]
        })

    headers = {"Session-Token": session_token, "App-Token": APP_TOKEN, "Content-Type": "application/json"}
    params = {
        "criteria[0][field]": 1, "criteria[0][searchtype]": "contains", "criteria[0][value]": keyword,
        "criteria[1][link]": "OR",
        "criteria[1][field]": 21, "criteria[1][searchtype]": "contains", "criteria[1][value]": keyword,
        "range": "0-9",
        "forcedisplay[0]": 1, "forcedisplay[1]": 21, "forcedisplay[2]": 12, "forcedisplay[3]": 19,
    }

    try:
        with _get_client() as client:
            r = client.get(f"{base_url}/search/Ticket", headers=headers, params=params)
        body = _safe_json(r)
        if r.status_code in (200, 206):
            result = ok("Recherche ticket", {
                "keyword": keyword,
                "total_found": body.get("totalcount", 0),
                "http_status": r.status_code,
                "results_sample": body.get("data", [])[:3],
            })
        else:
            result = fail("Recherche ticket", {"http_status": r.status_code, "body": body, "hint": _glpi_hint(r.status_code, body)})
    except Exception as e:
        result = fail("Recherche ticket", str(e))

    _kill_session(session_token, base_url)
    return JSONResponse(content={"results": [result]})


# =============================================================================
# ROUTE MASTER
# =============================================================================
@app.get("/test/all", tags=["Master"], summary="🚀 Tous les tests")
def run_all_tests():
    """Lance toutes les étapes et retourne un rapport complet."""
    def _call(fn):
        r = fn()
        return json.loads(r.body)

    report = {
        "etape_1_reseau":        _call(test_network),
        "etape_2a_init_token":   _call(test_init_session_token),
        "etape_2b_init_basic":   _call(test_init_session_basic),
        "etape_3_fetch":         _call(test_fetch_data),
        "etape_4_create_ticket": _call(test_create_ticket),
        "etape_5_search":        _call(lambda: test_search_ticket("test")),
    }

    all_ok = all(
        any(r.get("status", "").startswith("✅") for r in v.get("results", []))
        for v in report.values()
        if isinstance(v, dict) and "results" in v
    )
    report["__summary__"] = {
        "global": "✅ Tout OK — prêt pour l'intégration !" if all_ok
                  else "❌ Des erreurs détectées — voir les étapes ci-dessus",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return JSONResponse(content=report)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("glpi_test_v2:app", host="0.0.0.0", port=8001, reload=True)