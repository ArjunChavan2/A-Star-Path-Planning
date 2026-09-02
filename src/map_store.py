"""In-memory OccupancyGrid-like map storage and coordinate conversions.

See spec/PROJECT1_ASTAR.md "/map format" and "Geometry, movement, and
optimality" for the exact rules this implements. No persistence across
`make run` invocations -- a later valid publish on /map replaces the current
map (including replacing the student's own map with a staff grading map, and
vice versa).
"""
from __future__ import annotations

import math
from typing import Any

FREE_MAX_EXCLUSIVE = 50  # 0 <= occupancy < 50 is free; >= 50 or < 0 is blocked


class MapStore:
    def __init__(self) -> None:
        self._grid: dict[str, Any] | None = None

    def set_map(self, grid_msg: dict[str, Any]) -> None:
        """Store a new OccupancyGrid-like message, replacing any previous map."""
        self._grid = grid_msg

    def has_map(self) -> bool:
        return self._grid is not None

    @property
    def width(self) -> int:
        return self._grid["info"]["width"]

    @property
    def height(self) -> int:
        return self._grid["info"]["height"]

    @property
    def resolution(self) -> float:
        return self._grid["info"]["resolution"]

    @property
    def origin_x(self) -> float:
        return self._grid["info"]["origin"]["position"]["x"]

    @property
    def origin_y(self) -> float:
        return self._grid["info"]["origin"]["position"]["y"]

    def in_bounds(self, cell_x: int, cell_y: int) -> bool:
        return 0 <= cell_x < self.width and 0 <= cell_y < self.height

    def occupancy(self, cell_x: int, cell_y: int) -> int:
        return self._grid["data"][cell_y * self.width + cell_x]

    def is_free(self, cell_x: int, cell_y: int) -> bool:
        if not self.in_bounds(cell_x, cell_y):
            return False
        value = self.occupancy(cell_x, cell_y)
        return 0 <= value < FREE_MAX_EXCLUSIVE

    def world_to_cell(self, world_x: float, world_y: float) -> tuple[int, int]:
        cell_x = math.floor((world_x - self.origin_x) / self.resolution)
        cell_y = math.floor((world_y - self.origin_y) / self.resolution)
        return cell_x, cell_y

    def cell_to_world(self, cell_x: int, cell_y: int) -> tuple[float, float]:
        world_x = self.origin_x + (cell_x + 0.5) * self.resolution
        world_y = self.origin_y + (cell_y + 0.5) * self.resolution
        return world_x, world_y
