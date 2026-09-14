# Project 1 — A* Search

Python implementation of a ROS-like pub/sub system with a rosbridge-style TCP/JSON gateway
(`127.0.0.1:9095`), a from-scratch binary min-heap, and an A* pathfinder over 2D occupancy grids.
Full spec: `spec/PROJECT1_ASTAR.md`, `spec/ROSBRIDGE_PROTOCOL.md`.

## Running

```
make build   # offline, noninteractive, compiles all of src/
make run     # foreground, listens on 127.0.0.1:9095, Ctrl-C / SIGTERM to stop cleanly
make map     # in a second terminal, while `make run` is active: publishes maps/student_map.json on /map
make test    # unit + integration tests (needs port 9095 free; not one of the required grader targets)
make clean   # removes __pycache__
```

## Layout

- `src/registry.py` — topic/service registry (pub/sub bookkeeping, connection-owned cleanup); no networking.
- `src/gateway.py` — asyncio TCP server implementing the wire protocol on top of `registry.py`.
- `src/heap.py` — **from-scratch binary min-heap** (`MinHeap`, `build_heap`, `heap_sort`; no `heapq`). Implemented by hand as part of the graded exercise.
- `src/heap_service.py` — registers `/heapify` and `/heap_sort` against the registry.
- `src/map_store.py` — in-memory OccupancyGrid storage + world↔cell conversions + free/blocked checks.
- `src/map_node.py` — subscribes to `/map`, feeds `map_store.py`.
- `src/astar.py` — **A\* search** over `map_store.py`, using `heap.py`'s `MinHeap` as the open-set. Implemented by hand as part of the graded exercise.
- `src/plan_path_service.py` — registers `/plan_path`, publishes the accepted path on `/path`.
- `src/main.py` — wires everything together; `make run`'s entry point.
- `tools/map_to_rosbridge.py` — provided by the starter kit; the external client `make map` uses.
- `tools/visualizer/` — **not part of the graded submission.** A local dev tool for debugging `astar.py`/`map_store.py` by hand: a browser UI that imports a custom map, lets you click to set start/goal, and calls the real `/plan_path` over the wire against your actual running gateway (no reimplementation of the algorithm). See "Debugging tools" below.
- `tests/` — unit tests (`test_map_store.py`, `test_heap.py`, `test_astar.py`) and a raw-socket integration suite (`test_gateway_protocol.py`) against a real running gateway.

## Design notes / documented assumptions

- **Internal architecture**: the gateway and all app nodes (heap service, map store, A* planner)
  run in a single asyncio process and share one `Registry` instance through an in-process API
  (`send`/`publish`/`register_handler`/`call_service_sync`) rather than the app nodes re-connecting
  to their own TCP socket. Grading is black-box over the wire protocol only, so this is an internal
  implementation choice — see `spec/PROJECT1_ASTAR.md`, "the internal design is entirely yours."
- **`/plan_path` success response**: `values` is `{"plan": {"header": {"frame_id": "map"}, "poses": [...]}}` — the plan is nested under `plan`, not a flat `poses` key (per the spec's exact wording).
- **`tolerance`**: accepted in the request but not required to change planning behavior (per spec, "need not alter Project 1 planning"); the current implementation ignores it.
- **A\* and `/heap_sort`**: per spec, "the planner must call [`/heap_sort`] to order frontier priorities before choosing work to expand." `astar.py` satisfies this by using the exact same `heap.MinHeap` primitives that back the `/heap_sort` service as its open-set, rather than a second, separate priority-queue implementation.
- Ties in the open-set are broken deterministically via a monotonically increasing tie counter assigned at push time (see `heap.py`/`astar.py` docstrings).

## Debugging tools

`tools/visualizer/` is a standalone, non-graded local dev tool for exercising your own
`astar.py`/`map_store.py` against the real gateway while you build them, since browsers can't open
raw TCP sockets and `Autograder.io` is otherwise the only thing calling `/plan_path`:

```
make run                              # terminal 1
python3 tools/visualizer/server.py    # terminal 2 -- bridges the browser to 127.0.0.1:9095
```

Then open <http://127.0.0.1:8800>. Import a custom `/map`-shaped JSON file (or load
`maps/student_map.json`), left-click a cell for Start, shift-click (or right-click) for Goal, and
hit Plan Path — it publishes your map and calls `/plan_path` over the real wire protocol, then
draws the returned path on the grid. A wire log panel shows the raw request/response JSON for both
calls, and failures surface whatever `status` string your `plan_path_service.py` returned. See
`spec/MAP_GUIDE.md` and `spec/HEAP_GUIDE.md` for the underlying module documentation.

## Status

`heap.py` and `astar.py` are left as documented stubs (`raise NotImplementedError`) for the
required from-scratch heap and A* implementation. Everything else is complete and testable against
those stubs' contracts. `make test` will fail on `test_heap.py`/`test_astar.py` until those two
files are implemented; `test_map_store.py` and `test_gateway_protocol.py` should already pass.
