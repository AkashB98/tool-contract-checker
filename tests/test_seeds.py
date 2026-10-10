"""Seeded Helios contracts: v1->v2 breaking, v2->v3 compatible (end to end)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from checker import check_versions  # noqa: E402
from migrate import migration_plan  # noqa: E402
from registry import ContractRegistry  # noqa: E402

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
TOOL = "helios.place_order"


class TestSeededContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = ContractRegistry(os.path.join(REPO_ROOT, "contracts"))

    def test_v1_to_v2_is_breaking(self):
        r = check_versions(self.reg, TOOL, "v1", "v2")
        self.assertEqual(r["verdict"], "BREAKING")
        self.assertGreater(r["severity"], 0)

    def test_v1_to_v2_breaking_paths(self):
        r = check_versions(self.reg, TOOL, "v1", "v2")
        paths = {f["path"] for f in r["findings"]
                 if f["kind"] == "BREAKING"}
        self.assertEqual(paths, {
            "$.properties.priority",   # new required, no default
            "$.properties.quantity",   # minimum 1 -> 2
            "$.properties.sku",        # renamed from product_id
            "$.properties.zip",        # pattern changed
        })

    def test_v1_to_v2_rename_detected(self):
        r = check_versions(self.reg, TOOL, "v1", "v2")
        renames = [f for f in r["findings"]
                   if f["category"] == "renamed_property"]
        self.assertEqual(len(renames), 1)
        self.assertIn("product_id", renames[0]["message"])

    def test_v2_to_v3_is_compatible(self):
        r = check_versions(self.reg, TOOL, "v2", "v3")
        self.assertEqual(r["verdict"], "COMPATIBLE")
        self.assertEqual(r["severity"], 0)
        self.assertEqual(r["breaking_count"], 0)

    def test_v2_to_v3_has_additive_findings(self):
        r = check_versions(self.reg, TOOL, "v2", "v3")
        cats = {f["category"] for f in r["findings"]}
        self.assertIn("new_optional_property", cats)   # gift_wrap
        self.assertIn("enum_value_added", cats)        # same_day

    def test_v1_to_v3_is_breaking(self):
        r = check_versions(self.reg, TOOL, "v1", "v3")
        self.assertEqual(r["verdict"], "BREAKING")

    def test_migration_plan_notes_actionable(self):
        r = check_versions(self.reg, TOOL, "v1", "v2")
        p = migration_plan(r)
        actions = {n["path"]: n["action"] for n in p["migration_notes"]}
        self.assertEqual(actions["$.properties.priority"], "client_must_add")
        self.assertEqual(actions["$.properties.sku"], "client_must_update")
        self.assertGreater(p["actions_required"], 0)


if __name__ == "__main__":
    unittest.main()
