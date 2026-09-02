"""Node that subscribes to /map and feeds MapStore.

Validates just enough to avoid crashing the gateway on a malformed publish
(the wire protocol allows ``msg`` to be any JSON value); a rejected message is
silently dropped rather than tearing down the connection, since /map has no
acknowledgement in this protocol.
"""
from __future__ import annotations

from typing import Any

from map_store import MapStore
from registry import Registry

MAP_TOPIC = "/map"


def _looks_like_valid_grid(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    info = msg.get("info")
    if not isinstance(info, dict):
        return False
    width, height, resolution = info.get("width"), info.get("height"), info.get("resolution")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return False
    if not isinstance(resolution, (int, float)) or resolution <= 0:
        return False
    origin = info.get("origin", {})
    position = origin.get("position", {}) if isinstance(origin, dict) else {}
    if not isinstance(position.get("x"), (int, float)) or not isinstance(position.get("y"), (int, float)):
        return False
    data = msg.get("data")
    if not isinstance(data, list) or len(data) != width * height:
        return False
    return all(isinstance(v, int) for v in data)


class _InProcessSubscriber:
    """A Registry "connection" for internal nodes: routes publishes to a callback."""

    def __init__(self, on_message) -> None:
        self._on_message = on_message

    def send(self, message: dict) -> None:
        if message.get("op") == "publish":
            self._on_message(message.get("msg"))


def register(registry: Registry, map_store: MapStore) -> None:
    def on_map(msg: Any) -> None:
        if _looks_like_valid_grid(msg):
            map_store.set_map(msg)

    registry.subscribe(_InProcessSubscriber(on_map), MAP_TOPIC)
