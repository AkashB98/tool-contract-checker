#!/usr/bin/env python3
"""Golden evals: 27 hand-verified contract-diff pairs.

Each breaking case expects verdict BREAKING with the exact set of breaking
finding paths (and categories); each compatible case expects verdict
COMPATIBLE with zero breaking findings.

The whole suite runs twice in-process; the two reports must be identical
(determinism). The report is written to evals/eval_report.json with stable
bytes (sorted keys, no timestamps) so md5 is identical across runs.

Stdlib only. No network.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from checker import check  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_cases():
    with open(os.path.join(_HERE, "golden_cases.json"), encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def run_once(cases):
    results = []
    for case in cases:
        report = check(case["from"], case["to"], tool="helios.place_order",
                       from_version="eval-from", to_version="eval-to")
        got_paths = sorted(f["path"] for f in report["findings"]
                           if f["kind"] == "BREAKING")
        got_cats = sorted(f["category"] for f in report["findings"]
                          if f["kind"] == "BREAKING")
        verdict_ok = report["verdict"] == case["expected_verdict"]
        paths_ok = got_paths == sorted(case["expected_breaking_paths"])
        cats_ok = got_cats == sorted(case["expected_breaking_categories"])
        passed = verdict_ok and paths_ok and cats_ok
        results.append({
            "id": case["id"],
            "expected_verdict": case["expected_verdict"],
            "got_verdict": report["verdict"],
            "expected_breaking_paths": sorted(case["expected_breaking_paths"]),
            "got_breaking_paths": got_paths,
            "expected_breaking_categories": sorted(
                case["expected_breaking_categories"]),
            "got_breaking_categories": got_cats,
            "severity": report["severity"],
            "passed": passed,
        })
    return results


def main() -> int:
    cases = load_cases()
    first = run_once(cases)
    second = run_once(cases)
    deterministic = (json.dumps(first, sort_keys=True)
                     == json.dumps(second, sort_keys=True))

    passed = sum(1 for r in first if r["passed"])
    report = {
        "suite": "tool-contract-checker golden evals",
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "deterministic": deterministic,
        "all_passed": passed == len(cases) and deterministic,
        "cases": first,
    }
    out_path = os.path.join(_HERE, "eval_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True, indent=2) + "\n")

    print(f"{passed}/{len(cases)} golden cases passed; "
          f"deterministic={deterministic}")
    for r in first:
        if not r["passed"]:
            print(f"  FAIL {r['id']}: expected {r['expected_verdict']} "
                  f"{r['expected_breaking_paths']}, got {r['got_verdict']} "
                  f"{r['got_breaking_paths']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
