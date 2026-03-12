"""Helpers for interacting with the ``bkr`` command-line client.

The ``bkr`` CLI handles Kerberos authentication natively, so every
function here requires only a valid Kerberos ticket (``kinit``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("mcp-beaker")

_BKR_TIMEOUT = 60


def is_bkr_available() -> bool:
    """Return True if the ``bkr`` CLI client is on PATH."""
    return shutil.which("bkr") is not None


async def _run_bkr(
    args: list[str],
    *,
    timeout: int = _BKR_TIMEOUT,
    error_prefix: str = "bkr command failed",
) -> subprocess.CompletedProcess[str]:
    """Run a ``bkr`` subcommand in a thread, raising on non-zero exit."""

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bkr", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    result = await asyncio.to_thread(_run)
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{error_prefix}: {msg}")
    return result


# -- Identity ---------------------------------------------------------------


async def bkr_whoami() -> dict[str, Any]:
    """Return identity info via ``bkr whoami``."""
    result = await _run_bkr(["whoami"], error_prefix="bkr whoami failed")
    text = result.stdout.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"username": text, "email_address": ""}


# -- Job operations ---------------------------------------------------------


async def bkr_job_submit(job_xml: str) -> str:
    """Submit a job via ``bkr job-submit``.  Returns the job ID (e.g. ``J:12345``)."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", prefix="beaker_job_", delete=False,
    )
    try:
        tmp.write(job_xml)
        tmp.close()
        result = await _run_bkr(
            ["job-submit", tmp.name],
            error_prefix="bkr job-submit failed",
        )
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    output = result.stdout.strip()
    if "J:" in output:
        start = output.index("J:")
        job_id = ""
        for ch in output[start:]:
            if ch in "J:0123456789":
                job_id += ch
            else:
                break
        if job_id:
            return job_id
    return output


async def bkr_job_cancel(taskspec: str, msg: str = "") -> None:
    """Cancel a job/recipe via ``bkr job-cancel``."""
    args = ["job-cancel", taskspec]
    if msg:
        args.extend(["--msg", msg])
    await _run_bkr(args, error_prefix=f"bkr job-cancel {taskspec} failed")


async def bkr_job_set_response(taskspec: str, response: str) -> None:
    """Ack/nak a job via ``bkr job-modify --response``."""
    await _run_bkr(
        ["job-modify", "--response", response, taskspec],
        error_prefix=f"bkr job-modify --response {taskspec} failed",
    )


# -- System operations ------------------------------------------------------


async def bkr_system_reserve(fqdn: str) -> None:
    """Reserve a system via ``bkr system-reserve``."""
    await _run_bkr(
        ["system-reserve", fqdn],
        error_prefix=f"bkr system-reserve {fqdn} failed",
    )


async def bkr_system_release(fqdn: str) -> None:
    """Release a system via ``bkr system-release``."""
    await _run_bkr(
        ["system-release", fqdn],
        error_prefix=f"bkr system-release {fqdn} failed",
    )


async def bkr_system_power(fqdn: str, action: str = "reboot", *, force: bool = False) -> None:
    """Power-control a system via ``bkr system-power``."""
    args = ["system-power", "--action", action, fqdn]
    if force:
        args.append("--force")
    await _run_bkr(args, error_prefix=f"bkr system-power {fqdn} failed")


async def bkr_system_provision(
    fqdn: str,
    distro_tree_id: int,
    *,
    ks_meta: str = "",
    kernel_options: str = "",
    kernel_options_post: str = "",
    kickstart: str = "",
    reboot: bool = True,
) -> None:
    """Provision a system via ``bkr system-provision``."""
    args = ["system-provision", "--distro-tree", str(distro_tree_id), fqdn]
    if ks_meta:
        args.extend(["--ks-meta", ks_meta])
    if kernel_options:
        args.extend(["--kernel-options", kernel_options])
    if kernel_options_post:
        args.extend(["--kernel-options-post", kernel_options_post])
    if not reboot:
        args.append("--no-reboot")

    if kickstart:
        ks_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ks", prefix="beaker_ks_", delete=False,
        )
        try:
            ks_tmp.write(kickstart)
            ks_tmp.close()
            args.extend(["--kickstart", ks_tmp.name])
            await _run_bkr(
                args, error_prefix=f"bkr system-provision {fqdn} failed",
            )
        finally:
            Path(ks_tmp.name).unlink(missing_ok=True)
    else:
        await _run_bkr(
            args, error_prefix=f"bkr system-provision {fqdn} failed",
        )


# -- Watchdog ---------------------------------------------------------------


async def bkr_watchdog_extend(taskspec: str, seconds: int) -> None:
    """Extend a task watchdog via ``bkr watchdog-extend``."""
    await _run_bkr(
        ["watchdog-extend", "--by", str(seconds), taskspec],
        error_prefix=f"bkr watchdog-extend {taskspec} failed",
    )


# -- Legacy aliases kept for backwards compatibility -------------------------

submit_job_via_bkr = bkr_job_submit
