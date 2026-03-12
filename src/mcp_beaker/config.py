"""Beaker server configuration loaded from environment variables and CLI options."""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field


def _env_bool(key: str, default: bool = True) -> bool:
    val = os.environ.get(key, "").lower()
    if not val:
        return default
    return val in ("true", "1", "yes")


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
        """Build an SSL context from configuration.

        Returns None when SSL verification is enabled with default certs
        (httpx/xmlrpc handle this natively).
        """
        if not self.ssl_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if self.ca_cert:
            ctx = ssl.create_default_context(cafile=self.ca_cert)
            return ctx
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
