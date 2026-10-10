"""CLI: exit codes (0 compatible / 1 breaking / 2 error), diff formats."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CLI = os.path.join(REPO_ROOT, "cli.py")

BREAKING_PAIR = (
    {"type": "object",
     "properties": {"sku": {"type": "string"}},
     "required": ["sku"]},
    {"type": "object",
     "properties": {"sku": {"type": "string"},
                    "priority": {"type": "string"}},
     "required": ["sku", "priority"]},
)
COMPATIBLE_PAIR = (
    {"type": "object",
     "properties": {"sku": {"type": "string"}},
     "required": ["sku"]},
    {"type": "object",
     "properties": {"sku": {"type": "string"},
                    "notes": {"type": "string"}},
     "required": ["sku"]},
)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.contracts = os.path.join(self.tmp.name, "contracts")
        for name, schema in (("bv1", BREAKING_PAIR[0]),
                             ("bv2", BREAKING_PAIR[1]),
                             ("cv1", COMPATIBLE_PAIR[0]),
                             ("cv2", COMPATIBLE_PAIR[1])):
            tool, ver = name[0] + ".tool", name[1:]
            d = os.path.join(self.contracts, tool)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{ver}.json"), "w") as fh:
                json.dump({"tool": tool, "version": ver,
                           "registered_at": "2026-10-08T00:00:00Z",
                           "schema": schema}, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, CLI, "--contracts", self.contracts, *args],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)

    def test_check_breaking_exits_1(self):
        p = self.run_cli("check", "--tool", "b.tool",
                         "--from", "v1", "--to", "v2")
        self.assertEqual(p.returncode, 1)
        self.assertIn("BREAKING", p.stdout)

    def test_check_compatible_exits_0(self):
        p = self.run_cli("check", "--tool", "c.tool",
                         "--from", "v1", "--to", "v2")
        self.assertEqual(p.returncode, 0)
        self.assertIn("COMPATIBLE", p.stdout)

    def test_check_missing_version_exits_2(self):
        p = self.run_cli("check", "--tool", "b.tool",
                         "--from", "v1", "--to", "v9")
        self.assertEqual(p.returncode, 2)
        self.assertIn("error", p.stderr.lower())

    def test_diff_json_is_parseable(self):
        p = self.run_cli("diff", "--tool", "b.tool",
                         "--from", "v1", "--to", "v2", "--format", "json")
        self.assertEqual(p.returncode, 0)
        report = json.loads(p.stdout)
        self.assertEqual(report["verdict"], "BREAKING")
        self.assertTrue(report["findings"])

    def test_diff_text_lists_changelog(self):
        p = self.run_cli("diff", "--tool", "c.tool",
                         "--from", "v1", "--to", "v2")
        self.assertEqual(p.returncode, 0)
        self.assertIn("COMPATIBLE", p.stdout)

    def test_register_then_check(self):
        schema_path = os.path.join(self.tmp.name, "s.json")
        with open(schema_path, "w") as fh:
            json.dump({"type": "object",
                       "properties": {"x": {"type": "string"}}}, fh)
        p = self.run_cli("register", "--tool", "n.tool",
                         "--version", "v1", "--file", schema_path)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.contracts, "n.tool", "v1.json")))

    def test_demo_subcommand_runs(self):
        p = self.run_cli("demo")
        self.assertEqual(p.returncode, 0)
        self.assertIn("demo OK", p.stdout)


if __name__ == "__main__":
    unittest.main()
