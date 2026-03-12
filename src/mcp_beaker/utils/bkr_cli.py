"""Helpers for interacting with the ``bkr`` command-line client."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("mcp-beaker")


def is_bkr_available() -> bool:
    """Return True if the ``bkr`` CLI client is on PATH."""
    return shutil.which("bkr") is not None


async def submit_job_via_bkr(job_xml: str) -> str:
    """Submit a Beaker job using the ``bkr job-submit`` CLI.

    The bkr client handles Kerberos authentication natively, so no
    username/password is needed.  A valid Kerberos ticket (``kinit``)
    is the only prerequisite.

    Returns the job ID string (e.g. ``J:12345``) on success.
    Raises ``RuntimeError`` on failure.
    """
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".xml", prefix="beaker_job_", delete=False)
    try:
        tmp.write(job_xml)
        tmp.close()

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bkr", "job-submit", tmp.name],
                capture_output=True,
                text=True,
                timeout=60,
            )

        result = await asyncio.to_thread(_run)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"bkr job-submit failed: {error_msg}")

    output = result.stdout.strip()
    if "J:" in output:
        start = output.index("J:")
        job_id = ""
        for ch in output[start:]:
            if ch in "JjJ:0123456789":
                job_id += ch
            else:
                break
        if job_id:
            return job_id

    return output
