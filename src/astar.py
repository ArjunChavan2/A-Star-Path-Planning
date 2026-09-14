"""A* search over a MapStore's occupancy grid.

STUB: implement plan_path() yourself. See spec/PROJECT1_ASTAR.md ("A*
planner" section) for the full rules; the essentials are restated here.

Requirements this function must satisfy:
  - Movement is 4-connected only (N/S/E/W), each move costs 1. No diagonals,
    no corner-cutting, no teleporting.
  - Use heap.MinHeap as the open-set/frontier -- the project spec requires
    the same from-scratch heap machinery that backs /heap_sort to be reused
    here (do not implement a second, separate priority queue). Push
    ``(f_score, tie_counter, cell)`` so ties break deterministically on a
    monotonically increasing tie_counter (assign one per push).
  - Use the Manhattan distance to the goal cell as the heuristic (admissible
    and consistent for a 4-connected, unit-cost grid -- do NOT use Euclidean,
    it can overestimate here and break optimality).
  - A from-scratch heap has no efficient decrease-key. The standard fix:
    keep a "best g-score seen so far" dict per cell; when you pop an entry,
    if its g-score is worse than the best known for that cell, it's stale --
    discard it and pop again instead of expanding it.
  - Reconstruct the path via a came_from dict (cell -> predecessor cell),
    walking backward from the goal cell to the start cell, then reversing.
  - Convert cells to world coordinates via MapStore.cell_to_world (returns
    cell centers, per the spec's exact formulas already implemented there).
  - Returned path must be optimal: minimum number of moves. Any equal-cost
    route is acceptable.

Failure cases -- return (False, []) for all of these, never raise:
  - map_store.has_map() is False (no map published yet)
  - start or goal cell is out of bounds (map_store.in_bounds)
  - start or goal cell is blocked/unknown (not map_store.is_free)
  - open set exhausted with the goal never reached (unreachable)

Special case: if start_cell == goal_cell (and that cell is free/in-bounds),
return (True, [start_cell]) immediately without running search.

tolerance: accepted for signature compatibility with the /plan_path request,
but per spec "need not alter Project 1 planning" -- it is fine to ignore it
entirely (ignore the parameter, or use it as documented in plan_path_service.py
if you choose to support it as a stretch goal).
"""
from __future__ import annotations
from math import inf
from heap import MinHeap
from map_store import MapStore

Cell = tuple[int, int]

def manhattan_dist(n1: Cell,
                   n2: Cell):
  return abs(n1[0] - n2[0]) + abs(n1[1] - n2[1])

def plan_path(
    map_store: MapStore,
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    tolerance: float,
) -> tuple[bool, list[Cell]]:
    """Return (success, path_cells) where path_cells is ordered start -> goal.

    path_cells is a list of (cell_x, cell_y) tuples. Converting each cell to
    a world-coordinate PoseStamped-like pose (cell centers) is the caller's
    job (see plan_path_service.py) -- this function only deals in grid cells.
    """
    if not map_store.has_map():
      return (False, [])
    queue = MinHeap()
    start_world = map_store.world_to_cell(*start_world)
    goal_world = map_store.world_to_cell(*goal_world)
    if not (map_store.is_free(*goal_world) and map_store.is_free(*start_world)):
      return (False, [])
    if start_world == goal_world:
      return (True, [start_world])
    queue.push(0, start_world)
    lib = {start_world: [0, None, False]}
      
    
    while queue.__len__() > 0:
      priority, curr = queue.pop()
      if lib.get(curr) == None:
        lib[curr] = [inf, None, False]
      if lib[curr][2]:
        continue
      lib[curr][2] = True
      
      if manhattan_dist(curr, goal_world) == 1:
        lib[goal_world] = [0, curr, True]
        i = goal_world
        path = []
        while lib[i][1] != None:
          path.append(i)
          i = lib[i][1]
        path.append(i)
        return (True, path[::-1])
      
      def check_next(next):
        if map_store.is_free(*next):
          if lib.get(next) == None:
            lib[next] = [inf, None, False]
          tent_dist = lib[curr][0] + 1
          if tent_dist < lib[next][0]:
            lib[next][0] = tent_dist
            lib[next][1] = curr
            queue.push(tent_dist + manhattan_dist(next, goal_world), next)
      check_next((curr[0] + 1, curr[1]))
      check_next((curr[0] - 1, curr[1]))
      check_next((curr[0], curr[1] + 1))
      check_next((curr[0], curr[1] - 1))        
    return (False, [])
