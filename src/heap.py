"""From-scratch binary min-heap.

STUB: implement this file yourself. No built-in heap/priority-queue utilities
are allowed here (no ``heapq``, no ``queue.PriorityQueue``, etc.) -- the
sift-up/sift-down logic below must be written by hand.

This module backs three things, all of which must share this exact logic
(the project spec requires astar.py to reuse the same heap machinery that
answers /heap_sort, not a second parallel priority-queue implementation):
  - the ``/heapify`` service (heap_service.py calls ``build_heap``)
  - the ``/heap_sort`` service (heap_service.py calls ``heap_sort``)
  - astar.py's open-set (uses the ``MinHeap`` class directly)

Heap array convention: 0-indexed, children of index i live at 2*i+1 and
2*i+2, parent of i lives at (i-1)//2. A valid min-heap satisfies, for every
index i with a present child c: array[i] <= array[c].
"""
from __future__ import annotations

from typing import Any


class MinHeap:
    """A binary min-heap over ``(priority, payload)`` pairs.

    ``priority`` must be totally orderable (e.g. a float, or a tuple used for
    deterministic tie-breaking such as ``(f_score, tie_counter)``).
    ``payload`` is arbitrary and is not compared -- only ``priority`` decides
    ordering. This is what astar.py's open-set is built on.
    """

    def __init__(self) -> None:
        self._data: list[tuple[Any, Any]] = []

    def __len__(self) -> int:
        raise NotImplementedError

    def push(self, priority: Any, payload: Any) -> None:
        """Insert (priority, payload) and restore the heap invariant."""
        raise NotImplementedError

    def pop(self) -> tuple[Any, Any]:
        """Remove and return the (priority, payload) pair with the smallest priority.

        Raises IndexError if the heap is empty.
        """
        raise NotImplementedError

    def peek(self) -> tuple[Any, Any]:
        """Return (without removing) the (priority, payload) pair with the smallest priority.

        Raises IndexError if the heap is empty.
        """
        raise NotImplementedError

    # -- internal helpers you will likely want ------------------------------

    def _sift_up(self, index: int) -> None:
        raise NotImplementedError

    def _sift_down(self, index: int) -> None:
        raise NotImplementedError


def build_heap(values: list[float]) -> list[float]:
    """Build a valid binary min-heap array containing exactly the input multiset.

    Used directly by the /heapify service: the returned list is sent back
    verbatim as ``{"heap": [...]}}``. Any valid heap layout is accepted by the
    grader (there is no single "correct" arrangement) -- classic O(n)
    bottom-up heapify (sift-down starting from the last parent index down to
    0) is the standard approach.

    Must handle: empty input, duplicates, negative and fractional values.
    """
    raise NotImplementedError


def heap_sort(numbers: list[float]) -> list[float]:
    """Return ``numbers`` sorted ascending, using a from-scratch heap (no built-ins).

    Used directly by the /heap_sort service, and required by astar.py to
    order/select frontier priorities (see MinHeap above, which is the shared
    mechanism this project's A* must use).

    Must handle: empty input, duplicates, negative and fractional values.
    """
    raise NotImplementedError
