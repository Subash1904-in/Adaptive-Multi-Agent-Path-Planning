# Phase 35 — Persistence and Experiment History

## 1. Objective & Acceptance Checklist

The objective of Phase 35 is to implement a robust, transactionally isolated, deterministic persistence layer and experiment history tracking system for AMAPP (Adaptive Multi-Agent Path Planning).

This phase establishes:
1. Authoritative Django ORM data models (`SimulationRun`, `BenchmarkConfiguration`, `BenchmarkTrial`, and `ExperimentMetric`) capturing runs, benchmarks, trials, and granular time-series metrics.
2. Canonical, deterministic SHA-256 configuration fingerprinting with invariant key ordering, normalized float precision, non-finite number rejection, and strict exclusion/rejection of secrets and absolute host filesystem paths.
3. Explicit lifecycle state machine management (`CREATED`, `VALIDATING`, `READY`, `RUNNING`, `COMPLETED`, `CANCELLED`, `FAILED`, `LIMIT_REACHED`) with strict validation of legal transitions.
4. Non-blocking persistence failure containment: database errors are safely logged and isolated, never crashing running simulation executions or benchmark sweeps.
5. Zero per-tick database writes: high-frequency tick simulation writes are strictly contained in memory, persisting only summary metrics and lifecycle milestones.
6. REST API historical query endpoints under `/api/v1/` supporting limit-offset pagination (`AMAPPHistoryPagination`), structured multi-parameter filtering, and read-only protection on historical records.
7. Seamless backward compatibility: existing fixtures, in-memory simulations, and persistence-disabled modes operate without regressions.

### Acceptance Checklist
- [x] **Persistent Django Models:** Implemented `SimulationRun`, `BenchmarkConfiguration`, `BenchmarkTrial`, and `ExperimentMetric` in `backend/apps/core/models.py` with explicit constraints (`unique_benchmark_trial_identity`), indexes on `(status, created_at)` and `(configuration_fingerprint)`, and cascaded/nullified deletion semantics.
- [x] **Database Migrations:** Generated `0001_initial.py` in `backend/apps/core/migrations/` and verified with `python backend/manage.py makemigrations --check --dry-run` (0 issues).
- [x] **Deterministic Fingerprinting:** Implemented `compute_configuration_fingerprint()` in `backend/apps/core/persistence/fingerprint.py` with canonical JSON serialization, float normalization to 6 decimal places, rejection of `NaN`/`Infinity`, rejection of sensitive credential keys (`token`, `password`, `secret`, `key`), rejection of absolute paths (`/home/...`, `C:\...`), and deterministic exclusion of operational runtime fields (`run_id`, `created_at`, `timestamp`).
- [x] **Lifecycle State Machine:** Enforced state transitions (`transition_to`) across `CREATED`, `VALIDATING`, `READY`, `RUNNING`, `COMPLETED`, `CANCELLED`, `FAILED`, and `LIMIT_REACHED` in models and persistence service.
- [x] **Transaction Isolation & Failure Containment (`SimulationPersistenceService`):** Implemented in `backend/apps/core/persistence/service.py` using `transaction.atomic()`, comprehensive try/except error containment returning `PersistenceResult(success=False, error=...)`, and idempotent duplicate finalization handling.
- [x] **Benchmark Integration:** Integrated `SimulationPersistenceService` into `BenchmarkRunner.run_suite()` to automatically persist benchmark configurations, individual trials, and aggregated experiment metrics.
- [x] **REST History Endpoints & DRF Serializers:** Updated `RunListCreateView`, `RunDetailView`, and `RunMetricsView`, and added `BenchmarkConfigurationListView`, `BenchmarkConfigurationDetailView`, `BenchmarkTrialListView`, and `BenchmarkTrialDetailView` with `AMAPPHistoryPagination` (default 20, max 100) and read-only protections (`POST`/`PUT`/`DELETE` return 405 Method Not Allowed).
- [x] **Automated Test Suite:** Created 30 automated tests across 4 dedicated test modules:
  - `test_persistence_models_and_migrations.py` (8 tests)
  - `test_persistence_fingerprint.py` (8 tests)
  - `test_persistence_lifecycle_and_failures.py` (7 tests)
  - `test_api_persistence_history.py` (7 tests)
- [x] **Regression & Coverage Maintenance:** Full backend pytest suite passes with **1,247 passed, 0 failed** at **95% coverage** (exceeding the 80% CI requirement). All 192 frontend tests pass across 11 suites; ESLint, TypeScript strict typecheck, and Vite production bundle build succeed cleanly.
- [x] **Authoritative CI Evolution:** Updated `.github/workflows/ci.yml` adding `docs/progress/PHASE_35.md` to repository hygiene and adding automated migration dry-run and persistence model verification steps.

---

## 2. Starting Repository & Environment State

- **Starting Branch:** `main`
- **Initial Working Commit SHA:** `c64848616d5cd68739646fcdbf950bd8fd3f8bac`
- **Reported Phase 34 Implementation Commit:** `e028018`
- **Platform:** Windows-10-10.0.26300-SP0 (local) / Ubuntu-24.04 (GitHub Actions CI)
- **Python Version:** 3.11.9
- **Django Version:** 5.1.15
- **Django REST Framework Version:** 3.15.2
- **Database Engine:** SQLite (local development and CI execution), PostgreSQL-ready Django ORM field definitions

---

## 3. Architecture & Persistent Data Models

The persistence layer is organized under `backend/apps/core/persistence/` with models in `backend/apps/core/models.py`:

```
backend/apps/core/
├── models.py                          # SimulationRun, BenchmarkConfiguration, BenchmarkTrial, ExperimentMetric
├── migrations/
│   └── 0001_initial.py               # Authoritative schema migration
├── persistence/
│   ├── __init__.py                    # Public exports
│   ├── fingerprint.py                 # Canonical SHA-256 fingerprinting & validation
│   └── service.py                     # SimulationPersistenceService orchestration
└── api/
    ├── pagination.py                  # AMAPPHistoryPagination
    ├── serializers.py                 # DRF historical serializers
    ├── views.py                       # Historical list/detail views
    └── urls.py                        # Endpoint route registrations
```

### 3.1 Data Models Overview

1. **`SimulationRun`:**
   - Primary Key: `id` (AutoField).
   - Identity: `run_id` (CharField, unique, max_length=128, db_index=True).
   - Scenario Context: `scenario_id` (CharField, max_length=128, db_index=True).
   - Lifecycle: `status` (CharField, choices=RunLifecycleState, default='CREATED', db_index=True).
   - Determinism: `configuration_fingerprint` (CharField, max_length=64, db_index=True) storing canonical SHA-256.
   - Configuration: `configuration_payload` (JSONField) storing normalized run configuration.
   - Temporal: `created_at`, `started_at`, `completion_time`, `simulation_duration_s`, `completed_ticks`.
   - Error Diagnostics: `error_category` and `error_details` (JSONField).
   - Indexes: Composite index `[status, created_at]`, index on `configuration_fingerprint`.

2. **`BenchmarkConfiguration`:**
   - Identity: `config_id` (CharField, unique, max_length=128, db_index=True).
   - Name & Description: Human-readable metadata.
   - Algorithms & Scenarios: `algorithms` (JSONField), `scenarios` (JSONField).
   - Repetition & Seed: `trials_per_pair` (PositiveIntegerField), `base_seed` (IntegerField).
   - Determinism: `configuration_fingerprint` (CharField, max_length=64, unique, db_index=True).
   - Payloads: `configuration_payload` (JSONField).

3. **`BenchmarkTrial`:**
   - Foreign Key: `benchmark_config` (ForeignKey -> `BenchmarkConfiguration`, on_delete=CASCADE).
   - Identity: `trial_id` (CharField, unique, max_length=128, db_index=True).
   - Pair Attributes: `scenario_id` (CharField, max_length=128), `algorithm_name` (CharField, max_length=64), `repetition_index` (PositiveIntegerField), `seed` (IntegerField).
   - Execution Status: `status` (CharField, choices=[SUCCESS, FAILED, INFEASIBLE, TIMEOUT, CANCELLED]).
   - Results: `route_cost` (FloatField, nullable), `route_length_m` (FloatField, nullable), `planning_time_ms` (FloatField), `simulation_travel_time_s` (FloatField, nullable), `collision_count` (PositiveIntegerField), `pdr_percent` (FloatField, nullable).
   - Linked Simulation: `simulation_run` (ForeignKey -> `SimulationRun`, on_delete=SET_NULL, null=True, blank=True).
   - Constraints: `UniqueConstraint(fields=['benchmark_config', 'scenario_id', 'algorithm_name', 'repetition_index'], name='unique_benchmark_trial_identity')`.

4. **`ExperimentMetric`:**
   - Associations: `simulation_run` (ForeignKey -> `SimulationRun`, on_delete=CASCADE, null=True), `benchmark_trial` (ForeignKey -> `BenchmarkTrial`, on_delete=CASCADE, null=True).
   - Identity: `metric_name` (CharField, max_length=128, db_index=True), `metric_type` (CharField, choices=[GAUGE, COUNTER, HISTOGRAM_SUMMARY, SCALAR]).
   - Temporal & Tick: `sample_tick` (PositiveIntegerField, null=True), `sample_timestamp_s` (FloatField, null=True).
   - Value: `metric_value` (FloatField, validated with `math.isfinite()`).
   - Dimensions: `dimensions` (JSONField, default=dict).

---

## 4. Deterministic Configuration Fingerprinting

Implemented in `backend/apps/core/persistence/fingerprint.py`:

```python
def compute_configuration_fingerprint(
    config: Mapping[str, Any] | Any,
    excluded_keys: Sequence[str] | None = None,
) -> str:
    """Compute a canonical, deterministic SHA-256 fingerprint for a configuration."""
```

### Fingerprinting Invariants & Security Rules
- **Key Sorting:** Dictionaries are sorted recursively by key at all nesting depths.
- **Float Normalization:** All floating-point numbers are rounded to 6 decimal places (`round(val, 6)`), eliminating microscopic machine-dependent IEEE 754 precision drifts.
- **Rejection of Non-Finite Floats:** `math.isnan(val)` or `math.isinf(val)` raises `NonFiniteValueError` to prevent indeterminate JSON representations.
- **Rejection of Secret & Credential Keys:** Any key matching sensitive patterns (`token`, `password`, `secret`, `credential`, `private_key`) raises `SensitiveConfigurationKeyError`.
- **Rejection of Absolute Filesystem Paths:** String values matching Unix (`/home/...`, `/etc/...`) or Windows (`C:\...`, `D:\...`, `\\share\...`) absolute paths raise `AbsolutePathConfigurationError` to guarantee environment-agnostic fingerprint portability.
- **Automatic Operational Field Exclusion:** Ephemeral runtime fields (`run_id`, `created_at`, `updated_at`, `timestamp`, `elapsed_time_s`) are systematically excluded before hashing.

---

## 5. Lifecycle State Machine & Transition Rules

The simulation lifecycle strictly follows:

```
                  +-----------------------------------+
                  |              CREATED              |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------------------------+
                  |            VALIDATING             |
                  +--------+------------------+-------+
                           |                  |
              Validation OK|                  | Validation Failed
                           v                  v
                  +-----------------+   +-------------+
                  |      READY      |   |   FAILED    |
                  +--------+--------+   +-------------+
                           |
                           v
                  +-----------------+
                  |     RUNNING     |
                  +---+----+----+---+
                      |    |    |
           Cancel Req |    |    | Error
      +---------------+    |    +---------------+
      |                    |                    |
      v                    v                    v
+-----------+       +--------------+      +------------+
| CANCELLED |       |  COMPLETED   |      |   FAILED   |
+-----------+       +--------------+      +------------+
                           |
                           v Max ticks / duration reached
                    +--------------+
                    |LIMIT_REACHED |
                    +--------------+
```

### Illegal Transition Protection
`SimulationRun.transition_to(target_state)` raises `IllegalLifecycleTransitionError` when an illegal transition is attempted (e.g., transition from `COMPLETED` to `RUNNING`, or `CANCELLED` to `VALIDATING`).

---

## 6. Resilience, Non-Blocking Guarantees & Transaction Isolation

The `SimulationPersistenceService` guarantees that database operations never disrupt the core simulation engine:

1. **Transactional Boundaries:** All multi-row updates and writes are wrapped in `transaction.atomic()`. If any step fails, the transaction rolls back cleanly without partial or corrupted state.
2. **Error Containment:** All public service methods catch database errors, log descriptive warnings/errors via standard logging, and return a structured `PersistenceResult(success=False, record_id=..., error=...)`. The simulation runner never crashes due to a persistence exception.
3. **Zero Per-Tick Writes:** In-memory simulations step up to 100 Hz without touching the database. Metrics are accumulated in memory and flushed only at milestone intervals or run completion via `record_run_completed`.
4. **Persistence Disabled Mode:** When `SimulationPersistenceService(enabled=False)` is used (or in memory-constrained environments), all methods return `PersistenceResult(success=True)` as immediate no-ops.

---

## 7. REST API Historical Endpoints & Pagination

The following endpoints are registered under `/api/v1/`:

| Endpoint | Method | Description | Filtering & Pagination |
| :--- | :--- | :--- | :--- |
| `/api/v1/runs/` | `GET` | List persistent historical simulation runs | `status`, `scenario_id`, `fingerprint`, `date_from`, `date_to`, `limit`, `offset` |
| `/api/v1/runs/<run_id>/` | `GET` | Retrieve run details, status, timings, and configuration | Read-only guarantee |
| `/api/v1/runs/<run_id>/metrics/` | `GET` | Retrieve time-series metrics recorded for run | `metric_name`, `sample_tick` |
| `/api/v1/benchmarks/configurations/` | `GET` | List benchmark configurations | `fingerprint`, `limit`, `offset` |
| `/api/v1/benchmarks/configurations/<config_id>/` | `GET` | Retrieve benchmark configuration detail | Read-only guarantee |
| `/api/v1/benchmarks/trials/` | `GET` | List benchmark trials | `config_id`, `scenario_id`, `algorithm`, `status`, `limit`, `offset` |
| `/api/v1/benchmarks/trials/<trial_id>/` | `GET` | Retrieve benchmark trial detail | Read-only guarantee |

### Pagination Structure
All listing endpoints use `AMAPPHistoryPagination` yielding:
```json
{
  "count": 42,
  "next": "http://.../api/v1/runs/?limit=20&offset=20",
  "previous": null,
  "results": [...]
}
```

---

## 8. Test Suite & Coverage Metrics

### Phase 35 Test Modules

| Test File | Test Class | Tests | Status | Scope |
| :--- | :--- | :---: | :---: | :--- |
| `test_persistence_models_and_migrations.py` | `TestPersistenceModelsAndMigrations` | 8 | PASSED | Model CRUD, unique constraints, dry-run migrations, finite validation |
| `test_persistence_fingerprint.py` | `TestPersistenceFingerprint` | 8 | PASSED | Key invariance, float precision, secret rejection, absolute path rejection |
| `test_persistence_lifecycle_and_failures.py` | `TestPersistenceLifecycleAndFailures` | 7 | PASSED | End-to-end lifecycle, failure containment, idempotency, zero per-tick writes |
| `test_api_persistence_history.py` | `TestApiPersistenceHistory` | 7 | PASSED | Endpoint pagination, filters, 404 handling, read-only protections |

### Suite-Wide Verification Results
- **Phase 35 Dedicated Tests:** 30 passed, 0 failed in 7.60s.
- **Total Pytest Suite:** **1,247 passed, 0 failed, 3 warnings** in 69.48s.
- **Backend Code Coverage:** **95%** across all files (enforced gate $\ge 80\%$).
- **Frontend Vitest Suite:** **192 passed, 0 failed** across 11 test files in 3.24s.
- **Frontend Typecheck & Build:** TypeScript strict check passed; Vite production build generated in 1.75s.

---

## 9. Authoritative CI Pipeline Verification

The GitHub Actions pipeline (`.github/workflows/ci.yml`) validates:
1. `repo-hygiene`: Existence of `docs/progress/PHASE_35.md`, absence of leaked secret files or raw databases (`.sqlite3`).
2. `backend-quality`: Ruff linting, Django check, Django dry-run migration check (`makemigrations --check --dry-run`), database migration execution (`migrate`), persistence model validation check, complete pytest suite with `--cov-fail-under=80`, benchmark smoke test, Gymnasium env checker, RL baseline training smoke test, and learned policy benchmark smoke test.
3. `frontend-quality`: `npm ci`, ESLint, strict TypeScript typecheck, Vitest unit tests, and production build bundle.

- **GitHub Actions Run URL:** [Run #39746773012](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39746773012)
- **Commit SHA:** `c06df01`
- **Workflow Status:** **100% SUCCESS / ALL GATES PASSED**

### Completed Jobs & Evidence

1. **Repository Hygiene & Documentation Integrity (`119717073015`):**
   - Duration: 5s
   - Outcome: `SUCCESS`
   - Verified present: `docs/progress/PHASE_35.md`, `README.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, and all previous phase progress artifacts.
   - Secret Leak Scan: No prohibited extensions or secret patterns detected.

2. **Frontend Lint, Typecheck, Test & Production Build (`119717073144`):**
   - Duration: 28s
   - Outcome: `SUCCESS`
   - `npm ci`: Clean reproducible installation.
   - ESLint: 0 errors.
   - TypeScript: Strict typecheck passed (`tsc -b`).
   - Vitest Unit Tests: 192 passed across 11 test files.
   - Production Build: Vite production bundle built cleanly in 1.75s.

3. **Backend Lint, Test & Coverage (`119717072679`):**
   - Duration: 2m 3s
   - Outcome: `SUCCESS`
   - Ruff: All checks passed.
   - Django System Checks: 0 issues identified.
   - Database Migrations: `makemigrations --check --dry-run` detected 0 unstaged schema changes; `migrate` successfully applied `core.0001_initial` on SQLite.
   - Persistence Verification: Phase 35 models (`SimulationRun`, `BenchmarkConfiguration`, `BenchmarkTrial`, `ExperimentMetric`) verified in Django environment.
   - Full Test Suite: **1,247 passed, 0 failed** in 69.48s.
   - Coverage: **95%** (enforced threshold $\ge 80\%$).
   - Benchmarking Smoke Verification: `run_benchmark --smoke` passed.
   - Gymnasium Environment Check: `check_env` compliant.
   - RL Baseline Training Smoke: `train_rl_baseline --smoke` passed.
   - Learned Routing Policy & Safe Fallback Benchmark: `run_benchmark --algorithms learned` passed with honest `INFEASIBLE` accounting for partitioned scenarios.
