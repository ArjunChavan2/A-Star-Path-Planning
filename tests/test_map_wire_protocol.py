"""Integration tests for the real `/map` wire path.

Audit finding (agent-notes/AUDIT.md, Finding 1): every prior map test called
MapStore.set_map() directly with a pre-validated dict, never touching
map_node.py's validator or the registry.subscribe -> _InProcessSubscriber ->
on_map delivery path a real TCP client actually exercises. These tests close
that gap: a real socket client connects, advertises, and publishes on /map,
and we confirm the message travels gateway.py -> registry.py ->
map_node.py's validator -> map_store.py, exactly as an autograder client
would.

Each test gets its own fresh server (own MapStore, own port-9095 bind) via
setUp/tearDown so map-replacement state from one test can't leak into
another.
"""
import asyncio
import copy
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import heap_service  # noqa: E402
import map_node  # noqa: E402
import plan_path_service  # noqa: E402
from gateway import Gateway  # noqa: E402
from map_store import MapStore  # noqa: E402
from registry import Registry  # noqa: E402

from client_helper import Client  # noqa: E402

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

# A second, structurally different valid map: different size, origin, and
# resolution, so replacement can't be mistaken for a no-op overwrite with an
# identical payload.
OTHER_VALID_GRID = {
    "header": {"frame_id": "map"},
    "info": {
        "resolution": 1.0,
        "width": 2,
        "height": 2,
        "origin": {"position": {"x": 5.0, "y": -3.0, "z": 0.0}, "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}},
    },
    "data": [0, 0, 0, 0],
}


class _ServerThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.registry = Registry()
        self.map_store = MapStore()
        heap_service.register(self.registry)
        map_node.register(self.registry, self.map_store)
        plan_path_service.register(self.registry, self.map_store)
        self.gateway = Gateway(self.registry)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.gateway.start())
        self.loop.run_forever()

    def start(self) -> None:
        self._thread.start()
        time.sleep(0.2)  # let the server begin listening

    def stop(self) -> None:
        # Close the listening socket (and wait for it to actually close)
        # before stopping the loop/thread, so the next test's server can
        # rebind 127.0.0.1:9095 immediately instead of racing a lingering
        # socket from this one.
        fut = asyncio.run_coroutine_threadsafe(self.gateway.stop(), self.loop)
        try:
            fut.result(timeout=2)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=2)


def _publish_map(msg) -> None:
    """Publish `msg` on /map as an ordinary external TCP/JSON client would."""
    with Client() as pub:
        pub.advertise("/map")
        pub.publish("/map", msg)
    # Delivery is in-process synchronous dispatch on the gateway's event
    # loop, but it runs on a different thread from the test; give it a
    # moment to be scheduled and processed.
    time.sleep(0.2)


def _store_matches(map_store: MapStore, grid: dict) -> bool:
    if not map_store.has_map():
        return False
    info = grid["info"]
    if map_store.width != info["width"] or map_store.height != info["height"]:
        return False
    if map_store.resolution != info["resolution"]:
        return False
    if map_store.origin_x != info["origin"]["position"]["x"]:
        return False
    if map_store.origin_y != info["origin"]["position"]["y"]:
        return False
    for y in range(map_store.height):
        for x in range(map_store.width):
            if map_store.occupancy(x, y) != grid["data"][y * info["width"] + x]:
                return False
    return True


class TestMapWireProtocol(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _ServerThread()
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    # -- Finding 1: real wire path reaches MapStore -------------------------

    def test_valid_map_publish_reaches_map_store(self) -> None:
        self.assertFalse(self.server.map_store.has_map())
        _publish_map(copy.deepcopy(SPEC_EXAMPLE_GRID))
        self.assertTrue(
            _store_matches(self.server.map_store, SPEC_EXAMPLE_GRID),
            "MapStore did not pick up a valid /map publish sent over a real TCP connection",
        )

    def test_second_valid_map_replaces_first(self) -> None:
        _publish_map(copy.deepcopy(SPEC_EXAMPLE_GRID))
        self.assertTrue(_store_matches(self.server.map_store, SPEC_EXAMPLE_GRID))

        _publish_map(copy.deepcopy(OTHER_VALID_GRID))
        self.assertTrue(
            _store_matches(self.server.map_store, OTHER_VALID_GRID),
            "second valid /map publish did not replace the first",
        )
        # Confirm it's a real replacement, not a merge/leftover of the first map's shape.
        self.assertEqual(self.server.map_store.width, 2)
        self.assertEqual(self.server.map_store.height, 2)

    def test_malformed_map_rejected_without_corrupting_previous_map(self) -> None:
        _publish_map(copy.deepcopy(SPEC_EXAMPLE_GRID))
        self.assertTrue(_store_matches(self.server.map_store, SPEC_EXAMPLE_GRID))

        malformed_variants = {
            "missing info": {"header": {"frame_id": "map"}, "data": []},
            "wrong data length": {**copy.deepcopy(OTHER_VALID_GRID), "data": [0, 0, 0]},
            "non-integer data entry": {
                **copy.deepcopy(OTHER_VALID_GRID),
                "data": [0, 0, "blocked", 0],
            },
            "non-positive width": {
                **copy.deepcopy(OTHER_VALID_GRID),
                "info": {**OTHER_VALID_GRID["info"], "width": 0},
                "data": [],
            },
            "negative resolution": {
                **copy.deepcopy(OTHER_VALID_GRID),
                "info": {**OTHER_VALID_GRID["info"], "resolution": -1.0},
            },
            "not a dict at all": "this is not a map",
            "null": None,
            "list instead of dict": [1, 2, 3],
        }

        for name, bad_msg in malformed_variants.items():
            with self.subTest(variant=name):
                _publish_map(bad_msg)
                self.assertTrue(
                    _store_matches(self.server.map_store, SPEC_EXAMPLE_GRID),
                    f"malformed /map variant {name!r} corrupted or discarded the previously-stored valid map",
                )
                # Connection/gateway must still be alive and serving other clients.
                with Client() as probe:
                    resp = probe.call_service("/heap_sort", {"numbers": []})
                    self.assertTrue(resp["result"], f"gateway appears unhealthy after malformed /map variant {name!r}")

    # -- how map state flows into plan_path_service.py ----------------------

    def test_plan_path_gate_reflects_map_presence(self) -> None:
        # Before any map: plan_path_service.py must gate on has_map() and
        # return a clean failure with a "no map" style status, without ever
        # reaching astar.py (which is an intentional stub / hand-implemented
        # exercise, out of scope here).
        with Client() as client:
            resp = client.call_service(
                "/plan_path",
                {
                    "start": {"header": {}, "pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}}},
                    "goal": {"header": {}, "pose": {"position": {"x": 1.0, "y": 1.0, "z": 0.0}}},
                    "tolerance": 0.0,
                },
            )
        self.assertFalse(resp["result"])
        self.assertIn("no map", resp.get("status", "").lower())

        # After a valid /map publish, plan_path_service.py must get past the
        # has_map() gate (map state actually flowed in) -- whatever happens
        # next is astar.py's job, out of scope, and expected to raise
        # NotImplementedError today, which the gateway catches and reports
        # as an internal error rather than "no map".
        _publish_map(copy.deepcopy(SPEC_EXAMPLE_GRID))
        with Client() as client:
            resp = client.call_service(
                "/plan_path",
                {
                    "start": {"header": {}, "pose": {"position": {"x": -0.75, "y": 2.25, "z": 0.0}}},
                    "goal": {"header": {}, "pose": {"position": {"x": 0.25, "y": 2.25, "z": 0.0}}},
                    "tolerance": 0.0,
                },
            )
        self.assertFalse(resp["result"])  # astar.py stub always fails today; not under test
        self.assertNotIn("no map", resp.get("status", "").lower())


if __name__ == "__main__":
    unittest.main()
