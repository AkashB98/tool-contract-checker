# tool-contract-checker

**The API-versioning discipline every team shipping agent tools to customers needs.**

An **agent** — an AI program that takes actions by calling tools — talks to its tools through **contracts** — JSON Schemas that declare exactly what arguments each tool accepts. When a tool team renames `product_id` to `sku`, tightens a limit, or adds a required field, every agent built against the old contract can break at 2 AM. This project is the **CI gate** — continuous integration, the automated checks that run on every code change — that catches those breaks *before* they ship: it versions each tool's **JSON Schema** — a standard for declaring the required shape of JSON data — diffs versions, classifies every change as breaking or safe, and emits a **migration plan** — a machine-readable upgrade guide telling client teams what to change.

Where it sits in this portfolio's agent-shipping story: `structured-output-validator` makes tool-call outputs safe at **runtime** — while the agent is actually running; **this one keeps the contracts stable in CI**, so the validator never sees a surprise the tool team introduced last Tuesday.

## What it does

1. **Contract registry** (`registry.py`) — register and look up named, versioned tool contracts (`helios.place_order` v1 → v2 → v3), pinned as JSON under `contracts/`. Sample data is a fictional Helios Home store toolset with a realistic v1 → v2 → v3 evolution (a breaking v2, a compatible v3).
2. **Schema differ** (`diff.py`) — deep-diffs two contract versions and classifies each change as **BREAKING** — an old client can now fail validation — **ADDITIVE** — only widens what is accepted; old clients keep working — or **NON-BREAKING** — compatible but not purely additive. **Renames** — a property renamed between versions — are detected as a single remove+add pair (one finding with an old → new migration hint) instead of two unrelated findings. Changed **regex** — regular expression, a text-matching pattern — patterns are flagged breaking on purpose: proving a new pattern accepts everything the old one did is undecidable in general, so the tool asks a human to verify widening manually.
3. **Migration planner** (`migrate.py`) — per-version **changelog** — a human-readable list of what changed — plus a machine-readable JSON plan with per-path actions (`client_must_add`, `client_must_update`, `no_action`).
4. **Verdict API** (`checker.py`) — overall `COMPATIBLE` / `BREAKING` verdict, a weighted **severity score** — a single number summarizing how dangerous the change is — and findings with **JSON paths** — addresses like `$.properties.priority` pointing at the exact changed field — plus before/after evidence quotes.
5. **CLI** (`cli.py`) — `register` / `diff` / `check` / `demo` / `serve`. `check` exits 0 = compatible, 1 = breaking, 2 = error, so a pipeline can gate on it. `serve` exposes a tiny JSON API (`POST /diff`, `GET /contracts`) on localhost.
6. **One-command demo** (`demo.py`) — registers the seeds, diffs v1 → v2 (breaking, 4 findings) and v2 → v3 (compatible), prints the migration plan. Asserts internally, so it doubles as a smoke test.

## Quickstart

```bash
# one-command end-to-end (registers seeds, diffs v1->v2 and v2->v3)
python demo.py

# CI verdict: exit 0 = compatible, 1 = breaking, 2 = error
python cli.py check --tool helios.place_order --from v1 --to v2
python cli.py check --tool helios.place_order --from v2 --to v3

# classified diff (text or JSON)
python cli.py diff --tool helios.place_order --from v1 --to v2 --format json

# register your own contract version
python cli.py register --tool my.tool --version v1 --file schema.json

# tiny JSON API on :8765 (localhost only)
python cli.py serve --port 8765
# POST /diff {"tool": "helios.place_order", "from": "v1", "to": "v2"}
# GET  /contracts
```

Stdlib only — no dependencies, no network at runtime (the test suite stubs sockets to prove it).

## How it works

```
contracts/helios.place_order/v{N}.json
        │  registry.py: register / lookup / list
        ▼
diff.py: diff_schemas(old, new)
  ├─ type lattice      (integer ⊂ number: number→integer is a NARROWING)
  ├─ enum / bounds / pattern / additionalProperties / items
  ├─ required-ness flips (optional→required is breaking)
  └─ rename pairing    (remove+add with matching shape → one rename finding;
                        paired sub-schemas are still diffed for inner changes)
        ▼
checker.py: verdict + severity = Σ weights of breaking findings
        ▼
migrate.py: changelog lines + per-path migration notes + JSON plan
        ▼
cli.py: check (exit 0/1/2) · diff · register · serve · demo
```

**Severity weights** (roughly: "a client that worked yesterday breaks today" scores highest):

| Change | Weight |
|---|---|
| removed required property, new required field without default | 10 |
| optional → required | 9 |
| type narrowed/changed, renamed property | 8 |
| removed enum value, array items narrowed/changed | 6 |
| pattern added/changed | 5 |
| bound tightened (`minimum`, `maximum`, `minLength`, …), `additionalProperties` tightened | 4 |

## Breaking-change taxonomy

| # | Change | Verdict | Example path |
|---|---|---|---|
| 1 | Removed required property | BREAKING | `$.properties.quantity` |
| 2 | New required field without default | BREAKING | `$.properties.priority` |
| 3 | New required field *with* default | ADDITIVE | `$.properties.priority` |
| 4 | Optional → required | BREAKING | `$.properties.notes` |
| 5 | Required → optional | NON-BREAKING | `$.properties.notes` |
| 6 | Type narrowed (`number`→`integer`, `string`→`number`) | BREAKING | `$.properties.rating` |
| 7 | Type widened (`integer`→`number`, `integer`→`[integer, null]`) | ADDITIVE | `$.properties.qty` |
| 8 | Removed enum value | BREAKING | `$.properties.delivery_speed` |
| 9 | Added enum value | ADDITIVE | `$.properties.delivery_speed` |
| 10 | Bound tightened (`minimum`↑, `maximum`↓, `minLength`↑, `maxLength`↓) | BREAKING | `$.properties.quantity` |
| 11 | Bound loosened | NON-BREAKING | `$.properties.notes` |
| 12 | Pattern added/changed | BREAKING (verify widening manually) | `$.properties.zip` |
| 13 | Pattern removed | NON-BREAKING | `$.properties.zip` |
| 14 | `additionalProperties` true→false | BREAKING | `$` |
| 15 | `additionalProperties` false→true | NON-BREAKING | `$` |
| 16 | Array `items` narrowed | BREAKING | `$.properties.tags` |
| 17 | Renamed property (remove+add pair) | BREAKING (+ migration hint) | `$.properties.sku` |
| 18 | New optional property | ADDITIVE | `$.properties.gift_wrap` |
| 19 | Description-only edit | silent (no finding) | — |

## Evals

`python evals/run_evals.py` runs 27 hand-verified golden pairs: 15 breaking (each pins the **exact** breaking finding path set and category) and 12 compatible (each pins zero breaking findings, including the **false-positive traps** — traps that must NOT fire: description-only edits, added optional fields, widened enums, loosened bounds, removed patterns, type widenings, new required-with-default, and a remove+add pair with mismatched shapes that must NOT be called a rename). The suite runs twice in-process and the reports must be identical; `evals/eval_report.json` is committed with byte-stable output (sorted keys, no timestamps).

**Evals: 27/27 pass; report md5 byte-identical across runs** (see Verification below).

## Dev loop: what the tests caught

The tests genuinely found and fixed real bugs during this build (not after-the-fact polish):

1. **`number → integer` misclassified as `type_changed` instead of `type_narrowed`.** The differ compared raw type-name strings, so `{"number"}` vs `{"integer"}` looked like unrelated sets and fell through to the disjoint-change branch. But in **JSON Schema** — the standard for declaring the required shape of JSON data — `number` *accepts integers* (`4` validates as `number`), so `number → integer` is a true narrowing: `4.5` used to validate and now doesn't. Fixed with a type-**atom** — smallest unit of the type lattice — model where `number` = {integer, number}; subset relations are now computed on accepted values, not names. Caught by `test_type_narrowed_is_breaking`.
2. **Renamed properties swallowed their own inner changes.** When `product_id` → `sku` paired as a rename, the differ emitted the rename finding and never compared the two sub-schemas — so a rename *plus* a tightened `minLength` silently lost the bound-tightening finding. The verdict stayed correct (rename is already breaking) but the changelog lied by omission. Fixed: paired sub-schemas are now recursively diffed at the new property's path. Caught by `test_rename_plus_tightening_reports_both`.
3. **Same-shape coincidence rename** (design decision, pinned by test): with an aggressive pairing threshold, removing required `a: string` and adding required `b: string` pairs as a rename rather than remove+add. The tests forced the call: one BREAKING rename finding is more actionable than a remove+add pair for a same-shape swap, and both are breaking, so the heuristic stands — documented in `test_identical_shape_swap_pairs_as_rename`.

Also hardened: a 3,000-pair randomized fuzz over the differ (zero crashes, findings always sorted, kinds always valid).

## Verification

- **90/90 hermetic unit tests pass** (stdlib `unittest`; independently re-run twice).
- **27/27 golden evals pass**; `evals/eval_report.json` committed, md5 byte-identical across 3 runs.
- `demo.py` + `cli.py check/diff/demo/serve` smoke-tested live (serve hit over localhost, then shut down).
- Secret sweep clean (see below); stdlib only; no network at runtime.
- One clean commit; working tree clean; no remotes.

### Secret sweep

Ran over all `.py` / `.json` / `.md` files for `sk-…` keys, `api_key`/`password` assignments, and email addresses: **zero hits**. Copyright line in LICENSE carries the author's own name, as expected. No secrets, no personal data — all sample data is the fictional Helios Home store.

## Sample data

All contracts describe the fictional **Helios Home** smart-home store (`helios.place_order`). Zero personal data, zero real credentials. The v1 → v2 hop is deliberately breaking (rename `product_id`→`sku`, new required `priority`, tightened `quantity.minimum`, changed `zip` pattern, additive `overnight` shipping); v2 → v3 is deliberately compatible (optional `gift_wrap`, widened bounds/enum, `priority` gains a default).
