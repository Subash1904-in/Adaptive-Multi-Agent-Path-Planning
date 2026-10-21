/**
 * Three.js visualization overlay for active routes, planned baseline routes,
 * alternative candidate paths, and rerouting decision markers.
 *
 * Implements geometry reuse, pause-freezing, speed scaling, and complete GPU disposal.
 */

import * as THREE from "three";
import type {
  ActiveRoute,
  CandidateRoute,
  PlannedRoute,
  RouteOverlayOptions,
  RouteSubsystemSnapshot,
} from "../../types/routing";
import { DEFAULT_ROUTE_OVERLAY_OPTIONS } from "../../types/routing";

export class RouteOverlayManager {
  public readonly rootGroup: THREE.Group = new THREE.Group();
  public readonly activeRouteGroup: THREE.Group = new THREE.Group();
  public readonly plannedRouteGroup: THREE.Group = new THREE.Group();
  public readonly candidatesGroup: THREE.Group = new THREE.Group();
  public readonly markersGroup: THREE.Group = new THREE.Group();

  private options: RouteOverlayOptions = { ...DEFAULT_ROUTE_OVERLAY_OPTIONS };

  // Reusable materials
  private activeLineMaterial: THREE.LineBasicMaterial;
  private plannedLineMaterial: THREE.LineDashedMaterial;
  private candidateLineMaterial: THREE.LineDashedMaterial;
  private candidateSelectedMaterial: THREE.LineBasicMaterial;
  private markerAcceptedMaterial: THREE.MeshBasicMaterial;
  private markerRejectedMaterial: THREE.MeshBasicMaterial;

  // Shared geometry
  private markerGeometry: THREE.OctahedronGeometry;

  // Tracked Three.js objects
  private activeLineMeshes: Map<string, THREE.Line> = new Map();
  private plannedLineMeshes: Map<string, THREE.Line> = new Map();
  private candidateLineMeshes: Map<string, THREE.Line> = new Map();
  private markerMeshes: Map<string, THREE.Mesh> = new Map();

  constructor() {
    this.rootGroup.name = "RouteOverlayRoot";
    this.activeRouteGroup.name = "ActiveRouteGroup";
    this.plannedRouteGroup.name = "PlannedRouteGroup";
    this.candidatesGroup.name = "CandidatesGroup";
    this.markersGroup.name = "MarkersGroup";

    this.rootGroup.add(this.plannedRouteGroup);
    this.rootGroup.add(this.candidatesGroup);
    this.rootGroup.add(this.activeRouteGroup);
    this.rootGroup.add(this.markersGroup);

    // High-contrast cyan line for authoritative active route
    this.activeLineMaterial = new THREE.LineBasicMaterial({
      color: 0x06b6d4,
      linewidth: 4,
      depthWrite: false,
    });

    // Subdued slate dashed line for initial planned route
    this.plannedLineMaterial = new THREE.LineDashedMaterial({
      color: 0x94a3b8,
      linewidth: 2,
      dashSize: 3,
      gapSize: 2,
      transparent: true,
      opacity: 0.65,
      depthWrite: false,
    });

    // Purple dashed line for alternative evaluated candidate routes
    this.candidateLineMaterial = new THREE.LineDashedMaterial({
      color: 0xa855f7,
      linewidth: 2,
      dashSize: 2.5,
      gapSize: 1.5,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
    });

    // Vibrant magenta solid line for currently inspected candidate path
    this.candidateSelectedMaterial = new THREE.LineBasicMaterial({
      color: 0xf43f5e,
      linewidth: 4,
      depthWrite: false,
    });

    // Emerald diamond for accepted reroutes
    this.markerAcceptedMaterial = new THREE.MeshBasicMaterial({
      color: 0x10b981,
      transparent: true,
      opacity: 0.9,
    });

    // Amber diamond for rejected or no-change evaluations
    this.markerRejectedMaterial = new THREE.MeshBasicMaterial({
      color: 0xf59e0b,
      transparent: true,
      opacity: 0.85,
    });

    this.markerGeometry = new THREE.OctahedronGeometry(0.7, 0);
  }

  public getOptions(): RouteOverlayOptions {
    return { ...this.options };
  }

  public setOptions(newOptions: Partial<RouteOverlayOptions>): void {
    this.options = { ...this.options, ...newOptions };
    this.applyVisibility();
  }

  private applyVisibility(): void {
    this.activeRouteGroup.visible = this.options.showActiveRoutes;
    this.plannedRouteGroup.visible = this.options.showPlannedRoutes;
    this.candidatesGroup.visible = this.options.showCandidateRoutes;
    this.markersGroup.visible = this.options.showRerouteMarkers;
  }

  /**
   * Update 3D route meshes from an authoritative RouteSubsystemSnapshot.
   * If a selected vehicle is provided, renders its active, planned, and candidate routes.
   * Otherwise renders active routes for all tracked vehicles.
   */
  public update(
    snapshot: RouteSubsystemSnapshot | null | undefined,
    selectedVehicleId: string | null | undefined,
    selectedCandidateId: string | null | undefined
  ): void {
    if (!snapshot) {
      this.clear();
      return;
    }

    this.applyVisibility();

    // 1. Synchronize Active Routes
    const currentActiveMeshes = new Map<string, THREE.Line>();
    const vehiclesToRender = selectedVehicleId
      ? [selectedVehicleId]
      : Array.from(snapshot.activeRoutes.keys());

    for (const vId of vehiclesToRender) {
      const activeRoute: ActiveRoute | undefined = snapshot.activeRoutes.get(vId);
      if (!activeRoute || activeRoute.worldPoints.length < 2) continue;

      let line = this.activeLineMeshes.get(vId);
      if (!line) {
        const points = activeRoute.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        line = new THREE.Line(geo, this.activeLineMaterial);
        line.name = `ActiveRoute_${vId}`;
        this.activeRouteGroup.add(line);
      } else {
        // Reuse geometry buffer if point count matches, else recreate
        const points = activeRoute.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
        line.geometry.dispose();
        line.geometry = new THREE.BufferGeometry().setFromPoints(points);
      }
      currentActiveMeshes.set(vId, line);
    }

    // Remove inactive active route lines
    for (const [vId, line] of this.activeLineMeshes.entries()) {
      if (!currentActiveMeshes.has(vId)) {
        this.activeRouteGroup.remove(line);
        line.geometry.dispose();
      }
    }
    this.activeLineMeshes = currentActiveMeshes;

    // 2. Synchronize Planned Routes (Baseline comparisons)
    const currentPlannedMeshes = new Map<string, THREE.Line>();
    const plannedVehicles = selectedVehicleId
      ? [selectedVehicleId]
      : Array.from(snapshot.plannedRoutes.keys());

    for (const vId of plannedVehicles) {
      const plannedRoute: PlannedRoute | undefined = snapshot.plannedRoutes.get(vId);
      if (!plannedRoute || plannedRoute.worldPoints.length < 2) continue;

      let line = this.plannedLineMeshes.get(vId);
      if (!line) {
        const points = plannedRoute.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        line = new THREE.Line(geo, this.plannedLineMaterial);
        line.computeLineDistances();
        line.name = `PlannedRoute_${vId}`;
        this.plannedRouteGroup.add(line);
      } else {
        const points = plannedRoute.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
        line.geometry.dispose();
        line.geometry = new THREE.BufferGeometry().setFromPoints(points);
        line.computeLineDistances();
      }
      currentPlannedMeshes.set(vId, line);
    }

    for (const [vId, line] of this.plannedLineMeshes.entries()) {
      if (!currentPlannedMeshes.has(vId)) {
        this.plannedRouteGroup.remove(line);
        line.geometry.dispose();
      }
    }
    this.plannedLineMeshes = currentPlannedMeshes;

    // 3. Synchronize Evaluated Alternative Candidate Routes
    const currentCandidateMeshes = new Map<string, THREE.Line>();
    const candidateVehicles = selectedVehicleId
      ? [selectedVehicleId]
      : Array.from(snapshot.candidateRoutes.keys());

    for (const vId of candidateVehicles) {
      const cands: CandidateRoute[] | undefined = snapshot.candidateRoutes.get(vId);
      if (!cands || cands.length === 0) continue;

      for (const cand of cands) {
        if (!cand || cand.worldPoints.length < 2) continue;
        const candKey = cand.id;
        const isSelected = selectedCandidateId === candKey;
        const mat = isSelected ? this.candidateSelectedMaterial : this.candidateLineMaterial;

        let line = this.candidateLineMeshes.get(candKey);
        if (!line) {
          const points = cand.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          line = new THREE.Line(geo, mat);
          if (!isSelected) {
            line.computeLineDistances();
          }
          line.name = `CandidateRoute_${candKey}`;
          this.candidatesGroup.add(line);
        } else {
          line.material = mat;
          const points = cand.worldPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
          line.geometry.dispose();
          line.geometry = new THREE.BufferGeometry().setFromPoints(points);
          if (!isSelected) {
            line.computeLineDistances();
          }
        }
        currentCandidateMeshes.set(candKey, line);
      }
    }

    for (const [candKey, line] of this.candidateLineMeshes.entries()) {
      if (!currentCandidateMeshes.has(candKey)) {
        this.candidatesGroup.remove(line);
        line.geometry.dispose();
      }
    }
    this.candidateLineMeshes = currentCandidateMeshes;

    // 4. Synchronize Rerouting Decision Markers (Diamonds)
    const currentMarkers = new Map<string, THREE.Mesh>();
    for (const ev of snapshot.rerouteEvents) {
      if (!ev || !ev.markerPosition) continue;
      // If a vehicle is selected, filter markers to that vehicle
      if (selectedVehicleId && ev.vehicleId !== selectedVehicleId) continue;

      const markerKey = ev.id;
      let mesh = this.markerMeshes.get(markerKey);
      const mat = ev.isAccepted ? this.markerAcceptedMaterial : this.markerRejectedMaterial;

      if (!mesh) {
        mesh = new THREE.Mesh(this.markerGeometry, mat);
        mesh.position.set(ev.markerPosition.x, ev.markerPosition.y, ev.markerPosition.z);
        mesh.name = `RerouteMarker_${markerKey}`;
        this.markersGroup.add(mesh);
      } else {
        mesh.material = mat;
        mesh.position.set(ev.markerPosition.x, ev.markerPosition.y, ev.markerPosition.z);
      }
      currentMarkers.set(markerKey, mesh);
    }

    for (const [markerKey, mesh] of this.markerMeshes.entries()) {
      if (!currentMarkers.has(markerKey)) {
        this.markersGroup.remove(mesh);
      }
    }
    this.markerMeshes = currentMarkers;
  }

  /**
   * Advance presentation animation (marker rotation).
   * Freezes when simulation is paused. Scales with playback speed.
   */
  public tick(dt: number, speedMultiplier = 1, isPaused = false): void {
    if (isPaused || dt <= 0) {
      return;
    }

    const rotationDelta = dt * 1.5 * Math.max(0.2, speedMultiplier);
    for (const mesh of this.markerMeshes.values()) {
      mesh.rotation.y += rotationDelta;
    }
  }

  /**
   * Remove all active 3D meshes without disposing reusable materials.
   */
  public clear(): void {
    for (const line of this.activeLineMeshes.values()) {
      this.activeRouteGroup.remove(line);
      line.geometry.dispose();
    }
    this.activeLineMeshes.clear();

    for (const line of this.plannedLineMeshes.values()) {
      this.plannedRouteGroup.remove(line);
      line.geometry.dispose();
    }
    this.plannedLineMeshes.clear();

    for (const line of this.candidateLineMeshes.values()) {
      this.candidatesGroup.remove(line);
      line.geometry.dispose();
    }
    this.candidateLineMeshes.clear();

    for (const mesh of this.markerMeshes.values()) {
      this.markersGroup.remove(mesh);
    }
    this.markerMeshes.clear();
  }

  /**
   * Cleanly dispose of all GPU geometries, materials, and groups.
   */
  public dispose(): void {
    this.clear();

    this.activeLineMaterial.dispose();
    this.plannedLineMaterial.dispose();
    this.candidateLineMaterial.dispose();
    this.candidateSelectedMaterial.dispose();
    this.markerAcceptedMaterial.dispose();
    this.markerRejectedMaterial.dispose();
    this.markerGeometry.dispose();

    this.rootGroup.remove(this.activeRouteGroup);
    this.rootGroup.remove(this.plannedRouteGroup);
    this.rootGroup.remove(this.candidatesGroup);
    this.rootGroup.remove(this.markersGroup);
  }
}
