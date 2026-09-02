"""Project 1 runtime entry point (`make run`).

Wires the Registry, TCP gateway, and all in-process nodes together, then runs
the asyncio event loop in the foreground until SIGINT/SIGTERM for clean
termination.
"""
from __future__ import annotations

import asyncio
import signal

import heap_service
import map_node
import plan_path_service
from gateway import Gateway, log
from map_store import MapStore
from registry import Registry


async def run() -> None:
    registry = Registry()
    map_store = MapStore()

    heap_service.register(registry)
    map_node.register(registry, map_store)
    plan_path_service.register(registry, map_store)

    gateway = Gateway(registry)
    await gateway.start()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        log("shutting down")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_stop)

    await stop_event.wait()
    await gateway.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
