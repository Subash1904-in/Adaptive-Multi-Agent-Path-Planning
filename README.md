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

### 6.12 Troubleshooting
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
- [docs/TESTING.md](docs/TESTING.md): Testing standards, fixtures, and regression policies.
- [docs/API.md](docs/API.md): API and WebSocket telemetry protocol contracts.
- [docs/decisions/ADR-001-modular-simulation-architecture.md](docs/decisions/ADR-001-modular-simulation-architecture.md): Architectural Decision Record on simulation decoupling.
