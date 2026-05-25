Serve · SH
#!/bin/bash
# Lancer Laravel avec PHP built-in server multi-thread
# Place ce fichier dans le dossier racine Laravel et exécute : bash serve.sh

cd "$(dirname "$0")"

echo "🚀 Démarrage Laravel sur http://127.0.0.1:8001 (8 workers)"

# PHP_CLI_SERVER_WORKERS = nombre de workers parallèles
# Nécessaire pour SSE + requêtes normales en même temps
PHP_CLI_SERVER_WORKERS=8 php artisan serve --host=127.0.0.1 --port=8001

