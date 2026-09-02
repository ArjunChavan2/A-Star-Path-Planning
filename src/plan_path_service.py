"""Registers the /plan_path service and publishes successful plans on /path.

Request shape (spec/PROJECT1_ASTAR.md "/plan_path"):
    {"start": {"header": {...}, "pose": {"position": {"x", "y", "z"}, "orientation": {...}}},
     "goal":  {"header": {...}, "pose": {"position": {"x", "y", "z"}, "orientation": {...}}},
     "tolerance": 0.0}

Success response values: {"plan": {"header": {"frame_id": "map"}, "poses": [...]}}
Failure response values: {} (status carries a short diagnostic string; content is unspecified by spec)
"""
from __future__ import annotations

from typing import Any

import astar
from map_store import MapStore
from registry import Registry

PATH_TOPIC = "/path"

_IDENTITY_ORIENTATION = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}


def _pose_stamped(x: float, y: float) -> dict:
    return {
        "header": {"frame_id": "map"},
        "pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": _IDENTITY_ORIENTATION},
    }


def _extract_xy(pose_stamped: Any) -> tuple[float, float] | None:
    try:
        position = pose_stamped["pose"]["position"]
        return float(position["x"]), float(position["y"])
    except (KeyError, TypeError, ValueError):
        return None


def register(registry: Registry, map_store: MapStore) -> None:
    def handle_plan_path(args: Any) -> tuple[bool, dict, str]:
        args = args or {}
        start_xy = _extract_xy(args.get("start"))
        goal_xy = _extract_xy(args.get("goal"))
        tolerance = args.get("tolerance", 0.0)

        if start_xy is None or goal_xy is None:
            return False, {}, "malformed start/goal"
        if not map_store.has_map():
            return False, {}, "no map"

        success, path_cells = astar.plan_path(map_store, start_xy, goal_xy, tolerance)
        if not success:
            return False, {}, "unreachable or invalid endpoint"

        poses = [_pose_stamped(*map_store.cell_to_world(cx, cy)) for cx, cy in path_cells]
        plan = {"header": {"frame_id": "map"}, "poses": poses}
        registry.publish(PATH_TOPIC, plan)
        return True, {"plan": plan}, ""

    registry.register_handler("/plan_path", handle_plan_path)
