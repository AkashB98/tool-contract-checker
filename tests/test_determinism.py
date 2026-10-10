"""Determinism: same inputs -> byte-identical outputs, every run."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from checker import check, report_to_json  # noqa: E402
from migrate import migration_plan  # noqa: E402


def sample_pair():
    old = obj({"a": {"type": "string", "minLength": 3},
               "b": {"type": "integer", "minimum": 1},
               "c": {"type": "string", "enum": ["x", "y"]}},
              required=["a", "b"])
    new = obj({"a": {"type": "string", "minLength": 5},
               "b": {"type": "number"},
               "d": {"type": "boolean"}},
              required=["a", "b", "d"])
    return old, new


class TestDeterminism(unittest.TestCase):
    def test_check_bytes_identical_across_runs(self):
        old, new = sample_pair()
        first = report_to_json(check(old, new, tool="t",
                                     from_version="v1", to_version="v2"))
        second = report_to_json(check(old, new, tool="t",
                                      from_version="v1", to_version="v2"))
        self.assertEqual(first, second)

    def test_migration_plan_bytes_identical(self):
        old, new = sample_pair()
        first = json.dumps(migration_plan(check(old, new)), sort_keys=True)
        second = json.dumps(migration_plan(check(old, new)), sort_keys=True)
        self.assertEqual(first, second)

    def test_demo_stdout_identical_across_runs(self):
        import demo
        outs = []
        for _ in range(2):
            buf = io.StringIO()
            with redirect_stdout(buf):
                demo.main()
            outs.append(buf.getvalue())
        self.assertEqual(outs[0], outs[1])
        self.assertIn("demo OK", outs[0])

    def test_many_shuffled_inputs_stable(self):
        # Property diff iterates sets; confirm output order never depends
        # on set iteration by diffing a wide schema repeatedly.
        props = {f"p{i:02d}": {"type": "string"} for i in range(30)}
        old = obj(props, required=[f"p{i:02d}" for i in range(15)])
        new_props = dict(props)
        del new_props["p00"]
        new_props["p30"] = {"type": "string"}
        new = obj(new_props, required=[f"p{i:02d}" for i in range(1, 16)]
                  + ["p30"])
        outs = {report_to_json(check(old, new)) for _ in range(5)}
        self.assertEqual(len(outs), 1)


if __name__ == "__main__":
    unittest.main()
