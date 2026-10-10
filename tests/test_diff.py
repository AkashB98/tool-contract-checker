"""Diff classification: every breaking class fires, boundaries hold."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from diff import (  # noqa: E402
    ADDITIVE,
    BREAKING,
    NON_BREAKING,
    diff_schemas,
)


def kinds(findings):
    return [(f.kind, f.category, f.path) for f in findings]


def breaking(findings):
    return [f for f in findings if f.kind == BREAKING]


class TestRemovedRequiredProperty(unittest.TestCase):
    def test_removed_required_is_breaking(self):
        old = obj({"product_id": {"type": "string"},
                   "notes": {"type": "string"}},
                  required=["product_id"])
        new = obj({"notes": {"type": "string"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "removed_required_property")
        self.assertEqual(b[0].path, "$.properties.product_id")

    def test_removed_optional_is_not_breaking(self):
        old = obj({"product_id": {"type": "string"},
                   "notes": {"type": "string"}},
                  required=["product_id"])
        new = obj({"product_id": {"type": "string"}},
                  required=["product_id"])
        b = breaking(diff_schemas(old, new))
        self.assertEqual(b, [])
        cats = [f.category for f in diff_schemas(old, new)]
        self.assertIn("removed_optional_property", cats)


class TestNewRequiredProperty(unittest.TestCase):
    def test_new_required_no_default_is_breaking(self):
        old = obj({"sku": {"type": "string"}}, required=["sku"])
        new = obj({"sku": {"type": "string"},
                   "priority": {"type": "string"}},
                  required=["sku", "priority"])
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "new_required_no_default")
        self.assertEqual(b[0].path, "$.properties.priority")
        self.assertIn("must add", b[0].message)

    def test_new_required_with_default_is_additive(self):
        old = obj({"sku": {"type": "string"}}, required=["sku"])
        new = obj({"sku": {"type": "string"},
                   "priority": {"type": "string", "default": "standard"}},
                  required=["sku", "priority"])
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].kind, ADDITIVE)
        self.assertEqual(f[0].category, "new_required_with_default")

    def test_new_optional_property_is_additive(self):
        old = obj({"sku": {"type": "string"}}, required=["sku"])
        new = obj({"sku": {"type": "string"},
                   "gift_wrap": {"type": "boolean"}}, required=["sku"])
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual([(x.kind, x.category) for x in f],
                         [(ADDITIVE, "new_optional_property")])

    def test_optional_to_required_is_breaking(self):
        old = obj({"sku": {"type": "string"}, "notes": {"type": "string"}},
                  required=["sku"])
        new = obj({"sku": {"type": "string"}, "notes": {"type": "string"}},
                  required=["sku", "notes"])
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "required_tightened")
        self.assertEqual(b[0].path, "$.properties.notes")

    def test_required_to_optional_is_compatible(self):
        old = obj({"sku": {"type": "string"}, "notes": {"type": "string"}},
                  required=["sku", "notes"])
        new = obj({"sku": {"type": "string"}, "notes": {"type": "string"}},
                  required=["sku"])
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "required_loosened")


class TestTypeChanges(unittest.TestCase):
    def test_type_narrowed_is_breaking(self):
        old = obj({"rating": {"type": "number"}})
        new = obj({"rating": {"type": "integer"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "type_narrowed")

    def test_type_changed_disjoint_is_breaking(self):
        old = obj({"sku": {"type": "string"}})
        new = obj({"sku": {"type": "boolean"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "type_changed")

    def test_type_widened_is_additive(self):
        old = obj({"qty": {"type": "integer"}})
        new = obj({"qty": {"type": ["integer", "number"]}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "type_widened")

    def test_identical_type_no_finding(self):
        old = obj({"sku": {"type": "string"}})
        new = obj({"sku": {"type": "string"}})
        self.assertEqual(diff_schemas(old, new), [])


class TestEnumChanges(unittest.TestCase):
    def test_enum_value_removed_is_breaking(self):
        old = obj({"speed": {"type": "string",
                             "enum": ["standard", "express"]}})
        new = obj({"speed": {"type": "string", "enum": ["standard"]}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "enum_value_removed")
        self.assertIn("express", b[0].message)

    def test_enum_value_added_is_additive(self):
        old = obj({"speed": {"type": "string",
                             "enum": ["standard", "express"]}})
        new = obj({"speed": {"type": "string",
                             "enum": ["standard", "express", "overnight"]}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "enum_value_added")


class TestBounds(unittest.TestCase):
    def test_minlength_tightened_is_breaking(self):
        old = obj({"pid": {"type": "string", "minLength": 8}})
        new = obj({"pid": {"type": "string", "minLength": 10}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "bound_tightened")

    def test_minlength_same_value_no_finding(self):
        old = obj({"pid": {"type": "string", "minLength": 8}})
        new = obj({"pid": {"type": "string", "minLength": 8}})
        self.assertEqual(diff_schemas(old, new), [])

    def test_minlength_loosened_is_compatible(self):
        old = obj({"pid": {"type": "string", "minLength": 10}})
        new = obj({"pid": {"type": "string", "minLength": 8}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "bound_loosened")

    def test_minimum_raised_is_breaking(self):
        old = obj({"qty": {"type": "integer", "minimum": 1}})
        new = obj({"qty": {"type": "integer", "minimum": 2}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "bound_tightened")

    def test_minimum_lowered_is_compatible(self):
        old = obj({"qty": {"type": "integer", "minimum": 2}})
        new = obj({"qty": {"type": "integer", "minimum": 1}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "bound_loosened")

    def test_maximum_lowered_is_breaking(self):
        old = obj({"qty": {"type": "integer", "maximum": 99}})
        new = obj({"qty": {"type": "integer", "maximum": 50}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "bound_tightened")

    def test_maximum_raised_is_compatible(self):
        old = obj({"qty": {"type": "integer", "maximum": 99}})
        new = obj({"qty": {"type": "integer", "maximum": 200}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "bound_loosened")

    def test_maxlength_tightened_is_breaking(self):
        old = obj({"notes": {"type": "string", "maxLength": 200}})
        new = obj({"notes": {"type": "string", "maxLength": 100}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "bound_tightened")

    def test_maxlength_widened_is_compatible(self):
        old = obj({"notes": {"type": "string", "maxLength": 200}})
        new = obj({"notes": {"type": "string", "maxLength": 500}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "bound_loosened")

    def test_bound_added_is_breaking(self):
        old = obj({"qty": {"type": "integer"}})
        new = obj({"qty": {"type": "integer", "minimum": 1}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "bound_tightened")

    def test_bound_removed_is_compatible(self):
        old = obj({"qty": {"type": "integer", "minimum": 1}})
        new = obj({"qty": {"type": "integer"}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "bound_loosened")


class TestPattern(unittest.TestCase):
    def test_pattern_changed_is_breaking(self):
        old = obj({"zip": {"type": "string", "pattern": "^[0-9]{5}$"}})
        new = obj({"zip": {"type": "string",
                           "pattern": "^[0-9]{5}(-[0-9]{4})?$"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "pattern_added_or_changed")

    def test_pattern_added_is_breaking(self):
        old = obj({"zip": {"type": "string"}})
        new = obj({"zip": {"type": "string", "pattern": "^[0-9]{5}$"}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "pattern_added_or_changed")

    def test_pattern_removed_is_compatible(self):
        old = obj({"zip": {"type": "string", "pattern": "^[0-9]{5}$"}})
        new = obj({"zip": {"type": "string"}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "pattern_removed")


class TestAdditionalProperties(unittest.TestCase):
    def test_true_to_false_is_breaking(self):
        old = obj({"a": {"type": "string"}}, additionalProperties=True)
        new = obj({"a": {"type": "string"}}, additionalProperties=False)
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "additional_properties_tightened")
        self.assertEqual(b[0].path, "$")

    def test_absent_to_false_is_breaking(self):
        # JSON Schema default is true, so absent -> false is a tightening.
        old = obj({"a": {"type": "string"}})
        new = obj({"a": {"type": "string"}}, additionalProperties=False)
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)

    def test_false_to_true_is_compatible(self):
        old = obj({"a": {"type": "string"}}, additionalProperties=False)
        new = obj({"a": {"type": "string"}}, additionalProperties=True)
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])
        self.assertEqual(f[0].category, "additional_properties_loosened")


class TestItems(unittest.TestCase):
    def test_items_narrowed_is_breaking(self):
        old = obj({"tags": {"type": "array",
                            "items": {"type": "string"}}})
        new = obj({"tags": {"type": "array",
                            "items": {"type": "integer"}}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].category, "items_narrowed")
        self.assertEqual(b[0].path, "$.properties.tags")

    def test_items_widened_is_compatible(self):
        old = obj({"tags": {"type": "array",
                            "items": {"type": "integer"}}})
        new = obj({"tags": {"type": "array",
                            "items": {"type": ["integer", "number"]}}})
        f = diff_schemas(old, new)
        self.assertEqual(breaking(f), [])


class TestFalsePositiveTraps(unittest.TestCase):
    """Changes that look scary but are safe must not be breaking."""

    def test_description_only_change_is_silent(self):
        old = obj({"sku": {"type": "string", "description": "old text"}})
        new = obj({"sku": {"type": "string", "description": "new text"}})
        self.assertEqual(diff_schemas(old, new), [])

    def test_identical_schemas_zero_findings(self):
        schema = obj({"sku": {"type": "string", "minLength": 8},
                      "qty": {"type": "integer", "minimum": 1}},
                     required=["sku"])
        self.assertEqual(diff_schemas(schema, schema), [])

    def test_nested_property_path(self):
        old = obj({"addr": {"type": "object",
                            "properties": {"zip": {"type": "string"}}}})
        new = obj({"addr": {"type": "object",
                            "properties": {"zip": {"type": "integer"}}}})
        b = breaking(diff_schemas(old, new))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].path,
                         "$.properties.addr.properties.zip")


class TestDeterminismOfDiff(unittest.TestCase):
    def test_findings_sorted_stable(self):
        old = obj({"b": {"type": "string"}, "a": {"type": "string"}},
                  required=["a", "b"])
        new = obj({})
        first = [f.to_dict() for f in diff_schemas(old, new)]
        second = [f.to_dict() for f in diff_schemas(old, new)]
        self.assertEqual(first, second)
        paths = [f["path"] for f in first]
        self.assertEqual(paths, sorted(paths))


if __name__ == "__main__":
    unittest.main()
