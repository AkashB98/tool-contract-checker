"""No-network enforcement: core flows work with sockets stubbed out.

Nothing in registry/diff/checker/migrate/demo may touch the network.
We stub socket.socket and socket.create_connection to raise, then run
the full core pipeline in-process. (The `serve` command is the only
network surface; it is smoke-tested manually, not in the suite.)
"""

import io
import os
import socket
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest_helper import obj  # noqa: E402

from checker import check  # noqa: E402
from migrate import migration_plan  # noqa: E402
from registry import ContractRegistry  # noqa: E402


def _raising_socket(*args, **kwargs):
    raise AssertionError("network socket used during hermetic test")


class TestNoNetwork(unittest.TestCase):
    def test_core_pipeline_with_sockets_stubbed(self):
        with mock.patch.object(socket, "socket", _raising_socket), \
             mock.patch.object(socket, "create_connection", _raising_socket):
            import tempfile
            tmp = tempfile.TemporaryDirectory()
            reg = ContractRegistry(os.path.join(tmp.name, "c"))
            old = obj({"sku": {"type": "string"}}, required=["sku"])
            new = obj({"sku": {"type": "string"},
                       "priority": {"type": "string"}},
                      required=["sku", "priority"])
            reg.register("demo.tool", "v1", old)
            reg.register("demo.tool", "v2", new)
            report = check(reg.lookup("demo.tool", "v1"),
                           reg.lookup("demo.tool", "v2"))
            plan = migration_plan(report)
            self.assertEqual(report["verdict"], "BREAKING")
            self.assertTrue(plan["changelog"])
            tmp.cleanup()

    def test_demo_with_sockets_stubbed(self):
        with mock.patch.object(socket, "socket", _raising_socket), \
             mock.patch.object(socket, "create_connection", _raising_socket):
            import demo
            buf = io.StringIO()
            with redirect_stdout(buf):
                demo.main()
            self.assertIn("demo OK", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
