"""Reusable MCP prompt templates for Beaker workflows."""

from __future__ import annotations

from fastmcp.prompts import Message

from mcp_beaker.servers import mcp


@mcp.prompt()
def reserve_system(
    arch: str,
    distro: str,
    hostname_pattern: str,
    reserve_hours: int = 99,
    min_disk_gb: int = 0,
    min_processors: int = 0,
    post_script: str = "",
) -> list[Message]:
    """Reserve a Beaker system with the given requirements.

    Generates a step-by-step workflow to find the latest matching distro,
    build a proper job XML, and submit it.
    """
    reserve_seconds = reserve_hours * 3600

    instructions = [
        "Follow these steps to reserve a Beaker system:\n",
        "## Step 1: Find the latest distro",
        f"Call list_distro_trees with name='{distro}' and arch='{arch}'.",
        "Pick the most recent compose from the results.\n",
        "## Step 2: Build the job XML",
        "Build a complete Beaker job XML with these specs:",
        f"  - Architecture: {arch}",
        "  - Distro variant: BaseOS",
        f"  - Hostname pattern: <hostname op='like' value='{hostname_pattern}'/>",
        f"  - Reserve time: {reserve_seconds} seconds ({reserve_hours} hours)",
    ]

    if min_disk_gb > 0:
        disk_mb = min_disk_gb * 1024
        instructions.append(
            f"  - Disk space: <key_value key='DISKSPACE' op='>=' value='{disk_mb}'/>"
        )
    if min_processors > 0:
        instructions.append(
            f"  - Processors: <key_value key='PROCESSORS' op='>=' value='{min_processors}'/>"
        )

    instructions.append("  - Include <system_type value='Machine'/> in hostRequires")
    instructions.append(
        "  - Tasks: /distribution/check-install first, "
        "then /distribution/reservesys with the RESERVETIME param"
    )

    if post_script:
        instructions.append("\n## Post-install script")
        instructions.append("Add a <ks_append> with a CDATA %post section containing:")
        instructions.append(f"  {post_script}")

    instructions.append(
        "\n## Step 3: Submit and confirm"
        "\nCall submit_job with the built XML."
        "\nThen call get_job_status to confirm it is queued or running."
        "\nReport the Job ID, URL, and auth method to the user."
    )

    return [Message("\n".join(instructions))]


@mcp.prompt()
def diagnose_beaker_job(job_id: str) -> list[Message]:
    """Step-by-step diagnosis workflow for a Beaker job."""
    text = (
        f"Diagnose Beaker job {job_id} step by step:\n\n"
        "## Step 1: Check status\n"
        f"Call get_job_status with job_id='{job_id}'.\n"
        "Identify the overall job status and which tasks passed or failed.\n\n"
        "## Step 2: Deep analysis (if failed)\n"
        f"If the job failed, call watch_job with job_id='{job_id}' "
        "to get a deep failure analysis including:\n"
        "  - Exact failure reasons from task results\n"
        "  - Host and distro constraints that were used\n"
        "  - Whether the distro is still available\n"
        "  - Whether matching hosts exist\n\n"
        "## Step 3: Suggest fixes\n"
        "Based on the analysis:\n"
        "  - If 'does not match any systems': check hostname pattern "
        "and hardware constraints\n"
        "  - If task failed: identify the specific task and its logs\n"
        "  - If aborted: check if the system was reclaimed or timed out\n\n"
        "## Step 4: Offer to resubmit\n"
        "If a fix is possible, offer to build a corrected XML and resubmit."
    )
    return [Message(text)]
