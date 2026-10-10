"""Shared fixtures for the tool-contract-checker test suite."""

from __future__ import annotations

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


def obj(properties, required=(), **kw):
    schema = {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
    }
    schema.update(kw)
    return schema
