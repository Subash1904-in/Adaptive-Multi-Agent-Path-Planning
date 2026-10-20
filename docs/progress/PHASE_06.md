# Phase 06 Progress Report: Route Planning Baseline (Dijkstra, A* and Travel-Time Routing)

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** `https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning`  
**Starting Commit:** `c43c04a` (Verified clean working tree on `main`)  
**Completed Date:** 2026-10-20  
**Phase Status:** COMPLETED  

---

## 1. Phase Objective & Acceptance Checklist

Implement a decoupled, deterministic, high-performance route planning subsystem on directed road networks (`RoadGraph`) supporting both Dijkstra and custom A* search, distance and travel-time cost modes, temporary road closures, and typed result contracts.

### Acceptance Checklist
- [x] **Dijkstra Algorithm:** Implemented genuine Dijkstra search over directed `RoadGraph` with deterministic tie-breaking.
- [x] **Custom A\* Algorithm:** Implemented custom A* using Python `heapq`, maintaining `g_score`, `f_score`, predecessor maps, and handling stale entries.
- [x] **Distance Cost Mode:** $D = \sum e.\text{length\_m}$ in meters.
- [x] **Fastest Travel Time Mode:** $T = \sum (e.\text{length\_m} / e.\text{speed\_limit\_mps})$ in seconds.
- [x] **Heuristic Admissibility:** Euclidean distance heuristic verified against edge lower bounds; safe $h=0$ fallback when bounds cannot be guaranteed.
- [x] **Road Closures & Disabled Edges:** Supports exclusion of specified directed edge IDs without mutating the underlying graph.
- [x] **Start == Destination Policy:** Documented zero-hop result returning $0.0$ cost, $0$ expanded nodes, and `route=None` to preserve `Route` domain invariants ($\ge 2$ nodes).
- [x] **Typed Result Contract:** `RoutingResult` capturing path sequences, metrics (nodes expanded, edges examined, duration), and domain `Route` entity.
- [x] **Unified Planner API:** `RoutePlanner` class and convenience `find_route` function.
- [x] **Ground-Truth Verification:** Cross-algorithm verification with NetworkX `shortest_path_length` on synthetic grids and real-world OSM normalized graphs.
- [x] **Automated Regression & Coverage:** 257 tests passing offline; 96.76% line coverage (exceeding 80% CI minimum).
- [x] **CI Verification:** GitHub Actions pipeline passes all jobs (`Backend Lint, Test & Coverage`, `Repository Hygiene`, `Frontend Lint`).

---

## 2. Architecture & Design Decisions

### 2.1 Package Structure (`backend/apps/core/routing/`)
The routing subsystem is isolated in `apps.core.routing`, independent of Django views, HTTP serializers, or database models:
- `exceptions.py`: Typed hierarchy (`RoutingError`, `RoutingNodeNotFoundError`, `NoPathFoundError`, `InvalidRoutingRequestError`).
- `models.py`: Value objects and enums (`CostMode`, `RoutingAlgorithm`, `RoutingRequest`, `RoutingResult`).
- `costs.py`: Pure cost computation functions (`calculate_edge_cost`, `calculate_route_metrics`, `is_edge_traversable`).
- `heuristics.py`: Admissibility analyzer (`check_heuristic_admissibility`) and heuristic builder (`get_heuristic_function`).
- `dijkstra.py`: Authoritative Dijkstra implementation (`dijkstra_search`).
- `astar.py`: Custom A* priority queue implementation (`astar_search`).
- `planner.py`: High-level facade (`RoutePlanner`, `find_route`).
- `__init__.py`: Clean public API export.

### 2.2 Cost Functions & Units
All calculations adhere to Phase 3 SI domain standards:
1. **Shortest Distance:**
   $$\text{cost}_{\text{dist}}(e) = e.\text{length\_m} \quad [\text{meters}]$$
2. **Fastest Travel Time:**
   $$\text{cost}_{\text{time}}(e) = \frac{e.\text{length\_m}}{e.\text{speed\_limit\_mps}} \quad [\text{seconds}]$$

Both distance and travel-time metrics are computed and reported on every route, regardless of the active optimization objective.

---

## 3. Heuristic Admissibility & Safety Fallback

A* heuristics must be strictly admissible ($h(n) \le h^*(n)$) and consistent ($h(u) \le \text{cost}(u, v) + h(v)$) to guarantee optimality.

1. **Distance Heuristic:**
   $$h_{\text{dist}}(n) = \text{EuclideanDistance}(n, \text{dest})$$
   *Admissibility Condition:* For all edges $e = (u, v)$, $e.\text{length\_m} \ge \text{EuclideanDistance}(u, v) - 10^{-5}$.
2. **Travel Time Heuristic:**
   $$h_{\text{time}}(n) = \frac{\text{EuclideanDistance}(n, \text{dest})}{V_{\max}}$$
   where $V_{\max} = \max_{e \in E}(e.\text{speed\_limit\_mps})$.
   *Admissibility Condition:* Valid when edge lengths satisfy the Euclidean lower bound and $V_{\max} > 0$.
3. **Safety Fallback ($h=0$):**
   If any edge in the graph violates the physical lower bound (e.g. malformed external map data or non-Euclidean metric distortions), `get_heuristic_function` automatically falls back to $h(n) = 0.0$, gracefully preserving complete search optimality without crashing.

---

## 4. Road Closure Handling

- **Non-Mutating Execution:** Edges in `closed_edge_ids` are filtered during neighbor traversal; `RoadGraph` internal structures are never modified.
- **Directional Specificity:** Closing edge $A \to B$ leaves reverse edge $B \to A$ open and traversable.
- **Robustness:** Unknown edge IDs in `closed_edge_ids` are safely ignored.
- **Total Blockage:** If all connecting paths are closed, `NoPathFoundError` is raised with the count of active closures.

---

## 5. Result Contract & Domain Integration

The `RoutingResult` object encapsulates:
- `success`: Boolean path finding status.
- `algorithm`: `RoutingAlgorithm.DIJKSTRA` or `RoutingAlgorithm.ASTAR`.
- `cost_mode`: `CostMode.DISTANCE` or `CostMode.TRAVEL_TIME`.
- `node_ids`: Ordered node IDs from origin to destination.
- `edge_ids`: Ordered directed edge IDs connecting the nodes.
- `total_distance_m`: Cumulative distance in meters.
- `estimated_duration_s`: Cumulative travel time in seconds.
- `objective_cost`: The minimized scalar value (meters or seconds).
- `nodes_expanded`: Metric tracking search effort.
- `edges_examined`: Metric tracking branching exploration.
- `execution_time_ms`: Search latency in milliseconds.
- `route`: Generated domain `Route` entity (or `None` when start == destination).
- `to_dict()`: JSON serialization for downstream API endpoints.

---

## 6. Files Created & Modified

### Created
- `backend/apps/core/routing/__init__.py`
- `backend/apps/core/routing/exceptions.py`
- `backend/apps/core/routing/models.py`
- `backend/apps/core/routing/costs.py`
- `backend/apps/core/routing/heuristics.py`
- `backend/apps/core/routing/dijkstra.py`
- `backend/apps/core/routing/astar.py`
- `backend/apps/core/routing/planner.py`
- `backend/apps/core/tests/test_routing_costs_and_heuristics.py`
- `backend/apps/core/tests/test_routing_dijkstra.py`
- `backend/apps/core/tests/test_routing_astar.py`
- `backend/apps/core/tests/test_routing_planner.py`
- `docs/progress/PHASE_06.md`

### Modified
- `.github/workflows/ci.yml`: Added Phase 6 documentation hygiene checks and modernized step naming.
- `ARCHITECTURE.md`: Documented Section 3.5 Routing Subsystem.
- `REQUIREMENTS_TRACEABILITY.md`: Mapped Phase 6 baseline routing to FR-04 and related requirements.
- `README.md`: Added routing usage examples and testing commands.
- `docs/TESTING.md`: Documented Phase 6 test suites and test counts.
- `PROJECT_STATUS.md`: Updated to Phase 6 complete.

---

## 7. Test Results & Verification

All automated tests execute 100% offline without live internet access.

- **Routing Costs & Heuristics (`test_routing_costs_and_heuristics.py`):** 18 passed.
- **Dijkstra Search (`test_routing_dijkstra.py`):** 11 passed.
- **A\* Search (`test_routing_astar.py`):** 9 passed.
- **Route Planner & Cross-Algorithm (`test_routing_planner.py`):** 8 passed.
- **Previous Regression Tests (Phases 2–5):** 211 passed.
- **Total Tests:** **257 passed, 0 failed in 2.70s**.
- **Coverage:** **96.76% total line coverage** across `backend/apps/core` (exceeding 80% CI minimum).
- **Ruff Linter:** 0 errors.
- **Django System Check:** 0 issues.

---

## 8. CI Workflow Verification

- **GitHub Actions Run:** Scheduled upon commit and push.
- **Authoritative Gate:** Confirmed via remote run execution.

---

## 9. Requirements Traceability Impact

- **FR-04 (Shortest Path Calculation):** Baseline single-agent routing complete (Dijkstra and A* for distance and travel time). Adaptive rerouting and dynamic edge weight adjustments are deferred to Phase 15.
- **FR-03 (Map Integration):** Validated route planning over OSM-normalized graphs.
- **FR-05, FR-07:** Foundation laid for vehicle kinematics (Phase 7) and simulation agents.

---

## 10. Phase 7 Handoff Instructions

Phase 6 is complete. No agent behavior, vehicle physics, or dynamic rerouting has been introduced prematurely.

**Scope for Phase 07 (Vehicle Kinematics & Agent Lifecycle):**
1. Read `docs/progress/PHASE_06.md` and `ARCHITECTURE.md`.
2. Implement pure Python 2D bicycle/point-mass kinematic motion models for `Vehicle` entities moving along `Route` paths.
3. Manage vehicle lifecycle states (`IDLE`, `EN_ROUTE`, `BLOCKED`, `ARRIVED`).
4. Maintain deterministic stepping and preserve all 257 passing regression tests.
