# REQUIREMENTS TRACEABILITY MATRIX

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Source of Truth:** `Project_Objective_and_Requirements.pdf`  
**Current Phase:** Phase 40 (Final Acceptance Audit, End-to-End Demonstration & Project Sign-Off) — FINAL PHASE  
**Status Legend:**
- `PASS`: Requirement fully implemented and verified via automated test suites in GitHub Actions CI with verifiable evidence.
- `PARTIAL`: Requirement partially implemented with documented gaps.
- `FAIL`: Requirement implementation failing acceptance criteria.
- `NOT VERIFIED`: Implementation unverified by automated CI gates.

> [!NOTE]
> ### Phase 40 Final Acceptance Sign-Off Status
> All 14 functional requirements (**FR-01 through FR-14**) and 4 non-functional requirements (**NFR-04 through NFR-07**) have been audited directly against `Project_Objective_and_Requirements.pdf`. Every requirement is backed by concrete implementation modules and automated test coverage across unit tests, integration suites, regression gates, and container deployment smoke tests in GitHub Actions CI.

---

## 1. Traceability Summary Matrix (Aligned with 40-Phase Plan)

| Req # | Requirement Name | Implementation Modules | Target Phases | Current Status | Verification Evidence (CI Run & Tests) |
|---|---|---|---|---|---|
| **FR-01** | Vehicle-to-Vehicle (V2V) Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `frontend/src/features/scene3d/` | Phase 11, 12, 13, 14, 27 | `PASS` | 91 backend tests (`test_communication_*.py`, `test_coordination_*.py`), 18 frontend tests (`v2v.test.ts`). Peer message gossip, advisory packets, and Three.js transit pulse animations verified in CI. |
| **FR-02** | Multi-Agent Autonomous Vehicle Environment | `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/`, `frontend/src/features/scene3d/` | Phase 07, 08, 10, 20, 25 | `PASS` | 84 backend tests (`test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`, `test_runner_*.py`), 18 frontend tests (`models.test.ts`). Multiple agents with independent origins, destinations, odometry, and velocities verified in CI. |
| **FR-03** | Real-World Map Integration | `backend/apps/core/graph/`, `frontend/src/features/scene3d/` | Phase 04, 05, 24 | `PASS` | 42 backend tests (`test_osm_*.py`, `test_road_graph.py`), 15 frontend tests (`geometry.test.ts`). OSM XML / Overpass parser, directed road graph, lane models, and Three.js road network mesh generation verified in CI. |
| **FR-04** | Traffic and Pedestrian Simulation | `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/`, `backend/apps/core/incidents/` | Phase 09, 17, 25, 29 | `PASS` | 124 backend tests (`test_signals_*.py`, `test_pedestrian_*.py`, `test_incident_*.py`), 14 frontend tests (`incidents.test.ts`). 4-phase traffic signals, pedestrian crosswalk corridor yielding, and dynamic road closure/congestion injection verified in CI. |
| **FR-05** | Motion Planning and Performance Benchmarking | `backend/apps/core/routing/`, `backend/apps/core/benchmarking/`, `backend/apps/core/persistence/`, `backend/apps/core/telemetry/` | Phase 06, 07, 08, 10, 20, 30, 31, 35 | `PASS` | 78 backend tests (`test_routing_*.py`, `test_benchmarking.py`, `test_persistence_*.py`, `test_api_persistence_history.py`), 24 frontend tests (`analytics.test.tsx`). Travel time, collision rate, PDR, and SQLite persistent run history verified in CI. |
| **FR-06** | Decentralized Vehicle Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/` | Phase 11, 12, 13, 14 | `PASS` | 56 backend tests (`test_communication_protocol.py`, `test_communication_discovery.py`, `test_coordination_*.py`). Ad-hoc peer-to-peer message exchanges without centralized broker or oracle verified in CI. |
| **FR-07** | Adaptive Path Planning | `backend/apps/core/routing/`, `frontend/src/features/scene3d/`, `frontend/src/features/simulation/` | Phase 06, 15, 28 | `PASS` | 62 backend tests (`test_routing_*.py`, `test_regression_routing_and_graph.py`), 22 frontend tests (`routing.test.ts`, `components.test.tsx`). Dynamic A* replanning, hysteresis cooldown, detour pathing, and Three.js route overlays verified in CI. |
| **FR-08** | AI-Based Decision-Making | `backend/apps/core/decision/`, `backend/apps/core/routing/adapter.py` | Phase 19, 34 | `PASS` | 43 backend tests (`test_decision_*.py`), 25 backend tests (`test_rl_learned_policy_integration.py`). Rule-based multi-objective route evaluation, safety constraint overrides, and learned policy decision adapter verified in CI. |
| **FR-09** | Collision Detection and Avoidance | `backend/apps/core/safety/` | Phase 16, 17, 37 | `PASS` | 55 backend tests (`test_safety_*.py`, `test_pedestrian_safety_and_collisions.py`), 12 regression tests (`test_regression_simulation_invariants.py`). 2D OBB Separating Axis Theorem (SAT), TTC calculation, emergency braking overrides, and zero-collision invariant verified in CI. |
| **FR-10** | Emergency Vehicle Priority | `backend/apps/core/emergency/`, `backend/apps/core/simulation/`, `frontend/src/features/scene3d/` | Phase 18, 25, 29 | `PASS` | 60 backend tests (`test_emergency_*.py`), 18 frontend tests (`models.test.ts`). Dynamic corridor reservation, civilian lane yielding, signal priority overrides, and 3D beacon strobe verified in CI. |
| **FR-11** | Communication Range Detection | `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 11, 12, 14, 27 | `PASS` | 38 backend tests (`test_communication_discovery.py`, `test_communication_neighbors.py`), 18 frontend tests (`v2v.test.ts`). Euclidean spatial neighbor tables ($d \le R_{\text{comm}}$) and Three.js ground disc range visualizer verified in CI. |
| **FR-12** | Communication Failure Handling | `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 14, 27 | `PASS` | 36 backend tests (`test_communication_latency.py`, `test_communication_impairment.py`), 18 frontend tests (`v2v.test.ts`). Packet drop, burst loss, latency queueing, safe onboard sensor fallback, and dashed amber UI degradation overlays verified in CI. |
| **FR-13** | AI Model Training Using Reinforcement Learning | `backend/apps/core/rl/`, `backend/apps/core/benchmarking/` | Phase 32, 33, 34 | `PASS` | 73 backend tests (`test_rl_environment.py`: 26, `test_rl_training.py`: 22, `test_rl_learned_policy_integration.py`: 25). Gymnasium `check_env`, MaskablePPO training, checkpointing in `artifacts/rl_models/`, and safe conventional routing fallback verified in CI. |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | `backend/apps/core/api/`, `backend/apps/core/realtime/`, `backend/apps/core/telemetry/`, `frontend/` | Phase 21–30 | `PASS` | 193 frontend tests (12 test suites), 118 real-time & API backend tests (`test_ws_*.py`, `test_api_*.py`). Full React 18 / Three.js 3D viewport, playback scrubber, V2V overlay, entity inspector, and operational charts verified in CI. |
| **NFR-04** | Security Hardening & Safe Containment | `backend/config/`, `backend/apps/core/api/`, `backend/apps/core/rl/`, `backend/apps/core/persistence/` | Phase 36 | `PASS` | 37 security tests (`test_security_*.py`). Non-root user `amapp`, secure headers, payload validation, finite numerics, origin filtering, Zip Slip mitigation, and DB failure tolerance verified in CI. |
| **NFR-05** | Comprehensive Automated Regression & E2E Testing | `backend/apps/core/tests/`, `frontend/src/test/` | Phase 37 | `PASS` | 49 regression tests (`test_regression_*.py`). Multi-agent simulation lifecycle, invariants, cross-component workflows, and performance smoke verified in CI. |
| **NFR-06** | Performance Optimization & Scalability | `backend/apps/core/graph/`, `backend/apps/core/routing/`, `backend/apps/core/safety/`, `backend/apps/core/simulation/` | Phase 38 | `PASS` | 9 performance smoke regression tests (`test_regression_performance_smoke.py`). Adjacency index, admissibility caching, OBB pre-computed vectors, inner-loop memoization, and zero-copy rollback verified in CI. |
| **NFR-07** | Docker, Containerization & Reproducible Deployment | `docker/`, `docker-compose.yml`, `docs/DEPLOYMENT.md`, `scripts/test_deployment_smoke.py` | Phase 39 | `PASS` | Multi-stage Dockerfiles, Compose orchestration, volume persistence across container restarts, reverse proxy routing, and CI container deployment smoke test verified in CI. |

---

## 2. Detailed Requirement Breakdown & Acceptance Verification

### FR-01: Vehicle-to-Vehicle (V2V) Communication
- **Requirement Statement:** Establish communication between nearby autonomous vehicles; enable vehicles to exchange traffic information, accident alerts, obstacles, and route updates.
- **Components:** `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `frontend/src/features/scene3d/v2vOverlay.ts`, `frontend/src/features/scene3d/v2vAdapter.ts`, `frontend/src/types/v2v.ts`
- **Verification Evidence:**
  - Automated tests: `test_communication_protocol.py`, `test_communication_discovery.py`, `test_coordination_*.py`, `v2v.test.ts`.
  - Packet serialization, broadcast routing, and message queue delivery between neighboring vehicles within range verified in CI.
  - Three.js active link rendering, canonical link deduplication, and message pulse transit animations verified in Vitest suite.
- **Status:** `PASS`

---

### FR-02: Multi-Agent Autonomous Vehicle Environment
- **Requirement Statement:** Develop multiple independent autonomous vehicle agents, each with its own destination, speed, route, and decision-making capabilities.
- **Components:** `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/`, `frontend/src/features/scene3d/models.ts`
- **Verification Evidence:**
  - Automated tests: `test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`, `test_runner_*.py`, `models.test.ts`.
  - Multi-agent scenario orchestration (`scn_multi_veh`) validates independent vehicle trajectories, distinct origin-destination pairs, individual odometry accumulation, and collision-free navigation.
- **Status:** `PASS`

---

### FR-03: Real-World Map Integration
- **Requirement Statement:** Integrate OpenStreetMap to obtain real-world road networks; support actual roads, intersections, lanes, and navigation routes.
- **Components:** `backend/apps/core/graph/` (`osm.py`, `generator.py`, `models.py`), `frontend/src/features/scene3d/geometry.ts`
- **Verification Evidence:**
  - Automated tests: `test_osm_loader.py`, `test_osm_normalizer.py`, `test_road_graph.py`, `geometry.test.ts`.
  - OpenStreetMap XML parser ingests highway tags, coordinates, and intersection topology. Generates deterministic directed road graph with fallback to synthetic grid. Frontend builds 3D road geometries and lane markings.
- **Status:** `PASS`

---

### FR-04: Traffic and Pedestrian Simulation
- **Requirement Statement:** Simulate realistic traffic conditions and vehicle movements; include traffic signals, congestion, pedestrian crossings, and unexpected road conditions.
- **Components:** `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/`, `backend/apps/core/incidents/`
- **Verification Evidence:**
  - Automated tests: `test_signals_*.py`, `test_pedestrian_*.py`, `test_incident_*.py`, `incidents.test.ts` (124 tests).
  - 4-phase traffic light cycle state machine, pedestrian crosswalk corridor conflict detection, vehicle deceleration/yielding invariants, and dynamic road closure/congestion incident injection verified.
- **Status:** `PASS`

---

### FR-05: Motion Planning and Performance Benchmarking
- **Requirement Statement:** Implement and compare different path-planning algorithms; evaluate travel time, collision rate, route efficiency, safety, and communication performance.
- **Components:** `backend/apps/core/routing/`, `backend/apps/core/benchmarking/`, `backend/apps/core/persistence/`, `backend/apps/core/management/commands/run_benchmark.py`
- **Verification Evidence:**
  - Automated tests: `test_benchmarking.py`, `test_persistence_*.py`, `test_api_persistence_history.py` (78 tests).
  - Controlled-seed comparative evaluation across Dijkstra, A*, Static, and Adaptive planners. Metrics recorded to SQLite models (`SimulationRun`, `BenchmarkTrial`, `ExperimentMetric`) and exported to JSON, CSV, and Markdown.
- **Status:** `PASS`

---

### FR-06: Decentralized Vehicle Communication
- **Requirement Statement:** Enable vehicles to communicate directly without depending on a central communication controller; support independent information sharing and coordination between vehicles.
- **Components:** `backend/apps/core/communication/`, `backend/apps/core/coordination/`
- **Verification Evidence:**
  - Automated tests: `test_communication_protocol.py`, `test_communication_discovery.py`, `test_coordination_*.py`.
  - Peer-to-peer message exchange operates entirely on localized neighbor tables and local knowledge stores without any centralized routing broker or global state oracle.
- **Status:** `PASS`

---

### FR-07: Adaptive Path Planning
- **Requirement Statement:** Implement dynamic route planning using algorithms such as A*; automatically calculate alternative routes during traffic congestion, accidents, or road blockages.
- **Components:** `backend/apps/core/routing/`, `frontend/src/features/scene3d/routeOverlay.ts`, `frontend/src/features/simulation/EntityInspector.tsx`
- **Verification Evidence:**
  - Automated tests: `test_routing_*.py`, `test_regression_routing_and_graph.py`, `routing.test.ts`.
  - Dynamic edge cost updates, hysteresis cooldown timers, safe route suffix replacement, alternative path evaluation, and 3D detour overlay rendering verified.
- **Status:** `PASS`

---

### FR-08: AI-Based Decision-Making
- **Requirement Statement:** Develop an intelligent decision-making system for autonomous vehicles; enable vehicles to independently accept or reject route suggestions based on traffic conditions, safety, and travel efficiency.
- **Components:** `backend/apps/core/decision/`, `backend/apps/core/routing/adapter.py`, `backend/apps/core/rl/adapter.py`
- **Verification Evidence:**
  - Automated tests: `test_decision_*.py` (43 tests), `test_rl_learned_policy_integration.py` (25 tests).
  - Pluggable decision policy with multi-objective utility scoring (`ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE`), hard safety constraints (closed edge rejection), and safe conventional routing fallback.
- **Status:** `PASS`

---

### FR-09: Collision Detection and Avoidance
- **Requirement Statement:** Detect nearby vehicles, pedestrians, and obstacles; implement collision avoidance mechanisms and maintain safe distances.
- **Components:** `backend/apps/core/safety/` (`geometry.py`, `detection.py`, `policy.py`, `manager.py`, `models.py`)
- **Verification Evidence:**
  - Automated tests: `test_safety_*.py`, `test_pedestrian_safety_and_collisions.py` (55 tests), `test_regression_simulation_invariants.py`.
  - 2D Oriented Bounding Box (OBB) Separating Axis Theorem collision checks, closing rate Time-To-Collision (TTC) calculations, emergency braking overrides, and zero-collision safety invariant verified.
- **Status:** `PASS`

---

### FR-10: Emergency Vehicle Priority
- **Requirement Statement:** Identify emergency vehicles such as ambulances, fire engines, and police cars; enable nearby vehicles to safely adjust their movement, yield, create dynamic corridors, and grant traffic signal priority.
- **Components:** `backend/apps/core/emergency/`, `backend/apps/core/simulation/engine.py`, `frontend/src/features/scene3d/models.ts`
- **Verification Evidence:**
  - Automated tests: `test_emergency_*.py` (60 tests), `models.test.ts` (18 tests).
  - Priority FSM, dynamic corridor reservation along emergency route, civilian vehicle yielding, preemptive green signal priority, and Three.js alternating siren beacon strobe verified.
- **Status:** `PASS`

---

### FR-11: Communication Range Detection
- **Requirement Statement:** Implement configurable vehicle communication ranges; automatically establish communication when vehicles enter the specified communication radius.
- **Components:** `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/v2vOverlay.ts`
- **Verification Evidence:**
  - Automated tests: `test_communication_discovery.py`, `test_communication_neighbors.py`, `v2v.test.ts`.
  - Neighbor discovery enforces $d \le R_{\text{comm}}$. Packets beyond range are dropped with explicit `OUT_OF_RANGE` reason. Three.js ground disc rendering visualizes communication range radius.
- **Status:** `PASS`

---

### FR-12: Communication Failure Handling
- **Requirement Statement:** Detect communication failures, delayed messages, and packet loss; implement fallback mechanisms to maintain safe vehicle operation during communication failures.
- **Components:** `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/v2vOverlay.ts`
- **Verification Evidence:**
  - Automated tests: `test_communication_latency.py`, `test_communication_impairment.py`, `v2v.test.ts`.
  - Injected packet drop, burst loss, and network latency models verify vehicle fallback to onboard sensors. Three.js displays dashed amber links and packet loss warning overlays.
- **Status:** `PASS`

---

### FR-13: AI Model Training Using Reinforcement Learning
- **Requirement Statement:** Develop and train a reinforcement learning model for intelligent route selection; improve vehicle decision-making through interaction with simulated traffic environments.
- **Components:** `backend/apps/core/rl/`, `backend/apps/core/benchmarking/adapters.py`
- **Verification Evidence:**
  - Automated tests: `test_rl_environment.py` (26 tests), `test_rl_training.py` (22 tests), `test_rl_learned_policy_integration.py` (25 tests).
  - Gymnasium-compliant single-agent and multi-agent environments (`check_env` passes), MaskablePPO training via `train_rl_baseline`, checkpointing in `artifacts/rl_models/`, and safe conventional routing fallback (`SafeFallbackPolicyWrapper`) when model unavailable or edge blocked.
- **Status:** `PASS`

---

### FR-14: Real-Time 3D Visualization and Interactive Dashboard
- **Requirement Statement:** Develop a web-based dashboard using Django and Three.js; visualize realistic roads, buildings, autonomous vehicles, pedestrians, and traffic conditions; display real-time vehicle movements, V2V communication, route changes, and AI decisions.
- **Components:** `backend/apps/core/api/`, `backend/apps/core/realtime/`, `frontend/src/`
- **Verification Evidence:**
  - Automated tests: 193 Vitest frontend tests across 12 test suites; 118 WebSocket and REST backend tests; complete Vite production bundle build.
  - Three.js 3D city viewport, playback timeline scrubber (Play/Pause/Step/Speed), V2V communication overlays, incident injection panel, entity inspector, and operational analytics dashboard verified.
- **Status:** `PASS`

---

## 3. Final Phase 40 Sign-Off Decision

**Acceptance Decision:** **ACCEPTED & COMPLETE (40/40 Phases)**  
**Verification Gate:** GitHub Actions CI Pipeline — All jobs passing cleanly (Repository Hygiene, Backend Lint & Test, Frontend Lint & Test, Docker Deployment Smoke).  
**Educational Simulation Notice:** AMAPP is an educational and academic simulation platform and is not certified for real-world autonomous vehicle control.
