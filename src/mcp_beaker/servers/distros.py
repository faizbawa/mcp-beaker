"""Distro-related Beaker tools (2 read)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from mcp_beaker.exceptions import BeakerError
from mcp_beaker.models.distro import DistroTreeInfo
from mcp_beaker.servers import beaker_client, mcp
from mcp_beaker.utils.formatting import format_distro_trees, format_os_families

logger = logging.getLogger("mcp-beaker")


def _error(msg: str) -> str:
    return f"Error: {msg}"


@mcp.tool(
    tags={"beaker", "read", "distros"},
    annotations={"title": "List Distro Trees", "readOnlyHint": True},
)
async def list_distro_trees(
    ctx: Context,
    name: Annotated[
        str,
        Field(description="Distro name pattern (SQL wildcards, e.g. 'RHEL-10.2%')."),
    ] = "",
    family: Annotated[
        str,
        Field(description="Exact distro family, e.g. 'RedHatEnterpriseLinux10'."),
    ] = "",
    arch: Annotated[
        str,
        Field(description="Architecture, e.g. 'x86_64', 'aarch64', 's390x'."),
    ] = "",
    tags: Annotated[
        str,
        Field(description="Comma-separated distro tags, e.g. 'STABLE,RELEASED'. All must match."),
    ] = "",
    limit: Annotated[int, Field(description="Max results. Default: 10.")] = 10,
) -> str:
    """Search available distro trees on the Beaker server.

    Query the distro library to discover which distros are available
    before submitting a job. At least one search criterion is required.
    """
    client = beaker_client(ctx)
    filters: dict[str, Any] = {}
    if name:
        filters["name"] = name
    if family:
        filters["family"] = family
    if arch:
        filters["arch"] = arch
    if tags:
        filters["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if limit > 0:
        filters["limit"] = limit

    if not filters or filters.keys() == {"limit"}:
        return _error("At least one search criterion is required (name, family, arch, or tags).")

    desc_parts: list[str] = []
    if name:
        desc_parts.append(f"name={name}")
    if family:
        desc_parts.append(f"family={family}")
    if arch:
        desc_parts.append(f"arch={arch}")
    if tags:
        desc_parts.append(f"tags={tags}")
    filters_desc = ", ".join(desc_parts)

    try:
        trees_raw = await client.distrotrees_filter(filters)
        trees = [DistroTreeInfo.model_validate(t) for t in trees_raw]
        return format_distro_trees(trees, filters_desc)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch distro trees: %s", exc)
        return _error(f"Failed to fetch distro trees: {exc}")


@mcp.tool(
    tags={"beaker", "read", "distros"},
    annotations={"title": "List OS Families", "readOnlyHint": True},
)
async def list_os_families(
    ctx: Context,
    tags: Annotated[
        str,
        Field(description="Optional comma-separated tags to filter by (e.g. 'STABLE')."),
    ] = "",
) -> str:
    """List all distro families (OS major versions) known to Beaker.

    Returns family names like 'RedHatEnterpriseLinux10', 'Fedora41', etc.
    Optionally filter to families that have distros with specific tags.
    """
    client = beaker_client(ctx)
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        families = await client.distros_get_osmajors(tag_list)
        return format_os_families(families)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch OS families: %s", exc)
        return _error(f"Failed to fetch OS families: {exc}")
