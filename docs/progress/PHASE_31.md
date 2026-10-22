# Phase 31 — Reproducible Routing Benchmarking Framework

## 1. Phase Objective & Acceptance Checklist

The objective of Phase 31 is to design, implement, and verify a reproducible benchmarking framework that systematically evaluates and compares route-planning algorithms across standardized autonomous-vehicle simulation scenarios.

### Acceptance Checklist
- [x] **Verified Algorithm Inventory:** Inspected and validated real routing algorithm implementations (`dijkstra`, `astar`, `static`, `adaptive`) and created an extensible un-implemented placeholder (`learned`) for future RL policies (Phases 32–34).
- [x] **Common Benchmark Adapter Protocol:** Implemented `BaseRoutingBenchmarkAdapter` and concrete adapters with explicit parameters, metadata, and scenario configuration methods without duplicating core routing logic.
- [x] **Extensible Algorithm Registry:** Implemented `AlgorithmRegistry` providing registration, listing, and strict validation (raising `UnsupportedAlgorithmError` with available suggestions).
- [x] **Standardized Benchmark Scenario Suite:** Created 8 standardized scenarios with stable IDs, explicit seeds, and clean factory methods (`bench_grid_sparse_3x3`, `bench_urban_medium_4x4`, `bench_dense_corridor_5x5`, `bench_incident_closure`, `bench_incident_congestion`, `bench_infeasible_barrier`, `bench_emergency_corridor`, `bench_v2v_degradation`).
- [x] **Strict Seed & State Isolation:** Implemented `SeedPolicy` deriving deterministic seeds for each trial. State isolation ensures scenarios, graphs, vehicle states, route caches, and telemetry are created freshly per trial with zero cross-contamination.
- [x] **Honest Failure & Infeasibility Handling:** Infeasible routes and partitioned destinations (e.g. `bench_infeasible_barrier`) are explicitly classified as `infeasible` and are strictly excluded from successful route cost and travel time samples (never treated as artificial zero-cost successes).
- [x] **Authoritative Metrics Collection:** Integrated directly with the simulation engine and `MetricsAggregator` to capture route feasibility, length, objective cost, planning wall-clock duration, simulation travel time, trip completion rates, safety collisions/near-misses, intersection crossings, reroutes, and V2V PDR.
- [x] **Reproducible JSON & CSV Exports:** Implemented `BenchmarkExporter` producing valid RFC 8259 JSON, stable-column `trials.csv` and `summary.csv`, and Markdown reports with path traversal security defense.
- [x] **Django CLI Management Command:** Implemented `python backend/manage.py run_benchmark` with `--algorithms`, `--scenarios`, `--trials`, `--seed`, `--export-dir`, `--smoke`, `--list-algorithms`, and `--list-scenarios`.
- [x] **Deterministic Automated Testing:** Implemented comprehensive unit and integration tests (`test_benchmarking.py`) verifying adapters, cost parity between Dijkstra and A*, seed determinism, trial isolation, aggregation math, export round-tripping, path traversal rejection, and CLI execution.
- [x] **CI Pipeline Preservation & Evolution:** Updated `.github/workflows/ci.yml` to include `PHASE_31.md` in repository hygiene checks and integrated an automated benchmark smoke verification step into the backend test job.
- [x] **Strict Scope Discipline:** Did not implement Gymnasium environments or reinforcement learning models (strictly reserved for Phases 32–34).

---

## 2. Starting Repository State

- **Starting Branch:** `main`
- **Base Commit SHA:** `5dcbaed030a4953280d3bc9c57c4844cc531d74a` (Phase 30 documentation commit following implementation commit `c2cee96`)
- **Working Tree State:** Clean
- **Verified Algorithm Implementations:**
  - `dijkstra`: Real uniform-cost search in `backend/apps/core/routing/dijkstra.py`
  - `astar`: Real heuristic search in `backend/apps/core/routing/astar.py`
  - `static`: Fixed route execution via `AdaptiveRoutingConfig(enabled=False)`
  - `adaptive`: Real-time adaptive dynamic rerouting via `AdaptiveRoutingConfig(enabled=True)` and `AdaptiveRoutingPlannerAdapter` in `backend/apps/core/routing/adapter.py`
  - `learned`: Not implemented; stubbed with clear `is_implemented=False` and explicit `UnsupportedAlgorithmError` explaining Phase 32–34 scheduling.

---

## 3. Algorithm Inventory & Common Adapter Contract

### Registered Benchmark Algorithms

| Algorithm ID | Display Name | Version | Adaptive | Implemented | Technical Description |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `dijkstra` | Dijkstra Baseline | 1.0.0 | No | Yes | Uniform-cost priority queue search computing optimal paths without heuristics. |
| `astar` | A* Heuristic Baseline | 1.0.0 | No | Yes | Heuristic-guided search utilizing Euclidean distance lower bounds. |
| `static` | Static Fixed Route | 1.0.0 | No | Yes | Fixed pre-planned routing following original trajectory without dynamic adaptation. |
| `adaptive` | Adaptive Dynamic Rerouting | 1.0.0 | Yes | Yes | Decentralized adaptive route adjustment responding to closures, congestion, and hazards. |
| `learned` | Learned RL Policy (Future Extension) | 1.0.0 | Yes | No | Reinforcement learning policy extension point scheduled for Phases 32–34. |

### Common Adapter Protocol (`BaseRoutingBenchmarkAdapter`)
```python
class BaseRoutingBenchmarkAdapter(ABC):
    @property
    @abstractmethod
    def algorithm_id(self) -> str: ...
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def version(self) -> str: ...
    @property
    @abstractmethod
    def description(self) -> str: ...
    @property
    @abstractmethod
    def is_adaptive(self) -> bool: ...
    @property
    @abstractmethod
    def is_implemented(self) -> bool: ...
    @abstractmethod
    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]: ...
    @abstractmethod
    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition: ...
```

---

## 4. Standardized Scenario Suite

The framework registers 8 standardized scenarios covering diverse operational conditions:

1. `bench_grid_sparse_3x3` (v1.0.0): Single vehicle traversing diagonal path across a 3x3 grid (baseline comparison).
2. `bench_urban_medium_4x4` (v1.0.0): 4 vehicles with intersecting trajectories on a 4x4 grid testing multi-agent coordination.
3. `bench_dense_corridor_5x5` (v1.0.0): 8 vehicles with active traffic signals on a 5x5 network under high vehicle density.
4. `bench_incident_closure` (v1.0.0): Vehicle forced to dynamically detour around a closed road segment.
5. `bench_incident_congestion` (v1.0.0): Vehicles traversing parallel corridors under congestion simulation.
6. `bench_infeasible_barrier` (v1.0.0): Destination node completely partitioned by closures, verifying honest infeasibility handling.
7. `bench_emergency_corridor` (v1.0.0): High-priority emergency vehicle navigating among civilian traffic.
8. `bench_v2v_degradation` (v1.0.0): 3 vehicles communicating under spatial range limits and 15% packet loss probability.

---

## 5. Seed Policy & Reproducibility Guarantees

- **SeedPolicy:** Derives trial seeds using formula `(base_seed + trial_index * 1000) % 2147483647`.
- **State Isolation:** Every trial calls `scenario_def.create_scenario(seed=seed)`, building an entirely fresh `ScenarioDefinition`, `RoadGraph`, `WorldState`, and `SimulationEngine`.
- **Order Invariance:** Executing scenarios in any arbitrary order produces identical scenario inputs and deterministic outcomes for identical seeds.
- **Timing Variance Caveat:** Planning duration measures real CPU wall-clock time (`time.perf_counter()`) and may vary slightly across runs and hardware. Simulation travel time and route costs are 100% deterministic.

---

## 6. Actual Measured Benchmark Results

Executed real end-to-end benchmark suite comparing all 4 active algorithms across scenarios:

```
# AMAPP Routing Benchmark Report - bench_8727bb34

## 1. Execution Provenance & Environment
- Run ID: bench_8727bb34
- Git Commit SHA: 5dcbaed030a4953280d3bc9c57c4844cc531d74a
- Base Seed: 42
- Trials per (Scenario, Algorithm) Pair: 1
- Platform: Windows-10-10.0.26300-SP0
- Python Version: 3.11.9

## 2. Aggregated Comparison Matrix

| Scenario | Algorithm | Trials (Succ/Fail/Inf) | Feasibility % | Mean Cost | Mean Length (m) | Mean Plan (ms) | Mean Travel (s) | Collisions | PDR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `bench_grid_sparse_3x3` | `dijkstra` | 1 (1/0/0) | 100.0% | 20.00 | 200.0 | 0.06 | 21.70 | 0 | 0.00% |
| `bench_grid_sparse_3x3` | `astar` | 1 (1/0/0) | 100.0% | 20.00 | 200.0 | 0.07 | 21.70 | 0 | 0.00% |
| `bench_grid_sparse_3x3` | `static` | 1 (1/0/0) | 100.0% | 20.00 | 200.0 | 0.06 | 21.70 | 0 | 0.00% |
| `bench_grid_sparse_3x3` | `adaptive` | 1 (1/0/0) | 100.0% | 20.00 | 200.0 | 0.06 | 21.70 | 0 | 0.00% |
| `bench_incident_closure` | `dijkstra` | 1 (1/0/0) | 100.0% | 20.83 | 250.0 | 0.05 | 22.90 | 0 | 100.00% |
| `bench_incident_closure` | `astar` | 1 (1/0/0) | 100.0% | 20.83 | 250.0 | 0.06 | 22.90 | 0 | 100.00% |
| `bench_incident_closure` | `static` | 1 (1/0/0) | 100.0% | 20.83 | 250.0 | 0.06 | 22.90 | 0 | 100.00% |
| `bench_incident_closure` | `adaptive` | 1 (1/0/0) | 100.0% | 20.83 | 250.0 | 0.06 | 14.50 | 0 | 100.00% |
```

### Infeasible Partition Scenario Verification:
```
| Scenario | Algorithm | Trials (Succ/Fail/Inf) | Feasibility % | Mean Cost | Mean Length (m) | Mean Plan (ms) | Mean Travel (s) | Collisions | PDR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `bench_infeasible_barrier` | `astar` | 1 (0/0/1) | 0.0% | N/A | N/A | 0.07 | N/A | 0 | 100.00% |
```

---

## 7. Files Created, Modified, and Removed

### Created Files
- `backend/apps/core/benchmarking/__init__.py`: Package entry point exporting all models, adapters, registries, runner, and exporter.
- `backend/apps/core/benchmarking/exceptions.py`: Domain exceptions (`BenchmarkError`, `UnsupportedAlgorithmError`, `UnsupportedScenarioError`, `BenchmarkExecutionError`, `BenchmarkExportError`).
- `backend/apps/core/benchmarking/models.py`: Authoritative data classes (`BenchmarkStatus`, `SeedPolicy`, `BenchmarkTrialResult`, `BenchmarkAggregateResult`, `BenchmarkRunReport`).
- `backend/apps/core/benchmarking/adapters.py`: Adapter abstraction and concrete adapters for Dijkstra, A*, Static, Adaptive, and Learned policies, plus `AlgorithmRegistry`.
- `backend/apps/core/benchmarking/scenarios.py`: Standardized scenario definitions and `BenchmarkScenarioRegistry`.
- `backend/apps/core/benchmarking/runner.py`: Execution orchestrator managing trials, state isolation, and statistical aggregation.
- `backend/apps/core/benchmarking/export.py`: JSON, CSV (`trials.csv`, `summary.csv`), and Markdown report serializer with directory traversal security validation.
- `backend/apps/core/management/__init__.py`: Django management package marker.
- `backend/apps/core/management/commands/__init__.py`: Management commands package marker.
- `backend/apps/core/management/commands/run_benchmark.py`: Django CLI command (`run_benchmark`).
- `backend/apps/core/tests/test_benchmarking.py`: Comprehensive test suite (26 unit/integration tests).
- `docs/progress/PHASE_31.md`: Authoritative progress tracking and verification report.

### Modified Files
- `.github/workflows/ci.yml`: Added `docs/progress/PHASE_31.md` to mandatory file checks and added `python backend/manage.py run_benchmark --smoke` verification step.
- `PROJECT_STATUS.md`: Marked Phase 31 COMPLETED and Phase 32 PENDING.
- `ARCHITECTURE.md`: Added Section 27 documenting the Benchmarking Framework architecture, adapters, scenario registry, seed management, and export schema.
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-05 (Benchmarking & Routing Comparison) from PARTIALLY_TESTED to TESTED.
- `README.md`: Added benchmarking CLI documentation, supported algorithm matrix, standardized scenario catalog, and export instructions.
- `docs/TESTING.md`: Documented benchmarking automated tests, cost parity validation, seed determinism tests, and CLI execution.

---

## 8. Test Totals, Coverage & Quality Results

- **Backend Pytest Suite:** **1144 passed** in 27.68s
- **Backend Code Coverage:** **95.40%** (minimum threshold: 80.0%)
- **Backend Linting:** `ruff check backend` passed with 0 errors
- **Django System Checks:** `python backend/manage.py check` passed with 0 issues
- **Frontend Unit Tests:** **192 passed** across 11 test files
- **Frontend Linting:** `eslint .` passed with 0 errors/warnings
- **TypeScript Strict Typecheck:** `tsc --noEmit` passed with 0 errors
- **Frontend Production Build:** Vite build passed (`dist/` generated cleanly in 1.95s)

---

## 9. GitHub Actions CI Verification

- **Commit SHA:** `bfc00f6df2f515350c1bb2d451d4e7463a040efd`
- **Workflow Run URL:** [https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39706381184](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39706381184)
- **Job Outcomes:**
  - `repo-hygiene` (ID `119587272949`, duration 5s): SUCCESS
    - Verified all mandatory files including `docs/progress/PHASE_31.md`
    - Scanned for secret leaks / prohibited artifacts (0 detected)
  - `backend-quality` (ID `119587272712`, duration 1m6s): SUCCESS
    - Verified Python 3.11.17, Django 5.1.4, DRF 3.15.2, Channels 4.2.0, Daphne 4.1.2, NetworkX 3.4.2, OSMnx 2.0.1, Pytest 8.3.4
    - Ruff linting passed with 0 errors
    - Django system check passed with 0 issues
    - Backend pytest suite: 1,144 passed with 95.40% code coverage (exceeding 80% threshold)
    - Reproducible Routing Benchmark Smoke Verification passed: `python backend/manage.py run_benchmark --smoke` executed cleanly
  - `frontend-quality` (ID `119587272955`, duration 29s): SUCCESS
    - Node.js 22.x, reproducible `npm ci`
    - ESLint passed with 0 errors/warnings
    - TypeScript strict typecheck (`tsc --noEmit`) passed with 0 errors
    - Vitest unit tests: 192 passed across 11 test suites
    - Vite production bundle build passed cleanly

---

## 10. Phase 32 Handoff Instructions

Phase 31 is complete. Do NOT begin Phase 32 implementation prematurely.
When Phase 32 is authorized:
1. Review `ARCHITECTURE.md` and `PROJECT_STATUS.md` for Phase 32 scope (Gymnasium-Compatible Single/Multi-Agent RL Environment).
2. Use the benchmarking framework (`AlgorithmRegistry`, `BenchmarkScenarioRegistry`, `BenchmarkRunner`) as the evaluation baseline for future learned policies developed in Phases 32–34.
3. Keep the common adapter interface (`BaseRoutingBenchmarkAdapter`) as the integration contract for connecting RL agents to the AMAPP benchmark suite.
