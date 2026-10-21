# API & TELEMETRY PROTOCOL SPECIFICATION (BLUEPRINT)

> **Document Status:** Planned Architectural Specification (Phase 01)  
> **Implementation Status:** **PROPOSED / NOT IMPLEMENTED** (Implementation scheduled across Phases 2, 21, 22, 29, 35)

---

## 1. REST API Blueprint (`/api/v1/`)

All REST endpoints operate over HTTP/HTTPS with `Content-Type: application/json`. Error responses follow the RFC 7807 problem details specification.

### 1.1 Health & Service Status (Status: IMPLEMENTED & TESTED in Phase 02)
- **`GET /api/v1/health/`**
  - **Purpose:** Liveness and readiness probe for container orchestration, dev server health, and CI/CD smoke tests.
  - **Implementation:** `apps.core.views.HealthCheckView` registered at `api/v1/health/`.
  - **Authentication:** Unauthenticated (no headers/tokens required).
  - **Request:** HTTP GET with no body or parameters.
  - **Success Response (`200 OK`):**
    ```json
    {
      "status": "healthy",
      "service": "amapp-backend",
      "version": "1.0.0"
    }
    ```
  - **Test Suite:** `backend/apps/core/tests/test_health.py` (verifies 200 OK, JSON content-type, payload schema, unauthenticated access, and 404 for invalid paths).

---

### 1.2 Scenario Management (Status: IMPLEMENTED & TESTED in Phase 21)

All scenario endpoints operate on thread-safe in-memory `ScenarioDefinition` instances.

- **`GET /api/v1/scenarios/`**
  - **Purpose:** Enumerates available simulation scenarios (preloaded defaults and custom-registered scenarios) with compact metadata.
  - **Success Response (`200 OK`):**
    ```json
    [
      {
        "id": "scn_single_veh",
        "name": "Single Vehicle Grid Scenario",
        "description": "Synthetic grid navigation with a single vehicle agent.",
        "version": "1.0.0",
        "author": "AMAPP Core",
        "vehicle_count": 1,
        "road_network_source": "synthetic_grid",
        "time_step_s": 0.1,
        "max_ticks": 200,
        "effective_max_ticks": 200
      }
    ]
    ```

- **`POST /api/v1/scenarios/`**
  - **Purpose:** Validates and registers a new `ScenarioDefinition` in the registry.
  - **Request Payload:** Complete JSON dictionary corresponding to `ScenarioDefinition.to_dict()`.
  - **Success Response (`201 Created`):** Returns full `ScenarioDefinition` dictionary including academic disclaimer.
  - **Error Handling:**
    - `400 Bad Request` (`VALIDATION_ERROR`): Missing required fields or invalid numeric bounds.
    - `409 Conflict` (`DUPLICATE_SCENARIO_ID`): A scenario with the given ID already exists.

- **`GET /api/v1/scenarios/{scenario_id}/`**
  - **Purpose:** Retrieves the complete authoritative definition of a scenario.
  - **Success Response (`200 OK`):** Returns scenario dictionary with metadata, road network, vehicles, signals, crosswalks, pedestrians, emergencies, and subsystem configurations.
  - **Error Handling:** `404 Not Found` (`SCENARIO_NOT_FOUND`) if `scenario_id` is not registered.

- **`POST /api/v1/scenarios/validate/`**
  - **Purpose:** Validates a scenario payload without registering it in memory.
  - **Success Response (`200 OK`):**
    ```json
    {
      "valid": true,
      "scenario_id": "test_scn",
      "scenario_name": "Test Scenario",
      "disclaimer": "AMAPP is an educational simulation framework and is not intended for real-world autonomous vehicle safety-critical control."
    }
    ```
  - **Error Handling:** `400 Bad Request` (`VALIDATION_ERROR`) with details on invalid fields.

---

### 1.3 Simulation Run Lifecycle & Control (Status: IMPLEMENTED & TESTED in Phase 21)

Endpoints for initializing, stepping, cancelling, and inspecting scenario simulation runs.

- **`GET /api/v1/runs/`**
  - **Purpose:** Lists all active and past simulation runs.
  - **Success Response (`200 OK`):** Array of run status objects.

- **`POST /api/v1/runs/`**
  - **Purpose:** Initializes a new `ScenarioRunner` in `READY` state.
  - **Request Payload:**
    ```json
    {
      "scenario_id": "scn_single_veh",
      "run_id": "run_custom_01",
      "max_ticks": 100,
      "max_duration_s": 10.0,
      "time_step_s": 0.1,
      "stop_on_all_arrived": true,
      "seed": 42
    }
    ```
  - **Success Response (`201 Created`):**
    ```json
    {
      "run_id": "run_custom_01",
      "scenario_id": "scn_single_veh",
      "scenario_name": "Single Vehicle Grid Scenario",
      "lifecycle_state": "READY",
      "current_tick": 0,
      "elapsed_time_s": 0.0,
      "is_terminal": false,
      "arrived_count": 0,
      "active_count": 1,
      "total_vehicles": 1,
      "scenario_fingerprint": "...",
      "initial_world_state_fingerprint": "...",
      "commit_sha": "...",
      "disclaimer": "AMAPP is an educational simulation framework..."
    }
    ```
  - **Error Handling:**
    - `400 Bad Request` (`VALIDATION_ERROR`): Missing both `scenario_id` and `scenario`.
    - `404 Not Found` (`SCENARIO_NOT_FOUND`): Provided `scenario_id` does not exist.
    - `409 Conflict` (`DUPLICATE_RUN_ID`): `run_id` already exists in registry.

- **`GET /api/v1/runs/{run_id}/`**
  - **Purpose:** Retrieves point-in-time status of a simulation run.
  - **Success Response (`200 OK`):** Point-in-time status object.
  - **Error Handling:** `404 Not Found` (`RUN_NOT_FOUND`).

- **`POST /api/v1/runs/{run_id}/step/`**
  - **Purpose:** Advances the simulation run by $N$ discrete time steps or executes to completion.
  - **Request Payload (Optional):**
    ```json
    {
      "ticks": 1,
      "run_to_completion": false,
      "target_accels": {"veh_01": 1.5}
    }
    ```
  - **Success Response (`200 OK`):** Updated execution state, arrived/active vehicle counts, tick results, and completion reason.
  - **Error Handling:**
    - `404 Not Found` (`RUN_NOT_FOUND`).
    - `409 Conflict` (`LIFECYCLE_CONFLICT`): Attempting to step a run in a terminal state (`COMPLETED`, `CANCELLED`, `FAILED`, `LIMIT_REACHED`).

- **`POST /api/v1/runs/{run_id}/cancel/`**
  - **Purpose:** Requests cooperative cancellation of an active simulation run.
  - **Request Payload (Optional):**
    ```json
    {
      "reason": "Operator requested stop"
    }
    ```
  - **Success Response (`200 OK`):** Run status transitioning to `CANCELLED`.
  - **Error Handling:**
    - `409 Conflict` (`LIFECYCLE_CONFLICT`): If run has already completed or terminated.

---

### 1.4 Simulation Results, Metrics & Telemetry (Status: IMPLEMENTED & TESTED in Phase 21)

- **`GET /api/v1/runs/{run_id}/result/`**
  - **Purpose:** Retrieves the full `ScenarioExecutionResult` for a run (final or intermediate).
  - **Success Response (`200 OK`):** Full execution result dictionary with final world snapshot and reproducibility fingerprints.

- **`GET /api/v1/runs/{run_id}/metrics/`**
  - **Purpose:** Retrieves cross-subsystem aggregated metrics compiled by `MetricsAggregator`.
  - **Success Response (`200 OK`):**
    ```json
    {
      "run_id": "run_01",
      "lifecycle_state": "RUNNING",
      "current_tick": 10,
      "metrics": {
        "simulation": {"vehicles_registered": 1, "vehicles_arrived": 0, "vehicles_active": 1, "simulated_duration_s": 1.0, "time_step_s": 0.1},
        "kinematics": {"total_distance_traveled_m": 8.5, "max_speed_observed_mps": 3.0, "average_speed_mps": 1.8},
        "routing": {"reroutes_evaluated": 0, "reroutes_accepted": 0},
        "communication": {"messages_sent": 10, "messages_delivered": 10, "packet_delivery_ratio": 1.0},
        "coordination": {"conflicts_detected": 0, "conflicts_resolved": 0},
        "safety": {"pair_checks": 0, "near_misses": 0, "actual_collisions": 0},
        "pedestrians": {"crosswalk_waits": 0, "crosswalk_crossings_completed": 0},
        "emergency": {"corridors_created": 0, "corridors_active_final": 0},
        "decision": {"evaluations_total": 0, "decisions_accepted": 0}
      },
      "disclaimer": "AMAPP is an educational simulation framework..."
    }
    ```

- **`GET /api/v1/runs/{run_id}/telemetry/`**
  - **Purpose:** Queries bounded in-memory telemetry records with optional multi-attribute filters.
  - **Query Parameters:**
    - `record_type`: Event category (e.g., `vehicle_state`, `safety_event`, `run_state_change`).
    - `name`: Specific event name string.
    - `tick_start`: Minimum inclusive tick index (int $\ge 0$).
    - `tick_end`: Maximum inclusive tick index (int $\ge 0$).
    - `limit`: Maximum records returned (int $\in [1, 50000]$).
  - **Success Response (`200 OK`):**
    ```json
    {
      "run_id": "run_01",
      "total_records_buffered": 52,
      "query_returned_count": 5,
      "drop_stats": {"total_dropped": 0, "by_category": {}},
      "records": [ ... ],
      "disclaimer": "AMAPP is an educational simulation framework..."
    }
    ```

- **`GET /api/v1/runs/{run_id}/export/`**
  - **Purpose:** Exports execution result and telemetry observations as RFC 8259 valid JSON.
  - **Query Parameters:**
    - `max_bytes`: Maximum allowed payload size in bytes (default: `10000000`).
    - `indent`: Optional indentation spaces (e.g. `2`).
    - `max_telemetry_records`: Optional cap on telemetry records included in export.
  - **Success Response (`200 OK`):** Direct JSON payload with `Content-Type: application/json`.
  - **Error Handling:** `413 Payload Too Large` (`EXPORT_SIZE_LIMIT_EXCEEDED`) if serialized byte size exceeds `max_bytes`.


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
