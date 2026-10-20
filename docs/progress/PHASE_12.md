# Phase 12 Implementation Report: Dynamic Neighbor Tables, Heartbeats, and Neighbor Loss Detection

**Phase:** Phase 12 — Dynamic Neighbor Tables, Heartbeats, and Neighbor Loss Detection  
**Status:** COMPLETED  
**Authoritative Acceptance Gate:** GitHub Actions CI Passing  
**Timestamp:** 2026-10-20  
**Starting Commit:** `01db6a0dc3e757b30e1cb3cabb3da705a200292d`  

---

## 1. Executive Summary & Objective

Phase 12 implements a dynamic, simulation-time-driven neighbor-management subsystem for the Adaptive Multi-Agent Path Planning (AMAPP) platform. Building upon the Phase 11 Vehicle-to-Vehicle (V2V) message protocol and spatial peer discovery framework, this subsystem allows each vehicle agent to maintain a dedicated local neighbor table tracking communicating peers, latest observed spatial telemetry, heartbeat freshness, timeout transitions (stale/removed), and atomic rollback snapshots.

Crucially, the architecture enforces a strict conceptual separation between physical proximity ($d \le R$), spatial discovery queries, and communication-derived neighbor knowledge. Physical proximity alone does not populate or refresh a neighbor record without valid message transmission.

All operations execute deterministically using simulation time, avoiding any reliance on wall-clock timers, background threads, or real networking sockets.

---

## 2. Phase 12 Acceptance Checklist

- [x] **Per-Vehicle Neighbor Tables:** Dedicated `NeighborTable` instances for all registered participants.
- [x] **Typed Neighbor Records:** Immutable `NeighborRecord` containing vehicle ID, observed position, distance, speed, heading, last seen simulation timestamp, last heartbeat timestamp, sequence number, and status.
- [x] **Physical Peer vs. Known Neighbor Separation:** Physical proximity ($d \le R$) does not populate neighbor tables without valid received communication packets (no omniscient leakage).
- [x] **Simulation-Time Heartbeats:** Periodic status broadcasts (`V2VMessageType.HEARTBEAT`) serve as heartbeats with monotonic per-sender sequence numbering.
- [x] **Deterministic Timeout & Stale Detection:** Stale boundary evaluated as $t_{\text{now}} - t_{\text{last\_hb}} \ge T_{\text{timeout}} - \epsilon$ ($\epsilon = 10^{-9}$).
- [x] **Configurable Stale Policies:** Configurable policies (`STALE_THEN_REMOVE`, `REMOVE_IMMEDIATELY`, `MARK_STALE`) with optional grace period $T_{\text{grace}}$.
- [x] **Fresh Heartbeat Recovery:** A fresh valid message ($seq > last\_seq$, unexpired) immediately restores a stale neighbor back to `ACTIVE`.
- [x] **Duplicate & Out-of-Order Rejection:** Older or duplicate sequence numbers and duplicate message IDs are safely rejected.
- [x] **Authoritative Engine Stepping:** Step ordering ingests inboxes into neighbor tables and runs maintenance deterministically within `SimulationEngine.step()`.
- [x] **Atomic Rollback Integration:** Failure during vehicle agent execution restores neighbor tables, sequence counters, transit queues, and metrics to pre-tick state.
- [x] **Deterministic Replay:** Identical scenario configurations and seeds yield bit-identical neighbor tables and metric histories.
- [x] **Full Regression Integrity:** All 586 Phase 2–11 tests remain passing; 38 new Phase 12 tests added (624 total passing, 96.78% line coverage).
- [x] **GitHub Actions Acceptance:** CI workflow updated and verified green across all jobs.

---

## 3. Architecture & Subsystem Design

### 3.1 Peer Classifications & Terminology

The neighbor subsystem establishes five distinct categories:
1. **Physical Peer:** A vehicle whose actual coordinate distance from the host satisfies $d \le R_{\text{comm}}$.
2. **Discovered Peer:** A candidate vehicle detected by a spatial geometric proximity query (`SpatialPeerDiscovery.find_peers`).
3. **Known Neighbor:** A vehicle for which the host has received and validated at least one communication packet, represented by an entry in `NeighborTable`.
4. **Stale Neighbor:** A previously known neighbor whose latest valid heartbeat exceeds the configured timeout:
   $$t_{\text{now}} - t_{\text{last\_heartbeat}} \ge T_{\text{timeout}}$$
5. **Removed Neighbor:** A stale neighbor whose elapsed silence has exceeded the combined timeout and grace period ($T_{\text{timeout}} + T_{\text{grace}}$), resulting in eviction from `NeighborTable`.

### 3.2 NeighborRecord Contract

Defined in `backend/apps/core/communication/neighbors.py`:
```python
@dataclass(frozen=True)
class NeighborRecord:
    vehicle_id: str
    last_position: Position2D
    last_distance_m: float
    last_speed_mps: float
    last_heading_rad: float
    last_seen_timestamp_s: float
    last_heartbeat_timestamp_s: float
    last_sequence_number: int
    status: NeighborStatus = NeighborStatus.ACTIVE
    last_message_id: Optional[str] = None
```

Invariants enforced during `__post_init__`:
- `vehicle_id` must be a non-empty string.
- `last_position` must be an instance of `Position2D`.
- `last_distance_m`, `last_speed_mps`, `last_seen_timestamp_s`, and `last_heartbeat_timestamp_s` must be finite non-negative numbers.
- `last_heading_rad` must be a finite float.
- `last_sequence_number` must be an integer $\ge 0$.
- `status` must be `NeighborStatus.ACTIVE` or `NeighborStatus.STALE`.

### 3.3 Per-Vehicle NeighborTable

Each registered participant maintains an independent `NeighborTable`:
- **Self-Exclusion:** Attempting to record `message.sender_id == owner_vehicle_id` raises `SelfNeighborError`.
- **Monotonic Sequence Enforcement:** If $seq \le last\_sequence\_number$, the message is rejected as out-of-order or duplicate.
- **Message Expiration:** Expired packets ($t_{\text{now}} \ge expiry\_timestamp\_s$) are rejected.
- **Distance Computation:** Evaluated at reception time using the receiver's current coordinate and the sender's reported position:
  $$d_{\text{observed}} = \text{observer\_position.distance\_to}(\text{message.sender\_position})$$
- **Deterministic Iteration:** All enumerations (`get_all_neighbors`, `get_active_neighbors`, `get_stale_neighbors`, `get_known_ids`) return records sorted by `vehicle_id`.
- **Snapshot Immutability:** `get_snapshot` produces an immutable `NeighborTableSnapshot`. Mutating the table afterwards does not alter the snapshot.

### 3.4 Heartbeat Timeout & Neighbor Loss Detection

Maintenance executes deterministically at each scheduled update interval:
- For policy `STALE_THEN_REMOVE`:
  - If $\Delta t_{\text{hb}} \ge T_{\text{timeout}} + T_{\text{grace}} - \epsilon$: Evict neighbor record.
  - Else if $\Delta t_{\text{hb}} \ge T_{\text{timeout}} - \epsilon$ and `status == ACTIVE`: Transition to `STALE`.
- For policy `REMOVE_IMMEDIATELY`:
  - If $\Delta t_{\text{hb}} \ge T_{\text{timeout}} - \epsilon$: Evict neighbor record directly.
- For policy `MARK_STALE`:
  - If $\Delta t_{\text{hb}} \ge T_{\text{timeout}} - \epsilon$ and `status == ACTIVE`: Transition to `STALE`; retain indefinitely until refreshed.

Maintenance is idempotent: repeated executions at the same timestamp produce no state changes or duplicate metric counts.

---

## 4. Simulation Engine & World State Integration

### 4.1 Authoritative Engine Stepping Sequence

In `SimulationEngine.step()`:
1. **Rollback Capture:** Pre-tick state of agents, signals, and communication network (including all `NeighborTable` instances and metrics) is captured.
2. **Network Advance:**
   - In-transit packets are delivered to inboxes for `NEXT_TICK` delivery policy.
   - Deliverable inbox messages are ingested into recipient neighbor tables via `update_neighbor_tables()`.
   - Heartbeat timeout and loss maintenance runs via `perform_neighbor_maintenance()`.
   - Periodic status broadcasts for due vehicles are created and dispatched.
   - For `SAME_TICK` delivery policy, newly broadcasted packets are immediately ingested into recipient tables.
3. **Agent Step Execution:** Each vehicle agent advances by $\Delta t$.
   - If an exception occurs, pre-tick state (including all neighbor tables and metrics) is restored atomically.
4. **Clock Advance:** Authoritative `SimulationClock.tick()` advances time.
5. **Signal Update:** Traffic signals update to new simulation time.
6. **Result Assembly:** Structured `TickResult` constructed and returned.

---

## 5. Automated Test Suite & Verification Results

### 5.1 Test Breakdown

| Test File | Test Count | Description |
|---|---|---|
| `test_communication_neighbors.py` | 24 | Invariants of `NeighborRecord`, `NeighborTable`, `NeighborManager`, serialization, and `CommunicationConfig` |
| `test_communication_heartbeat.py` | 8 | Exact timeout boundaries ($t \ge T_{\text{timeout}}$), grace periods, stale policies, stale recovery, and idempotency |
| `test_communication_neighbors_integration.py` | 6 | Multi-agent engine stepping, range entry/exit, no-omniscient leakage, atomic rollback, and deterministic replay |
| Pre-existing Phase 2–11 regression tests | 586 | Complete preservation of all earlier domain, graph, kinematics, signal, and scenario tests |
| **Total Test Suite** | **624** | **100% Passed across full automated test suite** |

### 5.2 Commands Executed and Results

```bash
# 1. Code style and linting
.\.venv\Scripts\ruff.exe check backend
# Output: All checks passed!

# 2. Django system checks
.\.venv\Scripts\python.exe backend/manage.py check
# Output: System check identified no issues (0 silenced).

# 3. Full pytest regression suite with coverage
.\.venv\Scripts\pytest.exe --cov=backend/apps/core --cov-report=term-missing --cov-fail-under=80
# Output: 624 passed in 6.32s, Required test coverage of 80% reached. Total coverage: 96.78%
```

---

## 6. GitHub Actions CI Verification

- **Workflow File:** `.github/workflows/ci.yml`
- **Trigger:** Git push to `main`
- **Commit SHA:** `b437ecd`
- **Run URL:** https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39404421887
- **Individual Job Statuses:**
  - `Repository Hygiene & Documentation Integrity`: SUCCESS (6s)
  - `Backend Lint, Test & Coverage`: SUCCESS (23s, 624 tests passed, 96.78% coverage)
  - `Frontend Lint, Typecheck & Build`: SUCCESS (5s, Node 22.x verified, frontend cleanly deferred)

---

## 7. Files Created, Modified, and Traceability

### 7.1 Files Created
- `backend/apps/core/communication/neighbors.py`
- `backend/apps/core/tests/test_communication_neighbors.py`
- `backend/apps/core/tests/test_communication_heartbeat.py`
- `backend/apps/core/tests/test_communication_neighbors_integration.py`
- `docs/progress/PHASE_12.md`

### 7.2 Files Modified
- `backend/apps/core/communication/exceptions.py`
- `backend/apps/core/communication/models.py`
- `backend/apps/core/communication/network.py`
- `backend/apps/core/communication/__init__.py`
- `backend/apps/core/simulation/engine.py`
- `backend/apps/core/simulation/world.py`
- `.github/workflows/ci.yml`
- `PROJECT_STATUS.md`
- `ARCHITECTURE.md`
- `REQUIREMENTS_TRACEABILITY.md`
- `README.md`
- `docs/TESTING.md`

---

## 8. Exact Phase 13 Handoff Instructions

1. **Phase 12 Completion Status:** Fully verified, all 624 automated tests passing locally and in GitHub Actions CI with 96.78% line coverage.
2. **Current Baseline Commit:** `b437ecd` (and documentation sync commit).
3. **Phase 13 Objective:** Implement **Decentralized V2V Coordination** (P2P sharing of congestion levels, road closures, and hazard alerts; vehicle-private knowledge stores and belief states).
4. **Strict Scope Discipline:** Do not implement adaptive rerouting (Phase 15), collision avoidance (Phase 16), or emergency priority (Phase 18) prematurely.
