# AMAPP Acceptance Demonstration Guide

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Phase:** 40 of 40 — Final Acceptance Audit, End-to-End Demonstration & Project Sign-Off  
**Target Environment:** Local Docker Compose or Native Python/Node Development Stack  

---

> [!IMPORTANT]
> ### Educational Simulation Boundary Notice
> AMAPP is an educational and academic multi-agent path planning simulation platform. It is developed to evaluate decentralized V2V coordination, collision avoidance invariants, adaptive rerouting heuristics, and reinforcement-learning navigation policies under controlled simulation environments.
> 
> **Simulated collision avoidance, emergency vehicle corridors, routing decisions, and learned policies in this platform DO NOT constitute certified autonomous-vehicle control software and are NOT safe for physical deployment in real-world vehicles or on public roads.**

---

## 1. Quickstart Demonstration Options

AMAPP provides two reproducible demonstration pathways:
1. **Interactive Visual 3D Demonstration:** Real-time Three.js graphical dashboard in the web browser with live 3D city visualization, timeline playback controls, V2V communication overlays, dynamic incident injection, and operational metric charts.
2. **Automated End-to-End Acceptance Script:** Scripted CLI runner (`scripts/demo_acceptance.py`) that deterministically exercises all system capabilities, verifies API contracts, steps through multi-agent scenarios, tests V2V packets, injects dynamic incidents, verifies WebSocket streams, and checks database persistence.

---

## 2. Launching the System

### Option A: Containerized Deployment (Recommended)

Ensure Docker and Docker Compose v2 are installed and running:

```bash
# 1. Build and start containers in the background
docker compose up -d --build

# 2. Verify both services are healthy
docker compose ps

# Expected output:
# NAME             IMAGE            COMMAND                  SERVICE    STATUS
# amapp-backend    amapp-backend    "daphne -b 0.0.0.0..."   backend    Up (healthy)
# amapp-frontend   amapp-frontend   "/docker-entrypoint..."  frontend   Up (healthy)
```

The services will be available at:
- **Interactive 3D Dashboard:** `http://localhost:3000`
- **REST API & Swagger:** `http://localhost:3000/api/v1/` (proxied) or `http://localhost:8000/api/v1/` (direct)
- **ASGI Real-time WebSocket:** `ws://localhost:3000/ws/v1/`

### Option B: Native Host Execution

If running without Docker:

```bash
# Terminal 1: Backend Daphne ASGI Server
cd backend
python manage.py migrate
daphne -b 127.0.0.1 -p 8000 config.asgi:application

# Terminal 2: Frontend Development Server
cd frontend
npm ci
npm run dev
# Vite runs at http://localhost:5173
```

---

## 3. Interactive 3D Demonstration Script

Follow this step-by-step demonstration in the browser at `http://localhost:3000`:

### Step 1: Scenario Selection & Initial World State
1. Observe the top navigation bar and scenario catalog selector.
2. Select **Multi-Vehicle Navigation (`scn_multi_veh`)** from the dropdown.
3. Observe the Three.js 3D viewport rendering:
   - 3D road network grid with lanes, intersections, and street markings.
   - Distinct colored autonomous vehicle meshes placed at their initial spawn nodes.
   - Surrounding procedural urban building blocks.
4. Interact with the 3D scene using mouse controls:
   - **Left Click + Drag:** Orbit camera view.
   - **Right Click + Drag:** Pan across the city grid.
   - **Scroll Wheel:** Zoom in and out.

### Step 2: Simulation Playback & Vehicle Movement
1. Click the **Play** button on the bottom playback bar.
2. Observe the vehicles moving smoothly across road segments towards their respective destination nodes.
3. Use the playback speed toggles (`0.5x`, `1.0x`, `2.0x`, `5.0x`) to observe speed adjustments.
4. Click **Pause**, then click **Step Forward (+1)** to inspect discrete tick transitions.
5. Drag the **Timeline Scrubber** backwards to inspect historical simulation states cached in the client-side history buffer.

### Step 3: V2V Communication & Neighbor Overlays
1. Click on any active vehicle in the 3D scene to inspect it.
2. In the right-hand **Entity Inspector**, observe:
   - Real-time kinematic telemetry: velocity, acceleration, odometry, heading, and distance to destination.
   - Communication radius disc ($R_{\text{comm}} = 50.0\text{m}$) rendered on the ground around the inspected vehicle.
3. In the overlay settings panel, toggle **V2V Communication Links**:
   - Active green link lines indicate reciprocal V2V neighbor pairs within communication radius.
   - Transit pulses animate along link lines when cooperative messages (speed advisories, incident warnings) are exchanged.
   - Stale or degraded links transition to dashed amber if packet loss occurs.

### Step 4: Traffic Incidents & Adaptive Rerouting
1. Open the **Incident Control Panel** from the right toolbar.
2. Select **Road Closure** incident type.
3. Choose an edge along the planned route of an approaching vehicle (e.g., `edge_r0_c0_to_r1_c0`).
4. Set severity to **High** and click **Inject Incident**.
5. Observe the 3D scene:
   - A bright orange warning marker and road closure obstruction barrier appears over the blocked edge.
   - The approaching vehicle receives the incident warning via direct perception or V2V gossip.
   - The vehicle replans its route dynamically using A* / Adaptive routing.
   - The route overlay updates in real time to show the detour trajectory avoiding the closed edge.

### Step 5: Traffic Signals & Pedestrian Interactions
1. Switch to scenario **Pedestrian Crossing (`scn_ped_crossing_walk`)**.
2. Click **Play** and observe:
   - Signalized intersection cycling through Green $\to$ Yellow $\to$ Red phases.
   - Pedestrian agent meshes traversing the designated crosswalk.
   - Vehicles approaching the crosswalk smoothly decelerating and yielding to active pedestrians in the conflict corridor, maintaining strict safety margins.

### Step 6: Emergency Vehicle Priority & Corridor Clearance
1. Switch to scenario **Ambulance Corridor (`scn_ambulance_corridor`)**.
2. Click **Play** and observe:
   - The emergency vehicle (ambulance with distinctive alternating beacon lights) broadcasting emergency reservation announcements.
   - Civilian vehicles ahead detecting the high-priority corridor, decelerating, and yielding the lane.
   - Intersections along the corridor extending green signal phases to grant preemptive right-of-way.

### Step 7: Operational Analytics & Historical Run Inspection
1. Open the **Analytics Dashboard** tab.
2. Inspect live performance graphs:
   - **Average Travel Time & Speed:** Velocity distributions over time.
   - **Safety Metrics:** Zero-collision invariant, minimum Time-To-Collision (TTC) safety margin.
   - **Communication Performance:** Packet Delivery Ratio (PDR), broadcast packet counts, and neighbor table sizes.
3. Switch to **Run History** tab to view completed runs persisted in SQLite across container restarts.

---

## 4. Automated Acceptance Demonstration Script

The platform includes a zero-dependency CLI demonstration script (`scripts/demo_acceptance.py`) that automates all verification steps.

### Running Against Containerized Deployment

```bash
python scripts/demo_acceptance.py \
  --frontend-url http://localhost:3000 \
  --backend-url http://localhost:8000 \
  --ws-url ws://localhost:3000
```

### Running in Standalone In-Process Mode

```bash
python scripts/demo_acceptance.py --standalone
```

### Demonstration Script Verification Steps

| Step | Capability Area | Description |
|---|---|---|
| **Step 01** | Infrastructure Health | Verifies `/healthz`, backend ASGI `/api/v1/health/`, and reverse proxy routing |
| **Step 02** | Scenario Discovery | Validates preloaded scenario catalog (`scn_multi_veh`, `scn_congestion_sharing`, etc.) |
| **Step 03** | Multi-Agent Simulation | Instantiates run, steps simulation, and verifies independent vehicle odometry |
| **Step 04** | V2V Communication | Queries analytics for packet counts, delivery ratio, and neighbor tables |
| **Step 05** | Pedestrian & Signals | Executes crosswalk scenario verifying vehicle yield and signal compliance |
| **Step 06** | Emergency Priority | Executes ambulance scenario verifying dynamic corridor reservation and yielding |
| **Step 07** | Dynamic Incidents | Injects road closure and verifies active incident status and adaptive rerouting |
| **Step 08** | Real-Time WebSockets | Establishes WebSocket handshake envelope (`event_type: "run.status"`) and ping/pong |
| **Step 09** | Persistence & History | Completes simulation, queries historical run database, and validates disclaimer |
| **Step 10** | Educational Disclaimer | Displays mandatory educational simulation boundary notice |

---

## 5. Teardown and Reset

To cleanly shut down containerized services:

```bash
# Stop containers and preserve database volume:
docker compose down

# Stop containers and wipe database volume (clean reset):
docker compose down -v
```
