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

## 4. Active Test Suites & Commands (Phase 05)

### 4.1 Running Active Tests
```bash
# Run entire backend test suite via pytest (211 passed)
pytest

# Run with verbose output
pytest -v

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

### 4.2 Verified Test Coverage (Phase 05 — 211 Tests Passing)
- **OSM Models, Bounds & Planar Projector (`test_osm_models_and_projector.py`, 31 passed):**
  - BoundingBox validation: range checks ($[-90, 90]$, $[-180, 180]$), non-numeric and non-finite rejection, strict ordering (`north > south`, `east > west`), span limits ($\le 0.25^\circ$).
  - BoundingBox conversion: `to_osmnx_bbox` converting to `(west, south, east, north)`, dictionary serialization and deserialization.
  - LocalPlanarProjector: origin projection to $(0.0, 0.0)$, Cartesian meters displacement matching geodesic formulas, bidirectional unproject round-trip restoration, invalid coordinate rejection.
  - Configuration & Results: `OSMImportConfig` mode/timeout validation, `OSMImportResult` serialization via `to_dict()`.
- **OSM Graph Normalization Pipeline (`test_osm_normalizer.py`, 12 passed):**
  - Node normalization: WGS84 coordinates to `GeoCoordinate` and `Position2D`, deterministic node IDs (`osm_node_{id}`), skipping malformed/uninitialized nodes.
  - Edge normalization: one-way vs. bidirectional road generation, forward and reverse directed edge separation, deterministic edge IDs (`osm_edge_{u}_{v}`).
  - Attribute extraction: speed limit parsing (km/h, mph, numeric strings, road class fallbacks), lane count parsing, length calculation fallback via Euclidean distance.
  - Invariant enforcement: skipping parallel edges in simple graph, skipping self-loops, skipping edges with nonexistent endpoints, raising `OSMEmptyGraphError` on empty input.
- **OSM Import Service & Fallback (`test_osm_service_and_fallback.py`, 17 passed):**
  - End-to-end orchestration: successful acquisition and normalization returning `source_type="osm"`.
  - Fallback policy: missing OSMnx, service unavailable, timeouts, and empty graphs fall back to synthetic grid when `allow_fallback=True`.
  - Strict error raising: raising `OSMNotInstalledError`, `OSMServiceUnavailableError`, `OSMTimeoutError`, or `OSMEmptyGraphError` when `allow_fallback=False`.
  - Bounds integrity: invalid bounding boxes raise `InvalidBoundingBoxError` immediately and are never disguised by synthetic fallback.
  - Fallback determinism: identical seeds produce bit-identical graph topology; custom `fallback_config` options are strictly respected.
  - Acquisition error classification: verifying timeout, connection error, and empty response mappings.
- **Road Network Graph Abstraction (`test_road_graph.py`, 25 passed):**
  - Node storage, directed edge storage, adjacency & neighborhoods, weak vs strong connectivity, traffic signals, topology validation.
- **Deterministic Synthetic City Generator (`test_city_generator.py`, 16 passed):**
  - Dimensions, spacing, speed limits, alternative paths, one-way grids, signal placement, deterministic seeded reproducibility.
- **Domain Value Types (`test_domain_values.py`, 33 passed):**
  - Position2D, GeoCoordinate, Dimensions2D validations and round-trips.
- **Domain Models & Invariants (`test_domain_models.py`, 55 passed):**
  - Invariant validation across all 10 domain models.
- **Serialization & Codecs (`test_domain_serialization.py`, 17 passed):**
  - Full round-trip equivalence across all domain entities and JSON error handling.
- **Core Health Endpoint (`test_health.py`, 5 passed):**
  - Regression: HTTP 200, Content-Type, payload schema, unauthenticated access, 404 for invalid paths.

---

## 5. CI Rules & Testing Policy
- **GitHub Actions Authoritative Gate:** GitHub Actions CI is the primary test and acceptance environment.
- **No Blanket `continue-on-error`:** CI jobs must fail when any required test fails.
- **No Test Weakening:** Never weaken assertion thresholds solely to pass CI builds.
- **Coverage Target:** Minimum line coverage threshold of 80% for `sim_engine/`.
