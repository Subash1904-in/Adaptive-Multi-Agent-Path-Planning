# API & TELEMETRY PROTOCOL SPECIFICATION (BLUEPRINT)

> **Document Status:** Planned Architectural Specification (Phase 01)  
> **Implementation Status:** **PROPOSED / NOT IMPLEMENTED** (Implementation scheduled across Phases 2, 21, 22, 29, 35)

---

## 1. REST API Blueprint (`/api/v1/`)

All REST endpoints operate over HTTP/HTTPS with `Content-Type: application/json`. Error responses follow the RFC 7807 problem details specification.

### 1.1 Health & Service Status (Target Phase: Phase 02, refined in Phase 21)
- **`GET /api/v1/health/`**
  - **Purpose:** Liveness and readiness probe for container orchestration and CI/CD smoke tests.
  - **Request:** No body or query parameters.
  - **Success Response (`200 OK`):**
    ```json
    {
      "status": "healthy",
      "version": "1.0.0",
      "sim_engine_ready": true,
      "timestamp": "2026-10-19T15:00:00Z"
    }
    ```
  - **Error Handling:** Returns `503 Service Unavailable` if the simulation worker process is unresponsive.

---

### 1.2 Simulation Lifecycle Management (Target Phase: Phase 21)
- **`POST /api/v1/simulation/create/`**
  - **Purpose:** Initializes a new simulation instance in memory with designated configuration.
  - **Request Payload:**
    ```json
    {
      "scenario_id": "synthetic_grid_4x4",
      "agent_count": 20,
      "seed": 42,
      "v2v_radius_m": 50.0,
      "packet_loss_rate": 0.05
    }
    ```
  - **Validation Expectations:**
    - `scenario_id`: Required string matching an existing scenario fixture.
    - `agent_count`: Required integer $\in [1, 100]$.
    - `seed`: Optional integer for deterministic reproduction (default: 42).
    - `v2v_radius_m`: Required float $> 0.0$.
    - `packet_loss_rate`: Float $\in [0.0, 1.0]$.
  - **Success Response (`201 Created`):** Returns simulation instance ID, initial node/edge counts, and active agent IDs.
  - **Error Handling:** `400 Bad Request` with field validation errors if bounds are violated.

- **`POST /api/v1/simulation/control/`**
  - **Purpose:** Dispatches execution commands to the authoritative simulation clock.
  - **Request Payload:**
    ```json
    {
      "action": "PLAY" // Valid actions: "PLAY", "PAUSE", "STEP", "RESET"
    }
    ```
  - **Validation Expectations:** `action` must be one of the recognized enum strings.
  - **Success Response (`200 OK`):**
    ```json
    {
      "status": "OK",
      "current_state": "RUNNING", // "STOPPED", "RUNNING", "PAUSED"
      "tick": 420,
      "sim_time_sec": 42.0
    }
    ```
  - **Error Handling:** `409 Conflict` if attempting to step while in `RUNNING` state.

---

### 1.3 Scenario Configuration (Target Phase: Phase 21)
- **`GET /api/v1/scenarios/`**
  - **Purpose:** Enumerates available simulation scenarios (both local synthetic grids and cached OSM extracts).
  - **Success Response (`200 OK`):**
    ```json
    {
      "count": 2,
      "scenarios": [
        {
          "id": "synthetic_grid_4x4",
          "name": "Synthetic 4x4 Grid Network",
          "type": "SYNTHETIC",
          "nodes": 16,
          "edges": 48,
          "default_agents": 20
        },
        {
          "id": "osm_sample_downtown",
          "name": "OSM Downtown Sample",
          "type": "OSM",
          "nodes": 45,
          "edges": 112,
          "default_agents": 35
        }
      ]
    }
    ```

---

### 1.4 Vehicle & Road-Network State (Target Phase: Phase 21)
- **`GET /api/v1/map/`**
  - **Purpose:** Retrieves the static geometry of the currently active road graph for 3D mesh building in Three.js.
  - **Success Response (`200 OK`):**
    ```json
    {
      "scenario_id": "synthetic_grid_4x4",
      "nodes": [
        {"id": "node_01", "x": 0.0, "y": 0.0, "is_signalized": true}
      ],
      "edges": [
        {"id": "edge_01_02", "source": "node_01", "target": "node_02", "length_m": 100.0, "speed_limit_mps": 13.8, "lanes": 2}
      ],
      "crosswalks": [
        {"id": "cw_01", "node_id": "node_01", "width_m": 4.0}
      ]
    }
    ```

- **`GET /api/v1/vehicles/`**
  - **Purpose:** Paginated inspection endpoint for current vehicle states, routes, and local knowledge snapshots.
  - **Query Params:** `?page=1&limit=50&status=NAVIGATING`
  - **Success Response (`200 OK`):** Returns array of vehicle records with ID, type, route, speed, and current edge.

---

### 1.5 Simulation Metrics & Telemetry (Target Phase: Phase 21)
- **`GET /api/v1/metrics/`**
  - **Purpose:** Real-time aggregate telemetry query for the dashboard HUD.
  - **Success Response (`200 OK`):**
    ```json
    {
      "tick": 1200,
      "sim_time_sec": 120.0,
      "active_agents": 18,
      "completed_agents": 2,
      "collision_events": 0,
      "near_miss_events": 1,
      "packets_sent": 4520,
      "packets_delivered": 4310,
      "packet_delivery_rate": 0.953,
      "mean_travel_time_sec": 38.4
    }
    ```

---

### 1.6 Traffic Incident Injection (Target Phase: Phase 29)
- **`POST /api/v1/incidents/`**
  - **Purpose:** Dynamically introduces road closures, accidents, or obstacles to trigger adaptive vehicle rerouting.
  - **Request Payload:**
    ```json
    {
      "type": "ROAD_CLOSURE", // "ROAD_CLOSURE", "ACCIDENT", "OBSTACLE"
      "edge_id": "edge_01_02",
      "severity": 1.0,
      "duration_sec": 60.0
    }
    ```
  - **Validation Expectations:** `edge_id` must exist in the active graph; `severity` must be $\in (0.0, 1.0]$.
  - **Success Response (`201 Created`):** Incident ID, affected edge, and timestamp.
  - **Error Handling:** `404 Not Found` if `edge_id` does not exist.

---

### 1.7 Experiment History & Persistence (Target Phase: Phase 35)
- **`GET /api/v1/experiments/`**
  - **Purpose:** Lists stored benchmarking runs and historical evaluation metrics.
- **`POST /api/v1/experiments/export/`**
  - **Purpose:** Generates downloadable CSV/JSON archive of trajectory and benchmark data.

---

## 2. WebSocket Streaming Protocol (`ws://<host>:8000/ws/simulation/`)

**Target Phase:** Phase 22 (Django Channels)  
**Encoding:** JSON UTF-8  
**Rate:** Configurable $10\text{--}30\,\text{Hz}$ (server-throttled)

### 2.1 Backend Broadcast Event Schemas (Server $\rightarrow$ Client)

#### Category 1: `SIMULATION_SNAPSHOT` (High Frequency)
Transmitted at each tick interval to provide authoritative positions for Three.js interpolation.
```json
{
  "event": "SIMULATION_SNAPSHOT",
  "tick": 340,
  "sim_time": 34.0,
  "vehicles": [
    {
      "id": "veh_001",
      "type": "STANDARD",
      "x": 45.2,
      "y": 0.0,
      "z": -18.4,
      "heading_rad": 1.5708,
      "speed_mps": 11.2,
      "state": "NAVIGATING",
      "comm_radius": 50.0
    },
    {
      "id": "amb_001",
      "type": "EMERGENCY",
      "x": 30.0,
      "y": 0.0,
      "z": -18.4,
      "heading_rad": 1.5708,
      "speed_mps": 18.0,
      "siren_active": true,
      "comm_radius": 100.0
    }
  ],
  "pedestrians": [
    {
      "id": "ped_001",
      "x": 50.0,
      "y": 0.0,
      "z": -15.0,
      "state": "CROSSING"
    }
  ],
  "traffic_signals": [
    {"junction_id": "junc_01", "phase": "GREEN", "time_remaining_sec": 7.5}
  ]
}
```

#### Category 2: `V2V_EVENT` (Event Driven)
Notifies the client of message transmissions, range discoveries, or dropped packets.
```json
{
  "event": "V2V_EVENT",
  "tick": 342,
  "action": "TRANSMIT", // "TRANSMIT", "DELIVER", "DROP_PACKET", "PEER_DISCOVERED"
  "message_id": "msg_98234",
  "sender_id": "veh_001",
  "recipient_id": "veh_002",
  "message_type": "HAZARD_ALERT",
  "latency_ticks": 2,
  "sender_pos": {"x": 45.2, "z": -18.4}
}
```

#### Category 3: `ROUTE_CHANGE` (Event Driven)
Transmitted when an agent adaptively replans its route based on V2V alerts or sensor detections.
```json
{
  "event": "ROUTE_CHANGE",
  "tick": 345,
  "vehicle_id": "veh_002",
  "reason": "V2V_HAZARD_ALERT",
  "old_route": ["node_01", "node_02", "node_06"],
  "new_route": ["node_01", "node_03", "node_07", "node_06"],
  "cost_difference": -12.4
}
```

#### Category 4: `INCIDENT_EVENT` (Event Driven)
Notifies of dynamic environmental hazards or collision incidents.
```json
{
  "event": "INCIDENT_EVENT",
  "tick": 350,
  "incident_type": "COLLISION", // "ROAD_BLOCKAGE", "COLLISION", "NEAR_MISS"
  "involved_agents": ["veh_005", "veh_008"],
  "location": {"x": 100.0, "z": -40.0}
}
```

#### Category 5: `METRICS_UPDATE` (Low Frequency, 1 Hz)
Aggregated performance telemetry for HUD charts.
```json
{
  "event": "METRICS_UPDATE",
  "tick": 350,
  "fps": 28.5,
  "pdr": 0.945,
  "active_count": 22,
  "collisions_total": 0
}
```

#### Category 6: `CONNECTION_STATUS` / `ERROR`
```json
{
  "event": "CONNECTION_STATUS",
  "status": "CONNECTED",
  "channel_id": "sim_ch_001"
}
```

---

### 2.2 Client Interactive Commands (Client $\rightarrow$ Server)
```json
{
  "action": "COMMAND",
  "command": "STEP", // "PLAY", "PAUSE", "STEP", "RESET", "INJECT_HAZARD"
  "payload": {}
}
```
