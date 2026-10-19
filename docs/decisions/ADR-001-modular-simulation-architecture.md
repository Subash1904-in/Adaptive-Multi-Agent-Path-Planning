# ADR-001: Separation of Core Simulation Engine, Decentralized Agent Logic, and Visualization Layers

## Status
Accepted

## Context
The project requires building a multi-agent autonomous vehicle simulation supporting 14 distinct functional requirements:
- V2V communication, decentralized protocol, range detection, channel failure handling
- Road network graph with OpenStreetMap integration and offline fallback
- Traffic signals, pedestrian dynamics, collision avoidance, and emergency priority
- AI/RL route selection model training via Gymnasium
- Real-time 3D web visualization via Django and Three.js

A monolithic or tightly coupled design (e.g., embedding physics logic inside Django views, or computing pathfinding inside the browser) would severely hinder automated unit testing, headless RL training, benchmark reproducibility, and continuous integration.

## Decision
We enforce a strict three-tier architecture:

1. **Authoritative Headless Simulation Core (`sim_engine/`):**
   - Implemented as pure Python modules with zero dependency on Django, HTTP, or browser runtimes.
   - Authoritative for ground truth physics, simulation time, spatial indices, collision resolution, and V2V packet delivery.
   - Fully runnable and testable via `pytest` and consumable directly by Gymnasium RL environments.

2. **Decentralized Agent Knowledge Base (`sim_engine/agents/`):**
   - Individual vehicles do not have access to global ground truth.
   - Each agent maintains a private belief state populated strictly from onboard sensor queries and received V2V packets.
   - Route planning (A*) and decision policies operate on this private local belief state.

3. **Transport & Visualization Layer (`backend/` & `frontend/`):**
   - Django Channels (Daphne ASGI) packages simulation frames into JSON over WebSockets at fixed tick intervals.
   - The Three.js frontend acts strictly as a rendering engine and user input controller; it never invents physics, positions, or collision outcomes.

## Consequences
### Positive
- **Headless Testability:** 100% of physical and algorithmic logic can be validated via pytest without starting web servers or browsers.
- **RL Training Efficiency:** Gymnasium environments can run thousands of simulation steps per second headlessly during reinforcement learning training.
- **Architectural Integrity:** Clean separation of concerns prevents visualization code from introducing simulation artifacts or state desynchronization.
- **Network Resilience:** The simulation can run offline using synthetic deterministic road grids when internet access or external OSM tile servers are unavailable.

### Negative / Trade-offs
- Requires serialization of telemetry data across the WebSocket boundary.
- Requires maintaining clear interface contracts and synchronization between server tick rates and frontend rendering loops.
