"""One-command end-to-end demo: register v1/v2/v3, diff, print migration plans.

Runs fully offline on the fictional Helios Home place_order contracts.
Each stage asserts what it expects, so the demo doubles as a smoke test.
"""

from __future__ import annotations

import json
import os

from checker import check_versions, report_to_json
from migrate import migration_plan
from registry import ContractRegistry

TOOL = "helios.place_order"


def _here(*parts: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def main() -> None:
    reg = ContractRegistry(_here("contracts"))
    reg.seed_helios()
    print(f"registered: {reg.list_versions(TOOL)}")

    # v1 -> v2: BREAKING (rename + tightened bound + new required field)
    r12 = check_versions(reg, TOOL, "v1", "v2")
    assert r12["verdict"] == "BREAKING", r12["verdict"]
    plan12 = migration_plan(r12)
    print(f"\n== {TOOL}: v1 -> v2 = {r12['verdict']} "
          f"(severity {r12['severity']}, {r12['breaking_count']} breaking) ==")
    for line in plan12["changelog"]:
        print(f"  {line}")
    print("\n-- migration notes --")
    for note in plan12["migration_notes"]:
        print(f"  [{note['action']}] {note['path']}: {note['note']}")

    # v2 -> v3: COMPATIBLE (optional adds, widenings, defaults)
    r23 = check_versions(reg, TOOL, "v2", "v3")
    assert r23["verdict"] == "COMPATIBLE", r23["verdict"]
    plan23 = migration_plan(r23)
    print(f"\n== {TOOL}: v2 -> v3 = {r23['verdict']} "
          f"(severity {r23['severity']}) ==")
    for line in plan23["changelog"]:
        print(f"  {line}")
    assert plan23["actions_required"] == 0

    # machine-readable plan for the breaking hop
    print("\n-- machine-readable migration plan (v1 -> v2, excerpt) --")
    excerpt = {k: plan12[k] for k in
               ("tool", "from_version", "to_version", "verdict",
                "severity", "actions_required")}
    excerpt["migration_notes"] = plan12["migration_notes"]
    print(json.dumps(excerpt, indent=2, sort_keys=True))
    print("\ndemo OK: v1->v2 breaking as expected, v2->v3 compatible as expected")


if __name__ == "__main__":
    main()
