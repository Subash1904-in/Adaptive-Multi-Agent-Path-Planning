# REQUIREMENTS TRACEABILITY MATRIX

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Source of Truth:** `Project_Objective_and_Requirements.pdf`  
**Current Phase:** Phase 12 (Dynamic Neighbor Tables, Heartbeats, and Neighbor Loss Detection)  
**Status Legend:**
- `NOT STARTED`: Requirement specified and mapped; functional implementation not yet begun.
- `IN PROGRESS`: Modules under active development in current phase.
- `IMPLEMENTED`: Code implemented but awaiting complete integration/system testing.
- `TESTED`: Automated unit and integration tests passing with evidence.
- `BLOCKED`: Development impeded by dependencies or unresolved technical blockers.

> *Note on Phase 12 (Dynamic Neighbor Tables, Heartbeats, and Neighbor Loss Detection):* Phase 12 implements dynamic, per-vehicle neighbor tables (`NeighborTable`) maintaining communication knowledge (`NeighborRecord`), simulation-time heartbeats and timeout loss detection ($t_{\text{now}} - t_{\text{last\_hb}} \ge T_{\text{timeout}}$), configurable stale and removal policies (`STALE_THEN_REMOVE`, `REMOVE_IMMEDIATELY`, `MARK_STALE`), deterministic sequence tracking, and atomic rollback integration across the simulation engine and world state (624 total tests passing, 96.78% line coverage). This fulfills the dynamic tracking layer for FR-01 (V2V Communication), FR-06 (Decentralized Vehicle Communication), FR-11 (Communication Range Detection), and FR-12 (Communication Failure Handling). Decentralized cooperative coordination (Phase 13), adaptive rerouting (Phase 15), and collision avoidance (Phase 16) remain deferred to their designated future phases.

---

## 1. Traceability Summary Matrix (Aligned with 40-Phase Plan)

| Req # | Requirement Name | Implementation Modules | Target Phases | Current Status | Test Coverage |
|---|---|---|---|---|---|
| **FR-01** | Vehicle-to-Vehicle (V2V) Communication | `backend/apps/core/communication/` | Phase 11, 12, 13, 27 | `NOT STARTED` | Phase 11 & 12 Protocol, Neighbors & Delivery Tested (`test_communication_*.py`) |
| **FR-02** | Multi-Agent Autonomous Vehicle Environment | `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/` | Phase 07, 08, 10, 25 | `NOT STARTED` | Phase 07, 08, 10 Tested (`test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`) |
| **FR-03** | Real-World Map Integration | `backend/apps/core/graph/` | Phase 04, 05, 24 | `NOT STARTED` | Phase 04 & 05 Foundation Tested (`test_osm_*.py`, `test_road_graph.py`) |
| **FR-04** | Traffic and Pedestrian Simulation | `backend/apps/core/signals/`, `sim_engine/safety/`, `sim_engine/pedestrians/` | Phase 09, 17, 25, 29 | `NOT STARTED` | Phase 09 Signals Tested (`test_signals_*.py`) |
| **FR-05** | Motion Planning and Performance Benchmarking | `backend/apps/core/routing/`, `backend/apps/core/kinematics/`, `backend/apps/core/simulation/`, `backend/apps/core/scenarios/` | Phase 06, 07, 08, 10, 30, 31 | `NOT STARTED` | Phase 06–10 Tested (`test_routing_*.py`, `test_kinematics_*.py`, `test_simulation_*.py`, `test_scenarios_*.py`) |
| **FR-06** | Decentralized Vehicle Communication | `backend/apps/core/communication/`, `sim_engine/agents/` | Phase 11, 12, 13 | `NOT STARTED` | Phase 11 & 12 Protocol, Discovery & Neighbors Tested (`test_communication_*.py`) |
| **FR-07** | Adaptive Path Planning | `backend/apps/core/routing/`, `sim_engine/planning/` | Phase 06, 15, 28 | `NOT STARTED` | Phase 06 Baseline Tested (`test_routing_*.py`) |
| **FR-08** | AI-Based Decision-Making | `sim_engine/agents/`, `rl_engine/policies/` | Phase 19, 34 | `NOT STARTED` | Pending Phase 19 |
| **FR-09** | Collision Detection and Avoidance | `sim_engine/safety/` | Phase 16, 37 | `NOT STARTED` | Pending Phase 16 |
| **FR-10** | Emergency Vehicle Priority | `sim_engine/agents/`, `sim_engine/safety/` | Phase 18, 25, 29 | `NOT STARTED` | Pending Phase 18 |
| **FR-11** | Communication Range Detection | `backend/apps/core/communication/discovery.py`, `backend/apps/core/communication/neighbors.py` | Phase 11, 12, 27 | `NOT STARTED` | Phase 11 & 12 Spatial Discovery & Tables Tested (`test_communication_discovery.py`, `test_communication_neighbors.py`) |
| **FR-12** | Communication Failure Handling | `backend/apps/core/communication/network.py`, `backend/apps/core/communication/neighbors.py` | Phase 11, 12, 14, 27 | `NOT STARTED` | Phase 11 & 12 Loss, Timeout & Stale Recovery Tested (`test_communication_heartbeat.py`, `test_communication_network.py`) |
| **FR-13** | AI Model Training Using Reinforcement Learning | `rl_engine/` | Phase 32, 33, 34 | `NOT STARTED` | Pending Phase 32 |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | `backend/`, `frontend/` | Phase 21–30 | `NOT STARTED` | Pending Phase 21 |


---

## 2. Detailed Requirement Breakdown

### FR-01: Vehicle-to-Vehicle (V2V) Communication
- **Requirement Statement:** Establish communication between nearby autonomous vehicles; enable vehicles to exchange traffic information, accident alerts, obstacles, and route updates.
- **Target Phases:** Phase 11 (V2V message protocol), Phase 13 (Decentralized V2V coordination), Phase 27 (V2V visualization).
- **Components:** `sim_engine/v2v/message.py`, `sim_engine/v2v/channel.py`, `sim_engine/v2v/dispatcher.py`
- **Verification Plan:** Unit tests for packet serialization, broadcast routing, and message queue delivery between neighboring vehicles within range.
- **Current Status:** `NOT STARTED`

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
- **Current Status:** `NOT STARTED`

---

### FR-04: Traffic and Pedestrian Simulation
- **Requirement Statement:** Simulate realistic traffic conditions and vehicle movements; include traffic signals, congestion, pedestrian crossings, and unexpected road conditions.
- **Target Phases:** Phase 09 (Vehicle movement and traffic rules), Phase 17 (Pedestrians and traffic signals), Phase 25 (Vehicle and pedestrian visualization), Phase 29 (Traffic incidents and scenario controls).
- **Components:** `sim_engine/safety/traffic_signals.py`, `sim_engine/pedestrians/pedestrian.py`, `sim_engine/map/crosswalk.py`
- **Verification Plan:** State machine tests for 4-phase traffic lights, pedestrian crosswalk crossing logic, and vehicle yield enforcement.
- **Current Status:** `NOT STARTED`

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
- **Components:** `sim_engine/agents/decision_policy.py`, `rl_engine/policies/`
- **Verification Plan:** Evaluation tests verifying agent evaluates candidate paths and rationally selects optimal route under conflicting traffic suggestions.
- **Current Status:** `NOT STARTED`

---

### FR-09: Collision Detection and Avoidance
- **Requirement Statement:** Detect nearby vehicles, pedestrians, and obstacles; implement collision avoidance mechanisms and maintain safe distances.
- **Target Phases:** Phase 16 (Collision detection and avoidance), Phase 37 (Automated testing and regression).
- **Components:** `sim_engine/safety/collision.py`, `sim_engine/safety/idm.py`, `sim_engine/safety/emergency_brake.py`
- **Verification Plan:** Geometric overlap tests, Time-To-Collision (TTC) calculations, and deceleration validation preventing rear-end and intersection collisions.
- **Current Status:** `NOT STARTED`

---

### FR-10: Emergency Vehicle Priority
- **Requirement Statement:** Identify emergency vehicles such as ambulances; enable nearby vehicles to safely adjust their movement and provide priority.
- **Target Phases:** Phase 18 (Emergency vehicle priority), Phase 25 (Vehicle and pedestrian visualization), Phase 29 (Traffic incidents and scenario controls).
- **Components:** `sim_engine/agents/emergency_vehicle.py`, `sim_engine/safety/priority_yielding.py`
- **Verification Plan:** Scenario test with ambulance broadcasting siren beacon, confirming surrounding vehicles transition to yielding state and create corridor.
- **Current Status:** `NOT STARTED`

---

### FR-11: Communication Range Detection
- **Requirement Statement:** Implement configurable vehicle communication ranges; automatically establish communication when vehicles enter the specified communication radius.
- **Target Phases:** Phase 12 (Communication range and peer discovery), Phase 27 (V2V visualization).
- **Components:** `sim_engine/v2v/proximity.py`, `sim_engine/core/spatial_index.py`
- **Verification Plan:** Geometric radius tests confirming messages pass only when Euclidean distance $d \le R_{\text{comm}}$ and are dropped when $d > R_{\text{comm}}$.
- **Current Status:** `NOT STARTED`

---

### FR-12: Communication Failure Handling
- **Requirement Statement:** Detect communication failures, delayed messages, and packet loss; implement fallback mechanisms to maintain safe vehicle operation during communication failures.
- **Target Phases:** Phase 14 (Communication failures and recovery), Phase 27 (V2V visualization).
- **Components:** `sim_engine/v2v/channel_noise.py`, `sim_engine/agents/fallback_policy.py`
- **Verification Plan:** Injected packet loss/latency test suite ensuring vehicle safely decelerates or relies on onboard sensor envelope when V2V links degrade.
- **Current Status:** `NOT STARTED`

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
- **Components:** `backend/channels/consumer.py`, `frontend/src/scene/`, `frontend/src/ui/`
- **Verification Plan:** WebSocket frame serialization tests, client connection lifecycle tests, Three.js mesh rendering verification, and end-to-end integration tests.
- **Current Status:** `NOT STARTED`
