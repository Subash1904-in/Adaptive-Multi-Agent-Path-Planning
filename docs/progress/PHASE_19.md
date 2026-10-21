# Phase 19 Engineering Progress Report: Pluggable AI Decision Policies for Autonomous Vehicle Agents

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Repository:** [Subash1904-in/Adaptive-Multi-Agent-Path-Planning](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  
**Date:** 2026-10-21  
**Baseline Git Commit:** `d9c325d` (Phase 18 completion commit)  
**Branch:** `main`  
**Phase Status:** COMPLETED  

---

## 1. Executive Summary & Phase Objective

Phase 19 delivers a modular, typed, pluggable AI decision policy subsystem for autonomous vehicle agents within the AMAPP platform. It establishes a clean separation of concerns between route generation (Phase 7/8 Dijkstra/A* planners), local observation and belief stores (Phase 13 V2V coordination), and decision-making policy evaluation.

Key capabilities delivered in Phase 19:
1. **Typed Pluggable Policy Protocol (`DecisionPolicy`)**:
   - Defines a standard `evaluate(context: DecisionContext, candidates: Sequence[CandidateRoute]) -> DecisionResult` protocol.
   - Allows seamless substitution of alternate policy heuristics without altering simulation engine lifecycle or routing algorithms.
2. **Deterministic Baseline Policy (`RuleBasedDecisionPolicy`)**:
   - Implements multi-objective candidate scoring with strict constraint ordering.
   - Preserves complete repeatability: identical inputs produce bit-identical decisions.
3. **Multi-Objective Candidate Scoring**:
   - Evaluates candidate quality across travel time, local congestion beliefs, hazard costs, observation confidence, and route stability hysteresis:
     $$S(c) = -w_t \cdot T_{\text{norm}}(c) - w_g \cdot G_{\text{norm}}(c) - w_h \cdot H_{\text{norm}}(c) + w_c \cdot C(c) + w_r \cdot R(c)$$
   - Deterministic 4-tier tie-breaking: `(-raw_score, -confidence, travel_time_s, candidate_id)`.
4. **Hard Safety Constraints Precedence**:
   - Evaluates hard constraints prior to scoring: impassable road closures, active emergency corridor reservations (Phase 18), and structural connectivity.
   - Hard constraint violations yield $S(c) = -\infty$ and can never be accepted, irrespective of travel time advantages.
5. **Bounded Observation Confidence & Deferral**:
   - Confidence bounded strictly in $[0.0, 1.0]$.
   - Candidates supported by stale observations or low-confidence beliefs trigger `DEFER` outcomes with documented fallbacks.
6. **Route Flapping Prevention & Stability Hysteresis**:
   - Incorporates route stability bonus $R(c) = 1.0$ for the currently active route and requires alternative candidates to exceed `min_score_improvement` threshold to trigger acceptance.
7. **Explicit Taxonomy of Decision Outcomes & Reason Codes**:
   - Outcomes: `ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE`.
   - Comprehensive reason taxonomy via `DecisionReasonCode`.
8. **Decentralized Local Knowledge Isolation**:
   - Context is constructed strictly from the agent's own `VehicleKnowledgeStore`.
   - Guarantees zero cross-vehicle private state leakage or global state access.
9. **SimulationEngine Single-Clock Integration & Atomic Rollback**:
   - Evaluates policies within `DynamicRouteAdapter.evaluate_agent()`.
   - Records structured `DecisionRecord` events and telemetry metrics.
   - Pre-tick snapshot capture and atomic rollback on tick execution failure.
10. **Automated Testing & Full Regression Verification**:
    - Adds 43 new unit and integration tests across 6 dedicated test modules.
    - Achieves **956 total passed tests** with **96% line coverage** across `backend/apps/core`, zero regressions against Phase 2–18 suites.

> **Educational Simulation Disclaimer:** This simulation platform is developed solely for educational, academic, and research purposes in multi-agent coordination. It is NOT certified, verified, or suitable for deployment in physical autonomous vehicles.

---

## 2. Baseline State & Starting Repository Context

- **Baseline Commit:** `d9c325d` (Phase 18 completed).
- **Starting Test Suite:** 913 passing tests, 0 failures, 96% line coverage on `backend/apps/core`.
- **Working Tree:** Verified clean prior to Phase 19 implementation.
- **Architectural Scope Boundaries:** No reinforcement learning or neural network training (reserved for future phases), no frontend dashboards.

---

## 3. Subsystem Architecture & Implementation Details

### 3.1 Decision Domain Models (`backend/apps/core/decision/models.py`)
- `DecisionOutcome`: Enum (`ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE`).
- `DecisionReasonCode`: Typed reason taxonomy (`FASTEST_FEASIBLE_ROUTE`, `HARD_CONSTRAINT_VIOLATION`, `EMERGENCY_CORRIDOR_CONFLICT`, `LOW_CONFIDENCE`, `INSUFFICIENT_IMPROVEMENT`, `CURRENT_ROUTE_CLOSED`, `NO_FEASIBLE_CANDIDATE`, `STALE_OBSERVATION`, `EMPTY_CANDIDATES`, `FALLBACK_RETAIN_CURRENT`).
- `CandidateRoute`: Immutable dataclass capturing candidate trajectory, timing, congestion, hazard costs, confidence, and current route indicator.
- `CandidateScore`: Structured scoring result preserving normalized components, raw score, confidence, stability bonus, and violation reason. Allows `-inf` raw score when `hard_constraint_violated=True`.
- `DecisionContext`: Agent-isolated snapshot capturing vehicle state, destination, known closed edges, emergency corridors, local congestion, and confidence.
- `DecisionResult`: Policy evaluation verdict including selected candidate, scores map, outcome, and audit reason code.
- `DecisionRecord`: Serialized telemetry event for replay and analysis.

### 3.2 Validated Configuration (`backend/apps/core/decision/config.py`)
- `DecisionConfig`: Dataclass governing weights ($w_t=1.0, w_g=0.5, w_h=0.8, w_c=0.4, w_r=0.2$), normalization bounds ($T_{\text{norm}}=300\text{s}, G_{\text{norm}}=100, H_{\text{norm}}=100$), confidence threshold ($0.40$), hysteresis improvement ($0.05$), and telemetry logging flags. Enforces strict numeric validation.

### 3.3 Feature Extraction & Normalization (`backend/apps/core/decision/features.py`)
- `normalize_travel_time()`: Clamps $[0, \text{max\_travel\_time\_norm\_s}]$ to $[0.0, 1.0]$.
- `normalize_congestion()`: Normalizes $[0, \text{max\_congestion\_cost\_norm}]$ to $[0.0, 1.0]$.
- `normalize_hazard()`: Normalizes $[0, \text{max\_hazard\_cost\_norm}]$ to $[0.0, 1.0]$.
- `evaluate_hard_constraints()`: Checks for empty routes, disconnected transitions, closed edges, and active emergency corridor overlaps.
- `compute_stability_bonus()`: Awards $1.0$ if candidate is the currently active route, otherwise $0.0$.

### 3.4 Multi-Objective Scoring & Tie-Breaking (`backend/apps/core/decision/scoring.py`)
- `CandidateScorer`: Computes normalized multi-objective score. If hard constraints are violated, returns raw score $-\infty$.
- `rank_candidates()`: Deterministic 4-tier sorting:
  1. Higher raw score (descending)
  2. Higher confidence (descending)
  3. Shorter estimated travel time (ascending)
  4. Candidate ID string lexicographical order (ascending)

### 3.5 Pluggable Policy Protocol & Baseline (`backend/apps/core/decision/policy.py`)
- `DecisionPolicy`: Python `@runtime_checkable` `Protocol`.
- `RuleBasedDecisionPolicy`: Evaluates candidates against hard constraints, checks confidence thresholds, handles route closure emergency rerouting, and enforces stability hysteresis.

### 3.6 Metrics & Telemetry (`backend/apps/core/decision/metrics.py`)
- `DecisionMetrics`: Counters for evaluated, accepted, deferred, and rejected decisions, hard constraint violations, latency tracking, and rollback state capture/restoration.

### 3.7 Manager & Routing Adapter Integration (`backend/apps/core/decision/manager.py`, `backend/apps/core/routing/adapter.py`)
- `DecisionManager`: Central agent evaluation coordinator, maintaining decision audit records and metrics.
- `DynamicRouteAdapter`: When `decision_config.enabled` is True, evaluates planned alternative route against currently active route through `DecisionManager`. Only mutates agent route when policy returns `ACCEPT`. When disabled, preserves 100% Phase 15 baseline behavior.

### 3.8 SimulationEngine Lifecycle & Rollback (`backend/apps/core/simulation/engine.py`, `world.py`)
- `SimulationEngine.step()`: Pre-tick captures `decision_manager.capture_state()`.
- On step exception: calls `decision_manager.restore_state(snapshot)` for atomic rollback.
- Populates `TickResult.decision_metrics` and `TickResult.decision_records`.

---

## 4. Scenario Fixtures & Examples (`backend/apps/core/scenarios/examples.py`)

Added 6 deterministic scenario fixtures exercising Phase 19 policies:
1. `create_ai_decision_fastest_route_scenario()`: Vehicle chooses fastest feasible route under policy evaluation.
2. `create_ai_decision_road_closure_rejection_scenario()`: Vehicle rejects candidate traversing closed edge and reroutes.
3. `create_ai_decision_congestion_belief_preference_scenario()`: Vehicle prefers alternative route with lower locally known congestion.
4. `create_ai_decision_low_confidence_deferral_scenario()`: Decision deferred when candidate confidence is below threshold.
5. `create_ai_decision_route_stability_hysteresis_scenario()`: Marginally faster candidate is rejected to preserve route stability.
6. `create_ai_decision_emergency_corridor_rejection_scenario()`: Non-emergency vehicle rejects route traversing active emergency corridor.

---

## 5. Automated Testing & Verification

### 5.1 Test Suites Created
- `backend/apps/core/tests/test_decision_models_and_config.py` (11 tests): Dataclass validation, config bounds, serialization, immutability.
- `backend/apps/core/tests/test_decision_features_and_scoring.py` (6 tests): Feature normalization, scoring terms, hard constraints, 4-tier tie-breaking.
- `backend/apps/core/tests/test_decision_policy_outcomes.py` (8 tests): `ACCEPT`, `REJECT`, `DEFER`, `REEVALUATE` outcomes, stability hysteresis, reason codes.
- `backend/apps/core/tests/test_decision_adapter_integration.py` (4 tests): Integration with `DynamicRouteAdapter`, local knowledge isolation, backward compatibility.
- `backend/apps/core/tests/test_decision_engine_and_rollback.py` (4 tests): `SimulationEngine.step()` telemetry, atomic rollback, deterministic replay, world reset.
- `backend/apps/core/tests/test_decision_scenarios.py` (10 tests): Scenario validation, builder injection, and execution across all 6 fixtures.

### 5.2 Verification Results
- **Pytest Suite:** 956 passed in 9.51s (100% pass rate).
- **Line Coverage:** 95.72% on `backend/apps/core` (exceeding enforced 80% threshold).
- **Ruff Linter:** `ruff check backend` $\to$ All checks passed (0 errors, 0 warnings).
- **Django Checks:** `python backend/manage.py check` $\to$ 0 issues identified.

---

## 6. Files Created and Modified

### Created Files
- `backend/apps/core/decision/__init__.py`
- `backend/apps/core/decision/config.py`
- `backend/apps/core/decision/exceptions.py`
- `backend/apps/core/decision/features.py`
- `backend/apps/core/decision/manager.py`
- `backend/apps/core/decision/metrics.py`
- `backend/apps/core/decision/models.py`
- `backend/apps/core/decision/policy.py`
- `backend/apps/core/decision/scoring.py`
- `backend/apps/core/tests/test_decision_adapter_integration.py`
- `backend/apps/core/tests/test_decision_engine_and_rollback.py`
- `backend/apps/core/tests/test_decision_features_and_scoring.py`
- `backend/apps/core/tests/test_decision_models_and_config.py`
- `backend/apps/core/tests/test_decision_policy_outcomes.py`
- `backend/apps/core/tests/test_decision_scenarios.py`
- `docs/progress/PHASE_19.md`

### Modified Files
- `backend/apps/core/routing/adapter.py`
- `backend/apps/core/scenarios/builder.py`
- `backend/apps/core/scenarios/examples.py`
- `backend/apps/core/scenarios/models.py`
- `backend/apps/core/scenarios/validation.py`
- `backend/apps/core/simulation/engine.py`
- `backend/apps/core/simulation/models.py`
- `backend/apps/core/simulation/world.py`
- `.github/workflows/ci.yml`
- `PROJECT_STATUS.md`
- `ARCHITECTURE.md`
- `REQUIREMENTS_TRACEABILITY.md`
- `README.md`
- `docs/TESTING.md`

---

## 7. Phase 20 Handoff Instructions

Phase 19 is fully verified and complete. The codebase is prepared for Phase 20.
- Next Phase: **Phase 20 — Backend Integration Expansion, Scenario Runner Enhancements, and Advanced Telemetry Streams**.
- Prerequisites for Phase 20: Maintain the single-clock stepping architecture, zero regressions across all 956 tests, and the $\ge 80\%$ test coverage requirement.
