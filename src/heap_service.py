"""Registers the /heapify and /heap_sort services against a Registry.

Thin wrapper: all algorithmic logic lives in heap.py.
"""
from __future__ import annotations

from typing import Any

import heap
from registry import Registry


def _heapify(args: Any) -> tuple[bool, dict, str]:
    values = (args or {}).get("values", [])
    result_heap = heap.build_heap(list(values))
    return True, {"heap": result_heap}, ""


def _heap_sort(args: Any) -> tuple[bool, dict, str]:
    numbers = (args or {}).get("numbers", [])
    sorted_numbers = heap.heap_sort(list(numbers))
    return True, {"sorted": sorted_numbers}, ""


def register(registry: Registry) -> None:
    registry.register_handler("/heapify", _heapify)
    registry.register_handler("/heap_sort", _heap_sort)
