#!/bin/bash
set -e

if [ -n "$BEAKER_CA_CERT_DATA" ]; then
    printf '%b' "$BEAKER_CA_CERT_DATA" > /tmp/ca-bundle.crt
    export BEAKER_CA_CERT=/tmp/ca-bundle.crt
fi

if klist -s 2>/dev/null; then
    echo "[mcp-beaker] Kerberos ticket valid ($(klist 2>/dev/null | head -1))" >&2
elif [ -f "${KRB5CCNAME#FILE:}" ] 2>/dev/null || [ -f /tmp/krb5cc_0 ]; then
    echo "[mcp-beaker] WARNING: Kerberos ticket cache found but expired. Run: kinit -c FILE:/tmp/krb5cc_beaker" >&2
elif [ -n "$KRB5_PRINCIPAL" ] && [ -n "$KRB5_PASSWORD" ]; then
    echo "$KRB5_PASSWORD" | kinit "$KRB5_PRINCIPAL" >/dev/null 2>&1
elif [ -f /etc/krb5.keytab ]; then
    kinit -k -t /etc/krb5.keytab "${KRB5_PRINCIPAL:-}" >/dev/null 2>&1
fi

exec mcp-beaker "$@"
