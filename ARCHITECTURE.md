# ARCHITECTURE: Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)

> **Document Status:** Implementation Blueprint (Phase 01)  
> **Component Implementation Status:** **PROPOSED / SPECIFICATION ONLY** (No runtime application code implemented yet)

---

## 1. System Overview & Component Status

The **Adaptive Multi-Agent Path Planning (AMAPP)** simulation platform is a decentralized multi-agent autonomous vehicle research environment. It simulates autonomous vehicles navigating real-world or synthetic road networks with dynamic traffic, pedestrians, signalized intersections, emergency vehicles, and decentralized Vehicle-to-Vehicle (V2V) communications under realistic channel constraints (range attenuation, delay, packet loss).

```mermaid
flowchart TB
    subgraph Frontend["Frontend Layer (Browser / Three.js - Planned Phases 23-30)"]
        UI["Interactive Dashboard HUD"]
        ThreeCanvas["Three.js 3D Scene (Vehicles, Roads, V2V Waves)"]
        WSClient["WebSocket Client (JSON Telemetry Stream)"]
        RESTClient["REST API Client (Scenario Config / Controls)"]
    end

    subgraph BackendTransport["Transport Layer (Django Channels & DRF - Planned Phases 2, 21-22)"]
        Daphne["ASGI Server (Daphne)"]
        WSChannel["Simulation WebSocket Consumer"]
        RESTViews["REST API Endpoints (/api/v1/...)"]
    end

    subgraph SimulationCore["Authoritative Simulation Core (Python - Planned Phases 3-20)"]
        Clock["Simulation Clock (Fixed dt Step)"]
        SpatialIndex["Spatial Partitioning (R-tree / Grid)"]
        
        subgraph Subsystems["Simulation Subsystems"]
            MapGraph["Road Network Graph (OSM / NetworkX)"]
            TrafficCtrl["Traffic Signals & Pedestrians"]
            CollisionEngine["Collision Detection Engine"]
            V2VChannel["Decentralized V2V Message Delivery Engine"]
            Benchmarking["Performance & Metric Benchmarking"]
        end

        subgraph VehicleAgents["Vehicle Agents Pool"]
            AgentA["Agent 1 (Local Belief + A* + Local Policy)"]
            AgentB["Agent 2 (Local Belief + RL Policy)"]
            AgentE["Emergency Vehicle (Ambulance / Priority)"]
        end
    end

    subgraph RLSubsystem["Reinforcement Learning Subsystem (Gymnasium / SB3 - Planned Phases 32-34)"]
        GymEnv["AMAPP Gymnasium Environment"]
        SB3Model["Trained Policy (PPO / DQN)"]
    end

    Frontend <-->|WebSocket Stream & REST| BackendTransport
    BackendTransport <--> SimulationCore
    SimulationCore <--> RLSubsystem
```

### Component Status Summary
- **Backend Scaffold & Health API (`backend/`, `apps.core`):** **IMPLEMENTED & TESTED** in Phase 02 (Django 5.1.x, DRF 3.15.x, ASGI/WSGI entrypoints, `GET /api/v1/health/`, automated pytest suite passing).
- **Simulation Domain Layer (`backend/apps/core/domain/`):** **IMPLEMENTED & TESTED** in Phase 03 (Typed dataclasses for 10 domain models, 3 immutable value types, 9 enumerations, validation boundaries, and JSON serialization contracts).
- **Road Graph & Synthetic City (`backend/apps/core/graph/`):** **IMPLEMENTED & TESTED** in Phase 04 (`RoadGraph` wrapping NetworkX `DiGraph`, `CityGridConfig`, `generate_synthetic_city_grid`, weak/strong connectivity analysis, traffic signal integration, 151 tests passing).
- **Simulation Core & Subsystems (`sim_engine/*`):** **PLANNED ARCHITECTURAL BLUEPRINTS** (Phases 5–20).
- **Transport Streaming & Advanced REST (`backend/channels/`, etc.):** **PLANNED** (Phases 21–22).
- **Reinforcement Learning (`rl_engine/*`):** **PLANNED** (Phases 32–34).
- **Frontend Dashboard (`frontend/*`):** **PLANNED** (Phases 23–30).

---

## 2. Core Architectural Principles

### 2.1 Authoritative Simulation Core vs. Decentralized Agent Autonomy
A fundamental requirement of AMAPP is the strict separation between global ground truth and local agent perception:

1. **Global Ground-Truth State ($\mathcal{S}_{\text{global}}$):**
   - Maintained exclusively by the authoritative simulation engine (`sim_engine/`).
   - Contains exact 2D/3D coordinates $(x, y, z)$, true heading $\theta$, actual velocity $v$, active obstacles, actual collision events, signal phases, and message packet positions in flight.
   - **Agents have NO direct access to $\mathcal{S}_{\text{global}}$.**

2. **Direct Local Observations ($\mathcal{O}_i(t)$):**
   - Emulates onboard vehicle sensors (radar/LiDAR range $R_{\text{sens}}$, forward-facing camera, lane sensors).
   - Generates observations strictly within line-of-sight and physical sensor horizons.

3. **Received V2V Messages ($\mathcal{M}_i(t)$):**
   - Peer-to-peer messages received from neighboring agents within communication radius $R_{\text{comm}}$, subject to simulated transmission latency, packet loss, and message expiration.

4. **Private Local Knowledge Base / Belief State ($\mathcal{K}_i(t)$):**
   - Each vehicle maintains its own private belief state:
     $$\mathcal{K}_i(t) = \mathcal{O}_i(t) \cup \mathcal{M}_i(t) \cup \mathcal{G}_{\text{static\_map}}$$
   - Each agent independently computes its route adaptation, collision avoidance, and yielding maneuvers using solely its local belief $\mathcal{K}_i(t)$.
   - **The simulation scheduler/engine manages physical stepping and message transport, but NEVER secretly computes or overrides route decisions for agents.**

### 2.2 Deterministic Execution & Reproducibility
- The simulation loop advances using a discrete, fixed timestep $\Delta t = 0.1\,\text{s}$ (10 Hz).
- All stochastic processes (agent spawn distributions, packet loss triggers, pedestrian crossings) are governed by explicit, seedable pseudorandom generators (`RandomState(seed)`).
- Identical scenario configurations and seeds produce bit-identical simulation trajectories.

### 2.3 Headless Testability & Layer Decoupling
- The core simulation engine is 100% pure Python and has zero runtime dependencies on Django, Channels, WebSockets, or browser DOM.
- It can be initialized, stepped, inspected, and benchmarked headlessly via automated `pytest` suites and Gymnasium RL environments in milliseconds.

---

## 3. Subsystem Layer Specifications

### 3.0 Domain Layer & Simulation Contracts (`backend/apps/core/domain/` — IMPLEMENTED & TESTED in Phase 03)
- **Decoupled Architecture:** Pure Python typed dataclasses completely decoupled from Django ORM database tables and migrations.
- **10 Core Domain Entities:**
  - `RoadNode`: Unique identifier, planar `Position2D`, optional WGS84 `GeoCoordinate`, metadata attributes.
  - `RoadEdge`: Unique identifier, start/end node references (self-loops prohibited), length ($m > 0$), speed limit ($m/s > 0$), lane count ($\ge 1$).
  - `Route`: Unique identifier, ordered sequence of at least 2 node IDs, optional edge sequence, cached distance and duration metrics.
  - `Vehicle`: Unique identifier, 2D position, speed ($0 \le v \le v_{\max}$), heading normalized to $[0, 2\pi)$, state enum, classification enum, physical dimensions.
  - `Pedestrian`: Unique identifier, 2D position, state enum (WAITING, CROSSING, SAFE), speed bounds, optional crossing crosswalk node.
  - `TrafficSignal`: Unique identifier, controlling intersection node reference, signal phase (RED, YELLOW, GREEN), cycle duration and remaining phase duration.
  - `Obstacle`: Unique identifier, 2D position, obstacle type enum, physical footprint dimensions, optional edge reference.
  - `Incident`: Unique identifier, 2D position, incident type enum, severity enum, resolution status enum, reporting timestamp.
  - `V2VMessage`: Unique packet ID, sender ID, optional target recipient (None for broadcast), message type enum, emission timestamp, expiration timestamp, sender position, structured payload.
  - `SimulationConfig`: Discrete timestep duration ($\Delta t \in [0.001, 2.0]\,s$), deterministic random seed, communication radius ($m$), time horizon, vehicle capacity limit.
- **3 Value Types (Immutable `frozen=True`):** `Position2D`, `GeoCoordinate`, `Dimensions2D`.
- **Validation Boundaries:** Invariants enforced strictly at construction (`__post_init__`), raising `DomainValidationError`.
- **Serialization:** Full JSON round-trip serialization (`to_dict`, `from_dict`, `to_json`, `from_json`) with enum string mappings and clear error handling via `SerializationError`.

### 3.1 Simulation Core (`backend/apps/core/simulation/` — IMPLEMENTED & TESTED in Phase 08)
- **Phase 8 Implementation Status:** **COMPLETED & TESTED**. The simulation core coordinates discrete time progression, world-state ownership, multi-agent stepping, and atomic rollback guarantees.
- **Module Architecture (`backend/apps/core/simulation/`):**
  - `clock.py`: Authoritative discrete simulation clock (`SimulationClock`) tracking integer tick count $k$ and fixed step duration $\Delta t \in [0.0001, 10.0]\,\text{s}$. Eliminates floating-point drift by deriving simulated time as $t = \text{round}(k \cdot \Delta t, 9)$. Independent of wall-clock time.
  - `world.py`: Centralized container (`WorldState`) owning the `RoadGraph`, authoritative `SimulationClock`, and registered `VehicleAgent` instances. Enforces unique agent identifiers (`DuplicateAgentIdError`), validates agent-graph compatibility (`IncompatibleAgentGraphError`), enumerates agents in stable identifier order (`sorted by vehicle.id`), captures initial registration baselines, and restores state on reset.
  - `engine.py`: Execution sequencer (`SimulationEngine`) coordinating clock ticks and vehicle stepping. Ensures identical $\Delta t$ distribution across all agents, provides idempotent pause/resume, allows explicit single-stepping while paused, and enforces atomic rollback on stepping failures.
  - `models.py`: Value objects and snapshot models (`EngineStatus`, `VehicleSnapshot`, `WorldSnapshot`, `TickResult`).
  - `exceptions.py`: Typed exception hierarchy (`SimulationError`, `InvalidTimeStepError`, `ClockStateError`, `DuplicateAgentIdError`, `AgentNotFoundError`, `IncompatibleAgentGraphError`, `EngineStateError`, `TickExecutionError`).
- **Atomic Tick Semantics & Rollback Guarantees:**
  - Before advancing agents, pre-tick rollback snapshots of all registered agents are captured.
  - If any agent raises an exception during stepping, all agents revert immediately to their pre-tick state, the clock does not advance, and the engine enters `FAILED` status, preventing partial or corrupted simulation states.
- **Single-Step & Paused Execution:**
  - When paused, calling `step()` acts as an explicit single-step advancing exactly one tick while maintaining the engine's paused status. Calling `run()` while paused raises `EngineStateError`.
- **Reset Invariants:**
  - `reset()` restores clock tick count to 0, elapsed time to 0.0, engine status to `INITIALIZED`, and restores all agents to their baseline registration states without recreating the road graph.
- **Strict Boundary Decoupling:**
  - Does NOT yet implement vehicle stopping/braking behavior at red lights (Phase 16), scenario scheduling (Phase 10), V2V messaging (Phase 11), or collision avoidance (Phase 16).

### 3.2 Traffic Signals and Intersection Management (`backend/apps/core/signals/` — IMPLEMENTED & TESTED in Phase 09)
- **Phase 9 Implementation Status:** **COMPLETED & TESTED**. The traffic signal subsystem provides deterministic, clock-synchronized intersection control and approach-edge queries.
- **Module Architecture (`backend/apps/core/signals/`):**
  - `models.py`: Validated cycle configurations (`SignalCycleConfig`), immutable point-in-time snapshots (`SignalSnapshot`), and vehicle query contracts (`SignalQueryResult`).
  - `controller.py`: State machine (`TrafficSignalController`) executing deterministic cyclic transitions ($\text{RED} \to \text{GREEN} \to \text{YELLOW} \to \text{RED}$) synchronized with authoritative simulation clock.
  - `exceptions.py`: Signal error hierarchy (`SignalError`, `InvalidSignalCycleError`, `DuplicateSignalError`, `SignalNotFoundError`, `InvalidIntersectionAssociationError`).
- **Timing & Progression Mathematics:**
  - Cycle period $T = d_{\text{red}} + d_{\text{green}} + d_{\text{yellow}}$.
  - Instantaneous phase position $\tau = (t_{\text{sim}} + t_{\text{offset}}) \pmod T$, eliminating accumulated floating-point drift.
  - Strictly cyclic non-overlapping half-open intervals: $\text{RED} \in [0, d_{\text{red}})$, $\text{GREEN} \in [d_{\text{red}}, d_{\text{red}} + d_{\text{green}})$, $\text{YELLOW} \in [d_{\text{red}} + d_{\text{green}}, T)$.
- **Intersection & Approach Associations:**
  - Signals govern specific intersection nodes and incoming road approach edges ($e \in \text{incoming}(n)$).
  - Validation ensures controlled edges terminate at the signal's node and graph consistency is maintained.
- **Engine & WorldState Integration:**
  - `WorldState` manages a centralized signal registry, $O(1)$ lookups by signal ID, node ID, and incoming edge ID, auto-registers signals from `RoadGraph`, captures snapshots, and executes resets.
  - `SimulationEngine` advances signals on clock ticks, includes `signal_states` in `TickResult`, provides atomic rollback alongside vehicles upon stepping errors, and exposes `query_signal` and `query_signal_for_edge` APIs.
- **Strict Boundary Decoupling:**
  - Does NOT implement vehicle stopping/braking behavior at red lights (Phase 16), intersection collision resolution, or adaptive signal timing.

### 3.3 Vehicle Kinematics & Agent Lifecycle (`backend/apps/core/kinematics/` — IMPLEMENTED & TESTED in Phase 07)
- **Responsibilities:** Individual vehicle lifecycle, deterministic point-mass kinematic motion along planned routes, speed and acceleration limits, heading orientation updates, segment transitions, overshoot prevention, and pure mathematical integration.
- **Module Architecture (`backend/apps/core/kinematics/`):**
  - `models.py`: Validated configuration (`KinematicsConfig`) and step result contract (`MotionStepResult`).
  - `motion.py`: Pure mathematical integration (`integrate_motion`), heading calculation (`compute_heading`), and planar interpolation (`interpolate_position`).
  - `vehicle_agent.py`: Individual vehicle lifecycle and route-following coordinator (`VehicleAgent`).
  - `exceptions.py`: Typed exceptions (`KinematicsError`, `InvalidKinematicsConfigError`, `InvalidMotionInputError`, `InvalidRouteError`, `InvalidLifecycleTransitionError`).
- **Kinematic Motion Model:**
  - *Equations of Motion:*
    $$v(t) = v_0 + a \Delta t$$
    $$d(t) = v_0 \Delta t + \frac{1}{2} a \Delta t^2$$
  - *Acceleration & Braking Limits:* Applied acceleration is clamped to $[-b_{\max}, a_{\max}]$:
    $$a_{\text{applied}} = \max(-config.\text{max\_deceleration\_mps2}, \min(a_{\text{cmd}}, config.\text{max\_acceleration\_mps2}))$$
  - *Mid-Step Stopping:* If braking stops the vehicle mid-step ($t_{\text{stop}} = v_0 / |a_{\text{applied}}| < \Delta t$), distance is clamped to $d = \frac{v_0^2}{2 |a_{\text{applied}}|}$ and speed becomes $0.0$; no reverse motion occurs.
  - *Mid-Step Speed Capping:* If accelerating reaches $v_{\text{cap}}$ mid-step ($t_{\text{sat}} < \Delta t$), motion integrates acceleration up to $t_{\text{sat}}$ and constant-speed cruise for the remainder.
  - *Destination Arrival & Overshoot Prevention:* Distance is clamped by remaining route distance ($d \le d_{\text{rem}}$). Reaching destination transitions vehicle to `ARRIVED` and brings speed to $0.0$.
  - *Multi-Segment Progression:* Large time steps traverse intermediate segment endpoints without losing traveled distance.
- **Lifecycle State Machine:**
  - `IDLE`: Initial parked state. Stepping produces zero movement. Starting requires an assigned route.
  - `EN_ROUTE`: Actively advancing along route segments.
  - `BLOCKED` / `STOPPED`: Paused/waiting state. Speed is $0.0$. Position and progress along segment are preserved. Stepping produces zero movement. Calling `resume()` restores `EN_ROUTE`.
  - `ARRIVED`: Final destination reached. Speed is $0.0$. Repeated stepping produces zero movement. Resuming requires explicit `reset()`.
- **Explicit Boundaries:** Operates on an individual vehicle without a global clock, collision avoidance, traffic signal obedience, or multi-agent negotiation (deferred to Phases 8, 9, 11, 16).

### 3.3 Road Graph & Synthetic City Generator (`backend/apps/core/graph/` — IMPLEMENTED & TESTED in Phase 04)
- **Responsibilities:** Directed road network graph representation $G = (V, E)$ wrapping NetworkX (`nx.DiGraph`); authoritative storage of typed `RoadNode` and `RoadEdge` domain entities; deterministic synthetic city grid generation; topological queries and reachability analysis.
- **Implementation Components:**
  - `RoadGraph`: Wrapper around `nx.DiGraph` enforcing unique node/edge IDs, valid endpoints, directed forward/reverse edge separation, self-loop prevention, traffic signal indexing, and export to JSON-compatible dictionary structures.
  - `CityGridConfig`: Validated parameter set defining grid rows, columns, inter-intersection spacing in meters, base speed limits in m/s, lane counts, traffic signal locations, and deterministic pseudorandom seed.
  - `generate_synthetic_city_grid`: Deterministic city network generator producing connected road grids with planar Cartesian coordinates, edge lengths agreeing with Euclidean node spacing, alternative paths, and signalized internal junctions. Fully offline with zero external network or map service dependencies.
- **Topological Invariants & Connectivity:**
  - *Weak Connectivity:* Underlying undirected graph is connected.
  - *Strong Connectivity:* Every intersection is mutually reachable via directed paths (guaranteed in bidirectional grid mode).
  - *Alternative Paths:* Grid topology provides multiple distinct paths between non-adjacent intersections for dynamic rerouting.

### 3.4 OpenStreetMap Import & Normalization (`backend/apps/core/graph/` — IMPLEMENTED & TESTED in Phase 05)
- **Responsibilities:** Geographic bounding-box acquisition via OSMnx, WGS84-to-planar Cartesian coordinate projection, normalization into `RoadNode` and `RoadEdge` domain entities, directed road topology preservation, and deterministic offline fallback to synthetic city grids.
- **Implementation Components:**
  - `BoundingBox`: Strictly validated geographic bounding box with coordinate range checks ($[-90, 90]$, $[-180, 180]$), orientation verification (`north > south`, `east > west`), and area span limits ($\le 0.25^\circ$).
  - `LocalPlanarProjector`: Conformal equirectangular planar projection converting WGS84 $(\text{lat}, \text{lon})$ to local Cartesian meters $(\text{Position2D})$ relative to the southwest origin $(x \ge 0, y \ge 0)$ with bidirectional round-trip support.
  - `normalize_osm_graph`: Normalizes external NetworkX `MultiDiGraph` into internal `RoadGraph`. Generates deterministic IDs (`osm_node_{id}`, `osm_edge_{u}_{v}`), computes Euclidean lengths, parses speed limits and lane counts, separates one-way from bidirectional ways, and skips self-loops and duplicate parallel edges.
  - `acquire_osm_graph`: Defensive acquisition adapter querying Overpass via OSMnx with timeout and error classification (`OSMTimeoutError`, `OSMServiceUnavailableError`, `OSMEmptyGraphError`, `OSMNotInstalledError`).
  - `import_osm_road_network`: High-level orchestration service. If acquisition fails or OSMnx is absent and `allow_fallback=True`, seamlessly falls back to a deterministic synthetic city grid, preserving error diagnostics in structured metadata.
- **Fallback Policy:** Invalid geographic bounds immediately raise `InvalidBoundingBoxError` and are never disguised by synthetic fallback. Synthetic fallback is engaged only when acquisition/dependency errors occur and fallback is explicitly enabled.

### 3.5 Route Planning Baseline & Adaptive Rerouting (`backend/apps/core/routing/` — Phase 6 IMPLEMENTED; Phase 15 Planned)
- **Phase 6 Implementation Status:** **COMPLETED & TESTED**. The baseline route planning subsystem operates over the directed `RoadGraph` abstraction, supporting both Dijkstra and custom A* search, distance and travel-time objectives, non-mutating edge closures, and typed result contracts.
- **Module Architecture (`backend/apps/core/routing/`):**
  - `costs.py`: Pure cost computation (`calculate_edge_cost`, `calculate_route_metrics`, `is_edge_traversable`).
  - `heuristics.py`: Admissibility analyzer (`check_heuristic_admissibility`) and heuristic builder (`get_heuristic_function`).
  - `dijkstra.py`: Authoritative Dijkstra search (`dijkstra_search`) with deterministic tie-breaking.
  - `astar.py`: Custom A* priority queue search (`astar_search`) with stale entry pruning and secondary tie-breaking.
  - `planner.py`: High-level facade (`RoutePlanner`, `find_route`) caching admissibility checks.
  - `models.py`: Value objects (`CostMode`, `RoutingAlgorithm`, `RoutingRequest`, `RoutingResult`).
  - `exceptions.py`: Typed hierarchy (`RoutingError`, `RoutingNodeNotFoundError`, `NoPathFoundError`, `InvalidRoutingRequestError`).
- **Cost Formulation & Units:**
  1. *Shortest Distance:* $\text{Cost}_{\text{dist}}(e) = e.\text{length\_m}$ [meters].
  2. *Fastest Travel Time:* $\text{Cost}_{\text{time}}(e) = e.\text{length\_m} / e.\text{speed\_limit\_mps}$ [seconds].
- **Heuristic Admissibility & Consistency:**
  - *Distance Heuristic:* $h_{\text{dist}}(n) = \text{EuclideanDistance}(n, \text{dest})$. Admissible when $e.\text{length\_m} \ge \text{EuclideanDistance}(u, v) - 10^{-5}$ for all edges.
  - *Travel Time Heuristic:* $h_{\text{time}}(n) = \text{EuclideanDistance}(n, \text{dest}) / V_{\max}$ where $V_{\max} = \max_{e \in E}(e.\text{speed\_limit\_mps})$.
  - *Safety Fallback ($h=0$):* If the graph violates Euclidean edge bounds or has non-positive speed limits, `get_heuristic_function` automatically falls back to $h=0.0$, guaranteeing search optimality without failure.
- **Road Closures:** Closed edge IDs are filtered during search without mutating `RoadGraph`. Unknown closed edge IDs are safely ignored.
- **Start == Destination Policy:** Returning $0.0$ cost, $0$ expanded nodes, and `route=None` to preserve `Route` domain invariants ($\ge 2$ nodes).
- **Future Adaptive Rerouting (Phase 15):** Dynamic congestion factors, incident penalty weights, and re-planning cooldown timers will be layered over this baseline in Phase 15.

### 3.6 V2V Communication Subsystem (`sim_engine/v2v/` — Planned Phases 11–14)
- **Responsibilities:** Peer-to-peer message protocol, spatial proximity detection ($d \le R_{\text{comm}}$), transmission latency, packet loss ($P_{\text{loss}}$), message expiration, and deduplication.
- **Message Types:**
  - `BEACON`: Periodic broadcast (ID, position, speed, heading).
  - `HAZARD_ALERT`: Event-driven alert (incident location, closure, congestion level).
  - `EMERGENCY_PRIORITY`: Priority corridor clearance beacon.
- **Failure Handling (Phase 14):** When packets are dropped or peers disconnect, agents fall back to local sensor observations and conservative headway following.

### 3.7 Safety, Collisions & Traffic Rules (`sim_engine/safety/` — Planned Phases 16–18)
- **Responsibilities:** Bounding-box and circle intersection checks, Time-To-Collision (TTC) calculations, Intelligent Driver Model (IDM) car-following, pedestrian crosswalk yielding, signal phase obedience, emergency corridor formation.

### 3.8 AI & Reinforcement Learning (`sim_engine/policies/` & `rl_engine/` — Planned Phases 19, 32–34)
- **Interpretable Decision Policy (Phase 19):** Transparent, weighted scoring baseline evaluating travel time, congestion, risk, and communication confidence:
  $$\text{Score}(\text{route}) = w_1 \cdot \text{Time} + w_2 \cdot \text{Congestion} + w_3 \cdot \text{Risk} - w_4 \cdot \text{Confidence}$$
- **Gymnasium Environment (Phase 32):** Standard RL interface providing bounded vector observations and discrete/continuous action spaces for route selection.
- **Stable-Baselines3 Model (Phases 33–34):** PPO agent trained on route selection with bounded training budget, fully decoupled from the baseline policy.

### 3.9 Web Backend & Transport (`backend/` — Planned Phases 2, 21–22, 35)
- **Responsibilities:** Django REST Framework API for scenario discovery, simulation lifecycle control (play/pause/step/reset), metrics querying, and experiment history persistence.
- **Django Channels (ASGI / Daphne):** Streams authoritative simulation snapshots and V2V events over WebSockets at bounded frequencies (10–30 Hz).

### 3.10 Frontend & Visualization (`frontend/` — Planned Phases 23–30)
- **Responsibilities:** TypeScript + Three.js application rendering 3D road networks, vehicles, pedestrians, traffic signals, communication range rings, and hazard indicators.
- **Strict Rendering Boundary:** The frontend never computes physics or invents simulation state; it strictly interpolates authoritative state received from WebSockets.

---

## 4. Top-Level Module Blueprint

| Module Path | Responsibility | Intro Phase | Dependencies | Public Contract | Test Suite | Forbidden Dependencies |
|---|---|---|---|---|---|---|
| `backend/apps/core/domain/` | Typed domain dataclasses, value objects, enums, units, validation, serialization | Phase 03 (IMPLEMENTED & TESTED) | Python Standard Library (`dataclasses`, `enum`, `typing`, `json`, `math`) | 10 Domain Models (`Vehicle`, `RoadNode`, `RoadEdge`, `Route`, `Pedestrian`, `TrafficSignal`, `Obstacle`, `Incident`, `V2VMessage`, `SimulationConfig`), 3 Value Types (`Position2D`, `GeoCoordinate`, `Dimensions2D`), `to_dict`, `from_dict`, `to_json`, `from_json` | `backend/apps/core/tests/test_domain_*.py` | Must NOT depend on Django ORM, Channels, or external geometry packages |
| `backend/apps/core/graph/` | Directed road graph abstraction, synthetic city grid generator, OSM road-network acquisition and normalization, offline fallback | Phase 04 & 05 (IMPLEMENTED & TESTED) | NetworkX, `backend/apps/core/domain/`, optional OSMnx | `RoadGraph`, `CityGridConfig`, `generate_synthetic_city_grid`, `BoundingBox`, `OSMImportConfig`, `OSMImportResult`, `LocalPlanarProjector`, `normalize_osm_graph`, `import_osm_road_network` | `backend/apps/core/tests/test_road_graph.py`, `backend/apps/core/tests/test_city_generator.py`, `backend/apps/core/tests/test_osm_*.py` | Must NOT depend on vehicle kinematics, routing, or web layer |
| `backend/apps/core/routing/` | Baseline shortest-path planning (Dijkstra, A*), distance/travel-time cost modes, road closures, heuristic admissibility | Phase 06 (IMPLEMENTED & TESTED) | NetworkX, `backend/apps/core/domain/`, `backend/apps/core/graph/` | `RoutePlanner`, `find_route`, `dijkstra_search`, `astar_search`, `CostMode`, `RoutingAlgorithm`, `RoutingRequest`, `RoutingResult` | `backend/apps/core/tests/test_routing_*.py` | Must NOT depend on vehicle kinematics, global clock, or web endpoints |
| `backend/apps/core/simulation/` | Authoritative simulation clock, fixed-step execution sequencer, world-state container, atomic rollback, pause/resume/step | Phase 08 (IMPLEMENTED & TESTED) | `backend/apps/core/domain/`, `backend/apps/core/graph/`, `backend/apps/core/kinematics/` | `SimulationEngine`, `SimulationClock`, `WorldState`, `EngineStatus`, `WorldSnapshot`, `TickResult` | `backend/apps/core/tests/test_simulation_*.py` | Must NOT depend on Django views or WebSocket consumers |
| `sim_engine/v2v/` | Message validation, proximity detection, channel noise | Phase 11 | `sim_engine/domain/`, SciPy/NumPy | `V2VChannel`, `ProximityDetector`, `MessageDispatcher` | `tests/unit/test_v2v.py` | Must NOT modify agent routes directly |
| `sim_engine/safety/` | Collision detection, IDM, signals, pedestrian yielding | Phase 16 | `sim_engine/domain/`, NumPy | `CollisionDetector`, `IDMController`, `TrafficSignalController` | `tests/unit/test_safety.py` | Must NOT depend on frontend rendering |
| `backend/` | Django project, settings, ASGI/WSGI, health check API (scaffold: Phase 02; full APIs: Phase 21) | Phase 02, 21 | Django, DRF, Channels, Daphne | Health check (`/api/v1/health/`), future REST API & WebSockets | `backend/apps/core/tests/test_health.py` | Core simulation must run without `backend/` |
| `rl_engine/` | Gymnasium environment, SB3 PPO training, model evaluation | Phase 32 | Gymnasium, Stable-Baselines3, PyTorch | `AMAPPEnv`, `train_ppo()`, `evaluate_policy()` | `tests/unit/test_gym_env.py` | Core simulation must function if SB3 is absent |
| `frontend/` | TypeScript + Three.js 3D dashboard & HUD | Phase 23 | Node.js, Vite, Three.js | Browser UI, WebSocket client, Canvas renderer | Frontend test runner (Vitest/ESLint) | Must NOT compute authoritative vehicle movements |

---

## 5. Dependency Strategy & Compatibility Matrix

```mermaid
graph TD
    subgraph CoreBackend["Backend & Simulation Stack"]
        Python["Python 3.11.9 (Verified)"]
        Django["Django 5.1.x"]
        DRF["djangorestframework 3.15.x"]
        Channels["channels 4.2.x & daphne 4.1.x"]
        NumPy["numpy >= 1.26.0, < 2.0.0"]
        NetworkX["networkx >= 3.2.0"]
        SciPy["scipy >= 1.12.0"]
    end

    subgraph OptionalGeospatial["Optional Geospatial Stack"]
        OSMnx["osmnx >= 1.9.0 (Optional)"]
        Shapely["shapely >= 2.0.0"]
    end

    subgraph RLStack["Reinforcement Learning Stack"]
        Gymnasium["gymnasium >= 0.29.1"]
        SB3["stable-baselines3 >= 2.3.0"]
        Torch["torch >= 2.2.0 (CPU)"]
    end

    subgraph FrontendStack["Frontend Stack (Node 22.x)"]
        TypeScript["typescript >= 5.4.0"]
        ThreeJS["three >= 0.165.0"]
        Vite["vite >= 5.2.0"]
    end

    Python --> Django
    Python --> NetworkX
    Python --> NumPy
    Django --> DRF
    Django --> Channels
```

### Dependency Groupings & Version Pinning Strategy

1. **Core Simulation & Numerical Computing (Phases 3–20):**
   - `python`: 3.11.9 (Verified host runtime)
   - `networkx`: ~3.3 (Graph topology, A* algorithm)
   - `numpy`: ~1.26.4 (Spatial coordinates, vector math, bounded < 2.0.0 for library stability)
   - `scipy`: ~1.13.0 (Spatial distance computations, KDTree proximity queries)

2. **Web Backend & Transport (Phases 2, 21–22):**
   - `django`: ~5.1.2 (LTS/current stable release)
   - `djangorestframework`: ~3.15.2 (REST serializers, views)
   - `channels`: ~4.2.0 (ASGI WebSocket routing)
   - `daphne`: ~4.1.2 (ASGI production server)
   - `channels-redis`: ~4.2.0 (Optional Redis channel layer, with in-memory fallback)

3. **Optional Geospatial (Phase 5):**
   - `osmnx`: ~1.9.4
   - `shapely`: ~2.0.4
   - *Compatibility Guard:* OSMnx requires underlying C-libraries (GEOS/GDAL). Phase 5 will implement strict defensive imports: if OSMnx is uninstalled or fails on Windows, the system transparently utilizes the deterministic synthetic grid without crashing.

4. **Reinforcement Learning (Phases 32–34):**
   - `gymnasium`: ~0.29.1
   - `stable-baselines3`: ~2.3.2
   - `torch`: ~2.2.2+cpu (CPU-only build to keep installation lightweight and CI fast)

5. **Testing & Code Quality (Phases 1–40):**
   - `pytest`: ~8.2.0
   - `pytest-cov`: ~5.0.0
   - `pytest-django`: ~4.8.0
   - `pytest-asyncio`: ~0.23.6
   - `ruff`: ~0.4.4

6. **Frontend Stack (Phases 23–30):**
   - Node.js: 22.18.0 (Verified host runtime)
   - npm: 10.9.3
   - `three`: ~0.165.0
   - `@types/three`: ~0.165.0
   - `vite`: ~5.2.11
   - `typescript`: ~5.4.5
   - `eslint`: ~8.57.0

---

## 6. Technical Risks & Mitigation Strategies

| Risk ID | Description | Severity | Mitigation Strategy |
|---|---|---|---|
| **TR-01** | Geospatial dependency installation failures (GDAL/GEOS with OSMnx on Windows) | Medium | Make OSMnx strictly optional via dynamic import guards; provide a complete offline synthetic grid as primary fallback. |
| **TR-02** | PyTorch / SB3 CI runtime weight and build slowdown | Medium | Use CPU-only PyTorch wheels; confine model training to isolated bounded jobs (Phase 33), using small observation spaces. |
| **TR-03** | High-frequency WebSocket streaming saturating browser thread | High | Decouple simulation tick rate from client frame rate; implement snapshot throttling (10–20 Hz) and client-side interpolation. |
| **TR-04** | Route oscillation during multi-agent dynamic rerouting | High | Implement re-planning cooldown timers, hysteresis margins ($\Delta C > 15\%$), and staggered update intervals. |
| **TR-05** | State desynchronization between backend physics and frontend 3D rendering | Critical | Backend is authoritative for all coordinates, states, and collisions. Frontend strictly interpolates backend snapshots and never creates collision events. |
| **TR-06** | Flaky or non-deterministic tests in CI | High | Mandate fixed pseudorandom seeds across all unit, integration, and scenario tests; avoid wall-clock sleeps. |
