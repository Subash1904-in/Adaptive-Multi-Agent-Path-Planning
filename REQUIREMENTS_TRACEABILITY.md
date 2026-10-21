# REQUIREMENTS TRACEABILITY MATRIX

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Source of Truth:** `Project_Objective_and_Requirements.pdf`  
**Current Phase:** Phase 27 (Implement V2V Communication Links, Message Animations, and Network-State Overlays)  
**Status Legend:**
- `NOT STARTED`: Requirement specified and mapped; functional implementation not yet begun.
- `IN PROGRESS`: Modules under active development in current phase.
- `IMPLEMENTED`: Code implemented but awaiting complete integration/system testing.
- `TESTED`: Automated unit and integration tests passing with evidence.
- `BLOCKED`: Development impeded by dependencies or unresolved technical blockers.

> *Note on Phase 27 (V2V Communication Links, Message Animations, and Network-State Overlays):* Phase 27 delivers an interactive Three.js 3D V2V communication layer grounded in authoritative backend telemetry. It visualizes active and stale communication links from `neighbor_tables` with canonical deduplication, renders verified communication range discs and rings around inspected vehicles (displaying "Unavailable" if unconfigured), bounds message transmission pulses and drop indicators with pause-freezing and speed scaling, renders network degradation overlays (channel state, packet loss, partitions, PDR), provides an accessible HUD toggle toolbar and collapsible V2V visual legend, and integrates deep-cloned communication states into the historical playback scrubber. 147 frontend tests passing, 1,097 backend tests passing (95.67% coverage).

---

## 1. Traceability Summary Matrix (Aligned with 40-Phase Plan)

| Req # | Requirement Name | Implementation Modules | Target Phases | Current Status | Test Coverage |
|---|---|---|---|---|---|
| **FR-01** | Vehicle-to-Vehicle (V2V) Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `frontend/src/features/scene3d/` | Phase 11, 12, 13, 14, 27 | `TESTED` | Phase 11–14 Backend Protocol & Phase 27 Three.js Link/Message Overlays Tested (`test_communication_*.py`, `test_coordination_*.py`, `v2v.test.ts`) |
| **FR-02** | Multi-Agent Autonomous Vehicle Environment | `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/` | Phase 07, 08, 10, 20, 25 | `TESTED` | Phase 07, 08, 10, 20 Tested (`test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`, `test_runner_*.py`) |
| **FR-03** | Real-World Map Integration | `backend/apps/core/graph/`, `frontend/src/features/scene3d/` | Phase 04, 05, 24 | `TESTED` | Phase 04 & 05 Foundation Tested (`test_osm_*.py`, `test_road_graph.py`); Phase 24 Frontend OSM Adapter Tested (`geometry.test.ts`) |
| **FR-04** | Traffic and Pedestrian Simulation | `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/` | Phase 09, 17, 25, 29 | `TESTED` | Phase 09 Signals & Phase 17 Pedestrians Tested (`test_signals_*.py`, `test_pedestrian_*.py`) |
| **FR-05** | Motion Planning and Performance Benchmarking | `backend/apps/core/routing/`, `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/`, `backend/apps/core/telemetry/` | Phase 06, 07, 08, 10, 20, 30, 31 | `TESTED` | Phase 06–10 & Phase 20 Metrics Aggregation & Export Tested (`test_routing_*.py`, `test_runner_metrics_aggregation.py`, `test_runner_determinism_and_export.py`) |
| **FR-06** | Decentralized Vehicle Communication | `backend/apps/core/communication/`, `backend/apps/core/coordination/`, `sim_engine/agents/` | Phase 11, 12, 13, 14 | `NOT STARTED` | Phase 11–14 Protocol, Discovery, Neighbors, Knowledge & Outages Tested (`test_communication_*.py`, `test_coordination_*.py`) |
| **FR-07** | Adaptive Path Planning | `backend/apps/core/routing/`, `sim_engine/planning/` | Phase 06, 15, 28 | `NOT STARTED` | Phase 06 & 15 Baseline & Adaptive Rerouting Tested (`test_routing_*.py`) |
| **FR-08** | AI-Based Decision-Making | `backend/apps/core/decision/`, `backend/apps/core/routing/adapter.py` | Phase 19, 34 | `TESTED` | Phase 19 Pluggable Rule-Based AI Decision Policies Tested (`test_decision_*.py`: 43 tests passing) |
| **FR-09** | Collision Detection and Avoidance | `backend/apps/core/safety/` | Phase 16, 17, 37 | `TESTED` | Phase 16 V2V & Phase 17 Vehicle-Pedestrian Collision Avoidance Tested (`test_safety_*.py`, `test_pedestrian_safety_and_collisions.py`) |
| **FR-10** | Emergency Vehicle Priority | `backend/apps/core/emergency/`, `backend/apps/core/simulation/` | Phase 18, 25, 29 | `TESTED` | Phase 18 Emergency Priority, Corridors, Yielding & Signals Tested (`test_emergency_*.py`: 60 tests passing) |
| **FR-11** | Communication Range Detection | `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 11, 12, 14, 27 | `TESTED` | Phase 11, 12, 14 Spatial Discovery & Phase 27 3D Range Disc Visualization Tested (`test_communication_discovery.py`, `v2v.test.ts`) |
| **FR-12** | Communication Failure Handling | `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py`, `frontend/src/features/scene3d/` | Phase 11, 12, 14, 27 | `TESTED` | Phase 11, 12, 14 Degradation & Phase 27 Channel State / Drop Indicators Tested (`test_communication_impairment.py`, `v2v.test.ts`) |
| **FR-13** | AI Model Training Using Reinforcement Learning | `rl_engine/` | Phase 32, 33, 34 | `NOT STARTED` | Pending Phase 32 |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | `backend/apps/core/api/`, `backend/apps/core/realtime/`, `frontend/` | Phase 21–30 | `IN PROGRESS` | Phases 21–27 Complete (147 frontend tests, 1,097 backend tests passing; Playback controls, timeline scrubber, 3D city/models, and Three.js V2V layer fully integrated; Phase 28 Adaptive Routing Visualization Next) |



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
- **Components:** `backend/apps/core/signals/`, `backend/apps/core/pedestrians/`, `backend/apps/core/safety/`
- **Verification Plan:** State machine tests for 4-phase traffic lights, pedestrian crosswalk corridor model, signalized and unsignalized pedestrian crossing logic, clearance policy, and vehicle yield/braking enforcement (`test_signals_*.py`, `test_pedestrian_*.py`: 109 tests passing).
- **Current Status:** `TESTED (Phase 09 Traffic Signals & Phase 17 Pedestrian Agents, Crosswalks, and Signal Interaction Complete)`

---

### FR-05: Motion Planning and Performance Benchmarking
- **Requirement Statement:** Implement and compare different path-planning algorithms; evaluate travel time, collision rate, route efficiency, safety, and communication performance.
- **Target Phases:** Phase 06 (Route planning baseline), Phase 30 (Operational metrics dashboard), Phase 31 (Benchmarking framework).
- **Components:** `sim_engine/planning/`, `sim_engine/benchmarks/metrics.py`, `sim_engine/benchmarks/evaluator.py`
- **Verification Plan:** Comparative benchmark test suite evaluating A*, Dijkstra, and RL routes against standard baseline scenarios.
- **Current Status:** `NOT STARTED`

---

### FR-06: Decentralized Vehicle Communication
- **Requirement Statement:** Enable vehicles to communicate directly without depending on a central communication controller; support independent information sharing and coordination between vehicles.
- **Target Phases:** Phase 11 (V2V message protocol), Phase 12 (Communication range and peer discovery), Phase 13 (Decentralized V2V coordination).
- **Components:** `sim_engine/v2v/protocol.py`, `sim_engine/agents/knowledge_base.py`
- **Verification Plan:** Multi-agent test proving vehicles communicate in peer-to-peer fashion without centralized dispatch or global oracle knowledge.
- **Current Status:** `NOT STARTED`

---

### FR-07: Adaptive Path Planning
- **Requirement Statement:** Implement dynamic route planning using algorithms such as A*; automatically calculate alternative routes during traffic congestion, accidents, or road blockages.
- **Target Phases:** Phase 06 (Route planning baseline), Phase 15 (Adaptive rerouting), Phase 28 (Adaptive routing visualization).
- **Components:** `sim_engine/planning/dynamic_astar.py`, `sim_engine/planning/cost_field.py`
- **Verification Plan:** Rerouting tests verifying an agent recalculates path when downstream edges receive hazard flags via V2V or sensor detection.
- **Current Status:** `NOT STARTED`

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
- **Components:** `rl_engine/envs/ma_nav_env.py`, `rl_engine/training/train_agent.py`, `rl_engine/policies/`
- **Verification Plan:** Gymnasium `check_env` validation, deterministic reward progression tests, and bounded headless training execution.
- **Current Status:** `NOT STARTED`

---

### FR-14: Real-Time 3D Visualization and Interactive Dashboard
- **Requirement Statement:** Develop a web-based dashboard using Django and Three.js; visualize realistic roads, buildings, autonomous vehicles, pedestrians, and traffic conditions; display real-time vehicle movements, V2V communication, route changes, and AI decisions.
- **Target Phases:** Phase 21 (Django REST API), Phase 22 (Real-time WebSocket streaming), Phase 23 (Frontend scaffold), Phase 24 (3D city and road rendering), Phase 25 (Vehicle and pedestrian visualization), Phase 26 (Live simulation controls), Phase 27 (V2V visualization), Phase 28 (Adaptive routing visualization), Phase 29 (Traffic incidents and scenario controls), Phase 30 (Operational metrics dashboard).
- **Components:** `backend/apps/core/realtime/`, `backend/apps/core/api/`, `frontend/src/features/scene3d/` (`SimulationViewer3D.tsx`, `geometry.ts`, `models.ts`, `interpolation.ts`, `v2vOverlay.ts`, `v2vAdapter.ts`), `frontend/src/features/playback/` (`playbackScheduler.ts`, `historyBuffer.ts`, `PlaybackBar.tsx`), `frontend/src/features/simulation/EntityInspector.tsx`
- **Verification Plan:** WebSocket frame serialization tests, client connection lifecycle tests, Three.js mesh rendering verification, temporal interpolation unit tests, playback scheduler tests (fake timers, cadence scaling, non-overlapping requests, terminal stopping), history buffer tests (deep-cloning, deduplication, binary search ordering, bounded retention), V2V overlay unit tests (range extraction, link deduplication, bounded animation queues, pause freezing, history buffer immutability), and component tests (`websocket-client.test.ts`, `api-client.test.ts`, `geometry.test.ts`, `interpolation.test.ts`, `models.test.ts`, `playback.test.ts`, `v2v.test.ts`, `components.test.tsx`: 147 tests passing).
- **Current Status:** `IN PROGRESS (Phases 21–27 COMPLETED & TESTED; 147 frontend tests, 1,097 backend tests passing; Phase 28 Adaptive Routing Visualization Next)`


