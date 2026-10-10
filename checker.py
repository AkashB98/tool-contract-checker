"""Verdict API: is the new contract version safe for old clients?

check(old_schema, new_schema) -> a JSON-serializable report with:
  verdict  "COMPATIBLE" (no breaking findings) or "BREAKING"
  severity a weighted score: higher = more dangerous change
  findings every classified change with path + before/after evidence

check_versions(registry, tool, from_version, to_version) does the same
lookup by name from a ContractRegistry.

Stdlib only. No network. Deterministic.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from diff import diff_schemas
from registry import ContractRegistry

# Severity weights per breaking change class. Roughly: "a client that
# worked yesterday breaks today" events score highest; subtler tightenings
# score lower. Non-breaking findings never add to the score.
SEVERITY_WEIGHTS: Dict[str, int] = {
    "removed_required_property": 10,
    "new_required_no_default": 10,
    "required_tightened": 9,
    "type_narrowed": 8,
    "type_changed": 8,
    "renamed_property": 8,
    "enum_value_removed": 6,
    "items_narrowed": 6,
    "items_changed": 6,
    "pattern_added_or_changed": 5,
    "bound_tightened": 4,
    "additional_properties_tightened": 4,
}

_EVIDENCE_LIMIT = 220


def _evidence(value: Any) -> str | None:
    """Compact, truncated before/after quote for a finding."""
    if value is None:
        return None
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(text) > _EVIDENCE_LIMIT:
        text = text[: _EVIDENCE_LIMIT - 1] + "…"
    return text


def check(old_schema: Dict[str, Any], new_schema: Dict[str, Any], *,
          tool: str = "?", from_version: str = "?",
          to_version: str = "?") -> Dict[str, Any]:
    findings = diff_schemas(old_schema, new_schema)
    breaking = [f for f in findings if f.kind == "BREAKING"]
    severity = sum(SEVERITY_WEIGHTS.get(f.category, 3) for f in breaking)
    verdict = "BREAKING" if breaking else "COMPATIBLE"
    return {
        "tool": tool,
        "from_version": from_version,
        "to_version": to_version,
        "verdict": verdict,
        "severity": severity,
        "breaking_count": len(breaking),
        "finding_count": len(findings),
        "findings": [
            {
                "kind": f.kind,
                "category": f.category,
                "path": f.path,
                "message": f.message,
                "evidence_before": _evidence(f.old),
                "evidence_after": _evidence(f.new),
            }
            for f in findings
        ],
    }


def check_versions(registry: ContractRegistry, tool: str,
                   from_version: str, to_version: str) -> Dict[str, Any]:
    """Check two registered contract versions by name."""
    old_schema = registry.lookup(tool, from_version)
    new_schema = registry.lookup(tool, to_version)
    return check(old_schema, new_schema, tool=tool,
                 from_version=from_version, to_version=to_version)


def report_to_json(report: Dict[str, Any]) -> str:
    """Canonical JSON rendering (stable bytes for determinism checks)."""
    return json.dumps(report, sort_keys=True, indent=2) + "\n"
