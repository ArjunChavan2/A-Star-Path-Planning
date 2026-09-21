# Test Results — Map creation and map handling

Scope: `src/map_store.py`, `src/map_node.py`, `tools/map_to_rosbridge.py` (starter-provided,
used only as a client), `maps/student_map.json`, the `Makefile`'s `map` target, and how map
state flows into `src/plan_path_service.py`. Per the standing project rule, `src/astar.py` and
`src/heap.py` are out of scope (hand-implemented stubs); a `NotImplementedError` from either is
expected and not treated as a defect unless explicitly required otherwise.

## Summary

**Overall result: PASS**, with the audit's major finding closed and its minor/informational
findings confirmed as real (and low-severity, matching the audit's assessment).

The real `/map` wire path — TCP client → `gateway.py` → `registry.py` →
`map_node.py`'s validator → `map_store.py` — is now exercised end-to-end for the first time in
this repository (`tests/test_map_wire_protocol.py`, 4 new tests, all passing). Map replacement,
rejection of malformed publishes without state corruption or gateway crash, and the
`plan_path_service.py` map-presence gate all behave correctly. A live `make build && make run &&
make map` run against the real runtime also succeeds: `make map` exits 0, a subscriber connected
before the run receives exactly `maps/student_map.json`'s payload on `/map`, no background
process is left behind, and the server (`make run`) shuts down cleanly on SIGINT.

While writing the new integration tests, an unrelated **test-harness bug** (not a production
defect) was found and fixed: `tests/test_gateway_protocol.py`'s `_ServerThread.stop()` never
actually closed the gateway's listening socket before stopping the event loop/thread, which could
leave port 9095 bound long enough to cause an intermittent `OSError: address already in use` when
a second server-backed test module (e.g. the new `test_map_wire_protocol.py`) starts immediately
after it in the same `python -m unittest discover` run. Fixed by awaiting `gateway.stop()` before
stopping the loop, mirroring the same pattern already used in `test_map_wire_protocol.py`'s own
harness. This is a test-only change (see "Production-code boundary" — no `src/`, `tools/`, or
`maps/` files were modified).

Findings 2, 3, and 4 from `agent-notes/AUDIT.md` were dynamically confirmed as real (not just
inspection-based conjecture): the validator does accept a missing/malformed `header` and
`origin.orientation`, does silently drop rejected maps with zero diagnostic output, and does
accept `bool` where `int` is expected. All three remain low real-world risk exactly as the audit
assessed, since nothing downstream currently reads those fields — documented below for the record,
not fixed (out of the "do not modify production code" boundary for this phase).

## Test environment

- Python 3.14.6, macOS (Darwin 25.3.0), stdlib only (`asyncio`, `unittest`, `socket`, `json`) —
  no external dependencies.
- Repository root: `~/367_1`. All commands run from there.
- `make build` → `python3 -m py_compile src/*.py` (succeeds, no output).
- Full existing suite: `make test` (`python3 -m unittest discover -s tests -v`).
- New file added: `tests/test_map_wire_protocol.py` (test-only; see below).
- Modified file: `tests/test_gateway_protocol.py` (test-harness robustness fix only; see
  "Failures" for the underlying harness bug this fixes).
- Live end-to-end check: `make build`, then `make run` backgrounded, then `make map`, then a
  manual `SIGINT` to the `make run` process to confirm clean shutdown.
- Assumption: `127.0.0.1:9095` is free at the start of each server-backed test/run (true in this
  sandboxed environment; verified no stray listeners before starting).

## Tests performed

### 1. Valid `/map` publish reaches `MapStore` over the real wire path

- **Requirement/risk:** Audit Finding 1 — no test previously exercised
  `gateway.py → registry.py → map_node.py's validator → map_store.py`; all prior map tests called
  `MapStore.set_map()` directly with a pre-validated dict.
- **Method:** `tests/test_map_wire_protocol.py::test_valid_map_publish_reaches_map_store`. Spins
  up a real `Gateway` + `Registry` + `map_node`/`plan_path_service`/`heap_service` on a background
  thread/event loop (same pattern as `tests/test_gateway_protocol.py`), connects a raw
  `client_helper.Client`, sends `advertise` then `publish` on `/map` with the spec's exact example
  grid (`spec/PROJECT1_ASTAR.md`'s `/map format` JSON), then inspects the server's live
  `MapStore` instance (width, height, resolution, origin, and every cell's occupancy value) after
  a short settle delay.
- **Expected:** `MapStore.has_map()` becomes `True` and every stored field/cell matches the
  published payload.
- **Observed:** Matches exactly.
- **Result:** pass.

### 2. Second valid `/map` publish replaces the first

- **Requirement/risk:** Spec: "A later valid map replaces an earlier map, including your own
  map." Audit Finding 1 (replacement never exercised over the real wire path).
- **Method:** `test_second_valid_map_replaces_first`. Publishes the spec example grid (4×3,
  resolution 0.5, origin (-1,2)), confirms the store matches it, then publishes a structurally
  different valid grid (2×2, resolution 1.0, origin (5,-3)) and confirms the store now fully
  matches the *second* grid (dimensions, resolution, origin, and cell data), not a merge or
  leftover of the first.
- **Expected:** Store reflects only the second map after the second publish.
- **Observed:** Matches exactly; `width`/`height` correctly read back as 2/2 after replacement.
- **Result:** pass.

### 3. Malformed `/map` publishes are rejected without corrupting state or crashing the gateway

- **Requirement/risk:** Audit Finding 1 (malformed-publish path never exercised); protocol spec
  ("Malformed requests may be rejected... but they must not terminate the gateway or unrelated
  connections").
- **Method:** `test_malformed_map_rejected_without_corrupting_previous_map`. After establishing a
  known-good stored map, publishes 8 malformed variants in sequence over the same live server:
  missing `info`, wrong `data` length, a non-integer `data` entry, non-positive `width`, negative
  `resolution`, a bare string instead of an object, `null`, and a JSON array instead of an object.
  After *each* variant, asserts (a) the previously-stored valid map is byte-for-byte unchanged in
  `MapStore`, and (b) the gateway is still healthy by making a fresh `/heap_sort` service call on a
  new connection.
- **Expected:** Every malformed variant is dropped silently; the prior map and gateway health are
  unaffected.
- **Result:** pass (all 8 subtests).

### 4. `plan_path_service.py`'s map-presence gate reflects real map state

- **Requirement/risk:** How map state flows into `src/plan_path_service.py` (in scope); spec:
  "Return prompt ordinary `result:false`... before a map arrives."
- **Method:** `test_plan_path_gate_reflects_map_presence`. Calls `/plan_path` on a server with no
  map yet published and checks the response is `result:false` with a status containing "no map".
  Then publishes a valid map over the real wire path and calls `/plan_path` again, checking that
  the response is *no longer* the "no map" status — i.e., `plan_path_service.py` correctly passed
  the `map_store.has_map()` gate because the map genuinely arrived via the wire path, not because
  the gate is broken. (The second call still fails, with an internal-error status from
  `astar.py`'s intentional `NotImplementedError` stub — this is expected per the standing
  out-of-scope rule and is not evidence of a map-handling defect; the assertion only checks that
  the status is no longer "no map".)
- **Expected:** "no map" before publish; some other (non-"no map") failure status after publish.
- **Observed:** Matches exactly. Gateway log during the test shows
  `service handler for /plan_path raised: NotImplementedError()`, confirming the failure's actual
  source is the out-of-scope `astar.py` stub, not a map-handling problem.
- **Result:** pass.

### 5. Live `make build && make run && make map` against the real runtime

- **Requirement/risk:** Audit unverified risk #2 — `make map` had only been inspected, never
  actually run against a live `make run`.
- **Method:** Ran `make build` (clean, no output). Backgrounded `make run`, confirmed
  `gateway listening on 127.0.0.1:9095` on stderr. Started an independent raw-socket subscriber to
  `/map` *before* running `make map` (to match "Autograder.io first subscribes to `/map`, invokes
  `make map`"). Ran `make map` in the foreground and captured its exit code. Checked `ps` for any
  process from `tools/map_to_rosbridge.py` still running after `make map` returned. Sent `SIGINT`
  to the `make run` process and checked for the "shutting down" log line and a clean process exit
  (no zombie/orphan).
- **Expected:** `make map` exits 0; the subscriber receives `maps/student_map.json`'s exact
  payload on `/map`; no process from `make map` survives it; `make run` terminates cleanly on
  SIGINT.
- **Observed:**
  - `make map` exit code: `0`.
  - Subscriber received: `{"op":"publish","topic":"/map","msg":{"header":{"frame_id":"map"},"info":{"resolution":0.5,"width":4,"height":3,"origin":{"position":{"x":-1.0,"y":2.0,"z":0.0},"orientation":{"x":0.0,"y":0.0,"z":0.0,"w":1.0}}},"data":[0,0,100,0,0,0,0,0,0,0,0,0]}}` —
    an exact match for `maps/student_map.json`.
  - `ps aux` after `make map` returned showed only the `make run` (`src/main.py`) process; no
    lingering `map_to_rosbridge.py` process.
  - After `kill -INT` on the `make run` PID: stderr showed `shutting down`; the process was gone
    within 1 second (checked via `ps -p`).
- **Result:** pass.

### 6. `maps/student_map.json` satisfies "at least two 4-connected free cells"

- **Requirement/risk:** Audit unverified risk #3 — this was checked only by hand-inspection in the
  audit; automate it so a future edit can't silently violate it.
- **Method:** One-off script reading `maps/student_map.json`, computing free cells
  (`0 <= occupancy < 50`), and checking for at least one 4-connected adjacent pair.
- **Expected:** At least one such pair exists.
- **Observed:** 11 of 12 cells are free (only cell `(2,0)` is blocked, value 100); many
  4-connected free pairs exist. Confirmed `True`.
- **Result:** pass. (This was a throwaway diagnostic script, not committed as a test file — see
  "Remaining gaps" for a recommendation to promote it to a real regression test.)

### 7. Audit Finding 2 — validator accepts missing/malformed `header` and `origin.orientation`

- **Requirement/risk:** Confirm or refute dynamically (audit flagged this from inspection only).
- **Method:** Called `map_node._looks_like_valid_grid` directly (white-box, since this is
  validator-internal logic with no black-box-observable side effect other than accept/reject) with
  six variants: header key deleted, `header` set to a non-dict string, `origin.orientation`
  deleted, `origin.orientation` set to a non-dict string, and (combined with Finding 4 below) a
  `bool` width and `bool` data entries.
- **Observed:** All variants — including the ones missing `header` and `origin.orientation`
  entirely — return `True` (accepted).
- **Result:** confirmed real, as audited. Severity as assessed by the audit (minor): harmless
  today since `MapStore`/`plan_path_service.py` never read `header` or `origin.orientation`.

### 8. Audit Finding 3 — rejected `/map` messages produce zero diagnostic output

- **Requirement/risk:** Confirm or refute dynamically.
- **Method:** Started a real gateway with stderr captured to a file, published a structurally
  invalid `/map` message (`{"not": "a valid grid"}`) over a real TCP connection, and inspected the
  captured stderr.
- **Observed:** Stderr contains only the startup `gateway listening on 127.0.0.1:9095` line — no
  rejection diagnostic of any kind for the malformed publish, and `map_store.has_map()` is
  confirmed `False` afterward (correctly rejected, just silently).
- **Result:** confirmed real, as audited. Severity as assessed (minor): not a spec violation
  (no response to a bad `/map` publish is required), but makes a rejected grading map or a
  student typo invisible with no diagnostic trail.

### 9. Audit Finding 4 — `bool` accepted where `int` is expected

- **Requirement/risk:** Confirm or refute dynamically.
- **Method:** Part of the same direct-call check as #7: `width=True` (with matching `height`/
  `data` length) and `data=[True, False]` passed to `_looks_like_valid_grid`.
- **Observed:** Both accepted (`True`/`False` behave as `1`/`0` since `bool` subclasses `int` in
  Python).
- **Result:** confirmed real, as audited. Severity as assessed (informational): a spec-conformant
  publisher is very unlikely to send JSON booleans where integers are expected; the starter tool
  (`tools/map_to_rosbridge.py`) already excludes `bool` explicitly, so this repository's validator
  is the more permissive of the two, consistent with the audit's characterization ("a safe
  direction of mismatch").

## Failures

No production-code (`src/`, `tools/`, `maps/`) failures were found in this scope.

One test-harness bug was found and fixed:

- **What:** `tests/test_gateway_protocol.py`'s `_ServerThread.stop()` (before this fix) called
  only `self.loop.call_soon_threadsafe(self.loop.stop)` — it never called `Gateway.stop()`
  (which does `server.close(); await server.wait_closed()`). This leaves the listening socket on
  `127.0.0.1:9095` open and bound after the test class's `tearDownClass` returns, because nothing
  ever closes the underlying `asyncio` server object; the socket fd is only reclaimed when Python
  eventually garbage-collects it.
- **Reproduction (as originally observed, before the fix below):** Add a second
  server-backed test module after `test_gateway_protocol.py` in the same
  `python -m unittest discover -s tests` run, spinning up its own `_ServerThread` immediately in
  its own `setUp`/`setUpClass`. Intermittently (observed on the very first run while developing
  `tests/test_map_wire_protocol.py`, before applying the fix in item 2 below): `OSError: [Errno 48]
  address already in use` when the second module's server tries to bind port 9095, because
  `test_gateway_protocol.py`'s listener socket from the previous class was still open.
- **Fix applied (test-only):** In both `tests/test_gateway_protocol.py` and
  `tests/test_map_wire_protocol.py`, `_ServerThread.stop()` now does
  `asyncio.run_coroutine_threadsafe(self.gateway.stop(), self.loop).result(timeout=2)` before
  stopping the loop, ensuring the listening socket is actually closed before the next
  server-backed test tries to bind the same port.
- **Verification the fix holds:** `python3 -m unittest discover -s tests -v` run 4 times in a row
  after the fix (once during development, three more as an explicit repeatability check) — all
  runs produced the identical result (38 tests, 7 errors, all in `test_astar.py`, all
  `NotImplementedError` from the out-of-scope `astar.py` stub; zero errors/failures in any
  map-related test).
- **Attribution:** test-harness bug, not a production defect — `src/gateway.py`'s own
  `Gateway.stop()` correctly closes the server; the bug was only in the test class that never
  called it. No `src/`, `tools/`, or `maps/` file was touched.

## Remaining gaps

- **Concurrent/rapid `/map` publishes** (audit unverified risk #5 — the starter tool's own 3×
  back-to-back publish behavior in `tools/map_to_rosbridge.py`) was exercised implicitly by test
  #5 (the live `make map` run, which does send 3 publishes 50ms apart per the tool's own code) and
  produced no observable ill effect (single, correct final map state; clean exit), but no test
  asserts anything about *intermediate* state during that rapid sequence — a genuinely adversarial
  interleaving (e.g. two different clients racing to publish two different maps at nearly the same
  instant) was not exercised, since the single-event-loop/no-locking design makes this a low-value
  test (each `publish` is handled to completion before the next line is read off any socket).
- **`astar.py`/`heap.py` interaction with map state** (audit unverified risk #4): out of scope per
  the standing rule for this task; `plan_path_service.py`'s gating behavior around `map_store` is
  now verified (test #4), but the full `/plan_path → /path` success path against a real map cannot
  be verified until `astar.py` is implemented. Flagging forward for a future test pass once that
  stub is filled in, as the audit already recommended.
- **The one-off "at least two 4-connected free cells" check (test #6)** was a throwaway diagnostic
  script, not committed to `tests/`. Recommend promoting it to a small permanent regression test
  (e.g. `tests/test_student_map.py`) so a future hand-edit of `maps/student_map.json` can't
  silently violate the spec's minimum-connectivity requirement without a test catching it. Not
  added in this pass to keep the new test surface focused on the audit's stated top priority (the
  wire-path gap); can be added on request.
- **`maps/README.md`'s stale `docs/PROJECT1_ASTAR.md` path** (audit Finding 5, informational,
  not graded): not independently re-verified here since it's a static doc-content check with
  nothing to dynamically exercise; the audit's inspection-based finding stands as-is.
