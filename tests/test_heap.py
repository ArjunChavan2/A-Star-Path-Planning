"""Contract tests for src/heap.py -- expected to fail until you implement it."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import heap  # noqa: E402


def _is_valid_min_heap(array: list) -> bool:
    for i, value in enumerate(array):
        for child in (2 * i + 1, 2 * i + 2):
            if child < len(array) and value > array[child]:
                return False
    return True


class TestBuildHeap(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(heap.build_heap([]), [])

    def test_single_element(self) -> None:
        self.assertEqual(heap.build_heap([5.0]), [5.0])

    def test_preserves_multiset(self) -> None:
        values = [3.0, 1.0, 2.0, 1.0]
        result = heap.build_heap(values)
        self.assertEqual(sorted(result), sorted(values))

    def test_valid_heap_invariant(self) -> None:
        for _ in range(20):
            values = [random.uniform(-100, 100) for _ in range(random.randint(0, 30))]
            result = heap.build_heap(values)
            self.assertTrue(_is_valid_min_heap(result), f"not a valid heap: {result}")


class TestHeapSort(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(heap.heap_sort([]), [])

    def test_single_element(self) -> None:
        self.assertEqual(heap.heap_sort([5.0]), [5.0])

    def test_example_from_spec(self) -> None:
        self.assertEqual(heap.heap_sort([3.0, 1.0, 2.0]), [1.0, 2.0, 3.0])

    def test_duplicates(self) -> None:
        self.assertEqual(heap.heap_sort([2.0, 1.0, 2.0, 1.0]), [1.0, 1.0, 2.0, 2.0])

    def test_negatives_and_fractions(self) -> None:
        self.assertEqual(heap.heap_sort([-1.5, 2.25, -3.0, 0.0]), [-3.0, -1.5, 0.0, 2.25])

    def test_already_sorted(self) -> None:
        self.assertEqual(heap.heap_sort([1.0, 2.0, 3.0, 4.0]), [1.0, 2.0, 3.0, 4.0])

    def test_reverse_sorted(self) -> None:
        self.assertEqual(heap.heap_sort([4.0, 3.0, 2.0, 1.0]), [1.0, 2.0, 3.0, 4.0])

    def test_random_matches_builtin_sorted(self) -> None:
        for _ in range(20):
            values = [random.uniform(-100, 100) for _ in range(random.randint(0, 40))]
            self.assertEqual(heap.heap_sort(values), sorted(values))


class TestMinHeap(unittest.TestCase):
    def test_push_pop_ascending(self) -> None:
        h = heap.MinHeap()
        for priority, payload in [(3, "c"), (1, "a"), (2, "b")]:
            h.push(priority, payload)
        self.assertEqual(len(h), 3)
        self.assertEqual(h.pop(), (1, "a"))
        self.assertEqual(h.pop(), (2, "b"))
        self.assertEqual(h.pop(), (3, "c"))
        self.assertEqual(len(h), 0)

    def test_pop_empty_raises(self) -> None:
        h = heap.MinHeap()
        with self.assertRaises(IndexError):
            h.pop()

    def test_tuple_priority_tie_break(self) -> None:
        h = heap.MinHeap()
        h.push((5, 2), "second")
        h.push((5, 1), "first")
        self.assertEqual(h.pop(), ((5, 1), "first"))
        self.assertEqual(h.pop(), ((5, 2), "second"))


if __name__ == "__main__":
    unittest.main()
