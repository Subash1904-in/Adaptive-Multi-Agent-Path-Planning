# TESTING STANDARDS & STRATEGY

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Frameworks:** `pytest`, `pytest-cov`, `pytest-django`, `pytest-asyncio`

---

## 1. Testing Philosophy

The simulation platform must maintain verifiable correctness across all 40 development phases. Every new capability must be accompanied by automated tests.

### Testing Levels
1. **Unit Tests (`tests/unit/`):**
   - Test isolated mathematical, geometric, and logical routines.
   - Examples: Kinematic equations, A* heuristic calculation, V2V packet serialization, collision box intersection.
   - Run in milliseconds without external dependencies or disk I/O.
2. **Integration Tests (`tests/integration/`):**
   - Test interaction between multiple subsystems.
   - Examples: Agent receiving a V2V hazard alert and invoking local rerouting; traffic signal phase change triggering vehicle deceleration; emergency vehicle corridor clearance.
3. **Scenario & Regression Tests (`tests/scenarios/`):**
   - End-to-end deterministic simulation runs with fixed seeds.
   - Verify that standard scenarios (e.g., 4-way unsignalized intersection with 8 agents, highway lane blockage with 12 agents) execute without crashes, invalid states, or unexpected collisions.
4. **Benchmarks (`sim_engine/benchmarks/`):**
   - Metric evaluations tracking travel time, throughput, collision rates, and V2V packet delivery ratios across algorithmic configurations.

---

## 2. Directory Layout

```text
tests/
├── conftest.py                # Global fixtures, deterministic seeds, test graphs
├── unit/
│   ├── test_kinematics.py     # Vehicle motion & update equations
│   ├── test_map_graph.py      # NetworkX road graph operations
│   ├── test_planning.py       # A* and Dijkstra path calculations
│   ├── test_v2v_protocol.py   # Packet formats and range detection
│   ├── test_collision.py      # Geometry and TTC calculations
│   └── test_traffic_lights.py # Signal controller state machines
├── integration/
│   ├── test_agent_v2v.py      # Multi-agent communication exchange
│   ├── test_rerouting.py      # Dynamic hazard alert reaction
│   ├── test_emergency.py      # Emergency corridor formation
│   └── test_websocket.py      # Telemetry frame streaming
└── scenarios/
    ├── test_crossroad_scenario.py
    └── test_highway_incident_scenario.py
```

---

## 3. Determinism & Random Seeds

All tests must be deterministic. Never use unseeded pseudorandom functions (`random.random()`, `numpy.random.rand()`).
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

## 4. Execution Commands

Once the testing suite is introduced in Phase 01+:

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

## 5. CI Rules & Best Practices
- Never use blanket `continue-on-error` to hide failing tests.
- Never weaken assertions solely to pass a build.
- Minimum line coverage target for core simulation logic: 80%.
