# Phase 25 Implementation Report: Enhance Vehicle and Pedestrian Models, Animation, and Temporal Interpolation

**Project:** Adaptive Multi-Agent Path Planning for Autonomous Vehicles (AMAPP)  
**Phase:** 25 — Enhance Vehicle and Pedestrian Models, Animation, and Temporal Interpolation  
**Date:** 2026-10-21  
**Status:** COMPLETED  

---

## 1. Executive Summary & Objective

Phase 25 enhances the interactive 3D simulation viewer by replacing primitive bounding box representations with low-poly procedural vehicle and articulated pedestrian models, introducing presentation-only emergency beacon lighting, and implementing a deterministic temporal interpolation engine with shortest-path angular heading lerp.

### Key Capabilities Delivered:
1. **Procedural Low-Poly 3D Vehicle Models:** Custom procedural geometries with distinct profiles, palettes, cabins, wheels, windshields, headlights, and taillights for 5 distinct classes (`sedan`, `truck`, `bus`, `ambulance`, `fire_engine`) plus a robust fallback (`unknown`).
2. **Specialized Emergency Visual Accents:** Realistic presentation cues including medical red cross emblems for ambulances and roof-mounted silver utility ladders for fire engines.
3. **Presentation-Only Emergency Beacon Lighting:** Dual-beacon lightbars with 2.5 Hz alternating blue/red emissive strobes when active, dimmed when inactive, and steady static glow when `prefers-reduced-motion` is detected for accessibility compliance.
4. **Articulated Pedestrian Avatars:** Humanoid avatars with torso, head, and articulated leg pivot groups animated with velocity-driven sinusoidal walking swings ($v > 0.05\,\text{m/s}$).
5. **Deterministic Temporal Interpolation Engine (`EntityInterpolationBuffer`):** Pure TypeScript interpolation engine providing smooth 60 FPS visual motion between 10 Hz discrete simulation snapshots. Features linear planar position lerp, shortest-path angular heading lerp across the $0 \leftrightarrow 2\pi$ wraparound boundary, simulation heading to Three.js rotation mapping, duplicate/out-of-order sample rejection, bounded history pruning ($\le 10$ samples), bounded forward extrapolation ($\le 0.15\,\text{s}$), and stale entity detection ($> 1.0\,\text{s}$).
6. **Decoupled 60 FPS Animation Loop:** Viewport `requestAnimationFrame` loop queries interpolation buffers and directly mutates Three.js mesh transforms without triggering React component re-renders.
7. **Zero Per-Frame Allocations (`ModelAssetCache`):** Centralized asset cache ensuring vehicle and pedestrian meshes share reusable geometries and materials, eliminating WebGL memory leaks and garbage collection hitches.
8. **Entity Inspector Enhancements:** Displays model classification (title-cased), emergency status, priority level, tick/timestamp telemetry metadata, and live interpolated vs. stale data indicators.
9. **Rigorous Verification:** 107 frontend Vitest tests across 6 test suites pass cleanly. 1,095 backend pytest tests pass with 95.66% line coverage (well exceeding the 80% threshold). ESLint, TypeScript strict typecheck (`tsc --noEmit`), and Vite production builds complete with zero errors.

---

## 2. Baseline & Starting Environment

- **Starting Branch:** `main`
- **Baseline Commit SHA:** `c7f3950478df90a78ca83d470559eb482a5c317d` (`docs(phase-24): finalize CI run URL and completed job details in report`)
- **Authoritative Gate:** GitHub Actions (`.github/workflows/ci.yml`).
- **Strict Scope Boundaries Maintained:**
  - Rendering interpolation and animation cues are strictly presentation-only.
  - The frontend never invents simulation routes, advances authoritative simulation time ($t_{\text{sim}}$, ticks), overrides emergency priority, or calculates collisions.
  - No premature implementation of Phase 26+ features (interactive play/pause/step controls, V2V wireless link overlays, route comparison tools, incident injection controls, or RL benchmarks).

---

## 3. Vehicle Models Architecture & Geometry Details

### 3.1 Model Classification (`classifyVehicleType`)
The classifier maps vehicle attributes to one of five concrete model types:
- **`ambulance`**: Matches `emergency_type == "AMBULANCE"` or vehicle ID starting with `amb_` / containing `ambulance`.
- **`fire_engine`**: Matches `emergency_type == "FIRE_ENGINE"` or vehicle ID starting with `fire_` / containing `fire`.
- **`bus`**: Matches vehicle ID starting with `bus_` or containing `bus`.
- **`truck`**: Matches vehicle ID starting with `truck_` or containing `truck` / `cargo`.
- **`sedan`**: Default standard passenger car class.
- **`unknown`**: Fallback neutral compact box for unspecified or malformed entities.

### 3.2 Procedural Model Specifications
All vehicles feature a unified local coordinate frame where the vehicle points towards $+Z$ (Local Forward) with origin at ground contact ($Y = 0$).

| Model Class | Dimensions ($W \times H \times L$) | Base Body Color | Distinctive Geometric Features |
| :--- | :--- | :--- | :--- |
| **Sedan** | $1.8\,\text{m} \times 1.4\,\text{m} \times 4.2\,\text{m}$ | Royal Blue (`#2563eb`) | Sleek lower chassis, tapered glass cabin, dark charcoal bumper/trim, 4 rubber wheels, headlights (`#fef08a`), taillights (`#ef4444`). |
| **Truck** | $2.4\,\text{m} \times 2.8\,\text{m} \times 7.0\,\text{m}$ | Amber/Orange (`#d97706`) | Elevated cab, large rectangular cargo box (`#78716c`), dark undercarriage, 6 rubber wheels. |
| **Bus** | $2.5\,\text{m} \times 3.0\,\text{m} \times 10.0\,\text{m}$ | Emerald Green (`#059669`) | Elongated passenger body, panoramic side window bands, front destination display, 6 rubber wheels. |
| **Ambulance** | $2.2\,\text{m} \times 2.4\,\text{m} \times 5.5\,\text{m}$ | Pure White (`#f8fafc`) | High-visibility emergency box with reflective orange-red side stripes, red cross emblems on left/right panels, dual roof lightbars. |
| **Fire Engine** | $2.5\,\text{m} \times 2.9\,\text{m} \times 8.0\,\text{m}$ | Crimson Red (`#dc2626`) | Heavy-duty fire truck body, equipment compartments, roof-mounted silver utility ladder, high-intensity emergency lightbars. |
| **Unknown** | $1.8\,\text{m} \times 1.4\,\text{m} \times 4.0\,\text{m}$ | Slate Gray (`#64748b`) | Compact rounded chassis box with neutral cabin and wheels. |

### 3.3 Zero Per-Frame Allocations (`ModelAssetCache`)
Instantiating Three.js `BufferGeometry` or `MeshLambertMaterial` instances on every frame causes catastrophic memory leaks and garbage collection stutters. The `ModelAssetCache` singleton pre-instantiates shared geometries and materials:
- **Shared Geometries:** Chassis boxes, cabin boxes, cylinder wheels, glass window panes, light boxes, and cross emblems are created once and reused across all entity instances.
- **Shared Materials:** Opaque Lambert materials (body colors, wheel rubber, bumper slate, glass) are pooled and reused. Only emergency beacon materials require dynamic emissive updates during animation.

---

## 4. Articulated Pedestrian Model & Walking Animation

### 4.1 Hierarchical Avatar Structure
Pedestrian models are constructed with an articulated hierarchical structure:
- **Root Group:** Positioned at $(X, 0, Z)$ on the ground plane.
- **Torso Mesh:** Box geometry ($0.45\,\text{m} \times 0.65\,\text{m} \times 0.25\,\text{m}$) in indigo (`#4f46e5`) at $Y = 0.95\,\text{m}$.
- **Head Mesh:** Box geometry ($0.25\,\text{m} \times 0.25\,\text{m} \times 0.25\,\text{m}$) in warm peach (`#fed7aa`) at $Y = 1.45\,\text{m}$.
- **Left Leg Pivot Group:** Pivot positioned at hip joint $(+0.12, 0.65, 0)\,\text{m}$. Contains leg mesh ($0.16\,\text{m} \times 0.65\,\text{m} \times 0.18\,\text{m}$) in charcoal (`#1e293b`) extending downwards.
- **Right Leg Pivot Group:** Pivot positioned at hip joint $(-0.12, 0.65, 0)\,\text{m}$. Contains leg mesh extending downwards.

### 4.2 Velocity-Driven Walking Animation
- When pedestrian speed $v > 0.05\,\text{m/s}$, the walk cycle advances according to:
  $$\text{walkPhase}(t) = \text{walkPhase}(t_0) + \Delta t \times v \times 7.0$$
- Left and right leg pivot groups rotate along the local X-axis in opposing phases:
  $$\text{rotationX}_{\text{left}} = \sin(\text{walkPhase}) \times 0.55\,\text{rad}$$
  $$\text{rotationX}_{\text{right}} = -\sin(\text{walkPhase}) \times 0.55\,\text{rad}$$
- When stationary ($v \le 0.05\,\text{m/s}$), leg rotations decay smoothly to zero, returning the avatar to a natural standing posture.

---

## 5. Presentation-Only Emergency Beacon Lighting & Accessibility

### 5.1 Dual-Strobe Alternating Beacons
Emergency vehicles (`ambulance` and `fire_engine`) feature roof-mounted dual lightbars:
- Left beacon: Blue (`#2563eb`)
- Right beacon: Red (`#dc2626`)
- When active (`emergency_active == true`), the beacons flash in counter-phase at $2.5\,\text{Hz}$:
  $$\text{phase} = \sin(t_{\text{elapsed}} \times 2\pi \times 2.5)$$
  $$I_{\text{left}} = \text{phase} > 0 \,?\, 1.0 : 0.1$$
  $$I_{\text{right}} = \text{phase} \le 0 \,?\, 1.0 : 0.1$$
- When inactive, both beacon emissive intensities remain dimmed at $0.05$.

### 5.2 Accessibility (`prefers-reduced-motion`)
To protect users sensitive to rapid flashing lights, the animation engine queries:
```typescript
window.matchMedia("(prefers-reduced-motion: reduce)").matches
```
When reduced motion is preferred, alternating high-frequency strobing is completely disabled. Active beacons illuminate with a steady, static, non-strobing emissive glow ($I = 0.8$).

---

## 6. Deterministic Temporal Interpolation Engine

### 6.1 Buffer Architecture & Invariant Rules
The `EntityInterpolationBuffer` manages historical state snapshots for each entity:
- **Capacity:** Bounded to a maximum of 10 samples per entity. Older samples are pruned to prevent memory growth.
- **Monotonicity:** Samples with timestamps $\le$ the latest buffered timestamp are rejected to eliminate out-of-order or duplicate telemetry packets.
- **Zero Allocations on Query:** Interpolation queries calculate values mathematically from array indices without allocating temporary objects.

### 6.2 Shortest Angular Difference Heading Lerp
Direct linear interpolation between angles across the $0 \leftrightarrow 2\pi$ discontinuity causes severe 350° visual spins. The engine computes the minimal signed geodesic difference:
$$\Delta \theta = ((\theta_1 - \theta_0 + \pi) \pmod{2\pi}) - \pi$$
$$\theta(t) = (\theta_0 + \alpha \Delta \theta) \pmod{2\pi}$$
where $\alpha = \frac{t - t_0}{t_1 - t_0} \in [0, 1]$.

### 6.3 Simulation-to-Three.js Orientation Mapping
In AMAPP simulation coordinates:
- Heading $0 = \text{East } (+X)$
- Heading $\pi/2 = \text{North } (+Y)$

Three.js world coordinates map:
- $X_{\text{world}} = X_{\text{sim}}$
- $Z_{\text{world}} = -Y_{\text{sim}}$

Because vehicle models are authored with local forward pointing along $+Z$, the Three.js rotation angle around the vertical Y-axis is:
$$\text{rotationY} = \text{atan2}(\cos\theta, -\sin\theta)$$

### 6.4 Extrapolation Clamping & Stale Data Detection
- **Bounded Extrapolation:** If render time exceeds the latest buffered telemetry timestamp by $\le 0.15\,\text{s}$, the engine extrapolates forward using the latest known velocity vector:
  $$\vec{p}(t) = \vec{p}_{\text{latest}} + \vec{v} \cdot \Delta t_{\text{extrap}}$$
- **Extrapolation Clamping:** Extrapolation is hard-clamped at $0.15\,\text{s}$ to prevent runaway drift during network pauses.
- **Stale Data Flag:** If render time exceeds the latest sample by $> 1.0\,\text{s}$, the entity is flagged as `is_stale = true`. The entity remains at its last known position, and the inspector displays a `"STALE (Last Known State)"` badge.

---

## 7. Verification & Test Evidence

### 7.1 Frontend Quality Verification
- **ESLint (`npm run lint`):** Passed with 0 errors, 0 warnings.
- **TypeScript Typecheck (`npm run typecheck`):** Passed with 0 errors (`tsc --noEmit`).
- **Production Build (`npm run build`):** Built cleanly in 1.60s.
- **Vitest Unit Tests (`npm test`):** **107 passed across 6 test suites**:
  - `src/test/interpolation.test.ts`: **25 passed** (normalization, shortest angular diff, wraparound lerp, position lerp, heading rotation mapping, out-of-order rejection, duplicate timestamps, bounded history pruning, bounded extrapolation clamping, stale detection).
  - `src/test/models.test.ts`: **18 passed** (classification, asset cache reuse, procedural mesh hierarchies for sedan/truck/bus/ambulance/fire_engine/unknown, articulated pedestrian avatars, 2.5 Hz beacon animation, reduced motion compliance, leg swing walking cycle, scene disposal).
  - `src/test/geometry.test.ts`: **34 passed** (coordinates, road widths, lane markings, zebra stripes, inferred crosswalks, sidewalks/curbs, Mulberry32 PRNG, procedural buildings, OSM adapter).
  - `src/test/components.test.tsx`: **14 passed** (Header, ScenarioSelector, TelemetryFeed, MetricsPanel, EntityInspector model class, emergency status, priority, tick/timestamp, live/stale badges, SimulationViewer3D controls).
  - `src/test/api-client.test.ts`: **8 passed** (API client endpoints, RFC 7807 problem details, error handling).
  - `src/test/websocket-client.test.ts`: **8 passed** (handshake, subscriptions, heartbeat reply, backpressure, reconnection).

### 7.2 Backend Quality Verification
- **Ruff Linting (`ruff check backend`):** Passed with 0 errors.
- **Django System Checks (`python backend/manage.py check`):** Identified 0 issues.
- **Pytest Regression Suite (`pytest --cov=backend/apps/core --cov-fail-under=80`):**
  - **1,095 passed in 23.47s**
  - **95.66% line coverage** across `backend/apps/core` (exceeds 80% requirement).

---

## 8. Files Created, Modified, and Removed

### Created Files
- `frontend/src/features/scene3d/interpolation.ts`: Pure TypeScript temporal interpolation engine (`EntityInterpolationBuffer`, `interpolatePosition`, `interpolateHeading`, `simHeadingToWorldRotationY`, angle math helpers).
- `frontend/src/features/scene3d/models.ts`: Procedural 3D vehicle models (`createVehicleModel`), articulated pedestrian avatars (`createPedestrianModel`), `ModelAssetCache` singleton, beacon animation, and reduced-motion handling.
- `frontend/src/test/interpolation.test.ts`: 25 unit tests for temporal interpolation engine.
- `frontend/src/test/models.test.ts`: 18 unit tests for models, asset cache, beacon animation, and walking cycles.
- `docs/progress/PHASE_25.md`: This comprehensive Phase 25 implementation report.

### Modified Files
- `frontend/src/types/simulation.ts`: Extended `VehicleState` and `PedestrianState` with `model_type`, `emergency_type`, `priority_level`, `tick`, `simulation_time_s`, and `is_stale`.
- `frontend/src/app/App.tsx`: Plumbed simulation snapshot ticks, timestamps, emergency types, and priority levels into state stores.
- `frontend/src/features/scene3d/SimulationViewer3D.tsx`: Integrated procedural vehicle and pedestrian models, decoupled 60 FPS interpolation animation loop, and clean entity lifecycle management.
- `frontend/src/features/simulation/EntityInspector.tsx`: Added model classification display, emergency status badge, priority level, telemetry metadata, and live interpolated vs. stale data indicators.
- `frontend/src/test/components.test.tsx`: Added component tests for enhanced EntityInspector and model rendering.
- `.github/workflows/ci.yml`: Added `"docs/progress/PHASE_25.md"` to mandatory repo-hygiene files.
- `PROJECT_STATUS.md`: Marked Phase 25 as COMPLETED, set Phase 26 as next pending.
- `ARCHITECTURE.md`: Added Section 3.10 documenting 3D Vehicle & Pedestrian Entity Rendering and Temporal Interpolation Engine.
- `REQUIREMENTS_TRACEABILITY.md`: Updated FR-10 and FR-14 statuses and test evidence for Phase 25.
- `README.md`: Added Section 6.27 for Enhanced 3D Entity Models, Animation, and Temporal Interpolation.
- `docs/TESTING.md`: Updated Section 4.3 with 107-test frontend breakdown across 6 test suites.

---

## 9. CI Pipeline Execution & Evidence

- **Authoritative CI Run URL:** *(Updated upon push & verification in GitHub Actions)*
- **Commit SHA:** *(Updated upon commit)*
- **Workflow:** `CI Pipeline` (`.github/workflows/ci.yml`)
- **Trigger:** `push` on branch `main`
- **Expected Job Statuses:**
  - `repo-hygiene`: Verifies mandatory documentation and phase reports from `PHASE_01.md` through `PHASE_25.md`; scans for secret leaks and prohibited binary files.
  - `backend-quality`: Executes Ruff linting, Django system checks, and full pytest regression suite (1,095 passed, $\ge 80\%$ coverage).
  - `frontend-quality`: Executes `npm ci`, `npm run lint`, `npm run typecheck`, 107 Vitest tests, and Vite production bundle build.

---

## 10. Exact Phase 26 Handoff Instructions

When initiating **Phase 26 (Interactive Simulation Playback Controls)**:
1. **Interactive Timeline & Playback Bar:** Implement interactive play, pause, resume, single-step forward (+1 tick), and multi-step (+10 ticks) controls linked to authoritative backend endpoints (`POST /api/v1/runs/{run_id}/step/`).
2. **Speed Multiplier:** Implement playback speed multiplier (e.g. 0.5x, 1x, 2x, 5x) governing frontend playback timer interval and request cadence.
3. **Historical Telemetry Scrubber:** Build a timeline scrubber allowing users to seek backwards and replay buffered telemetry frames within the session buffer.
4. **Preserve Presentation-Only Boundary:** Playback controls send commands to the backend runner; they do not alter simulation physics or synthesize fake kinematics on the client.
5. **Preserve Existing Visuals:** Retain all Phase 24 city features (Day/Night, Persp/Ortho, Buildings toggle) and Phase 25 entity models and interpolation.
