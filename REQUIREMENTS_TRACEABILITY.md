# REQUIREMENTS TRACEABILITY MATRIX

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Source of Truth:** `Project_Objective_and_Requirements.pdf`  
**Current Phase:** Phase 36 (Security Hardening and Failure Handling)  
**Status Legend:**
- `NOT STARTED`: Requirement specified and mapped; functional implementation not yet begun.
- `IN PROGRESS`: Modules under active development in current phase.
- `IMPLEMENTED`: Code implemented but awaiting complete integration/system testing.
- `TESTED`: Automated unit and integration tests passing with evidence.
- `BLOCKED`: Development impeded by dependencies or unresolved technical blockers.

> *Note on Phase 36 (Security Hardening and Failure Handling):* Phase 36 establishes multi-layer platform hardening including strict SECRET_KEY and ALLOWED_HOSTS enforcement, HTTP security headers, request body limits (5MB), DRF rate limiting, RFC 7807 429 translation, path parameter regex sanitization, finite float validations (`math.isfinite`), WebSocket 64KB framing, origin whitelisting, role-based mutation policies, Zip Slip mitigation, model path containment, SafeFallbackPolicyWrapper, and persistence database failure tolerance. 192 frontend tests, 1,284 backend tests passing (94.91% line coverage).

---

## 1. Traceability Summary Matrix (Aligned with 40-Phase Plan)

| Req # | Requirement Name | Implementation Modules | Target Phases | Current Status | Test Coverage |
|---|---|---|---|---|---|
| **FR-01** | Vehicle-to-Vehicle (V2V) Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `frontend/src/features/scene3d/` | Phase 11, 12, 13, 14, 27 | `TESTED` | Phase 11–14 Backend Protocol & Phase 27 Three.js Link/Message Overlays Tested (`test_communication_*.py`, `test_coordination_*.py`, `v2v.test.ts`) |
| **FR-02** | Multi-Agent Autonomous Vehicle Environment | `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/` | Phase 07, 08, 10, 20, 25 | `TESTED` | Phase 07, 08, 10, 20 Tested (`test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`, `test_runner_*.py`) |
| **FR-03** | Real-World Map Integration | `backend/apps/core/graph/`, `frontend/src/features/scene3d/` | Phase 04, 05, 24 | `TESTED` | Phase 04 & 05 Foundation Tested (`test_osm_*.py`, `test_road_graph.py`); Phase 24 Frontend OSM Adapter Tested (`geometry.test.ts`) |
| **FR-04** | Traffic and Pedestrian Simulation | `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/`, `backend/apps/core/incidents/` | Phase 09, 17, 25, 29 | `TESTED` | Phase 09 Signals, Phase 17 Pedestrians & Phase 29 Incidents Tested (`test_signals_*.py`, `test_pedestrian_*.py`, `test_incident_*.py`) |
| **FR-05** | Motion Planning and Performance Benchmarking | `backend/apps/core/routing/`, `backend/apps/core/benchmarking/`, `backend/apps/core/persistence/`, `backend/apps/core/models.py`, `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/`, `backend/apps/core/telemetry/` | Phase 06, 07, 08, 10, 20, 30, 31, 35 | `TESTED` | Phase 06–10 & Phase 20 Metrics Aggregation; Phase 31 Benchmarking; Phase 35 Persistent Models, Fingerprinting, and History API Tested (`test_persistence_*.py`, `test_api_persistence_history.py`, `test_benchmarking.py`) |
| **FR-06** | Decentralized Vehicle Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/` | Phase 11, 12, 13, 14 | `TESTED` | Phase 11–14 Protocol, Discovery, Neighbors, Knowledge & Outages Tested (`test_communication_*.py`, `test_coordination_*.py`) |
| **FR-07** | Adaptive Path Planning | `backend/apps/core/routing/`, `frontend/src/features/scene3d/`, `frontend/src/features/simulation/` | Phase 06, 15, 28 | `TESTED` | Phase 06 & 15 Dynamic Rerouting & Phase 28 Three.js Route/Candidate Overlays Tested (`test_routing_*.py`, `routing.test.ts`, `components.test.tsx`) |
| **FR-08** | AI-Based Decision-Making | `backend/apps/core/decision/`, `backend/apps/core/routing/adapter.py` | Phase 19, 34 | `TESTED` | Phase 19 Pluggable Rule-Based AI Decision Policies Tested (`test_decision_*.py`: 43 tests passing) |
| **FR-09** | Collision Detection and Avoidance | `backend/apps/core/safety/` | Phase 16, 17, 37 | `TESTED` | Phase 16 V2V & Phase 17 Vehicle-Pedestrian Collision Avoidance Tested (`test_safety_*.py`, `test_pedestrian_safety_and_collisions.py`) |
| **FR-10** | Emergency Vehicle Priority | `backend/apps/core/emergency/`, `backend/apps/core/simulation/` | Phase 18, 25, 29 | `TESTED` | Phase 18 Emergency Priority, Corridors, Yielding & Signals Tested (`test_emergency_*.py`: 60 tests passing) |
| **FR-11** | Communication Range Detection | `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 11, 12, 14, 27 | `TESTED` | Phase 11, 12, 14 Spatial Discovery & Phase 27 3D Range Disc Visualization Tested (`test_communication_discovery.py`, `v2v.test.ts`) |
| **FR-12** | Communication Failure Handling | `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 14, 27 | `TESTED` | Phase 14 Failures & Recovery & Phase 27 3D Degradation Overlays Tested (`test_communication_latency.py`, `test_communication_impairment.py`, `v2v.test.ts`) |
| **FR-13** | AI Model Training Using Reinforcement Learning | `backend/apps/core/rl/`, `backend/apps/core/benchmarking/` | Phase 32, 33, 34 | `TESTED` | Phase 32 Gymnasium Env, Phase 33 MaskablePPO Training & Phase 34 Learned Adapter with Safe Fallback Tested (`test_rl_environment.py`: 26, `test_rl_training.py`: 22, `test_rl_learned_policy_integration.py`: 25 passed) |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | `backend/apps/core/api/`, `backend/apps/core/realtime/`, `backend/apps/core/telemetry/`, `frontend/` | Phase 21–30 | `TESTED` | Phases 21–30 Complete (192 frontend tests, 1,118 backend tests passing; Playback controls, timeline scrubber, 3D city/models, Three.js V2V layer, Adaptive Routing Overlays, Incident Controls, and Operational Metrics Dashboard fully tested) |
| **NFR-04** | Security Hardening & Failure Handling | `backend/config/`, `backend/apps/core/api/`, `backend/apps/core/realtime/`, `backend/apps/core/rl/`, `backend/apps/core/persistence/` | Phase 36 | `TESTED` | Phase 36 Complete (37 security tests across 5 test suites; 1,284 backend tests passing at 94.91% coverage; settings checks, headers, throttling, path regex, finite numeric validation, WebSocket framing, Zip Slip mitigation, database failure tolerance) |



---

## 2. Detailed Requirement Breakdown

### FR-01: Vehicle-to-Vehicle (V2V) Communication
- **Requirement Statement:** Establish communication between nearby autonomous vehicles; enable vehicles to exchange traffic information, accident alerts, obstacles, and route updates.
- **Target Phases:** Phase 11 (V2V message protocol), Phase 13 (Decentralized V2V coordination), Phase 27 (V2V visualization).
- **Components:** `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `frontend/src/features/scene3d/v2vOverlay.ts`, `frontend/src/features/scene3d/v2vAdapter.ts`, `frontend/src/types/v2v.ts`
- **Verification Plan:** Unit tests for packet serialization, broadcast routing, and message queue delivery between neighboring vehicles within range; Three.js active/stale link rendering, canonical link deduplication, and message pulse transit animations (`test_communication_*.py`, `test_coordination_*.py`, `v2v.test.ts`).
- **Current Status:** `TESTED`

---

### FR-02: Multi-Agent Autonomous Vehicle Environment
- **Requirement Statement:** Develop multiple independent autonomous vehicle agents, each with its own destination, speed, route, and decision-making capabilities.
- **Target Phases:** Phase 07 (Vehicle agents and lifecycle), Phase 10 (Multi-agent scenario orchestration), Phase 25 (Vehicle and pedestrian visualization).
- **Components:** `sim_engine/agents/vehicle.py`, `sim_engine/agents/state.py`, `sim_engine/core/lifecycle.py`
- **Verification Plan:** Multi-agent lifecycle tests verifying independent trajectories, individual odometry, and distinct origin-destination pairs.
- **Current Status:** `NOT STARTED`

---

### FR-03: Real-World Map Integration
- **Requirement Statement:** Integrate OpenStreetMap to obtain real-world road networks; support actual roads, intersections, lanes, and navigation routes.
- **Target Phases:** Phase 04 (Road graph and deterministic city), Phase 05 (OpenStreetMap import), Phase 24 (3D city and road rendering).
- **Components:** `sim_engine/map/osm_loader.py`, `sim_engine/map/graph.py`, `data/osm/`
- **Verification Plan:** Tests for OSM XML/OSMnx graph ingestion, node-edge connectivity, lane count attributes, and offline deterministic fallback grid.
- **Current Status:** `TESTED (Phase 04 RoadGraph & City Grid, Phase 05 OSM Normalizer, and Phase 24 3D Road Network & OSM Data Adapter Complete)`

---

### FR-04: Traffic and Pedestrian Simulation
- **Requirement Statement:** Simulate realistic traffic conditions and vehicle movements; include traffic signals, congestion, pedestrian crossings, and unexpected road conditions.
- **Target Phases:** Phase 09 (Vehicle movement and traffic rules), Phase 17 (Pedestrians and traffic signals), Phase 25 (Vehicle and pedestrian visualization), Phase 29 (Traffic incidents and scenario controls).
- **Components:** `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/`, `backend/apps/core/incidents/`
- **Verification Plan:** State machine tests for 4-phase traffic lights, pedestrian crosswalk corridor model, signalized and unsignalized pedestrian crossing logic, clearance policy, and vehicle yield/braking enforcement; authoritative incident management verifying road closures, congestion reports, physical obstacles, and signal phase overrides (`test_signals_*.py`, `test_pedestrian_*.py`, `test_incident_*.py`: 124 tests passing).
- **Current Status:** `TESTED (Phase 09 Traffic Signals, Phase 17 Pedestrians, and Phase 29 Traffic Incidents Complete)`

---

### FR-05: Motion Planning and Performance Benchmarking
- **Requirement Statement:** Implement and compare different path-planning algorithms; evaluate travel time, collision rate, route efficiency, safety, and communication performance.
- **Target Phases:** Phase 06 (Route planning baseline), Phase 30 (Operational metrics dashboard), Phase 31 (Benchmarking framework).
- **Components:** `backend/apps/core/routing/`, `backend/apps/core/benchmarking/`, `backend/apps/core/management/commands/run_benchmark.py`
- **Verification Plan:** Comparative benchmark test suite evaluating Dijkstra, A*, Static, and Adaptive algorithms against standardized benchmark scenarios with controlled seeds, deterministic execution, and JSON/CSV/Markdown exports (`test_benchmarking.py`: 26 tests passing).
- **Current Status:** `TESTED (Phase 06 Baselines, Phase 30 Operational Metrics, and Phase 31 Benchmarking Framework Complete)`

---

### FR-06: Decentralized Vehicle Communication
- **Requirement Statement:** Enable vehicles to communicate directly without depending on a central communication controller; support independent information sharing and coordination between vehicles.
- **Target Phases:** Phase 11 (V2V message protocol), Phase 12 (Dynamic neighbor tables & loss detection), Phase 13 (Decentralized V2V coordination), Phase 14 (Communication latency & packet loss).
- **Components:** `backend/apps/core/communication/`, `backend/apps/core/coordination/`
- **Verification Plan:** Multi-agent test proving vehicles communicate in peer-to-peer fashion without centralized dispatch or global oracle knowledge, maintaining private knowledge stores and neighbor tables (`test_communication_*.py`, `test_coordination_*.py`).
- **Current Status:** `TESTED`

---

### FR-07: Adaptive Path Planning
- **Requirement Statement:** Implement dynamic route planning using algorithms such as A*; automatically calculate alternative routes during traffic congestion, accidents, or road blockages.
- **Target Phases:** Phase 06 (Route planning baseline), Phase 15 (Adaptive rerouting), Phase 28 (Adaptive routing visualization).
- **Components:** `backend/apps/core/routing/`, `frontend/src/features/scene3d/routeOverlay.ts`, `frontend/src/features/scene3d/routeAdapter.ts`, `frontend/src/features/simulation/EntityInspector.tsx`
- **Verification Plan:** Dynamic edge cost evaluation, hysteresis & cooldown tests, safe route suffix replacement; Three.js active route overlay, candidate alternative path rendering, rotating 3D reroute markers, and authoritative telemetry inspector (`test_routing_*.py`, `routing.test.ts`, `components.test.tsx`).
- **Current Status:** `TESTED`

---

### FR-08: AI-Based Decision-Making
- **Requirement Statement:** Develop an intelligent decision-making system for autonomous vehicles; enable vehicles to independently accept or reject route suggestions based on traffic conditions, safety, and travel efficiency.
- **Target Phases:** Phase 19 (AI decision policy), Phase 34 (RL evaluation and policy integration).
- **Components:** `backend/apps/core/decision/` (`models.py`, `config.py`, `features.py`, `scoring.py`, `policy.py`, `manager.py`, `metrics.py`), `backend/apps/core/routing/adapter.py`
- **Verification Plan:** Multi-objective scoring tests, hard safety constraint rejection (closures, active corridors), bounded observation confidence evaluation, route stability hysteresis, explicit outcome taxonomy (`ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE`), decentralized local knowledge isolation, single-clock simulation engine stepping, and atomic rollback (`test_decision_*.py`: 43 tests passing).
- **Current Status:** `TESTED (Phase 19 Rule-Based Baseline Complete; RL Deferred to Phases 32-34)`

---

### FR-09: Collision Detection and Avoidance
- **Requirement Statement:** Detect nearby vehicles, pedestrians, and obstacles; implement collision avoidance mechanisms and maintain safe distances.
- **Target Phases:** Phase 16 (Collision detection and avoidance), Phase 17 (Pedestrians and traffic signals), Phase 37 (Automated testing and regression).
- **Components:** `backend/apps/core/safety/` (`geometry.py`, `detection.py`, `policy.py`, `manager.py`, `metrics.py`, `models.py`)
- **Verification Plan:** 2D OBB Separating Axis Theorem overlap tests, closing speed and Time-To-Collision (TTC) calculations, minimum safe separation distance enforcement, controlled deceleration and emergency braking overrides, conservative multi-conflict resolution, vehicle-pedestrian conflict detection, atomic rollback, and deterministic scenario fixtures (`test_safety_*.py`, `test_pedestrian_safety_and_collisions.py`: 55 tests passing).
- **Current Status:** `TESTED (Phase 16 V2V & Phase 17 Vehicle-Pedestrian Collision Detection, Safe Separation, and Avoidance Complete)`

---

### FR-10: Emergency Vehicle Priority
- **Requirement Statement:** Identify emergency vehicles such as ambulances, fire engines, and police cars; enable nearby vehicles to safely adjust their movement, yield, create dynamic corridors, and grant traffic signal priority.
- **Target Phases:** Phase 18 (Emergency vehicle priority), Phase 25 (Vehicle and pedestrian visualization), Phase 29 (Traffic incidents and scenario controls).
- **Components:** `backend/apps/core/emergency/` (`models.py`, `v2v.py`, `corridor_planner.py`, `yielding_policy.py`, `priority_manager.py`, `metrics.py`), `backend/apps/core/signals/controller.py`, `backend/apps/core/simulation/engine.py`, `frontend/src/features/scene3d/models.ts`
- **Verification Plan:** Unit and integration tests for emergency models, priority FSM, tie-breaking, V2V announcements without leakage, corridor reservations and preemption, yielding with physical limits, red signal and crosswalk protection, signal priority override with pedestrian clearance denial, single-clock engine execution, atomic rollback, and 3D visual distinction with subtle alternating beacon pulsing (`test_emergency_*.py`: 60 tests passing; `models.test.ts`: 18 tests passing).
- **Current Status:** `TESTED (Phase 18 Backend Engine & Phase 25 Emergency 3D Visual Treatments Complete)`

---

### FR-11: Communication Range Detection
- **Requirement Statement:** Implement configurable vehicle communication ranges; automatically establish communication when vehicles enter the specified communication radius.
- **Target Phases:** Phase 12 (Communication range and peer discovery), Phase 27 (V2V visualization).
- **Components:** `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/v2vOverlay.ts`, `frontend/src/features/scene3d/v2vAdapter.ts`
- **Verification Plan:** Geometric radius tests confirming messages pass only when Euclidean distance $d \le R_{\text{comm}}$ and are dropped when $d > R_{\text{comm}}$; Three.js ground-level communication range disc ($y=0.08\text{m}$) and perimeter ring rendering around inspected vehicles with "Unavailable" fallback when unconfigured (`test_communication_discovery.py`, `test_communication_impairment.py`, `v2v.test.ts`).
- **Current Status:** `TESTED`

---

### FR-12: Communication Failure Handling
- **Requirement Statement:** Detect communication failures, delayed messages, and packet loss; implement fallback mechanisms to maintain safe vehicle operation during communication failures.
- **Target Phases:** Phase 14 (Communication failures and recovery), Phase 27 (V2V visualization).
- **Components:** `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/v2vOverlay.ts`, `frontend/src/features/scene3d/v2vAdapter.ts`
- **Verification Plan:** Injected packet loss/latency test suite ensuring vehicle safely decelerates or relies on onboard sensor envelope when V2V links degrade; Three.js network degradation overlays visualizing stale links (dashed amber), dropped packet warning markers (red crosses), channel state (Good/Bad), and network partitions (`test_communication_latency.py`, `test_communication_impairment.py`, `v2v.test.ts`).
- **Current Status:** `TESTED`

---

### FR-13: AI Model Training Using Reinforcement Learning
- **Requirement Statement:** Develop and train a reinforcement learning model for intelligent route selection; improve vehicle decision-making through interaction with simulated traffic environments.
- **Target Phases:** Phase 32 (Reinforcement-learning environment), Phase 33 (Train and save an RL baseline), Phase 34 (RL evaluation and policy integration).
- **Components:** `backend/apps/core/rl/` (`env.py`, `multi_agent.py`, `features.py`, `rewards.py`, `config.py`, `adapter.py`, `model_manager.py`, `exceptions.py`), `backend/apps/core/rl/training/` (`config.py`, `trainer.py`, `evaluator.py`, `policy.py`), `backend/apps/core/benchmarking/adapters.py` (`LearnedRoutingBenchmarkAdapter`, `SafeFallbackPolicyWrapper`), `backend/apps/core/management/commands/train_rl_baseline.py`, `test_rl_environment.py`, `test_rl_training.py`, `test_rl_learned_policy_integration.py`.
- **Verification Plan:** Gymnasium `check_env` validation, deterministic reward progression tests, observation bounds, action masking, multi-agent coordination, benchmark bridge execution, Stable-Baselines3/sb3-contrib MaskablePPO baseline training, model checkpointing in `artifacts/rl_models/`, deterministic model reload, model discovery/validation lifecycle (`RLModelManager`), safe conventional fallback (`SafeFallbackPolicyWrapper`), and held-out 8-scenario benchmark evaluation against Dijkstra, A*, Static, and Adaptive planners (`test_rl_environment.py`: 26 tests, `test_rl_training.py`: 22 tests, `test_rl_learned_policy_integration.py`: 25 tests passing).
- **Current Status:** `TESTED (Phase 32 Gymnasium Environments, Phase 33 Baseline Training & Checkpointing, and Phase 34 Policy Integration with Safe Fallback COMPLETED; 1,217 backend tests passing, 95% coverage)`


---

### FR-14: Real-Time 3D Visualization and Interactive Dashboard
- **Requirement Statement:** Develop a web-based dashboard using Django and Three.js; visualize realistic roads, buildings, autonomous vehicles, pedestrians, and traffic conditions; display real-time vehicle movements, V2V communication, route changes, and AI decisions.
- **Target Phases:** Phase 21 (Django REST API), Phase 22 (Real-time WebSocket streaming), Phase 23 (Frontend scaffold), Phase 24 (3D city and road rendering), Phase 25 (Vehicle and pedestrian visualization), Phase 26 (Live simulation controls), Phase 27 (V2V visualization), Phase 28 (Adaptive routing visualization), Phase 29 (Traffic incidents and scenario controls), Phase 30 (Operational metrics dashboard).
- **Components:** `backend/apps/core/realtime/`, `backend/apps/core/api/`, `backend/apps/core/telemetry/analytics.py`, `frontend/src/features/scene3d/` (`SimulationViewer3D.tsx`, `geometry.ts`, `models.ts`, `interpolation.ts`, `v2vOverlay.ts`, `v2vAdapter.ts`, `routeOverlay.ts`, `routeAdapter.ts`, `incidentOverlay.ts`, `incidentAdapter.ts`), `frontend/src/features/playback/` (`playbackScheduler.ts`, `historyBuffer.ts`, `PlaybackBar.tsx`), `frontend/src/features/simulation/` (`EntityInspector.tsx`, `IncidentControlPanel.tsx`), `frontend/src/features/analytics/` (`OperationalDashboard.tsx`)
- **Verification Plan:** WebSocket frame serialization tests, client connection lifecycle tests, Three.js mesh rendering verification, temporal interpolation unit tests, playback scheduler tests, history buffer tests with deep cloning, V2V overlay unit tests, route overlay unit tests, incident overlay unit tests, operational analytics engine aggregation tests, and component tests (`websocket-client.test.ts`, `api-client.test.ts`, `geometry.test.ts`, `interpolation.test.ts`, `models.test.ts`, `playback.test.ts`, `v2v.test.ts`, `routing.test.ts`, `incidents.test.ts`, `components.test.tsx`, `analytics.test.tsx`: 192 frontend tests, 1,170 backend tests passing).
- **Current Status:** `TESTED (Phases 21–30 COMPLETED & TESTED; 192 frontend tests across 11 test suites; Phase 31 Benchmarking Framework COMPLETED & TESTED; Phase 32 Gymnasium RL Environments COMPLETED & TESTED with 1,170 backend tests; Phase 33 Model Training Next)`



