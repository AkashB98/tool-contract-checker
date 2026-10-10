"""Versioned contract registry for agent tool-call JSON Schemas.

A contract registry is a version-controlled store of the JSON Schemas that
describe each agent tool's arguments. Think of it like an address book for
tools: "helios.place_order" has a v1 contract, a v2 contract, and so on, and
every version is pinned to disk so CI can diff them later.

Layout on disk: <root>/<tool>/<version>.json, each file holding
{"tool": ..., "version": ..., "registered_at": ..., "schema": {...}}.

Stdlib only. No network.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ContractNotFound(KeyError):
    """Raised when a tool/version pair is not in the registry."""


class ContractRegistry:
    """Register and look up named, versioned tool contracts."""

    def __init__(self, root: str = "contracts") -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    # -- paths -----------------------------------------------------------
    def _tool_dir(self, tool: str) -> str:
        return os.path.join(self.root, tool)

    def _version_path(self, tool: str, version: str) -> str:
        return os.path.join(self._tool_dir(tool), f"{version}.json")

    # -- writes ----------------------------------------------------------
    def register(
        self,
        tool: str,
        version: str,
        schema: Dict[str, Any],
        registered_at: str | None = None,
    ) -> str:
        """Store a contract version. Returns the file path written."""
        if not isinstance(schema, dict):
            raise ValueError("schema must be a JSON object (dict)")
        record = {
            "tool": tool,
            "version": version,
            "registered_at": registered_at or _utcnow_iso(),
            "schema": schema,
        }
        os.makedirs(self._tool_dir(tool), exist_ok=True)
        path = self._version_path(tool, version)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def register_file(self, tool: str, version: str, schema_path: str) -> str:
        """Register a contract from a JSON file on disk."""
        with open(schema_path, encoding="utf-8") as fh:
            data = json.load(fh)
        schema = data["schema"] if isinstance(data, dict) and "schema" in data else data
        return self.register(tool, version, schema)

    # -- reads -----------------------------------------------------------
    def get_record(self, tool: str, version: str) -> Dict[str, Any]:
        path = self._version_path(tool, version)
        if not os.path.isfile(path):
            raise ContractNotFound(f"no contract registered: {tool} {version}")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def lookup(self, tool: str, version: str) -> Dict[str, Any]:
        """Return just the JSON Schema for a tool/version pair."""
        return self.get_record(tool, version)["schema"]

    def list_tools(self) -> List[str]:
        if not os.path.isdir(self.root):
            return []
        return sorted(
            d
            for d in os.listdir(self.root)
            if os.path.isdir(os.path.join(self.root, d))
        )

    def list_versions(self, tool: str) -> List[str]:
        d = self._tool_dir(tool)
        if not os.path.isdir(d):
            return []
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))

    # -- seed data -------------------------------------------------------
    def seed_helios(self) -> List[str]:
        """Write the fictional Helios Home place_order v1/v2/v3 contracts.

        Fully deterministic content; re-running is idempotent (same bytes):
        versions whose stored schema is already identical are left untouched,
        so re-seeding never dirties the tree with fresh timestamps.
        Returns the list of (tool, version) seeded.
        """
        seeded = []
        for version, schema in sorted(_HELIOS_PLACE_ORDER.items()):
            path = self._version_path("helios.place_order", version)
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if existing.get("schema") == schema:
                        seeded.append(("helios.place_order", version))
                        continue
                except (OSError, ValueError):
                    pass
            self.register("helios.place_order", version, schema)
            seeded.append(("helios.place_order", version))
        return seeded


_HELIOS_PLACE_ORDER: Dict[str, Dict[str, Any]] = {
    "v1": {
        "type": "object",
        "title": "place_order v1",
        "description": "Fictional Helios Home store order tool (v1 contract).",
        "additionalProperties": False,
        "required": ["product_id", "quantity", "delivery_speed"],
        "properties": {
            "product_id": {
                "type": "string",
                "pattern": "^HH-[0-9]{4}$",
                "minLength": 8,
                "description": "Helios catalog product code",
            },
            "quantity": {
                "type": "integer",
                "minimum": 1,
                "maximum": 99,
                "description": "Number of units to order",
            },
            "delivery_speed": {
                "type": "string",
                "enum": ["standard", "express"],
                "description": "Shipping speed",
            },
            "notes": {
                "type": "string",
                "maxLength": 200,
                "description": "Free-text note for the warehouse",
            },
            "zip": {
                "type": "string",
                "pattern": "^[0-9]{5}$",
                "description": "Delivery ZIP code",
            },
        },
    },
    "v2": {
        "type": "object",
        "title": "place_order v2",
        "description": "Fictional Helios Home store order tool (v2 contract).",
        "additionalProperties": False,
        "required": ["sku", "quantity", "delivery_speed", "priority"],
        "properties": {
            "sku": {
                "type": "string",
                "pattern": "^HH-[0-9]{4}$",
                "minLength": 8,
                "description": "Helios catalog product code (renamed from product_id in v2)",
            },
            "quantity": {
                "type": "integer",
                "minimum": 2,
                "maximum": 99,
                "description": "Number of units to order",
            },
            "delivery_speed": {
                "type": "string",
                "enum": ["standard", "express", "overnight"],
                "description": "Shipping speed",
            },
            "priority": {
                "type": "string",
                "enum": ["standard", "high"],
                "description": "Order handling priority",
            },
            "notes": {
                "type": "string",
                "maxLength": 200,
                "description": "Free-text note for the warehouse",
            },
            "zip": {
                "type": "string",
                "pattern": "^[0-9]{5}(-[0-9]{4})?$",
                "description": "Delivery ZIP or ZIP+4 code",
            },
        },
    },
    "v3": {
        "type": "object",
        "title": "place_order v3",
        "description": "Fictional Helios Home store order tool (v3 contract).",
        "additionalProperties": False,
        "required": ["sku", "quantity", "delivery_speed", "priority"],
        "properties": {
            "sku": {
                "type": "string",
                "pattern": "^HH-[0-9]{4}$",
                "minLength": 8,
                "description": "Helios catalog product code",
            },
            "quantity": {
                "type": "integer",
                "minimum": 2,
                "maximum": 200,
                "description": "Number of units to order (bulk orders allowed since v3)",
            },
            "delivery_speed": {
                "type": "string",
                "enum": ["standard", "express", "overnight", "same_day"],
                "description": "Shipping speed",
            },
            "priority": {
                "type": "string",
                "enum": ["standard", "high"],
                "default": "standard",
                "description": "Order handling priority",
            },
            "notes": {
                "type": "string",
                "maxLength": 500,
                "description": "Free-text note for the warehouse",
            },
            "zip": {
                "type": "string",
                "pattern": "^[0-9]{5}(-[0-9]{4})?$",
                "description": "Delivery ZIP or ZIP+4 code",
            },
            "gift_wrap": {
                "type": "boolean",
                "description": "Add gift wrapping at checkout",
            },
        },
    },
}
