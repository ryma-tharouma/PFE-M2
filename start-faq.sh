#!/bin/bash
# Script de démarrage complet pour la partie FAQ Admin

set -e

echo "════════════════════════════════════════════"
echo "🚀 Démarrage du système FAQ Admin"
echo "════════════════════════════════════════════"

PROJECT_ROOT="/home/liza/PFE_M2/PFE-M2"
BACKEND_DIR="$PROJECT_ROOT/dev/backend"
FRONTEND_DIR="$PROJECT_ROOT/dev/frontend"

# Check directories
echo -e "\n📁 Vérification des répertoires..."
[ -d "$BACKEND_DIR" ] && echo "   ✅ Backend trouvé" || (echo "❌ Backend non trouvé"; exit 1)
[ -d "$FRONTEND_DIR" ] && echo "   ✅ Frontend trouvé" || (echo "❌ Frontend non trouvé"; exit 1)
[ -d "$PROJECT_ROOT/extract/app/faq" ] && echo "   ✅ Dossier FAQ trouvé" || echo "   ⚠️  Dossier FAQ sera créé automatiquement"

# Check dependencies
echo -e "\n📦 Vérification des dépendances..."
command -v python3 > /dev/null && echo "   ✅ Python3 trouvé" || (echo "❌ Python3 non trouvé"; exit 1)
command -v php > /dev/null && echo "   ✅ PHP trouvé" || (echo "❌ PHP non trouvé"; exit 1)
command -v curl > /dev/null && echo "   ✅ curl trouvé" || (echo "❌ curl non trouvé"; exit 1)

# Option 1: Démarrer le backend FastAPI
if [ "$1" == "backend" ]; then
    echo -e "\n🚀 Démarrage du backend FastAPI..."
    cd "$BACKEND_DIR"
    echo "   📍 Répertoire: $(pwd)"
    echo ""
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
elif [ "$1" == "frontend" ]; then
    echo -e "\n🚀 Démarrage du frontend Laravel..."
    cd "$FRONTEND_DIR"
    echo "   📍 Répertoire: $(pwd)"
    echo ""
    php artisan serve --host 0.0.0.0 --port 8001
elif [ "$1" == "test" ]; then
    echo -e "\n🧪 Lancement des tests..."
    bash "$PROJECT_ROOT/test_faq_endpoints.sh" "${2:-http://localhost:8000}"
elif [ "$1" == "all" ]; then
    echo -e "\n🔧 Configuration complète:"
    echo "   1. BACKEND:  http://localhost:8000"
    echo "   2. FRONTEND: http://localhost:8001"
    echo "   3. QDRANT:   http://localhost:6333"
    echo ""
    echo "⚠️  Veuillez démarrer les services dans des terminaux séparés:"
    echo ""
    echo "Terminal 1 (Backend):"
    echo "  cd $BACKEND_DIR && python -m uvicorn main:app --host 0.0.0.0 --port 8000"
    echo ""
    echo "Terminal 2 (Frontend):"
    echo "  cd $FRONTEND_DIR && php artisan serve --host 0.0.0.0 --port 8001"
    echo ""
    echo "Terminal 3 (Qdrant) - Optionnel:"
    echo "  docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant"
    echo ""
    echo "Terminal 4 (Tests) - Après démarrage:"
    echo "  bash $PROJECT_ROOT/test_faq_endpoints.sh"
    echo ""
else
    echo -e "\n📖 Usage:"
    echo "   ./start-faq.sh backend             # Démarrer FastAPI backend"
    echo "   ./start-faq.sh frontend            # Démarrer Laravel frontend"
    echo "   ./start-faq.sh test [url]          # Tester les endpoints"
    echo "   ./start-faq.sh all                 # Afficher les instructions complètes"
    echo ""
    echo "Pour une première utilisation, préférez 'all' pour voir tous les détails"
fi

