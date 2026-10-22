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
- **Operational Metrics Dashboard & Live KPIs:** Live KPI summary cards, pure SVG travel time distribution histogram and discrete step time-series charts, category filters, time-window query filters, and honest unavailable metric labels without data fabrication.

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

### 6.20 Emergency Vehicle Priority and Dynamic Corridors (Phase 18)
- **Module:** `backend/apps/core/emergency/`
- **Key Classes:** `EmergencyPriorityManager`, `EmergencyCorridorPlanner`, `YieldingPolicy`, `EmergencyType`, `EmergencyLifecycleState`, `PriorityRequest`, `CorridorReservation`, `YieldRequest`, `EmergencyMetrics`.
- **Capabilities:** Authoritative management of emergency vehicles (`AMBULANCE`, `FIRE_ENGINE`, `POLICE`) with numeric priority hierarchy (lower numeric value = higher authority); deterministic tie-breaking `(priority_level, creation_time_s, vehicle_id)`; V2V priority announcements and local awareness stores without omniscient leakage; dynamic corridor reservations with TTL and preemption conflict policies; cooperative yielding policies observing physical deceleration limits, stopping at red traffic signals, respecting crossing pedestrians, and deferring to Phase 16 safety collision avoidance overrides; traffic-signal priority overrides with absolute protection for pedestrians in `CROSSING` state; single-clock engine execution and atomic rollback guarantees.
- **Python API Usage Example:**
  ```python
  from apps.core.emergency import (
      EmergencyPriorityManager,
      EmergencyType,
      EmergencyConfig,
  )
  from apps.core.simulation import SimulationEngine, WorldState

  # 1. Initialize world with emergency support
  world = WorldState(emergency_config=EmergencyConfig(enabled=True, signal_priority_enabled=True))
  world.register_emergency_vehicle("amb_01")

  # 2. Activate emergency vehicle priority
  req = world.emergency_manager.activate_emergency(
      vehicle_id="amb_01",
      emergency_type=EmergencyType.AMBULANCE,
      destination_node_id="node_r2_c2",
      current_time_s=0.0,
      priority_level=2,
  )

  # 3. Advance simulation step
  engine = SimulationEngine(world=world)
  tick_res = engine.step()
  print(f"Active corridors: {tick_res.emergency_metrics['active_corridors']}")
  ```
### 6.21 Pluggable AI Decision Policies for Autonomous Vehicle Agents (Phase 19)
- **Module:** `backend/apps/core/decision/`
- **Key Classes:** `DecisionPolicy`, `RuleBasedDecisionPolicy`, `DecisionManager`, `DecisionConfig`, `CandidateRoute`, `CandidateScore`, `DecisionContext`, `DecisionResult`, `DecisionOutcome`, `DecisionReasonCode`, `DecisionMetrics`.
- **Capabilities:** Pluggable, typed protocol interface for local autonomous vehicle decision-making; deterministic multi-objective candidate scoring balancing estimated travel time, local congestion beliefs, hazard penalties, observation confidence, and route stability hysteresis; strict pre-scoring evaluation of hard safety constraints (known impassable closures, active emergency corridors from Phase 18, structural graph discontinuity) where constraint violations result in $S(c) = -\infty$ and can never be accepted; bounded observation confidence scoring $[0.0, 1.0]$ with automatic deferral when confidence is below configured threshold; route stability bonus and hysteresis threshold preventing rapid route oscillation (anti-flapping); explicit decision outcome and reason taxonomy; complete local knowledge isolation preserving decentralized principles without omniscient cross-vehicle state leakage; authoritative single-clock engine execution and atomic rollback guarantees.
- **Clarification:** This baseline policy is a deterministic, rule-based multi-objective decision system. It does **not** train a neural network or claim to be a learned reinforcement-learning model (RL model training is strictly scheduled for Phases 32–34).
- **Python API Usage Example:**
  ```python
  from apps.core.decision import (
      CandidateRoute,
      DecisionConfig,
      DecisionContext,
      RuleBasedDecisionPolicy,
      DecisionOutcome,
  )

  # 1. Initialize decision config and deterministic baseline policy
  cfg = DecisionConfig(
      enabled=True,
      weight_travel_time=1.0,
      weight_confidence=0.4,
      min_confidence_threshold=0.40,
      min_score_improvement=0.05,
  )
  policy = RuleBasedDecisionPolicy(config=cfg)

  # 2. Assemble agent-isolated decision context with local knowledge
  ctx = DecisionContext(
      agent_id="veh_01",
      current_time_s=10.0,
      destination_node_id="node_dest",
      known_closed_edges=frozenset({"edge_blocked"}),
  )

  # 3. Create candidate routes: one traversing a closed edge, another clear alternative
  infeasible_cand = CandidateRoute(
      candidate_id="route_closure",
      node_ids=("node_start", "node_mid", "node_dest"),
      edge_ids=("edge_blocked", "edge_2"),
      estimated_travel_time_s=15.0,  # Fast travel time, but traverses a closure
      confidence=0.95,
  )
  feasible_cand = CandidateRoute(
      candidate_id="route_open",
      node_ids=("node_start", "node_alt", "node_dest"),
      edge_ids=("edge_open1", "edge_open2"),
      estimated_travel_time_s=22.0,  # Slightly longer, but structurally passable
      confidence=0.90,
  )

  # 4. Evaluate candidates under policy
  result = policy.evaluate(context=ctx, candidates=[infeasible_cand, feasible_cand])

  print(f"Outcome: {result.outcome.value}")  # 'accept'
  print(f"Selected Candidate: {result.selected_candidate_id}")  # 'route_open'
  print(f"Reason: {result.reason_code.value}")  # 'fastest_feasible_route'
  # Infeasible route rejected with S(c) = -inf despite shorter travel time!
  ```
> *Educational Simulation Disclaimer:* This software is designed solely for educational and academic research into multi-agent path planning. It is not designed or certified for real-world vehicular control.

### 6.22 Backend Integration Expansion, Scenario Runner Enhancements, and Advanced Telemetry Streams (Phase 20)
- **Module:** `backend/apps/core/scenarios/` & `backend/apps/core/telemetry/`
- **Key Classes:** `ScenarioRunner`, `RunLifecycleState`, `RunConfig`, `RunMetadata`, `TelemetryCollector`, `TelemetryRecord`, `TelemetryRecordType`, `TelemetryConfig`, `TelemetryDropStats`, `MetricsAggregator`, `RunMetricsSummary`.
- **Capabilities:** Explicit 8-state scenario execution lifecycle (`CREATED` -> `VALIDATING` -> `READY` -> `RUNNING` -> `COMPLETED`/`CANCELLED`/`FAILED`/`LIMIT_REACHED`); cooperative idempotent cancellation between ticks; configurable execution limits (`max_ticks`, `max_duration_s`, `stop_on_all_arrived`); deterministic reproducibility via canonical SHA-256 fingerprints for scenario definition, initial world state, and final world state; active Git commit SHA discovery; bounded in-memory telemetry stream with 14 event categories and zero-drop critical event retention; unified cross-subsystem metrics aggregator; RFC 8259 JSON result export with safe non-finite float sanitization and payload size limits.
- **Python API Usage Example:**
  ```python
  from apps.core.scenarios.examples import create_single_vehicle_scenario
  from apps.core.scenarios.models import RunConfig
  from apps.core.scenarios.runner import ScenarioRunner

  # 1. Create a validated scenario definition and execution runner
  scenario = create_single_vehicle_scenario(max_ticks=20, time_step_s=0.1)
  runner = ScenarioRunner.create(
      scenario=scenario,
      run_config=RunConfig(max_ticks=20, stop_on_all_arrived=True),
  )

  # 2. Run simulation to completion
  result = runner.run_to_completion()
  print(f"Lifecycle State: {result.lifecycle_state.value}")  # 'completed' or 'limit_reached'
  print(f"Completed Ticks: {result.completed_ticks}")

  # 3. Access reproducibility metadata and aggregated metrics
  print(f"Scenario Fingerprint: {result.run_metadata.scenario_fingerprint[:12]}...")
  print(f"Total Distance: {result.metrics_summary['kinematics']['total_distance_traveled_m']} m")

  # 4. Export result to RFC 8259 JSON
  json_output = runner.export_result(indent=2)
  print(f"Export Size: {len(json_output)} bytes")
  ```
> *Educational Simulation Disclaimer:* This software is designed solely for educational and academic research into multi-agent path planning. It is not designed or certified for real-world vehicular control.

### 6.23 Django REST API for Scenario Management, Simulation Runs, and Telemetry (Phase 21)
- **Module:** `backend/apps/core/api/`
- **Key Endpoints:**
  - `GET /api/v1/health/`: Liveness and readiness probe.
  - `GET`, `POST /api/v1/scenarios/`: Enumerate preloaded and custom scenarios, register new scenarios with atomic validation.
  - `POST /api/v1/scenarios/validate/`: Pre-flight scenario validation without persistence.
  - `GET /api/v1/scenarios/{id}/`: Full scenario definition retrieval.
  - `GET`, `POST /api/v1/runs/`: List simulation runs, initialize a new `ScenarioRunner` in `READY` state.
  - `POST /api/v1/runs/{id}/step/`: Advance discrete ticks (`ticks=N` or `run_to_completion=true`).
  - `POST /api/v1/runs/{id}/cancel/`: Cooperative run cancellation.
  - `GET /api/v1/runs/{id}/result/`: Retrieve intermediate or final `ScenarioExecutionResult`.
  - `GET /api/v1/runs/{id}/metrics/`: Unified cross-subsystem metrics aggregated on-the-fly.
  - `GET /api/v1/runs/{id}/telemetry/`: Query bounded in-memory telemetry records by tick range and category.
  - `GET /api/v1/runs/{id}/export/`: Export simulation results as RFC 8259 JSON with payload caps.
- **REST API Usage Example:**
  ```bash
  # Initialize simulation run
  curl -X POST http://127.0.0.1:8000/api/v1/runs/ \
    -H "Content-Type: application/json" \
    -d '{"scenario_id": "scn_single_veh", "run_id": "run_01", "max_ticks": 50}'

  # Step simulation by 10 ticks
  curl -X POST http://127.0.0.1:8000/api/v1/runs/run_01/step/ \
    -H "Content-Type: application/json" \
    -d '{"ticks": 10}'
  ```

### 6.24 Django Channels WebSockets for Live Simulation & Telemetry Streaming (Phase 22)
- **Module:** `backend/apps/core/realtime/` & `backend/config/asgi.py`
- **Key Classes:** `SimulationRunConsumer`, `SimulationEventBroadcaster`, `SimulationOriginValidator`, `SimulationEventType`.
- **WebSocket Endpoint:** `ws://127.0.0.1:8000/ws/v1/runs/{run_id}/`
- **Capabilities:**
  - Real-time asynchronous streaming over Daphne ASGI with standardized JSON event envelopes (`schema_version="1.0.0"`).
  - 21 discrete simulation event types spanning run lifecycle, kinematic snapshots, V2V transmissions, safety conflicts, reroutes, pedestrian crossings, emergency corridors, and autonomous decision scoring.
  - Point-in-time handshake validation with 4404 close code on unknown runs and 4401 on unauthorized origins.
  - Bounded outbound queueing (default 128 messages) per consumer with backpressure drop policy for high-frequency state updates and zero-drop guarantees for critical lifecycle events.
  - Automatic `telemetry.gap` notification on outbound buffer overflow or expired historical replay.
  - Bounded replay from in-memory telemetry buffer using client `subscribe` commands with `from_sequence` or `from_tick` (capped at 500 records).
  - Client interactive simulation steering (`step`, `cancel`, `ping`, `heartbeat`).
- **WebSocket Connection Example (JavaScript):**
  ```javascript
  const socket = new WebSocket("ws://127.0.0.1:8000/ws/v1/runs/run_01/");

  socket.onopen = () => {
    console.log("Connected to AMAPP simulation run channel");
    // Advance simulation by 5 ticks
    socket.send(JSON.stringify({ type: "step", ticks: 5 }));
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`[${data.event_type}] Seq:${data.sequence} Tick:${data.tick}`, data.payload);
  };
  ```
> *Educational Simulation Disclaimer:* This software is designed solely for educational and academic research into multi-agent path planning. It is not designed or certified for real-world vehicular control.

### 6.24 Frontend Dashboard & Interactive 3D Simulation Viewer (Phase 23)
The platform includes an industrial-grade simulation workstation frontend built with React 18, TypeScript, Three.js, and Vite:

#### Prerequisites
- Node.js 22.x LTS (or 20.x LTS)
- npm 10.x

#### Environment Configuration
In the `frontend/` directory, copy the example environment file:
```bash
cd frontend
cp .env.example .env
```
Default configuration:
- `VITE_API_BASE_URL=/api/v1` (proxied by Vite dev server to backend)
- `VITE_WS_BASE_URL=ws://127.0.0.1:8000/ws/v1`

#### Dependency Installation
```bash
cd frontend
npm ci
```

#### Running the Development Server
```bash
npm run dev
```
The application will launch at `http://localhost:5173/` with Hot Module Replacement (HMR).

#### Running Frontend Quality Checks & Tests
```bash
# Run ESLint (flat config)
npm run lint

# Run strict TypeScript type check
npm run typecheck

# Run unit tests via Vitest
npm test

# Build production bundle
npm run build
```

### 6.26 Enhanced 3D City, Road Network & Urban Environment Rendering (Phase 24)
Phase 24 upgrades the Three.js viewport into a navigable 3D urban environment:
- **Layered Road Surface & Anti-Z-Fighting Hierarchy**: Enforces a strict vertical elevation structure: Ground Grid ($Y=-0.10\,\text{m}$), Drivable Asphalt ($Y=0.02\,\text{m}$), Junction Pads ($Y=0.022\,\text{m}$), Multi-Lane Markings ($Y=0.035\,\text{m}$), Zebra Crosswalk Stripes ($Y=0.04\,\text{m}$), and Curbs/Sidewalks ($Y=0.06-0.12\,\text{m}$).
- **Multi-Lane Markings**: Solid white outer borders, solid yellow centerlines on two-way roads, and dashed white lane dividers on multi-lane and one-way roadways.
- **Intersections & Crosswalks**: Smooth junction cylinder pads bridging adjoining roads with zero holes. Zebra crosswalk stripes rendered from explicit scenario definitions or inferred at intersection approaches (clearly designated as visual inference).
- **Curbs & Sidewalks**: Raised concrete sidewalk meshes parallel to roadways set back from intersections to prevent obstruction.
- **Procedural Urban Buildings**: Seeded deterministic PRNG (Mulberry32) generating urban buildings with strict Euclidean distance exclusion zones ($d \ge W_{\text{road}}/2 + W_{\text{sidewalk}} + \text{clearance} + R_{\text{bld}}$), ensuring zero overlap with roads or intersections. Toggleable in HUD. *Clearly designated as procedural visual context, distinct from real mapped structures.*
- **Day & Night Visual Modes**: HUD toggle between neutral daylight illumination and dark night mode with glowing headlights, moonlight, and high-contrast traffic signal heads.
- **Dual Camera Projections**: Seamless HUD switching between 3D Perspective (45° FOV) and 2D Orthographic camera modes with synchronized orbit targets and scales.
- **OpenStreetMap Data Adapter**: Deterministic adapter (`adaptOsmRoadNetwork`) with Equirectangular geographic-to-Cartesian projection (`projectGeoCoordinatesToLocalMeters`) and documented synthetic grid fallback.

### 6.27 Enhanced Vehicle and Pedestrian Models, Animation, and Temporal Interpolation (Phase 25)
Phase 25 enhances dynamic simulation entity rendering in Three.js with temporal smoothness and visual fidelity:
- **Reusable Low-Poly Vehicle Models**: Procedural Three.js compound geometries representing Sedan, Commercial Truck, Transit Bus, EMS Ambulance, Fire Engine, and Unknown fallback. Models reuse static geometries and materials from `ModelAssetCache` to prevent memory allocation per frame or telemetry event.
- **Emergency Vehicle Distinction**: Distinguishable visual styling (medical crosses, roof equipment ladders, color livery) reflecting actual backend data. Subtle alternating 2.5 Hz beacon pulsing without full-screen flashes; automatically reverts to static glow when `prefers-reduced-motion` is enabled.
- **Low-Poly Pedestrian Avatars**: Human proportioned avatars (~1.75m) with articulated legs placed consistently at ground/crosswalk elevation. Includes high-visibility amber styling during `crossing` states and subtle procedural walking animations that never mutate authoritative speed or crossing states.
- **Bounded Temporal Interpolation Engine**: Dedicated `EntityInterpolationBuffer` performing deterministic linear position interpolation and shortest-path angular heading lerp across the $0 \leftrightarrow 2\pi$ wraparound boundary. Eliminates visual jitter and 360° spins while clamping extrapolation ($\le 0.15$s) when simulation halts.
- **Authoritative Boundary Preservation**: Rendering interpolation and animation cues are strictly presentation-only. Backend simulation time, collision detection, and routing decisions remain 100% authoritative.
- **Lifecycle Cleanup**: Run switches and scene unmounts clear interpolation buffers and Three.js scene groups, completely preventing stale entity leakage.

### 6.28 Interactive Simulation Playback, Timeline, and Step Controls (Phase 26)
Phase 26 establishes interactive simulation steering, a visible timeline scrubber, bounded history retention, and concurrent request protection:
- **Interactive Playback Controller (`PlaybackScheduler`)**: Client-driven playback engine with Play/Pause/Resume, single-step (+1 tick), and multi-step (+10 ticks) controls. Automatically halts upon terminal states (`COMPLETED`, `CANCELLED`, `FAILED`, `LIMIT_REACHED`).
- **Cadence Multipliers (Speed Multipliers)**: Configurable playback speeds ($0.5\times, 1\times, 2\times, 5\times$) that adjust the interval between client-issued step requests without modifying backend simulation physics, clock tick durations ($\Delta t_{\text{sim}}$), or vehicle kinematics.
- **Request Overlap & Tab Throttling Protection**: Chained timeout scheduling guarantees the next request is dispatched only after the preceding HTTP response resolves, preventing request queue buildup and browser-tab throttling bursts.
- **Bounded Historical Telemetry Buffer (`SimulationHistoryBuffer`)**: Local FIFO queue retaining up to 500 immutable, deep-cloned historical frame snapshots with binary-search sorted insertion and tick deduplication across REST and WebSocket streams.
- **Distinct Live vs. Historical Review Mode**: Interactive range slider scrubber for exploring past snapshots without issuing backend step requests. Review mode features a cyan `REVIEW (Tick N)` badge, a `Return to Live ➔` button, and a 3D viewport banner.
- **Backend Concurrency Safety**: Non-blocking runner execution lock (`runner._execution_lock.acquire(blocking=False)`) returning HTTP 409 Conflict (`CONCURRENT_STEP_IN_PROGRESS`) if concurrent step requests are dispatched.

### 6.29 V2V Communication Links, Message Animations, and Network-State Overlays (Phase 27)
Phase 27 establishes a real-time, interactive Three.js 3D visualization layer for Vehicle-to-Vehicle (V2V) communications:
- **Authoritative Link Rendering**: Visualizes active communication links in emerald green (`#10b981`) and stale links in dashed amber (`#f59e0b`) extracted directly from vehicle `neighbor_tables`. Unordered pairs $(A, B)$ are canonicalized to prevent redundant geometry allocation.
- **Verified Communication Range Disc**: Displays a semi-transparent planar circle ($y=0.08\,\text{m}$) and outer perimeter ring tracking the inspected vehicle with the exact radius ($R_{\text{comm}} = 50.0\,\text{m}$) configured in backend scenario parameters. Displays `"Unavailable"` if range is unconfigured.
- **Bounded Message Pulse Animations**: Translates luminous spherical wave pulses along Euclidean vectors between sender and receiver agents. Enforces a bounded queue of 20 concurrent pulses and 10 drop indicators with pause-freezing and dynamic playback speed scaling.
- **Network Degradation Overlays**: Visualizes Gilbert-Elliott two-state channel conditions (`GOOD`/`BAD`), packet loss counts (distance vs. burst), active partitions, and overall Packet Delivery Ratio (PDR).
- **Accessible HUD Toggles & Legend**: Glassmorphism viewport overlay controls (`🔗 Links`, `📡 Range`, `✨ Pulses`, `⚠️ Degradation`, `Reset V2V`, `📖 V2V Legend`) with WCAG-compliant `aria-pressed` states and a collapsible V2V Visual Legend panel.
- **Historical Playback Synchronization**: Extended `SimulationFrameSnapshot` with deep-cloned communication state, allowing operators to scrub through timeline history and inspect past V2V network states.

### 6.30 Adaptive Routing Visualization, Route Alternatives, and Rerouting Explanations (Phase 28)
Phase 28 builds an interactive Three.js 3D route visualization and explanation layer grounded strictly in authoritative backend telemetry:
- **Z-Fighting Elimination**: All active routes and candidate paths rendered at elevation $y = 0.12\,\text{m}$ (above asphalt at $0.0$, markings at $0.035$, sidewalks at $0.06$, and V2V range discs at $0.08$). Reroute diamond markers placed at $y = 0.5\,\text{m}$.
- **Planned Baseline vs. Active Dynamic Routes**: Baseline planned paths rendered as dashed slate gray lines (`#94a3b8`); active dynamic routes rendered as solid cyan lines (`#06b6d4`, width 2.5px).
- **Alternative Candidate Paths (Strict Non-Fabrication)**: Evaluated candidate paths rendered as dashed purple lines (`#a855f7`) only when supplied by the backend routing engine. Interactive "Inspect 3D" button in `EntityInspector` highlights the chosen candidate path in solid bright magenta (`#f43f5e`).
- **3D Reroute Decision Markers & Explanations**: Rotating octahedron diamond markers rendered at locations where reroutes occurred: emerald green (`#10b981`) for accepted reroutes, amber (`#f59e0b`) for rejected or insufficient benefit decisions. Displays authoritative backend decision reasons and cost comparisons.
- **Agent Inspector Routing Telemetry**: Displays active route ID, total route distance, remaining distance (`remaining_route_distance_m`), dynamic progress ratio bar, node sequence traversal, rerouting history card, and candidate inspection buttons. Renders `"Not provided by backend"` when remaining distance or ETA is not supplied.
- **Accessible HUD Toggles & Legend**: Dedicated HUD overlay buttons (`🛣️ Active`, `🗺️ Planned`, `🔀 Candidates`, `📍 Markers`, `Reset Routes`, `📖 Route Legend`) with WCAG-compliant `aria-pressed` states and a collapsible Route Visual Legend panel.
- **Historical Playback Synchronization**: Extended `SimulationFrameSnapshot` with deep-cloned routing state, allowing operators to scrub through timeline history and inspect past route configurations and reroute events.

### 6.31 Interactive Traffic Incident Injection and Scenario Controls (Phase 29)
Phase 29 establishes an interactive, operator-facing, backend-authoritative incident management workflow for simulation runs:
- **Simulation-Only Safety Boundary**: Incident controls and physical parameter overrides are strictly simulation-only; never connected to physical or safety-critical traffic hardware.
- **Authoritative Supported Incident Types**:
  - **Road Closure (`road_closure`)**: Complete blockage of a target road edge, dynamically elevating traversal cost to $\infty$ in vehicle A* routing graphs and disseminating closure beliefs via coordination stores to trigger adaptive dynamic rerouting. Removal restores original edge traversability and baseline cost.
  - **Localized Congestion (`congestion`)**: Dynamic application of delay and travel-time multipliers ($1.0\times$ to $5.0\times$) onto specified edges, evaluated by the backend adaptive routing engine during vehicle stepping.
  - **Obstacle / Blocked Segment (`obstacle`)**: Physical hazard placements (`CONSTRUCTION`, `DEBRIS`, `STALLED_VEHICLE`, `STATIC_BARRIER`) localized at road segments, impeding traffic flow.
  - **Traffic Signal Phase Override (`signal_override`)**: Direct operator override of physical intersection traffic signals (forcing `RED`, `YELLOW`, or `GREEN` phases) until deactivated, restoring normal cyclic signal progression.
- **Backend-Authoritative Lifecycle**: REST endpoints (`GET /api/v1/runs/{run_id}/incidents/`, `POST /api/v1/runs/{run_id}/incidents/`, `DELETE /api/v1/runs/{run_id}/incidents/{incident_id}/`) validate edge/signal existence and reject mutations on terminal runs with RFC 7807 400 Bad Request problem details.
- **Live Real-Time Synchronization**: Django Channels WebSocket protocol broadcasts `incident.created` and `incident.removed` events across the simulation run channel group, updating live frontends without polling.
- **Three.js Overlays at Elevation $y = 0.10\,\text{m}$**: Dedicated incident visualization layer situated cleanly between V2V discs ($y = 0.08\,\text{m}$) and vehicle route lines ($y = 0.12\,\text{m}$), eliminating z-fighting. Features crimson road closure barriers, pulsating amber congestion glow, yellow obstacle warning beacons, and signal override phase rings.
- **Operator Control Panel UI (`IncidentControlPanel.tsx`)**: Accessible, collapsible glassmorphism panel allowing operators to inject validated incidents, monitor active incident counts, and remove active incidents with instant visual feedback.
- **Historical Playback Synchronization**: Extended `SimulationFrameSnapshot` with deep-cloned incident state, ensuring historical timeline scrubbing displays authentic historical incident state without mutating active runner state.

### 6.32 Operational Metrics Dashboard, Live KPIs, and Simulation Analytics (Phase 30)
Phase 30 introduces a comprehensive operational metrics dashboard and simulation analytics engine grounded strictly in backend simulation truth without synthetic fabrication:
- **8 Authoritative KPI Cards**: Completion Rate, Average Travel Time, 90th Percentile Travel Time, Intersection Throughput, Collision Rate, Near-Miss Rate, V2V Packet Delivery Ratio (PDR), and Reroute Efficiency.
- **Pure SVG Visualizations**: Travel-time distribution histogram with dynamic binning and discrete step time-series charts with multi-metric toggles.
- **Strict Data Integrity**: Unobserved metrics display explicit `"Unavailable"` badges; historical playback scrubbing isolates historical metrics from active live runs.

### 6.33 Reproducible Routing Benchmarking Framework (Phase 31)
Phase 31 implements an extensible, reproducible benchmarking framework that evaluates route-planning algorithms across standardized simulation scenarios:
- **Supported Routing Algorithms**:
  - `dijkstra`: Optimal shortest-path baseline using Dijkstra's algorithm with static road graph edge weights.
  - `astar`: Optimal shortest-path baseline using A* heuristic search (Euclidean distance admissible heuristic).
  - `static`: Fixed baseline path computed at departure; no dynamic rerouting or incident avoidance.
  - `adaptive`: Dynamic A* routing policy that reacts to incident broadcasts (road closures, congestion delays) and local knowledge stores.
  - `learned`: Extensible architectural stub for future reinforcement-learning policies (Phases 32–34); cleanly raises `UnsupportedAlgorithmError` if invoked before RL training.
- **8 Standardized Benchmark Scenarios**:
  - `bench_grid_sparse_3x3`: Small 3x3 sparse grid baseline (1 vehicle, 50m spacing, 250 ticks).
  - `bench_urban_dense_4x4`: Medium 4x4 urban grid (4 vehicles, signalized intersections, 350 ticks).
  - `bench_traffic_heavy_3x3`: High vehicle density stress test (8 vehicles, 400 ticks).
  - `bench_incident_closure`: Dynamic incident injection comparing static vs. adaptive rerouting (300 ticks).
  - `bench_multi_agent_fleet`: Concurrent multi-agent fleet routing (6 vehicles, 350 ticks).
  - `bench_infeasible_barrier`: Complete network partition testing honest infeasibility handling (100 ticks).
  - `bench_emergency_corridor`: Emergency priority corridor yielding evaluation (300 ticks).
  - `bench_v2v_coordination`: V2V communication and shared obstacle awareness (350 ticks).
- **Seed Policy & Determinism**:
  - Configurable `SeedPolicy` (default: `FIXED`). Seeds all random-number generators (`random`, `numpy.random`, Python hash seeds) and derives per-trial seeds deterministically: $\text{trial\_seed} = \text{base\_seed} + i \times 1000$.
  - Complete scenario and world-state isolation between trials: no mutable graph or vehicle state leaks.
- **Metrics Aggregation & Honest Accounting**:
  - Infeasible routes and failed trials are explicitly recorded with status `INFEASIBLE` / `FAILED` and `None` cost/travel time. They are never converted to zero-cost successes.
  - Statistical summaries compute sample count, success rate, mean, median, min, max, standard deviation, and p90/p95 percentiles.
- **Reproducible Exports (JSON, CSV, Markdown)**:
  - JSON output conforming to schema `amapp.benchmark.v1`.
  - RFC 4180 compliant CSV exports: `trials.csv` (per-trial metrics) and `summary.csv` (aggregated metrics).
  - Human-readable Markdown summary report: `report.md`.
  - Secure path validation preventing path traversal escapes outside designated export directories.
- **CLI Commands (`run_benchmark`)**:
  ```powershell
  # Run bounded smoke test (runs in CI pipeline)
  python backend/manage.py run_benchmark --smoke

  # List available algorithms and scenarios
  python backend/manage.py run_benchmark --list-algorithms
  python backend/manage.py run_benchmark --list-scenarios

  # Run custom benchmark comparison with export
  python backend/manage.py run_benchmark \
    --algorithms dijkstra astar static adaptive \
    --scenarios bench_grid_sparse_3x3 bench_incident_closure \
    --trials 3 \
    --seed 42 \
    --export-dir artifacts/benchmark_results
  ```

### 6.34 Gymnasium-Compatible Reinforcement Learning Environment (Phase 32)
The platform exposes deterministic Gymnasium environments for route-selection training under `backend/apps/core/rl/`:
- **Single-Agent Environment (`AMAPPSingleAgentEnv`)**:
  - Full compliance with `gymnasium.utils.env_checker.check_env`.
  - **Observation Space**: `spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)`. Normalizes vehicle position, speed, heading trigonometry, destination distance, route progress, edge speed limit/length/congestion/closure, junction branch density, traffic signal phases, neighbor distances, incidents, and emergency vehicles.
  - **Action Space**: `spaces.Discrete(K + 1)` (default size 9). Action 0 keeps the current route; actions $1 \le a \le K$ select alternative outgoing branches at upcoming intersections.
  - **Action Masking**: `action_masks() -> np.ndarray[bool]` masks out closed or non-existent branches.
  - **Objective-Driven Reward Function**: Computes progress toward goal, step duration cost, arrival bonus (+100 credited strictly once), collision (-20) and near-miss (-2) penalties, invalid action penalty (-1), and truncation penalty (-10).
  - **Minimal Reset/Step Example**:
    ```python
    from apps.core.rl import AMAPPSingleAgentEnv, SingleAgentRLConfig

    config = SingleAgentRLConfig(scenario_id="bench_grid_sparse_3x3", max_steps=100)
    env = AMAPPSingleAgentEnv(config=config)

    obs, info = env.reset(seed=42)
    mask = info["action_mask"]

    # Choose action 0 (Keep Route) or sample from valid actions
    obs, reward, terminated, truncated, info = env.step(0)
    print(f"Step reward: {reward:.3f}, Arrived: {info['is_arrived']}, Terminated: {terminated}")
    env.close()
    ```
- **Multi-Agent Environment Extension (`AMAPPMultiAgentEnv`)**:
  - Decentralized multi-vehicle routing environment supporting simultaneous action selection across vehicles.
  - Returns dictionaries of observations, rewards, terminations, truncations, and action masks keyed by `agent_id`.
- **Phase 31 Benchmark Bridge (`evaluate_rl_environment_episode`)**:
  - Runs benchmark episodes inside `AMAPPSingleAgentEnv` driven by test policies (`GreedyProgressTestPolicy`, `RandomTestPolicy`).
- **Notice on Model Training**: Phase 32 establishes the standard training interface only. Model training, PPO baselines, and policy convergence belong to Phase 33.

### 6.35 Reinforcement Learning Baseline Training, Evaluation, and Model Management (Phase 33)
The platform provides an end-to-end, reproducible training pipeline for route selection using Stable-Baselines3 and sb3-contrib `MaskablePPO` under `backend/apps/core/rl/training/`:
- **Training Architecture**:
  - `RLTrainingConfig`: Immutable configuration for hyperparameters, policy types (`maskable_ppo`, `ppo`), rollout buffers, learning rate, and artifact paths.
  - `RLBaselineTrainer`: Executes real optimizer updates on CPU, tracks training loss metrics (`LossTrackingCallback`), saves periodic checkpoints to `artifacts/rl_models/<run>/checkpoints/`, serializes final model zip, and writes `training_metadata.json`.
  - `RLModelPolicy`: Wraps trained model for deterministic inference with action masking to prevent invalid branch selection.
  - `RLBaselineEvaluator`: Evaluates saved models on held-out seeds and scenarios against heuristic baselines (`GreedyProgressTestPolicy`, `RandomTestPolicy`), producing machine-readable `evaluation_report.json` and Markdown summaries.
- **CLI Commands (`python backend/manage.py train_rl_baseline`)**:
  - **Bounded CI / Local Smoke Test**:
    ```bash
    python backend/manage.py train_rl_baseline --smoke
    ```
    Runs a fast 64-timestep bounded training cycle, saves checkpoints and final model to `artifacts/rl_models/smoke_test/`, reloads the model, verifies deterministic inference, and runs held-out evaluation across 2 seeds.
  - **Full Baseline Training**:
    ```bash
    python backend/manage.py train_rl_baseline --train \
      --algorithm maskable_ppo \
      --scenario bench_grid_sparse_3x3 \
      --timesteps 2048 \
      --seed 42 \
      --output-dir artifacts/rl_models
    ```
  - **Model Evaluation Only**:
    ```bash
    python backend/manage.py train_rl_baseline --eval-only \
      --model-dir artifacts/rl_models/maskableppo_bench_grid_sparse_3x3_s42 \
      --eval-seeds 101 102 103 104 105
    ```
- **Scope Discipline**:
  - The trained RL model baseline was established in Phase 33 and safely integrated in Phase 34.

### 6.36 Reinforcement Learning Policy Integration and Safe Fallback (Phase 34)
The platform integrates the trained RL routing policy into the simulation and benchmarking framework as an optional, explicitly configured strategy with multi-tier safe conventional fallback:
- **Model Discovery and Lifecycle (`RLModelManager`)**:
  - Validates model archive integrity, observation space shape `(32,)`, dtype `float32`, and action space dimension `(K + 1)` against `AMAPPSingleAgentEnv`.
  - Enforces thread-safe caching and explicit reload mechanisms.
- **Multi-Layer Defensive Fallback (`SafeFallbackPolicyWrapper`)**:
  - Automatically catches missing/corrupt models, PyTorch exceptions, inference timeouts (`inference_timeout_s`), non-finite outputs, out-of-bounds discrete actions, and masked illegal branches.
  - Safely falls back to conventional graph planners (A* / Dijkstra) or Action 0 (`Keep Route`) without corrupting simulation or graph state.
- **Benchmark Registry Integration (`LearnedRoutingBenchmarkAdapter`)**:
  - Conforms to `BaseRoutingBenchmarkAdapter` (`is_implemented = True`).
  - Pre-evaluates initial graph feasibility, returning `BenchmarkStatus.INFEASIBLE` directly on unreachable network partitions.
- **Runtime Configuration (`LearnedRoutingConfig`)**:
  - Strictly opt-in (`enabled = False`, `lazy_load = True`). Conventional planners remain the authoritative default.
- **Benchmark Execution Example**:
  ```bash
  python backend/manage.py run_benchmark \
    --algorithms dijkstra astar static adaptive learned \
    --scenarios bench_grid_sparse_3x3,bench_infeasible_barrier \
    --trials 1 \
    --seed 42
  ```
- **Safety Boundary**: This is an academic research simulation. The learned policy provides advisory branch suggestions only; vehicle kinematics, traffic signals, speed limits, road closures, and collision avoidance overrides remain strictly authoritative. Real vehicle or physical traffic control is prohibited.

### 6.36 Troubleshooting
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
- [docs/progress/PHASE_18.md](docs/progress/PHASE_18.md): Phase 18 emergency vehicle priority, yielding policies, and dynamic corridors report.
- [docs/progress/PHASE_19.md](docs/progress/PHASE_19.md): Phase 19 pluggable AI decision policies for autonomous vehicle agents report.
- [docs/progress/PHASE_20.md](docs/progress/PHASE_20.md): Phase 20 backend integration expansion, scenario runner enhancements, and telemetry streams report.
- [docs/progress/PHASE_21.md](docs/progress/PHASE_21.md): Phase 21 Django REST API for scenario management and simulation runs report.
- [docs/progress/PHASE_22.md](docs/progress/PHASE_22.md): Phase 22 Django Channels WebSockets for live simulation and telemetry streaming report.
- [docs/progress/PHASE_23.md](docs/progress/PHASE_23.md): Phase 23 frontend foundation and interactive 3D simulation viewer report.
- [docs/progress/PHASE_24.md](docs/progress/PHASE_24.md): Phase 24 3D city, road network, and urban environment rendering report.
- [docs/progress/PHASE_25.md](docs/progress/PHASE_25.md): Phase 25 vehicle and pedestrian models, animation, and temporal interpolation report.
- [docs/progress/PHASE_26.md](docs/progress/PHASE_26.md): Phase 26 interactive simulation playback, timeline, and step controls report.
- [docs/progress/PHASE_27.md](docs/progress/PHASE_27.md): Phase 27 V2V communication links, message animations, and network-state overlays report.
- [docs/progress/PHASE_28.md](docs/progress/PHASE_28.md): Phase 28 adaptive routing visualization, route alternatives, and rerouting explanations report.
- [docs/progress/PHASE_29.md](docs/progress/PHASE_29.md): Phase 29 interactive traffic incident injection and scenario controls report.
- [docs/progress/PHASE_30.md](docs/progress/PHASE_30.md): Phase 30 operational metrics dashboard, live KPIs, and simulation analytics report.
- [docs/progress/PHASE_31.md](docs/progress/PHASE_31.md): Phase 31 reproducible routing benchmarking framework report.
- [docs/progress/PHASE_32.md](docs/progress/PHASE_32.md): Phase 32 Gymnasium-compatible single-agent and multi-agent RL environment report.
- [docs/progress/PHASE_33.md](docs/progress/PHASE_33.md): Phase 33 train, evaluate, and save reinforcement-learning baseline report.
- [docs/progress/PHASE_34.md](docs/progress/PHASE_34.md): Phase 34 evaluate and integrate learned routing policy with safe fallback report.
- [docs/TESTING.md](docs/TESTING.md): Testing standards, fixtures, and regression policies.
- [docs/API.md](docs/API.md): API and WebSocket telemetry protocol contracts.
- [docs/decisions/ADR-001-modular-simulation-architecture.md](docs/decisions/ADR-001-modular-simulation-architecture.md): Architectural Decision Record on simulation decoupling.



