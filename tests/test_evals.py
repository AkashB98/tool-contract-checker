"""The committed golden eval report must match a fresh run byte-for-byte."""

import json
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
EVALS = os.path.join(REPO_ROOT, "evals")
RUN_EVALS = os.path.join(EVALS, "run_evals.py")
REPORT = os.path.join(EVALS, "eval_report.json")


class TestEvals(unittest.TestCase):
    def test_golden_cases_file_valid(self):
        with open(os.path.join(EVALS, "golden_cases.json")) as fh:
            data = json.load(fh)
        self.assertGreaterEqual(len(data["cases"]), 20)
        for c in data["cases"]:
            self.assertIn(c["expected_verdict"], ("BREAKING", "COMPATIBLE"))
            self.assertIn("from", c)
            self.assertIn("to", c)

    def test_eval_report_matches_fresh_run(self):
        with open(REPORT, "rb") as fh:
            committed = fh.read()
        p = subprocess.run([sys.executable, RUN_EVALS],
                           capture_output=True, text=True,
                           cwd=REPO_ROOT, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(REPORT, "rb") as fh:
            fresh = fh.read()
        self.assertEqual(committed, fresh)
        report = json.loads(fresh)
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["passed"], report["case_count"])


if __name__ == "__main__":
    unittest.main()
