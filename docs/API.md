# API & TELEMETRY PROTOCOL SPECIFICATION

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles  
**Protocol Version:** 1.0.0-draft  
**Transports:** HTTP / JSON (REST) and WebSockets / JSON (Real-Time Telemetry)

---

## 1. REST API Endpoints (`/api/v1/`)

### 1.1 Health & Status
- **`GET /api/v1/health/`**
  - **Description:** Verifies service health and backend readiness.
  - **Response `200 OK`:**
    ```json
    {
      "status": "healthy",
      "version": "1.0.0",
      "timestamp": "2026-10-19T14:30:00Z"
    }
    ```

### 1.2 Scenario Management
- **`GET /api/v1/scenarios/`**
  - **Description:** Lists available simulation scenarios (synthetic grids, real-world OSM maps).
  - **Response `200 OK`:**
    ```json
    {
      "count": 2,
      "scenarios": [
        {
          "id": "synthetic_grid_4x4",
          "name": "Synthetic 4x4 Grid Network",
          "description": "Deterministic local fallback grid with 16 intersections and traffic signals",
          "default_agents": 20
        },
        {
          "id": "osm_sample_downtown",
          "name": "OSM Sample Downtown Intersection",
          "description": "OpenStreetMap real-world road geometry with multi-lane segments",
          "default_agents": 35
        }
      ]
    }
    ```

- **`POST /api/v1/scenarios/load/`**
  - **Description:** Loads and initializes a scenario in the simulation engine.
  - **Payload:**
    ```json
    {
      "scenario_id": "synthetic_grid_4x4",
      "agent_count": 15,
      "seed": 42,
      "v2v_radius_m": 50.0,
      "packet_loss_rate": 0.05
    }
    ```
  - **Response `200 OK`:**
    ```json
    {
      "status": "LOADED",
      "scenario_id": "synthetic_grid_4x4",
      "nodes_count": 16,
      "edges_count": 48,
      "active_agents": 15
    }
    ```

### 1.3 Simulation Control
- **`POST /api/v1/simulation/control/`**
  - **Description:** Dispatches execution commands to the simulation runner.
  - **Payload:**
    ```json
    {
      "action": "PLAY" // Options: "PLAY", "PAUSE", "STEP", "RESET"
    }
    ```
  - **Response `200 OK`:**
    ```json
    {
      "status": "OK",
      "current_state": "RUNNING",
      "tick": 420
    }
    ```

### 1.4 Benchmark Metrics
- **`GET /api/v1/benchmarks/latest/`**
  - **Description:** Retrieves aggregate benchmark performance metrics.
  - **Response `200 OK`:**
    ```json
    {
      "total_ticks": 1200,
      "elapsed_sim_time_sec": 120.0,
      "agents_completed": 18,
      "active_agents": 2,
      "collision_events": 0,
      "near_miss_events": 1,
      "v2v_packets_sent": 8420,
      "v2v_packets_delivered": 7980,
      "packet_delivery_rate": 0.947,
      "mean_travel_time_sec": 42.6
    }
    ```

---

## 2. WebSocket Telemetry Stream

- **Endpoint:** `ws://<host>:8000/ws/simulation/`
- **Protocol:** `amapp-v1`
- **Streaming Rate:** 10–30 frames per second (configurable)

### 2.1 Backend Broadcast Frame (`SIMULATION_FRAME`)
Sent by the Django Channels consumer at each simulation step:
```json
{
  "type": "SIMULATION_FRAME",
  "tick": 105,
  "sim_time": 10.5,
  "vehicles": [
    {
      "id": "veh_01",
      "type": "STANDARD",
      "x": 42.15,
      "y": 0.0,
      "z": -12.4,
      "heading_rad": 1.5708,
      "speed_mps": 11.2,
      "state": "NAVIGATING",
      "route": ["n1", "n4", "n9"],
      "comm_radius": 50.0
    },
    {
      "id": "amb_01",
      "type": "EMERGENCY",
      "x": 30.0,
      "y": 0.0,
      "z": -12.4,
      "heading_rad": 1.5708,
      "speed_mps": 18.5,
      "siren_active": true,
      "comm_radius": 100.0
    }
  ],
  "pedestrians": [
    {
      "id": "ped_01",
      "x": 45.0,
      "y": 0.0,
      "z": -8.0,
      "state": "CROSSING"
    }
  ],
  "traffic_signals": [
    {
      "junction_id": "junc_01",
      "phase": "GREEN",
      "time_remaining_sec": 6.4
    }
  ],
  "v2v_events": [
    {
      "sender_id": "veh_01",
      "type": "HAZARD_ALERT",
      "hazard_type": "CONGESTION",
      "location": {"x": 42.15, "z": -12.4},
      "radius": 50.0
    }
  ],
  "metrics": {
    "active_agents": 16,
    "collisions": 0,
    "pdr": 0.96
  }
}
```

### 2.2 Client Interactive Commands
Sent from the Three.js dashboard back to the server:
```json
{
  "action": "INJECT_HAZARD",
  "hazard_type": "ROAD_BLOCKAGE",
  "edge_id": "edge_n4_n9"
}
```
