# Heap module — documentation and usage

Reference documentation for `src/heap.py` and `src/heap_service.py`: the from-scratch binary
min-heap implementation, the wire services built on it, and how the rest of the project consumes
it. See [`PROJECT1_ASTAR.md`](PROJECT1_ASTAR.md) ("Project checkpoint — Heap services") for the
graded contract this module must satisfy, and [`ROSBRIDGE_PROTOCOL.md`](ROSBRIDGE_PROTOCOL.md) for
the wire envelope `/heapify` and `/heap_sort` are served over.

## Why a from-scratch heap

The project spec forbids built-in heap/priority-queue utilities (`heapq`, `queue.PriorityQueue`,
etc.) for this module. `src/heap.py` implements the sift-up/sift-down logic by hand, and — per the
spec's requirement that A* "must call [`/heap_sort`] to order frontier priorities" using "the same
heap machinery" — every other consumer of a priority queue in this project (the A* open-set
included) is expected to reuse this exact module rather than write a second, parallel
implementation.

## Array representation

All heap operations here work over a plain Python `list` using the standard 0-indexed binary-heap
layout:

```text
index i's children:  2*i + 1 (left), 2*i + 2 (right)
index i's parent:    (i - 1) // 2
```

A valid min-heap satisfies, for every index `i` with a present child `c`: `array[i] <= array[c]`.
No extra tree structure or pointers are used — parent/child relationships are computed from the
index alone.

## API reference

### `glb_sift_down(array, index, size, key=identity) -> int`

The shared sift-down primitive behind every other function in this module. Restores the min-heap
invariant *below* `index` by repeatedly swapping `array[index]` with its smaller present child
until it is no longer bigger than either child, or it has no children left within `size`.

- `size` is the *logical* heap length to consider, which may be less than `len(array)`. This lets
  `heap_sort` shrink the active region in place as it extracts elements, without needing to slice
  or resize the underlying array on every step.
- `key` extracts the comparable priority from each element — the identity function for a plain
  list of numbers (`build_heap`, `heap_sort`), or `lambda pair: pair[0]` for `MinHeap`'s
  `(priority, payload)` tuples.
- Returns the final resting index of the element that started at `index` (not currently used by
  any caller in this project, but useful for testing / debugging sift behavior in isolation).
- Runs in `O(log n)` time — at most one path from `index` down to a leaf.

### `class MinHeap`

A binary min-heap over `(priority, payload)` pairs, backed by a single internal `list`.
`priority` must be totally orderable (a `float`, or a tuple such as `(f_score, tie_counter)` for
deterministic tie-breaking — see the A* section below); `payload` is arbitrary and is never
compared, only carried alongside its priority.

| Method | Behavior | Complexity |
| --- | --- | --- |
| `MinHeap()` | Construct an empty heap. | `O(1)` |
| `len(heap)` | Number of elements currently stored. | `O(1)` |
| `push(priority, payload)` | Insert `(priority, payload)`, then sift it up to restore the invariant. | `O(log n)` |
| `pop()` | Remove and return the `(priority, payload)` pair with the smallest priority. Raises `IndexError` on an empty heap. | `O(log n)` |
| `peek()` | Return (without removing) the smallest-priority pair. Raises `IndexError` on an empty heap. | `O(1)` |

Internally, `push` appends to the end of the list and calls the private `_sift_up` helper to swap
the new element upward past any larger-priority ancestors. `pop` swaps the root with the last
element, removes and saves the old last element (now at the root), then calls `glb_sift_down` on
the new root to restore the invariant over the shrunk list.

**No decrease-key.** Like most array-backed binary heaps, `MinHeap` has no efficient way to lower
an already-pushed element's priority in place. Callers that need "found a better priority for
something already in the heap" behavior (A* being the canonical example) should push a fresh
`(priority, payload)` entry instead, and treat stale entries as disposable when popped — see
"Consuming `MinHeap` from `astar.py`" below.

### `build_heap(values: list[float]) -> list[float]`

Classic bottom-up ("Floyd") heapify: starting from the last parent index (`len(values) // 2 - 1`)
and walking down to index `0`, calls `glb_sift_down` at each position. Runs in `O(n)` time overall
(not `O(n log n)`) because most nodes are near the bottom of the tree, where sift-down does very
little work.

- Mutates and returns the same list — the returned array contains exactly the input multiset,
  rearranged into a valid heap layout. There is no single correct output arrangement; any valid
  heap over the same multiset is acceptable (this is what `/heapify` returns to callers verbatim).
- Handles empty input (loop simply doesn't execute), duplicates, negatives, and fractional values
  without special-casing, since comparison-based sifting doesn't care about value distribution.

### `heap_sort(numbers: list[float]) -> list[float]`

Textbook heapsort built entirely on the above primitives: `build_heap` the input, then repeatedly
swap the root (current minimum) to the end of the shrinking active region and `glb_sift_down` the
new root — this is the "selection from a min-heap" variant, so the extracted minimums come out in
descending order at the tail of the array as `size` shrinks. The final `[::-1]` reverses that into
ascending order before returning.

Same edge-case handling as `build_heap` (empty, duplicates, negative/fractional values), and runs
in `O(n log n)` time: `n` extractions, each doing an `O(log n)` sift-down.

## Wire-level usage: `/heapify` and `/heap_sort`

`src/heap_service.py` is a thin adapter: it has no algorithmic logic of its own, only argument
unpacking and response shaping, so `heap.py` remains the single place the heap logic lives.

```
call_service /heapify   {"values": [3.0, 1.0, 2.0]}   -> values: {"heap": [1.0, 3.0, 2.0]}  (any valid heap layout)
call_service /heap_sort {"numbers": [3.0, 1.0, 2.0]}  -> values: {"sorted": [1.0, 2.0, 3.0]}
```

Both handlers always report `result: true` — there is no failure mode for well-formed numeric
input, and missing arguments default to an empty list (`build_heap([])` / `heap_sort([])` both
handle that cleanly, per the "empty input succeeds" requirement in the project spec).

Example raw wire exchange (see `ROSBRIDGE_PROTOCOL.md` for the full envelope):

```json
--> {"op": "call_service", "id": "1", "service": "/heap_sort", "args": {"numbers": [3.0, 1.0, 2.0]}}
<-- {"op": "service_response", "service": "/heap_sort", "id": "1", "result": true, "values": {"sorted": [1.0, 2.0, 3.0]}, "status": ""}
```

## Internal usage: consuming `MinHeap` from `astar.py`

The A* planner's open-set/frontier is required by the project spec to reuse this exact
`heap.MinHeap`, not a second bespoke priority queue. The intended pattern:

1. **Priority shape.** Push `(f_score, tie_counter)` as the `priority` (a tuple, so Python compares
   `f_score` first and falls back to `tie_counter` only on an exact tie) and the grid cell (plus
   whatever else the planner needs to detect staleness — see below) as the `payload`.
2. **Deterministic tie-breaking.** `f_score` alone is not totally consistent under ties (multiple
   cells can share the same `f_score`); assign each `push` call a monotonically increasing
   `tie_counter` so equal-`f_score` entries still compare unambiguously and pop in a fixed,
   reproducible order.
3. **Working around no decrease-key.** When the planner discovers a cheaper path to a cell already
   in the open set, it cannot lower that entry's priority in place — it pushes a brand-new
   `(f_score, tie_counter)` entry for the same cell instead, leaving the old, now-worse entry
   sitting in the heap. The planner tracks the best known `g_score` per cell in a separate dict;
   when it later `pop()`s an entry, it compares that entry's own `g_score` (carried in the payload)
   against the best known value for that cell, and discards (skips, without expanding) any entry
   that turns out to be stale — i.e. worse than a `g_score` already found for that cell by the time
   it's popped.
4. **Termination.** The search loop continues popping from the `MinHeap` (discarding stale entries
   as they surface) until either the goal cell is popped (success) or the heap is exhausted with
   the goal never reached (failure — return promptly, never crash or hang, per spec).

This module deliberately does not implement any of steps 1–4 itself — `MinHeap` is a general
priority-queue primitive; the A*-specific priority shape, tie-breaking, and staleness bookkeeping
live in `astar.py`, which is the piece of this project left for you to implement by hand.

## Testing

`tests/test_heap.py` exercises `build_heap`, `heap_sort`, and `MinHeap` directly (empty input,
single element, duplicates, negatives/fractions, the exact worked example from the spec, a
randomized cross-check against Python's builtin `sorted`, and `MinHeap`'s push/pop ordering and
tuple-priority tie-breaking). `tests/test_gateway_protocol.py` additionally exercises `/heapify`
and `/heap_sort` end-to-end over a real TCP connection to a running gateway. Run either in
isolation with:

```
python3 -m unittest tests.test_heap -v
python3 -m unittest tests.test_gateway_protocol.TestGatewayProtocol.test_heapify_and_heap_sort_service -v
```
