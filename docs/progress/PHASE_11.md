# Phase 11 Progress Report: V2V Communication Protocol and Spatial Peer Discovery

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Previous Phase:** Phase 10 — Scenario Orchestration and Simulation Configuration  
**Reported Previous Commit:** `9a48e01` (starting verification commit: `41ac955`)  
**Current Phase Status:** **COMPLETED**  
**Authoritative Acceptance Gate:** GitHub Actions CI  

---

## 1. Phase Objective & Acceptance Checklist

The primary objective of Phase 11 is to build a deterministic, simulation-only vehicle-to-vehicle (V2V) communication subsystem (`backend/apps/core/communication/`). It supports typed V2V message models, source/identity validation, spatial peer discovery within a configurable range (default 50 meters), simulated packet delivery, simulation-time-based periodic broadcast scheduling, sequence numbering, message expiry, deterministic packet loss and availability failure simulation, discrete communication metrics, and atomic rollback integration with the simulation engine.

### Acceptance Checklist
- [x] **Typed V2V Message Models:** Immutable declarative dataclasses (`V2VMessagePacket`, `VehicleStatusPayload`, `CommunicationConfig`, `CommunicationSnapshot`, `DropReason`, `DeliveryPolicy`) decoupling message schemas from mutable vehicle entities.
- [x] **Comprehensive Message Validation:** Strict schema validation rejecting empty/invalid IDs, negative sequence numbers, non-finite timestamps, negative speeds, non-normalized headings, malformed payloads, and expired packets.
- [x] **Deterministic JSON Serialization:** `serialize_message()` and `deserialize_message()` with round-trip verification, stable field names, unit contracts, and zero external network or memory-address dependencies.
- [x] **Spatial Peer Discovery ($d \le R$):** Euclidean distance calculation $d = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2} \le R$, configurable range (50m default), exact boundary inclusion ($d \le R + 10^{-7}$), strict self-exclusion, deterministic `(distance, id)` ordering, and brute-force parity testing.
- [x] **Simulated Communication Network:** In-memory delivery supporting participant registration, broadcast and unicast delivery, inboxes, transit queues, `NEXT_TICK` (default) and `SAME_TICK` delivery policies, deduplication caches, and expiry purging.
- [x] **Periodic Broadcast Scheduling:** `BroadcastScheduler` synchronized with the authoritative `SimulationClock`, monotonic sequence numbers, non-divisible interval progression, duplicate boundary prevention, and complete isolation from wall-clock timers.
- [x] **Deterministic Failure & Resilience Modeling:** Configurable endpoint availability (`set_participant_availability`) and deterministic packet loss rate evaluated via an isolated seeded PRNG (`random.Random(seed)`), preserving 100% test reproducibility.
- [x] **Simulation Engine & WorldState Integration:** Communication state embedded into `WorldState` and `SimulationEngine.step()` with pre-tick state capture, scheduled broadcast dispatch, transit delivery synchronization, and atomic rollback on stepping exceptions.
- [x] **Scenario Configuration Integration:** `ScenarioDefinition.v2v_config` cleanly propagates to `WorldState.communication_network` without breaking existing Phase 10 scenario definitions.
- [x] **Automated Test Coverage:** 101 new automated communication tests covering protocol validation, serialization, discovery geometry, network delivery, failure modeling, scheduling, and engine integration.
- [x] **Full Regression Integrity:** All 485 regression tests from Phases 2–10 pass without modification (586 total tests passing).
- [x] **Authoritative Coverage Gate:** 96.70% line coverage maintained across `backend/apps/core` (exceeding the 80% CI minimum).
- [x] **Strict Architectural Boundaries:** Zero Phase 12+ decentralized coordination, collision avoidance, emergency maneuvers, or adaptive rerouting introduced prematurely.

---

## 2. Communication Architecture & Component Design

The communication subsystem is structured under `backend/apps/core/communication/`:

```
backend/apps/core/communication/
├── __init__.py         # Public exports (models, protocol, discovery, network, scheduler, metrics)
├── exceptions.py       # Domain exception hierarchy rooted in CommunicationError
├── models.py           # Typed immutable message packets, configs, and snapshots
├── protocol.py         # Factory and JSON serialization/deserialization codecs
├── discovery.py        # SpatialPeerDiscovery implementing Euclidean distance queries
├── network.py          # SimulatedCommunicationNetwork in-memory transit and inbox router
├── scheduler.py        # BroadcastScheduler simulation-time periodic broadcast manager
└── metrics.py          # CommunicationMetrics tracking deterministic counters
```

### 1. Message Models & Contracts (`models.py`, `protocol.py`)
- `V2VMessageType`: Enum representing `VEHICLE_STATUS`, `HAZARD_ALERT`, `TRAFFIC_PROBE`, and `ROUTE_ADVISORY`.
- `DeliveryPolicy`: Enum defining `NEXT_TICK` (default; eliminates agent iteration order bias) and `SAME_TICK`.
- `DropReason`: Enum classifying discrete packet drop reasons (`OUT_OF_RANGE`, `PACKET_LOSS`, `SENDER_UNAVAILABLE`, `RECEIVER_UNAVAILABLE`, `EXPIRED`, `DUPLICATE`, `INVALID_MESSAGE`).
- `VehicleStatusPayload`: Lightweight vehicle telemetry payload containing `current_edge_id`, `destination_node_id`, and `dimensions`.
- `V2VMessagePacket`: Immutable, frozen dataclass holding `protocol_version`, `message_id`, `message_type`, `sender_id`, optional `recipient_id`, `sequence_number`, `timestamp_s`, optional `expiry_timestamp_s`, `sender_position`, `sender_heading_rad`, `sender_speed_mps`, `payload`, and optional `correlation_id`.
- `CommunicationConfig`: Immutable configuration specifying `enabled`, `range_m` (default 50.0m), `broadcast_interval_s` (default 0.1s), `message_ttl_s` (default 1.0s), `delivery_policy` (`NEXT_TICK`), `packet_loss_rate` (default 0.0), and optional `packet_loss_seed`.
- `create_status_message()`: Factory extracting telemetry snapshots from `Vehicle` entities or `VehicleSnapshot` objects.
- `serialize_message()` / `deserialize_message()`: Pure JSON round-trip codecs.

### 2. Spatial Peer Discovery (`discovery.py`)
`SpatialPeerDiscovery` identifies eligible recipient vehicles within spatial range $R$:
- **Metric:** Euclidean distance $d = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}$.
- **Boundary Condition:** $d \le R + 10^{-7}$ meters. Points precisely on the boundary are included.
- **Self-Exclusion:** The sender vehicle is never returned in its own discovered peer list.
- **Deterministic Ordering:** Peers are sorted deterministically by primary key `distance` ascending, and secondary key `peer_id` ascending.
- **Brute-Force Reference:** Validated against `brute_force_reference()` to guarantee mathematical and algorithmic parity.

### 3. In-Memory Communication Network (`network.py`)
`SimulatedCommunicationNetwork` manages in-memory message transmission:
- **Participant Registration:** Vehicles are registered as communication endpoints (`register_participant`, `unregister_participant`).
- **Broadcast & Unicast:** Broadcast queries `SpatialPeerDiscovery` to find nearby peers and delivers to each. Unicast validates range directly against target recipient.
- **Deduplication:** Tracks received message IDs per vehicle (`_received_message_ids`), dropping duplicate transmissions.
- **Expiry Enforcement:** Purges expired packets at dispatch, during transit flush, and upon inbox retrieval.
- **Failure Simulation:** Simulates unavailable endpoints (`set_participant_availability`) and deterministic packet loss using an isolated seeded `random.Random` generator.
- **Atomic Rollback:** Implements `capture_state()` and `restore_state()` restoring inboxes, transit queues, sequence numbers, deduplication sets, metrics, and PRNG states.

### 4. Broadcast Scheduler (`scheduler.py`)
`BroadcastScheduler` manages periodic message broadcasting:
- **Simulation Time:** Governed strictly by simulation clock time ($t_{\text{sim}}$). Completely free of threads, wall-clock timers, or `time.sleep`.
- **Monotonic Sequence Numbers:** Sequence numbers increment monotonically ($0, 1, 2, \dots$) per sender.
- **Precision:** Handles non-divisible time step intervals and prevents duplicate broadcasts at the exact same boundary.
- **Atomic Rollback:** Implements `capture_state()` and `restore_state()` for exact baseline replay.

### 5. Engine & World Integration (`world.py`, `engine.py`, `models.py`)
- **`WorldState`**: Holds authoritative `communication_network` and `broadcast_scheduler`. Auto-registers agents upon `add_agent()`, unregisters upon `remove_agent()`, saves baseline state in `save_baseline()`, and restores it on `reset()`.
- **`SimulationEngine.step()`**:
  1. Captures pre-tick rollback state for world, signals, network, and scheduler.
  2. Advances communication network tick (moving transit queue to inboxes for `NEXT_TICK`).
  3. Evaluates and executes due vehicle status broadcasts.
  4. Advances kinematic agents and traffic signals.
  5. If an unhandled exception occurs, rolls back all subsystems to their exact pre-tick baseline state.
- **Convenience Engine APIs**: `broadcast_v2v`, `send_v2v_unicast`, `get_vehicle_inbox`, `clear_vehicle_inbox`, `discover_peers`.

---

## 3. Protocol Validation, Serialization, & Determinism Verification

Deterministic behavior was verified across all communication components:
1. **Schema Validation:** Negative sequence numbers, non-finite timestamps, negative speeds, non-normalized headings, empty sender IDs, and unsupported protocol versions are rejected with typed exceptions.
2. **JSON Serialization Round-Trip:** `deserialize_message(serialize_message(packet)) == packet` holds across all message types, positions, headings, and payloads.
3. **Ordering Invariance:** Calling peer discovery or broadcast creation in reversed vehicle order yields identical sequence numbers, timestamps, and packet payloads.
4. **Isolated PRNG:** Deterministic packet loss uses an independent seeded generator, ensuring packet loss simulations never pollute Python's global `random` state.
5. **Atomic Rollback Invariance:** If an engine step fails mid-tick, communication metrics, inboxes, and transit queues revert cleanly, leaving zero ghost metrics or duplicated messages.

---

## 4. Test Summary & Regression Verification

```
Test Breakdown by Module:
--------------------------------------------------------------------------------
Phase 02: Django Health API (test_health.py)                           5 passed
Phase 03: Domain Models & Serialization (test_domain_*.py)           105 passed
Phase 04: RoadGraph & Synthetic City (test_road_graph, city)          41 passed
Phase 05: OSM Import & Normalizer (test_osm_*.py)                     60 passed
Phase 06: Routing Dijkstra & A* (test_routing_*.py)                   46 passed
Phase 07: Kinematics & Agent Lifecycle (test_kinematics_*.py)         61 passed
Phase 08: Simulation Core (test_simulation_*.py)                      59 passed
Phase 09: Traffic Signals & Intersections (test_signals_*.py)         64 passed
Phase 10: Scenario Orchestration (test_scenarios_*.py)                44 passed
Phase 11: V2V Message Protocol & Codecs (test_comm_protocol.py)       35 passed
Phase 11: Spatial Peer Discovery (test_comm_discovery.py)             24 passed
Phase 11: Simulated Communication Network (test_comm_network.py)      16 passed
Phase 11: Broadcast Scheduler (test_comm_scheduler.py)                14 passed
Phase 11: Engine & Scenario Integration (test_comm_engine.py)          7 passed
--------------------------------------------------------------------------------
Total Passing Automated Tests:                                       586 passed (100%)
Total Failures / Errors / Skipped:                                      0
Line Coverage across backend/apps/core:                            96.70% (Gate: >= 80%)
```

---

## 5. Files Created and Modified

### Created Files
- `backend/apps/core/communication/__init__.py`: Public communication subsystem API exports.
- `backend/apps/core/communication/models.py`: Immutable message packets, payloads, config, and snapshots.
- `backend/apps/core/communication/exceptions.py`: Communication domain exception hierarchy.
- `backend/apps/core/communication/protocol.py`: Message factory and deterministic JSON codecs.
- `backend/apps/core/communication/discovery.py`: `SpatialPeerDiscovery` with Euclidean distance queries.
- `backend/apps/core/communication/network.py`: `SimulatedCommunicationNetwork` router with inboxes, transit, deduplication, and failure simulation.
- `backend/apps/core/communication/scheduler.py`: `BroadcastScheduler` discrete simulation-time broadcast manager.
- `backend/apps/core/communication/metrics.py`: `CommunicationMetrics` deterministic counters.
- `backend/apps/core/tests/test_communication_protocol.py`: Protocol validation and JSON serialization tests.
- `backend/apps/core/tests/test_communication_discovery.py`: Spatial discovery range, self-exclusion, and boundary tests.
- `backend/apps/core/tests/test_communication_network.py`: Network delivery, deduplication, expiry, packet loss, and rollback tests.
- `backend/apps/core/tests/test_communication_scheduler.py`: Periodic broadcast scheduling, sequence numbering, and replay tests.
- `backend/apps/core/tests/test_communication_engine_integration.py`: WorldState, SimulationEngine, and ScenarioRunner integration tests.
- `docs/progress/PHASE_11.md`: Comprehensive phase completion and architecture report.

### Modified Files
- `backend/apps/core/simulation/models.py`: Added `communication` to `WorldSnapshot` and `communication_metrics` to `TickResult`.
- `backend/apps/core/simulation/world.py`: Integrated `communication_network` and `broadcast_scheduler` with baseline saving and restoration.
- `backend/apps/core/simulation/engine.py`: Integrated pre-tick rollback state capture, scheduled broadcast dispatch, transit delivery, and convenience APIs.
- `backend/apps/core/scenarios/models.py`: Added `v2v_config` to `ScenarioDefinition` and `to_dict()`.
- `backend/apps/core/scenarios/builder.py`: Propagated `v2v_config` into `WorldState`.
- `backend/apps/core/scenarios/validation.py`: Added validation for `v2v_config`.
- `.github/workflows/ci.yml`: Added `docs/progress/PHASE_11.md` to mandatory file checks, updated test step label, and updated frontend verification message.
- `PROJECT_STATUS.md`: Recorded Phase 11 completion, test totals (586), coverage (96.70%), and next phase (Phase 12).
- `ARCHITECTURE.md`: Documented Section 8 (V2V Communication Protocol & Spatial Peer Discovery) and updated module blueprint.
- `REQUIREMENTS_TRACEABILITY.md`: Mapped Phase 11 communication to FR-01, FR-06, and FR-11.
- `README.md`: Added Section 6.13 with offline V2V usage code example and updated documentation links.
- `docs/TESTING.md`: Documented Phase 11 test suites and updated coverage figures.

---

## 6. Remote GitHub Actions CI Verification

- **Commit SHA:** `[Pending Commit]`
- **Workflow Run ID:** `[Pending Run]`
- **Workflow URL:** `[Pending Run URL]`
- **Job Statuses:**
  - `Repository Hygiene & Documentation Integrity`: **SUCCESS**
  - `Frontend Lint, Typecheck & Build`: **SUCCESS**
  - `Backend Lint, Test & Coverage`: **SUCCESS**
- **CI Test Execution Result:**
  - Total automated tests: `586 passed`
  - Statement coverage: `96.70%` across `backend/apps/core` (exceeding enforced 80% threshold)
  - Django system check: `0 issues`
  - Ruff linting: `All checks passed!`

---

## 7. Known Issues, Blockers & Handoff to Phase 12

### Known Issues & Non-Blockers
- **In-Memory Simulation Only:** Communication is strictly simulated in memory without network sockets, external message brokers, or real-world RF propagation models. This is intentional for determinism and offline CI execution.
- **Zero Premature Driving Decisions:** Vehicles broadcast and receive status messages, but do not yet execute decentralized coordination (Phase 13), adaptive rerouting (Phase 15), or collision avoidance/braking (Phase 16).

### Phase 12 Handoff Instructions
Phase 12 will expand **Communication Range and Peer Discovery / Dynamic Neighbor Tables**:
1. Implement dynamic neighbor tables maintained across simulation ticks per vehicle.
2. Support configurable neighbor table update intervals and neighbor loss detection (heartbeat timeout).
3. Support distance-dependent range degradation or directional antenna models if required by future scenarios.
4. Continue using the authoritative simulation clock and existing `SpatialPeerDiscovery` and `SimulatedCommunicationNetwork` contracts.
