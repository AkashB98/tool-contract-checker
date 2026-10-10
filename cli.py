#!/usr/bin/env python3
"""CLI for the tool-contract compatibility checker.

Commands:
  register  store a contract version: --tool NAME --version VER --file SCHEMA.json
  diff      show the classified diff between two versions (text or JSON)
  check     verdict for CI: exit 0 = COMPATIBLE, 1 = BREAKING, 2 = error
  demo      one-command end-to-end (registers seeds, diffs v1->v2 and v2->v3)
  serve     tiny JSON API: POST /diff {tool,from,to}, GET /contracts

Exit codes are CI-friendly: check exits 0/1/2 so a pipeline can gate on it.
Stdlib only. No network except `serve` (binds localhost only).
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from checker import check_versions, report_to_json
from migrate import migration_plan
from registry import ContractNotFound, ContractRegistry

EXIT_OK = 0          # compatible
EXIT_BREAKING = 1    # breaking changes detected
EXIT_ERROR = 2       # usage / lookup error


def _registry(root: str) -> ContractRegistry:
    return ContractRegistry(root)


def cmd_register(args: argparse.Namespace) -> int:
    reg = _registry(args.contracts)
    try:
        path = reg.register_file(args.tool, args.version, args.file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"registered {args.tool} {args.version} -> {path}")
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    reg = _registry(args.contracts)
    try:
        report = check_versions(reg, args.tool, args.from_version, args.to_version)
    except ContractNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.format == "json":
        print(report_to_json(report), end="")
    else:
        plan = migration_plan(report)
        print(f"{report['tool']}: {report['from_version']} -> {report['to_version']}")
        print(f"verdict: {report['verdict']}  severity: {report['severity']}")
        for line in plan["changelog"]:
            print(f"  {line}")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    reg = _registry(args.contracts)
    try:
        report = check_versions(reg, args.tool, args.from_version, args.to_version)
    except ContractNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    plan = migration_plan(report)
    print(f"{report['tool']}: {report['from_version']} -> {report['to_version']}: "
          f"{report['verdict']} (severity {report['severity']}, "
          f"{report['breaking_count']} breaking)")
    for line in plan["changelog"]:
        print(f"  {line}")
    return EXIT_OK if report["verdict"] == "COMPATIBLE" else EXIT_BREAKING


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    registry_root = "contracts"

    def _send(self, code: int, payload: object) -> None:
        body = json.dumps(payload, sort_keys=True, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/contracts":
            reg = ContractRegistry(self.registry_root)
            self._send(200, {"tools": {t: reg.list_versions(t)
                                       for t in reg.list_tools()}})
        elif self.path in ("/", "/health"):
            self._send(200, {"ok": True, "service": "tool-contract-checker"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/diff":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            reg = ContractRegistry(self.registry_root)
            report = check_versions(reg, payload["tool"],
                                    payload["from"], payload["to"])
        except (KeyError, ContractNotFound, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(200, {"verdict": report["verdict"],
                         "severity": report["severity"],
                         "plan": migration_plan(report)})

    def log_message(self, *args: object) -> None:  # quiet
        pass


def cmd_serve(args: argparse.Namespace) -> int:
    _Handler.registry_root = args.contracts
    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"serving on http://127.0.0.1:{args.port} "
          f"(contracts root: {args.contracts})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def cmd_demo(_args: argparse.Namespace) -> int:
    import demo
    demo.main()
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Version agent tool-call contracts; gate breaking changes in CI.")
    p.add_argument("--contracts", default="contracts",
                   help="contracts root directory (default: contracts)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("register", help="register a contract version")
    r.add_argument("--tool", required=True)
    r.add_argument("--version", required=True)
    r.add_argument("--file", required=True, help="JSON file holding the schema")
    r.set_defaults(func=cmd_register)

    d = sub.add_parser("diff", help="classified diff between two versions")
    d.add_argument("--tool", required=True)
    d.add_argument("--from", dest="from_version", required=True)
    d.add_argument("--to", dest="to_version", required=True)
    d.add_argument("--format", choices=["text", "json"], default="text")
    d.set_defaults(func=cmd_diff)

    c = sub.add_parser("check", help="CI verdict (exit 0 compatible, 1 breaking, 2 error)")
    c.add_argument("--tool", required=True)
    c.add_argument("--from", dest="from_version", required=True)
    c.add_argument("--to", dest="to_version", required=True)
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("serve", help="tiny JSON API (localhost only)")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    m = sub.add_parser("demo", help="one-command end-to-end demo")
    m.set_defaults(func=cmd_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
