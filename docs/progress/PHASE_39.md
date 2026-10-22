# Phase 39 — Docker, Containerization, and Reproducible Deployment

## 1. Objective & Acceptance Checklist

The primary objective of Phase 39 is to create a deterministic, reproducible, production-grade containerized deployment for the Adaptive Multi-Agent Path Planning (AMAPP) platform. The deployment packages the authoritative Python 3.11 Daphne ASGI backend and the Node 22 / React / Three.js frontend SPA into lightweight, secure container images orchestrated via Docker Compose, supporting real-time WebSocket communication, persistent SQLite storage, zero-leak secret handling, service health checks, and automated continuous deployment verification in GitHub Actions.

### Acceptance Checklist
- [x] **Production Backend Container (`docker/backend/Dockerfile`, `entrypoint.sh`):** Built on `python:3.11-slim-bookworm` running under dedicated non-root user `amapp` (UID/GID 10001); serves REST API and WebSocket protocols concurrently via Daphne ASGI (`config.asgi:application`); includes curl-based health probe.
- [x] **Production Frontend Container (`docker/frontend/Dockerfile`, `nginx.conf`):** Multi-stage build (Node 22 Alpine builder + Nginx 1.27 Alpine runner); compiles production Vite SPA and serves static assets; configures Nginx reverse proxy for `/api/` (REST) and `/ws/` (WebSockets with HTTP/1.1 upgrade headers); implements SPA client-side route fallback (`try_files $uri $uri/ /index.html`); includes `/healthz` probe.
- [x] **Docker Compose Orchestration (`docker-compose.yml`):** Root-level compose configuration defining `backend` and `frontend` services connected via internal bridge network `amapp-network`; establishes container health check dependencies (`depends_on: condition: service_healthy`); provisions named persistent volume `amapp-backend-data` mapped to `/app/data`.
- [x] **Safe Environment & Secret Handling (`.env.example`):** Fully documented template with non-secret placeholders; enforced production validations in `backend/config/settings.py` (rejecting dev keys and enforcing $\ge 32$ character secret keys when `DEBUG=False`); strict origin whitelisting without wildcards.
- [x] **Persistence & Data Volume Survival:** Configured `AMAPP_DATA_DIR=/app/data` to persist SQLite database (`db.sqlite3`) on named volume `amapp-backend-data`; automated CI verification confirming simulation runs and metrics survive container recreation (`docker compose down && docker compose up -d`).
- [x] **Automated Migration Handling:** Implemented safe migration startup flag `RUN_MIGRATIONS=true` in `entrypoint.sh` with manual override capability (`docker compose exec backend python manage.py migrate`).
- [x] **Service Health Checks & Readiness (`views.py`):** Enhanced backend `GET /api/v1/health/` to verify database connectivity (`SELECT 1`), returning HTTP 200 `connected` when healthy and HTTP 503 `unavailable` when degraded; frontend reports readiness via `GET /healthz`.
- [x] **End-to-End Deployment Smoke Verification (`scripts/test_deployment_smoke.py`):** Automated test suite verifying frontend health, direct backend health, reverse-proxied API health, scenario catalog listing, simulation run creation, discrete stepping, persistent metrics query, and WebSocket live streaming.
- [x] **Preserved Quality Gates & Zero Regressions:** All 1,338 backend tests passing with zero skips at 95.06% coverage; all 193 frontend tests passing cleanly; strict TypeScript, ESLint, and production build checks passing.
- [x] **Continuous Integration Verification (`.github/workflows/ci.yml`):** Added mandatory `deployment-smoke` job validating compose config, building images, waiting for container readiness, running smoke test client, verifying volume data persistence, and tearing down cleanly.

---

## 2. Container Architecture & Service Specifications

### 2.1 Topology & Network Flow
```mermaid
flowchart LR
    Client["Browser / Automated Client"] -->|Port 3000| Nginx["Frontend (Nginx 1.27)"]
    Nginx -->|/ Static Assets| SPA["Vite SPA Bundle"]
    Nginx -->|/api/ Proxy| Daphne["Backend (Daphne ASGI :8000)"]
    Nginx -->|/ws/ Proxy (Upgrade)| Daphne
    Daphne --> Django["Django REST & Channels"]
    Django --> Vol[("Named Volume:\namapp-backend-data\n(/app/data/db.sqlite3)")]
```

### 2.2 Service Breakdown
| Service | Image / Base | Internal Port | Host Port | User | Responsibilities |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`backend`** | `python:3.11-slim-bookworm` | `8000` | `8000` | `amapp` (10001) | Authoritative simulation stepping, REST endpoints (`/api/v1/`), WebSocket Channels (`/ws/v1/`), database migrations. |
| **`frontend`** | `nginx:1.27-alpine` | `80` | `3000` | `nginx` | Static file delivery, gzip compression, security headers, reverse proxy routing for `/api/` and `/ws/`. |

---

## 3. Environment Variables & Secret Handling

Configuration is managed via `.env` (copied from `.env.example`):
- **Secret Keys:** `DJANGO_SECRET_KEY` strictly requires $\ge 32$ characters when `DEBUG=False`. Insecure dev placeholders are strictly rejected at startup with an informative `ValueError`.
- **Allowed Hosts:** `ALLOWED_HOSTS=backend,localhost,127.0.0.1,frontend,web` enables container-to-container communication and host browser access without permissive wildcards.
- **WebSocket Origins:** `AMAPP_WS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000` permits cross-port WebSocket handshakes while blocking unapproved origins.
- **Persistence Path:** `AMAPP_DATA_DIR=/app/data` ensures all database writes target the persistent named Docker volume `amapp-backend-data`.

---

## 4. Health Checks & Readiness Probes

1. **Frontend Container Health Check:**
   - Endpoint: `GET /healthz`
   - Implementation: Nginx direct static response returning HTTP 200 `"healthy\n"`.
   - Probe: `wget -q -O - http://localhost/healthz || exit 1`.
2. **Backend Container Health Check:**
   - Endpoint: `GET /api/v1/health/`
   - Implementation: `HealthCheckView` in `backend/apps/core/views.py` executing `SELECT 1` on the active database connection.
   - Status Codes: Returns HTTP 200 with `"status": "healthy", "database": "connected"` when ready; returns HTTP 503 with `"status": "unhealthy", "database": "unavailable"` if the database is unreachable.
   - Probe: `curl -f http://localhost:8000/api/v1/health/ || exit 1`.
   - Startup Retries: Configured with 5 retries and 15s start period to allow migration completion before marking healthy.

---

## 5. End-to-End Smoke Verification (`scripts/test_deployment_smoke.py`)

The automated deployment smoke script tests the live container deployment:
```bash
python scripts/test_deployment_smoke.py --frontend-url http://localhost:3000 --backend-url http://localhost:8000 --ws-url ws://localhost:3000
```
Execution results:
1. `test_frontend_health`: HTTP 200 from `http://localhost:3000/healthz`.
2. `test_backend_health_direct`: HTTP 200 from direct backend `http://localhost:8000/api/v1/health/` with `"database": "connected"`.
3. `test_backend_health_via_proxy`: HTTP 200 forwarded via Nginx reverse proxy `http://localhost:3000/api/v1/health/`.
4. `test_rest_api_workflow`:
   - Retrieves scenario catalog (`GET /api/v1/scenarios/`).
   - Creates simulation run (`POST /api/v1/runs/`).
   - Advances simulation by 2 ticks (`POST /api/v1/runs/{id}/step/`).
   - Verifies persistent metric aggregation (`GET /api/v1/runs/{id}/metrics/`).
5. `async_test_websocket_streaming`:
   - Connects to `ws://localhost:3000/ws/v1/runs/{id}/`.
   - Receives initial handshake envelope with schema protocol version `1.0.0` and `event_type: "run.status"`.
   - Sends ping / heartbeat action over WebSocket and verifies received response envelope (`server.heartbeat`).

---

## 6. Persistence & Container Recreation Verification

To guarantee zero data loss during container upgrades and restarts:
1. The smoke test creates a persistent simulation run in `db.sqlite3` on volume `amapp-backend-data`.
2. The containers are stopped and destroyed via `docker compose down`.
3. The containers are recreated via `docker compose up -d`.
4. The backend reattaches to `/app/data/db.sqlite3` and queries `GET /api/v1/runs/?historical=true`.
5. Confirms the previously created simulation run is preserved and queryable.

---

## 7. Test Totals, Coverage & Quality Gates

### 7.1 Backend Test Suite (Pytest)
```text
================ 1338 passed, 4 warnings in 45.10s ================
Required test coverage of 80% reached. Total coverage: 95.06%
```
- Total tests passed: **1,338**
- Total tests failed: **0**
- Total tests skipped: **0**
- Coverage: **95.06%** across 28,124 statements (threshold: 80%)

### 7.2 Frontend Test Suite (Vitest)
```text
 Test Files  12 passed (12)
      Tests  193 passed (193)
   Duration  3.05s
```
- Total test files: 12
- Total tests passed: **193**
- Total tests failed: **0**
- Total tests skipped: **0**

### 7.3 Quality & Hygiene Gates
- **Ruff Linting (`ruff check .`):** Clean, 0 errors.
- **Django System Check (`python backend/manage.py check`):** 0 issues identified.
- **Django Migrations (`python backend/manage.py makemigrations --check --dry-run`):** No changes detected.
- **Routing Benchmark Smoke:** Passed.
- **Gymnasium Environment Compliance:** Passed.
- **RL Baseline Training Smoke:** Passed.
- **Learned RL Policy Benchmark:** Passed.
- **Phase 37 Automated Regression Matrix:** Passed.
- **Phase 38 Performance Smoke Regression Suite:** Passed (9/9 passed).
- **Frontend Typecheck & Lint:** 0 errors.
- **Frontend Production Bundle:** Built cleanly via Vite.

---

## 8. GitHub Actions CI Verification

The `.github/workflows/ci.yml` pipeline was updated to include:
1. Mandatory documentation integrity checks for `docs/progress/PHASE_39.md`, `docs/DEPLOYMENT.md`, `docker-compose.yml`, and `.dockerignore`.
2. Dedicated `deployment-smoke` job executing:
   - `docker compose config` validation.
   - `docker compose up -d --build` multi-stage image builds.
   - Container health check polling until both services report `healthy`.
   - `scripts/test_deployment_smoke.py` execution against live running containers.
   - Volume persistence verification across container teardown and restart.
   - Clean volume teardown via `docker compose down -v`.

### 8.1 Authoritative Verification & Provenance
- **Starting Commit:** `cb079c9`
- **Implementation Commit:** `af579b3`
- **Fix Commits:** `1f37063`, `446f316`, `b0bcf8e`, `27a8fd2`, `cd200e4`
- **Tested Final Commit:** `cd200e4`
- **Backend Test Count:** 1,338 passed, 0 failed, 0 skipped (95.06% coverage)
- **Frontend Test Count:** 193 passed, 0 failed, 0 skipped across 12 suites
- **Deployment Smoke Gate:** Passed (Docker build, healthchecks, REST, WebSockets, volume persistence)
- **Authoritative CI Run URL:** [https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39832687829](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39832687829)
- **Job Outcomes:**
  1. `Frontend Lint, Typecheck, Test & Production Build` — SUCCESS (31s, ID 120012701526)
  2. `Repository Hygiene & Documentation Integrity` — SUCCESS (4s, ID 120012701887)
  3. `Backend Lint, Test & Coverage` — SUCCESS (1m42s, ID 120012702184)
  4. `Docker Build, Healthcheck & Container Deployment Smoke Verification` — SUCCESS (55s, ID 120013571757)

### 8.2 Failures Encountered & Systematic Resolutions
1. **Frontend Dockerfile Asset Paths:**
   - *Failure:* Initial frontend Dockerfile referenced non-existent `frontend/public`, `tsconfig.app.json`, and `tsconfig.node.json`, failing buildx bake.
   - *Resolution:* Aligned COPY commands with the actual Vite structure (`tsconfig.json`, `vite.config.ts`, `eslint.config.js`, `index.html`, `src/`).
2. **Frontend Container Health Check Resolution (Alpine Musl IPv6 Mismatch):**
   - *Failure:* `wget -q -O - http://localhost/healthz` failed in Alpine Linux because `localhost` resolved to `::1` under musl libc, whereas Nginx was only listening on IPv4 (`listen 80;`).
   - *Resolution:* Added `listen [::]:80;` to `docker/frontend/nginx.conf` and updated health probes to use `http://127.0.0.1/healthz`.
3. **Smoke Test API Endpoints & Field Names:**
   - *Failure:* Smoke test queried non-existent `/api/v1/simulations/` and sent `steps` instead of `ticks`.
   - *Resolution:* Corrected URLs to `/api/v1/runs/`, updated step payload to `{"ticks": 2}`, and inspected `lifecycle_state` and `run_id`.
4. **Scenario Registry ID Resolution:**
   - *Failure:* `POST /api/v1/runs/` with `scenario_id='scn_ambulance_corridor'` failed with `SCENARIO_NOT_FOUND` because `ScenarioRegistry.preload_defaults()` registered with alias `'scn_ambulance'`.
   - *Resolution:* Enhanced `ScenarioRegistry.get()` and `exists()` in `backend/apps/core/api/services.py` to seamlessly resolve by either registered key or `scenario.metadata.id`.
5. **WebSocket Client Verification Schema:**
   - *Failure:* Smoke test asserted envelope field `type` instead of `event_type`.
   - *Resolution:* Aligned client assertion with `SimulationEventType` schema (`event_type == 'run.status'`).

---

## 9. Known Limitations

- **Single Worker Daphne Architecture:** Daphne currently runs as a single ASGI process using `InMemoryChannelLayer`. For high-concurrency horizontal scaling across multiple backend replicas, an external Redis channel layer container should be enabled via `REDIS_URL`.
- **Database Engine Default:** Default deployment uses volume-mounted SQLite (`/app/data/db.sqlite3`). For enterprise high-concurrency write workloads, an external PostgreSQL service can be configured via environment variables.

---

## 10. Phase 40 Handoff Instructions

Phase 39 has achieved full containerization, Docker Compose orchestration, volume persistence, and CI deployment verification.

### Scope for Phase 40: Final Acceptance, Comprehensive Audit, and Demonstration
1. **Audit All 14 Functional Requirements (FR-01 to FR-14):**
   - Conduct a systematic verification audit confirming every requirement from `Project_Objective_and_Requirements.pdf` is fully covered with automated test evidence.
2. **End-to-End System Demonstration:**
   - Prepare clean demonstration scripts and recorded runs showing live simulation, incident injection, dynamic rerouting, V2V packet delivery, and operational metrics.
3. **Project Blueprint & Final Documentation:**
   - Finalize `README.md`, `ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, and generate the final phase report `docs/progress/PHASE_40.md`.
4. **Final Sign-Off:**
   - Confirm complete green status across all CI quality gates on the master branch.
