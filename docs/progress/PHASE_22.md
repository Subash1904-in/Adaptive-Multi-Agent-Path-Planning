# Phase 22 Engineering Progress Report: Django Channels WebSockets for Live Simulation and Telemetry Streaming

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Date:** 2026-10-21  
**Baseline Git Commit:** `7cad5d6` (implementation commit `41359f8`)  
**Branch:** `main`  
**Phase Status:** COMPLETED  

---

## 1. Executive Summary & Phase Objective

Phase 22 implements a production-grade, real-time asynchronous WebSocket transport layer using Django Channels 4 and Daphne ASGI around the existing simulation services. Clients observing an active or completed simulation run subscribe over a dedicated, versioned route (`ws://host/ws/v1/runs/{run_id}/`) to receive streaming updates of simulation lifecycle transitions, vehicle kinematic updates, pedestrian movements, traffic signal state changes, route re-planning decisions, V2V communication events, safety warnings, collision detections, emergency vehicle priority corridors, periodic subsystem metrics snapshots, and heartbeats.

Crucially, the WebSocket consumer layer acts purely as an observation and control-message transport. It adheres strictly to the project's architectural boundary:
- WebSockets **never** implement a secondary simulation engine.
- WebSockets **never** mutate `WorldState` or `SimulationEngine` directly.
- All simulation queries, stepping, cancellations, and telemetry records are delegated to `SimulationService`, `RunRegistry`, and `ScenarioRunner`.
- Broadcaster failures or disconnected clients never alter simulation decisions, interrupt ticks, or corrupt runner state.

### Key Architectural Deliverables:
1. **ASGI Application Entrypoint & Channels Integration**:
   - `backend/config/asgi.py` combines standard Django HTTP request handling with an asynchronous WebSocket routing stack (`SimulationOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))`).
   - `SimulationOriginValidator` permits non-browser programmatic clients (CLI tools, headless test runners) while enforcing strict `ALLOWED_HOSTS` browser Origin validation.
2. **Versioned WebSocket Route & Consumer Architecture**:
   - Versioned endpoint: `ws://host/ws/v1/runs/{run_id}/` (with `wss://` supported under TLS).
   - Validates `run_id` syntax and verifies run existence in `default_run_registry`. Rejects unknown runs with close code `4404` and structured error envelope.
   - Prevents cross-run subscriptions: channel layer groups are strictly derived server-side as `run_{run_id}`. A client can never supply an arbitrary channel group name or override its bound `run_id`.
3. **Standardized Versioned JSON Message Protocol (Schema 1.0.0)**:
   - Server-to-client message envelope:
     ```json
     {
       "schema_version": "1.0.0",
       "message_id": "ws_msg_...",
       "event_type": "...",
       "run_id": "...",
       "tick": 0,
       "simulation_time_s": 0.0,
       "sequence": 0,
       "payload": { ... }
     }
     ```
   - Supported server-to-client event types:
     - Lifecycle: `run.status`, `run.started`, `run.completed`, `run.cancelled`, `run.failed`
     - State & Entities: `world.snapshot`, `vehicle.updated`, `pedestrian.updated`
     - Infrastructure & Routing: `signal.updated`, `route.changed`
     - Network & Safety: `communication.event`, `coordination.event`, `safety.event`, `collision.detected`
     - Emergency & Decisions: `emergency.updated`, `corridor.updated`, `decision.updated`
     - Metrics & Control: `metrics.snapshot`, `telemetry.gap`, `server.heartbeat`, `error`
   - Client-to-server supported messages: `subscribe`, `unsubscribe`, `heartbeat` (or `ping`), and optional staff-authorized control extensions `step` and `cancel`.
4. **Decoupled Event Broadcasting**:
   - `SimulationEventBroadcaster` attaches listeners to `TelemetryCollector` instances.
   - Dispatches observations via `channel_layer.group_send`.
   - Adaptive async/sync dispatch schedules tasks on running event loops without blocking synchronous engine threads.
   - Catches and logs all channel layer exceptions, ensuring runner isolation.
5. **Bounded Outbound Queues, Backpressure & Gap Notifications**:
   - Outbound queue bounded by `AMAPP_WS_MAX_QUEUE_SIZE=128`.
   - When queue saturates, non-critical events are dropped, tracking dropped counts and sequence ranges.
   - Critical events (`run.completed`, `run.failed`, `run.cancelled`, `safety.event`, `collision.detected`, `error`) are prioritized, evicting non-critical events to guarantee non-lossy delivery.
   - Upon buffer drainage, a `telemetry.gap` notification (`reason="buffer_overflow"`) is prepended so clients detect delivery gaps without inventing data.
6. **Bounded Telemetry Replay & Cursor Semantics**:
   - Replay requested via `last_sequence` or `replay_from_tick`, capped by `AMAPP_WS_MAX_REPLAY_RECORDS=500`.
   - If requested sequence precedes retained telemetry, consumer emits a `telemetry.gap` notification (`reason="expired_history"`).
7. **Authentication, Authorization & Security**:
   - Aligns with Phase 21 security model: anonymous connections allowed in dev mode when `AMAPP_API_REQUIRE_AUTHENTICATION=False`, rejected with close code `4401` (`UNAUTHENTICATED`) when `True`.
   - Non-staff users denied simulation control actions (`PERMISSION_DENIED`).
   - Query parameter credential passing prohibited; secrets and tracebacks never leaked.
8. **Automated Testing & Coverage**:
   - 42 new comprehensive asynchronous WebSocket tests across 5 test suites.
   - Total regression test suite: **1,095 passing tests**, **95.66% line coverage**.

---

## 2. Baseline State & Starting Repository Context

- **Baseline Commit:** `7cad5d6` (following Phase 21 completion).
- **Reported Phase 21 Implementation Commit:** `41359f8`.
- **Baseline Test Suite:** 1,053 passing tests, 0 failures, 95.77% coverage.
- **Working Tree:** Clean.

---

## 3. Dependency Verification

Verified and pinned dependencies:
- `channels==4.3.2` (specifier `channels>=4.1.0,<4.4.0` in `requirements.txt`)
- `daphne==4.2.3` (specifier `daphne>=4.1.0,<4.3.0` in `requirements.txt`)
- `pytest-asyncio==0.23.8` (specifier `pytest-asyncio>=0.23.0,<0.24.0` in `requirements-dev.txt`)
- Compatibility maintained with `django==5.1.15`, `pytest==8.2.2`, `pytest-cov==5.0.0`, `pytest-django==4.8.0`, and Python 3.11.

---

## 4. Subsystem Architecture & Implementation Details

### 4.1 Configuration & ASGI (`backend/config/settings.py` & `backend/config/asgi.py`)
- `"daphne"` placed at the very top of `INSTALLED_APPS` to ensure ASGI development server priority.
- `"channels"` added to `INSTALLED_APPS`.
- In-memory channel layer configured:
  ```python
  CHANNEL_LAYERS = {
      "default": {
          "BACKEND": "channels.layers.InMemoryChannelLayer",
      },
  }
  ```
- Tunable real-time WebSocket settings:
  ```python
  AMAPP_WS_MAX_QUEUE_SIZE = 128
  AMAPP_WS_MAX_MESSAGE_BYTES = 65536
  AMAPP_WS_MAX_REPLAY_RECORDS = 500
  AMAPP_WS_HEARTBEAT_INTERVAL_S = 30.0
  ```
- `SimulationOriginValidator`: Custom ASGI middleware inheriting from Channels `OriginValidator`. Inspects `Origin` headers: allows requests without `Origin` (CLI/tests) and validates browser `Origin` against `ALLOWED_HOSTS`.

### 4.2 Protocol Contracts (`backend/apps/core/realtime/protocol.py`)
- Standardized envelope format: `WEBSOCKET_SCHEMA_VERSION = "1.0.0"`.
- `SimulationEventType` enum encompassing 21 domain and transport events.
- `ClientMessageType` enum: `SUBSCRIBE`, `UNSUBSCRIBE`, `HEARTBEAT`, `PING`, `STEP`, `CANCEL`.
- `CRITICAL_WS_EVENT_TYPES` set: `RUN_COMPLETED`, `RUN_CANCELLED`, `RUN_FAILED`, `COLLISION_DETECTED`, `SAFETY_EVENT`, `ERROR`.
- `telemetry_record_to_websocket_event()`: Immutable transformation from `TelemetryRecord` to RFC 8259-compliant JSON envelope with educational disclaimer.

### 4.3 Simulation Event Broadcaster (`backend/apps/core/realtime/broadcaster.py`)
- Singleton `SimulationEventBroadcaster` managing active runner telemetry subscriptions.
- Attached via `default_run_registry.register()` and detached via `delete()` / `clear()`.
- Thread-safe and resilient: handles sync-to-async dispatch and loop task creation; swallows channel-layer network/connection errors without raising into the simulation runner.

### 4.4 Asynchronous WebSocket Consumer (`backend/apps/core/realtime/consumer.py`)
- `SimulationRunConsumer(AsyncJsonWebsocketConsumer)`:
  - Validates `run_id` pattern and existence on connect.
  - Negotiates authentication and initial `run.status` snapshot delivery.
  - Manages subscription group `run_{run_id}`.
  - Runs bounded background worker tasks: `_outbound_sender` and `_heartbeat_loop`.
  - Enforces backpressure, dropped event accounting, and `telemetry.gap` reporting.
  - Handles bounded replay requests with cursor validation (`last_sequence` or `replay_from_tick`).
  - Cleans up all channel group memberships and cancels worker tasks on disconnect.

### 4.5 WebSocket Routing (`backend/apps/core/realtime/routing.py`)
- Route pattern: `^ws/v1/runs/(?P<run_id>[a-zA-Z0-9_\-]+)/?$`.
- Preserves separation between HTTP REST namespace (`/api/v1/`) and WebSocket streaming namespace (`/ws/v1/`).

---

## 5. Verification & Test Suite Summary

### 5.1 Test Suites Implemented
1. `backend/apps/core/tests/test_ws_routing_and_handshake.py` (5 tests):
   - Valid WebSocket route connects and receives initial `run.status`.
   - Unknown run ID rejected with close code `4404` and error envelope.
   - Invalid regex pattern rejected with close code `4400`.
   - HTTP health and API routes continue working unimpeded.
   - Consumer resources cleaned up after disconnect.
2. `backend/apps/core/tests/test_ws_protocol_and_errors.py` (10 tests):
   - Valid subscription delivers point-in-time `run.status`.
   - Unsubscribe stops event delivery.
   - Malformed JSON returns `INVALID_JSON` error envelope.
   - Unsupported message type returns `UNSUPPORTED_MESSAGE_TYPE`.
   - Non-dict payload returns `INVALID_PAYLOAD_FORMAT`.
   - Binary frame returns `BINARY_NOT_SUPPORTED`.
   - Oversized message (>64KB) returns `MESSAGE_SIZE_EXCEEDED`.
   - Client cannot override bound `run_id`.
   - Schema version `1.0.0` validated.
   - Error envelopes never leak Python tracebacks.
3. `backend/apps/core/tests/test_ws_live_events.py` (9 tests):
   - Stepping run broadcasts `vehicle.updated` and `metrics.snapshot`.
   - World snapshot event delivered.
   - Pedestrian state changes delivered.
   - Traffic signal state changes delivered.
   - Emergency corridor activations delivered.
   - Safety warnings and collision detections delivered.
   - Run isolation: subscribers to run A never receive run B events.
   - Broadcasting does not mutate world state or agent positions.
   - Client disconnect does not interrupt or corrupt simulation stepping.
4. `backend/apps/core/tests/test_ws_replay_and_backpressure.py` (8 tests):
   - Bounded replay by `last_sequence` in ascending order.
   - Evicted telemetry history emits `telemetry.gap` notification with `expired_history`.
   - Replay max limit enforced.
   - Bounded replay by `replay_from_tick`.
   - Outbound queue saturation drops non-critical events and emits `telemetry.gap` with `buffer_overflow`.
   - Critical events evict non-critical events and are never lost.
   - Duplicate subscriptions do not duplicate deliveries.
   - Client ping/heartbeat receives `server.heartbeat` pong.
5. `backend/apps/core/tests/test_ws_auth_and_lifecycle.py` (10 tests):
   - Anonymous development mode allowed when `AMAPP_API_REQUIRE_AUTHENTICATION=False`.
   - Strict authentication rejects unauthenticated connections with code `4401`.
   - Authenticated user connects under strict mode.
   - Non-staff user denied simulation control actions (`PERMISSION_DENIED`).
   - Staff user permitted simulation control step and cancel.
   - Untrusted Origin header rejected by `SimulationOriginValidator`.
   - Terminal completion transition emits `run.completed` exactly once.
   - Cancellation transition emits `run.cancelled`.
   - Failure state transition emits `run.failed`.
   - Channel layer failures caught and logged without affecting simulation.

### 5.2 Test Execution Results
- **Command:** `pytest --cov=apps.core --cov-fail-under=80`
- **Result:** **1,095 passed in 38.66s**
- **Failures:** 0
- **Coverage:** **95.66%** across 20,932 statements (exceeds 80% threshold).

---

## 6. Process-Local & Deployment Limitations

- **In-Memory Channel Layer**: The test suite and default configuration utilize `channels.layers.InMemoryChannelLayer`. This is single-process local and thread-safe, suitable for single-node development and deterministic testing.
- **Horizontal Scaling**: Cross-worker channel event broadcasting in multi-process production deployments requires an external Redis instance via `channels_redis`. This is explicitly documented in `docs/API.md` and `ARCHITECTURE.md`.
- **In-Memory Registries**: `ScenarioRegistry` and `RunRegistry` are process-local in-memory registries. Worker processes do not share runner memory without a shared execution service.

---

## 7. Files Created and Modified

### Created:
- `backend/apps/core/realtime/__init__.py`
- `backend/apps/core/realtime/protocol.py`
- `backend/apps/core/realtime/broadcaster.py`
- `backend/apps/core/realtime/consumer.py`
- `backend/apps/core/realtime/routing.py`
- `backend/apps/core/tests/test_ws_routing_and_handshake.py`
- `backend/apps/core/tests/test_ws_protocol_and_errors.py`
- `backend/apps/core/tests/test_ws_live_events.py`
- `backend/apps/core/tests/test_ws_replay_and_backpressure.py`
- `backend/apps/core/tests/test_ws_auth_and_lifecycle.py`
- `docs/progress/PHASE_22.md`

### Modified:
- `requirements.txt` (added `channels`, `daphne`)
- `requirements-dev.txt` (added `pytest-asyncio`)
- `backend/config/settings.py` (added daphne, channels, channel layer, WS settings)
- `backend/config/asgi.py` (configured Channels ProtocolTypeRouter, auth stack, origin validator)
- `backend/apps/core/telemetry/collector.py` (added listener registration and dispatch)
- `backend/apps/core/api/services.py` (attached broadcaster on run registration, detached on delete/clear)
- `.github/workflows/ci.yml` (added PHASE_22.md to integrity check, added channels to env verification, updated test title)
- `PROJECT_STATUS.md` (updated Phase 22 status to COMPLETED, next Phase 23)
- `ARCHITECTURE.md` (added Section 18 for ASGI, WebSockets, and real-time streaming)
- `REQUIREMENTS_TRACEABILITY.md` (mapped requirements to Phase 22 implementation)
- `README.md` (added WebSocket endpoint overview, connection example, disclaimer)
- `docs/API.md` (added WebSocket protocol specification, schemas, close codes, replay, backpressure)
- `docs/TESTING.md` (documented WebSocket test suites, ASGI testing, and CI verification)

---

## 8. GitHub Actions Verification

- **Implementation Commit SHA:** `67ff723`
- **GitHub Actions Run URL:** [Run 39590816271](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39590816271)
- **Workflow:** `CI Pipeline` (`.github/workflows/ci.yml`)
- **Total Duration:** 56 seconds
- **Job Statuses:**
  - `repo-hygiene` (`Repository Hygiene & Documentation Integrity`): **PASSED** (4s, verified all required documents and progress reports exist)
  - `backend-quality` (`Backend Lint, Test & Coverage`): **PASSED** (56s, 1,095 passed in 26.25s, 95.64% line coverage, 0 lint warnings)
  - `frontend-quality` (`Frontend Lint, Typecheck & Build`): **PASSED** (7s, Node 22.x verified, deferred cleanly until package.json declared)
- **Acceptance Gate Result:** **100% GREEN (All 3 jobs successful, 1,095 passed, 95.64% coverage >= 80% threshold)**


---

## 9. Phase 23 Handoff Instructions

Phase 22 successfully establishes real-time live simulation and telemetry streaming over WebSockets. Phase 23 can now implement the frontend dashboard or client visualization layer:
- Connect to `ws://host/ws/v1/runs/{run_id}/` to stream live simulation states.
- Subscribe with `{"type": "subscribe"}` to begin streaming.
- Handle `telemetry.gap` notifications gracefully to account for connection reconnects or backpressure drops.
- Utilize REST API (`/api/v1/runs/`) for run creation and authoritative lifecycle commands.
