"""Job ID and message parsing utilities."""

from __future__ import annotations


def parse_job_id(job_id: str) -> tuple[str, str | None]:
    """Parse and validate a Beaker job ID string.

    Accepts ``"J:12345"``, ``"12345"``, or just the numeric part.
    Returns ``(numeric_id, error_or_none)``.
    """
    if not job_id or not job_id.strip():
        return "", "Error: job_id is required."
    numeric_id = job_id.strip().replace("J:", "")
    if not numeric_id.isdigit():
        return "", (
            f"Error: Invalid job ID '{job_id}'. Expected a numeric ID like 12345 or J:12345."
        )
    return numeric_id, None


def parse_task_id(task_id: str) -> tuple[str, str | None]:
    """Parse a Beaker task ID string.

    Accepts ``"T:99999"`` or ``"99999"``.
    Returns ``(formatted_id, error_or_none)`` where formatted_id
    includes the ``T:`` prefix.
    """
    if not task_id or not task_id.strip():
        return "", "Error: task_id is required."
    cleaned = task_id.strip()
    if cleaned.startswith(("T:", "R:", "RS:", "J:")):
        return cleaned, None
    if cleaned.isdigit():
        return f"T:{cleaned}", None
    return "", (
        f"Error: Invalid task ID '{task_id}'. "
        "Expected format like T:99999, R:12345, RS:4321, or J:12345."
    )


def extract_job_id_from_message(message: str) -> str | None:
    """Extract a numeric job ID from a result message containing ``J:12345``.

    Returns the numeric part, or ``None`` if no job ID is found.
    """
    if "J:" not in message:
        return None
    start = message.index("J:")
    digits = ""
    for ch in message[start + 2 :]:
        if ch.isdigit():
            digits += ch
        else:
            break
    return digits if digits else None
