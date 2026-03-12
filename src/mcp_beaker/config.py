"""Beaker server configuration loaded from environment variables and CLI options."""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path

_SYSTEM_CA_PATHS = (
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
)


def _env_bool(key: str, default: bool = True) -> bool:
    val = os.environ.get(key, "").lower()
    if not val:
        return default
    return val in ("true", "1", "yes")


def _find_system_ca() -> str | None:
    """Return the first system CA bundle path that exists, or None."""
    for candidate in _SYSTEM_CA_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


@dataclass(frozen=True)
class BeakerConfig:
    """Immutable configuration for connecting to a Beaker server.

    Resolution order for each field: CLI flag → environment variable → default.
    """

    url: str = ""
    auth_method: str = "kerberos"
    username: str = ""
    password: str = ""
    owner: str = ""
    ssl_verify: bool = True
    ca_cert: str = ""

    @classmethod
    def from_env(cls) -> BeakerConfig:
        return cls(
            url=os.environ.get("BEAKER_URL", "").rstrip("/"),
            auth_method=os.environ.get("BEAKER_AUTH_METHOD", "kerberos").lower(),
            username=os.environ.get("BEAKER_USERNAME", ""),
            password=os.environ.get("BEAKER_PASSWORD", ""),
            owner=os.environ.get("BEAKER_OWNER", "") or os.environ.get("USER", ""),
            ssl_verify=_env_bool("BEAKER_SSL_VERIFY", default=True),
            ca_cert=os.environ.get("BEAKER_CA_CERT", ""),
        )

    def make_ssl_context(self) -> ssl.SSLContext | None:
        """Build an SSL context usable by both XML-RPC and httpx.

        When verification is disabled, returns a permissive context.
        When enabled, looks for an explicit CA cert, then falls back to
        well-known system CA bundle paths.  Returns None only when no
        custom CA is needed and the platform defaults should suffice.
        """
        if not self.ssl_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        ca_file = self.ca_cert or _find_system_ca()
        if ca_file:
            return ssl.create_default_context(cafile=ca_file)
        return None

    @property
    def rpc_url(self) -> str:
        return f"{self.url}/RPC2" if self.url else ""


@dataclass(frozen=True)
class ServerSettings:
    """Runtime server settings separate from Beaker connection config."""

    read_only: bool = False
    enabled_tools: list[str] = field(default_factory=list)
    verbose: int = 0
