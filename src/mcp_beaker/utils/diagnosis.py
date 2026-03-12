"""Job failure diagnosis and auto-fix logic."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from mcp_beaker.utils.formatting import FAILURE_RESULTS, FAILURE_STATUSES
from mcp_beaker.utils.xml_validation import _find_descendant

logger = logging.getLogger("mcp-beaker")


def diagnose_job(data: dict[str, Any]) -> str:
    """Analyse a job JSON response and produce a human-readable diagnosis."""
    lines: list[str] = []

    job_id = data.get("id", "?")
    status = data.get("status", "Unknown")
    result = data.get("result", "Unknown")
    whiteboard = data.get("whiteboard", "") or ""
    is_finished = data.get("is_finished", False)
    submit_time = data.get("submitted_time", "")

    lines.append(f"Job J:{job_id}")
    lines.append("=" * 40)
    if whiteboard:
        lines.append(f"  Whiteboard : {whiteboard}")
    lines.append(f"  Status     : {status}")
    lines.append(f"  Result     : {result}")
    lines.append(f"  Finished   : {'Yes' if is_finished else 'No'}")
    if submit_time:
        lines.append(f"  Submitted  : {submit_time}")

    is_healthy = status not in FAILURE_STATUSES and result not in FAILURE_RESULTS
    if is_healthy and not is_finished:
        lines.append("\n  Job is still running -- no problems detected so far.")
    elif is_healthy and is_finished:
        lines.append("\n  Job completed successfully.")
    else:
        lines.append("\n  ** Problem detected at job level **")

    recipesets = data.get("recipesets", [])
    if not recipesets:
        lines.append("\n  No recipe set data available.")
        return "\n".join(lines)

    for rs_idx, rs in enumerate(recipesets, start=1):
        rs_id = rs.get("id", "?")
        rs_status = rs.get("status", "Unknown")
        rs_result = rs.get("result", "Unknown")
        rs_priority = rs.get("priority", "")

        lines.append(f"\n  Recipe Set #{rs_idx}  (RS:{rs_id})")
        lines.append(f"    Status   : {rs_status}")
        lines.append(f"    Result   : {rs_result}")
        if rs_priority:
            lines.append(f"    Priority : {rs_priority}")
        if rs_status in FAILURE_STATUSES or rs_result in FAILURE_RESULTS:
            lines.append("    ** This recipe set has problems **")

        recipes = rs.get("recipes", [])
        for r_idx, recipe in enumerate(recipes, start=1):
            r_id = recipe.get("id", "?")
            r_status = recipe.get("status", "Unknown")
            r_result = recipe.get("result", "Unknown")
            r_distro = recipe.get("distro_tree", {})
            r_system = recipe.get("system", {})
            r_whiteboard = recipe.get("whiteboard", "") or ""
            r_logs = recipe.get("logs", [])

            lines.append(f"\n    Recipe #{r_idx}  (R:{r_id})")
            lines.append(f"      Status : {r_status}")
            lines.append(f"      Result : {r_result}")
            if r_whiteboard:
                lines.append(f"      Whiteboard : {r_whiteboard}")

            if isinstance(r_distro, dict) and r_distro:
                distro_name = r_distro.get("distro", {}).get("name", "")
                distro_arch = r_distro.get("arch", "")
                distro_variant = r_distro.get("variant", "")
                parts = [p for p in [distro_name, distro_variant, distro_arch] if p]
                if parts:
                    lines.append(f"      Distro : {' / '.join(parts)}")

            if isinstance(r_system, dict) and r_system:
                sys_fqdn = r_system.get("fqdn", "")
                if sys_fqdn:
                    lines.append(f"      System : {sys_fqdn}")

            if r_status in FAILURE_STATUSES or r_result in FAILURE_RESULTS:
                lines.append("      ** This recipe failed **")
                status_reason = recipe.get("status_reason", "")
                if status_reason:
                    lines.append(f"      Reason : {status_reason}")

            tasks = recipe.get("tasks", [])
            for t_idx, task in enumerate(tasks, start=1):
                t_id = task.get("id", "?")
                t_name = task.get("name", "?")
                t_status = task.get("status", "Unknown")
                t_result = task.get("result", "Unknown")
                marker = ""
                if t_status in FAILURE_STATUSES or t_result in FAILURE_RESULTS:
                    marker = "  << FAILED"
                lines.append(
                    f"      Task #{t_idx} (T:{t_id}): {t_name}  [{t_status} / {t_result}]{marker}"
                )

            if r_logs:
                lines.append("      Logs:")
                for log_entry in r_logs[:5]:
                    log_href = log_entry.get("href", "") or log_entry.get("path", "")
                    if log_href:
                        lines.append(f"        - {log_href}")
                if len(r_logs) > 5:
                    lines.append(f"        ... and {len(r_logs) - 5} more")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deep failure analysis
# ---------------------------------------------------------------------------


def _extract_failure_reasons(xml_text: str) -> list[str]:
    reasons: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return reasons
    for result_el in root.iter("result"):
        text = (result_el.text or "").strip()
        result_val = result_el.get("result", "")
        if text and result_val in ("Warn", "Fail", "Panic"):
            if text not in reasons:
                reasons.append(text)
    return reasons


def _extract_constraints(xml_text: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return info

    recipe = root.find(".//recipe")
    if recipe is None:
        return info

    distro_req = recipe.find("distroRequires")
    if distro_req is not None:
        for tag in (
            "distro_name",
            "distro_family",
            "distro_arch",
            "distro_variant",
            "distro_method",
        ):
            el = _find_descendant(distro_req, tag)
            if el is not None:
                info[tag] = {"op": el.get("op", ""), "value": el.get("value", "")}

    host_req = recipe.find("hostRequires")
    if host_req is not None:
        hostname_el = _find_descendant(host_req, "hostname")
        if hostname_el is not None:
            info["hostname"] = {
                "op": hostname_el.get("op", ""),
                "value": hostname_el.get("value", ""),
            }
        sys_type_el = _find_descendant(host_req, "system_type")
        if sys_type_el is not None:
            info["system_type"] = {"value": sys_type_el.get("value", "")}
        kv_list: list[dict[str, str]] = []
        for kv in host_req.iter("key_value"):
            kv_list.append(
                {
                    "key": kv.get("key", ""),
                    "op": kv.get("op", ""),
                    "value": kv.get("value", ""),
                }
            )
        if kv_list:
            info["key_values"] = kv_list

    return info


def _build_suggestions(reasons: list[str], constraints: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    no_match = any("does not match any systems" in r for r in reasons)
    if not no_match:
        return suggestions

    hostname = constraints.get("hostname", {})
    hval = hostname.get("value", "")
    hop = hostname.get("op", "")
    if hval:
        suggestions.append(
            f"Hostname filter: op='{hop}' value='{hval}'. "
            "Verify the pattern matches actual FQDNs in Beaker. "
            "Try a broader wildcard (e.g. change 'ampere-mts%' to 'ampere-mtsnow%')."
        )

    for kv in constraints.get("key_values", []):
        key = kv.get("key", "")
        val = kv.get("value", "")
        if key == "MEMORY":
            try:
                mb = int(val)
                gb = mb // 1024
                suggestions.append(
                    f"MEMORY >= {val} MB ({gb} GB). "
                    "This may exceed what matching hosts have. "
                    "Try lowering the memory requirement."
                )
            except ValueError:
                pass
        elif key == "DISKSPACE":
            suggestions.append(
                f"DISKSPACE >= {val} MB. "
                "Verify the target hosts have enough disk. Try lowering if unsure."
            )
        elif key == "PROCESSORS":
            suggestions.append(f"PROCESSORS >= {val}. Verify the target hosts have enough cores.")

    distro_name = constraints.get("distro_name", {})
    if distro_name.get("value"):
        suggestions.append(
            f"Distro: {distro_name['value']}. "
            "Confirm this compose exists and is available "
            "on lab controllers serving the target hosts."
        )

    if not suggestions:
        suggestions.append(
            "No systems matched the combined constraints. "
            "Try relaxing one filter at a time to isolate the problem."
        )
    return suggestions


def _generate_corrected_xml(
    xml_text: str, reasons: list[str], constraints: dict[str, Any]
) -> str | None:
    no_match = any("does not match any systems" in r for r in reasons)
    if not no_match:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    changed = False
    recipe = root.find(".//recipe")
    if recipe is None:
        return None
    host_req = recipe.find("hostRequires")
    if host_req is None:
        return None
    hostname_el = _find_descendant(host_req, "hostname")
    if hostname_el is not None:
        hval = hostname_el.get("value", "")
        if hval and "%" not in hval:
            hostname_el.set("value", hval + "%")
            hostname_el.set("op", "like")
            changed = True
    if not changed:
        return None
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


async def attempt_auto_fix(
    base_url: str, job_id: int, rest_get_text: Any
) -> tuple[str, str | None]:
    """Analyse a failed job and try to produce a corrected XML.

    Returns ``(analysis_report, corrected_xml_or_none)``.
    """
    lines: list[str] = []

    try:
        xml_text = await rest_get_text(f"/jobs/{job_id}.xml")
    except Exception as exc:
        return f"Could not fetch job XML for analysis: {exc}", None

    reasons = _extract_failure_reasons(xml_text)
    if not reasons:
        return (
            f"Job J:{job_id} failed but no detailed failure reason was found in the task results."
        ), None

    lines.append("Failure Analysis")
    lines.append("=" * 40)
    lines.append("")
    lines.append("Failure reason(s):")
    for r in reasons:
        lines.append(f"  - {r}")

    constraints = _extract_constraints(xml_text)
    if constraints:
        lines.append("")
        lines.append("Job constraints:")
        for key, val in constraints.items():
            if key == "key_values":
                for kv in val:
                    lines.append(f"  - {kv['key']} {kv['op']} {kv['value']}")
            elif isinstance(val, dict):
                op = val.get("op", "")
                v = val.get("value", "")
                display = f"{op} {v}".strip() if op else v
                lines.append(f"  - {key}: {display}")

    suggestions = _build_suggestions(reasons, constraints)
    if suggestions:
        lines.append("")
        lines.append("Suggested fixes:")
        for idx, s in enumerate(suggestions, start=1):
            lines.append(f"  {idx}. {s}")

    corrected = _generate_corrected_xml(xml_text, reasons, constraints)
    if corrected:
        lines.append("")
        lines.append("A corrected XML was auto-generated and will be resubmitted automatically.")
    else:
        lines.append("")
        lines.append(
            "No automatic XML correction was possible. "
            "Please adjust the constraints manually based on the "
            "suggestions above."
        )

    return "\n".join(lines), corrected
