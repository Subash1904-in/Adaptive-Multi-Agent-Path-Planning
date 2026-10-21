# API & TELEMETRY PROTOCOL SPECIFICATION

> **Document Status:** Authoritative Architectural & API Specification  
> **Implementation Status:** **IMPLEMENTED & TESTED across Phases 02, 21, and 22** (All core REST endpoints and WebSocket live streaming fully tested)

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
    - `409 Conflict` (`CONCURRENT_STEP_IN_PROGRESS`): Attempting to dispatch a step request while a previous step execution is actively in progress on the runner's execution lock.

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
  - **Purpose:** Retrieves cross-subsystem aggregated metrics and deterministic operational analytics.
  - **Query Parameters (Optional):**
    - `tick_start`: Minimum inclusive tick index (int $\ge 0$).
    - `tick_end`: Maximum inclusive tick index (int $\ge 0$, must be $\ge \text{tick\_start}$).
    - `time_window_start_s`: Minimum simulated time window boundary (float $\ge 0.0$).
    - `time_window_end_s`: Maximum simulated time window boundary (float $\ge 0.0$, must be $\ge \text{time\_window\_start\_s}$).
    - `limit_samples`: Maximum time-series sample points returned (int $\in [1, 5000]$, default 500).
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
      "analytics": {
        "trips": {
          "completed_trips": 0,
          "total_trips": 1,
          "active_trips": 1,
          "completion_rate_pct": 0.0
        },
        "travel_time_distribution": {
          "sample_count": 0,
          "mean_s": null,
          "median_s": null,
          "p90_s": null,
          "p95_s": null,
          "min_s": null,
          "max_s": null,
          "bins": []
        },
        "throughput": {
          "total_crossings": 0,
          "crossings_per_minute": 0.0,
          "top_intersections": []
        },
        "safety": {
          "actual_collisions": 0,
          "near_misses": 0,
          "min_separation_observed_m": null,
          "min_ttc_observed_s": null
        },
        "communication": {
          "messages_sent": 10,
          "messages_delivered": 10,
          "pdr": 1.0,
          "loss_rate": 0.0,
          "latency_ms_available": false,
          "loss_breakdown": {
            "distance_attenuation": 0,
            "snr_fading": 0,
            "hidden_terminal": 0
          }
        },
        "routing": {
          "reroutes_evaluated": 0,
          "reroutes_accepted": 0,
          "acceptance_rate_pct": null
        },
        "incidents": {
          "total_active": 0,
          "active_by_type": {
            "road_closure": 0,
            "congestion": 0,
            "obstacle": 0,
            "signal_override": 0
          }
        },
        "time_series": [
          {
            "tick": 10,
            "sim_time_s": 1.0,
            "completed_trips": 0,
            "pdr": 1.0,
            "collisions": 0,
            "near_misses": 0,
            "active_incidents": 0,
            "reroutes_accepted": 0
          }
        ]
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

### 1.5 Interactive Traffic Incident Management (Status: IMPLEMENTED & TESTED in Phase 29)

Endpoints for querying, creating, and removing dynamic traffic incidents (road closures, congestion, obstacles, signal phase overrides) on active simulation runs.

- **`GET /api/v1/runs/{run_id}/incidents/`**
  - **Purpose:** Enumerates active and resolved incidents for the specified simulation run.
  - **Success Response (`200 OK`):**
    ```json
    {
      "run_id": "run_01",
      "count": 1,
      "incidents": [
        {
          "id": "inc_9f2a1b",
          "incident_type": "road_closure",
          "severity": "high",
          "status": "active",
          "affected_edge_id": "edge_north",
          "affected_node_id": null,
          "position": {"x": 10.0, "y": 20.0},
          "reported_timestamp_s": 5.2,
          "description": "Emergency road closure due to maintenance",
          "delay_multiplier": 1.0,
          "obstacle_type": null,
          "override_phase": null
        }
      ],
      "disclaimer": "AMAPP is an educational simulation framework..."
    }
    ```

- **`POST /api/v1/runs/{run_id}/incidents/`**
  - **Purpose:** Dynamically injects an authoritative traffic incident into the running simulation world.
  - **Request Payload:**
    ```json
    {
      "incident_type": "road_closure",
      "severity": "high",
      "affected_edge_id": "edge_north",
      "description": "Emergency utility maintenance"
    }
    ```
    *Additional parameters per incident type:*
    - **`road_closure`**: Requires valid `affected_edge_id`. Disseminates `RoadClosureReport` (status `CLOSED`), setting edge traversal cost to $\infty$ in `DynamicRouteAdapter`.
    - **`congestion`**: Requires valid `affected_edge_id`. Optional `delay_multiplier` (float $\ge 1.0$, default 2.0). Disseminates `CongestionReport`.
    - **`obstacle`**: Requires valid `affected_edge_id`. Optional `obstacle_type` (`CONSTRUCTION`, `DEBRIS`, `STALLED_VEHICLE`, `STATIC_BARRIER`).
    - **`signal_override`**: Requires valid `affected_node_id` (or `signal_id`). Requires `override_phase` (`RED`, `YELLOW`, `GREEN`). Intercepts `TrafficSignalController` cycle.
  - **Success Response (`201 Created`):** Returns complete serialized incident representation.
  - **Error Handling:**
    - `400 Bad Request` (`VALIDATION_ERROR`): Missing required fields, invalid edge ID, invalid signal node ID, or terminal run state (`COMPLETED`, `CANCELLED`, `FAILED`).
    - `404 Not Found` (`RUN_NOT_FOUND`): Run ID does not exist in the active runner registry.

- **`DELETE /api/v1/runs/{run_id}/incidents/{incident_id}/`**
  - **Purpose:** Deactivates/removes an active incident, restoring road traversability and baseline signal controller progression.
  - **Success Response (`200 OK`):**
    ```json
    {
      "run_id": "run_01",
      "incident_id": "inc_9f2a1b",
      "status": "resolved",
      "disclaimer": "AMAPP is an educational simulation framework..."
    }
    ```
  - **Error Handling:**
    - `400 Bad Request` (`TERMINAL_RUN`): Run is in a terminal state.
    - `404 Not Found` (`INCIDENT_NOT_FOUND`): Incident ID not found on this run.

---

### 1.7 Experiment History & Persistence (Target Phase: Phase 35)
- **`GET /api/v1/experiments/`**
  - **Purpose:** Lists stored benchmarking runs and historical evaluation metrics.
- **`POST /api/v1/experiments/export/`**
  - **Purpose:** Generates downloadable CSV/JSON archive of trajectory and benchmark data.

---

## 2. WebSocket Streaming Protocol (`ws://<host>:8000/ws/v1/runs/{run_id}/`)

> **Document Status:** Authoritative Architectural Contract  
> **Implementation Status:** **IMPLEMENTED & TESTED in Phase 22** (42 automated tests passing)  
> **Endpoint Route:** `ws://<host>:8000/ws/v1/runs/{run_id}/`  
> **ASGI Server:** Daphne 4.2+ (Protocol router in `backend/config/asgi.py`)  
> **Encoding:** UTF-8 JSON text frames  
> **Schema Version:** `1.0.0`

---

### 2.1 Connection Handshake, Origin Validation, and Close Codes

Clients connect to a specific simulation run channel via `ws://<host>:8000/ws/v1/runs/{run_id}/`.

1. **Origin Verification:** Handshake is evaluated by `SimulationOriginValidator`. In production or authenticated modes, origins must match `ALLOWED_HOSTS` or `AMAPP_WS_ALLOWED_ORIGINS`. Disallowed origins are rejected with close code `4401`.
2. **Run Existence Check:** The consumer resolves `run_id` against `RunRegistry`. If the run does not exist, connection is immediately closed with code `4404`.
3. **Connection ACK:** Upon successful connection, the server immediately sends a `connection.ack` event with schema version `1.0.0`, current run state, initial tick, and educational disclaimer.

#### WebSocket Close Codes
| Close Code | Constant Name | Condition |
| :--- | :--- | :--- |
| `1000` | Normal Closure | Clean disconnect by client or server shutdown. |
| `4400` | Bad Request | Malformed JSON payload or invalid/unknown client command. |
| `4401` | Unauthorized | Disallowed HTTP `Origin` header during handshake. |
| `4404` | Run Not Found | `run_id` was not found in the authoritative `RunRegistry`. |
| `4409` | Lifecycle Conflict | Client attempted to mutate a run in an invalid or terminal state. |

---

### 2.2 Standard WebSocket Event Envelope (Server $\rightarrow$ Client)

All server-to-client broadcasts conform strictly to a standardized envelope format:

```json
{
  "event_type": "simulation.snapshot",
  "run_id": "run_001",
  "sequence": 142,
  "tick": 24,
  "timestamp_s": 2.4,
  "schema_version": "1.0.0",
  "payload": { ... },
  "disclaimer": "AMAPP is an educational simulation framework and is not intended for real-world autonomous vehicle safety-critical control."
}
```

#### Field Specifications:
- `event_type` (`string`): One of the 21 defined `SimulationEventType` identifiers.
- `run_id` (`string`): Unique identifier of the simulation run.
- `sequence` (`integer` $\ge 0$): Monotonically increasing sequence number per event stream.
- `tick` (`integer` $\ge 0$): Discrete simulation tick when the event was generated.
- `timestamp_s` (`float` $\ge 0.0$): Simulated elapsed time in seconds.
- `schema_version` (`string`): SemVer string representing protocol contract version (`"1.0.0"`).
- `payload` (`object`): Event-specific dictionary.
- `disclaimer` (`string`): Academic and educational simulation disclaimer.

---

### 2.3 Catalog of 23 Server Broadcast Event Types

#### 1. Lifecycle Events (Critical — Zero-Drop)
- **`run.state_change`**: Lifecycle transition (e.g., `READY` $\rightarrow$ `RUNNING`). Payload: `{"from_state": "READY", "to_state": "RUNNING", "current_tick": 0}`.
- **`run.step`**: Notification of tick step completion. Payload: `{"tick": 1, "sim_time_s": 0.1, "arrived_count": 0, "active_count": 1}`.
- **`run.completed`**: Normal run completion. Payload: `{"completed_ticks": 150, "duration_s": 15.0, "reason": "all_vehicles_arrived"}`.
- **`run.cancelled`**: Operator cancellation. Payload: `{"cancelled_tick": 45, "reason": "operator_request"}`.
- **`run.failed`**: Execution failure. Payload: `{"failed_tick": 12, "error_message": "..."}`.
- **`run.limit_reached`**: Ticks or duration cap exceeded. Payload: `{"max_ticks": 200, "completed_ticks": 200}`.

#### 2. High-Frequency State Events (Sampled / Backpressure-Droppable)
- **`simulation.snapshot`**: Full world state at step boundary. Payload: `{"vehicles": [...], "traffic_signals": [...], "pedestrians": [...]}`.
- **`vehicle.state`**: Kinematic vehicle update. Payload: `{"vehicle_id": "veh_01", "position": {"x": 12.4, "y": 0.0}, "speed_mps": 8.5, "heading_rad": 1.57, "lifecycle_state": "en_route", "route_id": "route_01", "route": ["n0", "n1", "n2"], "remaining_route_distance_m": 48.5, "current_node_id": "n0", "target_node_id": "n1"}`.
- **`traffic_signals.update`**: Phase change for signals. Payload: `{"signal_id": "sig_01", "node_id": "int_01", "state": "GREEN", "time_to_green_s": 0.0, "time_to_red_s": 25.0}`.

#### 3. Subsystem Domain Events (Event-Driven)
- **`incident.created`**: Real-time notification of newly injected incident (road closure, congestion, obstacle, or signal override). Payload: serialized `Incident` object.
- **`incident.removed`**: Real-time notification of removed/resolved incident. Payload: `{"incident_id": "inc_01"}`.
- **`safety.event`**: Conflict detection, near-miss, or emergency deceleration override. Payload: `{"event_type": "near_miss", "vehicle_id": "veh_01", "other_id": "veh_02", "ttc_s": 1.4, "action": "emergency_brake"}`.
- **`routing.reroute`**: Dynamic reroute decision evaluated. Payload: `{"vehicle_id": "veh_01", "decision": "accept", "reason": "avoid_closure", "new_route": [...]}`.
- **`route.changed`**: Dynamic route update notification with explanation telemetry. Payload: `{"vehicle_id": "veh_01", "old_route_id": "r_old", "new_route_id": "r_new", "route": ["n0", "n_detour", "n2"], "decision_type": "reroute_accepted", "reason": "High traffic congestion detected on edge E1", "current_cost": 120.0, "candidate_cost": 95.0, "cost_improvement": 25.0, "candidate_node_ids": ["n0", "n_detour", "n2"]}`.
- **`communication.message`**: V2V packet transmitted or delivered. Triggers frontend 3D message transit pulse animations. Payload: `{"message_id": "msg_01", "sender_id": "veh_01", "message_type": "heartbeat", "receivers": ["veh_02"]}`.
- **`communication.impairment`**: Packet loss, degradation, or link outage. Triggers frontend 3D drop indicators and network degradation highlights. Payload: `{"outage_type": "partition", "affected_nodes": ["veh_01", "veh_02"], "burst_loss": false, "pdr": 0.95}`.
- **`communication.event`**: General V2V event envelope emitted during stepping. Carries sender/receiver coordinates, packet status (`delivered`, `dropped_distance`, `dropped_burst`), and latency.
- **`coordination.report`**: Congestion or road closure dissemination. Payload: `{"report_id": "rep_01", "report_type": "congestion", "edge_id": "edge_north", "confidence": 0.85}`.
- **`pedestrian.state`**: Pedestrian corridor crossing update. Payload: `{"pedestrian_id": "ped_01", "crosswalk_id": "cw_01", "lifecycle_state": "crossing"}`.
- **`emergency.event`**: Emergency vehicle corridor request or activation. Payload: `{"vehicle_id": "amb_01", "emergency_type": "ambulance", "priority_level": 2, "corridor": [...]}`.
- **`decision.evaluated`**: Autonomous policy scoring result. Payload: `{"vehicle_id": "veh_01", "outcome": "accept", "selected_candidate_id": "route_b", "scores": [...]}`.

#### 4. Diagnostic, Transport & Telemetry Events
- **`connection.ack`**: Handshake acknowledgement. Payload: `{"run_id": "run_01", "status": "READY", "initial_tick": 0}`.
- **`telemetry.gap`**: Notification of missed telemetry records due to outbound buffer overflow (`"reason": "buffer_overflow"`) or expired history during replay (`"reason": "expired_history"`). Payload includes `dropped_count` and `from_sequence`/`to_sequence`.
- **`metrics.summary`**: Periodic aggregated cross-subsystem metrics. Payload matches `MetricsAggregator.to_dict()`.
- **`heartbeat`**: Server-originated ping/keepalive frame. Payload: `{"server_time_s": 1729528000.0}`.
- **`error`**: Structured error notification. Payload: `{"error_code": "INVALID_COMMAND", "message": "..."}`.

---

### 2.4 Client Commands (Client $\rightarrow$ Server)

Clients send JSON text messages to the consumer:

```json
{
  "type": "step",
  "ticks": 5
}
```

#### Supported Commands:
1. **`subscribe`**:
   - Optional parameters: `from_sequence` (`integer`) or `from_tick` (`integer`).
   - Requests historical telemetry replay from in-memory ring buffer (up to `AMAPP_WS_MAX_REPLAY_RECORDS = 500`).
   - If requested history has already been evicted from the collector, a `telemetry.gap` event with `"reason": "expired_history"` is delivered first.
2. **`unsubscribe`**:
   - Stops event streaming to the consumer while keeping the WebSocket open.
3. **`step`**:
   - Optional parameters: `ticks` (`integer`, default: 1), `run_to_completion` (`boolean`, default: false), `target_accels` (`object`).
   - Advances the simulation runner and streams resulting tick events.
4. **`cancel`**:
   - Optional parameters: `reason` (`string`).
   - Requests cooperative cancellation of the running scenario.
5. **`ping` / `heartbeat`**:
   - Client keepalive probe. Server responds with a `heartbeat` event.

---

### 2.5 Backpressure and Bounded Outbound Queueing

To protect server responsiveness against slow WebSocket clients:
- Each connected consumer maintains an asynchronous, bounded outbound queue (`AMAPP_WS_MAX_QUEUE_SIZE = 128` messages).
- **Critical Event Preservation:** Critical events (`run.state_change`, `run.completed`, `run.cancelled`, `run.failed`, `connection.ack`, `telemetry.gap`) are marked non-droppable and wait for queue space.
- **Non-Critical Drop Policy:** If the outbound queue is full when high-frequency state updates arrive, non-critical events are discarded, and an internal drop counter increments.
- **Gap Notification:** When queue space recovers, a `telemetry.gap` event with `"reason": "buffer_overflow"` and `"dropped_count": N` is immediately queued to inform the client of the gap.

