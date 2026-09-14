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

from typing import Any, Callable


def _identity(x: Any) -> Any:
    return x


def glb_sift_down(array: list, index: int, size: int, key: Callable[[Any], Any] = _identity) -> int:
    """Restore the min-heap invariant below ``index`` by pushing array[index] down.

    STUB: implement this yourself. Intended as the one shared piece of sift
    logic behind build_heap, heap_sort, and MinHeap._sift_down -- the "same
    heap machinery" the project spec asks for, rather than separate ad-hoc
    implementations in each place.

    - ``size`` is the logical heap length to consider (may be less than
      ``len(array)``, e.g. heap_sort shrinking the active region as it
      extracts elements without needing to physically resize the array).
    - ``key`` extracts the comparable priority from each element (identity
      for a plain list of numbers; ``lambda pair: pair[0]`` for MinHeap's
      (priority, payload) tuples).
    - Must keep descending as long as array[index] is bigger than its
      smallest present child (0, 1, or 2 children -- check bounds against
      ``size``), not stop after a single compare-and-swap.
    - Returns the final resting index of the element that started at ``index``.
    """
    while True:
        smallerIndex = index
        left = index * 2 + 1
        right = index * 2 + 2
        if left < size and key(array[smallerIndex]) > key(array[left]):
            smallerIndex = left
        if right < size and key(array[smallerIndex]) > key(array[right]):
            smallerIndex = right
        if smallerIndex == index:
            return index
        temp = array[index]
        array[index] = array[smallerIndex]
        array[smallerIndex] = temp
        index = smallerIndex


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
        return len(self._data)

    def push(self, priority: Any, payload: Any) -> None:
        """Insert (priority, payload) and restore the heap invariant."""
        self._data.append((priority, payload))
        index = self.__len__() - 1
        self._sift_up(index)

    def pop(self) -> tuple[Any, Any]:
        """Remove and return the (priority, payload) pair with the smallest priority.

        Raises IndexError if the heap is empty.
        """
        self._data[0], self._data[-1] = self._data[-1], self._data[0]
        ret = self._data.pop()
        index = glb_sift_down(self._data, 0, self.__len__(), key=lambda pair: pair[0])
        return ret
        

    def peek(self) -> tuple[Any, Any]:
        """Return (without removing) the (priority, payload) pair with the smallest priority.

        Raises IndexError if the heap is empty.
        """
        return self._data[0]

    # -- internal helpers you will likely want ------------------------------

    def _sift_up(self, index: int) -> None:
        while index > 0 and (self._data[(index - 1) // 2][0] > self._data[index][0]):
            temp = self._data[(index - 1) // 2]
            self._data[(index - 1) // 2] = self._data[index]
            self._data[index] = temp
            index = (index - 1) // 2


def build_heap(values: list[float]) -> list[float]:
    """Build a valid binary min-heap array containing exactly the input multiset.

    Used directly by the /heapify service: the returned list is sent back
    verbatim as ``{"heap": [...]}}``. Any valid heap layout is accepted by the
    grader (there is no single "correct" arrangement) -- classic O(n)
    bottom-up heapify (sift-down starting from the last parent index down to
    0) is the standard approach.

    Must handle: empty input, duplicates, negative and fractional values.
    """
    l = len(values)
    parent = l // 2 - 1
    while parent >= 0:
        glb_sift_down(values, parent, l)
        parent = parent - 1
    return values
                


def heap_sort(numbers: list[float]) -> list[float]:
    """Return ``numbers`` sorted ascending, using a from-scratch heap (no built-ins).

    Used directly by the /heap_sort service, and required by astar.py to
    order/select frontier priorities (see MinHeap above, which is the shared
    mechanism this project's A* must use).

    Must handle: empty input, duplicates, negative and fractional values.
    """
    numbers = build_heap(numbers)
    l = len(numbers)
    size = l
    for i in range(l):
        numbers[0], numbers[size - 1] = numbers[size - 1], numbers[0]
        size = size - 1
        index = glb_sift_down(numbers, 0, size)
    return numbers[::-1]
        
    
