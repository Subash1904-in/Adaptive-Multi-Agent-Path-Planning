# PHASE 05 PROGRESS REPORT: OpenStreetMap Import and Road Network Normalization

## 1. Phase Objective & Acceptance Checklist

### Objective
Implement an OpenStreetMap import subsystem that can acquire road-network data for a specified geographic area, normalize that data into existing internal domain entities (`RoadNode`, `RoadEdge`), and construct a usable `RoadGraph` with deterministic offline fallback to the Phase 4 synthetic city when OSMnx is absent or external requests fail.

### Acceptance Checklist
- [x] **OSMnx Dependency Integrated:** Pinned `osmnx>=2.0.0,<2.1.0` in `requirements.txt` (installed 2.0.7 in Python 3.11 with NetworkX 3.3).
- [x] **Defensive & Lazy Imports:** Core backend, domain entities, and synthetic city generator operate without requiring OSMnx or external network services.
- [x] **Geographic Bounding Box Validation:** `BoundingBox` validates ranges ($[-90, 90]$, $[-180, 180]$), orientation (`north > south`, `east > west`), finiteness, and enforces a safety span limit ($\le 0.25^\circ$).
- [x] **Local Planar Coordinate Projection:** `LocalPlanarProjector` maps WGS84 coordinates to local Cartesian coordinates in meters (`Position2D`) relative to the southwest origin $(x \ge 0, y \ge 0)$ without treating lat/lon degrees as meters.
- [x] **Geographic Node Normalization:** Converts OSM nodes to `RoadNode` domain entities with `Position2D` (meters), `GeoCoordinate` (WGS84 degrees), and deterministic IDs (`osm_node_{id}`).
- [x] **Directed Road Edge Normalization:** Converts OSM ways to `RoadEdge` domain entities, distinguishing one-way from bidirectional streets, calculating lengths, parsing speed limits (km/h, mph, defaults) and lanes ($\ge 1$).
- [x] **Topological Integrity Preserved:** Endpoint existence verified, self-loops skipped, parallel edges consolidated/skipped for simple `RoadGraph` DiGraph topology.
- [x] **Deterministic Offline Fallback:** Seamlessly falls back to Phase 4 `generate_synthetic_city_grid` when OSMnx is uninstalled, network fails, requests timeout, or data is empty and `allow_fallback=True`.
- [x] **Strict Bounds Integrity:** Invalid bounding boxes raise `InvalidBoundingBoxError` immediately and are never disguised by synthetic fallback.
- [x] **Structured Metadata:** `OSMImportResult` reports source type (`osm` vs `synthetic_fallback`), node/edge counts, skipped records, fallback reason, and timestamps.
- [x] **Comprehensive Test Suite:** 60 new unit tests (31 model/projector tests, 12 normalizer tests, 17 service/fallback tests); total **211 passed in 1.49s** with 0 regressions.
- [x] **Code Quality & Checks:** `ruff check backend` (0 errors) and `python backend/manage.py check` (0 issues identified).
- [x] **Documentation Synchronized:** `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, `README.md`, `docs/TESTING.md`, and `docs/progress/PHASE_05.md`.
- [x] **Strict Phase Boundaries Preserved:** Zero Dijkstra / A* routing (Phase 6), vehicle kinematic agents (Phase 7), or WebSockets implemented.

---

## 2. Initial Repository State

- **Starting Branch:** `main`
- **Starting Commit:** `e4b4c16` (`docs(phase-04): record verified CI run URL and completed job details`)
- **Starting Working Tree:** Clean, 151 tests passing across Phase 2, 3, and 4 suites.
- **Python Runtime:** Python 3.11.9 on Windows amd64 in active `.venv`.

---

## 3. Architecture & Design Decisions

### Separation of Acquisition from Normalization
To guarantee 100% offline automated test execution without relying on live Overpass API availability:
1. **Acquisition (`osm_acquisition.py`):** Encapsulates the external HTTP boundary (`ox.graph_from_bbox`) with defensive dependency loading (`is_osmnx_available`) and structured exception classification (`OSMTimeoutError`, `OSMServiceUnavailableError`, `OSMEmptyGraphError`, `OSMNotInstalledError`).
2. **Normalization (`osm_normalizer.py`):** Pure deterministic function `normalize_osm_graph` operating on any NetworkX `MultiDiGraph` or `DiGraph` fixture without requiring network access.
3. **Orchestration (`osm_service.py`):** High-level entrypoint `import_osm_road_network` coordinating validation, acquisition, normalization, and fallback.

### Local Planar Projection vs. Degrees
Treating latitude and longitude degrees as Cartesian meters produces catastrophic distortion (1 degree latitude is ~111 km, while 1 degree longitude shrinks with $\cos(\text{latitude})$).
`LocalPlanarProjector` implements a conformal local equirectangular projection centered on the southwest origin of the bounding box:
- $y = R \times \text{radians}(\text{lat} - \text{south})$
- $x = R \times \text{radians}(\text{lon} - \text{west}) \times \cos\left(\frac{\text{radians}(\text{lat} + \text{south})}{2}\right)$
where $R = 6,371,000.0\text{ m}$. For educational simulation bounding boxes ($\le 25\text{ km}$), distortion is below 0.05% with zero external C/PROJ dependencies.

### Graph Invariant & Parallel Edge Policy
`RoadGraph` represents a simple directed graph ($u \to v$). OSMnx returns a `MultiDiGraph` where multiple parallel ways or multi-segment ways can connect $(u, v)$ with different keys ($0, 1$). When normalizing, the primary edge is preserved in `RoadGraph`, and subsequent parallel edges between the same directed pair are skipped and recorded in `skipped_records`.

---

## 4. Dependencies & Compatibility

- **Added Dependency:** `osmnx>=2.0.0,<2.1.0` in `requirements.txt`.
- **Installed Version:** `osmnx==2.0.7` in Python 3.11.9 with `networkx==3.3`.
- **Geospatial Sub-dependencies:** `geopandas==1.2.0`, `shapely==2.2.0`, `pyproj==3.7.2`, `pyogrio==0.13.0`.
- **Runtime Decoupling:** `apps.core.graph` uses lazy/defensive imports for `osmnx`. The core `RoadGraph` and synthetic city generator function identically even if `osmnx` is uninstalled.

---

## 5. Geographic Input Validation & Projection Conventions

### BoundingBox Invariants
- `north`, `south`: $[-90.0, 90.0]$
- `east`, `west`: $[-180.0, 180.0]$
- `north > south` (strictly enforced; equality or inversion raises `InvalidBoundingBoxError`)
- `east > west` (strictly enforced; equality or inversion raises `InvalidBoundingBoxError`)
- `north - south <= 0.25` degrees (~27.8 km safety limit)
- `east - west <= 0.25` degrees (~20–27 km safety limit)
- Non-numeric or non-finite values (NaN, Inf) are strictly rejected.

---

## 6. Acquisition & Normalization Behavior

### Acquisition Pipeline
1. Validates that `osmnx` is installed. If absent, raises `OSMNotInstalledError`.
2. Converts `BoundingBox` to OSMnx 2.x parameter tuple `(west, south, east, north)`.
3. Sets `ox.settings.timeout = int(config.timeout)`.
4. Executes `ox.graph_from_bbox` with `simplify=True` and `retain_all=True`.
5. Classifies timeout errors as `OSMTimeoutError`, network/HTTP errors as `OSMServiceUnavailableError`, and empty results as `OSMEmptyGraphError`.

### Normalization Pipeline
1. **Nodes:** Iterates over nodes, validates coordinates, projects planar $(x, y)$, attaches `GeoCoordinate`, generates ID `osm_node_{id}`, and inserts into `RoadGraph`.
2. **Edges:** Iterates over edges, validates endpoints exist, calculates length in meters (or computes projected Euclidean distance if missing), parses speed limit (km/h, mph, defaults), parses lane count, distinguishes one-way vs. bidirectional roads, generates deterministic IDs (`osm_edge_{u}_{v}`), skips self-loops and parallel duplicates.
3. If no nodes could be normalized, raises `OSMEmptyGraphError`.

---

## 7. Directed Edge & Attribute Handling

### One-Way vs. Bidirectional Roads
- If `oneway=True`: Normalizes forward directed edge $u \to v$.
- If `oneway=False`: Normalizes forward edge $u \to v$ AND reverse edge $v \to u$. If the reverse edge was not explicitly present in the source edge list, it is synthesized as an opposing `RoadEdge`.

### Speed Limit & Lane Defaults
- **Speed Parsing:** Checks `speed_kph` and `maxspeed` (supports `km/h`, `mph`, numeric strings). Falls back to highway class table (`motorway`: 30.0 m/s, `primary`: 16.67 m/s, `secondary`: 13.89 m/s, `residential`: 8.33 m/s) or default (13.89 m/s).
- **Lanes Parsing:** Integer $\ge 1$. Falls back to highway class table (`motorway`: 3, `primary`: 2, `secondary`: 1) or default (1).

---

## 8. Fallback Policy & Import Metadata

### Fallback Rules
- If acquisition fails (`OSMNotInstalledError`, `OSMServiceUnavailableError`, `OSMTimeoutError`, `OSMEmptyGraphError`) and `allow_fallback=True`:
  - Returns `OSMImportResult` with `source_type="synthetic_fallback"`, `fallback_used=True`.
  - Generates deterministic grid using `config.fallback_config` (or default 4x4 grid with seed 42).
  - Preserves original error type and message in `fallback_reason` and structured metadata.
- If acquisition fails and `allow_fallback=False`:
  - Re-raises the specific exception.
- If `BoundingBox` is invalid:
  - Immediately raises `InvalidBoundingBoxError`. Invalid bounding boxes are NEVER disguised by fallback.

---

## 9. Files Created, Modified, and Removed

### Created
- `backend/apps/core/graph/osm_exceptions.py`
- `backend/apps/core/graph/osm_models.py`
- `backend/apps/core/graph/osm_projector.py`
- `backend/apps/core/graph/osm_normalizer.py`
- `backend/apps/core/graph/osm_acquisition.py`
- `backend/apps/core/graph/osm_service.py`
- `backend/apps/core/tests/test_osm_models_and_projector.py`
- `backend/apps/core/tests/test_osm_normalizer.py`
- `backend/apps/core/tests/test_osm_service_and_fallback.py`
- `docs/progress/PHASE_05.md`

### Modified
- `requirements.txt` (added `osmnx>=2.0.0,<2.1.0`)
- `backend/apps/core/graph/road_graph.py` (added `has_edge_between`)
- `backend/apps/core/graph/__init__.py` (exported OSM types)
- `ARCHITECTURE.md` (documented Section 3.4 OSM subsystem)
- `REQUIREMENTS_TRACEABILITY.md` (updated Phase 5 status)
- `README.md` (documented OSM installation and offline fallback)
- `docs/TESTING.md` (documented Phase 5 test suites)
- `PROJECT_STATUS.md` (updated Phase 5 status to COMPLETED)

---

## 10. Actual Commands Executed & Results

1. `.\.venv\Scripts\pip.exe install "osmnx>=2.0.0,<2.1.0"`: Successfully installed `osmnx-2.0.7` and wheels for Windows. Exit code 0.
2. `.\.venv\Scripts\ruff.exe check backend`: Output: `All checks passed!` (0 errors). Exit code 0.
3. `.\.venv\Scripts\python.exe backend/manage.py check`: Output: `System check identified no issues (0 silenced).` Exit code 0.
4. `.\.venv\Scripts\pytest.exe`: Output: `211 passed in 1.49s`. Exit code 0.

---

## 11. Automated Test Results

- **OSM Models & Projector Tests (`test_osm_models_and_projector.py`):** 31 PASSED
- **OSM Normalizer Tests (`test_osm_normalizer.py`):** 12 PASSED
- **OSM Service & Fallback Tests (`test_osm_service_and_fallback.py`):** 17 PASSED
- **RoadGraph Abstraction Tests (`test_road_graph.py`):** 25 PASSED
- **City Generator Tests (`test_city_generator.py`):** 16 PASSED
- **Domain Value Types Tests (`test_domain_values.py`):** 33 PASSED
- **Domain Models & Invariants Tests (`test_domain_models.py`):** 55 PASSED
- **Serialization Tests (`test_domain_serialization.py`):** 17 PASSED
- **Health Check Regression Tests (`test_health.py`):** 5 PASSED
- **Total:** **211 passed, 0 failed in 1.49s**.

---

## 12. Code Quality & System Checks

- **Ruff Linting:** 0 diagnostics (`All checks passed!`).
- **Django System Check:** 0 issues identified.
- **Phase Boundary Verification:** Zero Dijkstra / A* routing or vehicle agent movement implemented.

---

## 13. Failure-Resolution History

1. **Ruff Line Length Diagnostic:**
   - *Problem:* Initial lines in `osm_models.py`, `osm_normalizer.py`, and `osm_service.py` exceeded 100 characters.
   - *Resolution:* Formatted compound conditionals and parameter lists over multiple lines; re-verified with `ruff check backend`.
2. **Default Fallback Grid Signalized Intersections Initialization:**
   - *Problem:* `DEFAULT_FALLBACK_GRID = CityGridConfig(..., signalized_intersections=True)` raised `GraphValidationError` because `signalized_intersections` must be `None` or a list of `(row, col)` tuples.
   - *Resolution:* Changed `signalized_intersections=None` in `osm_service.py`.
3. **Missing `has_edge_between` on `RoadGraph`:**
   - *Problem:* `normalize_osm_graph` attempted to call `road_graph.has_edge_between(u_id, v_id)`.
   - *Resolution:* Added `has_edge_between(start_node_id, end_node_id) -> bool` to `RoadGraph` in `road_graph.py`.
4. **NetworkX Auto-Created Node in `test_missing_endpoints_skipped`:**
   - *Problem:* `G.add_edge(1, 999, ...)` in NetworkX automatically creates node `999` with empty attributes, causing 1 uninitialized node skip + 1 missing endpoint edge skip (`skipped == 2` instead of 1).
   - *Resolution:* Updated test assertion to `assert skipped == 2` with clear explanatory comments.

---

## 14. CI Workflow Run & Verification

- **GitHub Actions Run:** [Run 39362343593](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39362343593)
- **Trigger:** Push to `main` (commit `2f73161`)
- **Status:** **PASSED (Success)** in 28s
- **Job Details:**
  - `Backend Lint, Test & Coverage`: **PASSED** (ID 118431158250 in 26s)
    - Ruff check: 0 errors
    - Django system check: 0 issues
    - Pytest: 211 passed, 0 failed in 1.40s
  - `Repository Hygiene & Documentation Integrity`: **PASSED** (ID 118431158601 in 4s)
  - `Frontend Lint, Typecheck & Build`: **PASSED** (ID 118431158613 in 6s, deferred cleanly)

---

## 15. Known Issues & Limitations

- **Limitations:** Phase 5 covers road-network ingestion and normalization into `RoadGraph`. Shortest path routing (Dijkstra, A*), travel cost fields, and vehicle simulation are reserved for Phase 6 onwards. Live Overpass downloads require active internet access; offline fallback is automatically engaged when offline.
- **Blockers:** None.

---

## 16. Requirement Traceability Impact

- **FR-03 (Real-World Map Integration):** Core acquisition and normalization foundation complete. Both real-world OSM bounding-box road networks and synthetic fallback grids normalize into `RoadGraph`.
- **FR-04, FR-05, FR-07:** Real-world road topology available for pathfinding algorithms (Phase 6) and simulation agents (Phase 7).
- All 14 functional requirements remain honestly marked as `NOT STARTED` functionally until routing and simulation are completed.

---

## 17. Exact Handoff Instructions for Phase 6

- **Next Phase:** **Phase 06: Route Planning Baseline**.
- **Scope for Phase 6:**
  - Implement shortest-path algorithms on `RoadGraph` using NetworkX Dijkstra and custom A* search.
  - Implement Euclidean distance heuristic using `Position2D.distance_to`.
  - Formulate travel time edge cost: $\text{Cost}(e) = \text{length} / \text{speed\_limit}$.
  - Support edge closures / disabled edges.
  - Provide automated unit tests comparing A* with NetworkX Dijkstra across synthetic and OSM-imported road networks.
