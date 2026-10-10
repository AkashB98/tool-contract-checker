"""Deep-diff two JSON Schema versions; classify each change.

Every change is classified into exactly one bucket:

- BREAKING      -- a client written against the OLD contract can now fail
                  validation against the NEW contract (removed required
                  field, narrowed type, tightened bound, ...).
- ADDITIVE     -- the change only widens what is accepted or adds optional
                  surface (new optional property, widened enum, widened
                  type). Old clients keep working; new capability is opt-in.
- NON-BREAKING -- compatible but not purely additive (description-only
                  edits, loosened bounds, removed optional property).

A *rename* is reported as a single BREAKING finding derived from a
remove+add pair, with an old->new migration hint, rather than as two
unrelated findings.

Changed regex patterns are treated as BREAKING on purpose: proving that a
new pattern accepts everything the old one did is undecidable in general,
so the tool flags it and asks a human to verify widening manually.
Removing a pattern is provably a widening, so it is NON-BREAKING.

Stdlib only. No network. Fully deterministic (findings sorted by path,
then category; no timestamps, no randomness).
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

BREAKING = "BREAKING"
NON_BREAKING = "NON-BREAKING"
ADDITIVE = "ADDITIVE"

# Rename pairing: pair a removed + added property only when their combined
# name/shape similarity clears this bar. Set high enough that a removed
# optional string and an added required enum-string do NOT pair.
RENAME_SIMILARITY_THRESHOLD = 0.5

# Schema keys that carry no validation semantics (ignored by shape compare).
_NON_SEMANTIC_KEYS = {"description", "title", "examples", "example", "$comment"}


@dataclass(frozen=True)
class Finding:
    kind: str        # BREAKING | NON-BREAKING | ADDITIVE
    category: str    # machine-readable change class, e.g. "enum_value_removed"
    path: str        # JSON path, e.g. "$.properties.priority"
    message: str     # human-readable explanation
    old: Any = None  # before (evidence)
    new: Any = None  # after (evidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "category": self.category,
            "path": self.path,
            "message": self.message,
            "old": self.old,
            "new": self.new,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# JSON Schema type lattice, expressed as atoms. Key subtlety: in JSON
# Schema, "number" accepts integers too (4 validates as number), so
# number -> integer is a NARROWING, not an unrelated change.
_TYPE_ATOMS = {
    "string": {"string"},
    "boolean": {"boolean"},
    "null": {"null"},
    "array": {"array"},
    "object": {"object"},
    "integer": {"integer"},
    "number": {"integer", "number"},
}


def _type_set(t: Any) -> Optional[Set[str]]:
    """Normalize a JSON Schema 'type' to a set of type names (or None)."""
    if t is None:
        return None
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return set(t)
    return None


def _type_atoms(t: Any) -> Optional[Set[str]]:
    names = _type_set(t)
    if names is None:
        return None
    atoms: Set[str] = set()
    for name in names:
        atoms |= _TYPE_ATOMS.get(name, {name})
    return atoms


def _strip_non_semantic(schema: Any) -> Any:
    """Remove documentation-only keys so shape comparison is semantic."""
    if isinstance(schema, dict):
        return {
            k: _strip_non_semantic(v)
            for k, v in schema.items()
            if k not in _NON_SEMANTIC_KEYS
        }
    if isinstance(schema, list):
        return [_strip_non_semantic(v) for v in schema]
    return schema


def _canonical(schema: Any) -> str:
    return json.dumps(_strip_non_semantic(schema), sort_keys=True)


def _shape_similarity(a: Any, b: Any) -> float:
    ca, cb = _canonical(a), _canonical(b)
    if ca == cb:
        return 1.0
    return difflib.SequenceMatcher(None, ca, cb).ratio()


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _is_object_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    t = _type_set(schema.get("type"))
    if t is not None and "object" not in t:
        return False
    return "properties" in schema or "required" in schema or "additionalProperties" in schema


# ---------------------------------------------------------------------------
# per-aspect comparisons
# ---------------------------------------------------------------------------

def _diff_type(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    ot, nt = _type_set(old.get("type")), _type_set(new.get("type"))
    if ot is None or nt is None or ot == nt:
        return
    # Compare by accepted-value atoms, not raw names: this makes
    # integer <-> number subset relations classify correctly.
    oa, na = _type_atoms(old.get("type")), _type_atoms(new.get("type"))
    assert oa is not None and na is not None
    if na > oa:
        out.append(Finding(
            ADDITIVE, "type_widened", path,
            f"type widened {sorted(ot)} -> {sorted(nt)}: "
            "previously-valid values are still accepted",
            sorted(ot), sorted(nt)))
    elif oa > na:
        out.append(Finding(
            BREAKING, "type_narrowed", path,
            f"type narrowed {sorted(ot)} -> {sorted(nt)}: "
            "values valid before may now be rejected",
            sorted(ot), sorted(nt)))
    else:
        out.append(Finding(
            BREAKING, "type_changed", path,
            f"type changed {sorted(ot)} -> {sorted(nt)}: "
            "previously-valid values may now be rejected",
            sorted(ot), sorted(nt)))


def _diff_enum(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    oe, ne = old.get("enum"), new.get("enum")
    if oe is None or ne is None:
        return
    old_vals, new_vals = list(oe), list(ne)
    if old_vals == new_vals:
        return
    removed = [v for v in old_vals if v not in new_vals]
    added = [v for v in new_vals if v not in old_vals]
    if removed:
        out.append(Finding(
            BREAKING, "enum_value_removed", path,
            f"enum value(s) removed {removed}: "
            "clients sending them will now fail validation",
            old_vals, new_vals))
    elif added:
        out.append(Finding(
            ADDITIVE, "enum_value_added", path,
            f"enum value(s) added {added}: old clients unaffected",
            old_vals, new_vals))
    else:  # same members, different order -> cosmetic
        out.append(Finding(
            NON_BREAKING, "enum_reordered", path,
            "enum members reordered; accepted values unchanged",
            old_vals, new_vals))


# (bound key, tighter_is: "larger" means the bound got MORE restrictive)
_BOUNDS: Tuple[Tuple[str, str], ...] = (
    ("minLength", "larger"),
    ("maxLength", "smaller"),
    ("minimum", "larger"),
    ("maximum", "smaller"),
    ("minItems", "larger"),
    ("maxItems", "smaller"),
)


def _diff_bounds(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    for key, tighter in _BOUNDS:
        ov, nv = old.get(key), new.get(key)
        if ov == nv:
            continue
        if ov is None:  # constraint added -> tightened
            out.append(Finding(
                BREAKING, "bound_tightened", path,
                f"{key} added ({nv}): previously-valid values may now be rejected",
                None, nv))
        elif nv is None:  # constraint removed -> loosened
            out.append(Finding(
                NON_BREAKING, "bound_loosened", path,
                f"{key} removed (was {ov}): strictly more values accepted",
                ov, None))
        else:
            tightened = (nv > ov) if tighter == "larger" else (nv < ov)
            if tightened:
                out.append(Finding(
                    BREAKING, "bound_tightened", path,
                    f"{key} tightened {ov} -> {nv}: "
                    "previously-valid values may now be rejected",
                    ov, nv))
            else:
                out.append(Finding(
                    NON_BREAKING, "bound_loosened", path,
                    f"{key} loosened {ov} -> {nv}: "
                    "previously-valid values are still accepted",
                    ov, nv))


def _diff_pattern(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    op, np = old.get("pattern"), new.get("pattern")
    if op == np:
        return
    if op is None:
        out.append(Finding(
            BREAKING, "pattern_added_or_changed", path,
            f"pattern added ({np!r}): previously-valid values may now be rejected; "
            "verify widening manually if this was meant to be compatible",
            None, np))
    elif np is None:
        out.append(Finding(
            NON_BREAKING, "pattern_removed", path,
            f"pattern removed (was {op!r}): strictly more values accepted",
            op, None))
    else:
        out.append(Finding(
            BREAKING, "pattern_added_or_changed", path,
            f"pattern changed {op!r} -> {np!r}: treated as potentially breaking; "
            "verify widening manually if this was meant to be compatible",
            op, np))


def _diff_additional_properties(old: Any, new: Any, path: str,
                                out: List[Finding]) -> None:
    # JSON Schema default for additionalProperties is True (allow anything).
    oa = old.get("additionalProperties", True)
    on = new.get("additionalProperties", True)
    if oa == on:
        return
    if on is False and oa is not False:
        out.append(Finding(
            BREAKING, "additional_properties_tightened", path,
            "additionalProperties true -> false: extra fields clients used to "
            "send will now be rejected",
            oa, on))
    elif on is True and oa is not True:
        out.append(Finding(
            NON_BREAKING, "additional_properties_loosened", path,
            "additionalProperties false -> true: extra fields now allowed",
            oa, on))
    # Any other change (e.g. true -> {"type": "string"}) is a tightening of
    # the unknown-field contract; flag it as breaking conservatively.
    elif oa is True:
        out.append(Finding(
            BREAKING, "additional_properties_tightened", path,
            f"additionalProperties changed {oa!r} -> {on!r}: "
            "extra-field contract tightened",
            oa, on))
    else:
        out.append(Finding(
            NON_BREAKING, "additional_properties_loosened", path,
            f"additionalProperties changed {oa!r} -> {on!r}",
            oa, on))


# ---------------------------------------------------------------------------
# property-level diff with rename pairing
# ---------------------------------------------------------------------------

def _pair_renames(removed: List[str], added: List[str],
                  old_props: Dict[str, Any],
                  new_props: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Greedily pair removed+added properties that look like renames."""
    scored: List[Tuple[float, str, str]] = []
    for r in removed:
        for a in added:
            name_sim = _name_similarity(r, a)
            shape_sim = _shape_similarity(old_props[r], new_props[a])
            combined = 0.5 * name_sim + 0.5 * shape_sim
            if combined >= RENAME_SIMILARITY_THRESHOLD:
                scored.append((combined, r, a))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))  # deterministic
    pairs: List[Tuple[str, str]] = []
    used_r, used_a = set(), set()
    for _, r, a in scored:
        if r not in used_r and a not in used_a:
            pairs.append((r, a))
            used_r.add(r)
            used_a.add(a)
    return pairs


def _diff_object(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    old_props = old.get("properties", {}) or {}
    new_props = new.get("properties", {}) or {}
    old_req = set(old.get("required", []) or [])
    new_req = set(new.get("required", []) or [])

    common = sorted(set(old_props) & set(new_props))
    removed = sorted(set(old_props) - set(new_props))
    added = sorted(set(new_props) - set(old_props))

    # 1. recurse into properties present in both versions
    for name in common:
        sub_path = f"{path}.properties.{name}"
        _diff_schema(old_props[name], new_props[name], sub_path, out)
        was_req, now_req = name in old_req, name in new_req
        if not was_req and now_req:
            out.append(Finding(
                BREAKING, "required_tightened", sub_path,
                f"'{name}' changed from optional to required: "
                "clients omitting it will now fail validation",
                {"required": False}, {"required": True}))
        elif was_req and not now_req:
            out.append(Finding(
                NON_BREAKING, "required_loosened", sub_path,
                f"'{name}' changed from required to optional: "
                "previously-valid calls are still accepted",
                {"required": True}, {"required": False}))

    # 2. rename pairing over removed+added
    pairs = _pair_renames(removed, added, old_props, new_props)
    paired_r = {r for r, _ in pairs}
    paired_a = {a for _, a in pairs}
    for r, a in sorted(pairs):
        sub_path = f"{path}.properties.{a}"
        out.append(Finding(
            BREAKING, "renamed_property", sub_path,
            f"property renamed '{r}' -> '{a}': clients still sending '{r}' "
            "will fail validation; update call sites",
            {"old_name": r, "schema": _strip_non_semantic(old_props[r])},
            {"new_name": a, "schema": _strip_non_semantic(new_props[a])}))
        # The rename pairs the two slots, but the property's own contract
        # may ALSO have changed (tightened bound, narrowed type, ...).
        # Diff the paired sub-schemas so those findings are not swallowed.
        _diff_schema(old_props[r], new_props[a], sub_path, out)

    # 3. unpaired removals
    for name in removed:
        if name in paired_r:
            continue
        sub_path = f"{path}.properties.{name}"
        if name in old_req:
            out.append(Finding(
                BREAKING, "removed_required_property", sub_path,
                f"required property '{name}' removed: "
                "clients sending it will fail validation",
                _strip_non_semantic(old_props[name]), None))
        else:
            out.append(Finding(
                NON_BREAKING, "removed_optional_property", sub_path,
                f"optional property '{name}' removed: "
                "compatible for clients that never sent it",
                _strip_non_semantic(old_props[name]), None))

    # 4. unpaired additions
    for name in added:
        if name in paired_a:
            continue
        sub_path = f"{path}.properties.{name}"
        sub = new_props[name]
        if name in new_req:
            if "default" in sub:
                out.append(Finding(
                    ADDITIVE, "new_required_with_default", sub_path,
                    f"new required property '{name}' has a default "
                    f"({sub['default']!r}): old clients may omit it; "
                    "the server fills the default",
                    None, _strip_non_semantic(sub)))
            else:
                out.append(Finding(
                    BREAKING, "new_required_no_default", sub_path,
                    f"new required property '{name}' without a default: "
                    f"clients must add '{name}' to calls",
                    None, _strip_non_semantic(sub)))
        else:
            out.append(Finding(
                ADDITIVE, "new_optional_property", sub_path,
                f"new optional property '{name}': old clients unaffected",
                None, _strip_non_semantic(sub)))

    # 5. additionalProperties
    _diff_additional_properties(old, new, path, out)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def _diff_schema(old: Any, new: Any, path: str, out: List[Finding]) -> None:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return
    _diff_type(old, new, path, out)
    _diff_enum(old, new, path, out)
    _diff_bounds(old, new, path, out)
    _diff_pattern(old, new, path, out)
    if _is_object_schema(old) or _is_object_schema(new):
        _diff_object(old, new, path, out)
    # arrays: compare items schemas
    if "items" in old or "items" in new:
        oi, ni = old.get("items"), new.get("items")
        if isinstance(oi, dict) and isinstance(ni, dict):
            before = len(out)
            _diff_schema(oi, ni, f"{path}.items", out)
            # re-point any BREAKING findings found inside items at the
            # property itself, so paths stay stable (e.g. $.properties.tags)
            for i in range(before, len(out)):
                f = out[i]
                if f.kind == BREAKING and f.path.startswith(f"{path}.items"):
                    out[i] = Finding(
                        BREAKING,
                        "items_narrowed" if f.category in
                        ("type_narrowed", "type_changed") else f.category,
                        path,
                        f"array items contract tightened: {f.message}",
                        f.old, f.new)
        elif oi != ni:
            out.append(Finding(
                BREAKING, "items_changed", path,
                "array 'items' schema changed incompatibly",
                oi, ni))


def diff_schemas(old: Dict[str, Any], new: Dict[str, Any],
                 path: str = "$") -> List[Finding]:
    """Diff two JSON Schemas; return findings sorted by (path, category)."""
    out: List[Finding] = []
    _diff_schema(old, new, path, out)
    out.sort(key=lambda f: (f.path, f.category, f.kind))
    return out
