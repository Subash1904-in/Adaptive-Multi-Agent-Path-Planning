# REQUIREMENTS TRACEABILITY MATRIX

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Source of Truth:** `Project_Objective_and_Requirements.pdf`  
**Current Phase:** Phase 0 (Preparation)  
**Status Legend:**
- `NOT STARTED`: Requirement specified and mapped; implementation not yet begun.
- `IN PROGRESS`: Modules under active development in current phase.
- `IMPLEMENTED`: Code implemented but awaiting complete integration/system testing.
- `TESTED`: Automated unit and integration tests passing with evidence.
- `BLOCKED`: Development impeded by dependencies or unresolved technical blockers.

---

## 1. Traceability Summary Matrix

| Req # | Requirement Name | Implementation Modules | Target Phases | Current Status | Test Coverage |
|---|---|---|---|---|---|
| **FR-01** | Vehicle-to-Vehicle (V2V) Communication | `sim_engine/v2v/` | Phase 10, 14, 26 | `NOT STARTED` | Pending Phase 10 |
| **FR-02** | Multi-Agent Autonomous Vehicle Environment | `sim_engine/agents/`, `sim_engine/core/` | Phase 02, 05, 09 | `NOT STARTED` | Pending Phase 02 |
| **FR-03** | Real-World Map Integration | `sim_engine/map/` | Phase 03, 04, 34 | `NOT STARTED` | Pending Phase 03 |
| **FR-04** | Traffic and Pedestrian Simulation | `sim_engine/safety/`, `sim_engine/pedestrians/` | Phase 18, 19 | `NOT STARTED` | Pending Phase 18 |
| **FR-05** | Motion Planning and Performance Benchmarking | `sim_engine/planning/`, `sim_engine/benchmarks/` | Phase 07, 23, 40 | `NOT STARTED` | Pending Phase 07 |
| **FR-06** | Decentralized Vehicle Communication | `sim_engine/v2v/`, `sim_engine/agents/` | Phase 10, 13 | `NOT STARTED` | Pending Phase 10 |
| **FR-07** | Adaptive Path Planning | `sim_engine/planning/`, `sim_engine/agents/` | Phase 08, 15 | `NOT STARTED` | Pending Phase 08 |
| **FR-08** | AI-Based Decision-Making | `rl_engine/policies/`, `sim_engine/agents/` | Phase 32 | `NOT STARTED` | Pending Phase 32 |
| **FR-09** | Collision Detection and Avoidance | `sim_engine/safety/` | Phase 16, 17 | `NOT STARTED` | Pending Phase 16 |
| **FR-10** | Emergency Vehicle Priority | `sim_engine/agents/`, `sim_engine/safety/` | Phase 20, 21 | `NOT STARTED` | Pending Phase 20 |
| **FR-11** | Communication Range Detection | `sim_engine/v2v/`, `sim_engine/core/` | Phase 11, 36 | `NOT STARTED` | Pending Phase 11 |
| **FR-12** | Communication Failure Handling | `sim_engine/v2v/`, `sim_engine/agents/` | Phase 12, 22 | `NOT STARTED` | Pending Phase 12 |
| **FR-13** | AI Model Training Using Reinforcement Learning | `rl_engine/` | Phase 28, 29, 30, 31 | `NOT STARTED` | Pending Phase 28 |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | `backend/channels/`, `frontend/` | Phase 26, 33-37 | `NOT STARTED` | Pending Phase 26 |

---

## 2. Detailed Requirement Breakdown

### FR-01: Vehicle-to-Vehicle (V2V) Communication
- **Requirement Statement:** Establish communication between nearby autonomous vehicles; enable vehicles to exchange traffic information, accident alerts, obstacles, and route updates.
- **Components:** `sim_engine/v2v/message.py`, `sim_engine/v2v/channel.py`, `sim_engine/v2v/dispatcher.py`
- **Verification Plan:** Unit tests for packet serialization, broadcast routing, and message queue delivery between neighboring vehicles within range.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Protocol design in Phase 10, hazard flooding in Phase 14.

---

### FR-02: Multi-Agent Autonomous Vehicle Environment
- **Requirement Statement:** Develop multiple independent autonomous vehicle agents, each with its own destination, speed, route, and decision-making capabilities.
- **Components:** `sim_engine/agents/vehicle.py`, `sim_engine/agents/state.py`, `sim_engine/core/lifecycle.py`
- **Verification Plan:** Multi-agent lifecycle tests verifying independent trajectories, individual odometry, and distinct origin-destination pairs.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Core agent kinematics in Phase 05, agent pool management in Phase 09.

---

### FR-03: Real-World Map Integration
- **Requirement Statement:** Integrate OpenStreetMap to obtain real-world road networks; support actual roads, intersections, lanes, and navigation routes.
- **Components:** `sim_engine/map/osm_loader.py`, `sim_engine/map/graph.py`, `data/osm/`
- **Verification Plan:** Tests for OSM XML/OSMnx graph ingestion, node-edge connectivity, lane count attributes, and offline deterministic fallback grid.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** NetworkX graph model in Phase 03, OSM parser and converter in Phase 04.

---

### FR-04: Traffic and Pedestrian Simulation
- **Requirement Statement:** Simulate realistic traffic conditions and vehicle movements; include traffic signals, congestion, pedestrian crossings, and unexpected road conditions.
- **Components:** `sim_engine/safety/traffic_signals.py`, `sim_engine/pedestrians/pedestrian.py`, `sim_engine/map/crosswalk.py`
- **Verification Plan:** State machine tests for 4-phase traffic lights, pedestrian crosswalk crossing logic, and vehicle yield enforcement.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Traffic signal state machines in Phase 18, dynamic pedestrians in Phase 19.

---

### FR-05: Motion Planning and Performance Benchmarking
- **Requirement Statement:** Implement and compare different path-planning algorithms; evaluate travel time, collision rate, route efficiency, safety, and communication performance.
- **Components:** `sim_engine/planning/`, `sim_engine/benchmarks/metrics.py`, `sim_engine/benchmarks/evaluator.py`
- **Verification Plan:** Comparative benchmark test suite evaluating A*, Dijkstra, and RL routes against standard baseline scenarios.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Planning baselines in Phase 07, automated benchmarking runner in Phase 23.

---

### FR-06: Decentralized Vehicle Communication
- **Requirement Statement:** Enable vehicles to communicate directly without depending on a central communication controller; support independent information sharing and coordination between vehicles.
- **Components:** `sim_engine/v2v/protocol.py`, `sim_engine/agents/knowledge_base.py`
- **Verification Plan:** Multi-agent test proving vehicles communicate in peer-to-peer fashion without centralized dispatch or global oracle knowledge.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Decentralized peer transport in Phase 10, private agent belief state in Phase 13.

---

### FR-07: Adaptive Path Planning
- **Requirement Statement:** Implement dynamic route planning using algorithms such as A*; automatically calculate alternative routes during traffic congestion, accidents, or road blockages.
- **Components:** `sim_engine/planning/dynamic_astar.py`, `sim_engine/planning/cost_field.py`
- **Verification Plan:** Rerouting tests verifying an agent recalculates path when downstream edges receive hazard flags via V2V or sensor detection.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Dynamic cost field in Phase 08, adaptive reroute triggers in Phase 15.

---

### FR-08: AI-Based Decision-Making
- **Requirement Statement:** Develop an intelligent decision-making system for autonomous vehicles; enable vehicles to independently accept or reject route suggestions based on traffic conditions, safety, and travel efficiency.
- **Components:** `rl_engine/policies/decision_engine.py`, `sim_engine/agents/controller.py`
- **Verification Plan:** Evaluation tests verifying agent evaluates candidate paths and rationally selects optimal route under conflicting traffic suggestions.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Decision policy integration in Phase 32.

---

### FR-09: Collision Detection and Avoidance
- **Requirement Statement:** Detect nearby vehicles, pedestrians, and obstacles; implement collision avoidance mechanisms and maintain safe distances.
- **Components:** `sim_engine/safety/collision.py`, `sim_engine/safety/idm.py`, `sim_engine/safety/emergency_brake.py`
- **Verification Plan:** Geometric overlap tests, Time-To-Collision (TTC) calculations, and deceleration validation preventing rear-end and intersection collisions.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Spatial collision engine in Phase 16, safe spacing / IDM in Phase 17.

---

### FR-10: Emergency Vehicle Priority
- **Requirement Statement:** Identify emergency vehicles such as ambulances; enable nearby vehicles to safely adjust their movement and provide priority.
- **Components:** `sim_engine/agents/emergency_vehicle.py`, `sim_engine/safety/priority_yielding.py`
- **Verification Plan:** Scenario test with ambulance broadcasting siren beacon, confirming surrounding vehicles transition to yielding state and create corridor.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Emergency vehicle definitions in Phase 20, yielding protocols in Phase 21.

---

### FR-11: Communication Range Detection
- **Requirement Statement:** Implement configurable vehicle communication ranges; automatically establish communication when vehicles enter the specified communication radius.
- **Components:** `sim_engine/v2v/proximity.py`, `sim_engine/core/spatial_index.py`
- **Verification Plan:** Geometric radius tests confirming messages pass only when Euclidean distance $d \le R_{\text{comm}}$ and are dropped when $d > R_{\text{comm}}$.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Spatial proximity engine in Phase 11, 3D visualization wave in Phase 36.

---

### FR-12: Communication Failure Handling
- **Requirement Statement:** Detect communication failures, delayed messages, and packet loss; implement fallback mechanisms to maintain safe vehicle operation during communication failures.
- **Components:** `sim_engine/v2v/channel_noise.py`, `sim_engine/agents/fallback_policy.py`
- **Verification Plan:** Injected packet loss/latency test suite ensuring vehicle safely decelerates or relies on onboard sensor envelope when V2V links degrade.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Channel noise simulation in Phase 12, safe fallback policy in Phase 22.

---

### FR-13: AI Model Training Using Reinforcement Learning
- **Requirement Statement:** Develop and train a reinforcement learning model for intelligent route selection; improve vehicle decision-making through interaction with simulated traffic environments.
- **Components:** `rl_engine/envs/ma_nav_env.py`, `rl_engine/training/train_agent.py`, `rl_engine/policies/`
- **Verification Plan:** Gymnasium `check_env` validation, deterministic reward progression tests, and bounded headless training execution.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** Gymnasium environment in Phase 28, reward function in Phase 29, SB3 model in Phase 30, training script in Phase 31.

---

### FR-14: Real-Time 3D Visualization and Interactive Dashboard
- **Requirement Statement:** Develop a web-based dashboard using Django and Three.js; visualize realistic roads, buildings, autonomous vehicles, pedestrians, and traffic conditions; display real-time vehicle movements, V2V communication, route changes, and AI decisions.
- **Components:** `backend/channels/consumer.py`, `frontend/src/scene/`, `frontend/src/ui/`
- **Verification Plan:** WebSocket frame serialization tests, client connection lifecycle tests, Three.js mesh rendering verification, and end-to-end integration tests.
- **Current Status:** `NOT STARTED`
- **Outstanding Work:** WebSocket channels in Phase 26, Three.js client in Phases 33-37.
