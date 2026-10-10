"""Migration plans: human changelog + machine-readable upgrade guide.

Given a checker report, migration_plan() produces:
  - "changelog": one line per finding, newest-first readable
  - "migration_notes": per-path actions for client teams:
      "client_must_add"    old clients must start sending a new field
      "client_must_update" old clients must change what they send
      "no_action"          safe; nothing to do
  - the full findings list, so the plan is self-contained.

Stdlib only. No network. Deterministic.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Which client action each finding category implies.
_ACTIONS: Dict[str, str] = {
    # must change what they send
    "removed_required_property": "client_must_update",
    "renamed_property": "client_must_update",
    "type_narrowed": "client_must_update",
    "type_changed": "client_must_update",
    "enum_value_removed": "client_must_update",
    "items_narrowed": "client_must_update",
    "items_changed": "client_must_update",
    "required_tightened": "client_must_update",
    "pattern_added_or_changed": "client_must_update",
    "bound_tightened": "client_must_update",
    "additional_properties_tightened": "client_must_update",
    # must send something new
    "new_required_no_default": "client_must_add",
    # safe
    "new_required_with_default": "no_action",
    "new_optional_property": "no_action",
    "removed_optional_property": "no_action",
    "required_loosened": "no_action",
    "bound_loosened": "no_action",
    "pattern_removed": "no_action",
    "additional_properties_loosened": "no_action",
    "type_widened": "no_action",
    "enum_value_added": "no_action",
    "enum_reordered": "no_action",
}

_NOTE_TEMPLATES: Dict[str, str] = {
    "removed_required_property": "stop sending '{name}'; it no longer exists",
    "renamed_property": "rename '{name}' in every call (see evidence for old -> new)",
    "type_narrowed": "'{name}' accepts a narrower type now; coerce values before sending",
    "type_changed": "'{name}' changed type; update the value you send",
    "enum_value_removed": "'{name}' lost allowed value(s); switch to a surviving value",
    "items_narrowed": "items of '{name}' accept a narrower type now",
    "items_changed": "items of '{name}' changed; update list elements",
    "required_tightened": "'{name}' is now required; always send it",
    "pattern_added_or_changed": "'{name}' has a new/changed pattern; validate values against it",
    "bound_tightened": "'{name}' has a tighter bound; keep values inside the new range",
    "additional_properties_tightened": "stop sending extra fields not in the contract",
    "new_required_no_default": "clients must add '{name}' to calls",
    "new_required_with_default": "safe: '{name}' has a server-side default; no action",
    "new_optional_property": "safe: '{name}' is optional; no action",
    "removed_optional_property": "safe if you never sent '{name}'; no action",
    "required_loosened": "safe: '{name}' is now optional; no action",
    "bound_loosened": "safe: '{name}' accepts a wider range; no action",
    "pattern_removed": "safe: '{name}' pattern removed; no action",
    "additional_properties_loosened": "safe: extra fields now allowed; no action",
    "type_widened": "safe: '{name}' accepts more types; no action",
    "enum_value_added": "safe: '{name}' accepts new value(s); no action",
    "enum_reordered": "safe: enum order only; no action",
}


def _prop_name(path: str) -> str:
    """'$.properties.priority' -> 'priority'; '$' -> '(contract root)'."""
    if ".properties." in path:
        return path.split(".properties.")[-1].split(".")[0]
    return "(contract root)"


def migration_plan(report: Dict[str, Any]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = report["findings"]
    changelog: List[str] = []
    notes: List[Dict[str, Any]] = []

    for f in findings:
        tag = {"BREAKING": "BREAKING", "ADDITIVE": "additive",
               "NON-BREAKING": "compatible"}[f["kind"]]
        changelog.append(f"[{tag}] {f['path']}: {f['message']}")
        action = _ACTIONS.get(f["category"], "no_action")
        template = _NOTE_TEMPLATES.get(
            f["category"], "safe: no action required")
        notes.append({
            "path": f["path"],
            "category": f["category"],
            "kind": f["kind"],
            "action": action,
            "note": template.format(name=_prop_name(f["path"])),
        })

    breaking_notes = [n for n in notes if n["kind"] == "BREAKING"]
    return {
        "tool": report["tool"],
        "from_version": report["from_version"],
        "to_version": report["to_version"],
        "verdict": report["verdict"],
        "severity": report["severity"],
        "breaking_count": report["breaking_count"],
        "changelog": changelog,
        "migration_notes": notes,
        "actions_required": len(breaking_notes),
        "findings": findings,
    }
