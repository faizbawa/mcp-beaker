#!/bin/bash
set -e

if [ -n "$BEAKER_CA_CERT_DATA" ]; then
    printf '%b' "$BEAKER_CA_CERT_DATA" > /tmp/ca-bundle.crt
    export BEAKER_CA_CERT=/tmp/ca-bundle.crt
fi

if klist -s 2>/dev/null; then
    : # valid ticket already present (mounted ccache)
elif [ -n "$KRB5_PRINCIPAL" ] && [ -n "$KRB5_PASSWORD" ]; then
    echo "$KRB5_PASSWORD" | kinit "$KRB5_PRINCIPAL" >/dev/null 2>&1
elif [ -f /etc/krb5.keytab ]; then
    kinit -k -t /etc/krb5.keytab "${KRB5_PRINCIPAL:-}" >/dev/null 2>&1
fi

exec mcp-beaker "$@"
