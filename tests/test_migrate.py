"""Migration plans: changelog lines, per-path actions, exactness."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from checker import check  # noqa: E402
from migrate import migration_plan  # noqa: E402


def plan_for(old, new, **kw):
    return migration_plan(check(old, new, tool="t.tool",
                                from_version="v1", to_version="v2", **kw))


class TestMigrationPlan(unittest.TestCase):
    def test_plan_echoes_verdict_and_severity(self):
        # Shapes differ on purpose so this is NOT rename-paired.
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"b": {"type": "integer"}}, required=["b"])
        p = plan_for(old, new)
        self.assertEqual(p["verdict"], "BREAKING")
        self.assertEqual(p["severity"], 20)
        self.assertEqual(p["tool"], "t.tool")
        self.assertEqual((p["from_version"], p["to_version"]), ("v1", "v2"))

    def test_changelog_one_line_per_finding(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"b": {"type": "string"}}, required=["b"])
        p = plan_for(old, new)
        self.assertEqual(len(p["changelog"]), len(p["findings"]))
        self.assertTrue(all(l.startswith(("[BREAKING]", "[additive]",
                                           "[compatible]"))
                            for l in p["changelog"]))

    def test_new_required_note_tells_clients_to_add(self):
        old = obj({"sku": {"type": "string"}}, required=["sku"])
        new = obj({"sku": {"type": "string"},
                   "priority": {"type": "string"}},
                  required=["sku", "priority"])
        p = plan_for(old, new)
        note = [n for n in p["migration_notes"]
                if n["path"] == "$.properties.priority"][0]
        self.assertEqual(note["action"], "client_must_add")
        self.assertIn("must add 'priority'", note["note"])

    def test_rename_note_tells_clients_to_rename(self):
        old = obj({"product_id": {"type": "string"}},
                  required=["product_id"])
        new = obj({"sku": {"type": "string"}}, required=["sku"])
        p = plan_for(old, new)
        note = p["migration_notes"][0]
        self.assertEqual(note["action"], "client_must_update")
        self.assertIn("rename", note["note"])

    def test_safe_changes_need_no_action(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"a": {"type": "string"}, "b": {"type": "boolean"}},
                  required=["a"])
        p = plan_for(old, new)
        self.assertEqual(p["verdict"], "COMPATIBLE")
        self.assertEqual(p["actions_required"], 0)
        self.assertTrue(all(n["action"] == "no_action"
                            for n in p["migration_notes"]))

    def test_actions_required_counts_breaking_only(self):
        old = obj({"a": {"type": "string"},
                   "speed": {"type": "string",
                             "enum": ["standard", "express"]}},
                  required=["a"])
        new = obj({"speed": {"type": "string",
                             "enum": ["standard", "express", "overnight"]}},
                  required=["speed"])
        # a removed (required->breaking) + speed now required (breaking) +
        # enum widened (additive)
        p = plan_for(old, new)
        self.assertEqual(p["actions_required"], p["breaking_count"])
        self.assertEqual(p["breaking_count"], 2)

    def test_plan_is_json_serializable(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({})
        p = plan_for(old, new)
        json.dumps(p, sort_keys=True)  # must not raise

    def test_plan_stable_across_runs(self):
        old = obj({"a": {"type": "string"}, "b": {"type": "integer"}},
                  required=["a"])
        new = obj({"c": {"type": "string"}}, required=["c"])
        first = json.dumps(plan_for(old, new), sort_keys=True)
        second = json.dumps(plan_for(old, new), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
