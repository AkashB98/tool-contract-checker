"""Registry: register/lookup round-trip, listing, seed idempotency."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from registry import ContractNotFound, ContractRegistry  # noqa: E402

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = ContractRegistry(os.path.join(self.tmp.name, "contracts"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_lookup_round_trip(self):
        schema = {"type": "object",
                  "properties": {"a": {"type": "string"}}}
        self.reg.register("demo.tool", "v1", schema)
        self.assertEqual(self.reg.lookup("demo.tool", "v1"), schema)

    def test_lookup_missing_raises(self):
        with self.assertRaises(ContractNotFound):
            self.reg.lookup("nope.tool", "v9")

    def test_list_versions_sorted(self):
        s = {"type": "object"}
        self.reg.register("demo.tool", "v2", s)
        self.reg.register("demo.tool", "v1", s)
        self.assertEqual(self.reg.list_versions("demo.tool"), ["v1", "v2"])

    def test_list_tools(self):
        self.reg.register("b.tool", "v1", {"type": "object"})
        self.reg.register("a.tool", "v1", {"type": "object"})
        self.assertEqual(self.reg.list_tools(), ["a.tool", "b.tool"])

    def test_register_rejects_non_object_schema(self):
        with self.assertRaises(ValueError):
            self.reg.register("demo.tool", "v1", ["not", "a", "dict"])

    def test_record_carries_metadata(self):
        self.reg.register("demo.tool", "v1", {"type": "object"})
        rec = self.reg.get_record("demo.tool", "v1")
        self.assertEqual(rec["tool"], "demo.tool")
        self.assertEqual(rec["version"], "v1")
        self.assertIn("registered_at", rec)

    def test_register_file(self):
        schema = {"type": "object", "properties": {}}
        path = os.path.join(self.tmp.name, "s.json")
        with open(path, "w") as fh:
            json.dump(schema, fh)
        self.reg.register_file("demo.tool", "v1", path)
        self.assertEqual(self.reg.lookup("demo.tool", "v1"), schema)

    def test_seed_helios_idempotent(self):
        first = self.reg.seed_helios()
        second = self.reg.seed_helios()
        self.assertEqual(first, second)
        files = [os.path.join(self.reg._tool_dir("helios.place_order"),
                              f"{v}.json") for v in ("v1", "v2", "v3")]
        mtimes = [os.path.getmtime(p) for p in files]
        self.reg.seed_helios()
        self.assertEqual(mtimes,
                         [os.path.getmtime(p) for p in files])


class TestCommittedSeeds(unittest.TestCase):
    def test_committed_seed_files_exist_and_load(self):
        reg = ContractRegistry(os.path.join(REPO_ROOT, "contracts"))
        self.assertEqual(reg.list_versions("helios.place_order"),
                         ["v1", "v2", "v3"])
        for v in ("v1", "v2", "v3"):
            schema = reg.lookup("helios.place_order", v)
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)


if __name__ == "__main__":
    unittest.main()
