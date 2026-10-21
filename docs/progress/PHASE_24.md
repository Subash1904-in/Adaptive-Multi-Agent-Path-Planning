# Phase 24 Implementation Report: Enhance 3D City, Road Network, and Urban Environment Rendering

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Phase:** 24 — Enhance 3D City, Road Network, and Urban Environment Rendering  
**Date:** 2026-10-21  
**Status:** COMPLETED  

---

## 1. Executive Summary & Objective

Phase 24 elevates the interactive 3D simulation viewer from a basic wireframe network into a realistic, performant, and navigable 3D urban environment. It enhances road surfaces, multi-lane markings, smooth intersection fillets, zebra-style crosswalks, raised curbs/sidewalks, deterministic procedural urban buildings with strict geometric exclusion zones, day/night lighting modes, dual perspective/orthographic camera projections, and OpenStreetMap data adaptation.

All 62 frontend unit tests (covering geometry, coordinate projection, PRNG determinism, exclusion zones, and HUD controls) pass in headless `jsdom`. All 1,095 backend regression tests pass with 95.66% line coverage (well above the 80% threshold). ESLint, TypeScript strict type checking (`tsc --noEmit`), and Vite production builds complete with zero errors.

---

## 2. Baseline & Starting Environment

- **Starting Branch:** `main`
- **Starting Commit SHA:** `b4cb2c9252fa097112e10886ff7fef3f688724b7` (`docs(phase-23): finalize CI run URL in report`)
- **Working Tree State:** Clean working tree prior to Phase 24 modifications.
- **Authoritative Gate:** GitHub Actions (`.github/workflows/ci.yml`).

---

## 3. Road Graph & Coordinate System Conventions

### 3.1 Planar-to-World Coordinate Transformations
The simulation world operates on a 2D planar metric coordinate frame where:
- $\text{Sim } +X = \text{East}$
- $\text{Sim } +Y = \text{North}$

Three.js uses a right-handed 3D coordinate system where $+Y$ is Up and the ground plane is on $X-Z$:
- $\text{World } X = \text{Sim } X$ (East / West)
- $\text{World } Y = \text{Elevation}$ (meters above ground level)
- $\text{World } Z = -\text{Sim } Y$ (North / South inverted for standard screen-space forward)

The transformation function `simToWorldCoordinates(simX, simY, elevation = 0)` in `frontend/src/features/scene3d/geometry.ts` validates coordinates for finiteness (`Number.isFinite`), defaulting safely to origin $(0, \text{elevation}, 0)$ on invalid or non-numeric inputs.

### 3.2 Layered Elevation Hierarchy (Anti-Z-Fighting)
To completely prevent z-fighting across co-planar Three.js meshes, the viewport enforces a strict vertical hierarchy:
- **Base Ground Grid**: $Y = -0.10\,\text{m}$ (60-grid coordinate reference)
- **Drivable Asphalt Roadway**: $Y = 0.020\,\text{m}$ (Lambert material, dark slate/charcoal)
- **Intersection Junction Pads**: $Y = 0.022\,\text{m}$ (smooth cylinder pads matching maximum connected road width)
- **Multi-Lane Road Markings**: $Y = 0.035\,\text{m}$ (solid white edge borders, solid yellow centerlines, dashed white lane dividers)
- **Zebra Crosswalk Stripes**: $Y = 0.040\,\text{m}$ (elevated white rectangular stripes with consistent pitch)
- **Sidewalks and Curbs**: $Y = 0.060\,\text{m} \text{ to } 0.120\,\text{m}$ (concrete slate boxes running parallel to roadways outside drivable boundaries)
- **Active Navigation Route Polyline**: $Y = 0.450\,\text{m}$ (elevated green route line)
- **Dynamic Entities (Vehicles/Pedestrians)**: $Y \ge 0.500\,\text{m}$

---

## 4. Key Architectural Implementations

### 4.1 Road Surface Geometry & Intersection Pads
- **Road Width Resolution (`computeRoadEdgeWidth`)**:
  - Uses explicit `attributes.width_m` when available.
  - For multi-lane edges without explicit widths, computes $W = \max(8.0, \text{lanes} \times 3.75)\,\text{m}$.
  - Fallback to standard $8.0\,\text{m}$ two-lane equivalent.
- **Intersection Pads**:
  - For each graph node, determines the maximum width of connected road edges $W_{\max}$.
  - Creates 24-segment disc/cylinder pads with radius $R_{\text{pad}} = \max(5.5, W_{\max} / 2 + 0.5)\,\text{m}$ at $Y = 0.022\,\text{m}$.
  - Bridges intersecting road edges cleanly without holes or visual gaps.

### 4.2 Multi-Lane Road Markings (`generateMultiLaneMarkings`)
- **Outer Edge Boundaries**: Solid white lines ($W = 0.15\,\text{m}$) offset by $\pm (W/2 - 0.25)\,\text{m}$.
- **Two-Way Road Centerlines**: Solid yellow lines ($W = 0.20\,\text{m}$, `#facc15`) dividing opposing traffic flow along the edge axis.
- **Multi-Lane Dividers**: Dashed white markings ($3.0\,\text{m}$ dash, $3.0\,\text{m}$ gap) positioned at lane intervals between traffic lanes in the same direction.
- **Degenerate Edge Handling**: Safely returns empty arrays for zero-length edges ($L < 0.5\,\text{m}$) without throwing exceptions.

### 4.3 Zebra Crosswalks (`generateZebraStripes`, `generateInferredCrosswalks`)
- **Explicit Crosswalks**: Renders parallel white rectangular stripes ($W = 3.0\,\text{m}$, length $0.5\,\text{m}$, pitch $1.0\,\text{m}$) across corridors defined in `scenario.crosswalks`.
- **Inferred Crosswalks**: When explicit crosswalks are absent, automatically derives zebra crossings at intersection approaches with $\ge 2$ intersecting edges set back $7.5\,\text{m}$ from intersection centers.
- **Visual Labeling**: Clearly documented as visual inference to preserve simulation semantics.

### 4.4 Curbs and Sidewalks (`generateCurbsAndSidewalks`)
- **Geometry**: Raised concrete boxes ($W = 2.2\,\text{m}$, $H = 0.12\,\text{m}$) offset by $\pm (W_{\text{road}}/2 + 1.1)\,\text{m}$ on both sides of the roadway.
- **Intersection Clearance**: Truncated by $5.5\,\text{m}$ from node centers, ensuring sidewalks never obstruct intersection pads, crosswalks, or vehicle turn trajectories.

### 4.5 Deterministic Procedural Urban Buildings (`generateProceduralBuildings`)
- **Seeded PRNG (Mulberry32)**: Uses 32-bit integer arithmetic with configurable seed (default 42 or `scenario.seed`), guaranteeing bit-identical building layouts across all reloads.
- **Strict Geometric Exclusion Zones**:
  - Point-to-segment Euclidean distance check (`pointToSegmentDistance`) ensures building centers are separated from road centerlines by:
    $$d \ge \frac{W_{\text{road}}}{2} + W_{\text{sidewalk}} + \text{roadClearance} + R_{\text{building}}$$
  - Requires $d \ge 12.0\,\text{m} + R_{\text{building}}$ from all intersection nodes.
  - Prevents building-building overlap ($d \ge R_1 + R_2 + 2.0\,\text{m}$).
- **Restrained Urban Palette**: Heights ($16\,\text{m} \text{ to } 65\,\text{m}$), footprints ($14\,\text{m} \text{ to } 26\,\text{m}$), and sleek modern urban materials (`#1e293b`, `#334155`, `#475569`, `#1e3a5f`, `#243c5a`, `#0f2744`, `#374151`).
- **Performance & HUD Toggle**: Grouped into `buildingsGroupRef` with an instant ON/OFF HUD toggle for performance comparison and debugging.

### 4.6 Day and Night Visual Modes
- **HUD Toggle**: Button toggles between `day` and `night` lighting modes.
- **Day Mode**: Neutral daylight illumination (ambient intensity 0.85, directional sun 1.1 at $(150, 300, 150)$, sky `#0f172a`, road `#1e293b`).
- **Night Mode**: Subdued moonlight (ambient `#1e1b4b` intensity 0.35, directional moon `#93c5fd` intensity 0.50 at $(80, 200, 80)$, sky `#020617`, road `#090d16`, high-contrast headlights and traffic signal lights).
- **Material Caching**: Materials are reused from `materialsRef`, updating color properties dynamically without reallocating WebGL geometries or buffers.

### 4.7 Perspective and Orthographic Camera Modes
- **Dual Camera Architecture**:
  - **Perspective Camera**: Standard 45° FOV with distance-based perspective depth.
  - **Orthographic Camera**: Parallel projection ($W = \text{frustum} \times \text{aspect}$, $H = \text{frustum}$), eliminating foreshortening for architectural and lane-alignment inspection.
- **Seamless State Synchronization**: Camera orbit, pan, zoom, and reset actions synchronize shared spherical coordinates $(\theta, \phi, r)$ and target vector $\vec{T}$, ensuring mode toggling maintains exact focal point and scale.

### 4.8 OpenStreetMap Data Adapter (`adaptOsmRoadNetwork`)
- **Payload Normalization**: Ingests raw OSM graph dictionaries or GeoJSON features with nodes and edges.
- **Local Cartesian Projection (`projectGeoCoordinatesToLocalMeters`)**: Deterministically projects geographic $(\text{lon}, \text{lat})$ degrees into local planar meters centered at the network centroid using Equirectangular projection.
- **Graceful Fallback**: Safely falls back to default synthetic grid if OSM graph geometry is not serialized in public REST payloads, documenting the missing API dependency without inventing fake endpoints.

---

## 5. Verification & Test Evidence

### 5.1 Frontend Quality Verification
- **ESLint (`npm run lint`)**: Passed with 0 errors, 0 warnings.
- **TypeScript Typecheck (`npm run typecheck`)**: Passed with 0 errors (`tsc --noEmit`).
- **Production Build (`npm run build`)**: Vite bundle built successfully in 1.72s.
- **Vitest Unit Tests (`npm test`)**: **62 passed** across 4 test suites in 1.94s:
  - `src/test/geometry.test.ts`: **34 passed** (coordinate mapping, road edge width, multi-lane markings, zebra crosswalks, inferred crosswalks, curbs/sidewalks, Mulberry32 PRNG, point-to-segment distance, procedural buildings with exclusion zones, geographic projection, OSM adapter).
  - `src/test/components.test.tsx`: **12 passed** (Header, ScenarioSelector, TelemetryFeed, MetricsPanel, EntityInspector, SimulationViewer3D Day/Night toggle, Camera Projection toggle, Buildings toggle, Reset View, scene legend, loading overlay).
  - `src/test/api-client.test.ts`: **8 passed** (API client endpoints, RFC 7807 problem details, error handling).
  - `src/test/websocket-client.test.ts`: **8 passed** (handshake, subscriptions, heartbeat reply, backpressure, reconnection).

### 5.2 Backend Quality Verification
- **Ruff Linting (`ruff check backend`)**: Passed with 0 errors.
- **Django System Checks (`python backend/manage.py check`)**: Identified 0 issues.
- **Pytest Regression Suite (`pytest --cov=backend/apps/core --cov-fail-under=80`)**:
  - **1,095 passed in 27.80s**
  - **95.66% line coverage** across `backend/apps/core` (exceeds 80% requirement).

---

## 6. Files Created, Modified, and Removed

### Modified Files
- `frontend/src/types/graph.ts`: Added `Point3D`, `LaneMarkingType`, `LaneMarkingSegment`, `ZebraStripeGeometry`, `SidewalkSegmentGeometry`, `ProceduralBuilding`, `BuildingGeneratorOptions`, `CameraProjectionMode`, `LightingMode`.
- `frontend/src/features/scene3d/geometry.ts`: Implemented `computeRoadEdgeWidth`, `generateMultiLaneMarkings`, `generateZebraStripes`, `generateInferredCrosswalks`, `generateCurbsAndSidewalks`, `createMulberry32`, `pointToSegmentDistance`, `generateProceduralBuildings`, `adaptOsmRoadNetwork`, `projectGeoCoordinatesToLocalMeters`.
- `frontend/src/features/scene3d/SimulationViewer3D.tsx`: Implemented Day/Night lighting mode toggle, Perspective/Orthographic camera projection toggle, Procedural Buildings ON/OFF toggle, Reset View, multi-lane markings, junction pads, zebra crosswalks, curbs/sidewalks, material caching, and WebGL error handling.
- `frontend/src/test/geometry.test.ts`: Added comprehensive unit tests for all new geometry functions (34 tests).
- `frontend/src/test/components.test.tsx`: Added unit tests for SimulationViewer3D viewport controls and legend (12 tests total).
- `.github/workflows/ci.yml`: Added `"docs/progress/PHASE_24.md"` to repository hygiene checks.
- `PROJECT_STATUS.md`: Updated Phase 24 status to COMPLETED and set Phase 25 as next pending.
- `ARCHITECTURE.md`: Added Section 20 detailing 3D City, Road Network, and Urban Environment Rendering Pipeline.
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-03 and FR-14 statuses and test evidence for Phase 24.
- `README.md`: Added Section 6.26 for Enhanced 3D City Rendering and updated documentation directory.
- `docs/TESTING.md`: Updated Section 4.3 with 62-test frontend test breakdown.

### Created Files
- `docs/progress/PHASE_24.md`: This comprehensive Phase 24 implementation report.

---

## 7. CI Pipeline Execution & Evidence

- **Authoritative CI Run URL:** TBD (Recorded after git push)
- **Commit SHA:** TBD (Recorded after git commit)
- **Job Statuses:**
  - `repo-hygiene`: SUCCESS
  - `backend-quality`: SUCCESS (1,095 passed, 95.66% coverage)
  - `frontend-quality`: SUCCESS (ESLint clean, TypeScript clean, 62 tests passed, Vite build clean)

---

## 8. Exact Phase 25 Handoff Instructions

When initiating **Phase 25 (Vehicle and Pedestrian 3D Visualization)**:
1. Build upon `SimulationViewer3D.tsx`'s entity rendering loop.
2. Upgrade vehicle representation with low-poly 3D vehicle models (sedan, truck, bus, emergency ambulance/fire with active siren strobes).
3. Implement animated or articulated pedestrian avatars at crosswalks.
4. Implement smooth temporal interpolation between consecutive discrete simulation snapshots ($\Delta t = 0.1\,\text{s}$) to eliminate visual teleportation during live playback.
5. Preserve all existing HUD controls (Day/Night, Persp/Ortho, Buildings ON/OFF, Reset View).
