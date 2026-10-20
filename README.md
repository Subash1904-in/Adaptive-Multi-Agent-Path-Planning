# Adaptive Multi-Agent Path Planning for Autonomous Vehicles

[![CI Pipeline](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/workflows/ci.yml/badge.svg)](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Node Version](https://img.shields.io/badge/node-22.x-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Important Notice:** This software is developed solely as an academic research and educational simulation platform. It is not intended, certified, or validated for safety-critical real-world autonomous vehicle control.

---

## 1. Project Overview

The **Adaptive Multi-Agent Path Planning (AMAPP)** platform is a comprehensive simulation framework designed to explore decentralized coordination, dynamic route optimization, and collision avoidance among autonomous vehicles operating in realistic traffic conditions.

### Key Capabilities
- **Decentralized Vehicle-to-Vehicle (V2V) Communication:** Peer-to-peer message dissemination within a spatial communication radius, simulating channel noise, packet loss, and latency.
- **Adaptive Path Planning & Hazard Avoidance:** Real-time dynamic graph-based rerouting (A* / Dijkstra) triggered by hazard and congestion alerts.
- **AI-Based Decision-Making & Reinforcement Learning:** Integrated Gymnasium multi-agent environment trained with Stable-Baselines3 for intelligent route selection.
- **Real-World Road Networks:** Ingestion and parsing of OpenStreetMap (OSM) geometries alongside a deterministic offline fallback grid.
- **Dynamic Traffic & Pedestrian Elements:** Signalized intersections, pedestrian crosswalks, jaywalking events, and emergency vehicle priority corridors.
- **Real-Time 3D Visualization Dashboard:** Interactive web dashboard powered by Django Channels (WebSockets) and Three.js for real-time telemetry rendering and simulation steering.

---

## 2. Technology Stack

- **Authoritative Backend Simulation:** Python 3.11, NetworkX, NumPy, SciPy
- **Web & Streaming Framework:** Django, Django REST Framework, Django Channels, Daphne (ASGI)
- **Reinforcement Learning:** Gymnasium, Stable-Baselines3
- **Map & Geospatial Data:** OpenStreetMap (OSM), OSMnx
- **3D Visualization & Frontend:** TypeScript, Three.js, Vite
- **Testing & Quality Assurance:** pytest, pytest-cov, Ruff, ESLint
- **DevOps & Reproducibility:** GitHub Actions, Docker, Docker Compose

---

## 3. The 14 Functional Requirements

The platform is designed around 14 core functional requirements defined in `Project_Objective_and_Requirements.pdf`:

1. **Vehicle-to-Vehicle (V2V) Communication**
2. **Multi-Agent Autonomous Vehicle Environment**
3. **Real-World Map Integration**
4. **Traffic and Pedestrian Simulation**
5. **Motion Planning and Performance Benchmarking**
6. **Decentralized Vehicle Communication**
7. **Adaptive Path Planning**
8. **AI-Based Decision-Making**
9. **Collision Detection and Avoidance**
10. **Emergency Vehicle Priority**
11. **Communication Range Detection**
12. **Communication Failure Handling**
13. **AI Model Training Using Reinforcement Learning**
14. **Real-Time 3D Visualization and Interactive Dashboard**

For complete status and mapping, see [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md).

---

## 4. System Architecture

For architectural specifications, data contracts, and component boundaries, refer to [ARCHITECTURE.md](ARCHITECTURE.md).

```text
AMAPP Architecture
├── Frontend (Three.js 3D Scene + HUD Dashboard)
│    ↕ (WebSockets JSON stream + REST API)
├── Backend Server (Django Channels ASGI + Daphne + DRF)
│    ↕ (Internal Memory / Direct API)
├── Simulation Engine (Clock, Spatial Grid, Map Graph, Agents)
│    ├── Decentralized V2V Message Network
│    ├── Collision & Headway Safety System
│    └── Adaptive Path Planner (A*)
└── RL Subsystem (Gymnasium Multi-Agent Environment + SB3 Policy)
```

---

## 5. Development Strategy (40 Incremental Phases)

This project follows a strict 40-phase incremental development roadmap. Each phase delivers a functional, tested increment without premature code generation.

Current status and ongoing progress are tracked in [PROJECT_STATUS.md](PROJECT_STATUS.md).

---

## 6. Getting Started & Development Setup

### 6.1 Prerequisites
- **Python:** 3.11.x (verified with Python 3.11.9)
- **Node.js:** 22.x or 20.x LTS (verified with Node v22.18.0)
- **npm:** 10.x
- **Git:** 2.40+

### 6.2 Virtual Environment & Dependency Installation

#### Windows (PowerShell)
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install runtime and development dependencies
pip install -r requirements-dev.txt
```

#### Linux / macOS (Bash / Zsh)
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install runtime and development dependencies
pip install -r requirements-dev.txt
```

### 6.3 Environment Configuration
Copy the template `.env.example` to create your local `.env`:
```bash
cp .env.example .env
```
Default parameters are pre-configured for local development. **Never commit `.env` to version control.**

### 6.4 Starting the Development Server
```bash
python backend/manage.py check
python backend/manage.py runserver 127.0.0.1:8000
```
> *Notice:* Django's built-in development server is intended for development and testing only, not for production deployment.

### 6.5 Health Check Endpoint
Once the server is running, query the health endpoint:
```bash
# Using curl or browser
curl http://127.0.0.1:8000/api/v1/health/
```
Expected JSON Response (`HTTP 200 OK`):
```json
{
  "status": "healthy",
  "service": "amapp-backend",
  "version": "1.0.0"
}
```

### 6.6 Running Lint & Automated Tests
```bash
# Run Ruff linting across backend code
ruff check backend

# Run automated tests via pytest
pytest

# Run tests with coverage report and 80% threshold enforcement
pytest --cov=backend/apps/core --cov-report=term-missing --cov-fail-under=80
```

### 6.7 OpenStreetMap Road Network Import & Offline Fallback
The platform supports ingesting real-world road networks from OpenStreetMap via OSMnx:
- **Dependency:** `osmnx>=2.0.0,<2.1.0` is declared in `requirements.txt`.
- **Offline Reliability:** All automated unit tests run 100% offline using mock fixtures.
- **Deterministic Fallback:** When OSMnx is not installed or when Overpass queries fail/timeout, `import_osm_road_network(config)` seamlessly falls back to the Phase 4 deterministic synthetic city grid when `allow_fallback=True`.
### 6.8 Route Planning Baseline (Dijkstra, A* and Travel-Time Routing)
The platform includes a dedicated, high-performance shortest-path route planner under `backend/apps/core/routing/`:
- **Algorithms:** Dijkstra search (`dijkstra_search`) and custom A* search (`astar_search`).
- **Cost Modes:** Shortest distance (`CostMode.DISTANCE`, meters) and fastest estimated travel time (`CostMode.TRAVEL_TIME`, seconds).
- **Road Closures:** Pass `closed_edge_ids={"edge_id"}` to simulate construction or incident closures without mutating the road network.
- **Python API Usage Example:**
  ```python
  from apps.core.routing import find_route

  # Find fastest route using A*
  result = find_route(
      road_graph,
      start_node_id="node_1",
      destination_node_id="node_10",
      algorithm="astar",
      cost_mode="travel_time",
  )
  print(f"Path nodes: {result.node_ids}, Duration: {result.estimated_duration_s:.1f}s")
  ```

### 6.9 Vehicle Kinematics and Agent Lifecycle
The platform includes an individual vehicle kinematics and route-following coordinator under `backend/apps/core/kinematics/`:
- **Models:** Point-mass bounded constant-acceleration kinematics (`integrate_motion`), heading calculation (`compute_heading`), and planar interpolation (`interpolate_position`).
- **VehicleAgent Coordinator:** Tracks segment traversal, orientation heading, distance along segments, destination arrival, and lifecycle transitions (`IDLE`, `EN_ROUTE`, `BLOCKED`, `ARRIVED`).
- **Python API Usage Example:**
  ```python
  from apps.core.domain.models import Vehicle
  from apps.core.kinematics import KinematicsConfig, VehicleAgent

  # Create vehicle and agent
  vehicle = Vehicle(id="veh_01", position=start_pos, speed_mps=0.0)
  agent = VehicleAgent(vehicle=vehicle, road_graph=road_graph, route=route)

  # Start journey and step discrete time
  agent.start()
  step_result = agent.step(dt=0.5)  # Advance 0.5s
  print(f"Position: ({step_result.new_position.x:.1f}, {step_result.new_position.y:.1f}), Speed: {step_result.new_speed_mps:.1f} m/s")
  ```

### 6.10 Authoritative Simulation Clock and World State (Phase 08)
- **Subsystem:** Discrete fixed-step simulation engine under `backend/apps/core/simulation/`.
- **Key Classes:** `SimulationClock`, `WorldState`, `SimulationEngine`, `EngineStatus`, `WorldSnapshot`, `TickResult`.
- **Capabilities:** Authoritative integer tick tracking, floating-point drift elimination, graph compatibility validation, stable agent identifier ordering, atomic rollback on stepping failures, pause/resume/single-step, and baseline reset.
- **Python API Usage Example:**
  ```python
  from apps.core.domain.models import SimulationConfig
  from apps.core.simulation import SimulationEngine, WorldState

  # Create world and engine
  world = WorldState(road_graph=road_graph, config=SimulationConfig(time_step_s=0.1))
  world.add_agent(agent1)
  world.add_agent(agent2)
  engine = SimulationEngine(world=world)

  # Execute 10 discrete simulation ticks
  tick_results = engine.run(ticks=10)
  print(f"Current tick: {engine.current_tick}, Elapsed time: {engine.elapsed_time_s}s")
  ```

### 6.11 Traffic Signals and Intersection Management (Phase 09)
- **Subsystem:** Deterministic traffic signal subsystem under `backend/apps/core/signals/`.
- **Key Classes:** `TrafficSignalController`, `SignalCycleConfig`, `SignalSnapshot`, `SignalQueryResult`.
- **Capabilities:** Strict cyclic phase progression ($\text{RED} \to \text{GREEN} \to \text{YELLOW} \to \text{RED}$), simulation-time synchronization without drift ($\tau = (t_{\text{sim}} + t_{\text{offset}}) \pmod T$), intersection approach edge lookups, time-to-green and time-to-red query API, and atomic rollback integration.
- **Python API Usage Example:**
  ```python
  from apps.core.domain.enums import TrafficSignalState
  from apps.core.domain.models import TrafficSignal
  from apps.core.signals import SignalCycleConfig, TrafficSignalController

  # Configure cycle (30s green, 5s yellow, 30s red)
  cfg = SignalCycleConfig(green_duration_s=30.0, yellow_duration_s=5.0, red_duration_s=30.0)
  signal = TrafficSignal(id="sig_01", node_id="node_int", state=TrafficSignalState.RED)
  controller = TrafficSignalController(signal=signal, config=cfg, road_graph=road_graph)

  # Query phase and transition timing
  query = controller.query(sim_time_s=15.0)
  print(f"State: {query.state}, Time to Green: {query.time_to_green_s}s, Time to Red: {query.time_to_red_s}s")
  ```

### 6.12 Scenario Orchestration and Simulation Configuration (Phase 10)
- **Subsystem:** Reusable scenario configuration, builder, and execution runner under `backend/apps/core/scenarios/`.
- **Key Classes:** `ScenarioDefinition`, `ScenarioMetadata`, `VehicleScenarioDefinition`, `RoadNetworkDefinition`, `ScenarioBuilder`, `ScenarioRunner`, `ScenarioExecutionResult`, `TerminationReason`.
- **Capabilities:** Typed immutable scenario configurations, structural and graph compatibility validation, unified runtime object assembly, initial route planning, traffic signal registration, discrete execution orchestration, arrival/tick termination semantics, and bit-identical reset/replay.
- **Python API Usage Example:**
  ```python
  from apps.core.scenarios import (
      ScenarioBuilder,
      ScenarioRunner,
      create_single_vehicle_scenario,
  )

  # Load or construct a validated scenario definition
  scenario = create_single_vehicle_scenario(time_step_s=0.1, max_ticks=200)

  # Build authoritative runtime objects
  context = ScenarioBuilder(scenario=scenario).build()

  # Execute scenario to completion
  runner = ScenarioRunner(context=context)
  result = runner.run_to_completion()
  print(f"Terminated: {result.termination_reason}, Arrived: {result.arrived_count}/{result.total_vehicles}, Ticks: {result.completed_ticks}")

  # Deterministic replay: reset restores exact baseline state
  runner.reset()
  replay_result = runner.run_to_completion()
  assert result.to_dict() == replay_result.to_dict()
  ```

### 6.13 V2V Communication Protocol and Spatial Peer Discovery (Phase 11)
- **Subsystem:** Deterministic in-memory V2V communication subsystem under `backend/apps/core/communication/`.
- **Key Classes:** `V2VMessagePacket`, `VehicleStatusPayload`, `CommunicationConfig`, `SpatialPeerDiscovery`, `SimulatedCommunicationNetwork`, `BroadcastScheduler`, `CommunicationMetrics`.
- **Capabilities:** Typed immutable message packets, deterministic JSON serialization/deserialization, Euclidean spatial peer discovery ($d \le R$, 50m default) with exact boundary inclusion and self-exclusion, in-memory network with `NEXT_TICK` (default) and `SAME_TICK` delivery, deduplication cache, expiry enforcement, endpoint availability and seeded packet-loss simulation, periodic broadcast scheduling, and atomic simulation engine rollback.
- **Python API Usage Example:**
  ```python
  from apps.core.communication import (
      CommunicationConfig,
      DeliveryPolicy,
      SimulatedCommunicationNetwork,
      SpatialPeerDiscovery,
      create_status_message,
  )
  from apps.core.domain.models import Vehicle
  from apps.core.domain.values import Position2D

  # 1. Instantiate vehicles
  v1 = Vehicle(id="veh_A", position=Position2D(x=0.0, y=0.0), speed_mps=10.0)
  v2 = Vehicle(id="veh_B", position=Position2D(x=30.0, y=0.0), speed_mps=8.0)

  # 2. Discover spatial peers within 50m range (30m <= 50m -> discovered)
  discovery = SpatialPeerDiscovery(range_m=50.0)
  peers = discovery.find_peers("veh_A", v1.position, {"veh_A": v1.position, "veh_B": v2.position})
  print(f"Discovered peers: {peers}")  # ['veh_B']

  # 3. Create typed status message packet
  msg = create_status_message(v1, current_time_s=1.0, sequence_number=0, ttl_s=2.0)

  # 4. Transmit over in-memory network
  config = CommunicationConfig(enabled=True, range_m=50.0, delivery_policy=DeliveryPolicy.SAME_TICK)
  network = SimulatedCommunicationNetwork(config=config)
  network.register_participant("veh_A")
  network.register_participant("veh_B")

  receivers = network.broadcast(msg, {"veh_A": v1.position, "veh_B": v2.position}, current_time_s=1.0)
  inbox = network.get_inbox("veh_B")
  print(f"Delivered to: {receivers}, veh_B inbox count: {len(inbox)}")
  ```

### 6.14 Dynamic Neighbor Tables, Heartbeats, and Loss Detection (Phase 12)
- **Subsystem:** Dynamic neighbor table tracking, heartbeat freshness, and timeout loss detection under `backend/apps/core/communication/`.
- **Key Classes:** `NeighborTable`, `NeighborManager`, `NeighborRecord`, `NeighborStatus`, `StaleNeighborPolicy`, `NeighborTableSnapshot`, `NeighborMetrics`.
- **Capabilities:** Per-vehicle neighbor tables tracking communicating peers, last observed position, distance, speed, heading, sequence number, and timestamps. Simulation-time heartbeats, stale detection on timeout ($t_{\text{now}} - t_{\text{last\_hb}} \ge T_{\text{timeout}}$), grace-period removal, fresh heartbeat restoration, strict self-exclusion, and atomic rollback guarantees.
- **Python API Usage Example:**
  ```python
  from apps.core.communication import (
      CommunicationConfig,
      DeliveryPolicy,
      SimulatedCommunicationNetwork,
      create_status_message,
  )
  from apps.core.domain.models import Vehicle
  from apps.core.domain.values import Position2D

  # 1. Setup network with neighbor tracking enabled
  config = CommunicationConfig(
      enabled=True,
      range_m=50.0,
      delivery_policy=DeliveryPolicy.SAME_TICK,
      heartbeat_timeout_s=0.5,
      stale_grace_period_s=1.0,
  )
  network = SimulatedCommunicationNetwork(config=config)
  network.register_participant("veh_A")
  network.register_participant("veh_B")

  # 2. Transmit periodic heartbeat from veh_B
  v_b = Vehicle(id="veh_B", position=Position2D(x=25.0, y=0.0), speed_mps=12.0)
  packet = create_status_message(v_b, current_time_s=1.0, sequence_number=1)
  network.broadcast(
      packet,
      {"veh_A": Position2D(x=0.0, y=0.0), "veh_B": v_b.position},
      current_time_s=1.0,
  )

  # 3. Update neighbor tables from inboxes
  network.update_neighbor_tables({"veh_A": Position2D(x=0.0, y=0.0)}, current_time_s=1.0)
  table_a = network.get_neighbor_table("veh_A")
  neighbor_b = table_a.get_neighbor("veh_B")
  print(
      f"Neighbor: {neighbor_b.vehicle_id}, Status: {neighbor_b.status.value}, "
      f"Distance: {neighbor_b.last_distance_m}m"
  )
  # Output: Neighbor: veh_B, Status: active, Distance: 25.0m
  ```

### 6.15 Decentralized V2V Coordination and Shared Traffic Knowledge (Phase 13)
- **Subsystem:** Decentralized traffic information exchange and belief state management under `backend/apps/core/coordination/`.
- **Key Classes:** `CongestionReport`, `RoadClosureReport`, `HazardReport`, `VehicleKnowledgeStore`, `InformationFusion`, `DisseminationManager`, `CoordinationManager`, `BeliefRecord`.
- **Capabilities:** Typed traffic reports, vehicle-private knowledge stores (no omniscient global truth), deterministic order-invariant belief fusion, bounded corroboration boost without duplicate inflation, multi-hop dissemination with hop limits and cycle prevention, atomic rollback, and strict route immobility invariant (sharing information only, no automatic route changes).
- **Python API Usage Example:**
  ```python
  from apps.core.coordination import (
      CongestionLevel,
      CongestionReport,
      CoordinationConfig,
      CoordinationManager,
      DisseminationManager,
      ReportType,
  )
  from apps.core.domain.values import Position2D

  # 1. Initialize coordination manager with private stores
  coord_mgr = CoordinationManager(config=CoordinationConfig(enabled=True, max_forwarding_hops=3))
  coord_mgr.register_vehicle("veh_1")
  coord_mgr.register_vehicle("veh_2")

  # 2. Vehicle 1 observes congestion and publishes locally
  report = CongestionReport(
      report_id="cong_e1_001",
      report_type=ReportType.CONGESTION,
      reporting_vehicle_id="veh_1",
      edge_id="e1",
      timestamp_s=5.0,
      congestion_level=CongestionLevel.HIGH,
      congestion_score=0.75,
      confidence=0.8,
  )
  coord_mgr.publish_local_observation("veh_1", report)

  # 3. Create V2V packet and deliver to Vehicle 2
  packet = DisseminationManager.create_report_packet(
      sender_id="veh_1",
      sender_position=Position2D(x=0.0, y=0.0),
      sender_heading_rad=0.0,
      sender_speed_mps=10.0,
      sequence_number=1,
      report=report,
      current_time_s=5.0,
  )
  coord_mgr.process_inbox_messages("veh_2", [packet], current_time_s=5.0)

  # 4. Inspect vehicle-private knowledge store and derived belief
  store_v2 = coord_mgr.get_store("veh_2")
  belief = store_v2.get_belief("e1")
  print(f"Vehicle 2 belief on e1: {belief.attributes['congestion_level']}, conf={belief.confidence}")
  # Note: Vehicle 2's route is strictly NOT modified solely by receiving this report.
  ```

### 6.16 Communication Latency, Packet Loss, and Network Degradation (Phase 14)
- **Subsystem:** Deterministic network impairment and degradation simulation under `backend/apps/core/communication/`.
- **Key Classes:** `InTransitPacket`, `DeliveryStatus`, `ChannelState`, `TemporaryOutage`, `TemporaryLinkOutage`, `CommunicationConfig`, `SimulatedCommunicationNetwork`.
- **Capabilities:** Multi-tick in-transit packet transit queues, configurable fixed and uniform latency, exact simulation tick boundary delivery policy, deterministic packet loss with isolated seeded PRNG, distance-dependent planar attenuation ($P_{\text{loss}} = (d/R)^\gamma$), two-state Markov Gilbert-Elliott burst-loss model, temporary participant and link outages, network partition boundaries, communication recovery without local knowledge wiping, granular drop metrics, and full simulation engine atomic rollback.
- **Python API Usage Example:**
  ```python
  from apps.core.communication import (
      CommunicationConfig,
      DeliveryStatus,
      SimulatedCommunicationNetwork,
      V2VMessagePacket,
      V2VMessageType,
  )
  from apps.core.domain.values import Position2D

  # 1. Configure network with 0.2s fixed latency and 10% packet loss
  config = CommunicationConfig(
      enabled=True,
      range_m=50.0,
      min_latency_s=0.2,
      max_latency_s=0.2,
      packet_loss_rate=0.0,  # Or set > 0.0 for deterministic loss
      latency_seed=42,
  )
  network = SimulatedCommunicationNetwork(config=config)
  network.register_participant("veh_A")
  network.register_participant("veh_B")

  # 2. Transmit message at t=1.0s
  packet = V2VMessagePacket(
      message_id="msg_001",
      sender_id="veh_A",
      sequence_number=1,
      timestamp_s=1.0,
      sender_position=Position2D(x=0.0, y=0.0),
      sender_heading_rad=0.0,
      sender_speed_mps=10.0,
      message_type=V2VMessageType.HEARTBEAT,
  )
  candidates = {"veh_A": Position2D(x=0.0, y=0.0), "veh_B": Position2D(x=20.0, y=0.0)}
  network.broadcast(packet, candidates, current_time_s=1.0)

  # 3. Inspect in-transit status (scheduled for delivery at t=1.2s)
  print(f"In-transit count at t=1.0s: {network.get_in_transit_count()}")  # 1
  assert network.get_inbox("veh_B") == []  # Not delivered yet!

  # 4. Advance clock: at t=1.1s it remains in transit; at t=1.2s it is delivered
  network.advance_tick(current_time_s=1.1)
  assert network.get_inbox("veh_B") == []  # Still in flight

  network.advance_tick(current_time_s=1.2)
  inbox = network.get_inbox("veh_B")
  print(f"Delivered at t=1.2s: {[m.message_id for m in inbox]}")  # ['msg_001']
  ```

### 6.17 Adaptive Rerouting and Dynamic Route Adjustment (Phase 15)
- **Subsystem:** Dynamic route cost evaluation, benefit hysteresis, cooldowns, and safe route suffix replacement under `backend/apps/core/routing/`.
- **Key Classes:** `DynamicEdgeCostEvaluator`, `DynamicRouteAdapter`, `AdaptiveRoutingConfig`, `AdaptiveRoutingMetrics`, `RerouteDecision`, `VehicleAgent.replace_remaining_route`.
- **Capabilities:** Vehicle-private dynamic edge costs ($C_v(e) = C_0(e) \cdot M_{\text{congestion}}(e) + P_{\text{hazard}}(e)$), avoidance of roads reported closed ($C_v(e) = \infty$), candidate path planning, pro-rated remaining route cost evaluation, benefit hysteresis ($\Delta C \ge \max(\Delta C_{\min}, \rho C_{\text{current}})$), rerouting cooldowns, repeat recalculation suppression via belief fingerprinting, safe active route suffix replacement preserving kinematic continuity and vehicle destination (`finish_edge` continuation policy), deterministic structured decisions, and full simulation engine integration with atomic rollback.
- **Python API Usage Example:**
  ```python
  from apps.core.coordination import (
      ReportType,
      RoadClosureReport,
      RoadClosureStatus,
      VehicleKnowledgeStore,
  )
  from apps.core.routing import (
      AdaptiveRoutingConfig,
      DynamicRouteAdapter,
      RerouteDecisionType,
  )
  from apps.core.scenarios.examples import create_adaptive_reroute_closure_scenario
  from apps.core.scenarios.runner import run_scenario

  # Run deterministic scenario demonstrating vehicle choosing an alternative route around closure
  scenario = create_adaptive_reroute_closure_scenario(max_ticks=30)
  result = run_scenario(scenario)
  assert result.is_success
  print(f"Vehicle safely rerouted around closure in {result.completed_ticks} ticks.")
  ```

### 6.18 Collision Detection, Safe Separation, and Avoidance (Phase 16)
- **Subsystem:** Deterministic geometric collision detection, safe separation, and collision avoidance subsystem under `backend/apps/core/safety/`.
- **Educational Simulation Disclaimer:** This software is an educational and research simulation model. It is NOT certified, verified, or suitable for direct deployment in physical autonomous vehicles.
- **Key Classes:** `OrientedBoundingBox2D`, `check_obb_overlap_sat`, `compute_obb_separation_distance`, `CollisionDetector`, `SafetyPolicy`, `SafetyManager`, `SafetyMetrics`, `SafetyConfig`, `SafetyEvent`.
- **Capabilities:** 2D Oriented Bounding Box (OBB) representation with Separating Axis Theorem (SAT) overlap detection; safe separation distance ($d_{\text{safe}} = d_0 + v_{\text{rel}}^{+} T_r + \frac{v^2}{2 a_{\text{brake}}}$); Time-to-Collision (TTC) estimation; 5-tier risk classification (`COLLISION`, `IMMINENT`, `HIGH_RISK`, `CAUTION`, `SAFE`); controlled deceleration and emergency braking overrides; conservative multi-conflict resolution (selecting strongest valid deceleration); structured near-miss and collision event logging; full SimulationEngine integration with atomic rollback.
- **Python API Usage Example:**
  ```python
  from apps.core.domain.models import Vehicle
  from apps.core.domain.values import Position2D
  from apps.core.kinematics.config import KinematicsConfig
  from apps.core.kinematics.vehicle_agent import VehicleAgent
  from apps.core.safety import CollisionDetector, SafetyConfig, SafetyPolicy
  from apps.core.graph import RoadGraph

  # 1. Setup two approaching vehicles on a collision course
  graph = RoadGraph("safety_demo")
  v1 = Vehicle(id="veh_1", position=Position2D(x=0.0, y=0.0), speed_mps=10.0, heading_rad=0.0)
  v2 = Vehicle(id="veh_2", position=Position2D(x=15.0, y=0.0), speed_mps=10.0, heading_rad=3.14159)

  ag1 = VehicleAgent(v1, graph, config=KinematicsConfig(max_deceleration_mps2=8.0))
  ag2 = VehicleAgent(v2, graph, config=KinematicsConfig(max_deceleration_mps2=8.0))

  # 2. Evaluate pairwise conflict
  detector = CollisionDetector(config=SafetyConfig(enabled=True, min_separation_m=4.0))
  conflicts = detector.detect_all_conflicts([ag1, ag2])

  # 3. Resolve safety policy to obtain braking overrides
  policy = SafetyPolicy(config=SafetyConfig(enabled=True, emergency_decel_mps2=7.0))
  overrides = policy.resolve_conflicts([ag1, ag2], conflicts)

  for vid, override in overrides.items():
      print(f"Vehicle {vid}: Action={override.action_type.value}, Decel={override.target_acceleration_mps2} m/s^2")
  # Vehicles receive emergency braking commands to prevent predicted physical collision!
  ```

### 6.19 Pedestrian Agents, Crosswalks, and Traffic Signals (Phase 17)
- **Module:** `backend/apps/core/pedestrians/`
- **Key Classes:** `PedestrianAgent`, `Crosswalk`, `PedestrianLifecycleState`, `PedestrianSignalState`, `PedestrianConfig`, `PedestrianMetrics`.
- **Capabilities:** Typed pedestrian agents with bounded kinematics and lifecycle states (`IDLE`, `APPROACHING_CROSSWALK`, `WAITING_TO_CROSS`, `CROSSING`, `WALKING`, `ARRIVED`, `BLOCKED`); geometric crosswalk corridor model with longitudinal and lateral 2D projections; signal indication mapping (`RED` -> `WALK`, `YELLOW` -> `CLEARANCE`, `GREEN` -> `DONT_WALK`; unsignalized -> `WALK`); clearance policy ensuring pedestrians crossing continue across the street upon signal change without stranding; vehicle-pedestrian conflict detection using the Phase 16 SAT OBB safety subsystem; authoritative single-clock engine execution; atomic rollback guarantees.
- **Python API Usage Example:**
  ```python
  from apps.core.domain.values import Position2D
  from apps.core.pedestrians import Crosswalk, PedestrianAgent, PedestrianLifecycleState
  from apps.core.simulation import SimulationEngine, WorldState

  # 1. Create a crosswalk corridor across a roadway
  crosswalk = Crosswalk(
      id="cw_main",
      node_id="intersection_1",
      entry_point=Position2D(x=50.0, y=-5.0),
      exit_point=Position2D(x=50.0, y=5.0),
      width_m=4.0,
  )

  # 2. Instantiate a pedestrian approaching the crosswalk
  ped = PedestrianAgent(
      pedestrian_id="ped_01",
      position=Position2D(x=50.0, y=-5.0),
      destination=Position2D(x=50.0, y=5.0),
      desired_speed_mps=1.2,
      crosswalk_id="cw_main",
  )

  # 3. Add to world and step simulation
  world = WorldState()
  world.add_crosswalk(crosswalk)
  world.add_pedestrian(ped)

  engine = SimulationEngine(world=world)
  result = engine.step()
  print(f"Pedestrian state: {ped.state.value}, position: ({ped.position.x}, {ped.position.y})")
  ```

### 6.20 Troubleshooting
- **ModuleNotFoundError for `config` or `apps`:** Ensure you run commands from the repository root or that `backend/` is in `PYTHONPATH`. `backend/manage.py` automatically injects `backend/` into `sys.path`.
- **PowerShell Execution Policy Error:** If `.venv\Scripts\Activate.ps1` is blocked, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
- **Port 8000 in use:** Launch on an alternative port: `python backend/manage.py runserver 127.0.0.1:8001`.

---

## 7. Documentation Directory

- [PROJECT_STATUS.md](PROJECT_STATUS.md): Primary status and handoff notes.
- [ARCHITECTURE.md](ARCHITECTURE.md): Comprehensive system architecture and data models.
- [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md): 14 Functional Requirements traceability matrix.
- [docs/progress/PHASE_00.md](docs/progress/PHASE_00.md): Phase 0 preparation report.
- [docs/progress/PHASE_01.md](docs/progress/PHASE_01.md): Phase 1 audit and blueprint report.
- [docs/progress/PHASE_02.md](docs/progress/PHASE_02.md): Phase 2 scaffold and dev environment report.
- [docs/progress/PHASE_03.md](docs/progress/PHASE_03.md): Phase 3 domain models and simulation contracts report.
- [docs/progress/PHASE_04.md](docs/progress/PHASE_04.md): Phase 4 road graph and deterministic city report.
- [docs/progress/PHASE_05.md](docs/progress/PHASE_05.md): Phase 5 OpenStreetMap import and road network normalization report.
- [docs/progress/PHASE_06.md](docs/progress/PHASE_06.md): Phase 6 route planning baseline (Dijkstra, A* and travel time) report.
- [docs/progress/PHASE_07.md](docs/progress/PHASE_07.md): Phase 7 vehicle kinematics and agent lifecycle report.
- [docs/progress/PHASE_08.md](docs/progress/PHASE_08.md): Phase 8 simulation clock and world state report.
- [docs/progress/PHASE_09.md](docs/progress/PHASE_09.md): Phase 9 traffic signals and intersection management report.
- [docs/progress/PHASE_10.md](docs/progress/PHASE_10.md): Phase 10 scenario orchestration and simulation configuration report.
- [docs/progress/PHASE_11.md](docs/progress/PHASE_11.md): Phase 11 V2V communication protocol and spatial peer discovery report.
- [docs/progress/PHASE_12.md](docs/progress/PHASE_12.md): Phase 12 dynamic neighbor tables, heartbeats, and loss detection report.
- [docs/progress/PHASE_13.md](docs/progress/PHASE_13.md): Phase 13 decentralized V2V coordination and shared traffic knowledge report.
- [docs/progress/PHASE_14.md](docs/progress/PHASE_14.md): Phase 14 communication latency, packet loss, network degradation, and recovery report.
- [docs/progress/PHASE_15.md](docs/progress/PHASE_15.md): Phase 15 adaptive rerouting and dynamic route adjustment report.
- [docs/progress/PHASE_16.md](docs/progress/PHASE_16.md): Phase 16 collision detection, safe separation, and avoidance report.
- [docs/progress/PHASE_17.md](docs/progress/PHASE_17.md): Phase 17 pedestrian agents, crosswalks, and traffic signals report.
- [docs/TESTING.md](docs/TESTING.md): Testing standards, fixtures, and regression policies.
- [docs/API.md](docs/API.md): API and WebSocket telemetry protocol contracts.
- [docs/decisions/ADR-001-modular-simulation-architecture.md](docs/decisions/ADR-001-modular-simulation-architecture.md): Architectural Decision Record on simulation decoupling.

