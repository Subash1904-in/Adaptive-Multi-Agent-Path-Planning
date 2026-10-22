# Phase 36 — Security Hardening and Failure Handling

## 1. Objective & Acceptance Checklist

The objective of Phase 36 is to systematically harden the Adaptive Multi-Agent Path Planning (AMAPP) platform against injection attacks, denial of service (DoS), path traversal, unauthorized mutations, framing exploits, and unexpected failure modes across the REST API, WebSocket realtime layer, model management, and persistence layer.

This phase establishes:
1. **Django Configuration Hardening:** Strict SECRET_KEY validation (minimum 32 characters, rejection of default/placeholder keys in non-debug mode), secure production `ALLOWED_HOSTS` enforcement, defensive HTTP headers (`SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS = 'DENY'`, cookie security flags), body memory limits (`DATA_UPLOAD_MAX_MEMORY_SIZE = 5MB`), and origin controls.
2. **REST API Validation & Defense-in-Depth:**
   - Strict regex-based path parameter validation (`^[a-zA-Z0-9_-]{1,128}$`) rejecting traversal sequences, control characters, and injection attempts.
   - Comprehensive finite numeric validation using `math.isfinite()` across all floating point inputs (target accelerations, metric bounds, timestamps) rejecting `NaN`, `+Inf`, and `-Inf`.
   - DRF rate limiting via `AnonRateThrottle`, `UserRateThrottle`, and `ScopedRateThrottle` (`simulation_create`, `simulation_step`).
   - RFC 7807 problem details exception handling translating throttling into `RATE_LIMIT_EXCEEDED` (HTTP 429) with `available_in_seconds`, and sanitizing internal 500 errors to prevent stack trace leaks.
   - Role-based mutation authorization (`AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS`) requiring staff status for mutating operations (`POST`, `PUT`, `PATCH`, `DELETE`) while preserving open read access for simulation analytics.
3. **Realtime WebSocket Hardening:**
   - Origin validation enforcing explicit `AMAPP_WS_ALLOWED_ORIGINS` and matching against `ALLOWED_HOSTS`.
   - Strict framing limits (maximum 64KB per text/binary frame) rejecting oversized payloads with code 4400.
   - Command schema validation and finite acceleration checks ($|a| \le 50.0\text{ m/s}^2$).
   - Protection against runtime run ID switching and guaranteed leak-free cleanup on abnormal disconnects.
4. **Filesystem & Model Artifact Safety:**
   - Strict path containment (`is_safe_contained_path`) ensuring model artifacts resolve only within approved project, working, or temp directories, rejecting traversal (`..`) and external absolute paths.
   - Zip Slip mitigation inspecting zip archive entries and rejecting directory traversal patterns, leading slashes, or Windows drive letter specifications.
   - Bounded archive decompression and corrupt archive detection returning structured invalid reports or raising structured domain errors.
   - SafeFallbackPolicyWrapper ensuring model inference or loading failures cleanly fall back to conventional routing without crashing active simulations.
5. **Persistence & Database Failure Containment:**
   - Atomic transaction guarantees ensuring partial failures cleanly rollback.
   - Non-blocking failure tolerance: database errors in `SimulationPersistenceService` return `PersistenceResult(success=False)` without interrupting simulation runs.
   - Idempotent finalization handling duplicate completion or failure transitions on terminal runs.
   - Non-finite float filtering sanitizing `NaN`, `+Inf`, and `-Inf` in metric recording and duration fields.
6. **Authoritative CI Acceptance Gate:** All 37 new Phase 36 security tests and all existing tests run and pass in GitHub Actions CI with zero skips and $\ge 80\%$ backend coverage.

### Acceptance Checklist
- [x] **Secure Django Settings:** Configured strict secret key validation, production allowed hosts enforcement, HTTP security headers, request body limits (5MB), and throttle rate limits.
- [x] **WebSocket Origin & Framing:** Implemented `SimulationOriginValidator` with explicit origin whitelist, 64KB frame size limits, schema validation, finite acceleration checks, and disconnect resource cleanup.
- [x] **REST API Parameter Sanitization & Throttling:** Added `validate_path_identifier` regex check, `AnonRateThrottle`/`UserRateThrottle`/`ScopedRateThrottle`, and RFC 7807 rate limit error translation.
- [x] **Role-Based Mutation Policy:** Configured `AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS` across REST views and WebSocket consumer actions.
- [x] **Safe Model Artifact Containment & Zip Slip Mitigation:** Implemented `is_safe_contained_path`, path resolution bounds, Zip Slip archive inspection, and corrupt archive handling in `model_manager.py`.
- [x] **Safe Conventional Fallback:** Verified `SafeFallbackPolicyWrapper` routes safely when RL models fail or are corrupted.
- [x] **Persistence Failure Tolerance:** Implemented atomic rollbacks, idempotent terminal transitions, and non-finite float filtering (`_safe_finite_float`).
- [x] **Automated Security Test Suite (37 tests across 5 modules):**
  - `test_security_configuration.py` (6 tests)
  - `test_security_api_validation_and_throttling.py` (9 tests)
  - `test_security_websocket_and_origin.py` (9 tests)
  - `test_security_artifact_and_path_traversal.py` (6 tests)
  - `test_security_persistence_failure_containment.py` (7 tests)
- [x] **Full Regression & Quality Verification:** Full backend test suite passing with **1,284 passed, 0 failed** at **94.91% coverage**; all 192 frontend tests passing; smoke benchmarks and RL training verified.
- [x] **CI Pipeline Evolution:** Updated `.github/workflows/ci.yml` adding `docs/progress/PHASE_36.md` to mandatory file checks and adding security configuration verification steps.

---

## 2. Starting Repository & Environment State

- **Starting Branch:** `main`
- **Initial Working Commit SHA:** `c06df01` (Phase 35 implementation)
- **Platform:** Windows-10-10.0.26300-SP0 (local) / Ubuntu-24.04 (GitHub Actions CI)
- **Python Version:** 3.11.9
- **Django Version:** 5.1.15
- **Django Channels Version:** 4.2.0
- **Daphne Version:** 4.1.2
- **Django REST Framework Version:** 3.15.2
- **PyTorch Version:** 2.2.0+cpu
- **Stable-Baselines3 Version:** 2.3.2

---

## 3. Threat Model & Security Posture Analysis

| Threat Category | Potential Attack Vector | Hardening / Mitigation Implemented |
| :--- | :--- | :--- |
| **Configuration Vulnerabilities** | Weak/default secret keys, wildcard allowed hosts, clickjacking, MIME-sniffing | Minimum 32-char key check, placeholder rejection in non-debug, `X_FRAME_OPTIONS='DENY'`, `SECURE_CONTENT_TYPE_NOSNIFF`, cookie `HttpOnly` and `SameSite='Lax'`. |
| **Denial of Service (DoS)** | Unbounded request bodies, WebSocket payload flooding, API endpoint brute-forcing | `DATA_UPLOAD_MAX_MEMORY_SIZE = 5MB`, 64KB WebSocket message limit, DRF anon (60/min) and user (300/min) throttling, scoped view throttling. |
| **Input Injection & Traversal** | Path traversal in URL identifiers (`..`, `%2F`, slashes), shell metacharacters | `validate_path_identifier` enforcing `^[a-zA-Z0-9_-]{1,128}$` across all detail/action endpoints; safe 400 Bad Request error response. |
| **Numeric Instability & Poisoning** | `NaN`, `+Inf`, `-Inf` in kinematic controls or metrics causing calculation crashes | Explicit `math.isfinite()` validation on acceleration inputs ($|a| \le 50.0$), metric queries, and persistence writes (`_safe_finite_float`). |
| **WebSocket Hijacking & Desync** | Cross-Site WebSocket Hijacking (CSWSH), unvalidated commands, run ID switching | `SimulationOriginValidator` enforcing `AMAPP_WS_ALLOWED_ORIGINS` and `ALLOWED_HOSTS`, schema validation, mutation authorization, immutability of run binding. |
| **Filesystem & Archive Exploits** | Zip Slip path traversal during model archive inspection, arbitrary file loading | `is_safe_contained_path` containment check, Zip Slip path inspection (`..`, leading `/`, drive letters), bounded archive inspection, `SafeFallbackPolicyWrapper`. |
| **Persistence Cascade Failures** | Database operational failure crashing active simulations or partial state pollution | `transaction.atomic()` rollbacks, non-blocking try/except returning `PersistenceResult(success=False)`, idempotent terminal state transitions. |

---

## 4. Hardening Implementations

### 4.1 Django Security Configuration & Defense-in-Depth

In `backend/config/settings.py`:
- `SECRET_KEY` validation: Ensures the key is at least 32 characters long and rejects insecure development defaults when `DEBUG=False`.
- `ALLOWED_HOSTS` validation: Rejects empty or wildcard (`*`) allowed hosts when `DEBUG=False`.
- Security Headers:
  - `SECURE_CONTENT_TYPE_NOSNIFF = True`
  - `X_FRAME_OPTIONS = "DENY"`
  - `SESSION_COOKIE_HTTPONLY = True`
  - `CSRF_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SAMESITE = "Lax"`
  - `CSRF_COOKIE_SAMESITE = "Lax"`
- Body Size Limit:
  - `DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024` (5 MB)
- Throttling Configuration:
  - Default rate classes: `AnonRateThrottle`, `UserRateThrottle`, `ScopedRateThrottle`.
  - Default rates: anon 60/min, user 300/min, `simulation_create` 30/min, `simulation_step` 1200/min.

In `backend/config/asgi.py`:
- `SimulationOriginValidator`: Inspects request origin header against `AMAPP_WS_ALLOWED_ORIGINS` and `ALLOWED_HOSTS`, permitting standard loopback/testing origins while rejecting unapproved domains.

### 4.2 REST API Validation, RFC 7807 Exception Translation, & Authorization

In `backend/apps/core/api/`:
- `validate_path_identifier`: Sanitizes route arguments matching `^[a-zA-Z0-9_-]{1,128}$` across `RunDetailView`, `RunStepView`, `RunCancelView`, `RunMetricsView`, `BenchmarkConfigurationDetailView`, `BenchmarkTrialDetailView`, and incident endpoints.
- `exceptions.py`: Custom `api_exception_handler` translates DRF `Throttled` into RFC 7807 `RATE_LIMIT_EXCEEDED` (HTTP 429) including `available_in_seconds` in `details`, and translates unhandled exceptions into safe 500 responses without exposing internal stack traces.
- `permissions.py`: `SimulationApiPermission` and `ReadOnlyOrAdminApiPermission` enforce `request.user.is_staff` when `AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS=True` on write verbs (`POST`, `PUT`, `PATCH`, `DELETE`).
- `serializers.py`: Validates `run_id`, `target_accels` (finite float and range $[-50.0, 50.0]$), and query parameters (`min_value`, `max_value`, `since_timestamp`).

### 4.3 Realtime WebSocket Framing & Safety

In `backend/apps/core/realtime/consumer.py`:
- Maximum message size check: In `receive()`, text and binary payloads exceeding `MAX_FRAME_SIZE = 65536` bytes (64 KB) are rejected with error code `PAYLOAD_TOO_LARGE` (code 4400) and connection termination.
- Schema & Action Validation: Validates incoming commands against recognized actions (`join`, `step`, `cancel`).
- Role-Based Action Authorization: Mutating actions (`step`, `cancel`) require `user.is_staff` when `AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS=True`.
- Finite Acceleration Validation: Validates `target_accels` values are finite floats within $[-50.0, 50.0]\text{ m/s}^2$.
- Session State Guard: Rejects attempts to switch `run_id` during an active connection.
- Disconnect Resource Cleanup: Guarantees detachment from simulation world and group channels upon disconnect.

### 4.4 Filesystem & Model Artifact Safety

In `backend/apps/core/rl/model_manager.py`:
- `is_safe_contained_path`: Validates that model file paths resolve strictly within approved project, working, or temp directories, preventing directory traversal.
- `resolve_model_artifact_path`: Rejects traversal attempts via explicit paths or `AMAPP_RL_MODEL_PATH` environment variables.
- `validate_model_artifact`:
  - Enforces approved root path containment.
  - Inspects zip entries for Zip Slip attacks (rejecting `..`, leading slashes, Windows drive specifications).
  - Validates zip archive integrity and required entries (`data`).
  - Verifies observation and action space dimensions against expected environment definitions.
- Safe Fallback Integration: `SafeFallbackPolicyWrapper` catches model inference or load errors and seamlessly falls back to conventional routing (A*, Dijkstra) without throwing unhandled exceptions.

### 4.5 Persistence Failure Containment & Non-Finite Float Sanitization

In `backend/apps/core/persistence/service.py`:
- `_safe_finite_float`: Utility converting non-finite float values (`NaN`, `+Inf`, `-Inf`) or malformed types to `None`, protecting database fields from invalid numbers.
- Transaction Isolation: Wraps multi-model writes (such as benchmark suite results) in `transaction.atomic()`, ensuring all-or-nothing persistence.
- Failure Containment: Catches database exceptions (`OperationalError`, `IntegrityError`) and returns `PersistenceResult(success=False, error=str(exc))` without bubbling up to crash simulations or benchmarks.
- Idempotent Finalization: Handles repeated completion or failure calls on terminal runs gracefully without raising errors.

---

## 5. Test Coverage & Verification Matrix

Phase 36 introduces 37 new targeted automated tests across 5 test suites:

### 5.1 Test Suites Summary

| Test Suite Module | Tests | Focus Area | Status |
| :--- | :---: | :--- | :---: |
| `test_security_configuration.py` | 6 | Secret key strength, allowed hosts enforcement, HTTP security headers, body size limits, settings error conditions. | **PASSED** |
| `test_security_api_validation_and_throttling.py` | 9 | Identifier path sanitization, finite float validation, RFC 7807 429 rate limit translation, role-based mutation permission. | **PASSED** |
| `test_security_websocket_and_origin.py` | 9 | Origin validator whitelist, 64KB frame limit, command schema validation, finite acceleration checks, disconnect cleanup. | **PASSED** |
| `test_security_artifact_and_path_traversal.py` | 6 | Path containment, Zip Slip mitigation, corrupt zip handling, SafeFallbackPolicyWrapper robustness. | **PASSED** |
| `test_security_persistence_failure_containment.py` | 7 | Non-finite float filtering, database error containment, transaction rollback, idempotent terminal transitions. | **PASSED** |
| **Total Phase 36 Tests** | **37** | **Comprehensive Platform Security Hardening** | **ALL PASSED** |

### 5.2 Full Test Suite & Coverage Metrics

- **Backend Pytest Execution:** 1,284 passed, 0 failed, 3 warnings in 67.99s.
- **Backend Code Coverage:** 94.91% across `backend/apps/core` (exceeding the 80% CI requirement).
- **Frontend Test Suite:** 192 passed across 11 test suites in 31.53s.
- **Frontend Build & Typecheck:** 0 TypeScript errors, 0 ESLint errors, Vite production bundle build successful.
- **Smoke Benchmarks:** `run_benchmark --smoke` and `train_rl_baseline --smoke` completed with 0 errors.

---

## 6. Residual Risks & Security Recommendations for Future Phases

1. **Authentication Provider Integration:** Currently, authentication uses Django's session/token model with research-mode fallback. In multi-tenant enterprise deployments, integrating OpenID Connect (OIDC) or OAuth2 with JWT validation is recommended.
2. **Distributed Cache for Throttling:** DRF throttles currently use Django's configured cache (in-memory for development/testing). In distributed multi-worker deployments, a shared Redis cache backend should back throttle counters.
3. **Model Artifact Digital Signatures:** Model archives are verified for structure, schema, and Zip Slip containment. For production edge deployments, cryptographic HMAC or asymmetric signature verification (e.g., Cosign/Sigstore) can be layered on model artifacts.
