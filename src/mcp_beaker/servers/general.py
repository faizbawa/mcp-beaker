"""General Beaker tools (2 read): whoami, lab controllers."""

from __future__ import annotations

import logging

from fastmcp import Context

from mcp_beaker.exceptions import BeakerError
from mcp_beaker.servers import beaker_client, mcp
from mcp_beaker.utils.formatting import format_lab_controllers, format_whoami

logger = logging.getLogger("mcp-beaker")


def _error(msg: str) -> str:
    return f"Error: {msg}"


@mcp.tool(
    tags={"beaker", "read", "general"},
    annotations={"title": "Who Am I", "readOnlyHint": True},
)
async def whoami(ctx: Context) -> str:
    """Show the currently authenticated Beaker user.

    Verifies that credentials are working and returns the username
    and email associated with the current session.
    """
    client = beaker_client(ctx)
    try:
        info = await client.whoami()
        return format_whoami(info)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to call whoami: %s", exc)
        return _error(f"Failed to get user info: {exc}")


@mcp.tool(
    tags={"beaker", "read", "general"},
    annotations={"title": "List Lab Controllers", "readOnlyHint": True},
)
async def list_lab_controllers(ctx: Context) -> str:
    """List all lab controllers attached to the Beaker server.

    Lab controllers manage system provisioning in specific labs.
    Useful for troubleshooting distro availability issues.
    """
    client = beaker_client(ctx)
    try:
        controllers = await client.lab_controllers()
        return format_lab_controllers(controllers)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch lab controllers: %s", exc)
        return _error(f"Failed to fetch lab controllers: {exc}")
