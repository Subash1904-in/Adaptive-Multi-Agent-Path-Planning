# Phase 16 Engineering Progress Report: Collision Detection, Safe Separation, and Collision Avoidance

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Date:** 2026-10-21  
**Baseline Git Commit:** `1fd8bf4` (Phase 15 verified CI completion commit)  
**Branch:** `main`  
**Phase Status:** COMPLETED  

---

## 1. Executive Summary & Phase Objective

Phase 16 introduces a deterministic safety subsystem into the AMAPP simulation platform for vehicle-to-vehicle collision detection, safe separation verification, Time-to-Collision (TTC) estimation, multi-tier risk classification, and controlled collision avoidance overrides via deceleration and emergency braking.

Prior to Phase 16, vehicle agents planned and traversed routes purely according to road graphs, kinematics, and traffic signals without detecting physical proximity or geometric overlap with other vehicles.

In Phase 16, we developed and verified:
1. **2D Oriented Bounding Box (OBB) & SAT Overlap Detection (`geometry.py`)**: Models vehicles as oriented rectangles with center $(x, y)$, length, width, and heading $\theta$. Tests overlap via the Separating Axis Theorem (SAT) across 4 normal projection axes with configurable boundary-touching semantics and exact polygon separation distance calculation.
2. **Kinematic Relative Motion & Closing Speed (`detection.py`)**: Computes closing speed vector projection along the relative displacement unit vector; explicitly classifies receding and parallel vehicles without artificial risk.
3. **Safe Separation Distance Policy (`detection.py`)**: Computes required headway $d_{\text{safe}} = d_0 + v_{\text{rel}}^{+} T_r + \frac{v^2}{2 a_{\text{brake}}}$ with strictly positive, validated physical quantities.
4. **Time-to-Collision (TTC) Estimation (`detection.py`)**: Formulates deterministic time-to-collision $\text{TTC} = d_{\text{separation}} / v_{\text{closing}}$, returning explicit `None` for non-closing or receding pairs.
5. **5-Tier Risk Classification (`detection.py`)**: Deterministically categorizes conflicts into `COLLISION` (physical overlap), `IMMINENT` ($\text{TTC} \le 1.5\text{s}$), `HIGH_RISK` ($\text{TTC} \le 3.0\text{s}$), `CAUTION` ($\text{TTC} \le 5.0\text{s}$), and `SAFE`.
6. **Conservative Simultaneous Conflict Resolution (`policy.py`)**: Selects the strongest valid deceleration override for vehicles involved in multiple conflicts, strictly enforcing kinematic acceleration and deceleration bounds.
7. **SimulationEngine Integration & Atomic Rollback (`world.py`, `engine.py`, `manager.py`)**: Executes safety checks on a frozen pre-tick snapshot of active vehicles; restores vehicle kinematics, routing state, neighbor tables, and safety metrics atomically if tick execution fails.
8. **Structured Event Logging & Cumulative Metrics (`metrics.py`, `models.py`)**: Records immutable `SafetyEvent` records for collisions and near-misses; tracks pair checks, overrides, minimum separation, and minimum TTC.
9. **Automated Testing & Strict Regression**: Added 48 new unit and integration tests across 4 test suites (`test_safety_*.py`), bringing the full regression suite to **808 passed tests** with **96% line coverage** on `backend/apps/core`.

> **Educational Simulation Disclaimer:** This software is an educational and research simulation model. It is NOT certified, verified, or suitable for direct deployment in physical autonomous vehicles.

---

## 2. Baseline State & Starting Repository Context

- **Baseline Commit:** `1fd8bf4` (`docs(phase-15): record verified CI run URL and completed job details`).
- **Starting Test Suite:** 760 passing tests, 0 failures, 95.69% line coverage on `backend/apps/core`.
- **Clean Working Tree:** Verified prior to Phase 16 modifications.
- **Architectural Boundary Adherence:** Zero implementation of pedestrian crosswalk simulation (Phase 17) or emergency vehicle priority (Phase 18).

---

## 3. Mathematical Formulations & Configuration Invariants

### 3.1 Oriented Bounding Box (OBB) & SAT Overlap Detection
Each vehicle is represented as a 2D Oriented Bounding Box:
- Center position: $(x_c, y_c) \in \mathbb{R}^2$
- Length: $L > 0$ along the vehicle's longitudinal axis
- Width: $W > 0$ along the vehicle's lateral axis
- Heading angle: $\theta \in \mathbb{R}$ (radians, counterclockwise from $+x$ East)

Four box corner vertices in world coordinates:
$$\mathbf{p}_{\text{corner}} = \begin{pmatrix} x_c \\ y_c \end{pmatrix} + \mathbf{R}(\theta) \begin{pmatrix} \pm L/2 \\ \pm W/2 \end{pmatrix}$$
where $\mathbf{R}(\theta) = \begin{pmatrix} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{pmatrix}$.

**Separating Axis Theorem (SAT):**
For two oriented bounding boxes $A$ and $B$, the set of potential separating axes $\mathcal{A}$ comprises the 4 unique edge normal vectors:
$$\mathcal{A} = \{ \mathbf{u}_{A,\text{long}}, \mathbf{u}_{A,\text{lat}}, \mathbf{u}_{B,\text{long}}, \mathbf{u}_{B,\text{lat}} \}$$
Boxes $A$ and $B$ overlap if and only if their 1D projected intervals overlap on every axis $\mathbf{a} \in \mathcal{A}$:
$$\max\left(\min_{i} \mathbf{p}_{A,i} \cdot \mathbf{a}, \min_{j} \mathbf{p}_{B,j} \cdot \mathbf{a}\right) \le \min\left(\max_{i} \mathbf{p}_{A,i} \cdot \mathbf{a}, \max_{j} \mathbf{p}_{B,j} \cdot \mathbf{a}\right)$$
Boundary touching is treated as overlap when `touching_is_overlap=True`.

### 3.2 Closing Speed & Vector Kinematics
Given vehicles $A$ and $B$ with center positions $\mathbf{p}_A, \mathbf{p}_B$ and velocities $\mathbf{v}_A, \mathbf{v}_B$:
$$\mathbf{u}_{AB} = \frac{\mathbf{p}_B - \mathbf{p}_A}{\|\mathbf{p}_B - \mathbf{p}_A\|}$$
$$v_{\text{closing}} = -(\mathbf{v}_B - \mathbf{v}_A) \cdot \mathbf{u}_{AB} = (\mathbf{v}_A - \mathbf{v}_B) \cdot \mathbf{u}_{AB}$$
- If $v_{\text{closing}} > 0$: distance between vehicles is decreasing (approaching).
- If $v_{\text{closing}} \le 0$: distance between vehicles is increasing or constant (receding or parallel).

### 3.3 Safe Separation Distance Formula
$$d_{\text{safe}} = d_0 + v_{\text{rel}}^{+} T_r + \frac{v^2}{2 a_{\text{brake}}}$$
where:
- $d_0 > 0$: Static geometric buffer clearance (default: $3.0\text{ m}$).
- $v_{\text{rel}}^{+} = \max(0, v_{\text{closing}})$: Closing speed component ($[0, \infty)$).
- $T_r \ge 0$: Driver/controller response interval (default: $0.5\text{ s}$).
- $a_{\text{brake}} > 0$: Reference braking deceleration capability (default: $4.0\text{ m/s}^2$).
- $v \ge 0$: Current vehicle speed ($\text{m/s}$).

### 3.4 Time-to-Collision (TTC) Estimation
$$\text{TTC} = \begin{cases} \frac{d_{\text{separation}}}{v_{\text{closing}}} & \text{if } v_{\text{closing}} > 10^{-4} \text{ m/s} \\ \infty \text{ (represented as None)} & \text{otherwise} \end{cases}$$
If vehicles already geometrically overlap ($d_{\text{separation}} = 0$), $\text{TTC} = 0.0\text{ s}$.

### 3.5 Risk Classification Thresholds
| Risk Level | Condition | Recommended Action | Default Deceleration |
|---|---|---|---|
| `COLLISION` | Geometric overlap ($d_{\text{sep}} = 0$) | `EMERGENCY_BRAKE` | Configured `emergency_decel_mps2` |
| `IMMINENT` | $\text{TTC} \le \text{TTC}_{\text{imminent}}$ ($1.5\text{s}$) or $d_{\text{sep}} < 0.5 \cdot d_0$ | `EMERGENCY_BRAKE` | Configured `emergency_decel_mps2` |
| `HIGH_RISK` | $\text{TTC} \le \text{TTC}_{\text{high\_risk}}$ ($3.0\text{s}$) or $d_{\text{sep}} < d_0$ | `STRONG_BRAKE` | Configured `strong_decel_mps2` |
| `CAUTION` | $\text{TTC} \le \text{TTC}_{\text{caution}}$ ($5.0\text{s}$) or $d_{\text{sep}} < d_{\text{safe}}$ | `GENTLE_BRAKE` | Configured `gentle_decel_mps2` |
| `SAFE` | $d_{\text{sep}} \ge d_{\text{safe}}$ and no TTC violation | `NONE` | No override ($0.0\text{ m/s}^2$) |

---

## 4. Configuration Schema (`SafetyConfig`)

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `enabled` | `bool` | `True` | Must be boolean | Master toggle for safety subsystem. (Defaults to `False` in legacy WorldState if omitted). |
| `vehicle_length_m` | `float` | `4.5` | $> 0$, finite | Longitudinal bounding box length in meters. |
| `vehicle_width_m` | `float` | `2.0` | $> 0$, finite | Lateral bounding box width in meters. |
| `min_separation_m` | `float` | `3.0` | $> 0$, finite | Static geometric buffer distance $d_0$. |
| `near_miss_distance_m` | `float` | `5.0` | $\ge 0$, finite | Threshold distance for logging near-miss events. |
| `reaction_time_s` | `float` | `0.5` | $\ge 0$, finite | Response time delay $T_r$ in seconds. |
| `braking_accel_reference_mps2` | `float` | `4.0` | $> 0$, finite | Reference deceleration magnitude for braking distance allowance. |
| `gentle_decel_mps2` | `float` | `2.0` | $> 0$, finite | Target deceleration for `CAUTION` risk level. |
| `strong_decel_mps2` | `float` | `4.5` | $\ge \text{gentle}$, finite | Target deceleration for `HIGH_RISK` risk level. |
| `emergency_decel_mps2` | `float` | `7.0` | $\ge \text{strong}$, finite | Target deceleration for `IMMINENT` and `COLLISION` risk levels. |
| `ttc_imminent_s` | `float` | `1.5` | $> 0$, finite | Threshold upper bound for imminent collision TTC. |
| `ttc_high_risk_s` | `float` | `3.0` | $> \text{imminent}$, finite | Threshold upper bound for high risk TTC. |
| `ttc_caution_s` | `float` | `5.0` | $> \text{high\_risk}$, finite | Threshold upper bound for caution risk TTC. |
| `touching_is_overlap` | `bool` | `True` | Must be boolean | Whether boundary-touching geometries count as collision. |
| `enable_event_logging` | `bool` | `True` | Must be boolean | Whether to buffer `SafetyEvent` records for dashboard visualization. |

---

## 5. Architectural Implementation Details

### 5.1 Package Structure (`backend/apps/core/safety/`)
```text
backend/apps/core/safety/
├── __init__.py           # Public exports (SafetyManager, CollisionDetector, SafetyPolicy, etc.)
├── exceptions.py         # Explicit safety exceptions (GeometryValidationError, etc.)
├── models.py             # Data classes, Enums, and configurations
├── geometry.py           # 2D OBB, SAT overlap, point-to-segment, exact polygon distance
├── detection.py          # Closing speed, safe separation, TTC, risk classification, Pairwise detector
├── policy.py             # Deterministic conflict resolution (strongest deceleration)
├── metrics.py            # Safety counters and atomic snapshot capture/restore
└── manager.py            # Safety manager facade coordinating detection, policy, overrides, rollback
```

### 5.2 Deterministic Multi-Vehicle Evaluation
To guarantee that evaluation ordering never depends on vehicle registration order:
1. Active vehicles are filtered to those in `EN_ROUTE` or `BLOCKED` states (excluding `ARRIVED` or inactive).
2. Vehicles are sorted by canonical string identifier: `sorted(vehicles, key=lambda a: a.vehicle.id)`.
3. Unique pairs $(A, B)$ are enumerated using `itertools.combinations` such that $A.\text{id} < B.\text{id}$.
4. A vehicle is never paired with itself, and no pair is evaluated twice in a tick.
5. All vehicle positions and headings are frozen from the pre-tick state snapshot, preventing control overrides applied to vehicle $A$ from mutating inputs for subsequent pair evaluations within the same tick.

### 5.3 Simultaneous Conflict Resolution Policy
When a vehicle faces multiple simultaneous conflicts (e.g., nearing an intersection with multiple crossing vehicles):
1. Candidate braking requests are aggregated into a candidate action list.
2. Candidate actions are sorted deterministically by deceleration magnitude descending:
   `candidates.sort(key=lambda item: (-item[1], item[0].value, item[3]))`
3. The strongest valid deceleration magnitude is selected (`max_candidate`).
4. Deceleration is clamped to the vehicle's physical kinematic capability:
   $$\text{target\_accel} = -\min(\text{selected\_decel}, \text{agent.config.max\_deceleration\_mps2})$$
5. Kinematic integration ensures speed is bounded at zero: $v_{t+\Delta t} = \max(0, v_t + a \Delta t)$.

### 5.4 SimulationEngine Integration Lifecycle
The high-level tick lifecycle in `SimulationEngine.step()`:
```text
1. Capture Pre-Tick Baseline (world, vehicles, routes, comms, coordination, safety metrics)
2. Advance V2V Communication Network (Phase 14)
3. Ingest Coordination Reports & Local Knowledge (Phase 13)
4. Evaluate Adaptive Rerouting & Route Replacements (Phase 15)
5. Freeze Snapshot of Active Vehicle States
6. Detect Pairwise Geometric Collisions, Separations, and TTC (Phase 16)
7. Classify Risks & Resolve Safety Overrides (Phase 16)
8. Merge Overrides with Target Accelerations (Safety overrides take precedence)
9. Authoritative Kinematics & Signal Stepping (Phases 7 & 9)
10. Record Safety Metrics, Collision Events & Near-Misses (Phase 16)
11. Commit World State & Clock Increment
```

### 5.5 Atomic Rollback Guarantees
If any failure occurs during agent stepping:
- `WorldState.restore_baseline()` is invoked.
- Vehicle positions, headings, velocities, and accelerations are reverted to pre-tick values.
- `SafetyManager.restore_state()` restores metrics counters and trims buffered `SafetyEvent` records to the pre-tick index.
- No partial collision count or override counter is leaked into subsequent ticks or retries.
- Verified via failure-injection tests (`test_stepping_failure_rolls_back_safety_metrics_and_events`).

---

## 6. Files Created and Modified

### Created Files:
- `backend/apps/core/safety/__init__.py`
- `backend/apps/core/safety/exceptions.py`
- `backend/apps/core/safety/models.py`
- `backend/apps/core/safety/geometry.py`
- `backend/apps/core/safety/detection.py`
- `backend/apps/core/safety/policy.py`
- `backend/apps/core/safety/metrics.py`
- `backend/apps/core/safety/manager.py`
- `backend/apps/core/tests/test_safety_geometry.py`
- `backend/apps/core/tests/test_safety_detection_and_ttc.py`
- `backend/apps/core/tests/test_safety_policy.py`
- `backend/apps/core/tests/test_safety_engine_integration.py`
- `docs/progress/PHASE_16.md`

### Modified Files:
- `backend/apps/core/simulation/models.py`: Added `safety_metrics` and `safety_events` to `TickResult`; added `safety` section to `WorldSnapshot`.
- `backend/apps/core/simulation/world.py`: Integrated `SafetyConfig`, `SafetyManager`, baseline capture/restore, reset, snapshot.
- `backend/apps/core/simulation/engine.py`: Integrated safety detection, override application, atomic rollback on error, structured `TickResult` safety metrics.
- `backend/apps/core/scenarios/models.py`: Added optional `safety_config: Optional[SafetyConfig]` to `ScenarioDefinition`.
- `backend/apps/core/scenarios/validation.py`: Added `safety_config` validation.
- `backend/apps/core/scenarios/builder.py`: Passes `safety_config` to `WorldState`, sets vehicle `max_speed_mps` from kinematics/initial speed.
- `backend/apps/core/scenarios/examples.py`: Added 4 deterministic Phase 16 safety scenario templates.
- `.github/workflows/ci.yml`: Added `"docs/progress/PHASE_16.md"` to required documentation files, updated test description to "(Phases 2-16)".
- `PROJECT_STATUS.md`: Recorded Phase 16 complete, set Phase 17 pending, updated test counts.
- `ARCHITECTURE.md`: Documented safety subsystem architecture, formulas, and boundaries.
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-09 traceability and status.
- `README.md`: Added Phase 16 feature overview, educational disclaimer, and deterministic braking example.
- `docs/TESTING.md`: Documented safety test suites and updated test metrics.

---

## 7. Automated Test Suite & Local Verification

### Test Breakdown:
- **Phase 16 Safety Geometry & SAT (`test_safety_geometry.py`):** 18 passed.
- **Phase 16 Detection, Closing Speed, TTC & Risk (`test_safety_detection_and_ttc.py`):** 13 passed.
- **Phase 16 Safety Policy & Conflict Resolution (`test_safety_policy.py`):** 9 passed.
- **Phase 16 Engine Integration, Scenarios & Rollback (`test_safety_engine_integration.py`):** 8 passed.
- **Phases 2–15 Regression Tests:** 760 passed.
- **Total Test Suite:** **808 passed, 0 failed in 5.98s**.

### Code Coverage:
- `backend/apps/core/safety/`: **98%** coverage.
- Total `backend/apps/core`: **96%** line coverage (enforced minimum: 80%).

### Code Quality & Hygiene:
- `ruff check backend`: Passed with 0 errors.
- `python backend/manage.py check`: Passed with 0 issues.

---

## 8. GitHub Actions CI Verification

- **Authoritative Gate:** GitHub Actions (`.github/workflows/ci.yml`).
- **Trigger Commit:** `e667aa7` (Initial implementation commit) -> Verified CI run.
- **GitHub Actions Workflow Run:** [CI Pipeline Run](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions)
- **Job Results:**
  - `repo-hygiene`: PASSED
  - `backend-quality`: PASSED (808 tests passed, 96% coverage)
  - `frontend-quality`: PASSED

---

## 9. Phase 17 Handoff Instructions

Phase 16 is complete and authoritative. When prompted for **Phase 17 (Pedestrians and Traffic Signals)**:
1. Implement pedestrian agents, pedestrian kinematics, and crossing zones/crosswalks.
2. Integrate pedestrian yield logic with traffic signal states and intersection stop lines.
3. Preserve the Phase 16 safety subsystem contracts without alteration.
4. Ensure all 808 existing regression tests remain passing.
