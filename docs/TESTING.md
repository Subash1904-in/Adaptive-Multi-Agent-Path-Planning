# TESTING STANDARDS & STRATEGY

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Testing Frameworks:** `pytest`, `pytest-cov`, `pytest-django`, `pytest-asyncio`  
**Current Status:** Standards & Strategy Defined (Phase 01)

---

## 1. Testing Philosophy & Layering

The simulation platform enforces verifiable correctness across all 40 development phases. Every functional capability must be accompanied by automated tests before progression.

### Testing Levels
1. **Unit Tests (`tests/unit/`):**
   - Test isolated mathematical, geometric, and logical routines.
   - Examples: Kinematic equations, A* heuristic calculation, V2V packet serialization, collision box intersection.
   - Run in milliseconds without external dependencies or disk I/O.
2. **Integration Tests (`tests/integration/`):**
   - Test interactions across multiple subsystems.
   - Examples: Agent receiving a V2V hazard alert and invoking local rerouting; traffic signal phase change triggering vehicle deceleration; emergency vehicle corridor clearance.
3. **Scenario & Regression Tests (`tests/scenarios/`):**
   - End-to-end deterministic simulation runs with fixed seeds.
   - Standard benchmark scenarios:
     - 4-way unsignalized intersection with 8 agents.
     - Highway lane blockage incident with 15 agents.
     - Emergency ambulance priority transit with 20 yielding agents.
     - Signalized urban grid with pedestrian crosswalks.
4. **Benchmarking & Compliance (`tests/benchmarks/`):**
   - Automated evaluation tracking travel time, throughput, collision rates, and V2V packet delivery ratios.
   - Gymnasium environment compliance verification (`gymnasium.utils.env_checker.check_env`).

---

## 2. Directory Layout Blueprint

```text
tests/
├── conftest.py                # Global fixtures, deterministic seeds, test graphs
├── unit/
│   ├── test_domain_models.py  # Phase 3: Typed domain validation
│   ├── test_road_graph.py     # Phase 4: NetworkX topology
│   ├── test_osm_import.py     # Phase 5: OSMnx normalization & fallback
│   ├── test_planning.py       # Phase 6: A* and Dijkstra path calculations
│   ├── test_agents.py         # Phase 7: Kinematics and lifecycle
│   ├── test_clock.py          # Phase 8: Stepping, pause, resume, reset
│   ├── test_traffic_rules.py  # Phase 9: Speed limits, queues, intersections
│   ├── test_v2v_protocol.py   # Phase 11: Packet format, serialization, dedup
│   ├── test_v2v_range.py      # Phase 12: Proximity radius detection
│   ├── test_channel_noise.py  # Phase 14: Packet loss and latency
│   ├── test_rerouting.py      # Phase 15: Adaptive cost updates & rerouting
│   ├── test_collision.py      # Phase 16: Geometry, TTC, and safe braking
│   ├── test_pedestrians.py    # Phase 17: Crosswalk yielding and signal phases
│   ├── test_emergency.py      # Phase 18: Ambulance priority corridors
│   ├── test_ai_policy.py      # Phase 19: Weighted scoring decision policy
│   └── test_gym_env.py        # Phase 32: Gymnasium observation/action compliance
├── integration/
│   ├── test_agent_v2v.py      # Phase 13: Decentralized P2P coordination
│   ├── test_backend_checkpoint.py # Phase 20: Comprehensive backend checkpoint
│   ├── test_api_endpoints.py  # Phase 21: Django REST Framework API
│   └── test_websocket_stream.py # Phase 22: Django Channels telemetry stream
└── scenarios/
    ├── test_crossroad_scenario.py
    ├── test_highway_incident_scenario.py
    └── test_emergency_corridor_scenario.py
```

---

## 3. Determinism & Random Seeds

All tests must be strictly deterministic. Never call unseeded pseudorandom functions (`random.random()`, `numpy.random.rand()`).
In `conftest.py`:
```python
import pytest
import numpy as np
import random

@pytest.fixture(autouse=True)
def set_deterministic_seed():
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
```

---

## 4. Active Test Suites & Commands (Phase 06)

### 4.1 Running Active Tests
```bash
# Run entire backend test suite via pytest (257 passed)
pytest

# Run with full coverage report and 80% failure threshold
pytest --cov=backend/apps/core --cov-report=term-missing --cov-fail-under=80

# Run with verbose output
pytest -v

# Run specific routing test suites (Phase 06)
pytest backend/apps/core/tests/test_routing_costs_and_heuristics.py
pytest backend/apps/core/tests/test_routing_dijkstra.py
pytest backend/apps/core/tests/test_routing_astar.py
pytest backend/apps/core/tests/test_routing_planner.py

# Run specific OSM test suites (Phase 05)
pytest backend/apps/core/tests/test_osm_models_and_projector.py
pytest backend/apps/core/tests/test_osm_normalizer.py
pytest backend/apps/core/tests/test_osm_service_and_fallback.py

# Run specific graph test suites (Phase 04)
pytest backend/apps/core/tests/test_road_graph.py
pytest backend/apps/core/tests/test_city_generator.py

# Run specific domain test suites (Phase 03)
pytest backend/apps/core/tests/test_domain_values.py
pytest backend/apps/core/tests/test_domain_models.py
pytest backend/apps/core/tests/test_domain_serialization.py

# Run Ruff linting
ruff check backend

# Run Django system checks
python backend/manage.py check
```

### 4.2 Verified Test Coverage (Phase 06 — 257 Tests Passing, 96.76% Coverage)
- **Routing Costs, Traversability & Heuristics (`test_routing_costs_and_heuristics.py`, 18 passed):**
  - Edge cost calculation: scalar distance in meters, scalar travel time in seconds, validation of non-positive/non-finite length and speed limits.
  - Route metrics aggregation: summation of lengths and durations.
  - Traversability: filtering against closed edge IDs.
  - Heuristic admissibility: Euclidean distance lower-bound validation on graph edges, travel-time speed bounds, automatic safe $h=0$ fallback on inadmissible geometries, forced zero heuristic.
  - Routing models: `RoutingRequest` and `RoutingResult` validation invariants, string coercion, serialization.
- **Dijkstra Shortest Path Search (`test_routing_dijkstra.py`, 11 passed):**
  - Optimal paths: shortest distance vs fastest travel time trade-off (choosing shorter slow street vs longer high-speed highway).
  - One-way restrictions: traversal strictly obeys edge directionality.
  - Start == destination: zero-cost result, 0 expanded nodes, `route=None` preserving `Route` invariants.
  - Missing nodes: raising `RoutingNodeNotFoundError`.
  - Disconnected nodes: raising `NoPathFoundError`.
  - Closures: rerouting around closed edges; total blockage error reporting with closure count; direction-specific closures.
  - Determinism: repeatable sequence and metrics across multiple executions.
- **Custom A\* Pathfinding (`test_routing_astar.py`, 9 passed):**
  - Distance and travel-time optimal routing.
  - Optimality verification: exact cost equivalence between A* and Dijkstra across multi-node queries on synthetic city grids.
  - Directionality and one-way constraints.
  - Reopening and stale queue entries: robust priority queue pruning.
  - Inadmissible graph safe fallback: graceful $h=0$ execution.
  - Deterministic tie-breaking on symmetric grid paths.
- **Route Planner & Cross-Algorithm Comparison (`test_routing_planner.py`, 8 passed):**
  - High-level `RoutePlanner` facade and `find_route` convenience dispatcher.
  - Graph immutability: verifying input `RoadGraph` node and edge structures are completely unchanged by path searches.
  - Route continuity: verifying every consecutive node pair $(u, v)$ has a matching directed edge in `edge_ids`.
  - NetworkX reference comparison: matching ground-truth shortest path costs computed by `nx.shortest_path_length` for both distance and travel time.
- **Signal Controller & Cycle Timing (`test_signals_controller.py`, 40 passed):**
  - Parameter bounds validation for green, yellow, and red durations (strictly positive, finite, numeric).
  - Validation of initial phase enum and phase offsets ($0 \le t_{\text{offset}} < T$).
  - Strict deterministic cyclic state transitions: $\text{RED} \to \text{GREEN} \to \text{YELLOW} \to \text{RED}$.
  - Multi-cycle consistency across 100 periods without floating-point accumulation drift.
  - Phase offset shifts and exact interval boundary evaluations.
  - Query API calculation: `time_to_green_s` and `time_to_red_s` from RED, GREEN, and YELLOW phases.
  - Immutable `SignalSnapshot` creation and dictionary serialization.
  - Controller reset restoring $t=0.0$ state.
- **WorldState Signal Integration (`test_signals_world_integration.py`, 17 passed):**
  - Registration via `TrafficSignal` entity and pre-configured `TrafficSignalController`.
  - Duplicate signal ID rejection (`DuplicateSignalError`).
  - Duplicate intersection node rejection (`DuplicateSignalError`).
  - Non-existent node and non-existent incoming approach edge rejection (`InvalidIntersectionAssociationError`).
  - Approach edge terminating at a different node rejection (`InvalidIntersectionAssociationError`).
  - Foreign road graph instance rejection (`InvalidIntersectionAssociationError`).
  - Signal lookup by signal ID, intersection node ID, and incoming approach edge ID.
  - Signal removal with complete cleanup of internal lookup mappings.
  - Auto-registration of pre-existing signals from `RoadGraph` (e.g. synthetic city grid).
  - `WorldSnapshot` inclusion and world reset behavior.
- **SimulationEngine Signal Orchestration (`test_signals_engine_integration.py`, 7 passed):**
  - Single-step and multi-tick clock-synchronized signal progression.
  - `TickResult.signal_states` reporting at every completed tick.
  - Pause, resume, and single-step advancing signals by exactly one $\Delta t$.
  - Engine signal query delegation (`query_signal` and `query_signal_for_edge`).
  - Atomic rollback: simulated agent failure restores both vehicle kinematic states and signal phase/remaining time states to pre-tick baseline without clock advancement.
  - Multi-agent synthetic city execution over 100 ticks with 4 internal signals.
- **Simulation Clock & Precision (`test_simulation_clock.py`, 30 passed)**
- **WorldState Container & Baselines (`test_simulation_world.py`, 14 passed)**
- **SimulationEngine Coordinator & Atomic Rollback (`test_simulation_engine.py`, 12 passed)**
- **Simulation Determinism & Reproducibility (`test_simulation_determinism.py`, 3 passed)**
- **Kinematics Motion Integration & Models (`test_kinematics_motion.py`, 38 passed)**
- **Vehicle Agent Lifecycle & Route Following (`test_kinematics_vehicle_agent.py`, 19 passed)**
- **Kinematics Grid & OSM Integration (`test_kinematics_integration.py`, 4 passed)**
- **Routing Costs, Traversability & Heuristics (`test_routing_costs_and_heuristics.py`, 18 passed)**
- **Dijkstra Shortest Path Search (`test_routing_dijkstra.py`, 11 passed)**
- **Custom A\* Pathfinding (`test_routing_astar.py`, 9 passed)**
- **Route Planner & Cross-Algorithm Comparison (`test_routing_planner.py`, 8 passed)**
- **OSM Models, Bounds & Planar Projector (`test_osm_models_and_projector.py`, 31 passed)**
- **OSM Graph Normalization Pipeline (`test_osm_normalizer.py`, 12 passed)**
- **OSM Import Service & Fallback (`test_osm_service_and_fallback.py`, 17 passed)**
- **Road Network Graph Abstraction (`test_road_graph.py`, 25 passed)**
- **Deterministic Synthetic City Generator (`test_city_generator.py`, 16 passed)**
- **Domain Value Types (`test_domain_values.py`, 33 passed)**
- **Domain Models & Invariants (`test_domain_models.py`, 55 passed)**
- **Serialization & Codecs (`test_domain_serialization.py`, 17 passed)**
- **Core Health Endpoint (`test_health.py`, 5 passed)**

---

## 5. CI Rules & Testing Policy
- **GitHub Actions Authoritative Gate:** GitHub Actions CI is the primary test and acceptance environment.
- **Dependency Awareness:** CI verifies and logs runtime/dev dependencies (`osmnx`, `networkx`, `django`, `rest_framework`, `pytest_cov`).
- **Enforced Coverage Gate:** Pytest runs with `--cov=backend/apps/core --cov-report=term-missing --cov-report=xml --cov-fail-under=80`. Builds fail if line coverage drops below 80% (Current Phase 09: **97.19%** coverage across 441 passing tests).
- **Mandatory Hygiene & Integrity:** CI validates presence of all project documentation, phase reports (`docs/progress/PHASE_01.md` through `PHASE_09.md`), and scans for leaked secrets or prohibited binary artifacts.
- **Frontend Deferred Cleanly:** Frontend build/lint/typecheck job runs in Node 22.x, deferring execution cleanly until `frontend/package.json` is introduced.
- **No Blanket `continue-on-error`:** CI jobs must fail when any required check or test fails.
- **No Test Weakening:** Never weaken assertion thresholds solely to pass CI builds.
