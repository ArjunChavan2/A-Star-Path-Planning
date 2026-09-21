# Audit — Map creation and map handling

Scope: `src/map_store.py`, `src/map_node.py`, `tools/map_to_rosbridge.py` (starter-provided,
reviewed only for correct use, not faulted), `maps/student_map.json`, `maps/README.md`, the
Makefile `map` target, and the map-related wiring in `src/main.py` and
`src/plan_path_service.py`. `src/astar.py` and `src/heap.py` are out of scope (documented stubs /
hand-implemented, per standing rule). This is a retroactive audit: there is no `PLAN.md` /
`IMPLEMENTATION.md` for this slice, so the implementation was compared directly against
`spec/PROJECT1_ASTAR.md` ("Map creation and map handling") and `spec/ROSBRIDGE_PROTOCOL.md`.

## Summary

The core map-handling path is small, correct, and matches the spec's geometry and free/blocked
formulas exactly (verified independently against `tests/test_map_store.py`, which passes 6/6 and
whose cases I hand-checked against the spec's formulas). `MapStore` is a thin, stateless-per-call
wrapper with no persistence across runs, and replacement is a trivial overwrite, matching "a later
valid map replaces an earlier map, including your own map." `map_node.py`'s validate-then-store
pattern is a reasonable way to avoid crashing the gateway on a malformed `/map` publish, and the
`Makefile`'s `map` target invokes the (unmodified) starter `tools/map_to_rosbridge.py` correctly
against `maps/student_map.json`.

However, the map-acceptance validator (`map_node._looks_like_valid_grid`) is looser than the
spec's stated `/map` contract in a few places, and — more importantly — there is **no test at any
level that exercises the actual `/map` wire path**: no test publishes a `/map` message over a real
or simulated connection and checks that `MapStore` picks it up, replaces a prior map, rejects a
malformed one, or that a subsequent `/plan_path` call succeeds against it. `tests/test_map_store.py`
only exercises `MapStore` directly against a dict that is handed to it pre-validated — it never
touches `map_node.py`'s validator or the `registry.subscribe` in-process delivery path at all. Given
map handling is 20% of the grade and is graded by external TCP publishes (both the student's own
map via `make map` and independent staff grading maps), this is the most significant gap.

## Findings

### Finding 1 — No test coverage for the `/map` receive/validate/replace path

- **Severity:** major
- **Location:** `tests/test_map_store.py`, `tests/test_gateway_protocol.py`, `src/map_node.py`
- **Problem:** Every existing map test constructs a `MapStore` directly and calls `set_map()` with
  an already-valid dict; `map_node.py`'s `_looks_like_valid_grid` validator and the
  `registry.subscribe` → `_InProcessSubscriber.send` → `on_map` delivery path are never exercised
  by any test. `tests/test_gateway_protocol.py` wires `map_node.register(...)` into its test
  harness but grep shows no test that sends a `publish` op on `/map` to the running gateway, so
  nothing verifies: (a) a well-formed external `/map` publish actually reaches `MapStore`; (b) a
  malformed `/map` publish is dropped rather than crashing or corrupting state; (c) a second valid
  `/map` publish replaces the first (including a smaller/larger grid with a different origin); (d)
  an end-to-end `/plan_path` call succeeds only after a real `/map` publish arrives over the wire.
- **Why it matters:** This is precisely the behavior the map category is graded on ("correctly
  receiving, interpreting, replacing, and planning against `/map`" — spec, "Grading"). All of it
  currently runs unverified except by manual/adversarial reasoning about the code.
- **Recommended action:** Flag for the test phase: add integration tests (using the existing
  `tests/client_helper.py` raw-socket client and the `_ServerThread` harness already present in
  `test_gateway_protocol.py`) that publish valid and invalid `/map` messages over TCP and assert on
  `MapStore` state (or on a subsequent `/plan_path` service response), plus a replacement test.

### Finding 2 — `_looks_like_valid_grid` accepts messages missing `header` or `origin.orientation`

- **Severity:** minor
- **Location:** `src/map_node.py:18-36`
- **Problem:** The spec lists `header`, `info.resolution`, `info.width`, `info.height`,
  `info.origin`, and `data` as all required, and states "Origin must have the Pose-like structure
  shown above; its orientation is identity/axis-aligned." `_looks_like_valid_grid` never inspects
  `msg.get("header")` at all (a message with no `header` key, or a non-dict `header`, still passes)
  and never inspects `origin.get("orientation")` (missing or malformed orientation still passes).
- **Why it matters:** Functionally harmless today, since neither `MapStore` nor
  `plan_path_service.py` ever reads `header` or `origin.orientation` from the stored grid — but it
  means the validator's name ("looks like a valid grid") overstates what it checks against the
  spec's actual required-field list, and a genuinely malformed map (e.g. one that a future consumer
  starts reading `header.frame_id` from) would silently be accepted.
- **Recommended action:** Either tighten the validator to check `isinstance(msg.get("header"), dict)`
  and the presence of a `w`/orientation-shaped dict under `origin`, or narrow the docstring/name to
  make clear it only validates the fields actually consumed downstream.

### Finding 3 — Rejected `/map` messages are dropped with zero diagnostics

- **Severity:** minor
- **Location:** `src/map_node.py:51-53`
- **Problem:** `on_map` calls `map_store.set_map(msg)` only `if _looks_like_valid_grid(msg)`; the
  `else` branch is implicit and silent — no call to `gateway.log` (the project's established
  pattern for diagnostic output kept off the protocol stream, used everywhere in `gateway.py`) and
  no `status` message to any client.
- **Why it matters:** The protocol doesn't require a response to a bad `/map` publish, so this is
  not a spec violation, but it makes a rejected grading map or a student mistake in
  `maps/student_map.json` silently invisible — the runtime just behaves as if no map (or the old
  map) were current, with no diagnostic trail to explain why `/plan_path` keeps failing.
- **Recommended action:** Log the rejection reason via `gateway.log` (or an equivalent stderr
  helper) when `_looks_like_valid_grid` returns `False`, without changing wire behavior.

### Finding 4 — `_looks_like_valid_grid`'s `int` checks accept `bool`

- **Severity:** informational
- **Location:** `src/map_node.py:25-27, 36`
- **Problem:** `isinstance(width, int)`, `isinstance(height, int)`, and `isinstance(v, int)` (for
  each `data` entry) all accept Python `bool`, since `bool` is a subclass of `int` (e.g.
  `width=True` behaves as `width=1`). By contrast, the starter's own
  `tools/map_to_rosbridge.py:integer()` explicitly excludes `bool` (`isinstance(value, bool) or not
  isinstance(value, int)` → reject). The two validators are therefore inconsistent, and this
  repository's validator is the more permissive one.
- **Why it matters:** Low real-world risk — a spec-conformant map or grading harness is very
  unlikely to send JSON `true`/`false` where an integer is expected — but it is a genuine gap
  relative to the stricter validation the project's own starter tool already models.
- **Recommended action:** Add `and not isinstance(width, bool)` (etc.) if tightening the validator
  per Finding 2; otherwise low priority.

### Finding 5 — `maps/README.md` points at a nonexistent path

- **Severity:** informational
- **Location:** `maps/README.md`
- **Problem:** The file tells the student to see "the map rules in `docs/PROJECT1_ASTAR.md`", but
  the spec actually lives at `spec/PROJECT1_ASTAR.md` in this repository (confirmed: `spec/` exists,
  `docs/` does not appear to hold this file).
- **Why it matters:** Not graded and not read by Autograder.io, but it's a stale/broken pointer for
  a human maintaining `maps/student_map.json` later.
- **Recommended action:** Fix the path reference.

## What checked out correctly (no defect found)

- `MapStore.is_free` implements the exact `0 <= occupancy < 50` free/blocked boundary from the
  spec, including the `-1`/negative-as-blocked case, and matches `tests/test_map_store.py`'s
  explicit boundary test at 49/50/-1/0.
- `MapStore.world_to_cell` / `cell_to_world` implement the spec's exact `floor` and cell-center
  formulas, verified against both the spec's own worked geometry and the existing nonzero-origin /
  non-unit-resolution test.
- Map replacement (`MapStore.set_map` unconditional overwrite of `self._grid`) correctly satisfies
  "a later valid map replaces an earlier map, including your own map" with no persistence across
  `make run` invocations.
- `map_node.py` correctly registers as an in-process `Registry` subscriber on `/map`
  (`_InProcessSubscriber.send` mirrors the real `Connection.send` shape used by TCP clients), so
  externally published `/map` messages and the student's own `make map` publish both flow through
  the identical `registry.publish` → subscriber fan-out path — there is no special-cased or
  bypassed delivery route for the student's own map.
- `plan_path_service.py` correctly gates on `map_store.has_map()` before calling into `astar.py`,
  returning a clean `result:false` ("no map") rather than crashing or hanging when no map has
  arrived yet, per spec ("Return prompt ordinary `result:false`... before a map arrives").
- The `Makefile`'s `map` target correctly requires `make run` to already be listening (it will fail
  cleanly, non-zero exit, if the connection is refused) and does not start a second runtime or
  leave background processes, matching the spec's `make map` contract.
- `tools/map_to_rosbridge.py` (starter-provided, not audited for defects per task scope) is invoked
  correctly and unmodified; its own `validate_map` pre-check is stricter than
  `map_node.py`'s acceptance check (see Finding 4), which is a safe direction of mismatch — the
  runtime is more permissive than the tool that feeds it, not less.
- No evidence of code resembling `~/reference-repos/rix-py` in the audited files; the map-handling
  code (in-process subscriber shim, validator, coordinate math) reads as independently written.
- Single-event-loop invariant (`registry.py`'s documented no-locking assumption) is respected:
  `main.py` runs everything under one `asyncio.run`, and the only place map-related code appears to
  cross a thread boundary is `tests/test_gateway_protocol.py`'s test harness, where the raw TCP
  client thread only writes bytes to a socket — it never calls `Registry`/`MapStore` methods
  directly, so the invariant isn't actually violated there either.

## Unverified risks

These require the test phase (dynamic execution), not just inspection:

1. **The actual `/map` wire path is unverified end-to-end** (see Finding 1) — this is the top
   priority for the test agent: publish a valid `/map` over a raw TCP client and confirm state
   change / a subsequent successful `/plan_path`; publish a second, different valid map and confirm
   replacement; publish a structurally invalid `/map` (missing field, wrong `data` length,
   non-integer `data` entries, non-positive `width`/`height`/`resolution`) and confirm it is
   dropped without affecting the previously-stored map or crashing the connection.
2. **`make map` has not been run against a live `make run`** as part of this audit (inspection
   only). The test phase should actually run `make build && make run` in the background, then
   `make map`, and confirm (a) `make map` exits 0, (b) a client subscribed to `/map` beforehand
   receives the publication, (c) `make map` itself leaves no background process running afterward.
3. **`maps/student_map.json`'s "at least two 4-connected free cells" requirement** is easy to
   confirm by inspection for this specific 4×3 grid (only one blocked cell), but should still be
   asserted by an automated check so a future edit to the file can't silently violate it.
4. **Interaction with `astar.py` once implemented**: `plan_path_service.py`'s contract with
   `map_store` (world↔cell conversion, `has_map`/`in_bounds`/`is_free` gating) is only exercised
   today via `test_map_store.py`'s unit-level checks; once `astar.py`'s stub is filled in, the test
   phase should re-verify the full `/plan_path` → `/path` flow against both the student's map and a
   staff-shaped map with a different origin/resolution, since that is explicitly called out in the
   spec as something the planner must handle ("your planner must handle arbitrary staff maps rather
   than rely on your example").
5. **Concurrent/rapid `/map` publishes** (e.g. the starter tool's own 3x back-to-back publish
   behavior in `tools/map_to_rosbridge.py`) have not been observed in practice — inspection suggests
   this is harmless (idempotent overwrite with identical payloads, single event loop serializes
   processing), but has not been dynamically confirmed to have no observable side effect (e.g. on
   any subscriber that reacts to every `/map` publish, not just changes).
