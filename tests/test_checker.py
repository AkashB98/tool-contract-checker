"""Checker: verdict, severity scoring, evidence quotes, JSON stability."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from checker import check, report_to_json  # noqa: E402


class TestVerdict(unittest.TestCase):
    def test_identical_schemas_compatible(self):
        s = obj({"a": {"type": "string"}}, required=["a"])
        r = check(s, s, tool="t", from_version="v1", to_version="v2")
        self.assertEqual(r["verdict"], "COMPATIBLE")
        self.assertEqual(r["severity"], 0)
        self.assertEqual(r["breaking_count"], 0)

    def test_breaking_change_verdict(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({}, )
        r = check(old, new)
        self.assertEqual(r["verdict"], "BREAKING")
        self.assertGreater(r["severity"], 0)
        self.assertEqual(r["breaking_count"], 1)

    def test_additive_only_is_compatible(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"a": {"type": "string"}, "b": {"type": "string"}},
                  required=["a"])
        r = check(old, new)
        self.assertEqual(r["verdict"], "COMPATIBLE")
        self.assertEqual(r["severity"], 0)
        self.assertEqual(r["finding_count"], 1)

    def test_severity_sums_weights(self):
        # removed required (10) + new required no default (10) = 20.
        # (Shapes differ on purpose so this is NOT rename-paired.)
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"b": {"type": "integer"}}, required=["b"])
        r = check(old, new)
        self.assertEqual(r["severity"], 20)
        self.assertEqual(r["breaking_count"], 2)

    def test_more_severe_change_scores_higher(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        removed = check(old, obj({}))
        loosened = check(
            obj({"n": {"type": "string", "maxLength": 10}}),
            obj({"n": {"type": "string", "maxLength": 50}}))
        self.assertGreater(removed["severity"], loosened["severity"])
        self.assertEqual(loosened["severity"], 0)


class TestEvidence(unittest.TestCase):
    def test_findings_carry_before_after_quotes(self):
        old = obj({"speed": {"type": "string",
                             "enum": ["standard", "express"]}})
        new = obj({"speed": {"type": "string", "enum": ["standard"]}})
        r = check(old, new)
        f = r["findings"][0]
        self.assertIn("express", f["evidence_before"])
        self.assertNotIn("express", f["evidence_after"])
        self.assertTrue(f["path"].startswith("$."))
        self.assertIn(f["kind"], ("BREAKING", "NON-BREAKING", "ADDITIVE"))

    def test_report_is_json_serializable(self):
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"b": {"type": "integer"}}, required=["b"])
        r = check(old, new, tool="t", from_version="v1", to_version="v2")
        text = report_to_json(r)
        self.assertEqual(json.loads(text)["verdict"], "BREAKING")

    def test_report_carries_versions(self):
        s = obj({"a": {"type": "string"}})
        r = check(s, s, tool="my.tool", from_version="v3", to_version="v4")
        self.assertEqual((r["tool"], r["from_version"], r["to_version"]),
                         ("my.tool", "v3", "v4"))


if __name__ == "__main__":
    unittest.main()
