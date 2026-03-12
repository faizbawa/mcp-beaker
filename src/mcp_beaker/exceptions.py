"""Custom exceptions for the Beaker MCP server."""

from __future__ import annotations


class BeakerError(Exception):
    """Base exception for all Beaker MCP errors."""


class BeakerConfigError(BeakerError):
    """Raised when required configuration is missing or invalid."""


class BeakerAuthenticationError(BeakerError):
    """Raised when authentication with the Beaker server fails (401/403)."""


class BeakerNotFoundError(BeakerError):
    """Raised when a requested resource (system, job, distro) is not found (404)."""


class BeakerConnectionError(BeakerError):
    """Raised when the Beaker server is unreachable."""


class BeakerXMLRPCError(BeakerError):
    """Raised when the Beaker XML-RPC endpoint returns a fault."""

    def __init__(self, fault_code: int, fault_string: str) -> None:
        self.fault_code = fault_code
        self.fault_string = fault_string
        super().__init__(f"XML-RPC fault {fault_code}: {fault_string}")


class BeakerValidationError(BeakerError):
    """Raised when job XML or other input fails validation."""
