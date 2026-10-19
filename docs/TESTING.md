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

## 4. Execution Commands (Phase 02+)

```bash
# Run all fast unit and integration tests
pytest -v

# Run with coverage report
pytest -v --cov=sim_engine --cov-report=term-missing --cov-report=xml

# Run specific subsystem tests
pytest tests/unit/test_v2v_protocol.py

# Run only scenario regression tests
pytest tests/scenarios/
```

---

## 5. CI Rules & Testing Policy
- **No Blanket `continue-on-error`:** CI jobs must fail when any required test fails.
- **No Test Weakening:** Never weaken assertion thresholds solely to pass CI builds.
- **Coverage Target:** Minimum line coverage threshold of 80% for `sim_engine/`.
