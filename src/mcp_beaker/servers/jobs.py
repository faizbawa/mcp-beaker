"""Job-related Beaker tools (5 read + 5 write)."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from mcp_beaker.exceptions import BeakerError, BeakerNotFoundError
from mcp_beaker.models.job import JobInfo, LogFileEntry
from mcp_beaker.servers import beaker_client, mcp
from mcp_beaker.utils.bkr_cli import is_bkr_available, submit_job_via_bkr
from mcp_beaker.utils.diagnosis import attempt_auto_fix, diagnose_job
from mcp_beaker.utils.formatting import (
    FAILURE_RESULTS,
    FAILURE_STATUSES,
    POSITIVE_SETTLED_STATUSES,
    RUNNING_STATUSES,
    format_job_details,
    format_job_ids,
    format_job_logs,
    format_submit_success,
)
from mcp_beaker.utils.parsing import extract_job_id_from_message, parse_job_id, parse_task_id
from mcp_beaker.utils.xml_validation import validate_and_autofill_job_xml

logger = logging.getLogger("mcp-beaker")


def _error(msg: str) -> str:
    return f"Error: {msg}"


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@mcp.tool(
    tags={"beaker", "read", "jobs"},
    annotations={"title": "List Jobs", "readOnlyHint": True},
)
async def list_jobs(
    ctx: Context,
    owner: Annotated[
        str,
        Field(description="Filter by job owner username. Defaults to BEAKER_OWNER env var."),
    ] = "",
    limit: Annotated[int, Field(description="Max jobs to return. Default: 50.")] = 50,
    finished: Annotated[
        str,
        Field(description="'true' for finished only, 'false' for unfinished, empty for all."),
    ] = "",
    min_id: Annotated[int, Field(description="Minimum job ID. 0 to ignore.")] = 0,
    max_id: Annotated[int, Field(description="Maximum job ID. 0 to ignore.")] = 0,
    whiteboard: Annotated[str, Field(description="Substring match on job whiteboard.")] = "",
    fetch_details: Annotated[
        bool, Field(description="Fetch full details for each job. Default: true.")
    ] = True,
) -> str:
    """List Beaker jobs filtered by owner and other criteria.

    Uses XML-RPC jobs.filter() to find matching job IDs, then
    optionally fetches full details for each via the REST API.
    """
    client = beaker_client(ctx)
    resolved_owner = owner or client.config.owner
    if not resolved_owner:
        return _error("Could not determine username. Set BEAKER_OWNER or pass owner parameter.")

    filters: dict[str, Any] = {"owner": resolved_owner}
    if limit > 0:
        filters["limit"] = limit
    if finished.lower() == "true":
        filters["is_finished"] = True
    elif finished.lower() == "false":
        filters["is_finished"] = False
    if min_id > 0:
        filters["minid"] = min_id
    if max_id > 0:
        filters["maxid"] = max_id
    if whiteboard:
        filters["whiteboard"] = whiteboard

    try:
        job_ids = await client.jobs_filter(filters)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch jobs via XML-RPC: %s", exc)
        return _error(f"Failed to fetch jobs: {exc}")

    if not job_ids:
        return f"No jobs found for owner '{resolved_owner}'."
    if not fetch_details:
        return format_job_ids(job_ids, resolved_owner)

    numeric_ids: list[int] = []
    for jid in job_ids:
        nid, err = parse_job_id(str(jid))
        if not err:
            numeric_ids.append(int(nid))

    async def _fetch(nid: int) -> JobInfo | None:
        try:
            data = await client.rest_get_json(f"/jobs/{nid}")
            return JobInfo.model_validate(data)
        except Exception:
            return None

    results = await asyncio.gather(*(_fetch(nid) for nid in numeric_ids))
    jobs = [r for r in results if r is not None]
    return format_job_details(jobs, resolved_owner)


@mcp.tool(
    tags={"beaker", "read", "jobs"},
    annotations={"title": "Get Job Status", "readOnlyHint": True},
)
async def get_job_status(
    ctx: Context,
    job_id: Annotated[str, Field(description="Beaker job ID. Accepts 'J:12345' or '12345'.")],
) -> str:
    """Check the status of a Beaker job and diagnose any failures.

    Fetches detailed job information including recipe sets, recipes,
    and tasks, then highlights any problems found with failure analysis.
    """
    numeric_id, err = parse_job_id(job_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        data = await client.rest_get_json(f"/jobs/{numeric_id}")
        return diagnose_job(data)
    except BeakerNotFoundError:
        return _error(f"Job J:{numeric_id} not found.")
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch job status for %s: %s", numeric_id, exc)
        return _error(f"Failed to fetch status for job J:{numeric_id}: {exc}")


@mcp.tool(
    tags={"beaker", "read", "jobs"},
    annotations={"title": "Get Job Results XML", "readOnlyHint": True},
)
async def get_job_results_xml(
    ctx: Context,
    task_id: Annotated[
        str,
        Field(
            description="Beaker task ID (e.g. 'J:12345', 'RS:4321', 'R:99999'). "
            "Determines the scope of results returned."
        ),
    ],
    clone: Annotated[
        bool,
        Field(description="Return XML suitable for resubmission (no results). Default: false."),
    ] = False,
) -> str:
    """Export Beaker job results as XML.

    Returns the XML representation of a job component including its
    current state. Use clone=true to get XML suitable for resubmission.
    """
    formatted_id, err = parse_task_id(task_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        xml_text = await client.taskactions_to_xml(formatted_id, clone=clone)
        return xml_text
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch results XML for %s: %s", task_id, exc)
        return _error(f"Failed to fetch results XML for {task_id}: {exc}")


@mcp.tool(
    tags={"beaker", "read", "jobs"},
    annotations={"title": "Get Job Logs", "readOnlyHint": True},
)
async def get_job_logs(
    ctx: Context,
    task_id: Annotated[
        str,
        Field(
            description="Beaker task ID (e.g. 'J:12345', 'R:99999', 'T:88888'). "
            "Returns log files for this component and its descendants."
        ),
    ],
) -> str:
    """List all log files for a Beaker job, recipe, or task.

    Returns URLs to log files including console.log, anaconda logs,
    and task output. Critical for debugging installation failures.
    """
    formatted_id, err = parse_task_id(task_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        files_raw = await client.taskactions_files(formatted_id)
        files = [LogFileEntry.model_validate(f) for f in files_raw]
        return format_job_logs(files, formatted_id)
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to fetch logs for %s: %s", task_id, exc)
        return _error(f"Failed to fetch logs for {task_id}: {exc}")


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Submit Job", "readOnlyHint": False},
)
async def submit_job(
    ctx: Context,
    job_xml: Annotated[
        str,
        Field(description="Complete Beaker job XML string defining the job to submit."),
    ],
    force: Annotated[
        bool,
        Field(description="Skip mandatory-field warnings and submit as-is. Default: false."),
    ] = False,
) -> str:
    """Submit a Beaker job from a complete job XML document.

    The XML is validated before submission. Missing optional fields
    are auto-filled with sensible defaults. Uses Kerberos auth via
    the bkr CLI if available, otherwise falls back to XML-RPC password auth.
    """
    if not job_xml or not job_xml.strip():
        return _error("job_xml is required. Provide a valid Beaker job XML string.")

    client = beaker_client(ctx)
    structural_errors, filled_xml, auto_filled, still_missing = validate_and_autofill_job_xml(
        job_xml
    )
    if structural_errors:
        header = "Job XML has structural errors that must be fixed:\n"
        body = "\n".join(f"  - {e}" for e in structural_errors)
        return header + body

    if still_missing and not force:
        parts: list[str] = []
        if auto_filled:
            parts.append("The following fields were auto-filled with defaults:\n")
            parts.append("\n".join(f"  + {m}" for m in auto_filled))
            parts.append("\n\n")
        parts.append("The following fields still need your input:\n")
        parts.append("\n".join(f"  - {m}" for m in still_missing))
        parts.append(
            "\n\nPlease provide these values in the job XML and "
            "resubmit, or re-call with force=true to submit as-is."
        )
        parts.append("\n\nUpdated XML with defaults applied:\n\n" + filled_xml)
        return "".join(parts)

    submit_xml = filled_xml if auto_filled else job_xml

    if is_bkr_available():
        result = await _submit_via_bkr(client.config.url, submit_xml)
    else:
        result = await _submit_via_xmlrpc(client, submit_xml)

    if auto_filled:
        note = "\n\nNote -- the following defaults were auto-filled:\n"
        note += "\n".join(f"  + {m}" for m in auto_filled)
        result += note

    return result


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Clone Job", "readOnlyHint": False},
)
async def clone_job(
    ctx: Context,
    job_id: Annotated[str, Field(description="Job ID to clone (e.g. 'J:12345' or '12345').")],
) -> str:
    """Clone (re-submit) an existing Beaker job.

    Fetches the original job's XML in clone mode, then submits it
    as a new job. Useful for retrying failed jobs or running the
    same test again.
    """
    numeric_id, err = parse_job_id(job_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        xml_text = await client.taskactions_to_xml(f"J:{numeric_id}", clone=True)
    except BeakerError as exc:
        return _error(f"Failed to fetch clone XML for J:{numeric_id}: {exc}")
    except Exception as exc:
        return _error(f"Failed to fetch clone XML: {exc}")

    if is_bkr_available():
        return await _submit_via_bkr(client.config.url, xml_text)
    return await _submit_via_xmlrpc(client, xml_text)


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Cancel Job", "readOnlyHint": False},
)
async def cancel_job(
    ctx: Context,
    task_id: Annotated[
        str,
        Field(
            description="Task ID to cancel (e.g. 'J:12345', 'RS:4321'). "
            "Cancelling any part cancels the entire job."
        ),
    ],
    reason: Annotated[str, Field(description="Reason for cancellation.")] = "Cancelled via MCP",
) -> str:
    """Cancel a running or queued Beaker job.

    Note: cancelling any part of a job (recipe, recipe set) cancels
    the entire job. The reason is recorded in the job history.
    """
    formatted_id, err = parse_task_id(task_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        await client.taskactions_stop(formatted_id, reason)
        return f"Successfully cancelled {formatted_id}. Reason: {reason}"
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to cancel %s: %s", task_id, exc)
        return _error(f"Failed to cancel {task_id}: {exc}")


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Watch Job", "readOnlyHint": False},
)
async def watch_job(
    ctx: Context,
    job_id: Annotated[str, Field(description="Beaker job ID (e.g. 'J:12345' or '12345').")],
    max_retries: Annotated[
        int, Field(description="Max auto-correct-and-resubmit cycles. Default: 2.")
    ] = 2,
    poll_interval: Annotated[
        int, Field(description="Seconds between status polls. Default: 30.")
    ] = 30,
) -> str:
    """Watch a Beaker job until completion, with failure analysis and auto-retry.

    Polls the job continuously. On success, returns a report. On failure,
    performs deep analysis (failure reasons, constraints, suggestions)
    and can auto-generate a corrected XML and resubmit up to max_retries times.
    Also works on already-finished jobs for post-mortem analysis.
    """
    numeric_id, err = parse_job_id(job_id)
    if err:
        return err
    client = beaker_client(ctx)
    full_report_parts: list[str] = []
    current_id = numeric_id
    retries_used = 0

    while True:
        data, poll_err = await _poll_until_done(client, current_id, poll_interval)
        if poll_err:
            full_report_parts.append(poll_err)
            break

        assert data is not None  # noqa: S101
        status = data.get("status", "Unknown")
        result = data.get("result", "Unknown")

        diagnosis = diagnose_job(data)
        full_report_parts.append(diagnosis)

        is_failed = status in FAILURE_STATUSES or result in FAILURE_RESULTS
        if not is_failed:
            is_finished = data.get("is_finished", False)
            if is_finished:
                full_report_parts.append(
                    "\nJob completed successfully -- no failure analysis needed."
                )
            else:
                full_report_parts.append(
                    f"\nJob is in a positive state ({status} / {result}) "
                    "-- no failure to analyse. Stopping watch."
                )
            break

        try:
            analysis_text, corrected_xml = await attempt_auto_fix(
                client.config.url, int(current_id), client.rest_get_text
            )
        except Exception as exc:
            logger.error("Failure analysis error for J:%s: %s", current_id, exc)
            full_report_parts.append(f"\nFailure analysis could not be completed: {exc}")
            break

        full_report_parts.append("")
        full_report_parts.append(analysis_text)

        if corrected_xml is None:
            full_report_parts.append("\nNo automatic correction available -- exiting.")
            break

        if retries_used >= max_retries:
            full_report_parts.append(
                f"\nReached maximum auto-retries ({max_retries}). "
                "Please review the suggestions above."
            )
            break

        retries_used += 1
        full_report_parts.append(f"\n--- Auto-retry {retries_used}/{max_retries} ---")

        if is_bkr_available():
            submit_result = await _submit_via_bkr(client.config.url, corrected_xml)
        else:
            submit_result = await _submit_via_xmlrpc(client, corrected_xml)

        full_report_parts.append(submit_result)
        new_id = extract_job_id_from_message(submit_result)
        if new_id is None:
            full_report_parts.append("Could not parse new job ID. Exiting.")
            break
        current_id = new_id
        full_report_parts.append(f"Now watching corrected job J:{current_id} ...\n")

    return "\n".join(full_report_parts)


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Extend Watchdog", "readOnlyHint": False},
)
async def extend_watchdog(
    ctx: Context,
    task_id: Annotated[int, Field(description="Numeric task ID to extend the watchdog for.")],
    seconds: Annotated[int, Field(description="Number of seconds to extend the watchdog by.")],
) -> str:
    """Extend the watchdog timer for a running Beaker task.

    Prevents a long-running reservation from being reclaimed by Beaker's
    watchdog. The task must be currently running.
    """
    if seconds <= 0:
        return _error("seconds must be a positive integer.")
    client = beaker_client(ctx)
    try:
        await client.recipes_tasks_extend(task_id, seconds)
        hours = seconds / 3600
        return f"Watchdog extended for task T:{task_id} by {seconds} seconds ({hours:.1f} hours)."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to extend watchdog for T:%s: %s", task_id, exc)
        return _error(f"Failed to extend watchdog for T:{task_id}: {exc}")


@mcp.tool(
    tags={"beaker", "write", "jobs"},
    annotations={"title": "Set Job Response", "readOnlyHint": False},
)
async def set_job_response(
    ctx: Context,
    task_id: Annotated[
        str,
        Field(description="Task ID for the recipe set or job (e.g. 'RS:4321' or 'J:12345')."),
    ],
    response: Annotated[
        str,
        Field(description="Response to set: 'ack' or 'nak' (nak is an alias for waiving)."),
    ],
) -> str:
    """Set the response (ack/nak) for a Beaker recipe set or job.

    Used to acknowledge or waive recipe set results. Setting 'nak'
    is equivalent to waiving the result.
    """
    if response not in ("ack", "nak"):
        return _error(f"Invalid response '{response}'. Must be 'ack' or 'nak'.")
    formatted_id, err = parse_task_id(task_id)
    if err:
        return err
    client = beaker_client(ctx)
    try:
        await client.jobs_set_response(formatted_id, response)
        return f"Set response '{response}' on {formatted_id}."
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to set response on %s: %s", task_id, exc)
        return _error(f"Failed to set response on {task_id}: {exc}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _submit_via_bkr(base_url: str, job_xml: str) -> str:
    try:
        job_id = await submit_job_via_bkr(job_xml)
        return format_submit_success(base_url, job_id, auth_method="Kerberos (bkr CLI)")
    except RuntimeError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to submit job via bkr: %s", exc)
        return _error(f"Failed to submit job via bkr: {exc}")


async def _submit_via_xmlrpc(client: Any, job_xml: str) -> str:
    try:
        job_id = await client.jobs_upload(job_xml)
        return format_submit_success(
            client.config.url,
            job_id,
            auth_method=f"XML-RPC (user={client.config.username})",
        )
    except BeakerError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.error("Failed to submit job: %s", exc)
        return _error(f"Failed to submit job: {exc}")


async def _poll_until_done(
    client: Any, numeric_id: str, poll_interval: int
) -> tuple[dict[str, Any] | None, str | None]:
    poll_count = 0
    while True:
        poll_count += 1
        try:
            data = await client.rest_get_json(f"/jobs/{numeric_id}")
        except BeakerNotFoundError:
            return None, _error(f"Job J:{numeric_id} not found.")
        except Exception as exc:
            return None, _error(f"Failed to fetch job J:{numeric_id}: {exc}")

        status = data.get("status", "Unknown")
        result = data.get("result", "Unknown")
        is_finished = data.get("is_finished", False)

        if is_finished or status not in RUNNING_STATUSES:
            return data, None

        is_positive = result not in FAILURE_RESULTS and status in POSITIVE_SETTLED_STATUSES
        if is_positive:
            logger.info(
                "Job J:%s reached positive state (%s / %s) -- stopping poll.",
                numeric_id,
                status,
                result,
            )
            return data, None

        logger.info(
            "Job J:%s still %s -- poll #%d, waiting %ds...",
            numeric_id,
            status,
            poll_count,
            poll_interval,
        )
        await asyncio.sleep(poll_interval)
