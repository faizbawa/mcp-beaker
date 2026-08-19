"""System-related Beaker tools (6 read + 6 write)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import Context
from pydantic import Field

from mcp_beaker.exceptions import BeakerError, BeakerNotFoundError
from mcp_beaker.models.system import (
    SystemHistoryEntry,
    SystemInfo,
    SystemListItem,
    SystemStatusInfo,
)
from mcp_beaker.servers import beaker_client, mcp
from mcp_beaker.utils.formatting import (
    format_system_arches,
    format_system_details,
    format_system_history,
    format_system_list,
    format_system_status,
)

logger = logging.getLogger("mcp-beaker")

VALID_PRESETS = {"all", "available", "free"}

SEARCH_TABLE_MAP: dict[str, str] = {
    "hostname": "System/Name",
    "cpu_vendor": "CPU/Vendor",
    "cpu_model_name": "CPU/ModelName",
    "cpu_family": "CPU/Family",
    "cpu_model": "CPU/Model",
    "cpu_cores": "CPU/Cores",
    "cpu_sockets": "CPU/Sockets",
    "cpu_processors": "CPU/Processors",
    "cpu_speed": "CPU/Speed",
    "cpu_hyper": "CPU/Hyper",
    "cpu_flags": "CPU/Flags",
    "arch": "System/Arch",
    "memory": "System/Memory",
    "status": "System/Status",
    "type": "System/Type",
    "vendor": "System/Vendor",
    "model": "System/Model",
    "location": "System/Location",
    "pool": "System/Pools",
    "numa_nodes": "System/NumaNodes",
    "disk_space": "Disk/Size",
    "hypervisor": "System/Hypervisor",
    "owner": "System/Owner",
    "user": "System/User",
    "lender": "System/Lender",
    "loaned_to": "System/LoanedTo",
}

COMPARISON_OPS = {">=": "greater than", "<=": "less than", ">": "greater than", "<": "less than"}


def _build_advancedsearch_params(
    filters: dict[str, str | int | float],
    limit: int = 20,
) -> list[tuple[str, str]]:
    """Convert filter dict to Beaker REST advancedsearch query tuples.

    The new Beaker Py3 REST API at ``/systems`` accepts repeated
    ``advancedsearch=table,operation,value`` query parameters for AND logic.
    """
    params: list[tuple[str, str]] = []
    for key, value in filters.items():
        table = SEARCH_TABLE_MAP.get(key)
        if table is None:
            continue
        str_value = str(value)
        operation = "is"
        for op_str, op_name in COMPARISON_OPS.items():
            if str_value.startswith(op_str):
                operation = op_name
                str_value = str_value[len(op_str):]
                break
        # Hostname is always substring match: Beaker's simple search uses
        # contains on System/Name, and callers pass prefixes like ampere-mtsnow.
        if operation == "is" and ("%" in str_value or key == "hostname"):
            operation = "contains"
            str_value = str_value.replace("%", "")
        params.append(("advancedsearch", f"{table},{operation},{str_value}"))
    params.append(("page_size", str(limit)))
    return params


def _error(msg: str) -> str:
    return f"Error: {msg}"


def _parse_json_systems(data: dict) -> list[SystemListItem]:
    """Parse the JSON response from ``GET /systems`` into SystemListItem list."""
    systems: list[SystemListItem] = []
    for entry in data.get("items", []):
        fqdn = entry.get("fqdn", "Unknown")
        systems.append(SystemListItem(fqdn=fqdn, url=""))
    return systems


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "List Systems", "readOnlyHint": True},
)
async def list_systems(
    ctx: Context,
    filter_type: Annotated[
        str,
        Field(description="System filter: 'all', 'available', or 'free'. Default: 'available'."),
    ] = "available",
    hostname: Annotated[
        str,
        Field(
            description="Hostname/FQDN substring to match, e.g. 'ampere-mtsnow' or "
            "'nvidia-grace-hopper%'. Always a contains match. Empty means any host."
        ),
    ] = "",
    limit: Annotated[
        int,
        Field(description="Maximum number of systems to return. Use 0 for all. Default: 20."),
    ] = 20,
) -> str:
    """List Beaker systems matching the filter criteria.

    Returns a list of system FQDNs filtered by availability status and
    optional hostname substring. Use 'available' for systems you can
    reserve, 'free' for idle ones, or 'all' for the complete inventory.
    """
    client = beaker_client(ctx)
    if filter_type not in VALID_PRESETS:
        return _error(
            f"Invalid filter_type '{filter_type}'. "
            f"Must be one of: {', '.join(VALID_PRESETS)}."
        )
    page_size = str(limit or 10000)
    params: list[tuple[str, str]] = [("page_size", page_size)]
    if filter_type != "all":
        params.append(("preset", filter_type))
        await client._ensure_rest_auth()
    if hostname:
        host_params = _build_advancedsearch_params({"hostname": hostname}, limit=int(page_size))
        params.extend(p for p in host_params if p[0] != "page_size")
    try:
        response = await client.rest_get(
            "/systems", params=params,
            headers={"Accept": "application/json"},
        )
        data = response.json()
        systems = _parse_json_systems(data)
        return format_system_list(systems, filter_type)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to list systems: %s", exc)
        return _error(f"Failed to list systems: {exc}")


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "Search Systems", "readOnlyHint": True},
)
async def search_systems(
    ctx: Context,
    hostname: Annotated[
        str,
        Field(
            description="Hostname/FQDN substring to match, e.g. 'ampere-mtsnow' or "
            "'nvidia-grace-hopper%'. Always a contains match."
        ),
    ] = "",
    cpu_vendor: Annotated[
        str,
        Field(description="CPU vendor string, e.g. 'GenuineIntel', 'AuthenticAMD', 'Ampere(R)'."),
    ] = "",
    cpu_model_name: Annotated[
        str,
        Field(description="CPU model name substring to match, e.g. 'Xeon Gold'."),
    ] = "",
    cpu_family: Annotated[
        int,
        Field(
            description="CPU family number. Intel=6, AMD Zen3/4=25, AMD Zen1/2=23, AMD Zen5=26.",
        ),
    ] = 0,
    cpu_model: Annotated[
        int,
        Field(
            description="CPU model number identifying microarchitecture. "
            "Intel family 6: 207=Emerald Rapids, 175=Sierra Forest, 173=Granite Rapids, "
            "143=Sapphire Rapids, 106=Ice Lake, 85=Skylake/Cascade Lake, "
            "79=Broadwell, 63=Haswell, 165=Comet Lake. "
            "AMD family 25: 17=Genoa, 1=Milan. AMD family 23: 49=Rome, 1=Naples. "
            "AMD family 26: Turin.",
        ),
    ] = 0,
    cpu_cores: Annotated[
        str,
        Field(description="CPU core count. Prefix with >= or <= for range, e.g. '>=64'."),
    ] = "",
    arch: Annotated[
        str,
        Field(description="Architecture filter: 'x86_64', 'aarch64', 's390x', 'ppc64le'."),
    ] = "",
    memory: Annotated[
        str,
        Field(
            description="Memory in MiB. Prefix with >= or <= for range, "
            "e.g. '>=131072' for 128GB+.",
        ),
    ] = "",
    pool: Annotated[
        str,
        Field(description="Beaker pool name, e.g. 'rhelvirt-gating'."),
    ] = "",
    owner: Annotated[
        str,
        Field(description="Owner username to filter by, e.g. 'tasharma'. Exact match."),
    ] = "",
    user: Annotated[
        str,
        Field(
            description="Current user (reserved by) username to filter by. "
            "Shows systems currently reserved by this user."
        ),
    ] = "",
    loaned_to: Annotated[
        str,
        Field(
            description="Username the system is loaned to. "
            "Shows systems currently loaned to this user."
        ),
    ] = "",
    status: Annotated[
        str,
        Field(
            description="System status: 'Automated', 'Manual', 'Broken', or '' for any. "
            "Default: 'Automated'."
        ),
    ] = "Automated",
    limit: Annotated[
        int,
        Field(description="Maximum number of systems to return. Default: 10."),
    ] = 10,
) -> str:
    """Search Beaker systems by hardware attributes and ownership.

    Find systems matching hostname, CPU, architecture, memory, pool,
    owner, and other criteria. All filters are combined with AND logic.
    """
    client = beaker_client(ctx)
    filters: dict[str, str | int | float] = {}
    if hostname:
        filters["hostname"] = hostname
    if cpu_vendor:
        filters["cpu_vendor"] = cpu_vendor
    if cpu_model_name:
        filters["cpu_model_name"] = cpu_model_name
    if cpu_family:
        filters["cpu_family"] = cpu_family
    if cpu_model:
        filters["cpu_model"] = cpu_model
    if cpu_cores:
        filters["cpu_cores"] = cpu_cores
    if arch:
        filters["arch"] = arch
    if memory:
        filters["memory"] = memory
    if pool:
        filters["pool"] = pool
    if owner:
        filters["owner"] = owner
    if user:
        filters["user"] = user
    if loaned_to:
        filters["loaned_to"] = loaned_to
    if status:
        filters["status"] = status

    if not filters:
        return _error("At least one search filter is required.")

    search_params = _build_advancedsearch_params(filters, limit=limit)

    try:
        response = await client.rest_get(
            "/systems", params=search_params,
            headers={"Accept": "application/json"},
        )
        data = response.json()
        systems = _parse_json_systems(data)
        if not systems:
            filter_desc = ", ".join(f"{k}={v}" for k, v in filters.items())
            return f"No systems found matching: {filter_desc}"
        lines = [f"Found {len(systems)} system(s) matching search criteria:\n"]
        for idx, system in enumerate(systems, start=1):
            lines.append(f"  {idx}. {system.fqdn}")
        return "\n".join(lines)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to search systems: %s", exc)
        return _error(f"Failed to search systems: {exc}")


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "Get System Details", "readOnlyHint": True},
)
async def get_system_details(
    ctx: Context,
    fqdn: Annotated[str, Field(description="Fully qualified domain name of the system.")],
) -> str:
    """Get detailed information about a specific Beaker system.

    Returns hardware specs, ownership, status, architectures, and
    lab controller assignment for the given system FQDN.
    """
    client = beaker_client(ctx)
    try:
        data = await client.rest_get_json(f"/systems/{fqdn}/")
        info = SystemInfo.model_validate(data)
        return format_system_details(info)
    except BeakerNotFoundError:
        return _error(f"System '{fqdn}' not found.")
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch system details for %s: %s", fqdn, exc)
        return _error(f"Failed to fetch details for system '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "Get System Status", "readOnlyHint": True},
)
async def get_system_status(
    ctx: Context,
    fqdn: Annotated[str, Field(description="Fully qualified domain name of the system.")],
) -> str:
    """Get the current status of a Beaker system: who has it loaned and who is using it.

    Returns the system condition (Automated/Manual/Broken/Removed),
    current loan details (recipient and comment), and current
    reservation details (user and recipe).
    """
    client = beaker_client(ctx)
    try:
        data = await client.systems_status(fqdn)
        status = SystemStatusInfo.model_validate(data)
        return format_system_status(status, fqdn)
    except BeakerNotFoundError:
        return _error(f"System '{fqdn}' not found.")
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch status for %s: %s", fqdn, exc)
        return _error(f"Failed to fetch status for system '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "Get System History", "readOnlyHint": True},
)
async def get_system_history(
    ctx: Context,
    fqdn: Annotated[str, Field(description="Fully qualified domain name of the system.")],
    since: Annotated[
        str,
        Field(description="ISO timestamp to fetch history from. Omit for last 24 hours."),
    ] = "",
) -> str:
    """Get activity history for a Beaker system.

    Shows who used the system, what changed, and when. Useful for
    investigating system state changes and usage patterns.
    """
    client = beaker_client(ctx)
    try:
        since_arg = since if since else None
        entries_raw = await client.systems_history(fqdn, since_arg)
        entries = [
            SystemHistoryEntry.model_validate(
                {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                    for k, v in e.items()
                }
            )
            for e in entries_raw
        ]
        return format_system_history(entries, fqdn)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch history for %s: %s", fqdn, exc)
        return _error(f"Failed to fetch history for '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "read", "systems"},
    annotations={"title": "Get System Architectures", "readOnlyHint": True},
)
async def get_system_arches(
    ctx: Context,
    fqdn: Annotated[str, Field(description="Fully qualified domain name of the system.")],
) -> str:
    """Get supported OS families and architectures for a Beaker system.

    Returns a mapping of distro family names to their supported
    architecture list for the given system.
    """
    client = beaker_client(ctx)
    try:
        arches = await client.systems_get_osmajor_arches(fqdn)
        return format_system_arches(arches, fqdn)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch arches for %s: %s", fqdn, exc)
        return _error(f"Failed to fetch arches for '{fqdn}': {exc}")


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Reserve System", "readOnlyHint": False},
)
async def reserve_system(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system to reserve.")],
) -> str:
    """Manually reserve a Beaker system.

    The system must be in 'Manual' condition and not currently in use.
    You must have permission to use the system. After reserving, you
    can provision it at will.
    """
    client = beaker_client(ctx)
    try:
        await client.systems_reserve(fqdn)
        return f"Successfully reserved system '{fqdn}'."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to reserve %s: %s", fqdn, exc)
        return _error(f"Failed to reserve '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Release System", "readOnlyHint": False},
)
async def release_system(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system to release.")],
) -> str:
    """Release a manually reserved Beaker system.

    You must be the current user of the system (i.e. you reserved it).
    """
    client = beaker_client(ctx)
    try:
        await client.systems_release(fqdn)
        return f"Successfully released system '{fqdn}'."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to release %s: %s", fqdn, exc)
        return _error(f"Failed to release '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Power System", "readOnlyHint": False},
)
async def power_system(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system to power control.")],
    action: Annotated[str, Field(description="Power action: 'on', 'off', or 'reboot'.")],
    force: Annotated[
        bool,
        Field(description="Override safety check if system is in use. Default: false."),
    ] = False,
) -> str:
    """Control power for a Beaker system (on, off, or reboot).

    Power control is not normally permitted when the system is in
    use by someone else. Use force=true to override this safety check.
    """
    if action not in ("on", "off", "reboot"):
        return _error(f"Invalid action '{action}'. Must be 'on', 'off', or 'reboot'.")
    client = beaker_client(ctx)
    try:
        await client.systems_power(action, fqdn, force=force)
        return f"Power {action} command sent to '{fqdn}'."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to power %s %s: %s", action, fqdn, exc)
        return _error(f"Failed to power {action} '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Loan System", "readOnlyHint": False},
)
async def loan_system(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system to loan.")],
    recipient: Annotated[
        str,
        Field(description="Username of the loan recipient. If empty, loans to the current user."),
    ] = "",
    comment: Annotated[
        str,
        Field(description="Reason or purpose for the loan."),
    ] = "",
) -> str:
    """Grant a loan for a Beaker system.

    The loan recipient gets full permissions to reserve, provision, and
    schedule jobs on the system. While loaned, only the recipient and
    the system owner can use it. You must have permission to loan the
    system (typically the owner or an admin).
    """
    client = beaker_client(ctx)
    try:
        await client.systems_loan_grant(
            fqdn,
            recipient=recipient or None,
            comment=comment,
        )
        target = recipient if recipient else "yourself"
        return f"Successfully loaned system '{fqdn}' to {target}."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to loan %s: %s", fqdn, exc)
        return _error(f"Failed to loan '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Return System Loan", "readOnlyHint": False},
)
async def return_loan(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system whose loan to return.")],
) -> str:
    """Return a current loan on a Beaker system.

    Either the loan recipient or a user with permission to loan the
    system can return it. The system reverts to its normal access policy.
    """
    client = beaker_client(ctx)
    try:
        await client.systems_loan_return(fqdn)
        return f"Successfully returned loan for system '{fqdn}'."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to return loan for %s: %s", fqdn, exc)
        return _error(f"Failed to return loan for '{fqdn}': {exc}")


@mcp.tool(
    tags={"beaker", "write", "systems"},
    annotations={"title": "Provision System", "readOnlyHint": False},
)
async def provision_system(
    ctx: Context,
    fqdn: Annotated[str, Field(description="FQDN of the system to provision.")],
    distro_tree_id: Annotated[
        int,
        Field(description="Numeric distro tree ID (from list_distro_trees results)."),
    ],
    ks_meta: Annotated[str, Field(description="Kickstart metadata variables.")] = "",
    kernel_options: Annotated[str, Field(description="Kernel options for installation.")] = "",
    kernel_options_post: Annotated[
        str, Field(description="Kernel options for the installed system.")
    ] = "",
    kickstart: Annotated[str, Field(description="Complete custom kickstart content.")] = "",
    reboot: Annotated[
        bool, Field(description="Reboot system after provisioning. Default: true.")
    ] = True,
) -> str:
    """Provision a reserved Beaker system with a specific distro.

    The system must be in 'Manual' condition and already reserved by you.
    Use list_distro_trees to find the distro_tree_id first.
    """
    client = beaker_client(ctx)
    try:
        await client.systems_provision(
            fqdn,
            distro_tree_id,
            ks_meta=ks_meta,
            kernel_options=kernel_options,
            kernel_options_post=kernel_options_post,
            kickstart=kickstart,
            reboot=reboot,
        )
        return f"Provisioning started for '{fqdn}' with distro tree {distro_tree_id}."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to provision %s: %s", fqdn, exc)
        return _error(f"Failed to provision '{fqdn}': {exc}")
