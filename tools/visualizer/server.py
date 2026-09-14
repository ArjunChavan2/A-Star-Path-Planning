"""Local debugging visualizer for the /map + /plan_path wire path.

NOT part of the graded submission -- a standalone dev tool for exercising
your own real gateway and astar.py implementation while you build them.
Browsers cannot open raw TCP sockets, so this is a tiny bridge: it serves
the static frontend (index.html) and translates a handful of HTTP endpoints
into raw newline-delimited JSON requests against the real gateway at
127.0.0.1:9095, per spec/ROSBRIDGE_PROTOCOL.md. It does not reimplement any
part of the wire protocol, the heap, or A* -- every request in this file is
answered by your actual running src/main.py.

Usage:
    Terminal:  python3 tools/visualizer/server.py
    Then open http://127.0.0.1:8800 in a browser and click "Restart gateway"
    (Python has no hot-reload, so every astar.py/map_store.py edit needs a
    fresh `make run` process -- the button kills whatever currently holds
    port 9095, ours or one started by hand in another terminal, and starts a
    new one). You can still run `make run` yourself in a separate terminal
    instead; the visualizer will report a clear error if it can't reach
    127.0.0.1:9095 either way.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9095
VISUALIZER_PORT = 8800

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(STATIC_DIR))
GATEWAY_LOG_PATH = os.path.join(STATIC_DIR, "gateway.log")

_gateway_proc: subprocess.Popen | None = None


def _port_is_open(timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((GATEWAY_HOST, GATEWAY_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _kill_whatever_is_on_gateway_port() -> None:
    """Kill any process bound to GATEWAY_PORT, ours or one started by hand.

    Restarting after an astar.py edit only works if the *old* interpreter
    actually exits -- Python has no hot-reload, so a stale `make run` left
    over from a previous terminal would otherwise keep answering on 9095
    while a freshly spawned one fails to bind. `lsof` finds the owner
    regardless of who started it (this bridge or a separate terminal).
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{GATEWAY_PORT}"], capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    pids = [int(p) for p in result.stdout.split() if p.strip()]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while pids and time.time() < deadline:
        pids = [p for p in pids if _pid_alive(p)]
        if not pids:
            break
        time.sleep(0.2)
    for pid in pids:  # still alive after SIGTERM grace period
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_gateway() -> tuple[bool, str]:
    """Start `make run` fresh and wait for it to bind GATEWAY_PORT."""
    global _gateway_proc
    log_f = open(GATEWAY_LOG_PATH, "wb")
    _gateway_proc = subprocess.Popen(
        ["make", "run"],
        cwd=PROJECT_ROOT,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # own process group, so we can clean up children too
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if _port_is_open():
            return True, ""
        if _gateway_proc.poll() is not None:
            break  # process already exited -- startup failed
        time.sleep(0.2)
    return False, _tail_log(40)


def _tail_log(n_lines: int) -> str:
    try:
        with open(GATEWAY_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n_lines:])
    except OSError:
        return ""


def _send_gateway_request(requests: list[dict], expect_id: str | None, timeout: float) -> list[dict]:
    """Open a fresh TCP connection, send each request line in order, collect responses.

    A new connection per call keeps this bridge simple and stateless; the
    gateway is required to accept multiple concurrent clients regardless.
    ``requests`` is a list so a caller can e.g. advertise then publish on the
    same connection -- the gateway only allows a publish from a connection
    that currently holds an advertisement on that topic (see gateway.py).
    Collects every JSON line received until a service_response matching
    ``expect_id`` arrives (for call_service), or until the read times out
    (for publish, which has no response to wait for per the protocol).
    """
    sock = socket.create_connection((GATEWAY_HOST, GATEWAY_PORT), timeout=timeout)
    sock.settimeout(timeout)
    responses: list[dict] = []
    try:
        for request in requests:
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                msg = json.loads(line.decode("utf-8"))
                responses.append(msg)
                if (
                    expect_id is not None
                    and msg.get("op") == "service_response"
                    and msg.get("id") == expect_id
                ):
                    return responses
    finally:
        sock.close()
    return responses


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, name: str, content_type: str) -> None:
        path = os.path.join(STATIC_DIR, name)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if self.path == "/api/sample_map":
            sample_path = os.path.join(PROJECT_ROOT, "maps", "student_map.json")
            try:
                with open(sample_path, "r", encoding="utf-8") as f:
                    self._send_json(200, json.load(f))
            except OSError as exc:
                self._send_json(404, {"error": str(exc)})
            return
        if self.path == "/api/gateway_status":
            self._send_json(200, {"listening": _port_is_open()})
            return
        if self.path == "/api/gateway_log":
            self._send_json(200, {"log": _tail_log(80)})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "malformed JSON body"})
            return

        try:
            if self.path == "/api/publish_map":
                self._handle_publish_map(payload)
            elif self.path == "/api/plan_path":
                self._handle_plan_path(payload)
            elif self.path == "/api/heap_sort":
                self._handle_heap_call("/heap_sort", "numbers", payload)
            elif self.path == "/api/heapify":
                self._handle_heap_call("/heapify", "values", payload)
            elif self.path == "/api/restart_gateway":
                self._handle_restart_gateway()
            else:
                self._send_json(404, {"error": "not found"})
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            self._send_json(
                502,
                {"error": f"could not reach gateway at {GATEWAY_HOST}:{GATEWAY_PORT} ({exc}). Is `make run` active?"},
            )

    def _handle_publish_map(self, payload: dict) -> None:
        grid = payload.get("map")
        if not isinstance(grid, dict):
            self._send_json(400, {"error": "missing 'map' object"})
            return
        # advertise before publish -- the gateway only accepts a publish from
        # a connection that currently holds an advertisement on that topic.
        advertise = {"op": "advertise", "topic": "/map", "type": "nav_msgs/OccupancyGrid"}
        publish = {"op": "publish", "topic": "/map", "msg": grid}
        _send_gateway_request([advertise, publish], expect_id=None, timeout=0.5)
        self._send_json(200, {"ok": True, "request": publish})

    def _handle_plan_path(self, payload: dict) -> None:
        start = payload.get("start")
        goal = payload.get("goal")
        tolerance = payload.get("tolerance", 0.0)
        if not isinstance(start, dict) or not isinstance(goal, dict):
            self._send_json(400, {"error": "missing start/goal"})
            return
        req_id = "viz-plan-1"
        identity = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        request = {
            "op": "call_service",
            "id": req_id,
            "service": "/plan_path",
            "args": {
                "start": {
                    "header": {"frame_id": "map"},
                    "pose": {"position": {"x": start["x"], "y": start["y"], "z": 0.0}, "orientation": identity},
                },
                "goal": {
                    "header": {"frame_id": "map"},
                    "pose": {"position": {"x": goal["x"], "y": goal["y"], "z": 0.0}, "orientation": identity},
                },
                "tolerance": tolerance,
            },
        }
        responses = _send_gateway_request([request], expect_id=req_id, timeout=5.0)
        service_response = next(
            (m for m in responses if m.get("op") == "service_response" and m.get("id") == req_id), None
        )
        self._send_json(200, {"request": request, "responses": responses, "service_response": service_response})

    def _handle_restart_gateway(self) -> None:
        try:
            _kill_whatever_is_on_gateway_port()
            ok, log_tail = _start_gateway()
            self._send_json(200, {"ok": ok, "log": log_tail})
        except Exception as exc:  # surfaced to the UI rather than a generic 502
            self._send_json(500, {"ok": False, "error": str(exc)})

    def _handle_heap_call(self, service: str, arg_key: str, payload: dict) -> None:
        req_id = "viz-heap-1"
        request = {"op": "call_service", "id": req_id, "service": service, "args": {arg_key: payload.get(arg_key, [])}}
        responses = _send_gateway_request([request], expect_id=req_id, timeout=3.0)
        service_response = next(
            (m for m in responses if m.get("op") == "service_response" and m.get("id") == req_id), None
        )
        self._send_json(200, {"request": request, "responses": responses, "service_response": service_response})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", VISUALIZER_PORT), Handler)
    print(f"Visualizer at http://127.0.0.1:{VISUALIZER_PORT}  (bridging to gateway at {GATEWAY_HOST}:{GATEWAY_PORT})")
    print("Use the page's 'Restart gateway' button after editing astar.py, or run `make run` yourself.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if _gateway_proc is not None:
            _kill_whatever_is_on_gateway_port()


if __name__ == "__main__":
    main()
