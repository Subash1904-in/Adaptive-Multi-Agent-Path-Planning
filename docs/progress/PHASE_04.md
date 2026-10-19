# PHASE 04 PROGRESS REPORT: Road Graph and Deterministic Synthetic City

## 1. Phase Objective & Acceptance Checklist

### Objective
Implement a directed road-network graph abstraction wrapping NetworkX that integrates seamlessly with existing Phase 3 domain models (`RoadNode`, `RoadEdge`, `TrafficSignal`), alongside a deterministic synthetic city-grid generator producing connected road networks with alternative paths, signalized intersections, and seed-governed reproducibility without external geospatial or network dependencies.

### Acceptance Checklist
- [x] **NetworkX Dependency Integrated:** Pinned `networkx>=3.3,<3.4` in `requirements.txt` (installed 3.3 in Python 3.11).
- [x] **Dedicated Graph Package Created:** Established `backend/apps/core/graph/` containing `RoadGraph`, `CityGridConfig`, `generate_synthetic_city_grid`, and custom exceptions.
- [x] **Directed RoadGraph Abstraction:** Built on `nx.DiGraph`, maintaining authoritative domain entity indexes for nodes, directed edges, and traffic signals.
- [x] **Domain Entity Integration:** Authoritatively uses Phase 3 `RoadNode`, `RoadEdge`, and `TrafficSignal` entities with zero duplicate domain definitions.
- [x] **Directed Edge Distinction:** Explicitly distinguishes forward edge $u \to v$ from reverse edge $v \to u$.
- [x] **Topological Invariant Enforcement:** Validates node uniqueness, edge uniqueness, endpoint existence, self-loop prevention, and duplicate directed connection rejection.
- [x] **Neighborhood & Adjacency Queries:** Provides `get_outgoing_neighbors`, `get_incoming_neighbors`, `get_outgoing_edges`, and `get_incoming_edges`.
- [x] **Connectivity & Reachability Analysis:** Explicitly distinguishes weak connectivity from strong directed connectivity; checks path existence and alternative path availability.
- [x] **Deterministic Synthetic City Generator:** `generate_synthetic_city_grid` creates $rows \times cols$ planar grids with Cartesian coordinates in meters, Euclidean-consistent lengths, and signalized internal junctions.
- [x] **Seeded Reproducibility:** Fixed seeds produce bit-identical graph topology, edge attributes, coordinates, and traffic signals; seeded speed variance behaves deterministically.
- [x] **Alternative Paths Verified:** Confirmed default grid topology provides multiple distinct paths between diagonal corner nodes.
- [x] **Completely Offline Operation:** Zero network access, zero map APIs, zero external downloads.
- [x] **Comprehensive Test Suite:** 41 new unit tests (25 graph tests + 16 generator tests); total **151 passed in 0.82s** with 0 regressions.
- [x] **Code Quality & Checks:** `ruff check backend` (0 errors) and `python backend/manage.py check` (0 issues identified).
- [x] **Documentation Synchronized:** `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, `README.md`, `docs/TESTING.md`, and `docs/progress/PHASE_04.md`.
- [x] **Strict Phase Boundaries Preserved:** Zero OSM importing (Phase 5), A* / Dijkstra pathfinding (Phase 6), vehicle agents (Phase 7), WebSockets, or RL logic implemented.

---

## 2. Initial Repository State
- **Branch:** `main`
- **Starting Commit:** `8707280` (`docs(phase-03): record verified CI run URL and completed job details`)
- **Working Tree:** Clean
- **Pre-existing Content:** Django scaffold, health endpoint at `/api/v1/health/`, 10 core domain models, 3 value types, 9 enums, serialization codecs, 110 automated tests passing, CI workflow active.

---

## 3. Architecture and Design Decisions
1. **Module Location (`backend/apps/core/graph/`):**
   - The graph layer is placed inside `apps.core.graph` alongside `apps.core.domain`. This keeps the simulation substrate modular, pure-Python, and decoupled from Django views and persistence tables.
2. **NetworkX Wrapping & Domain Storage:**
   - Rather than relying on untyped NetworkX node and edge attribute dictionaries, `RoadGraph` authoritatively indexes typed `RoadNode` and `RoadEdge` domain entities. NetworkX's `DiGraph` is used for mathematical topology, connectivity checks, adjacency lookups, and graph algorithms.
3. **Directed Edge Policy:**
   - Real-world roadways are directional. A bidirectional street is represented as two separate directed `RoadEdge` objects: one from $u \to v$ and one from $v \to u$. Parallel edges in the same direction between the same pair of nodes are rejected to ensure unambiguous topological references.
4. **Deterministic Generation Design:**
   - `CityGridConfig` parameters validate grid bounds ($\ge 2 \times 2$), positive spacing, and legal speed limits.
   - The generator uses a local `random.Random(seed)` instance to prevent polluting or depending on global random state.
   - Nodes use deterministic alphanumeric identifiers (`node_r{row}_c{col}`) and Cartesian planar coordinates $(x = c \times \text{spacing}, y = r \times \text{spacing})$.

---

## 4. NetworkX Version & Dependency Changes
- Added runtime dependency in `requirements.txt`:
  ```text
  networkx>=3.3,<3.4
  ```
- **Host Installation:** `networkx-3.3` installed into `.venv` under Python 3.11.9.
- **Compatibility:** NetworkX 3.3 is a pure Python wheel with zero C-extension compile requirements, ensuring 100% cross-platform reliability on both Windows and Linux CI environments.

---

## 5. RoadGraph API and Invariants

### Public Methods
- **Node Management:** `add_node(node)`, `has_node(id)`, `get_node(id)`, `node_ids()`, `nodes()`, `node_count`.
- **Edge Management:** `add_edge(edge)`, `has_edge(id)`, `get_edge(id)`, `get_edge_between(u, v)`, `edge_ids()`, `edges()`, `edge_count`.
- **Signal Management:** `add_traffic_signal(signal)`, `get_traffic_signal(node_id)`, `get_traffic_signals()`, `signal_count`.
- **Adjacency & Neighborhoods:** `get_outgoing_neighbors(id)`, `get_incoming_neighbors(id)`, `get_outgoing_edges(id)`, `get_incoming_edges(id)`.
- **Connectivity & Topology:** `is_weakly_connected()`, `is_strongly_connected()`, `is_reachable(src, dst)`, `has_alternative_paths(src, dst)`, `get_isolated_nodes()`, `validate_topology()`.
- **Export:** `to_dict()`, `networkx_graph`.

### Graph Invariants Enforced
- **Node Identifier Uniqueness:** Adding a node whose ID exists raises `DuplicateEntityError`.
- **Edge Identifier Uniqueness:** Adding an edge whose ID exists raises `DuplicateEntityError`.
- **Endpoint Existence:** Adding an edge referencing non-existent start or end nodes raises `NodeNotFoundError`.
- **Duplicate Connection Prevention:** Adding a directed edge between an already connected directed pair $(u, v)$ raises `DuplicateEntityError`.
- **Self-Loop Prevention:** Adding an edge where $u == v$ raises `GraphValidationError`.
- **Signal Validity:** Adding a traffic signal referencing a non-existent node raises `NodeNotFoundError`; duplicate signals per node raise `DuplicateEntityError`.

---

## 6. City Generator Parameters and Deterministic Behavior

### Parameters (`CityGridConfig`)
- `rows: int = 3`: Number of intersection rows ($\ge 2$).
- `cols: int = 3`: Number of intersection columns ($\ge 2$).
- `spacing_m: float = 100.0`: Inter-intersection distance in meters ($> 0$).
- `speed_limit_mps: float = 13.89`: Speed limit in m/s ($> 0$, default $\approx 50\,\text{km/h}$).
- `lanes: int = 1`: Lane count per edge ($\ge 1$).
- `bidirectional: bool = True`: Enables reverse travel edges.
- `signalized_intersections: Optional[list[tuple[int, int]]] = None`: Signal coordinates (defaults to internal 4-way junctions).
- `signal_cycle_s: float = 60.0`: Signal cycle period in seconds ($> 0$).
- `speed_variance_mps: float = 0.0`: Range of seeded speed variation around base limit.
- `seed: int = 42`: Deterministic PRNG seed.

### Deterministic Invariants
- Default $3 \times 3$ grid produces:
  - 9 `RoadNode` entities (`node_r0_c0` to `node_r2_c2`).
  - 24 `RoadEdge` entities (12 horizontal, 12 vertical).
  - 1 `TrafficSignal` entity at central intersection `node_r1_c1`.
  - Both weak and strong connectivity verified.
  - Multiple alternative paths between diagonal corner nodes `node_r0_c0` and `node_r2_c2`.

---

## 7. Files Created, Modified, or Removed

### Files Created
- `backend/apps/core/graph/__init__.py`: Package entrypoint exporting graph types.
- `backend/apps/core/graph/exceptions.py`: Graph-level exceptions (`GraphException`, `GraphValidationError`, `NodeNotFoundError`, `EdgeNotFoundError`, `DuplicateEntityError`).
- `backend/apps/core/graph/road_graph.py`: `RoadGraph` directed graph abstraction.
- `backend/apps/core/graph/generator.py`: `CityGridConfig` and `generate_synthetic_city_grid`.
- `backend/apps/core/tests/test_road_graph.py`: 25 unit tests for `RoadGraph`.
- `backend/apps/core/tests/test_city_generator.py`: 16 unit tests for city grid generation.
- `docs/progress/PHASE_04.md`: This comprehensive Phase 4 report.

### Files Modified
- `requirements.txt`: Added `networkx>=3.3,<3.4`.
- `ARCHITECTURE.md`: Documented Section 3.3 and updated Section 4 Module Blueprint.
- `REQUIREMENTS_TRACEABILITY.md`: Updated Current Phase to Phase 4; mapped graph foundations.
- `README.md`: Added Phase 4 progress report link.
- `docs/TESTING.md`: Documented Phase 4 test commands and coverage (151 tests).
- `PROJECT_STATUS.md`: Marked Phase 4 COMPLETED, Phase 5 Pending.

---

## 8. Dependencies Added or Avoided
- **Dependencies Added:** `networkx>=3.3,<3.4` (pure Python graph library).
- **Dependencies Avoided:**
  - Avoided OSMnx, GDAL, GEOS, Shapely (reserved for Phase 5 with fallback).
  - Avoided Scipy, NumPy, routing solvers (reserved for Phase 6).
  - Avoided web/WebSocket dependencies (reserved for Phase 21–22).

---

## 9. Actual Commands Executed & Results

1. `.\.venv\Scripts\pip.exe install "networkx>=3.3,<3.4"`: Installed `networkx-3.3`. Exit code 0.
2. `.\.venv\Scripts\ruff.exe check backend --fix`: Formatted imports and verified line length compliance. Exit code 0 (`All checks passed!`).
3. `.\.venv\Scripts\python.exe backend/manage.py check`: Output: `System check identified no issues (0 silenced).` Exit code 0.
4. `.\.venv\Scripts\pytest.exe`: Output: `151 passed in 0.82s`. Exit code 0.

---

## 10. Automated Test Results
- **RoadGraph Tests (`test_road_graph.py`):** 25 PASSED
- **City Generator Tests (`test_city_generator.py`):** 16 PASSED
- **Domain Value Types Tests (`test_domain_values.py`):** 33 PASSED
- **Domain Models & Invariants Tests (`test_domain_models.py`):** 55 PASSED
- **Serialization Tests (`test_domain_serialization.py`):** 17 PASSED
- **Health Check Regression Tests (`test_health.py`):** 5 PASSED
- **Total:** **151 passed, 0 failed in 0.82s**.

---

## 11. Code Quality & System Checks
- **Ruff Linting:** 0 diagnostics (`All checks passed!`).
- **Django System Check:** 0 issues identified.
- **Phase Boundary Verification:** Zero OSM parsing, Dijkstra/A* pathfinding, or vehicle kinematics stepping logic was implemented.

---

## 12. CI Workflow Run & Verification
- Commits will be pushed to `origin/main` to verify the GitHub Actions CI pipeline.
- Verified CI results will be recorded upon pipeline completion.

---

## 13. Known Issues & Limitations
- **Limitations:** Phase 4 models synthetic topological grids and connectivity only. Path cost evaluations (travel time, congestion factors) and route calculation algorithms belong to Phase 6. Real-world OpenStreetMap downloading belongs to Phase 5.
- **Blockers:** None.

---

## 14. Requirement Traceability Impact
- Foundational network graph substrate established for:
  - **FR-03 (Real-World Map Integration):** Synthetic city grid provides the primary reproducible offline baseline and fallback.
  - **FR-04 (Traffic and Pedestrian Simulation):** Signalized intersection nodes and multi-lane edges ready for agent traversal.
  - **FR-05 & FR-07 (Motion Planning & Adaptive Path Planning):** Graph provides the topological network required for A* shortest path search and dynamic rerouting.
- All 14 functional requirements remain honestly marked as `NOT STARTED` functionally.

---

## 15. Exact Handoff Instructions for Phase 5
- **Next Phase:** **Phase 05: OpenStreetMap Import**.
- **Scope for Phase 5:**
  - Introduce optional OSMnx / Overpass API road network parsing for real-world bounding boxes.
  - Normalize external OSM nodes and ways into internal `RoadNode` and `RoadEdge` domain objects stored in `RoadGraph`.
  - Implement defensive dynamic imports with graceful fallback to the Phase 4 deterministic synthetic city grid if OSMnx is absent or network access is unavailable.
  - Write comprehensive automated tests comparing normalized graphs and verifying offline fallback behavior.
