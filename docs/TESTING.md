# TESTING STANDARDS & STRATEGY

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Testing Frameworks:** `pytest`, `pytest-cov`, `pytest-django`, `pytest-asyncio`  
**Current Status:** Active Test Strategy Enforced (Phase 29 — 1,112 Backend Tests Passing at 95.61% Coverage; 183 Frontend Tests Passing across 10 test files)

---

## 1. Testing Philosophy & Layering

The simulation platform enforces verifiable correctness across all 40 development phases. Every functional capability must be accompanied by automated tests before progression.

### Testing Levels
1. **Unit Tests (`tests/unit/`):**
   - Test isolated mathematical, geometric, and logical routines.
   - Examples: Kinematic equations, A* heuristic calculation, V2V packet serialization, collision box intersection.
   - Run in milliseconds without external dependencies or disk I/O.
2. **Integration Tests (`tests/integration/`):**
   - Test interactions across multiple subsystems.
   - Examples: Agent receiving a V2V hazard alert and invoking local rerouting; traffic signal phase change triggering vehicle deceleration; emergency vehicle corridor clearance.
3. **Scenario & Regression Tests (`tests/scenarios/`):**
   - End-to-end deterministic simulation runs with fixed seeds.
   - Standard benchmark scenarios:
     - 4-way unsignalized intersection with 8 agents.
     - Highway lane blockage incident with 15 agents.
     - Emergency ambulance priority transit with 20 yielding agents.
     - Signalized urban grid with pedestrian crosswalks.
4. **Benchmarking & Compliance (`tests/benchmarks/`):**
   - Automated evaluation tracking travel time, throughput, collision rates, and V2V packet delivery ratios.
   - Gymnasium environment compliance verification (`gymnasium.utils.env_checker.check_env`).

---

## 2. Directory Layout Blueprint

```text
tests/
├── conftest.py                # Global fixtures, deterministic seeds, test graphs
├── unit/
│   ├── test_domain_models.py  # Phase 3: Typed domain validation
│   ├── test_road_graph.py     # Phase 4: NetworkX topology
│   ├── test_osm_import.py     # Phase 5: OSMnx normalization & fallback
│   ├── test_planning.py       # Phase 6: A* and Dijkstra path calculations
│   ├── test_agents.py         # Phase 7: Kinematics and lifecycle
│   ├── test_clock.py          # Phase 8: Stepping, pause, resume, reset
│   ├── test_traffic_rules.py  # Phase 9: Speed limits, queues, intersections
│   ├── test_v2v_protocol.py   # Phase 11: Packet format, serialization, dedup
│   ├── test_v2v_range.py      # Phase 12: Proximity radius detection
│   ├── test_channel_noise.py  # Phase 14: Packet loss and latency
│   ├── test_rerouting.py      # Phase 15: Adaptive cost updates & rerouting
│   ├── test_collision.py      # Phase 16: Geometry, TTC, and safe braking
│   ├── test_pedestrians.py    # Phase 17: Crosswalk yielding and signal phases
│   ├── test_emergency.py      # Phase 18: Ambulance priority corridors
│   ├── test_ai_policy.py      # Phase 19: Weighted scoring decision policy
│   └── test_gym_env.py        # Phase 32: Gymnasium observation/action compliance
├── integration/
│   ├── test_agent_v2v.py      # Phase 13: Decentralized P2P coordination
│   ├── test_backend_checkpoint.py # Phase 20: Comprehensive backend checkpoint
│   ├── test_api_endpoints.py  # Phase 21: Django REST Framework API
│   └── test_websocket_stream.py # Phase 22: Django Channels telemetry stream
└── scenarios/
    ├── test_crossroad_scenario.py
    ├── test_highway_incident_scenario.py
    └── test_emergency_corridor_scenario.py
```

---

## 3. Determinism & Random Seeds

All tests must be strictly deterministic. Never call unseeded pseudorandom functions (`random.random()`, `numpy.random.rand()`).
In `conftest.py`:
```python
import pytest
import numpy as np
import random

@pytest.fixture(autouse=True)
def set_deterministic_seed():
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
```

---

## 4. Active Test Suites & Commands (Phase 22)

### 4.1 Running Active Tests
```bash
# Run entire backend test suite via pytest (1,095 passed)
pytest

# Run with full coverage report and 80% failure threshold
pytest --cov=backend/apps/core --cov-report=term-missing --cov-fail-under=80

# Run with verbose output
pytest -v

# Run WebSocket test suites (Phase 22)
pytest backend/apps/core/tests/test_ws_routing_and_handshake.py
pytest backend/apps/core/tests/test_ws_protocol_and_errors.py
pytest backend/apps/core/tests/test_ws_live_events.py
pytest backend/apps/core/tests/test_ws_replay_and_backpressure.py
pytest backend/apps/core/tests/test_ws_auth_and_lifecycle.py

# Run REST API test suites (Phase 21)
pytest backend/apps/core/tests/test_api_scenarios.py
pytest backend/apps/core/tests/test_api_runs.py
pytest backend/apps/core/tests/test_api_telemetry_and_export.py
pytest backend/apps/core/tests/test_api_security_and_errors.py

# Run Ruff linting
ruff check backend

# Run Django system checks
python backend/manage.py check
```

### 4.2 Verified Test Coverage (Phase 22 — 1,095 Tests Passing, 95.66% Coverage)
- **WebSocket Routing & Handshake (`test_ws_routing_and_handshake.py`, 5 passed):**
  - URL routing matching valid alphanumeric, dash, and underscore run IDs (`ws://host/ws/v1/runs/{run_id}/`).
  - Invalid route rejection and 404 on unroutable paths.
  - Handshake execution with immediate `connection.ack` event broadcast.
  - Run resolution against `RunRegistry`: 4404 close code on missing run ID.
  - Educational disclaimer validation in connection ACK payload.
- **WebSocket Protocol & Error Handling (`test_ws_protocol_and_errors.py`, 10 passed):**
  - Standard JSON event envelope format (`event_type`, `run_id`, `sequence`, `tick`, `timestamp_s`, `schema_version`, `disclaimer`, `payload`).
  - Monotonically increasing sequence numbers per event stream.
  - Text frame decoding and malformed JSON text handling (4400 close code).
  - Client ping/heartbeat command handling with server heartbeat response.
  - Client unsubscribe and unknown command error reporting without unhandled exceptions.
  - Maximum message size enforcement (`AMAPP_WS_MAX_MESSAGE_BYTES = 65536`).
- **WebSocket Live Event Streaming (`test_ws_live_events.py`, 9 passed):**
  - Real-time event dispatch for all 21 `SimulationEventType` variants.
  - Telemetry collector listener bridge (`TelemetryRecord` -> WebSocket event envelope).
  - Lifecycle state transition streaming (`run.state_change`, `run.completed`, `run.cancelled`).
  - Periodic kinematic snapshot streaming (`simulation.snapshot`).
  - Discrete step notifications (`run.step`) and metrics summary streaming (`metrics.summary`).
  - Subsystem events: safety near-misses, routing reroutes, V2V transmissions, pedestrian crosswalk crossings, emergency corridors, and autonomous decision evaluations.
- **WebSocket Bounded Replay & Backpressure Handling (`test_ws_replay_and_backpressure.py`, 8 passed):**
  - Bounded history replay from in-memory telemetry buffer using `subscribe` with `from_sequence`.
  - Tick-based historical replay using `from_tick`.
  - Maximum replay limit enforcement (`AMAPP_WS_MAX_REPLAY_RECORDS = 500`).
  - Historical eviction gap notification (`telemetry.gap` with `reason="expired_history"`).
  - Bounded per-consumer outbound queue (`AMAPP_WS_MAX_QUEUE_SIZE = 128`).
  - Backpressure drop policy: non-critical events dropped on buffer saturation with `telemetry.gap` (`reason="buffer_overflow"`).
  - Zero-drop preservation of critical lifecycle events (`run.state_change`, `run.completed`, etc.).
- **WebSocket Authentication, Origin & Consumer Lifecycle (`test_ws_auth_and_lifecycle.py`, 10 passed):**
  - Origin validation via `SimulationOriginValidator` against `ALLOWED_HOSTS` and `AMAPP_WS_ALLOWED_ORIGINS`.
  - Disallowed origin rejection with 4401 Unauthorized close code.
  - Authentication state propagation through `AuthMiddlewareStack`.
  - Client-driven simulation step commands (`type="step"`) advancing the authoritative runner.
  - Client-driven cooperative cancellation (`type="cancel"`).
  - Multiple concurrent WebSocket consumers subscribed to the same simulation run.
  - Clean consumer disconnect and channel layer group deregistration.
  - Broadcaster resilience to absent or failed channel layer instances without runner crash.

- **API Scenario Management & Validation (`test_api_scenarios.py`, 10 passed):**
  - Scenario collection listing and preloaded example templates (`scn_single_veh`, `scn_multi_veh`, `scn_emergency_corridor`, `scn_signalized_intersection`).
  - Single scenario retrieval by ID with full structural definition serialization.
  - Custom scenario creation with atomic validation and duplicate ID rejection (409 Conflict).
  - Malformed scenario rejection with field-level RFC 7807 error details (400 Bad Request).
  - Dedicated validation endpoint (`POST /api/v1/scenarios/validate/`) for pre-flight checking without persistence.
  - Rich scenario definitions with signals, crosswalks, pedestrians, emergency vehicles, and subsystem configs.
- **API Simulation Run Lifecycle (`test_api_runs.py`, 15 passed):**
  - Run listing and run status retrieval (`GET /api/v1/runs/`, `GET /api/v1/runs/{run_id}/`).
  - Run creation from preloaded scenario ID or inline definition with custom ticks and random seed (`POST /api/v1/runs/`).
  - Duplicate run ID rejection (409 Conflict) and non-existent scenario rejection (404 Not Found).
  - Point-in-time snapshot and execution status inspection.
  - Discrete stepping: single-tick stepping, multi-tick stepping (`ticks=5`), and run-to-completion (`ticks=None`).
  - Terminal run stepping rejection (409 Conflict with `INVALID_RUN_LIFECYCLE_STATE`).
  - Cooperative cancellation: transitioning run to `CANCELLED` lifecycle state (`POST /api/v1/runs/{run_id}/cancel/`).
  - Already-terminal run cancellation rejection (409 Conflict).
- **API Telemetry, Metrics & RFC 8259 Export (`test_api_telemetry_and_export.py`, 11 passed):**
  - Full telemetry query and filtering by tick range (`min_tick`, `max_tick`) and limit.
  - Intermediate metrics aggregation computed on-the-fly (`GET /api/v1/runs/{run_id}/metrics/`).
  - Completed execution result retrieval (`GET /api/v1/runs/{run_id}/result/`).
  - Structured RFC 8259 JSON simulation export (`GET /api/v1/runs/{run_id}/export/`).
  - Export size limit enforcement (413 Payload Too Large with `EXPORT_SIZE_LIMIT_EXCEEDED`).
- **API Security, Error Envelope & Permissions (`test_api_security_and_errors.py`, 10 passed):**
  - Consistent RFC 7807 JSON error responses across 404, 405, 400 (malformed JSON), and sanitized 500 without stack trace leaks.
  - Open development access by default (`SimulationApiPermission`).
  - Strict authentication toggle (`AMAPP_API_REQUIRE_AUTHENTICATION`) returning 401 Unauthorized for unauthenticated clients and 403 Forbidden for non-staff mutations.
  - Safe read-only and admin mutations with `ReadOnlyOrAdminApiPermission`.
  - Thread-safe programmatic registry lifecycle and cleanup.

  - Edge cost calculation: scalar distance in meters, scalar travel time in seconds, validation of non-positive/non-finite length and speed limits.
  - Route metrics aggregation: summation of lengths and durations.
  - Traversability: filtering against closed edge IDs.
  - Heuristic admissibility: Euclidean distance lower-bound validation on graph edges, travel-time speed bounds, automatic safe $h=0$ fallback on inadmissible geometries, forced zero heuristic.
  - Routing models: `RoutingRequest` and `RoutingResult` validation invariants, string coercion, serialization.
- **Dijkstra Shortest Path Search (`test_routing_dijkstra.py`, 11 passed):**
  - Optimal paths: shortest distance vs fastest travel time trade-off (choosing shorter slow street vs longer high-speed highway).
  - One-way restrictions: traversal strictly obeys edge directionality.
  - Start == destination: zero-cost result, 0 expanded nodes, `route=None` preserving `Route` invariants.
  - Missing nodes: raising `RoutingNodeNotFoundError`.
  - Disconnected nodes: raising `NoPathFoundError`.
  - Closures: rerouting around closed edges; total blockage error reporting with closure count; direction-specific closures.
  - Determinism: repeatable sequence and metrics across multiple executions.
- **Custom A\* Pathfinding (`test_routing_astar.py`, 9 passed):**
  - Distance and travel-time optimal routing.
  - Optimality verification: exact cost equivalence between A* and Dijkstra across multi-node queries on synthetic city grids.
  - Directionality and one-way constraints.
  - Reopening and stale queue entries: robust priority queue pruning.
  - Inadmissible graph safe fallback: graceful $h=0$ execution.
  - Deterministic tie-breaking on symmetric grid paths.
- **Route Planner & Cross-Algorithm Comparison (`test_routing_planner.py`, 8 passed):**
  - High-level `RoutePlanner` facade and `find_route` convenience dispatcher.
  - Graph immutability: verifying input `RoadGraph` node and edge structures are completely unchanged by path searches.
  - Route continuity: verifying every consecutive node pair $(u, v)$ has a matching directed edge in `edge_ids`.
  - NetworkX reference comparison: matching ground-truth shortest path costs computed by `nx.shortest_path_length` for both distance and travel time.
- **Scenario Validation (`test_scenarios_validation.py`, 22 passed):**
  - Structural metadata constraints (non-empty ID and name).
  - Simulation parameter bounds ($0.0 < \Delta t \le 10.0\,\text{s}$, strictly positive tick limits and duration).
  - Effective max ticks derivation combining `max_ticks` and `max_duration_s`.
  - Road network source specification consistency (supplied graph presence, OSM config presence).
  - Vehicle definition invariants (unique IDs, non-empty start/destination, algorithm/cost mode validation, non-negative speed, kinematics config typecheck).
  - Traffic signal constraints (unique signal IDs, single signal per intersection node).
  - Graph compatibility validation (start/destination nodes exist in road graph, signal nodes and incoming approach edges exist).
  - Serialization to plain JSON dictionaries.
- **Scenario Builder (`test_scenarios_builder.py`, 9 passed):**
  - Synthetic grid scenario construction with multiple vehicles and varied path algorithms.
  - Supplied `RoadGraph` reuse without regeneration.
  - Explicit traffic signal registration without duplicate collisions.
  - Unreachable destination handling: strict rejection (`UnreachableDestinationError`) vs explicit exclusion.
  - Mocked offline OSM acquisition and graph normalization.
  - Atomic assembly failure handling without exposing partially initialized states.
  - Initial baseline snapshot capture for reset.
- **Scenario Runner (`test_scenarios_runner.py`, 10 passed):**
  - Single-step advancement via authoritative `SimulationEngine`.
  - Fixed-tick execution runs (`runner.run(ticks=N)`).
  - Termination condition evaluation: `ALL_ARRIVED`, `MAX_TICKS_REACHED`, `TARGET_TICKS_COMPLETED`, `PAUSED`, `STOPPED`, `FAILED`.
  - Paused engine semantics and single-stepping while paused.
  - Unrecoverable engine failure isolation with structured error reporting.
  - Engine reset restoring initial baseline states.
  - Complete execution of programmatic example scenario fixtures.
- **Scenario Determinism & Replay (`test_scenarios_determinism.py`, 3 passed):**
  - Bit-identical outcomes across separately constructed scenarios with identical configurations and seeds.
  - Bit-identical replay after `runner.reset()` (matching snapshots and results).
  - Tick-by-tick intermediate step result determinism (distances, speeds, headings, positions).
- **Coordination Models & Reports (`test_coordination_models.py`, 21 passed)**
- **Vehicle Knowledge Stores (`test_coordination_knowledge.py`, 11 passed)**
- **Communication Latency & Multi-Tick Queues (`test_communication_latency.py`, 9 passed)**
- **Packet Loss, Burst Loss, Outages & Partitions (`test_communication_impairment.py`, 17 passed)**
- **Degradation, Neighbor & Engine Integration (`test_communication_degradation_integration.py`, 7 passed)**
- **Coordination Models & Reports (`test_coordination_models.py`, 21 passed)**
- **Vehicle Knowledge Stores (`test_coordination_knowledge.py`, 11 passed)**
- **Safety Geometry & SAT Overlap (`test_safety_geometry.py`, 18 passed)**
  - 2D Oriented Bounding Box (OBB) construction and dimension/coordinate validation.
  - Separating Axis Theorem (SAT) 4-axis interval projection overlap tests.
  - Parallel, perpendicular (T-bone), angled diagonal, and boundary-touching geometries.
  - Exact polygon separation distance computations.
- **Safety Detection, Closing Speed, TTC & Risk (`test_safety_detection_and_ttc.py`, 13 passed)**
  - Vector closing-speed formulation along relative position direction.
  - Safe separation distance computation with reaction time and braking distance terms.
- **ScenarioRunner Lifecycle & Cancellation (`test_runner_lifecycle_and_cancellation.py`, 13 passed)**
  - 8-state lifecycle state machine progression (`CREATED` -> `VALIDATING` -> `READY` -> `RUNNING` -> terminal states).
  - Strict transition validation and rejection of attempts to resume terminal runs (`RunStateTransitionError`).
  - Tick-limit and simulation-duration limits, partial stepping (`TARGET_TICKS_COMPLETED`).
  - Cooperative cancellation between ticks, cancellation idempotency, and reason tracking.
  - Failure containment, error details preservation, and runner instance state isolation.
- **Telemetry Collector, Retention & Drops (`test_telemetry_collector_and_retention.py`, 11 passed)**
  - Record validation, schema version enforcement (`1.0.0`), non-finite float sanitization.
  - Bounded capacity, non-critical record dropping, drop stats accounting by category.
  - Strict retention overflow error, critical event zero-drop preservation via oldest non-critical eviction.
  - Buffer saturation overflow, category filtering, stream closure, multi-attribute querying.
- **Runner Determinism, Fingerprinting & Export (`test_runner_determinism_and_export.py`, 11 passed)**
  - Bit-identical execution reproducibility, scenario definition SHA-256 fingerprint determinism.
  - Operational wall-clock timestamp stripping from hashes, initial and final world state fingerprints.
  - Active Git commit SHA discovery, completed/cancelled/failed run RFC 8259 JSON export.
  - Non-finite numeric serialization, export byte size limit enforcement (`ExportSizeLimitExceededError`).
  - Export read-only state invariance (no mutation of engine, world snapshot, or tick history).
- **Cross-Subsystem Metrics Aggregation (`test_runner_metrics_aggregation.py`, 7 passed)**
  - Unified metrics aggregation across simulation, kinematics, routing, V2V, coordination, safety, pedestrians, emergency, and AI decisions.
  - Averaging, observed extrema, and division by zero protection (e.g. zero sent packets).
  - Failed tick exclusion (ticks rolled back are never counted in metrics).
- **End-to-End Backend Integration Scenarios (`test_backend_integration_scenarios.py`, 9 passed)**
  - End-to-end integration covering single-vehicle, multi-vehicle, traffic signals, adaptive routing, communication impairment, coordination, safety supervisor, pedestrian crosswalks, emergency corridors, and AI decision policies.
- **Decision Models & Config (`test_decision_models_and_config.py`, 11 passed)**
  - Dataclass validation, numeric bounds, immutable semantics for candidates and scores.
  - Serialization to dictionaries (`to_dict()`) and deserialization compatibility (`from_dict()`).
  - Handling of $-\infty$ raw score for hard-constraint violations without overflow.
- **Decision Features & Candidate Scoring (`test_decision_features_and_scoring.py`, 6 passed)**
  - Feature normalization (travel time, congestion delay, hazard penalties).
  - Multi-objective weighted score computation.
  - Hard constraint violations resulting in $S(c) = -\infty$.
  - 4-tier deterministic ranking and tie-breaking `(-raw_score, -confidence, travel_time_s, candidate_id)`.
  - Candidate input permutation invariance.
- **Decision Policy Outcomes & Hysteresis (`test_decision_policy_outcomes.py`, 8 passed)**
  - `ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE` outcomes with `DecisionReasonCode`.
  - Rejection of candidates violating hard constraints (closures, active corridors).
  - Route stability hysteresis preventing oscillation when improvement $< \text{min\_score\_improvement}$.
  - Low-confidence deferral when observation confidence $< \text{min\_confidence\_threshold}$.
  - Current route closure handling ensuring fallback alternative acceptance.
- **DynamicRouteAdapter & Isolation Integration (`test_decision_adapter_integration.py`, 4 passed)**
  - DynamicRouteAdapter evaluation with injected `DecisionManager`.
  - Updating agent route when candidate accepted, retaining current route when rejected.
  - Strict vehicle knowledge store isolation ensuring zero state leakage across vehicles.
  - 100% backward compatibility when decision policy is disabled in config.
- **SimulationEngine Stepping & Atomic Rollback (`test_decision_engine_and_rollback.py`, 4 passed)**
  - Single-clock stepping populating `TickResult.decision_metrics` and `decision_records`.
  - Atomic rollback restoring decision state and metrics upon simulated kinematic exception.
  - Deterministic replay producing bit-identical decision telemetry.
  - WorldState reset restoring decision manager to clean baseline state.
- **AI Decision Scenario Orchestration (`test_decision_scenarios.py`, 10 passed)**
  - Scenario validation and builder injection for decision configurations.
  - End-to-end execution across all 6 Phase 19 deterministic scenario fixtures.
  - Backward compatibility with legacy scenarios omitting decision configurations.
- **Emergency Models & Lifecycle FSM (`test_emergency_models_and_lifecycle.py`, 13 passed)**
  - Priority levels (1-3) and emergency types (`AMBULANCE`, `FIRE_ENGINE`, `POLICE`).
  - Lifecycle state machine transitions and invalid transition rejection.
  - Deterministic tie-breaking `(priority_level, creation_time_s, vehicle_id)` and TTL expiration.
  - Manager activation idempotency, destination conflict rejection, deactivation cleanup, and baseline reset.
- **Emergency V2V Announcements & Awareness (`test_emergency_v2v_announcements.py`, 14 passed)**
  - Packet builders and JSON codecs for emergency messages.
  - Local awareness store updates without omniscient leakage.
  - Stale and expired message rejection.
  - Delivery across simulated network subject to range and packet loss.
- **Emergency Corridors & Reservations (`test_emergency_corridors_and_reservations.py`, 8 passed)**
  - Dynamic corridor path extraction from existing `RoadGraph` without graph mutation.
  - Temporary edge and node reservations with time-to-live (`ttl_s`).
  - Preemption conflict resolution under `STRICT_PRIORITY` and `FIRST_COME_FIRST_SERVED` policies.
  - Complete reservation cleanup on priority deactivation.
- **Yielding Policies & Traffic Signals (`test_emergency_yielding_and_signals.py`, 8 passed)**
  - Cooperative yielding deceleration respecting physical vehicle limits.
  - Yielding vehicles stopping at red traffic signals without entering intersections.
  - Yielding vehicles stopping before occupied crosswalks with crossing pedestrians.
  - Traffic-signal priority overrides holding GREEN along emergency corridors.
  - Priority override denial protecting pedestrians actively crossing in crosswalks.
  - Phase 16 safety subsystem collision avoidance overrides retaining supreme authority.
- **Emergency Engine Integration & Atomic Rollback (`test_emergency_engine_integration.py`, 6 passed)**
  - Single-clock stepping integrating V2V inbox ingestion, corridor auto-commitment, and yielding.
  - Atomic rollback restoring emergency requests, corridors, reservations, and overrides on step failure.
  - Injected maintenance and vehicle motion failures verified.
  - Deterministic replay producing bit-identical snapshots.
  - Scenario reset restoring baseline emergency state.
- **Emergency Scenario Orchestration (`test_emergency_scenarios.py`, 11 passed)**
  - Scenario validation for emergency vehicle definitions, priority bounds, and road graph node presence.
  - End-to-end execution across all 6 Phase 18 example scenario fixtures.
  - Backward compatibility with scenarios omitting emergency configurations.
- **Pedestrian Models & Kinematics (`test_pedestrian_models_and_kinematics.py`, 12 passed)**
  - Pedestrian lifecycle states (`IDLE`, `APPROACHING_CROSSWALK`, `WAITING_TO_CROSS`, `CROSSING`, `WALKING`, `ARRIVED`, `BLOCKED`).
  - Strict transition validation (`validate_pedestrian_transition`) and error handling (`InvalidPedestrianStateError`).
  - Bounded velocity kinematics, target snapping at destination, and zero-overshoot guarantees.
  - Serialization (`to_dict()`) and deserialization compatibility.
- **Pedestrian Crosswalk Geometry & Projection (`test_pedestrian_crosswalk.py`, 10 passed)**
  - 2D crosswalk corridor modeling between entry and exit curb points.
  - Longitudinal and lateral unit vector projections.
  - `is_point_inside` corridor boundary determination.
  - Waiting area proximity evaluation (`is_at_waiting_area`).
  - Signal state translation (`RED` -> `WALK`, `YELLOW` -> `CLEARANCE`, `GREEN` -> `DONT_WALK`; unsignalized -> `WALK`).
- **Signal Interaction & Clearance Policy (`test_pedestrian_signal_interaction.py`, 6 passed)**
  - Pedestrians in `WAITING_TO_CROSS` yield at entry curb while traffic signal is `GREEN` (`DONT_WALK`).
  - Pedestrians enter crosswalk and transition to `CROSSING` once signal switches to `RED` (`WALK`).
  - Robust clearance policy: Pedestrians in `CROSSING` state continue walking across the corridor to exit curb upon signal change to `DONT_WALK` (no mid-street stranding or teleportation).
  - Vehicles continue respecting red signals in the presence of pedestrians.
  - Order-independent pedestrian registration and deterministic replay.
- **Vehicle-Pedestrian Safety & Collisions (`test_pedestrian_safety_and_collisions.py`, 7 passed)**
  - Bounding box creation for pedestrians (`OrientedBoundingBox2D.from_pedestrian`).
  - Vehicle-pedestrian conflict detection, separation distance, and TTC estimation via SAT OBB.
  - 5-tier safety risk classification (`COLLISION`, `IMMINENT`, `HIGH_RISK`, `CAUTION`, `SAFE`).
  - Controlled strong braking and emergency stopping overrides applied to vehicles for crossing pedestrians.
  - `SafetyManager` logs immutable `SafetyEvent` records referencing `pedestrian_id`.
  - Truthful recording of unavoidable collisions.
- **Simulation Engine Integration & Atomic Rollback (`test_pedestrian_engine_integration.py`, 6 passed)**
  - Single-clock progression: pedestrian stepping and metric updates in authoritative `SimulationEngine.step()`.
  - Pre-tick snapshot capture and atomic rollback: failure restores all pedestrian agents to exact previous state.
  - `WorldState.reset()` cleanly restores pedestrians, crosswalks, vehicles, and signals to scenario baseline.
  - Full tick result and world snapshot generation including pedestrian state dictionaries.
- **Pedestrian Scenario Orchestration (`test_pedestrian_scenarios.py`, 4 passed)**
  - Scenario validation and building for crosswalks and pedestrian definitions.
  - Execution of Phase 17 scenario templates: waiting at red signal, crossing permitted, vehicle braking for pedestrian, unavoidable collision.
- **Safety Geometry & SAT Overlap (`test_safety_geometry.py`, 18 passed)**
- **Safety Detection, TTC & Pairwise Classification (`test_safety_detection_and_ttc.py`, 13 passed)**
- **Safety Policy & Simultaneous Conflict Resolution (`test_safety_policy.py`, 9 passed)**
- **Safety Engine Integration, Deterministic Scenarios & Rollback (`test_safety_engine_integration.py`, 8 passed)**
- **Adaptive Dynamic Costs & Edge Evaluation (`test_routing_dynamic_costs.py`, 17 passed)**
- **Adaptive Rerouting Policy & Cooldowns (`test_routing_adaptive_policy.py`, 13 passed)**
- **Safe Active Route Replacement (`test_routing_replacement.py`, 7 passed)**
- **SimulationEngine Routing Integration & Scenarios (`test_routing_engine_integration.py`, 14 passed)**
- **Communication Degradation & Recovery Integration (`test_communication_degradation_integration.py`, 7 passed)**
- **Deterministic Latency & Transit Queues (`test_communication_latency.py`, 9 passed)**
- **Packet Loss, Burst Channels & Network Outages (`test_communication_impairment.py`, 17 passed)**
- **Coordination Models & Reports (`test_coordination_models.py`, 21 passed)**
- **Vehicle Knowledge Stores (`test_coordination_knowledge.py`, 11 passed)**
- **Deterministic Fusion & Conflicts (`test_coordination_fusion.py`, 8 passed)**
- **Dissemination & Multi-Hop Forwarding (`test_coordination_dissemination.py`, 5 passed)**
- **Simulation Engine Integration & Rollback (`test_coordination_engine_integration.py`, 7 passed)**
- **Neighbor Tables & Coordinator (`test_communication_neighbors.py`, 24 passed)**
- **Heartbeat Timing & Loss Detection (`test_communication_heartbeat.py`, 8 passed)**
- **Neighbor Subsystem Engine Integration (`test_communication_neighbors_integration.py`, 6 passed)**
- **V2V Message Protocol & Codecs (`test_communication_protocol.py`, 35 passed)**
- **Spatial Peer Discovery (`test_communication_discovery.py`, 24 passed)**
- **Simulated Communication Network (`test_communication_network.py`, 16 passed)**
- **Broadcast Scheduler (`test_communication_scheduler.py`, 14 passed)**
- **Simulation Engine & Scenario Integration (`test_communication_engine_integration.py`, 7 passed)**
- **Scenario Validation & Invariants (`test_scenarios_validation.py`, 20 passed)**
- **ScenarioBuilder Assembly & Graph Resolution (`test_scenarios_builder.py`, 12 passed)**
- **ScenarioRunner Execution & Replay (`test_scenarios_runner.py`, 9 passed)**
- **Multi-Agent Scenario Determinism (`test_scenarios_determinism.py`, 3 passed)**
- **Signal Controller & Cycle Timing (`test_signals_controller.py`, 40 passed)**
- **WorldState Signal Integration (`test_signals_world_integration.py`, 17 passed)**
- **SimulationEngine Signal Orchestration (`test_signals_engine_integration.py`, 7 passed)**
- **Simulation Clock & Time Tracking (`test_simulation_clock.py`, 30 passed)**
- **World State Container & Registry (`test_simulation_world.py`, 14 passed)**
- **Simulation Engine & Atomic Rollback (`test_simulation_engine.py`, 12 passed)**
- **Multi-Agent Simulation Determinism (`test_simulation_determinism.py`, 3 passed)**
- **Kinematics Motion Integration & Models (`test_kinematics_motion.py`, 38 passed)**
- **Vehicle Agent Lifecycle & Route Following (`test_kinematics_vehicle_agent.py`, 19 passed)**
- **Kinematics Grid & OSM Integration (`test_kinematics_integration.py`, 4 passed)**
- **Routing Costs, Traversability & Heuristics (`test_routing_costs_and_heuristics.py`, 18 passed)**
- **Dijkstra Shortest Path Search (`test_routing_dijkstra.py`, 11 passed)**
- **Custom A\* Pathfinding (`test_routing_astar.py`, 9 passed)**
- **Route Planner & Cross-Algorithm Comparison (`test_routing_planner.py`, 8 passed)**
- **OSM Models, Bounds & Planar Projector (`test_osm_models_and_projector.py`, 31 passed)**
- **OSM Graph Normalization Pipeline (`test_osm_normalizer.py`, 12 passed)**
- **OSM Import Service & Fallback (`test_osm_service_and_fallback.py`, 17 passed)**
- **Road Network Graph Abstraction (`test_road_graph.py`, 25 passed)**
- **Deterministic Synthetic City Generator (`test_city_generator.py`, 16 passed)**
- **Domain Value Types (`test_domain_values.py`, 33 passed)**
- **Domain Models & Invariants (`test_domain_models.py`, 55 passed)**
- **Serialization & Codecs (`test_domain_serialization.py`, 17 passed)**
- **Core Health Endpoint (`test_health.py`, 5 passed)**
- **Incident Management & Invariants (`test_incident_management.py`, 14 passed)**
  - Authoritative incident creation, validation, activation, expiry, and removal on `WorldState`.
  - Road closures dynamically blocking edges, setting traversal cost to $\infty$, and triggering adaptive vehicle rerouting.
  - Congestion events applying delay multipliers and travel time penalties.
  - Obstacle placements localized on road segments.
  - Traffic signal phase overrides locking cycle states (`RED`, `YELLOW`, `GREEN`).
  - Edge and signal restoration upon incident removal or scenario reset.
- **Incident REST APIs & Lifecycle (`test_api_incidents.py`, 12 passed)**
  - REST endpoint verification for `GET`, `POST`, and `DELETE` on `/api/v1/runs/{run_id}/incidents/`.
  - RFC 7807 problem details for invalid types, non-existent edges, unknown signals, and terminal runs (409 Conflict).
  - WebSocket event broadcasts (`incident.created`, `incident.removed`).

---

### 4.3 Frontend Test Suites & Commands (Phases 23–29)
The frontend application includes 10 comprehensive Vitest test suites executing in headless `jsdom` (183 tests passing):

```bash
# Run all frontend tests
cd frontend
npm test

# Run strict TypeScript compiler verification
npm run typecheck

# Run ESLint linting
npm run lint

# Run production bundle build
npm run build
```

#### Frontend Test Breakdown (183 tests across 10 suites):
- **`src/test/incidents.test.ts` (13 passed):** Unit tests for incident management data models, snapshot extraction, API client methods, 3D overlay creation/disposal, and historical buffer scrubbing. Validates typed payload creation (`CreateIncidentPayload`), snapshot extraction (`createIncidentSubsystemSnapshot`), API client methods (`listIncidents`, `createIncident`, `removeIncident`), Three.js overlay rendering at elevation $y = 0.10\,\text{m}$ (road closure barriers, congestion pulsating glow, obstacle hazard beacons, signal override rings), full geometry and material disposal on removal or unmount, and `SimulationHistoryBuffer` incident snapshot deep-cloned immutability.
- **`src/test/routing.test.ts` (16 passed):** Unit tests for adaptive routing visualization, candidate alternative paths, and Three.js route overlay management. Validates pure adapter functions (`resolveRouteWorldPoints` placing paths at $y = 0.12\,\text{m}$, `computeRouteDistance` calculating cumulative edge lengths, `extractActiveRoute` reading remaining distance without fabricating defaults, `extractPlannedRoute` extracting baseline routes, `extractRerouteEvent` parsing authoritative reasons and costs, `extractCandidateRoutes` extracting candidate paths only when supplied by backend, `deduplicateRerouteEvents`, and `createRouteSubsystemSnapshot`). Tests `RouteOverlayManager` Three.js lifecycle, active cyan route line rendering, planned dashed line rendering, evaluated candidate dashed purple line rendering, inspected candidate solid magenta line rendering, rotating 3D octahedron/diamond reroute markers (emerald for accepted, amber for rejected), layer toggles, animation freeze when paused, speed multiplier scaling, complete GPU resource disposal on teardown, and `SimulationHistoryBuffer` route snapshot deep-cloned immutability.
- **`src/test/components.test.tsx` (27 passed):** Component tests for Header branding, connection badge, scenario selection, run creation, run stats rendering and stepping (+1, +10, Run to End, Cancel), TelemetryFeed stream and gap alert banner, MetricsPanel grid rendering, EntityInspector vehicle and pedestrian inspection, vehicle route telemetry rendering (active route ID, total distance, remaining distance with authoritative badge, progress bar calculation, ETA unprovided disclaimer, route node sequence, reroute card with reason and cost comparison, candidate path inspection button, and unprovided fallbacks), SimulationViewer3D viewport controls (Day/Night lighting mode toggle, Perspective/Orthographic camera projection toggle, Procedural Buildings ON/OFF toggle, Reset View interaction, scene legend, loading state overlay, and historical review banner), `PlaybackBar` controls (Play/Pause/Resume, Step +1, Step +10, speed selector buttons, Live vs. Review badges, timeline range slider scrubber, and Return to Live button), V2V viewport controls (Links toggle, Range toggle, Pulses toggle, Degradation toggle, Reset V2V settings button, and collapsible V2V Visual Legend panel rendering and dismissal), Route viewport controls (Active Route toggle, Planned Route toggle, Candidate Paths toggle, Reroute Markers toggle, Reset Routes button, and collapsible Route Visual Legend panel rendering and dismissal), and Incident viewport controls (`IncidentControlPanel` rendering, collapsible drawer toggle, incident form validation, edge and signal selection, submission callback dispatch, removal callback dispatch, and terminal run state disabling).
- **`src/test/v2v.test.ts` (20 passed):** Unit tests for V2V communication data extraction and Three.js overlay management. Validates pure adapter functions (`extractV2VRange` returning configured meters or `null` without fabricating defaults, `extractV2VLinks` canonicalizing unordered vehicle pairs $\min(A, B) \leftrightarrow \max(A, B)$, mapping active vs stale links, `extractV2VDropMetrics`, `extractV2VNetworkState`, and `createV2VSubsystemSnapshot`). Tests `V2VOverlayManager` Three.js lifecycle, dynamic `LineSegments` buffer updates, ground-level range disc and perimeter ring visibility, bounded message pulse queue capacity ($\le 20$), bounded drop indicator capacity ($\le 10$), animation pause-freezing ($\Delta t = 0$), dynamic speed multiplier scaling ($0.5\times, 1\times, 2\times, 5\times$), clean GPU resource disposal on scene unmount, and `SimulationHistoryBuffer` V2V snapshot deep-cloned immutability.
- **`src/test/playback.test.ts` (14 passed):** Unit tests for simulation playback scheduling and historical buffering. Validates `PlaybackScheduler` state transitions (`idle`, `ready`, `playing`, `paused`), step request dispatching via fake timers, dynamic speed interval scaling ($0.5\times, 1\times, 2\times, 5\times$), strict prevention of overlapping step calls, halting upon terminal states (`COMPLETED`, `CANCELLED`, `FAILED`, `LIMIT_REACHED`), manual step sequencing, and error resilience. Tests `SimulationHistoryBuffer` snapshot addition, deep-cloned immutability preventing reference mutations, deduplication of matching ticks across REST and WebSocket streams, monotonic binary-search sorted insertion, bounded FIFO eviction, and clearing on run switch.
- **`src/test/interpolation.test.ts` (25 passed):** Unit tests for pure temporal interpolation engine (`EntityInterpolationBuffer`). Validates angle positive normalization (`normalizeAnglePositive`), shortest angular difference calculation (`shortestAngularDiff`), smooth heading lerp across the $0 \leftrightarrow 2\pi$ wraparound boundary (`interpolateHeading`), linear planar position lerp (`interpolatePosition`), simulation heading to Three.js rotation around Y (`simHeadingToWorldRotationY`), rejection of out-of-order samples, duplicate timestamp handling, bounded history pruning ($\le 10$ samples), bounded forward extrapolation clamping ($\le 0.15\text{s}$), and stale state detection ($> 1.0\text{s}$).
- **`src/test/models.test.ts` (18 passed):** Tests procedural low-poly 3D models and animation helpers. Verifies vehicle classification (`classifyVehicleType`), asset cache singleton geometry/material reuse (`ModelAssetCache`), procedural mesh hierarchies (Sedan, Truck, Bus, Ambulance with medical cross emblems, Fire Engine with roof ladder, Unknown fallback), articulated pedestrian avatars (torso, head, left/right leg pivot groups), emergency beacon animation state (alternating 2.5 Hz blue/red flashing when active, dimmed when inactive), accessibility compliance under `prefers-reduced-motion` (steady static glow), dynamic pedestrian walking leg swing driven by velocity ($v > 0.05\text{ m/s}$), and full scene resource cleanup/disposal methods.
- **`src/test/geometry.test.ts` (34 passed):** Tests planar-to-Three.js coordinate transforms (`simToWorldCoordinates`), non-finite coordinate safety, dynamic road edge width resolution (`computeRoadEdgeWidth`), multi-lane road markings (`generateMultiLaneMarkings`: solid white outer borders, solid yellow centerlines, dashed white lane dividers), zebra crosswalk stripes (`generateZebraStripes`), inferred intersection crosswalks (`generateInferredCrosswalks`), curbs and sidewalks (`generateCurbsAndSidewalks`), Mulberry32 PRNG determinism (`createMulberry32`), Euclidean point-to-segment distance calculation (`pointToSegmentDistance`), deterministic procedural urban buildings with strict road and junction exclusion zones (`generateProceduralBuildings`), local Cartesian Equirectangular projection (`projectGeoCoordinatesToLocalMeters`), and OpenStreetMap graph data adaptation (`adaptOsmRoadNetwork`).
- **`src/test/api-client.test.ts` (8 passed):** Tests base URL construction, trailing slash normalization, scenario listing, scenario detail, run creation, RFC 7807 problem details handling, invalid JSON defense, and network error handling.
- **`src/test/websocket-client.test.ts` (8 passed):** Tests initial handshake, automatic subscription command dispatch, Schema 1.0.0 envelope parsing, malformed JSON/binary frame resilience, server heartbeat ping/pong reply, non-recoverable 4404 close halting, bounded exponential backoff with stable connection window, and cleanup on disconnect.

---

## 5. CI Rules & Testing Policy
- **GitHub Actions Authoritative Gate:** GitHub Actions CI is the primary test and acceptance environment.
- **Dependency Awareness:** CI verifies and logs runtime/dev dependencies (`osmnx`, `networkx`, `django`, `rest_framework`, `pytest_cov`, `node`, `npm`).
- **Enforced Coverage Gate:** Pytest runs with `--cov=backend/apps/core --cov-report=term-missing --cov-report=xml --cov-fail-under=80`. Builds fail if line coverage drops below 80% (Current Phase 29: **95.61%** coverage across 1,112 passing backend tests).
- **Mandatory Hygiene & Integrity:** CI validates presence of all project documentation, phase reports (`docs/progress/PHASE_01.md` through `PHASE_29.md`), and scans for leaked secrets or prohibited binary artifacts.
- **Frontend CI Gate:** `frontend-quality` executes `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` inside `frontend/`. No skipping or conditional deferral.
- **No Blanket `continue-on-error`:** CI jobs must fail when any required check or test fails.
- **No Test Weakening:** Never weaken assertion thresholds solely to pass CI builds.


