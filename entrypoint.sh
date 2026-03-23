#!/bin/bash
set -e

if [ -n "$KRB5_PRINCIPAL" ] && [ -n "$KRB5_PASSWORD" ]; then
    echo "$KRB5_PASSWORD" | kinit "$KRB5_PRINCIPAL" 2>/dev/null
elif [ -f /etc/krb5.keytab ]; then
    kinit -k -t /etc/krb5.keytab "${KRB5_PRINCIPAL:-}" 2>/dev/null
fi

exec mcp-beaker "$@"
