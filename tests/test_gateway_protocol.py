"""Raw-socket integration tests for the gateway: topic isolation, service id
correlation, and connection cleanup, per spec/ROSBRIDGE_PROTOCOL.md.

Runs the real gateway (Registry + Gateway + heap/map/plan_path nodes) on its
own event loop in a background thread, then drives it with raw TCP clients
via client_helper.Client -- this exercises exactly what the autograder does.
"""
import asyncio
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
        # Close the listening socket (and wait for it to actually close) before
        # stopping the loop/thread. Without this, the port-9095 listener socket
        # is never closed (only abandoned mid-loop-stop), so it can still be
        # bound and listening when another test module's server tries to bind
        # 127.0.0.1:9095 right after -- an intermittent
        # "address already in use" failure observed when running the full
        # suite (`make test` / `python -m unittest discover`) depending on
        # test module ordering. See also tests/test_map_wire_protocol.py,
        # which relies on this same fix for its per-test server instances.
        fut = asyncio.run_coroutine_threadsafe(self.gateway.stop(), self.loop)
        try:
            fut.result(timeout=2)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=2)


class TestGatewayProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _ServerThread()
        cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_topic_isolation(self) -> None:
        with Client() as sub_foo, Client() as sub_bar, Client() as pub:
            sub_foo.subscribe("/foo")
            sub_bar.subscribe("/bar")
            time.sleep(0.1)
            pub.advertise("/foo")
            pub.publish("/foo", {"data": "hello"})

            msg = sub_foo.recv_matching(lambda m: m.get("op") == "publish", timeout=2)
            self.assertEqual(msg["topic"], "/foo")

            with self.assertRaises(TimeoutError):
                sub_bar.recv_matching(lambda m: m.get("op") == "publish", timeout=0.5)

    def test_publish_without_advertise_is_rejected(self) -> None:
        with Client() as sub, Client() as pub:
            sub.subscribe("/foo")
            time.sleep(0.1)
            pub.publish("/foo", {"data": "hello"})  # never advertised
            with self.assertRaises(TimeoutError):
                sub.recv_matching(lambda m: m.get("op") == "publish", timeout=0.5)

    def test_unadvertise_revokes_publish_rights(self) -> None:
        with Client() as client_a, Client() as client_b:
            client_a.advertise("/foo")
            client_b.subscribe("/foo")
            client_b.recv_matching(lambda m: m.get("op") == "status", timeout=2)  # subscription confirmed

            client_a.unadvertise("/foo")
            client_a.publish("/foo", {"data": "should not arrive"})

            with self.assertRaises(TimeoutError):
                client_b.recv_matching(lambda m: m.get("op") == "publish", timeout=0.5)

    def test_heapify_and_heap_sort_service(self) -> None:
        with Client() as client:
            resp = client.call_service("/heap_sort", {"numbers": [3.0, 1.0, 2.0]})
            self.assertTrue(resp["result"])
            self.assertEqual(resp["values"]["sorted"], [1.0, 2.0, 3.0])

    def test_call_service_id_correlation_under_concurrent_calls(self) -> None:
        with Client() as client:
            client.send({"op": "call_service", "service": "/heap_sort", "id": "a", "args": {"numbers": [2, 1]}})
            client.send({"op": "call_service", "service": "/heap_sort", "id": "b", "args": {"numbers": [9, 5]}})
            responses = {}
            for _ in range(2):
                msg = client.recv_matching(lambda m: m.get("op") == "service_response")
                responses[msg["id"]] = msg
            self.assertEqual(responses["a"]["values"]["sorted"], [1, 2])
            self.assertEqual(responses["b"]["values"]["sorted"], [5, 9])

    def test_call_service_with_no_provider_returns_false_promptly(self) -> None:
        with Client() as client:
            start = time.monotonic()
            resp = client.call_service("/no_such_service", {}, timeout=2)
            elapsed = time.monotonic() - start
            self.assertFalse(resp["result"])
            self.assertLess(elapsed, 1.0)

    def test_unknown_op_gets_error_status_without_dropping_connection(self) -> None:
        with Client() as client:
            client.send({"op": "not_a_real_op"})
            msg = client.recv_matching(lambda m: m.get("op") == "status")
            self.assertEqual(msg["level"], "error")
            # connection should still be alive and usable afterward
            resp = client.call_service("/heap_sort", {"numbers": []})
            self.assertTrue(resp["result"])

    def test_disconnect_cleans_up_subscription(self) -> None:
        sub = Client()
        sub.subscribe("/temp")
        time.sleep(0.1)
        sub.close()
        time.sleep(0.1)
        with Client() as pub:
            pub.advertise("/temp")
            pub.publish("/temp", {"data": 1})  # must not raise / hang the server
        with Client() as probe:
            resp = probe.call_service("/heap_sort", {"numbers": []})
            self.assertTrue(resp["result"])


if __name__ == "__main__":
    unittest.main()
