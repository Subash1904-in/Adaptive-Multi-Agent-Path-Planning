# Phase 17 Engineering Progress Report: Pedestrian Agents, Crosswalks, and Traffic-Signal Interaction

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Date:** 2026-10-21  
**Baseline Git Commit:** `eca40b4` (Phase 16 verified CI completion commit)  
**Branch:** `main`  
**Phase Status:** COMPLETED  

---

## 1. Executive Summary & Phase Objective

Phase 17 introduces realistic pedestrian agents, crosswalk corridors, traffic-signal crossing indications, and vehicle–pedestrian safety interaction to the AMAPP simulation platform.

Prior to Phase 17, roadway entities were exclusively vehicular. Phase 17 introduces:
1. **Typed Pedestrian Agents & Lifecycle State Machine (`PedestrianAgent`, `PedestrianLifecycleState`)**: Implements states (`IDLE`, `APPROACHING_CROSSWALK`, `WAITING_TO_CROSS`, `CROSSING`, `WALKING`, `ARRIVED`, `BLOCKED`) with strict transition validation, preventing invalid state jumps.
2. **Bounded Walking Kinematics**: Enforces speed bounds ($0.5 \le v \le 2.5\text{ m/s}$, default $1.2\text{ m/s}$), goal-directed planar vector stepping, and exact target snapping to avoid overshooting or oscillatory stepping artifacts.
3. **Crosswalk Corridor Modeling (`Crosswalk`)**: Defines rectangular crossing corridors with entry and exit curbs, width $W$, waiting radius $R_{\text{wait}}$, and longitudinal and lateral 2D vector projections ($s_{\text{long}} \in [0, L]$, $|s_{\text{lat}}| \le W/2$).
4. **Traffic Signal Crossing Indications**: Integrates crosswalks with Phase 9 intersection traffic signals, translating vehicular phases into pedestrian indications (`RED` $\to$ `WALK`, `YELLOW` $\to$ `CLEARANCE`, `GREEN` $\to$ `DONT_WALK`; unsignalized $\to$ `WALK`).
5. **Clearance Policy**: Guarantees that pedestrians already in the `CROSSING` state when a signal turns `DONT_WALK` continue advancing to the exit curb without sudden stops, mid-street stranding, or teleportation.
6. **Vehicle–Pedestrian Conflict Detection & Braking Overrides**: Extends the Phase 16 2D OBB Separating Axis Theorem (SAT) safety subsystem to evaluate vehicle–pedestrian conflicts, compute Time-to-Collision (TTC), enforce safe headways, and apply strong or emergency braking overrides to approaching vehicles.
7. **Authoritative SimulationEngine Single-Clock Integration**: Steps pedestrians in lockstep with the simulation clock, evaluates safety overrides from frozen pre-tick world snapshots, aggregates point-in-time and cumulative metrics, and provides atomic rollback and reset guarantees.
8. **Scenario Orchestration & Automated Testing**: Adds crosswalk and pedestrian scenario definition schema, builder assembly, and 45 new automated tests across 6 dedicated test modules, bringing the full regression suite to **853 passed tests** with **96% line coverage** on `backend/apps/core`.

> **Educational Simulation Disclaimer:** This software is an educational and research simulation model. It is NOT certified, verified, or suitable for direct deployment in physical autonomous vehicles.

---

## 2. Baseline State & Starting Repository Context

- **Baseline Commit:** `eca40b4` (`docs(phase-16): record verified CI run URL and completed job details`).
- **Starting Test Suite:** 808 passing tests, 0 failures, 96% line coverage on `backend/apps/core`.
- **Clean Working Tree:** Verified prior to Phase 17 modifications.
- **Architectural Boundary Adherence:** Zero implementation of emergency vehicle priority (Phase 18), reinforcement learning (Phases 32–34), or frontend dashboards (Phases 23–30).

---

## 3. Mathematical Formulations & Configuration Invariants

### 3.1 Pedestrian Kinematics & Target Snapping
Given pedestrian position $\mathbf{p}_t = (x_t, y_t)$, destination $\mathbf{p}_{\text{dest}} = (x_d, y_d)$, desired speed $v$, and time step $\Delta t$:
$$\mathbf{d} = \mathbf{p}_{\text{dest}} - \mathbf{p}_t, \quad d = \|\mathbf{d}\| = \sqrt{(x_d - x_t)^2 + (y_d - y_t)^2}$$

If $d \le v \Delta t$:
$$\mathbf{p}_{t+\Delta t} = \mathbf{p}_{\text{dest}}, \quad \text{state} \leftarrow \text{ARRIVED}$$
Otherwise:
$$\hat{\mathbf{u}} = \frac{\mathbf{d}}{d}, \quad \mathbf{p}_{t+\Delta t} = \mathbf{p}_t + v \Delta t \hat{\mathbf{u}}$$

This guarantees exact target arrival without numerical overshoot or limit cycles.

### 3.2 Crosswalk Corridor Vector Projections
For a crosswalk corridor defined by entry curb $\mathbf{p}_{\text{entry}}$ and exit curb $\mathbf{p}_{\text{exit}}$ with width $W$:
$$\mathbf{v}_{\text{corridor}} = \mathbf{p}_{\text{exit}} - \mathbf{p}_{\text{entry}}, \quad L = \|\mathbf{v}_{\text{corridor}}\|$$
$$\hat{\mathbf{u}} = \frac{\mathbf{v}_{\text{corridor}}}{L} = (\hat{u}_x, \hat{u}_y), \quad \hat{\mathbf{w}} = (-\hat{u}_y, \hat{u}_x)$$

For any 2D point $\mathbf{p} = (x, y)$, displacement $\Delta\mathbf{p} = \mathbf{p} - \mathbf{p}_{\text{entry}}$:
$$s_{\text{long}} = \Delta\mathbf{p} \cdot \hat{\mathbf{u}}, \quad s_{\text{lat}} = \Delta\mathbf{p} \cdot \hat{\mathbf{w}}$$
A point is within the crosswalk corridor if and only if:
$$0.0 \le s_{\text{long}} \le L \quad \text{and} \quad |s_{\text{lat}}| \le \frac{W}{2}$$

The waiting area is defined as:
$$\|\mathbf{p} - \mathbf{p}_{\text{entry}}\| \le R_{\text{wait}}$$

### 3.3 Traffic Signal Mapping & Clearance Policy
The crosswalk signal indication $S_{\text{ped}}$ is determined from vehicular signal phase $S_{\text{veh}}$:
$$S_{\text{ped}} = \begin{cases}
\text{WALK} & \text{if } S_{\text{veh}} = \text{RED} \text{ or unsignalized} \\
\text{CLEARANCE} & \text{if } S_{\text{veh}} = \text{YELLOW} \\
\text{DONT\_WALK} & \text{if } S_{\text{veh}} = \text{GREEN}
\end{cases}$$

- **Entry Invariant:** A pedestrian in `APPROACHING_CROSSWALK` or `WAITING_TO_CROSS` at the entry waiting area enters the corridor and transitions to `CROSSING` if and only if $S_{\text{ped}} = \text{WALK}$.
- **Clearance Invariant:** If a pedestrian is already in `CROSSING` and $S_{\text{ped}}$ changes to `CLEARANCE` or `DONT_WALK`, the pedestrian **continues stepping toward the exit curb** until reaching the destination curb.

### 3.4 Vehicle–Pedestrian Conflict Detection & SAT Overlap
Pedestrians are treated as oriented bounding boxes with dimensions $L_{\text{ped}} = 0.6\text{m}, W_{\text{ped}} = 0.6\text{m}$.
The Separating Axis Theorem evaluates 1D projection overlap across 4 normal axes ($\mathcal{A} = \{\mathbf{u}_{v,\text{long}}, \mathbf{u}_{v,\text{lat}}, \mathbf{u}_{p,\text{long}}, \mathbf{u}_{p,\text{lat}}\}$).
- When polygon separation distance $d_{\text{sep}} > 0$:
  $$v_{\text{closing}} = -(\mathbf{v}_{\text{vehicle}} - \mathbf{v}_{\text{ped}}) \cdot \frac{\mathbf{p}_{\text{ped}} - \mathbf{p}_{\text{vehicle}}}{\|\mathbf{p}_{\text{ped}} - \mathbf{p}_{\text{vehicle}}\|}$$
  $$\text{TTC} = \begin{cases} \frac{d_{\text{sep}}}{v_{\text{closing}}} & \text{if } v_{\text{closing}} > 0.1\text{ m/s} \\ \text{None} & \text{otherwise} \end{cases}$$
- Safe separation distance is enforced:
  $$d_{\text{safe}} = d_0 + \max(0, v_{\text{closing}}) T_r + \frac{v_{\text{vehicle}}^2}{2 a_{\text{brake}}}$$
- Vehicles approaching crossing pedestrians receive `STRONG_BRAKE` or `EMERGENCY_BRAKE` overrides.

---

## 4. Implementation Details

### 4.1 Subsystems Created or Modified

1. **`backend/apps/core/pedestrians/`**:
   - `exceptions.py`: `DuplicatePedestrianError`, `PedestrianNotFoundError`, `CrosswalkNotFoundError`, `InvalidCrosswalkError`, `InvalidPedestrianStateError`, `PedestrianKinematicsError`, `InvalidPedestrianConfigError`.
   - `models.py`: `PedestrianLifecycleState`, `PedestrianSignalState`, `PedestrianConfig`, `PedestrianStepResult`, `validate_pedestrian_transition`.
   - `crosswalk.py`: `Crosswalk` model with 2D corridor geometry, vector projections, and signal indication mapping.
   - `agent.py`: `PedestrianAgent` implementing kinematic stepping, clearance policy, arrival snapping, and state capture/restoration.
   - `metrics.py`: `PedestrianMetrics` tracking active, waiting, crossing, arrived counts, cumulative wait/crossing times, and conflicts.
   - `__init__.py`: Clean public API export.

2. **`backend/apps/core/safety/`**:
   - `models.py`: Added `pedestrian_length_m`, `pedestrian_width_m` to `SafetyConfig`, `is_pedestrian_conflict`, `pedestrian_id` to `VehiclePairCollision`, and `pedestrian_id` to `SafetyEvent`.
   - `geometry.py`: Added `OrientedBoundingBox2D.from_pedestrian`.
   - `detection.py`: Added `CollisionDetector.evaluate_vehicle_pedestrian`, updated `detect_all_conflicts` with pedestrian support.
   - `manager.py`: Integrated pedestrian conflict evaluation, vehicle deceleration override staging, and safety event logging.

3. **`backend/apps/core/simulation/`**:
   - `models.py`: Added `pedestrians`, `crosswalks`, `pedestrian_metrics` to `WorldSnapshot` and `TickResult`.
   - `world.py`: Added pedestrian and crosswalk registration, lookup, baselines, reset, and snapshots.
   - `engine.py`: Integrated single-clock pedestrian stepping, pre-tick rollback state capture, safety evaluation with pedestrians, and atomic rollback on failure.

4. **`backend/apps/core/scenarios/`**:
   - `models.py`: Added `CrosswalkScenarioDefinition` and `PedestrianScenarioDefinition` to `ScenarioDefinition`.
   - `validation.py`: Added structural, semantic, and graph compatibility validation rules.
   - `builder.py`: Added crosswalk and pedestrian registration during scenario assembly.
   - `examples.py`: Added Phase 17 scenario templates:
     - `create_pedestrian_waiting_at_red_signal_scenario`
     - `create_pedestrian_crossing_permitted_scenario`
     - `create_vehicle_braking_for_pedestrian_scenario`
     - `create_unavoidable_vehicle_pedestrian_collision_scenario`

---

## 5. Automated Test Suite & Verification Results

### 5.1 Test Breakdown by Module

| Test Module | Tests | Status | Scope Covered |
|---|---|---|---|
| `test_pedestrian_models_and_kinematics.py` | 12 | Passed | States, transitions, configs, bounded velocity, target arrival snapping |
| `test_pedestrian_crosswalk.py` | 10 | Passed | Geometry, vector projections, corridor bounds, waiting areas, signal mapping |
| `test_pedestrian_signal_interaction.py` | 6 | Passed | Waiting on RED veh signal, clearance policy, registration order independence |
| `test_pedestrian_safety_and_collisions.py` | 7 | Passed | SAT OBB evaluation, closing speed, TTC, braking overrides, event logging |
| `test_pedestrian_engine_integration.py` | 6 | Passed | Single clock stepping, pre-tick rollback snapshot, reset restoration, tick results |
| `test_pedestrian_scenarios.py` | 4 | Passed | Scenario validation, builder assembly, execution of 4 scenario templates |
| **Existing Regression Test Suite (Phases 2–16)** | **808** | **Passed** | **Zero regressions across all prior modules** |
| **Total Test Suite** | **853** | **Passed** | **100% passing across the entire repository** |

### 5.2 Code Quality & Coverage Verification
- **Ruff Linting:** 0 errors (`All checks passed!`).
- **Django Checks:** `System check identified no issues (0 silenced).`
- **Pytest:** `853 passed in 6.26s`.
- **Code Coverage:** **96% line coverage** across `backend/apps/core` (exceeds the 80% CI requirement).

---

## 6. Execution Evidence

### 6.1 Ruff Lint Output
```text
$ .venv\Scripts\ruff check backend
All checks passed!
```

### 6.2 Django System Check Output
```text
$ .venv\Scripts\python backend/manage.py check
System check identified no issues (0 silenced).
```

### 6.3 Pytest Output
```text
$ pytest --cov=backend/apps/core --cov-report=term-missing --cov-fail-under=80
...
TOTAL                                                                   14589    609    96%
============================= 853 passed in 6.26s =============================
```

---

## 7. CI Pipeline Acceptance Gate

- **GitHub Actions Authoritative Acceptance:** Verified 100% green run on `main`.
- **Verified CI Run URL:** [https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39497881408](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39497881408)
- **Git Commit SHA:** [`ed45049`](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/commit/ed45049)
- **CI Jobs Breakdown:**
  1. `Frontend Lint, Typecheck & Build`: **Success** (5s, ID 118887543688)
  2. `Repository Hygiene & Documentation Integrity`: **Success** (5s, ID 118887544120) — verified all 27 mandatory documents and zero secret leaks.
  3. `Backend Lint, Test & Coverage`: **Success** (40s, ID 118887544419) — `ruff check backend` passed with 0 errors, `python backend/manage.py check` identified 0 issues, and `pytest` passed **853/853 tests** in 10.64s with **95.83% (96%) line coverage**.

---

## 8. Educational Simulation Disclaimer

This simulation platform is developed solely for educational and research purposes. It is **NOT** certified or validated for safety-critical real-world autonomous vehicle control.

---

## 9. Next Phase Transition: Phase 18

With Phase 17 complete and verified, the next phase in the agreed roadmap is:
- **Phase 18: Emergency Vehicle Priority**
  - Scope: Emergency vehicle types (Ambulance, Fire, Police), emergency beacons, priority yielding policies, and dynamic emergency corridor creation.
