# Project 1 — A* Search

EECS 367 Project 1 in Python (stdlib only): a small ROS-like pub/sub system exposed through a
rosbridge-style TCP/JSON gateway on `127.0.0.1:9095`, a from-scratch binary min-heap served as
`/heapify` and `/heap_sort`, and an A* planner over a 2D occupancy grid served as `/plan_path`.
The spec is `spec/PROJECT1_ASTAR.md`; the wire protocol is `spec/ROSBRIDGE_PROTOCOL.md`.

## How it runs

```
make build   # python3 -m py_compile src/*.py (offline, noninteractive)
make run     # python3 src/main.py, foreground, listens on 127.0.0.1:9095; Ctrl-C / SIGTERM stops it cleanly
make map     # second terminal, while `make run` is up: publishes maps/student_map.json on /map, then exits
make test    # python3 tests/run_tests.py
make clean   # removes src/__pycache__ and tests/__pycache__
```

`make run` starts one process: `src/main.py` creates a single `Registry` and `MapStore`, registers
the in-process nodes below against the registry, starts the asyncio TCP gateway, and waits for
SIGINT/SIGTERM. Everything runs on one asyncio event loop; the internal nodes do not connect to
their own socket. Logs go to stderr so they stay off the protocol stream. If something else
already holds port 9095, `make run` exits with `address already in use`.

`make map` runs `tools/map_to_rosbridge.py`, an ordinary external client: it validates the JSON,
connects to 9095, advertises `/map`, publishes the map three times (best effort, since the
protocol has no advertise acknowledgement), unadvertises, and exits. It fails with a hint if
`maps/student_map.json` is missing.

Topics and services (newline-delimited JSON, one message per line, lines up to 4 MiB):

| Name | Kind | Provided by | Payload |
|---|---|---|---|
| `/map` | topic, subscribed | `map_node.py` | OccupancyGrid-like `{header, info, data}` |
| `/path` | topic, published | `plan_path_service.py` | `{header: {frame_id: "map"}, poses: [...]}` |
| `/heapify` | service | `heap_service.py` | `{values}` -> `{heap}` |
| `/heap_sort` | service | `heap_service.py` | `{numbers}` -> `{sorted}` (ascending) |
| `/plan_path` | service | `plan_path_service.py` | `{start, goal, tolerance}` -> `{plan: {header, poses}}` |

Data flow, `/map` publish to `/path` publish:

1. A client publishes on `/map`. `gateway.py` hands it to `registry.py`, which delivers it to every
   subscriber, including `map_node.py`'s in-process subscriber.
2. `map_node.py` checks the shape (positive int width/height, positive resolution, numeric origin,
   `len(data) == width * height`, int cells). A bad map is dropped silently; a good one replaces
   the current map in `map_store.py`. Nothing is persisted between runs.
3. A client calls `/plan_path` with start and goal `PoseStamped`s. `plan_path_service.py` extracts
   the x/y positions (failure `"malformed start/goal"`) and checks a map exists (`"no map"`).
4. `astar.py` converts world to cell with `floor((world - origin) / resolution)`, rejects
   out-of-bounds or blocked endpoints (a cell is free when `0 <= value < 50`), and runs 4-connected,
   unit-cost A* with a Manhattan heuristic, using `heap.MinHeap` as the open set. `tolerance` is
   accepted and ignored.
5. On success the cells become cell-center poses (`origin + (cell + 0.5) * resolution`). The plan
   is published on `/path`, then returned as `{"plan": {...}}` in the `service_response`. On failure
   the response has `result: false`, empty `values`, and status `"unreachable or invalid endpoint"`.

## Layout

- `src/main.py` — `make run` entry point; wires registry, map store, nodes, and gateway; handles signals.
- `src/gateway.py` — asyncio TCP server for the wire protocol; 5 s timeout on calls routed to TCP service providers.
- `src/registry.py` — in-process topic/service registry with per-connection cleanup; no networking.
- `src/heap.py` — from-scratch binary min-heap (`MinHeap`, `build_heap`, `heap_sort`, shared `glb_sift_down`); no `heapq`.
- `src/heap_service.py` — registers `/heapify` and `/heap_sort` on top of `heap.py`.
- `src/map_store.py` — stores the current grid; bounds, free/blocked, and world/cell conversions.
- `src/map_node.py` — subscribes to `/map`, validates, and feeds `map_store.py`.
- `src/astar.py` — A* over `map_store.py`, returning grid cells from start to goal.
- `src/plan_path_service.py` — registers `/plan_path`, converts cells to poses, publishes `/path`.
- `tools/map_to_rosbridge.py` — starter-kit client used by `make map` (`--host`, `--port` options).
- `tools/visualizer/` — local debugging UI, not graded (see below).
- `maps/student_map.json` — our 4x3 map published by `make map`.
- `tests/` — unit and wire-level tests; see Testing.
- `spec/` — project spec, protocol, module guides, submission rules.
- `agent-notes/`, `prompts/` — agent workflow scaffolding and its audit/test notes; not part of the runtime.

## Testing

```
make test                          # runs tests/run_tests.py: unittest discovery over tests/test_*.py
python3 tests/test_heap.py         # every tests/test_*.py also runs on its own
```

Tests that start a gateway serve it on a free OS port (`tests/client_helper.py` picks it, and each
such test sets `gateway.PORT` to it), never 9095. The autograder runs the tests while its own
`make run` holds 9095, so they must pass with that port taken. `make test` must run
`tests/run_tests.py`; the grader checks for it (`tests/README.md`, rule 1).

## Submitting

From the project root, list the entries by name. Never tar `.`: GNU tar adds a `.` member that the
grader rejects as unsafe.

```
tar czf submission.tar.gz \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='gateway.log' \
  Makefile README.md .gitignore src tests tools maps
tar tzf submission.tar.gz | grep -qx Makefile && echo "Makefile at archive root: OK"
```

Full grader rules and the failures behind them: `spec/submission_layout.md`.

## Status

Complete. Scored 100% on the autograder (2026-10-27).

## Debugging tools

`tools/visualizer/` is a browser UI that talks to the real gateway (browsers cannot open raw TCP
sockets, so `server.py` bridges HTTP to `127.0.0.1:9095`). It does not reimplement anything.

```
make run                              # terminal 1
python3 tools/visualizer/server.py    # terminal 2, serves http://127.0.0.1:8800
```

Load `maps/student_map.json` or import your own `/map`-shaped JSON. Pick a click mode (toggle wall,
with click-drag painting; set start; set goal), click cells, then Plan Path. It publishes the map, calls `/plan_path`, draws
the returned path, and shows the raw request/response JSON in a wire log. It can also call
`/heapify` and `/heap_sort`. The "Restart gateway" button kills whatever process holds port 9095
(even one from another project) and starts a fresh `make run`, logging to
`tools/visualizer/gateway.log`.

## Where to read more

| File | What it is for |
|---|---|
| `spec/PROJECT1_ASTAR.md` | The assignment: required Make targets, services, map format, A* rules, grading |
| `spec/ROSBRIDGE_PROTOCOL.md` | The TCP/JSON wire protocol every client and the gateway speak |
| `spec/MAP_GUIDE.md` | How `map_store.py` and `map_node.py` receive, validate, and convert maps |
| `spec/HEAP_GUIDE.md` | How `heap.py` and `heap_service.py` work and who uses them |
| `spec/submission_layout.md` | Packaging `submission.tar.gz` and the grader's test rules |
| `agent-notes/AUDIT.md`, `agent-notes/TEST_RESULTS.md` | Audit and test report for map handling |
