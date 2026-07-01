#!/bin/bash
# ══════════════════════════════════════════════════════
# import_users.sh — Import LDIF Sonatrach dans OpenLDAP
# ══════════════════════════════════════════════════════
LDAP_CONTAINER="openldap"
LDAP_ADMIN="cn=admin,dc=sonatrach,dc=test"
LDAP_PASS="pfe@2026"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LDIF_FILE="$SCRIPT_DIR/users.ldif"

# ── Vérifications préalables ──────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^${LDAP_CONTAINER}$"; then
    echo "❌ Le container '${LDAP_CONTAINER}' n'est pas démarré."
    echo "   Lance d'abord : docker-compose -f docker-compose.dev.yml up -d openldap"
    exit 1
fi

if [ ! -f "$LDIF_FILE" ]; then
    echo "❌ Fichier LDIF introuvable : $LDIF_FILE"
    exit 1
fi

# ── Copie et import ───────────────────────────────────
echo "📋 Copie du fichier LDIF dans le container..."
docker cp "$LDIF_FILE" "${LDAP_CONTAINER}:/tmp/users.ldif"

echo "📥 Import des utilisateurs (option -c : continue si entrée déjà existante)..."
docker exec "${LDAP_CONTAINER}" ldapadd \
    -c \
    -x \
    -H ldap://localhost \
    -D "${LDAP_ADMIN}" \
    -w "${LDAP_PASS}" \
    -f /tmp/users.ldif

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 68 ]; then
    # 68 = LDAP_ALREADY_EXISTS — normal lors d'une réimport
    echo "✅ Import terminé (les entrées déjà existantes ont été ignorées)."
else
    echo "⚠️  Import terminé avec le code $EXIT_CODE — vérifier les logs ci-dessus."
fi

# ── Vérification générale ─────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Utilisateurs importés dans ou=people :"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec "${LDAP_CONTAINER}" ldapsearch \
    -x \
    -H ldap://localhost \
    -D "${LDAP_ADMIN}" \
    -w "${LDAP_PASS}" \
    -b "ou=people,dc=sonatrach,dc=test" \
    "(objectClass=inetOrgPerson)" \
    uid mail title employeeNumber \
    | grep -E "^(uid|mail|title|employeeNumber):"

# ── Vérification superadmin ───────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "👑 Compte Super Admin (description=superadmin) :"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec "${LDAP_CONTAINER}" ldapsearch \
    -x \
    -H ldap://localhost \
    -D "${LDAP_ADMIN}" \
    -w "${LDAP_PASS}" \
    -b "ou=people,dc=sonatrach,dc=test" \
    "(description=superadmin)" \
    uid cn title employeeNumber \
    | grep -E "^(uid|cn|title|employeeNumber):"

# ── Vérification admins ───────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 Comptes Admin (description=admin) :"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec "${LDAP_CONTAINER}" ldapsearch \
    -x \
    -H ldap://localhost \
    -D "${LDAP_ADMIN}" \
    -w "${LDAP_PASS}" \
    -b "ou=people,dc=sonatrach,dc=test" \
    "(description=admin)" \
    uid cn employeeNumber \
    | grep -E "^(uid|cn|employeeNumber):"

# ── Vérification groupes ──────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "👥 Groupes présents dans ou=groups :"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec "${LDAP_CONTAINER}" ldapsearch \
    -x \
    -H ldap://localhost \
    -D "${LDAP_ADMIN}" \
    -w "${LDAP_PASS}" \
    -b "ou=groups,dc=sonatrach,dc=test" \
    "(objectClass=groupOfNames)" \
    cn \
    | grep "^cn:"

# ── Comptage total ────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL=$(docker exec "${LDAP_CONTAINER}" ldapsearch \
    -x -H ldap://localhost \
    -D "${LDAP_ADMIN}" -w "${LDAP_PASS}" \
    -b "ou=people,dc=sonatrach,dc=test" \
    "(objectClass=inetOrgPerson)" uid \
    | grep -c "^uid:")
echo "📊 Total utilisateurs importés : ${TOTAL}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Interface graphique ───────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Interface graphique phpLDAPadmin :"
echo "   URL   : http://localhost:6443"
echo "   Login : cn=admin,dc=sonatrach,dc=test"
echo "   Pass  : pfe@2026"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Tests d'authentification ──────────────────────────
echo ""
echo "🔑 Tests d'authentification :"
echo ""
echo "   ▸ Super Admin :"
echo "   docker exec ${LDAP_CONTAINER} ldapwhoami \\"
echo "     -x -H ldap://localhost \\"
echo "     -D 'uid=superadmin,ou=people,dc=sonatrach,dc=test' \\"
echo "     -w 'Sonatrach2026!'"
echo ""
echo "   ▸ Admin standard (exemple amine.benali) :"
echo "   docker exec ${LDAP_CONTAINER} ldapwhoami \\"
echo "     -x -H ldap://localhost \\"
echo "     -D 'uid=amine.benali,ou=people,dc=sonatrach,dc=test' \\"
echo "     -w 'Sonatrach2026!'"
echo ""
echo "   ▸ Recherche par code SON (exemple son00001) :"
echo "   docker exec ${LDAP_CONTAINER} ldapsearch \\"
echo "     -x -H ldap://localhost \\"
echo "     -D '${LDAP_ADMIN}' -w '${LDAP_PASS}' \\"
echo "     -b 'ou=people,dc=sonatrach,dc=test' \\"
echo "     '(employeeNumber=son00001)' uid cn title"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"