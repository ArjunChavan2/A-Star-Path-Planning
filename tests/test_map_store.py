import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from map_store import MapStore  # noqa: E402

SPEC_EXAMPLE_GRID = {
    "header": {"frame_id": "map"},
    "info": {
        "resolution": 0.5,
        "width": 4,
        "height": 3,
        "origin": {"position": {"x": -1.0, "y": 2.0, "z": 0.0}, "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}},
    },
    "data": [0, 0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}


class TestMapStore(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MapStore()
        self.store.set_map(SPEC_EXAMPLE_GRID)

    def test_no_map_initially(self) -> None:
        self.assertFalse(MapStore().has_map())

    def test_cell_indexing_matches_row_major_formula(self) -> None:
        # data[y*width+x]; cell (2,0) is index 2 -> value 100 -> blocked
        self.assertEqual(self.store.occupancy(2, 0), 100)
        self.assertFalse(self.store.is_free(2, 0))
        self.assertTrue(self.store.is_free(0, 0))

    def test_free_boundary_at_50(self) -> None:
        grid = dict(SPEC_EXAMPLE_GRID)
        grid["data"] = [49, 50, -1, 0] + [0] * 8
        self.store.set_map(grid)
        self.assertTrue(self.store.is_free(0, 0))
        self.assertFalse(self.store.is_free(1, 0))
        self.assertFalse(self.store.is_free(2, 0))
        self.assertTrue(self.store.is_free(3, 0))

    def test_out_of_bounds_is_not_free(self) -> None:
        self.assertFalse(self.store.is_free(-1, 0))
        self.assertFalse(self.store.is_free(4, 0))
        self.assertFalse(self.store.is_free(0, 3))

    def test_world_to_cell_and_back_with_nonzero_origin_and_non_unit_resolution(self) -> None:
        # origin=(-1.0, 2.0), resolution=0.5 -> cell (0,0) covers world x in [-1.0,-0.5), y in [2.0,2.5)
        self.assertEqual(self.store.world_to_cell(-0.75, 2.25), (0, 0))
        self.assertEqual(self.store.cell_to_world(0, 0), (-0.75, 2.25))

    def test_cell_to_world_returns_cell_center(self) -> None:
        x, y = self.store.cell_to_world(2, 0)
        self.assertAlmostEqual(x, -1.0 + 2.5 * 0.5)
        self.assertAlmostEqual(y, 2.0 + 0.5 * 0.5)


if __name__ == "__main__":
    unittest.main()
