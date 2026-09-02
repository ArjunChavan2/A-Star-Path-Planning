"""Contract tests for src/astar.py -- expected to fail until you implement it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import astar  # noqa: E402
from map_store import MapStore  # noqa: E402


def _make_grid(width: int, height: int, blocked_cells: set) -> dict:
    data = [100 if (x, y) in blocked_cells else 0 for y in range(height) for x in range(width)]
    return {
        "header": {"frame_id": "map"},
        "info": {
            "resolution": 1.0,
            "width": width,
            "height": height,
            "origin": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}},
        },
        "data": data,
    }


def _store(width: int, height: int, blocked_cells: set = frozenset()) -> MapStore:
    store = MapStore()
    store.set_map(_make_grid(width, height, blocked_cells))
    return store


class TestAStar(unittest.TestCase):
    def test_no_map_fails(self) -> None:
        success, path = astar.plan_path(MapStore(), (0.5, 0.5), (1.5, 0.5), 0.0)
        self.assertFalse(success)

    def test_open_grid_shortest_path_length(self) -> None:
        store = _store(5, 5)
        success, path = astar.plan_path(store, (0.5, 0.5), (4.5, 0.5), 0.0)
        self.assertTrue(success)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (4, 0))
        self.assertEqual(len(path), 5)  # 4 moves -> 5 cells, Manhattan distance 4

    def test_start_equals_goal(self) -> None:
        store = _store(3, 3)
        success, path = astar.plan_path(store, (0.5, 0.5), (0.5, 0.5), 0.0)
        self.assertTrue(success)
        self.assertEqual(path, [(0, 0)])

    def test_goal_out_of_bounds_fails(self) -> None:
        store = _store(3, 3)
        success, _ = astar.plan_path(store, (0.5, 0.5), (99.5, 0.5), 0.0)
        self.assertFalse(success)

    def test_blocked_goal_fails(self) -> None:
        store = _store(3, 3, blocked_cells={(2, 2)})
        success, _ = astar.plan_path(store, (0.5, 0.5), (2.5, 2.5), 0.0)
        self.assertFalse(success)

    def test_wall_forces_detour_but_still_optimal(self) -> None:
        # 3-wide corridor with a wall across column 1 except one gap at (1,2)
        blocked = {(1, 0), (1, 1)}
        store = _store(3, 3, blocked_cells=blocked)
        success, path = astar.plan_path(store, (0.5, 0.5), (2.5, 0.5), 0.0)
        self.assertTrue(success)
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            self.assertEqual(abs(x1 - x2) + abs(y1 - y2), 1)  # each step is 4-connected
        for cell in path:
            self.assertNotIn(cell, blocked)
        self.assertEqual(len(path), 7)  # forced detour through row 2

    def test_unreachable_goal_fails(self) -> None:
        # fully wall off column 1 -> column 2 is unreachable from column 0
        blocked = {(1, y) for y in range(3)}
        store = _store(3, 3, blocked_cells=blocked)
        success, _ = astar.plan_path(store, (0.5, 0.5), (2.5, 0.5), 0.0)
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
