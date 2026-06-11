"""
=============================================================================
GLPI AUTH TEST v4 — diagnostic complet HTTP/HTTPS + 2 endpoints
=============================================================================
Lance : uvicorn glpi_auth_test:app --reload --port 8002
Accède : http://localhost:8002/docs
=============================================================================
"""

import base64
import time
import socket
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
GLPI_PASSWORD = "iUZkULz7CtJmFs1c0qcqCw1EF3utKUQ2GCaRiNYL"  # = USER_TOKEN
TIMEOUT       = 10

# Les 4 combinaisons à tester : 2 protocoles x 2 endpoints
URLS_TO_TEST = [
    f"http://{GLPI_IP}/glpi/apirest.php",
    f"http://{GLPI_IP}/glpi/api",
    f"https://{GLPI_IP}/glpi/apirest.php",
    f"https://{GLPI_IP}/glpi/api",
]
# =============================================================================

app = FastAPI(
    title="GLPI Auth Tester v4",
    description="Diagnostic complet : HTTP + HTTPS, /apirest.php + /api, user_token + Basic Auth",
    version="4.0.0"
)


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
            "ERROR_WRONG_APP_TOKEN_PARAMETER":       "App-Token incorrect — vérifie dans Administration > API.",
            "ERROR_LOGIN_PARAMETERS_MISSING":        "user_token ou credentials manquants.",
            "ERROR_LOGIN_WITH_CREDENTIALS_DISABLED": "Auth par login/mdp désactivée dans Config > API.",
            "ERROR_GLPI_LOGIN":                      "Login ou mot de passe incorrects.",
            "ERROR_SESSION_TOKEN_INVALID":           "Session token invalide ou expiré.",
            "ERROR_RIGHT_MISSING":                   "Droits insuffisants pour le compte chatbot.",
        }
        return hints.get(code, f"[GLPI {code}] {body[1]}")
    return {
        400: "Requête malformée.",
        401: "Non autorisé — token invalide.",
        403: "Accès refusé — droits insuffisants.",
        404: "URL introuvable — mauvais chemin API.",
        500: "Erreur serveur GLPI — consulter logs PHP.",
    }.get(status, f"HTTP {status} inconnu")


def _test_one_url(base_url: str, headers: dict) -> dict:
    """Teste initSession sur une URL précise."""
    result = {"url": base_url}
    try:
        r = httpx.get(
            f"{base_url}/initSession",
            headers=headers,
            timeout=TIMEOUT,
            follow_redirects=False,
            verify=False,
        )
        body = _safe_json(r)
        result["http_status"] = r.status_code
        result["body"] = body
        result["location"] = r.headers.get("location", "—")

        if r.status_code == 200 and isinstance(body, dict) and "session_token" in body:
            result["status"] = "✅ SUCCÈS"
            result["session_token"] = body["session_token"]
        elif r.status_code in (301, 302, 307, 308):
            result["status"] = "↪️  REDIRECT"
            result["conseil"] = f"GLPI redirige vers : {r.headers.get('location', '?')} — utilise directement cette URL"
        else:
            result["status"] = "❌ ECHEC"
            result["hint"] = _glpi_hint(r.status_code, body)

    except httpx.ConnectError as e:
        result["status"] = "❌ CONNEXION REFUSÉE"
        result["detail"] = str(e)
        result["conseil"] = "Le serveur refuse la connexion sur ce port/protocole."
    except httpx.TimeoutException as e:
        result["status"] = "❌ TIMEOUT"
        result["detail"] = str(e)
        result["conseil"] = (
            "Timeout SSL probable. Causes possibles :\n"
            "  1. HTTPS non activé sur ce serveur GLPI\n"
            "  2. Pare-feu bloque le port 443\n"
            "  3. Apache/Nginx pas configuré en SSL\n"
            "→ Essaie avec HTTP directement ou vérifie la config Apache du serveur GLPI."
        )
    except Exception as e:
        result["status"] = f"❌ ERREUR {type(e).__name__}"
        result["detail"] = str(e)

    return result


# =============================================================================
# ROUTE 1 — diagnostic réseau (ports + redirect)
# =============================================================================
@app.get("/auth/diagnostic", tags=["Diagnostic"], summary="1️⃣  Diagnostic réseau et ports")
def diagnostic():
    """
    Vérifie les ports 80 et 443, puis fait un GET brut sur les 4 URLs
    pour voir si GLPI répond et s'il y a des redirects.
    """
    results = {}

    # --- Test connectivité ports ---
    ports_result = {}
    for port in [80, 443]:
        try:
            start = time.time()
            s = socket.create_connection((GLPI_IP, port), timeout=5)
            s.close()
            ms = round((time.time() - start) * 1000, 2)
            ports_result[port] = {"status": "✅ ouvert", "latency_ms": ms}
        except Exception as e:
            ports_result[port] = {
                "status": "❌ fermé ou filtré",
                "detail": str(e),
                "conseil": "Port 80 fermé → HTTP impossible. Port 443 fermé → HTTPS impossible." if port == 80
                           else "Port 443 fermé → HTTPS impossible. GLPI tourne peut-être uniquement en HTTP."
            }
    results["ports"] = ports_result

    # --- GET brut sur les 4 URLs (sans initSession) ---
    url_checks = []
    for url in URLS_TO_TEST:
        try:
            r = httpx.get(url, timeout=8, follow_redirects=False, verify=False)
            url_checks.append({
                "url": url,
                "http_status": r.status_code,
                "location": r.headers.get("location", "—"),
                "server": r.headers.get("server", "—"),
                "content_type": r.headers.get("content-type", "—"),
                "body_preview": r.text[:150],
            })
        except httpx.TimeoutException:
            url_checks.append({"url": url, "status": "❌ TIMEOUT", "conseil": "Port probablement fermé ou filtré."})
        except httpx.ConnectError as e:
            url_checks.append({"url": url, "status": "❌ CONNEXION REFUSÉE", "detail": str(e)})
        except Exception as e:
            url_checks.append({"url": url, "status": f"❌ {type(e).__name__}", "detail": str(e)})

    results["urls"] = url_checks
    results["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return JSONResponse(content=results)


# =============================================================================
# ROUTE 2 — test user_token sur les 4 URLs
# =============================================================================
@app.get("/auth/user-token", tags=["Auth"], summary="2️⃣  Test user_token (4 URLs)")
def test_user_token():
    """
    Teste user_token sur les 4 combinaisons :
      - http  + /glpi/apirest.php
      - http  + /glpi/api
      - https + /glpi/apirest.php
      - https + /glpi/api
    """
    headers = {
        "Authorization": f"user_token {USER_TOKEN}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    results = [_test_one_url(url, headers) for url in URLS_TO_TEST]
    any_ok = any(r["status"].startswith("✅") for r in results)

    return JSONResponse(
        status_code=200 if any_ok else 207,
        content={
            "method": "user_token",
            "results": results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    )


# =============================================================================
# ROUTE 3 — test Basic Auth (chatbot / USER_TOKEN comme password)
# =============================================================================
@app.get("/auth/basic", tags=["Auth"], summary="3️⃣  Test Basic Auth chatbot (4 URLs)")
def test_basic_auth():
    """
    Teste Basic Auth avec :
      - login    : chatbot
      - password : USER_TOKEN (= iUZkULz7...)
    sur les 4 combinaisons d'URLs.
    """
    headers = {
        "Authorization": f"Basic {_b64(GLPI_USER, GLPI_PASSWORD)}",
        "App-Token": APP_TOKEN,
        "Content-Type": "application/json",
    }
    results = [_test_one_url(url, headers) for url in URLS_TO_TEST]
    any_ok = any(r["status"].startswith("✅") for r in results)

    return JSONResponse(
        status_code=200 if any_ok else 207,
        content={
            "method": "basic_auth",
            "results": results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    )


# =============================================================================
# ROUTE MASTER — tout en un
# =============================================================================
@app.get("/auth/all", tags=["Auth"], summary="🚀 Rapport complet (diagnostic + tous les tests)")
def auth_all():
    """
    Lance tout d'un coup :
      1. Diagnostic réseau (ports + URLs)
      2. Test user_token sur 4 URLs
      3. Test Basic Auth sur 4 URLs
    Et produit un résumé avec les URLs qui fonctionnent.
    """
    import json

    def _call(fn):
        r = fn()
        return json.loads(r.body)

    report = {
        "1_diagnostic": _call(diagnostic),
        "2_user_token": _call(test_user_token),
        "3_basic_auth": _call(test_basic_auth),
    }

    # URLs qui ont réussi
    working = []
    for method_key in ["2_user_token", "3_basic_auth"]:
        method_name = method_key.split("_", 1)[1]
        for r in report[method_key].get("results", []):
            if r.get("status", "").startswith("✅"):
                working.append({
                    "methode": method_name,
                    "url": r["url"],
                    "session_token_exemple": r.get("session_token", "—"),
                })

    # Analyse ports pour conseil
    ports = report["1_diagnostic"].get("ports", {})
    port_80_ok  = ports.get(80, {}).get("status", "").startswith("✅")
    port_443_ok = ports.get(443, {}).get("status", "").startswith("✅")

    conseil = ""
    if not port_443_ok and port_80_ok:
        conseil = (
            "⚠️  Port 443 fermé mais port 80 ouvert → GLPI tourne en HTTP pur.\n"
            "   Options :\n"
            "   A) Configure ton code pour utiliser http:// directement\n"
            "   B) Active SSL sur Apache (mod_ssl) côté serveur GLPI\n"
            "   C) Demande à l'admin réseau d'ouvrir le port 443"
        )
    elif not port_80_ok and not port_443_ok:
        conseil = "❌ Ports 80 ET 443 fermés → GLPI inaccessible depuis ta VM. Vérifie le pare-feu ou l'IP."
    elif port_443_ok:
        conseil = "Port 443 ouvert mais SSL timeout → le certificat ou Apache SSL n'est pas bien configuré."

    report["__summary__"] = {
        "port_80":  ports.get(80,  {}).get("status", "non testé"),
        "port_443": ports.get(443, {}).get("status", "non testé"),
        "urls_fonctionnelles": working if working else [],
        "global": (
            "✅ Au moins une méthode fonctionne ! Voir urls_fonctionnelles."
            if working else
            "❌ Aucune méthode ne fonctionne."
        ),
        "conseil": conseil,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return JSONResponse(content=report)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("glpi_auth_test:app", host="0.0.0.0", port=8002, reload=True)