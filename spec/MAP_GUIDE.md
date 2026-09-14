# Map module — documentation and usage

Reference documentation for `src/map_store.py` and `src/map_node.py`: how an occupancy-grid `/map`
message is received over the wire, validated, stored, queried, and converted between world and
grid coordinates. See [`PROJECT1_ASTAR.md`](PROJECT1_ASTAR.md) ("Map creation and map handling",
"`/map` format") for the graded contract this module must satisfy, and
[`ROSBRIDGE_PROTOCOL.md`](ROSBRIDGE_PROTOCOL.md) for the `publish`/`subscribe` envelope `/map`
travels over.

## Data flow

```text
external client (make map / tools/map_to_rosbridge.py / Autograder.io)
                          |
                    publish /map  (TCP/JSON, see ROSBRIDGE_PROTOCOL.md)
                          |
                    gateway.py (wire layer)
                          |
                    registry.py (topic fan-out)
                          |
                    map_node.py  --_looks_like_valid_grid()--> reject (silent) or accept
                          |
                    map_store.py (MapStore.set_map)
                          |
              plan_path_service.py / astar.py read the stored grid
```

`map_node.py` is the only piece of code that ever calls `MapStore.set_map`; it subscribes to
`/map` as an ordinary `Registry` subscriber (via the in-process `_InProcessSubscriber` shim
described below) and only forwards a message into `MapStore` if it passes a structural validity
check first. `MapStore` itself has no opinion about *how* a grid arrived — it is a plain
in-memory container plus geometry helpers.

## `/map` wire format

Per the spec, a `/map` publish's `msg` is an OccupancyGrid-like JSON object:

```json
{
  "header": {"frame_id": "map"},
  "info": {
    "resolution": 0.5,
    "width": 4,
    "height": 3,
    "origin": {
      "position": {"x": -1.0, "y": 2.0, "z": 0.0},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    }
  },
  "data": [0, 0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0]
}
```

Required fields: `header`, `info.resolution`, `info.width`, `info.height`, `info.origin`, `data`.

- `width` / `height`: positive integers.
- `resolution`: a positive number (world units per cell).
- `data`: exactly `width * height` integer entries, **row-major**: cell `(x, y)` lives at
  `data[y * width + x]`.
- Occupancy semantics: a cell is **free** exactly when `0 <= occupancy < 50`; anything `< 0`
  (including the ROS convention `-1` for "unknown") or `>= 50` is **blocked**.
- `origin`: a Pose-like structure giving the world-coordinate position of grid cell `(0, 0)`'s
  corner; orientation is always identity/axis-aligned for this project (no rotated grids).
- A map must contain at least two 4-connected free cells, so an ordinary nontrivial planning
  request is possible against it.
- **Replacement, not merging:** a later valid `/map` publish replaces the entire prior map,
  including the student's own map being replaced by a staff grading map or vice versa. There is no
  persistence across `make run` invocations and no partial-update semantics.

## `src/map_node.py` — receiving and validating `/map`

### `_looks_like_valid_grid(msg) -> bool`

A structural gate run on every incoming `/map` payload before it's allowed to reach `MapStore`.
Because the wire protocol allows `msg` to be literally any JSON value, this function exists purely
to avoid crashing the gateway on garbage input — it is intentionally *permissive* rather than a
full spec-conformance validator (it does not currently inspect `header` or
`origin.orientation`, since nothing downstream reads them). It checks, in order:

1. `msg` is a `dict`.
2. `msg["info"]` is a `dict`.
3. `width`, `height` are `int` and positive; `resolution` is `int`/`float` and positive.
4. `origin.position.x` and `.y` are numeric (missing/malformed `origin` is tolerated as `{}`).
5. `data` is a `list` of length exactly `width * height`, and every entry is an `int`.

If any check fails, the message is silently dropped: `on_map` simply does not call
`map_store.set_map`, and the previously stored map (if any) is left untouched. There is no
acknowledgement or error response on `/map` in this protocol (it's a topic publish, not a service
call), so this silent-drop behavior is the correct failure mode — a malformed publish must never
crash the connection or corrupt the current map.

### `_InProcessSubscriber`

A minimal `Registry`-compatible "connection" object used to let an internal node (like this one)
subscribe to a topic the same way an external TCP client would, without actually opening a socket
to itself. Its `send(message)` method mirrors the shape a real `Connection.send` would receive on
a `publish` op, and forwards `message["msg"]` to a callback (`on_map`, here). This means an
externally published `/map` and the student's own `make map` publish both flow through the
*identical* `registry.publish` → subscriber fan-out path — there is no special-cased or bypassed
delivery route for either source.

### `register(registry, map_store)`

Wires the above together: constructs an `_InProcessSubscriber` around a closure that validates and
then stores each incoming message, and calls `registry.subscribe(...)` to attach it to the `/map`
topic. Called once from `src/main.py` at startup.

## `src/map_store.py` — storage and geometry

`MapStore` is a small, stateless-per-call wrapper around the most recently accepted grid message.
It holds at most one grid at a time (`self._grid`, or `None` before any map has arrived) and
exposes read-only geometry/occupancy queries over it.

| Member | Behavior |
| --- | --- |
| `set_map(grid_msg)` | Store `grid_msg`, unconditionally replacing whatever was stored before. Called only from `map_node.py`, only after `_looks_like_valid_grid` passes. |
| `has_map()` | `True` once any map has been stored. Used by `plan_path_service.py` to return a clean `result: false` ("no map") before a map arrives, rather than crashing or hanging. |
| `.width` / `.height` / `.resolution` | Direct passthroughs to `info.width` / `info.height` / `info.resolution` on the stored grid. |
| `.origin_x` / `.origin_y` | Passthroughs to `info.origin.position.x` / `.y`. |
| `in_bounds(cell_x, cell_y)` | `0 <= cell_x < width and 0 <= cell_y < height`. |
| `occupancy(cell_x, cell_y)` | Raw integer occupancy value at that cell, read from the row-major `data` array (`data[cell_y * width + cell_x]`). Callers must check `in_bounds` first — this does not bounds-check itself. |
| `is_free(cell_x, cell_y)` | `False` immediately if out of bounds; otherwise `0 <= occupancy < 50`, matching the spec's free/blocked boundary exactly (including the `-1`/negative-as-blocked case). |
| `world_to_cell(world_x, world_y)` | Converts a world-frame point to the `(cell_x, cell_y)` it falls in. |
| `cell_to_world(cell_x, cell_y)` | Converts a grid cell to its **center** point in the world frame (not its corner). |

### Coordinate conversion formulas

Exactly the formulas given in the spec, implemented with `math.floor` (not integer truncation —
these differ for negative inputs, which matters whenever `origin_x`/`origin_y` is nonzero or a
queried world point is negative relative to the origin):

```text
cell_x = floor((world_x - origin_x) / resolution)
cell_y = floor((world_y - origin_y) / resolution)

world_x = origin_x + (cell_x + 0.5) * resolution
world_y = origin_y + (cell_y + 0.5) * resolution
```

`world_to_cell` and `cell_to_world` are not exact inverses of each other in general — `world_to_cell`
maps every point *inside* a cell to that one cell (many-to-one), while `cell_to_world` picks the
canonical center point representative of that cell (one specific point back out). Round-tripping a
cell through `cell_to_world` then `world_to_cell` always returns the original cell, since the
center point is, by construction, strictly inside the cell's bounds.

**Worked example** (matching the sample grid above: `resolution = 0.5`, `origin = (-1.0, 2.0)`):

```text
world_to_cell(-0.75, 2.25):
    cell_x = floor((-0.75 - (-1.0)) / 0.5) = floor(0.5)  = 0
    cell_y = floor(( 2.25 -   2.0 ) / 0.5) = floor(0.5)  = 0
    -> cell (0, 0)

cell_to_world(0, 0):
    world_x = -1.0 + (0 + 0.5) * 0.5 = -0.75
    world_y =  2.0 + (0 + 0.5) * 0.5 =  2.25
    -> world (-0.75, 2.25)   (the cell's center — matches the point that mapped into it)
```

## Producing a map: `make map` and `tools/map_to_rosbridge.py`

`make map` must be run in a second terminal *while `make run` is already listening* — it connects
as an ordinary external TCP/JSON client, publishes exactly one occupancy-grid payload on `/map`,
and exits. This project's `Makefile` wires that target to
[`tools/map_to_rosbridge.py`](../tools/map_to_rosbridge.py) (starter-provided, unmodified) against
[`maps/student_map.json`](../maps/student_map.json) (student-authored). The tool performs its own
stricter pre-publish `validate_map` check (e.g. explicitly rejecting `bool` where an `int` is
expected, which `map_node.py`'s acceptance check does not) before sending the payload — this is a
safe mismatch, since it only makes the *feed* into the runtime stricter than the runtime's own
acceptance check, not the other way around.

Manually publishing a `/map` with a raw socket (for testing, or to understand the wire shape) looks
like:

```json
--> {"op": "publish", "topic": "/map", "msg": {"header": {"frame_id": "map"}, "info": {"resolution": 0.5, "width": 4, "height": 3, "origin": {"position": {"x": -1.0, "y": 2.0, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}}, "data": [0, 0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0]}}
```

There is no response to a `publish` op (see `ROSBRIDGE_PROTOCOL.md`) — success is only observable
indirectly, e.g. via a subsequent `/plan_path` call succeeding, or another subscriber on `/map`
receiving the fan-out.

## Testing

- `tests/test_map_store.py` — unit tests against `MapStore` directly: free/blocked boundary at
  occupancy 49/50/-1/0, row-major cell indexing, world↔cell round-tripping with a nonzero origin
  and non-unit resolution, `has_map()` before any map is set, and out-of-bounds cells reporting as
  not free.
- `tests/test_map_wire_protocol.py` — integration tests against a real running gateway: a valid
  `/map` publish actually reaching `MapStore` end-to-end through `map_node.py`'s validator and the
  `Registry` fan-out; a malformed `/map` publish being dropped without corrupting a
  previously-stored valid map; a second valid `/map` publish replacing the first; and
  `/plan_path`'s `result` reflecting whether a map is currently present.

```
python3 -m unittest tests.test_map_store -v
python3 -m unittest tests.test_map_wire_protocol -v
```

## Known validator gaps (see `agent-notes/AUDIT.md` for full detail)

`_looks_like_valid_grid` is intentionally permissive rather than a full conformance check against
every field the spec lists as required:

- It does not inspect `header` at all (a missing or non-dict `header` still passes).
- It does not inspect `origin.orientation` (missing or malformed orientation still passes).
- Its `isinstance(x, int)` checks (`width`, `height`, each `data` entry) accept Python `bool`,
  since `bool` is a subclass of `int` in Python — `tools/map_to_rosbridge.py`'s own validator is
  stricter here and explicitly excludes `bool`.
- A rejected `/map` message is dropped with no diagnostic output (no `gateway.log` call), so a
  malformed grading map or a mistake in `maps/student_map.json` is currently silent and hard to
  debug from the runtime's own output.

None of these are currently spec violations (nothing downstream reads `header` or
`origin.orientation`, and no test sends a `bool`-typed field), but they're documented here as
known, low-priority gaps rather than oversights — see `agent-notes/AUDIT.md` Findings 2-5 for the
full reasoning and suggested fixes if you choose to tighten them.
