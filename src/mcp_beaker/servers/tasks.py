"""Task-related Beaker tools (1 read)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from mcp_beaker.exceptions import BeakerError
from mcp_beaker.servers import beaker_client, mcp
from mcp_beaker.utils.formatting import format_tasks

logger = logging.getLogger("mcp-beaker")


def _error(msg: str) -> str:
    return f"Error: {msg}"


@mcp.tool(
    tags={"beaker", "read", "tasks"},
    annotations={"title": "Search Tasks", "readOnlyHint": True},
)
async def search_tasks(
    ctx: Context,
    osmajor: Annotated[
        str,
        Field(description="OS family, e.g. 'RedHatEnterpriseLinux10'. Limits to compatible tasks."),
    ] = "",
    distro_name: Annotated[str, Field(description="Distro name. Limits to compatible tasks.")] = "",
    packages: Annotated[
        str,
        Field(description="Comma-separated package names. Find tasks with matching Run-For."),
    ] = "",
    types: Annotated[
        str,
        Field(description="Comma-separated task types to include."),
    ] = "",
) -> str:
    """Search the Beaker task library for available test tasks.

    Find tasks compatible with a given OS, distro, or package list.
    Returns task names and their excluded architectures.
    """
    client = beaker_client(ctx)
    filters: dict[str, Any] = {}
    if osmajor:
        filters["osmajor"] = osmajor
    if distro_name:
        filters["distro_name"] = distro_name
    if packages:
        filters["packages"] = [p.strip() for p in packages.split(",") if p.strip()]
    if types:
        filters["types"] = [t.strip() for t in types.split(",") if t.strip()]

    if not filters:
        return _error("At least one filter is required (osmajor, distro_name, packages, or types).")

    try:
        tasks_raw = await client.tasks_filter(filters)
        return format_tasks(tasks_raw)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to search tasks: %s", exc)
        return _error(f"Failed to search tasks: {exc}")
