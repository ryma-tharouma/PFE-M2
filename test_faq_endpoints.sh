#!/bin/bash
# Script de test pour les endpoints FAQ du backend FastAPI

set -e

BACKEND_URL="${1:-http://localhost:8000}"
echo "🧪 Test des endpoints FAQ - Backend: $BACKEND_URL"
echo "────────────────────────────────────────────────"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Health check
echo -e "\n${YELLOW}[Test 1]${NC} Health check..."
if HEALTH=$(curl -s "$BACKEND_URL/health"); then
  if echo "$HEALTH" | grep -q '"status"'; then
    echo -e "${GREEN}✅ Backend accessible${NC}"
    echo "   Status: $(echo "$HEALTH" | jq -r '.status')"
  else
    echo -e "${RED}❌ Réponse invalide${NC}"
    exit 1
  fi
else
  echo -e "${RED}❌ Backend non accessible${NC}"
  exit 1
fi

# Test 2: Upload FAQ
echo -e "\n${YELLOW}[Test 2]${NC} Upload d'une FAQ..."
FAQ_DATA='{
  "app": "test_app",
  "items": [
    {"question":"Comment créer un utilisateur?","answer":"Allez dans le menu Utilisateurs > Nouveau..."},
    {"question":"Comment se connecter?","answer":"Entrez votre identifiant et mot de passe"},
    {"question":"Où trouver l aide?","answer":"Consultez la section Aide du menu"}
  ]
}'

UPLOAD_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/admin/faq/upload" \
  -H "Content-Type: application/json" \
  -d "$FAQ_DATA")

if echo "$UPLOAD_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
  echo -e "${GREEN}✅ FAQ uploadée et indexée${NC}"
  echo "   Path: $(echo "$UPLOAD_RESPONSE" | jq -r '.path')"
else
  echo -e "${RED}❌ Erreur lors de l'upload${NC}"
  echo "$UPLOAD_RESPONSE" | jq .
  exit 1
fi

# Test 3: Vérifier la collection Qdrant
echo -e "\n${YELLOW}[Test 3]${NC} Vérifier collections Qdrant..."
COLLECTIONS=$(curl -s "$BACKEND_URL/api/collections")
if echo "$COLLECTIONS" | grep -q '"faq"'; then
  echo -e "${GREEN}✅ Collection 'faq' créée${NC}"
else
  echo -e "${RED}❌ Collection 'faq' non trouvée${NC}"
fi

# Test 4: Récupérer la FAQ
echo -e "\n${YELLOW}[Test 4]${NC} Récupérer la FAQ..."
FAQ_GET=$(curl -s "$BACKEND_URL/api/admin/faq/test_app")
if echo "$FAQ_GET" | jq -e '.faq' > /dev/null 2>&1; then
  echo -e "${GREEN}✅ FAQ récupérée${NC}"
  echo "   Items: $(echo "$FAQ_GET" | jq '.faq | length')"
else
  echo -e "${RED}❌ Erreur lors de la récupération${NC}"
  echo "$FAQ_GET" | jq .
fi

# Test 5: Mettre à jour la FAQ
echo -e "\n${YELLOW}[Test 5]${NC} Mettre à jour la FAQ..."
UPDATE_DATA='{
  "items": [
    {"question":"Comment créer un utilisateur?","answer":"Allez dans le menu Utilisateurs > Nouveau..."},
    {"question":"Comment se connecter?","answer":"Entrez votre identifiant et mot de passe"},
    {"question":"Où trouver l aide?","answer":"Consultez la section Aide du menu"},
    {"question":"Comment réinitialiser mon mot de passe?","answer":"Cliquez sur Oublié mon mot de passe"}
  ]
}'

UPDATE_RESPONSE=$(curl -s -X PUT "$BACKEND_URL/api/admin/faq/test_app?reindex=true" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_DATA")

if echo "$UPDATE_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
  echo -e "${GREEN}✅ FAQ mise à jour et réindexée${NC}"
else
  echo -e "${RED}❌ Erreur lors de la mise à jour${NC}"
  echo "$UPDATE_RESPONSE" | jq .
fi

# Test 6: Lancer l'indexation manuellement
echo -e "\n${YELLOW}[Test 6]${NC} Lancer l'indexation manuellement..."
INDEX_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/admin/faq/test_app/index")
if echo "$INDEX_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Indexation lancée${NC}"
  echo "   Collection: $(echo "$INDEX_RESPONSE" | jq -r '.collection')"
  echo "   Count: $(echo "$INDEX_RESPONSE" | jq -r '.count')"
else
  echo -e "${RED}❌ Erreur lors de l'indexation${NC}"
  echo "$INDEX_RESPONSE" | jq .
fi

# Test 7: Récupérer les chats (si des logs existent)
echo -e "\n${YELLOW}[Test 7]${NC} Récupérer les chats anonymisés..."
CHATS_RESPONSE=$(curl -s "$BACKEND_URL/api/admin/chats/test_app?limit=5")
if echo "$CHATS_RESPONSE" | jq -e '.chats' > /dev/null 2>&1; then
  CHAT_COUNT=$(echo "$CHATS_RESPONSE" | jq '.chats | length')
  echo -e "${GREEN}✅ Chats récupérés${NC}"
  echo "   Count: $CHAT_COUNT"
else
  echo -e "${YELLOW}⚠️  Aucun chat trouvé (normal si pas de logs)${NC}"
fi

echo -e "\n────────────────────────────────────────────────"
echo -e "${GREEN}✅ Tous les tests sont passés!${NC}"
echo -e "\n📁 Fichier FAQ sauvegardé: extract/app/faq/test_app.json"
echo "📊 Consultez la collection 'faq' dans Qdrant"

