"""Rename detection: pairs remove+add into one BREAKING rename finding."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from diff import diff_schemas  # noqa: E402


def breaking(findings):
    return [f for f in findings if f.kind == "BREAKING"]


class TestRenameDetection(unittest.TestCase):
    def test_rename_detected_as_single_breaking_finding(self):
        old = obj({"customer_id": {"type": "string", "minLength": 4}},
                  required=["customer_id"])
        new = obj({"customerId": {"type": "string", "minLength": 4}},
                  required=["customerId"])
        f = diff_schemas(old, new)
        b = breaking(f)
        # exactly ONE finding: the rename (not a remove + an add)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "renamed_property")
        self.assertEqual(b[0].path, "$.properties.customerId")
        self.assertIn("customer_id", b[0].message)
        self.assertIn("customerId", b[0].message)

    def test_rename_requires_shape_similarity(self):
        # removed optional free-text string + added required enum string:
        # different shapes -> NOT a rename -> remove (non-breaking) +
        # new required (breaking).
        old = obj({"notes": {"type": "string", "maxLength": 200}})
        new = obj({"priority": {"type": "string",
                                "enum": ["standard", "high"]}},
                  required=["priority"])
        f = diff_schemas(old, new)
        cats = sorted(x.category for x in f)
        self.assertNotIn("renamed_property", cats)
        b = breaking(f)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "new_required_no_default")
        self.assertEqual(b[0].path, "$.properties.priority")

    def test_rename_evidence_carries_old_and_new(self):
        old = obj({"product_id": {"type": "string",
                                  "pattern": "^HH-[0-9]{4}$"}},
                  required=["product_id"])
        new = obj({"sku": {"type": "string", "pattern": "^HH-[0-9]{4}$"}},
                  required=["sku"])
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].old["old_name"], "product_id")
        self.assertEqual(b[0].new["new_name"], "sku")

    def test_identical_shape_swap_pairs_as_rename(self):
        # Documented heuristic: a same-shape single swap pairs as a rename
        # even with dissimilar names (one BREAKING rename, not remove+add).
        old = obj({"a": {"type": "string"}}, required=["a"])
        new = obj({"b": {"type": "string"}}, required=["b"])
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "renamed_property")

    def test_rename_plus_tightening_reports_both(self):
        # A rename whose own contract also tightened must surface BOTH
        # findings: the rename AND the inner bound change.
        old = obj({"product_id": {"type": "string", "minLength": 8}},
                  required=["product_id"])
        new = obj({"sku": {"type": "string", "minLength": 10}},
                  required=["sku"])
        f = diff_schemas(old, new)
        cats = sorted(x.category for x in breaking(f))
        self.assertEqual(cats, ["bound_tightened", "renamed_property"])
        inner = [x for x in breaking(f)
                 if x.category == "bound_tightened"][0]
        self.assertEqual(inner.path, "$.properties.sku")

    def test_rename_of_optional_property_still_breaking(self):
        old = obj({"nick": {"type": "string"}})
        new = obj({"nickname": {"type": "string"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "renamed_property")

    def test_multiple_renames_pair_greedily(self):
        old = obj({"first_name": {"type": "string", "minLength": 1},
                   "last_name": {"type": "string", "minLength": 1}})
        new = obj({"firstName": {"type": "string", "minLength": 1},
                   "lastName": {"type": "string", "minLength": 1}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 2)
        paths = sorted(x.path for x in b)
        self.assertEqual(paths, ["$.properties.firstName",
                                 "$.properties.lastName"])

    def test_rename_beats_plain_remove_add_count(self):
        # Sanity: without pairing we would see remove+add; with pairing,
        # the finding count collapses to the pair count.
        old = obj({"user_id": {"type": "integer", "minimum": 1}},
                  required=["user_id"])
        new = obj({"userId": {"type": "integer", "minimum": 1}},
                  required=["userId"])
        f = diff_schemas(old, new)
        self.assertEqual(len(f), 1)


if __name__ == "__main__":
    unittest.main()
