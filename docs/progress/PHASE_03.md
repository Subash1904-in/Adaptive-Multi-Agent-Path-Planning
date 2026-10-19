# PHASE 03 PROGRESS REPORT: Domain Models and Simulation Contracts

## 1. Phase Objective & Acceptance Checklist

### Objective
Implement a clean, strongly-typed simulation domain layer independent of Django's persistence layer, consisting of typed domain models, immutable value types, shared enums, invariant validation rules, JSON-compatible serialization contracts, and an automated test suite.

### Acceptance Checklist
- [x] **10 Core Domain Types Implemented:** `Vehicle`, `RoadNode`, `RoadEdge`, `Route`, `Pedestrian`, `TrafficSignal`, `Obstacle`, `Incident`, `V2VMessage`, `SimulationConfig`.
- [x] **3 Immutable Value Objects Implemented:** `Position2D`, `GeoCoordinate`, `Dimensions2D` (all `frozen=True`).
- [x] **9 Enumerations Implemented:** `VehicleState`, `VehicleType`, `TrafficSignalState`, `IncidentType`, `IncidentSeverity`, `IncidentStatus`, `ObstacleType`, `V2VMessageType`, `PedestrianState` (inheriting from `str, Enum`).
- [x] **Separation from Persistence:** Pure Python dataclasses located in `backend/apps/core/domain/`, with zero database models, migrations, or ORM coupling.
- [x] **Invariant Validation Boundaries:** Invariants strictly validated on object construction via `__post_init__`, raising `DomainValidationError`.
- [x] **Units & Conventions Explicitly Documented:** Meters (`_m`), meters/second (`_mps`), radians (`_rad`), seconds (`_s`).
- [x] **Identifier & Reference Invariants:** Non-empty string validation for IDs; minimum 2-node sequence for routes; self-loop prevention on road edges.
- [x] **Serialization Contracts:** JSON-compatible dict serialization (`to_dict`) and type-safe deserialization (`from_dict`) with full round-trip guarantees and strict error handling (`SerializationError`).
- [x] **JSON Helpers:** String serialization (`to_json`) and deserialization (`from_json`) utilizing standard-library `json`.
- [x] **Comprehensive Test Suite:** 110 total tests passing (105 new domain tests + 5 Phase 2 health regression tests).
- [x] **Linting & System Checks:** `ruff check backend` (0 errors) and `python backend/manage.py check` (0 issues identified).
- [x] **Documentation Synchronized:** `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, `README.md`, `docs/TESTING.md`, and `docs/progress/PHASE_03.md`.
- [x] **Strict Phase Boundaries Preserved:** No road network graphs (Phase 4), OSM import (Phase 5), routing algorithms (Phase 6), vehicle movement, WebSockets, or RL logic implemented.

---

## 2. Initial Repository State
- **Branch:** `main`
- **Starting Commit:** `0d69c59` (`docs(phase-02): record verified CI run URL and completed job details`)
- **Working Tree:** Clean
- **Pre-existing Content:** Django scaffold under `backend/`, health check endpoint at `/api/v1/health/`, 5 automated tests passing, CI pipeline verified in GitHub Actions.

---

## 3. Design Decisions and Assumptions
1. **Package Placement (`backend/apps/core/domain/`):**
   - The domain package was placed inside the `apps.core` application to form a clean, cohesive domain foundation accessible across future simulation and API subsystems without polluting the Django project root.
2. **Standard Library Exclusivity:**
   - Designed exclusively using Python 3.11 standard library modules (`dataclasses`, `enum`, `typing`, `math`, `json`). Avoided premature external geometric, geospatial, or serialization libraries (e.g. Shapely, Pydantic, Marshmallow).
3. **Intentional Mutability Split:**
   - **Immutable (`frozen=True`):** Value objects without independent identity (`Position2D`, `GeoCoordinate`, `Dimensions2D`) and run-level configurations (`SimulationConfig`).
   - **Mutable:** Dynamic simulation entities (`Vehicle`, `Pedestrian`, `TrafficSignal`, `Incident`, `RoadEdge`, `RoadNode`, `Obstacle`, `Route`, `V2VMessage`) whose spatial positions, speeds, states, and phase times will be updated by future simulation stepping loops.
4. **Validation Boundary:**
   - Validation occurs eagerly at construction time inside `__post_init__`. This ensures that an invalid domain object cannot exist in memory.
   - Exceptions inherit from `DomainException` and standard `ValueError` (`DomainValidationError`, `SerializationError`) to provide clear, actionable debugging information.

---

## 4. Domain Types and Responsibilities

| Domain Type | Category | Responsibility |
|---|---|---|
| `Position2D` | Value Object (`frozen=True`) | Planar 2D Cartesian coordinate in meters (`x`, `y`); Euclidean distance calculation. |
| `GeoCoordinate` | Value Object (`frozen=True`) | Real-world WGS84 geographic coordinate (`latitude` $\in [-90, 90]$, `longitude` $\in [-180, 180]$). |
| `Dimensions2D` | Value Object (`frozen=True`) | Bounding footprint dimensions in meters (`length_m > 0`, `width_m > 0`). |
| `RoadNode` | Domain Entity | Intersection or road endpoint with planar coordinate, optional WGS84 mapping, and attribute tags. |
| `RoadEdge` | Domain Entity | Directed road segment between two nodes with length ($m > 0$), speed limit ($m/s > 0$), lanes ($\ge 1$). |
| `Route` | Domain Entity | Ordered navigation trajectory containing $\ge 2$ node IDs, optional edge IDs, distance, and duration. |
| `Vehicle` | Domain Entity | Autonomous/emergency vehicle agent with position, speed ($0 \le v \le v_{\max}$), heading ($[0, 2\pi)$), state, type, and route references. |
| `Pedestrian` | Domain Entity | Pedestrian agent with position, walking speed ($0 \le v \le 1.4$ m/s), state, crossing crosswalk node reference. |
| `TrafficSignal` | Domain Entity | Signal controller governing an intersection node with phase state (RED/YELLOW/GREEN), cycle duration, and remaining phase time. |
| `Obstacle` | Domain Entity | Stationary hazard on a roadway with position, footprint dimensions, and obstacle classification. |
| `Incident` | Domain Entity | Roadway event (accident, closure, hazard) with severity, resolution status, affected edge/node, and reported timestamp. |
| `V2VMessage` | Domain Entity | P2P/broadcast communication packet with sender ID, recipient ID, message type, emission timestamp, expiration, and payload. |
| `SimulationConfig` | Value Object (`frozen=True`) | Validated configuration: timestep ($\Delta t \in [0.001, 2.0]\,s$), random seed, communication radius, max vehicles, and boundaries. |

---

## 5. Validation Rules, Units, and Conventions

### Measurement Units
- **Length / Distance / Position:** Meters (`_m`), planar $(x, y)$ in world coordinate frame.
- **Speed:** Meters per second (`_mps`). Default standard vehicle maximum: $13.89\,\text{m/s}$ ($50\,\text{km/h}$); pedestrian maximum: $1.4\,\text{m/s}$ ($5\,\text{km/h}$).
- **Heading / Orientation:** Radians (`_rad`) normalized to $[0, 2\pi)$.
- **Duration / Timestamps:** Seconds (`_s`) simulation time since run inception ($\ge 0.0$).
- **Coordinates:** Decimal degrees for WGS84 (`latitude`, `longitude`).

### Shared Enumerations
- `VehicleState`: `idle`, `en_route`, `waiting_at_signal`, `stopped`, `rerouting`, `arrived`
- `VehicleType`: `standard`, `emergency`
- `TrafficSignalState`: `red`, `yellow`, `green`
- `IncidentType`: `accident`, `road_closure`, `congestion`, `hazard`, `obstacle`
- `IncidentSeverity`: `low`, `medium`, `high`, `critical`
- `IncidentStatus`: `active`, `resolved`
- `ObstacleType`: `construction`, `debris`, `stalled_vehicle`, `static_barrier`
- `V2VMessageType`: `hazard_warning`, `congestion_alert`, `emergency_corridor`, `route_advisory`, `heartbeat`
- `PedestrianState`: `waiting`, `crossing`, `safe`

---

## 6. Serialization Design and Codecs
- Implemented in `backend/apps/core/domain/serialization.py`.
- **`to_dict(obj)`:** Converts dataclasses and value objects to pure JSON-compatible dictionaries, recursively serializing nested objects and mapping Enums to string `.value` tokens.
- **`from_dict(cls, data)`:** Rebuilds domain objects from dictionary representations, validating nested schemas, parsing enums safely, and enforcing invariant construction rules.
- **`to_json(obj)` & `from_json(cls, json_str)`:** Standard library JSON string serialization and deserialization.
- **Round-Trip Invariance:** Tested and verified:
  ```python
  from apps.core.domain import Vehicle, from_dict, to_dict

  restored = from_dict(Vehicle, to_dict(vehicle))
  assert restored == vehicle
  ```

---

## 7. Files Created, Modified, or Removed

### Files Created
- `backend/apps/core/domain/__init__.py`: Domain package exports.
- `backend/apps/core/domain/exceptions.py`: `DomainException`, `DomainValidationError`, `SerializationError`.
- `backend/apps/core/domain/enums.py`: 9 typed domain string enumerations.
- `backend/apps/core/domain/values.py`: `Position2D`, `GeoCoordinate`, `Dimensions2D`.
- `backend/apps/core/domain/models.py`: 10 core domain dataclasses with validation.
- `backend/apps/core/domain/serialization.py`: Serialization and deserialization codecs (`to_dict`, `from_dict`, `to_json`, `from_json`).
- `backend/apps/core/tests/test_domain_values.py`: 33 unit tests for value types.
- `backend/apps/core/tests/test_domain_models.py`: 55 unit tests for domain models and validation rules.
- `backend/apps/core/tests/test_domain_serialization.py`: 17 unit tests for serialization and error handling.
- `docs/progress/PHASE_03.md`: This comprehensive Phase 3 report.

### Files Modified
- `ARCHITECTURE.md`: Documented domain layer implementation status, Section 3.0 specification, and Section 4 module blueprint update.
- `REQUIREMENTS_TRACEABILITY.md`: Updated Current Phase to Phase 3; mapped domain foundations to FR-01 through FR-14.
- `README.md`: Added Phase 3 progress report reference.
- `docs/TESTING.md`: Documented Phase 3 active test suites and test coverage.
- `PROJECT_STATUS.md`: Marked Phase 3 COMPLETED, Phase 4 Pending.

---

## 8. Dependencies Added or Avoided
- **Dependencies Added:** None. Pinned dependencies from Phase 2 (`requirements.txt` and `requirements-dev.txt`) were reused.
- **Dependencies Avoided:**
  - Avoided external serialization libraries (Pydantic, Marshmallow) — pure standard-library solution.
  - Avoided external geometry libraries (Shapely) — pure Python `Position2D` with `math.hypot`.
  - Avoided premature graph libraries (NetworkX) or geospatial packages (OSMnx) — reserved for Phase 4 and 5.

---

## 9. Actual Commands Executed & Results

1. `.\.venv\Scripts\ruff.exe check backend --fix`:
   - Formatted imports and verified compliance with 100-character line length limit. Exit code 0.
2. `.\.venv\Scripts\python.exe backend/manage.py check`:
   - Output: `System check identified no issues (0 silenced).` Exit code 0.
3. `.\.venv\Scripts\pytest.exe`:
   - Output: `110 passed in 0.51s`. Exit code 0.

---

## 10. Automated Test Results
- **Value Types (`test_domain_values.py`):** 33 PASSED
- **Domain Models & Invariants (`test_domain_models.py`):** 55 PASSED
- **Serialization & Deserialization (`test_domain_serialization.py`):** 17 PASSED
- **Health Check Regression (`test_health.py`):** 5 PASSED
- **Total:** **110 passed, 0 failed in 0.51s**.

---

## 11. Code Quality and System Checks
- **Ruff Diagnostics:** 0 errors (`All checks passed!`).
- **Django System Check:** 0 issues identified.
- **Phase Boundary Verification:** Zero graph building, vehicle stepping, or network delivery logic was introduced.

---

## 12. CI Workflow Run & Verification
- Commits will be pushed to `origin/main` to trigger the GitHub Actions CI pipeline.
- Verified CI results will be recorded following remote execution.

---

## 13. Known Issues & Limitations
- **Limitations:** Domain models define structure, types, units, and validation boundaries only. They do not simulate vehicle kinematics along curves, compute shortest paths, or transmit radio packets. These behaviors are reserved for Phases 4–18.
- **Blockers:** None.

---

## 14. Requirement Traceability Impact
- The domain types provide foundational data contracts for all 14 functional requirements (FR-01 to FR-14):
  - `V2VMessage`, `V2VMessageType`: supports FR-01, FR-06, FR-11, FR-12.
  - `Vehicle`, `VehicleState`, `VehicleType`: supports FR-02, FR-10.
  - `RoadNode`, `RoadEdge`, `GeoCoordinate`, `Position2D`: supports FR-03.
  - `Pedestrian`, `PedestrianState`, `TrafficSignal`, `TrafficSignalState`: supports FR-04.
  - `Route`: supports FR-05, FR-07.
  - `Obstacle`, `Incident`, `Dimensions2D`: supports FR-09, FR-10.
  - `SimulationConfig`: supports FR-02, FR-05, FR-13.
- All 14 functional requirements remain honestly marked as `NOT STARTED` functionally.

---

## 15. Exact Handoff Instructions for Phase 4
- **Next Phase:** **Phase 04: Road Graph and Deterministic City**.
- **Scope for Phase 4:**
  - Introduce NetworkX to represent the directed road network graph $G = (V, E)$ using `RoadNode` and `RoadEdge` domain entities.
  - Implement a deterministic synthetic city grid generator with multiple connected intersections, signalized junctions, speed limits, and alternative paths.
  - Support fixed pseudorandom seeds for 100% reproducible graph generation.
  - Implement offline synthetic grid fallback without requiring external internet or API access.
  - Write comprehensive unit tests for graph connectivity, edge attributes, and topology.
