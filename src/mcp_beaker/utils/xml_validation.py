"""Beaker job XML validation and auto-fill logic.

Validates structural correctness and injects sensible defaults for
missing mandatory fields.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any

MANDATORY_FIELDS: list[dict[str, Any]] = [
    {
        "scope": "job",
        "type": "attribute",
        "name": "retention_tag",
        "hint": "e.g. retention_tag='scratch'",
        "default": "scratch",
    },
    {
        "scope": "job",
        "type": "child",
        "name": "whiteboard",
        "hint": "Job whiteboard description (non-empty text)",
    },
    {
        "scope": "recipeSet",
        "type": "attribute",
        "name": "priority",
        "hint": "e.g. priority='Normal'",
        "default": "Normal",
    },
    {
        "scope": "recipe",
        "type": "attribute",
        "name": "role",
        "hint": "e.g. role='RECIPE_MEMBERS'",
        "default": "RECIPE_MEMBERS",
    },
    {
        "scope": "recipe",
        "type": "child",
        "name": "autopick",
        "hint": "e.g. <autopick random='false'/>",
        "default": {"random": "false"},
    },
    {
        "scope": "recipe",
        "type": "child",
        "name": "watchdog",
        "hint": "e.g. <watchdog panic='ignore'/>",
        "default": {"panic": "ignore"},
    },
    {
        "scope": "distroRequires",
        "type": "descendant",
        "name": "distro_family",
        "hint": "e.g. <distro_family op='=' value='RedHatEnterpriseLinux10'/>",
    },
    {
        "scope": "distroRequires",
        "type": "descendant",
        "name": "distro_variant",
        "hint": "e.g. <distro_variant op='=' value='BaseOS'/>",
        "default": {"op": "=", "value": "BaseOS"},
    },
    {
        "scope": "distroRequires",
        "type": "descendant",
        "name": "distro_name",
        "hint": "e.g. <distro_name op='=' value='RHEL-10.2-20260127.0'/>",
    },
    {
        "scope": "distroRequires",
        "type": "descendant",
        "name": "distro_arch",
        "hint": "e.g. <distro_arch op='=' value='aarch64'/>",
    },
    {
        "scope": "hostRequires",
        "type": "descendant",
        "name": "hostname",
        "hint": (
            "e.g. <hostname op='=' value='host.example.com'/> or "
            "<hostname op='like' value='ampere%'/> for wildcard"
        ),
    },
    {
        "scope": "hostRequires",
        "type": "descendant",
        "name": "system_type",
        "hint": "e.g. <system_type value='Machine'/>",
        "default": {"value": "Machine"},
    },
    {
        "scope": "task",
        "type": "attribute",
        "name": "name",
        "hint": "e.g. name='/distribution/reservesys'",
    },
    {
        "scope": "task",
        "type": "attribute",
        "name": "role",
        "hint": "e.g. role='STANDALONE'",
        "default": "STANDALONE",
    },
]

# ---------------------------------------------------------------------------
# Distro-name → family inference (regex-based, first match wins)
# ---------------------------------------------------------------------------
#
# Covers all major Linux distributions commonly imported into Beaker.
# The list is derived from Beaker's own ``beaker-import`` behaviour
# (which reads the ``family`` field from ``.composeinfo`` / ``.treeinfo``)
# and the naming conventions documented at beaker-project.org.
#
# Users can extend this list at runtime via the environment variable
# ``BEAKER_EXTRA_DISTRO_PATTERNS`` -- a semicolon-separated list of
# ``prefix=FamilyName`` pairs, e.g.:
#   BEAKER_EXTRA_DISTRO_PATTERNS="MyDistro-=MyDistroFamily;OtherOS-=OtherFamily"
# These custom entries are checked *before* the built-in rules.

_DISTRO_FAMILY_RULES: list[tuple[re.Pattern[str], str]] = [
    # Red Hat Enterprise Linux
    (re.compile(r"^RHEL-(\d+)"), r"RedHatEnterpriseLinux\1"),
    # CentOS Stream
    (re.compile(r"^CentOS-Stream-(\d+)"), r"CentOSStream\1"),
    # CentOS (traditional releases)
    (re.compile(r"^CentOS-(\d+)"), r"CentOS\1"),
    # Fedora
    (re.compile(r"^Fedora-Rawhide"), "FedoraRawhide"),
    (re.compile(r"^Fedora-(\d+)"), r"Fedora\1"),
    # AlmaLinux
    (re.compile(r"^AlmaLinux-(\d+)"), r"AlmaLinux\1"),
    # Rocky Linux
    (re.compile(r"^Rocky-(\d+)"), r"RockyLinux\1"),
    (re.compile(r"^RockyLinux-(\d+)"), r"RockyLinux\1"),
    # Oracle Linux
    (re.compile(r"^OracleLinux-(\d+)"), r"OracleLinux\1"),
    (re.compile(r"^OL-(\d+)"), r"OracleLinux\1"),
    # SUSE Linux Enterprise
    (re.compile(r"^SLES-(\d+)"), r"SUSELinuxEnterprise\1"),
    (re.compile(r"^SLED-(\d+)"), r"SUSELinuxEnterprise\1"),
    # openSUSE
    (re.compile(r"^openSUSE-Leap-(\d+)"), r"openSUSELeap\1"),
    (re.compile(r"^openSUSE-Tumbleweed"), "openSUSETumbleweed"),
    # Ubuntu
    (re.compile(r"^Ubuntu-(\d+)"), r"Ubuntu\1"),
    # Debian
    (re.compile(r"^Debian-(\d+)"), r"Debian\1"),
    # Amazon Linux
    (re.compile(r"^AmazonLinux-(\d+)"), r"AmazonLinux\1"),
    (re.compile(r"^AL(\d+)"), r"AmazonLinux\1"),
    # Scientific Linux
    (re.compile(r"^SL-(\d+)"), r"ScientificLinux\1"),
    (re.compile(r"^ScientificLinux-(\d+)"), r"ScientificLinux\1"),
    # EuroLinux
    (re.compile(r"^EuroLinux-(\d+)"), r"EuroLinux\1"),
    # Navy Linux
    (re.compile(r"^NavyLinux-(\d+)"), r"NavyLinux\1"),
    # Arch Linux
    (re.compile(r"^Arch-"), "ArchLinux"),
    # Gentoo
    (re.compile(r"^Gentoo-"), "Gentoo"),
]

_extra_patterns_cache: list[tuple[re.Pattern[str], str]] | None = None


def _load_extra_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Load user-defined distro patterns from ``BEAKER_EXTRA_DISTRO_PATTERNS``."""
    global _extra_patterns_cache  # noqa: PLW0603
    if _extra_patterns_cache is not None:
        return _extra_patterns_cache

    raw = os.environ.get("BEAKER_EXTRA_DISTRO_PATTERNS", "")
    extras: list[tuple[re.Pattern[str], str]] = []
    if raw:
        for pair in raw.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            prefix, family = pair.split("=", 1)
            extras.append((re.compile(rf"^{re.escape(prefix.strip())}"), family.strip()))
    _extra_patterns_cache = extras
    return extras


def _infer_distro_family(distro_name_value: str) -> str | None:
    """Derive the Beaker distro-family name from a distro_name value.

    E.g. ``"RHEL-10.2-20260127.0"`` -> ``"RedHatEnterpriseLinux10"``.
    Returns ``None`` when the pattern is not recognised.
    """
    for pattern, replacement in _load_extra_patterns():
        m = pattern.search(distro_name_value)
        if m:
            return m.expand(replacement)

    for pattern, replacement in _DISTRO_FAMILY_RULES:
        m = pattern.search(distro_name_value)
        if m:
            return m.expand(replacement)

    return None


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _find_descendant(element: ET.Element, tag: str) -> ET.Element | None:
    """Recursively search for *tag* inside *element*, walking into
    ``<and>`` / ``<or>`` wrapper elements that Beaker uses in
    ``<distroRequires>`` and ``<hostRequires>``.

    Returns the first matching element, or ``None``.
    """
    for child in element:
        if child.tag == tag:
            return child
        if child.tag in ("and", "or"):
            found = _find_descendant(child, tag)
            if found is not None:
                return found
    return None


def _check_field(
    rule: dict[str, Any],
    element: ET.Element,
    label: str,
) -> str | None:
    """Check a single mandatory-field *rule* against *element*.

    Returns a human-readable error string, or ``None`` when the rule passes.
    """
    rule_type = rule["type"]
    name = rule["name"]
    hint = rule["hint"]

    if rule_type == "attribute":
        if not element.get(name, ""):
            return f"{label}: missing required attribute '{name}' ({hint})."
        return None

    if rule_type == "child":
        child = element.find(name)
        if child is None:
            return f"{label}: missing required element <{name}> ({hint})."
        if name == "whiteboard" and not (child.text or "").strip():
            return f"{label}: <{name}> must not be empty ({hint})."
        return None

    if rule_type == "descendant":
        found = _find_descendant(element, name)
        if found is None:
            return f"{label}: missing required element <{name}> ({hint})."
        return None

    return None


def _get_insertion_parent(container: ET.Element) -> ET.Element:
    """Return the element inside *container* where new descendants should go.

    If an ``<and>`` wrapper already exists, new elements are appended
    inside it to keep the structure consistent.  Otherwise they go
    directly into *container*.
    """
    and_el = container.find("and")
    if and_el is not None:
        return and_el
    return container


def _insert_default(
    element: ET.Element,
    rule: dict[str, Any],
    default: str | dict[str, str],
) -> None:
    """Insert *default* into *element* according to *rule* type."""
    rule_type = rule["type"]
    name = rule["name"]

    if rule_type == "attribute":
        element.set(name, str(default))

    elif rule_type == "child":
        if isinstance(default, dict):
            ET.SubElement(element, name, default)
        else:
            child = ET.SubElement(element, name)
            child.text = str(default)

    elif rule_type == "descendant":
        parent = _get_insertion_parent(element)
        if isinstance(default, dict):
            ET.SubElement(parent, name, default)
        else:
            child = ET.SubElement(parent, name)
            child.text = str(default)


def _maybe_infer_distro_family(
    distro_req: ET.Element,
    label: str,
    auto_filled: list[str],
) -> None:
    """If ``distro_family`` is absent but ``distro_name`` is present,
    infer the family and inject it into the tree."""
    if _find_descendant(distro_req, "distro_family") is not None:
        return

    distro_name_el = _find_descendant(distro_req, "distro_name")
    if distro_name_el is None:
        return

    distro_name_value = distro_name_el.get("value", "")
    if not distro_name_value:
        return

    family = _infer_distro_family(distro_name_value)
    if family is None:
        return

    parent = _get_insertion_parent(distro_req)
    ET.SubElement(parent, "distro_family", {"op": "=", "value": family})
    auto_filled.append(
        f"{label}: auto-inferred distro_family='{family}' from distro_name='{distro_name_value}'"
    )


def _apply_defaults_to_element(
    element: ET.Element,
    scope: str,
    label: str,
    auto_filled: list[str],
    still_missing: list[str],
) -> None:
    """For every :data:`MANDATORY_FIELDS` rule matching *scope*, check
    whether the field is already present on *element*.  If not:

    * **has default** -> inject the default and record in *auto_filled*.
    * **no default**  -> record the warning in *still_missing*.
    """
    rules = [r for r in MANDATORY_FIELDS if r["scope"] == scope]

    for rule in rules:
        err = _check_field(rule, element, label)
        if err is None:
            continue

        default = rule.get("default")
        if default is not None:
            _insert_default(element, rule, default)
            auto_filled.append(f"{label}: auto-filled '{rule['name']}' -> {default}")
        else:
            still_missing.append(err)


def validate_and_autofill_job_xml(
    job_xml: str,
) -> tuple[list[str], str, list[str], list[str]]:
    """Validate a Beaker job XML and auto-fill missing fields in one pass.

    Performs structural validation first (invalid XML, missing
    ``<recipeSet>``/``<recipe>``/``<task>``, etc.).  If the XML is
    structurally valid, applies sensible defaults for missing mandatory
    fields and infers values where possible (e.g. ``distro_family`` from
    ``distro_name``).

    Returns:
        ``(structural_errors, filled_xml, auto_filled, still_missing)``

        * *structural_errors* -- problems that must be fixed before
          submission.  If non-empty the remaining values are
          empty / unchanged.
        * *filled_xml* -- the XML string with defaults injected.
        * *auto_filled*  -- human-readable list of what was auto-filled.
        * *still_missing* -- human-readable list of fields that still
          need user input.
    """
    try:
        root = ET.fromstring(job_xml)
    except ET.ParseError as exc:
        return [f"Invalid XML: {exc}"], job_xml, [], []

    if root.tag != "job":
        return [f"Root element must be <job>, got <{root.tag}>."], job_xml, [], []

    errors: list[str] = []
    auto_filled: list[str] = []
    still_missing: list[str] = []

    recipe_sets = root.findall("recipeSet")
    if not recipe_sets:
        errors.append("Missing <recipeSet>: a <job> must contain at least one <recipeSet>.")
        return errors, job_xml, [], []

    _apply_defaults_to_element(root, "job", "<job>", auto_filled, still_missing)

    for rs_idx, rs in enumerate(recipe_sets, start=1):
        rs_label = f"recipeSet #{rs_idx}"
        _apply_defaults_to_element(rs, "recipeSet", rs_label, auto_filled, still_missing)

        recipes = rs.findall("recipe")
        if not recipes:
            errors.append(f"{rs_label}: must contain at least one <recipe>.")
            continue

        for r_idx, recipe in enumerate(recipes, start=1):
            r_label = f"{rs_label}, recipe #{r_idx}"
            _apply_defaults_to_element(recipe, "recipe", r_label, auto_filled, still_missing)

            distro_req = recipe.find("distroRequires")
            if distro_req is None:
                errors.append(
                    f"{r_label}: missing <distroRequires>. Specify the distro to install."
                )
            else:
                _maybe_infer_distro_family(distro_req, r_label, auto_filled)
                _apply_defaults_to_element(
                    distro_req,
                    "distroRequires",
                    f"{r_label}, <distroRequires>",
                    auto_filled,
                    still_missing,
                )

            host_req = recipe.find("hostRequires")
            if host_req is None:
                errors.append(
                    f"{r_label}: missing <hostRequires>. "
                    "Include <hostRequires> with at least a <hostname> element."
                )
            else:
                _apply_defaults_to_element(
                    host_req,
                    "hostRequires",
                    f"{r_label}, <hostRequires>",
                    auto_filled,
                    still_missing,
                )

            tasks = recipe.findall("task")
            if not tasks:
                errors.append(
                    f"{r_label}: must contain at least one <task>. "
                    'Example: <task name="/distribution/reservesys" '
                    'role="STANDALONE"/>.'
                )
            else:
                for t_idx, task in enumerate(tasks, start=1):
                    t_label = f"{r_label}, task #{t_idx}"
                    _apply_defaults_to_element(task, "task", t_label, auto_filled, still_missing)

    if errors:
        return errors, job_xml, [], []

    ET.indent(root, space="  ")
    filled_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return [], filled_xml, auto_filled, still_missing
