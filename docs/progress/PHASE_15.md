# Phase 15 Engineering Progress Report: Adaptive Rerouting and Dynamic Route Adjustment

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Date:** 2026-10-21  
**Baseline Git Commit:** `3f8d622` (Phase 14 verified CI run and job details)  
**Branch:** `main`  
**Phase Status:** COMPLETED  

---

## 1. Executive Summary & Phase Objective

Phase 15 introduces decentralized adaptive rerouting and dynamic route adjustment into the AMAPP simulation platform. Prior to Phase 15, vehicle agents followed static routes planned at scenario initialization without adapting to changing traffic conditions or incidents communicated over the V2V coordination network.

In Phase 15, we developed and verified:
1. **Vehicle-Specific Dynamic Edge Costs (`DynamicEdgeCostEvaluator`)**: Combines immutable baseline road graph travel costs with a vehicle's private traffic beliefs (congestion multipliers, hazard penalties, and closed road avoidance).
2. **Decoupled Adaptive Routing Policy (`DynamicRouteAdapter`)**: Evaluates candidate paths and makes structured decisions without modifying underlying Dijkstra or A* algorithms or embedding policy into vehicle agents.
3. **Current-Route Evaluation with Pro-Rating**: Evaluates remaining active path cost using the identical dynamic cost model, pro-rating active edge traversal progress.
4. **Benefit Hysteresis & Cooldowns**: Enforces minimum absolute and relative improvement thresholds ($\Delta C \ge \max(\Delta C_{\min}, \rho C_{\text{current}})$), configurable cooldown periods, and belief fingerprinting to eliminate route oscillation and redundant graph searches.
5. **Safe Active-Route Replacement (`VehicleAgent.replace_remaining_route`)**: Centralized route suffix splicing with `finish_edge` continuation policy, preserving vehicle position, speed, heading, and destination target.
6. **Authoritative Simulation Engine Integration & Atomic Rollback**: Integrated into `SimulationEngine.step()` with pre-tick state capture restoring routes, cooldown timers, belief hashes, and metrics on step failure.
7. **Comprehensive Scenario Coverage**: 9 standard scenario fixtures demonstrating closure bypass, congestion diversion, hazard avoidance, benefit suppression, cooldown suppression, stale report pruning, and unreachable destination handling.
8. **Automated Testing & Strict Regression**: 51 new automated tests across 4 test suites, bringing the project total to **760 passing tests** with **95.69% line coverage** on `backend/apps/core`.

---

## 2. Baseline State & Starting Repository Context

- **Baseline Commit:** `3f8d622` (`docs(phase-14): record verified CI run URL and completed job details`).
- **Starting Test Suite:** 709 passing tests, 0 failures, 96% coverage on `backend/apps/core`.
- **Clean Working Tree:** Verified prior to Phase 15 modifications.
- **Architectural Boundary Adherence:** Zero premature implementation of collision avoidance (Phase 16) or emergency vehicle priority (Phase 18).

---

## 3. Dynamic Edge-Cost Formula, Defaults & Validation

The dynamic edge cost function is evaluated per edge $e$ by querying vehicle $v$'s local knowledge store:

$$C_v(e) = C_0(e) \cdot M_{\text{congestion}}(e) + P_{\text{hazard}}(e)$$

where:
- $C_0(e) > 0$ is the baseline graph traversal cost (travel time or distance).
- $M_{\text{congestion}}(e) \ge 1.0$ is the congestion multiplier. If a `travel_time_factor` attribute is present on the belief, it takes precedence; otherwise, qualitative congestion levels map to configured multipliers.
- $P_{\text{hazard}}(e) \ge 0.0$ is the additive penalty for mapped hazards affecting edge $e$.
- **Road Closures**: If a valid, non-expired closure belief exists, $C_v(e) = \infty$, rendering the edge impassable to shortest-path planners.

### Configuration Parameters (`AdaptiveRoutingConfig`)

| Parameter | Type | Default | Validation Constraint | Description |
|---|---|---|---|---|
| `enabled` | `bool` | `False` | Must be boolean | Master switch for adaptive rerouting. |
| `min_absolute_benefit` | `float` | `5.0` | $\ge 0.0$, finite | Minimum absolute cost improvement required to accept a reroute. |
| `min_relative_benefit` | `float` | `0.10` | $\ge 0.0$, finite | Minimum relative cost improvement ($\rho$) required. |
| `reroute_cooldown_s` | `float` | `5.0` | $\ge 0.0$, finite | Cooldown duration in simulation seconds after an accepted reroute. |
| `min_confidence_threshold` | `float` | `0.5` | $0.0 \le c \le 1.0$ | Minimum belief confidence required to apply cost penalties. |
| `disputed_closure_policy` | `str` | `"conservative"` | `"conservative"` or `"permissive"` | If conservative, disputed closures block the road; if permissive, road remains open. |
| `congestion_multipliers` | `dict` | `{"low": 1.0, "moderate": 1.5, "high": 2.5, "severe": 4.0}` | Multipliers $\ge 1.0$ | Travel time multipliers by qualitative congestion level. |
| `hazard_penalties` | `dict` | `{"low": 5.0, "medium": 15.0, "high": 30.0, "critical": 60.0}` | Penalties $\ge 0.0$ | Additive penalties by hazard severity. |
| `current_edge_continuation_policy` | `str` | `"finish_edge"` | `"finish_edge"` | Policy for vehicle active on an edge when route is updated. |
| `repeat_suppression` | `bool` | `True` | Must be boolean | Suppresses recalculation if local traffic knowledge has not changed. |
| `algorithm` | `RoutingAlgorithm` | `ASTAR` | `DIJKSTRA` or `ASTAR` | Pathfinding algorithm used for candidate routes. |
| `cost_mode` | `CostMode` | `TRAVEL_TIME` | `DISTANCE` or `TRAVEL_TIME` | Cost optimization mode. |

---

## 4. Architectural Implementation Details

### 4.1 Separation of Routing Policy from Route Planners
- **Planners (`DijkstraRouter`, `AStarRouter`)**: Answer reachability and shortest-path queries given an arbitrary edge cost function `edge_cost_fn: Callable[[RoadEdge, CostMode], float]`.
- **Policy (`DynamicRouteAdapter`)**: Manages agent evaluation eligibility, cooldown tracking, candidate generation, cost improvement threshold checks, and route replacement staging.
- **Vehicle Agent Independence**: `VehicleAgent` remains a pure kinematic and lifecycle controller without internal rerouting policies.

### 4.2 Vehicle-Private Routing Knowledge Isolation
- `DynamicEdgeCostEvaluator` requires a `VehicleKnowledgeStore`. All beliefs are queried strictly from this store.
- If a vehicle has not received or accepted a closure/congestion report, its evaluated cost remains baseline.
- Vehicles never query the global road graph for dynamic restrictions or access another vehicle's private knowledge.

### 4.3 Benefit Hysteresis, Cooldowns & Repeat Suppression
- **Benefit Condition**:
  $$\Delta C = C_{\text{current}} - C_{\text{candidate}} \ge \max(\Delta C_{\min}, \rho C_{\text{current}})$$
- **Cooldown Suppression**: If $t_{\text{now}} - t_{\text{last\_reroute}} < \Delta t_{\text{cooldown}}$, returns `COOLDOWN_ACTIVE`.
- **Belief Fingerprinting**: MD5 hash of sorted active beliefs `(target_id, belief_type, status, confidence, attributes)` combined with `current_edge_index`. If identical to the previous evaluation, redundant graph searches are suppressed with `INSUFFICIENT_BENEFIT`.

### 4.4 Safe Active-Route Suffix Replacement
`VehicleAgent.replace_remaining_route(candidate_route, resume_node_id, new_route_id)`:
- Validates vehicle state: vehicle must not be in `ARRIVED` state.
- Validates candidate connectivity: candidate must start at `resume_node_id` and terminate at vehicle's target node.
- If vehicle is actively traversing an edge (`distance_along_segment_m > 0`), the active edge is completed toward `resume_node_id`, and the candidate suffix is seamlessly appended.
- If vehicle has not yet begun moving (`current_edge_index == 0` and `distance == 0.0`), route replacement begins directly from origin.
- Physical coordinates $(x, y)$, heading $\theta$, speed $v$, and acceleration $a$ remain unaltered.

### 4.5 Simulation Engine Integration & Atomic Rollback
Integrated into `SimulationEngine.step()` sequence:
1. **Pre-Tick Capture**: Snapshots agent routes, segment lists, total distance, adapter cooldown timestamps, belief fingerprints, and metrics.
2. **Network Delivery**: Advances V2V packet queues.
3. **Coordination**: Ingests received reports into private knowledge stores.
4. **Adaptive Routing Step**: Evaluates vehicles in deterministic sorted `vehicle_id` order. Accepted reroutes update vehicle route suffixes.
5. **Kinematic Stepping**: Advances vehicle positions along updated routes.
6. **Tick Result Commit**: Emits `routing_decisions` and `routing_metrics` in `TickResult`.
7. **Rollback on Error**: Any kinematic or signal failure restores routes, segments, cooldown state, and metrics to pre-tick values.

---

## 5. Routing Metrics & Telemetry

`AdaptiveRoutingMetrics` tracks deterministic, inspectable simulation counters:
- `evaluations`: Total agent rerouting evaluations performed.
- `candidate_routes_computed`: Total candidate path searches executed.
- `reroutes_accepted`: Total route replacements committed.
- `reroutes_rejected`: Total evaluations resulting in rejection or no change.
- `cooldown_suppressions`: Evaluations suppressed by active cooldown.
- `insufficient_benefit_suppressions`: Evaluations where candidate improvement failed hysteresis threshold.
- `no_route_outcomes`: Instances where destination was unreachable under current closures.
- `closure_restrictions_applied`: Edges blocked due to active closure beliefs.
- `congestion_multipliers_applied`: Congestion multiplier evaluations.
- `hazard_penalties_applied`: Hazard penalties added to edge costs.
- `route_changes_by_vehicle`: Per-vehicle breakdown of accepted reroutes.
- `total_cost_savings`: Cumulative difference between pre-reroute and post-reroute remaining path costs.

---

## 6. Scenario Configurations & Deterministic Scenario Fixtures

Nine standard Phase 15 scenario factories were implemented in `apps.core.scenarios.examples`:
1. `create_adaptive_reroute_closure_scenario`: Road closure forces bypass onto viable alternative route.
2. `create_adaptive_reroute_congestion_scenario`: Severe congestion diverts vehicle to parallel corridor.
3. `create_adaptive_reroute_hazard_scenario`: Additive hazard penalty exceeds threshold, triggering reroute.
4. `create_adaptive_reroute_insufficient_benefit_scenario`: Minor delay rejected due to benefit hysteresis.
5. `create_adaptive_reroute_cooldown_scenario`: Subsequent recalculation suppressed during active cooldown.
6. `create_adaptive_reroute_stale_report_scenario`: Expired closure beliefs do not permanently restrict edges.
7. `create_adaptive_reroute_no_alternative_scenario`: Isolated destination yields explicit `NO_ALTERNATIVE_ROUTE`.
8. `create_adaptive_reroute_current_edge_continuation_scenario`: Vehicle finishes active edge before following new suffix.
9. `create_adaptive_reroute_delayed_network_scenario`: Network latency delays closure until after TTL expires.

---

## 7. Verification & Test Evidence

### Test Summary
- **Test Command:** `pytest backend/apps/core/tests/ -v --cov=backend/apps/core --cov-fail-under=80`
- **Total Tests Passing:** **760 passed in 5.50s** (0 failures, 0 errors, 0 skipped).
- **Line Coverage:** **95.69%** (enforced minimum threshold $\ge 80\%$).

### Test Suite Breakdown
| Test Suite File | Tests | Coverage | Scope / Focus |
|---|---|---|---|
| `test_routing_dynamic_costs.py` | 17 | 100% | Baseline cost immutability, congestion multipliers, closure blocks, reopening, hazard mapping, stale/expired beliefs, disputed policy, vehicle isolation, remaining route pro-rating. |
| `test_routing_adaptive_policy.py` | 13 | 100% | Reroute acceptance, no alternative, congestion triggers, absolute/relative hysteresis, cooldown suppression, repeat suppression, expired closures, deterministic agent ordering, state capture/restore. |
| `test_routing_replacement.py` | 7 | 100% | Safe suffix replacement, kinematic preservation (position, speed, heading), resume node matching, destination validation, arrived vehicle rejection, origin replacement, segment history. |
| `test_routing_engine_integration.py` | 14 | 100% | Engine step decisions and metrics, private knowledge isolation, kinematics failure rollback, world reset restoration, deterministic replay, 9 scenario fixture executions. |
| Regression Suites (Phases 2–14) | 709 | 96% | Domain models, road graph, OSM, kinematics, signals, clock, scenarios, communication, coordination, degradation. |
| **Total** | **760** | **95.69%** | Full AMAPP regression suite. |

---

## 8. Files Created & Modified

### Created Files
- `backend/apps/core/routing/evaluator.py`: Dynamic edge cost evaluator and pro-rating logic.
- `backend/apps/core/routing/adapter.py`: Dynamic route adapter, hysteresis policy, cooldown tracking, and belief fingerprinting.
- `backend/apps/core/routing/metrics.py`: Adaptive routing telemetry and metrics container.
- `backend/apps/core/tests/test_routing_dynamic_costs.py`: Tests for dynamic costs, closures, hazards, and vehicle isolation.
- `backend/apps/core/tests/test_routing_adaptive_policy.py`: Tests for benefit thresholds, cooldowns, and repeat suppression.
- `backend/apps/core/tests/test_routing_replacement.py`: Tests for safe active route suffix replacement.
- `backend/apps/core/tests/test_routing_engine_integration.py`: Tests for simulation engine integration, rollback, and scenarios.
- `docs/progress/PHASE_15.md`: This comprehensive engineering report.

### Modified Files
- `backend/apps/core/routing/models.py`: Added `RerouteDecisionType`, `RerouteDecision`, `AdaptiveRoutingConfig`, extended `RoutingRequest` with `edge_cost_fn`.
- `backend/apps/core/routing/exceptions.py`: Added `AdaptiveRoutingError`, `RouteReplacementError`, `InvalidReroutePolicyError`.
- `backend/apps/core/routing/dijkstra.py`: Supported dynamic `edge_cost_fn`.
- `backend/apps/core/routing/astar.py`: Supported dynamic `edge_cost_fn`.
- `backend/apps/core/routing/planner.py`: Forwarded `edge_cost_fn` to routers.
- `backend/apps/core/routing/__init__.py`: Exported new routing types and components.
- `backend/apps/core/kinematics/vehicle_agent.py`: Implemented `replace_remaining_route()`.
- `backend/apps/core/simulation/models.py`: Extended `TickResult` with `routing_decisions` and `routing_metrics`.
- `backend/apps/core/simulation/world.py`: Integrated `adaptive_routing_config` and `adaptive_routing_adapter`.
- `backend/apps/core/simulation/engine.py`: Integrated adaptive routing evaluation and pre-tick rollback snapshotting.
- `backend/apps/core/scenarios/models.py`: Added `adaptive_routing_config` to `ScenarioDefinition`.
- `backend/apps/core/scenarios/validation.py`: Added validation for adaptive routing configuration.
- `backend/apps/core/scenarios/builder.py`: Wired adaptive routing configuration into `WorldState`.
- `backend/apps/core/scenarios/examples.py`: Added 9 Phase 15 scenario factories.
- `backend/apps/core/scenarios/__init__.py`: Exported new scenario factories.
- `.github/workflows/ci.yml`: Updated CI verification for Phase 15 artifacts and test suites.
- `PROJECT_STATUS.md`: Updated current phase status and test totals.
- `ARCHITECTURE.md`: Added Section 11 documenting adaptive rerouting architecture.
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-07 status and notes.
- `README.md`: Added Section 6.17 describing adaptive rerouting with code example.
- `docs/TESTING.md`: Documented Phase 15 test suites and coverage.

---

## 9. CI/CD Integration & GitHub Actions Verification

- **Workflow File:** `.github/workflows/ci.yml`
- **Authoritative Gate:** All jobs passed in GitHub Actions.
- **Commit SHA:** `3ac1174` (`feat(phase-15): implement adaptive rerouting and dynamic route adjustment`)
- **Run URL:** [https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39480605410](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39480605410)
- **Individual Job Outcomes:**
  - `Backend Lint, Test & Coverage` (Job ID: `118827843363`): **SUCCESS** (31s)
    - Python 3.11 environment verification
    - Ruff linting: 0 errors
    - Django system checks: 0 issues
    - Pytest regression suite: **760 passed in 7.82s**, **95.69% line coverage** (surpassing 80% threshold)
  - `Repository Hygiene & Documentation Integrity` (Job ID: `118827843854`): **SUCCESS** (5s)
    - Mandatory documentation and phase progress artifacts verified (`PHASE_01.md` through `PHASE_15.md`)
    - Zero prohibited binary files or secret patterns detected
  - `Frontend Lint, Typecheck & Build` (Job ID: `118827844047`): **SUCCESS** (5s)
    - Node 22.x runtime verified; clean deferred message logged until frontend packages introduced

---

## 10. Phase 16 Handoff Instructions

Phase 15 is 100% complete and verified.

### Next Phase: Phase 16 — Collision Detection and Avoidance
- **Scope:**
  - Planar geometric collision checks between vehicle bounding boxes.
  - Safe separation distance and time-to-collision (TTC) calculations.
  - Deceleration and emergency braking maneuvers.
  - Near-miss logging and safety metrics.
- **Boundary Warning:** Do not implement emergency vehicle priority (Phase 18) or reinforcement learning policies (Phase 32) in Phase 16.
