#!/bin/bash
# Script to initialize OpenLDAP with LDIF data
# Designed to be run after the OpenLDAP container starts

set -e

LDAP_HOST="${LDAP_HOST:-localhost}"
LDAP_PORT="${LDAP_PORT:-1389}"
LDAP_ADMIN_DN="cn=admin,dc=sonatrach,dc=test"
LDAP_ADMIN_PASSWORD="${LDAP_ADMIN_PASSWORD:-pfe@2026}"
LDIF_FILE="/container/service/slapd/assets/config/bootstrap/ldif/users.ldif"

echo "Waiting for LDAP to be ready..."
sleep 5

# Check if base DN exists
if ! ldapsearch -x -H ldap://${LDAP_HOST}:${LDAP_PORT} -b "dc=sonatrach,dc=test" -s base > /dev/null 2>&1; then
    echo "Base DN not found, creating..."

    # Create base DN
    cat > /tmp/base_dn.ldif << 'EOF'
dn: dc=sonatrach,dc=test
objectClass: dcObject
objectClass: organization
dc: sonatrach
o: Sonatrach
EOF

    ldapadd -x -H ldap://${LDAP_HOST}:${LDAP_PORT} -D "${LDAP_ADMIN_DN}" -w "${LDAP_ADMIN_PASSWORD}" -f /tmp/base_dn.ldif 2>&1 || true
fi

# Check if users exist (already loaded)
if ldapsearch -x -H ldap://${LDAP_HOST}:${LDAP_PORT} -D "${LDAP_ADMIN_DN}" -w "${LDAP_ADMIN_PASSWORD}" -b "ou=people,dc=sonatrach,dc=test" -s base > /dev/null 2>&1; then
    echo "Users already loaded"
else
    echo "Loading LDIF data..."
    if [ -f "${LDIF_FILE}" ]; then
        ldapadd -x -H ldap://${LDAP_HOST}:${LDAP_PORT} -D "${LDAP_ADMIN_DN}" -w "${LDAP_ADMIN_PASSWORD}" -f "${LDIF_FILE}" 2>&1 || true
        echo "LDIF data loaded successfully"
    else
        echo "Warning: LDIF file not found at ${LDIF_FILE}"
    fi
fi

echo "LDAP initialization complete"

