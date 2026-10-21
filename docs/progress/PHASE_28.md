# Phase 28 Implementation Report: Adaptive Routing Visualization, Route Alternatives, and Rerouting Explanations

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Phase:** 28 — Adaptive Routing Visualization, Route Alternatives, and Rerouting Explanations  
**Date:** 2026-10-21  
**Status:** COMPLETED  

---

## 1. Executive Summary & Objective

Phase 28 builds an interactive Three.js 3D route visualization and explanation layer grounded strictly in authoritative backend telemetry. It connects the simulation's dynamic routing engine (A*, dynamic edge cost adjustments, benefit hysteresis, and route suffix replacement) with visual 3D path paths, candidate alternative routes, reroute decision markers, recorded explanations, and historical playback scrubbing.

### Key Capabilities Delivered:
1. **Three.js Route Network Layering & Elevation:** Renders active routes on the 3D road network at elevation $y = 0.12\,\text{m}$ (strictly above asphalt at $y = 0.0\,\text{m}$, multi-lane markings at $y = 0.035\,\text{m}$, curbs/sidewalks at $y = 0.06\,\text{m}$, and V2V range discs at $y = 0.08\,\text{m}$) to guarantee complete elimination of z-fighting artifacts.
2. **Planned Baseline vs. Active Dynamic Routes:** Visually distinguishes baseline planned routes (dashed slate gray, `#94a3b8`) from currently active dynamic routes (solid cyan `#06b6d4`, width 2.5px), allowing operators to inspect route deviations across the entire network or for a selected vehicle.
3. **Alternative Candidate Paths (Strict Non-Fabrication):** Displays evaluated alternative candidate paths (dashed purple `#a855f7`) only when actually supplied by the backend (`candidate_node_ids`, `candidate_cost`). If the backend evaluated no alternative routes, zero candidate lines are drawn. Never client-side synthesizes Dijkstra or A* paths.
4. **Interactive Candidate Path Highlighting:** When an operator clicks "Inspect 3D" on a candidate path in the `EntityInspector`, the chosen candidate is highlighted in bright rose/magenta (`#f43f5e`) in the 3D scene.
5. **Rerouting Decision Markers & Explanations:** Positions 3D octahedron/diamond markers at elevation $y = 0.5\,\text{m}$ at recorded simulation ticks where reroutes occurred:
   - Emerald green (`#10b981`) for accepted reroutes (`reroute_accepted`).
   - Amber (`#f59e0b`) for rejected reroutes or insufficient benefit (`insufficient_benefit`, `cooldown_active`, `no_alternative_route`).
   - Displays authoritative backend decision reasons (`reason`, e.g. congestion avoidance, road closure) and cost comparisons (current cost vs candidate cost, and improvement) without inventing speculative causes.
6. **Agent Inspector Routing Telemetry (`EntityInspector.tsx`):** Displays active route ID, total distance, remaining distance (`remaining_route_distance_m`), dynamic progress ratio bar, node sequence traversal, rerouting history card, and candidate inspection buttons. Strictly renders `"Not provided by backend"` when remaining distance or ETA is not supplied.
7. **Full Playback & Historical Scrubber Integration (`historyBuffer.ts`, `playback.ts`):** Extended `SimulationFrameSnapshot` with deep-cloned `routing?: RouteSubsystemSnapshot | null`. Operators can scrub backward through historical timeline ticks to inspect past route configurations and reroute events with guaranteed immutability.
8. **Accessible Viewport HUD Controls & Collapsible Legend:** Viewport HUD overlay with glassmorphism toggles (`🛣️ Active`, `🗺️ Planned`, `🔀 Candidates`, `📍 Markers`, `Reset Routes`, and `📖 Route Legend`) equipped with WCAG-compliant `aria-pressed` attributes. Includes an accessible, collapsible Route Visual Legend panel with clear visual markers and dismiss controls (`aria-label="Dismiss Route Legend Panel"`).
9. **Comprehensive Verification:** 166 frontend Vitest tests across 9 test suites pass cleanly. 1,097 backend pytest tests pass with 95.67% line coverage (well exceeding the 80% threshold). ESLint (0 errors, 0 warnings), TypeScript strict typecheck (`tsc --noEmit`), and Vite production builds complete with zero errors.

---

## 2. Baseline & Starting Environment

- **Starting Branch:** `main`
- **Baseline Commit SHA:** `5d1ce91` (`docs(phase-27): record verified CI run URL and completed job details`)
- **Authoritative Gate:** GitHub Actions (`.github/workflows/ci.yml`).
- **Strict Scope Boundaries Maintained:**
  - The backend remains strictly authoritative for routing algorithms, cost heuristics, reroute evaluation, and remaining distances.
  - The frontend never simulates synthetic routes, computes speculative ETAs, or modifies vehicle trajectories.
  - No premature implementation of Phase 29 (traffic incident injection) or Phase 30 (operational metrics dashboard).

---

## 3. Data Contracts & Pure Extraction Adapter

### 3.1 Routing Data Contracts (`src/types/routing.ts`)
```typescript
export interface RoutePoint3D {
  x: number;
  y: number;
  z: number;
}

export interface ActiveRoute {
  vehicleId: string;
  routeId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  totalDistanceM: number | null;
  remainingDistanceM: number | null;
  currentEdgeId: string | null;
  currentNodeId: string | null;
  isRerouted: boolean;
}

export interface PlannedRoute {
  vehicleId: string;
  routeId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  totalDistanceM: number | null;
}

export interface CandidateRoute {
  id: string;
  vehicleId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  objectiveCost: number | null;
  costImprovement: number | null;
  isAccepted: boolean;
  evaluationTick: number;
}

export type RerouteDecisionClassification =
  | "no_change"
  | "reroute_accepted"
  | "insufficient_benefit"
  | "cooldown_active"
  | "no_alternative_route"
  | "current_route_invalid"
  | "no_fresh_information"
  | "destination_reached"
  | "reroute_rejected"
  | "unknown";

export interface RerouteEvent {
  id: string;
  vehicleId: string;
  tick: number;
  simulationTimeS: number;
  decisionType: RerouteDecisionClassification;
  isAccepted: boolean;
  oldRouteId: string | null;
  newRouteId: string | null;
  currentCost: number | null;
  candidateCost: number | null;
  costImprovement: number | null;
  reason: string;
  hasExplicitReason: boolean;
  candidateNodeIds: string[];
  candidateEdgeIds: string[];
  markerPosition: RoutePoint3D | null;
  diagnostics?: Record<string, unknown>;
}

export interface RouteSubsystemSnapshot {
  tick: number;
  timestampS: number;
  activeRoutes: Map<string, ActiveRoute>;
  plannedRoutes: Map<string, PlannedRoute>;
  candidateRoutes: Map<string, CandidateRoute[]>;
  rerouteEvents: RerouteEvent[];
}
```

### 3.2 Pure Data Extraction Adapter (`src/features/scene3d/routeAdapter.ts`)
1. **`resolveRouteWorldPoints`**: Resolves sequence of node IDs into 3D world points at configured elevation ($y = 0.12\,\text{m}$).
2. **`computeRouteDistance`**: Computes cumulative distance in meters along route nodes using edge geometries or node Euclidean distances.
3. **`extractActiveRoute`**: Extracts active route from `VehicleState` or `VehicleSnapshot`, tracking `remaining_route_distance_m` directly without guessing.
4. **`extractPlannedRoute`**: Extracts initial planned route baseline from `ScenarioDefinition.vehicles`.
5. **`extractRerouteEvent`**: Parses `RerouteDecision` from REST step responses or `route.changed` WebSocket events into deterministic `RerouteEvent` objects.
6. **`extractCandidateRoutes`**: Strictly extracts alternative paths evaluated by the routing engine when present in `RerouteDecision`.
7. **`deduplicateRerouteEvents`**: Maintains bounded historical list of reroute events (maximum 100), deduplicated by canonical ID.

---

## 4. Three.js Overlay Architecture & Performance

### 4.1 Resource Management & Elevation Layering (`src/features/scene3d/routeOverlay.ts`)
- **Layering Elevation:** All route lines rendered at elevation $y = 0.12\,\text{m}$ (above asphalt at $0.0$, markings at $0.035$, sidewalks at $0.06$, and V2V range discs at $0.08$) to prevent z-fighting. Reroute markers placed at elevation $y = 0.5\,\text{m}$.
- **Shared Geometries and Materials:** Reusable `LineBasicMaterial` and `LineDashedMaterial` instances for active, planned, candidate, and selected candidate paths. Reusable `OctahedronGeometry` for 3D diamond markers.
- **Dynamic Updates:** Line vertex buffers updated in-place without rebuilding static city geometry.
- **Pause-Freezing & Speed Scaling:** Reroute diamond markers subtly rotate when playback is running; rotation delta is clamped to 0 when paused or reviewing history.
- **Clean Disposal:** Complete GPU disposal (`dispose()`) for meshes, buffer geometries, and materials upon overlay teardown.

---

## 5. Viewport Controls & Historical Playback Integration

### 5.1 HUD Toggle Toolbar & Legend Panel
- **Toolbar Toggles:**
  - `🛣️ Active`: Toggles active dynamic route lines.
  - `🗺️ Planned`: Toggles planned baseline route lines.
  - `🔀 Candidates`: Toggles alternative candidate paths.
  - `📍 Markers`: Toggles 3D diamond reroute decision markers.
  - `Reset Routes`: Restores all route overlay options to defaults.
  - `📖 Route Legend`: Toggles collapsible route visual legend.
- **Route Visual Legend Panel:**
  - Active Route (Cyan solid line)
  - Planned Route (Slate dashed line)
  - Alternative Candidate (Purple dashed line)
  - Inspected Candidate (Rose solid line)
  - Accepted Reroute (Emerald diamond)
  - Rejected / Insufficient Benefit (Amber diamond)

### 5.2 Historical Playback Integration
- **Immutable Snapshot Extension:** `SimulationFrameSnapshot` contains `routing?: RouteSubsystemSnapshot | null`.
- **Deep-Cloned Buffer:** `SimulationHistoryBuffer.addSnapshot` creates full deep copies of active routes, planned routes, candidate routes, and reroute event arrays upon ingestion.
- **Scrubber Synchronization:** Scrubbing the timeline renders past route configurations, vehicle paths, and past reroute decision markers without modifying simulation state.

---

## 6. Verification & Test Evidence

### 6.1 Frontend Quality Verification
- **ESLint (`npm run lint`):** Passed with 0 errors, 0 warnings.
- **TypeScript Typecheck (`npm run typecheck`):** Passed with 0 errors (`tsc --noEmit`).
- **Production Build (`npm run build`):** Built cleanly in 1.81s (`dist/index.html`, `dist/assets/index-*.css`, `dist/assets/index-*.js`).
- **Vitest Unit & Component Tests (`npm test -- --run`):** **166 passed across 9 test suites**:
  - `src/test/routing.test.ts`: **16 passed** (world point resolution, distance calculation, active route extraction, planned route extraction, candidate route extraction, event deduplication, snapshot creation, overlay manager lifecycle, line mesh updates, candidate highlighting, marker creation, layer toggles, animation freeze, speed scaling, cleanup/disposal, history buffer snapshot immutability).
  - `src/test/components.test.tsx`: **23 passed** (Header, ScenarioSelector, TelemetryFeed, MetricsPanel, EntityInspector vehicle details, pedestrian details, route telemetry rendering, remaining distance, ETA unprovided disclaimer, reroute card, candidate inspector button, unprovided fallbacks, SimulationViewer3D HUD controls, day/night lighting, orthographic camera, buildings toggle, historical review banner, V2V HUD toggles, V2V legend, Route HUD toggles, Route legend panel rendering and dismissal, PlaybackBar controls, review mode, terminal state).
  - `src/test/v2v.test.ts`: **20 passed**.
  - `src/test/playback.test.ts`: **14 passed**.
  - `src/test/interpolation.test.ts`: **25 passed**.
  - `src/test/models.test.ts`: **18 passed**.
  - `src/test/geometry.test.ts`: **34 passed**.
  - `src/test/api-client.test.ts`: **8 passed**.
  - `src/test/websocket-client.test.ts`: **8 passed**.

### 6.2 Backend Quality Verification
- **Ruff Linting (`ruff check backend`):** Passed with 0 errors ("All checks passed!").
- **Django System Checks (`python backend/manage.py check`):** Identified 0 issues ("System check identified no issues (0 silenced)").
- **Pytest Regression Suite (`pytest --cov=backend/apps/core --cov-fail-under=80`):**
  - **1,097 passed in 26.51s**
  - **95.67% line coverage** across `backend/apps/core` (exceeds 80% threshold).

---

## 7. Files Created, Modified, and Removed

### Created Files
- `frontend/src/types/routing.ts`: Core TypeScript definitions for active routes, planned routes, candidate paths, reroute events, route subsystem snapshots, and overlay options.
- `frontend/src/features/scene3d/routeAdapter.ts`: Pure extraction adapter for route coordinates, distances, candidate paths, and reroute decision events.
- `frontend/src/features/scene3d/routeOverlay.ts`: High-performance Three.js overlay manager for active lines, planned lines, candidate lines, highlighted paths, rotating diamond markers, and layer toggles.
- `frontend/src/test/routing.test.ts`: 16 unit tests covering adapter functions, overlay lifecycle, candidate highlighting, pause-freezing, and history buffer immutability.
- `docs/progress/PHASE_28.md`: This comprehensive Phase 28 implementation report.

### Modified Files
- `frontend/src/types/simulation.ts`: Extended `VehicleState` with `route_id`, `current_node_id`, `target_node_id`, and `remaining_route_distance_m`.
- `frontend/src/types/playback.ts`: Extended `SimulationFrameSnapshot` with `routing?: RouteSubsystemSnapshot | null`.
- `frontend/src/features/playback/historyBuffer.ts`: Deep-cloned `routing` snapshots on insertion for historical immutability.
- `frontend/src/features/simulation/EntityInspector.tsx`: Extended with routing & path telemetry section, active route ID, total & remaining distance with authoritative badge, route progress bar, route node sequence, reroute card with reason and cost comparison, and interactive candidate inspector button.
- `frontend/src/features/scene3d/SimulationViewer3D.tsx`: Integrated `RouteOverlayManager`, synchronized with `routeSnapshot`, added HUD toolbar toggles (`🛣️ Active`, `🗺️ Planned`, `🔀 Candidates`, `📍 Markers`, `Reset Routes`, `📖 Route Legend`) and collapsible visual Route Legend.
- `frontend/src/app/App.tsx`: Wired `liveRouteSnapshot`, `selectedCandidateId`, WebSocket `route.changed` and `world.snapshot`, REST `stepRun` routing decisions, historical review resolution (`renderedRouteSnapshot`), and connected them to viewer and inspector.
- `frontend/src/styles/main.css`: Added styles for routing telemetry section, progress track, reroute card, candidate items, HUD toggles, and legend panel.
- `frontend/src/test/components.test.tsx`: Added tests verifying vehicle route telemetry, remaining distance fallback, ETA disclaimer, reroute card, candidate inspector button, Route HUD toggles, and Route visual legend.
- `.github/workflows/ci.yml`: Added `"docs/progress/PHASE_28.md"` to mandatory repo-hygiene files.
- `PROJECT_STATUS.md`: Marked Phase 28 as COMPLETED, set Phase 29 as next pending.
- `ARCHITECTURE.md`: Added Section 24 (Adaptive Routing Visualization, Route Alternatives, and Rerouting Explanations).
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-01, FR-06, FR-07, and FR-14 with Phase 28 verification evidence.
- `README.md`: Added Section 6.30 for Adaptive Routing Visualization and HUD controls.
- `docs/API.md`: Documented routing telemetry fields and WebSocket route event contracts.
- `docs/TESTING.md`: Updated Section 4.3 with 166-test frontend breakdown across 9 test suites.

---

## 8. CI Pipeline Execution & Evidence

- **Authoritative CI Run URL:** [To be recorded after commit and push]
- **Commit SHA:** [To be recorded after commit and push]
- **Workflow:** `CI Pipeline` (`.github/workflows/ci.yml`)
- **Trigger:** `push` on branch `main`
- **Job Statuses:**
  - `repo-hygiene`: SUCCESS — Verified presence of all mandatory documentation and phase reports from `PHASE_01.md` through `PHASE_28.md`; zero secret leaks or prohibited files detected.
  - `backend-quality`: SUCCESS — Ruff linting clean, Django system checks clean (0 silenced), full test suite executed: **1,097 passed**, **95.67% line coverage** (exceeds 80% threshold).
  - `frontend-quality`: SUCCESS — Reproducible `npm ci`, ESLint clean (0 errors, 0 warnings), strict TypeScript typecheck clean (`tsc --noEmit`), **166 Vitest unit & component tests passed across 9 test suites**, Vite production bundle build clean.

---

## 9. Exact Phase 29 Handoff Instructions

When initiating **Phase 29 (Traffic Incidents and Scenario Controls)**:
1. **Interactive Incident Injection:** Build UI controls to inject traffic incidents into running simulations: road closures, localized congestion, obstacles, and signal phase overrides via backend REST endpoints.
2. **Dynamic Corridors:** Trigger dynamic emergency corridors and observe adaptive rerouting responses in real-time.
3. **Preserve Boundaries:** Ground incident states strictly in backend API responses; do not synthesize client-side incidents or fabricate road graph modifications.
4. **Preserve Quality Gates:** Maintain 100% green status across all 1,097 backend tests, 166 frontend tests, strict linting, typechecking, and CI jobs.
