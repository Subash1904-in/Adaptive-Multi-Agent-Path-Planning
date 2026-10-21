/**
 * Three.js visualization overlay for interactive traffic incidents and scenario controls.
 *
 * Renders backend-authoritative road closures, localized congestion glows, obstacle/hazard
 * markers, and traffic signal override indicators.
 *
 * Elevation hierarchy:
 *   - Asphalt: 0.0m
 *   - Road markings: 0.035m
 *   - Sidewalks: 0.06m
 *   - V2V range rings: 0.08m
 *   - Incident edge highlights: 0.10m
 *   - Route lines: 0.12m
 *   - Incident 3D obstacle/signal beacons: 0.60m
 */

import * as THREE from "three";
import type { RoadNetworkGeometry } from "../../types/graph";
import type { IncidentRecord } from "../../types/incidents";
import { simToWorldCoordinates } from "./geometry";

export const INCIDENT_OVERLAY_ELEVATION_M = 0.10;
export const INCIDENT_MARKER_ELEVATION_M = 0.60;

export interface IncidentOverlayOptions {
  showRoadClosures: boolean;
  showCongestion: boolean;
  showObstacles: boolean;
  showSignalOverrides: boolean;
}

export const DEFAULT_INCIDENT_OVERLAY_OPTIONS: IncidentOverlayOptions = {
  showRoadClosures: true,
  showCongestion: true,
  showObstacles: true,
  showSignalOverrides: true,
};

export class IncidentOverlayManager {
  public readonly rootGroup: THREE.Group = new THREE.Group();
  public readonly closuresGroup: THREE.Group = new THREE.Group();
  public readonly congestionGroup: THREE.Group = new THREE.Group();
  public readonly obstaclesGroup: THREE.Group = new THREE.Group();
  public readonly signalOverridesGroup: THREE.Group = new THREE.Group();

  private options: IncidentOverlayOptions = { ...DEFAULT_INCIDENT_OVERLAY_OPTIONS };

  // Shared reusable materials
  private closureLineMaterial: THREE.LineBasicMaterial;
  private congestionLineMaterial: THREE.LineBasicMaterial;
  private obstacleMarkerMaterial: THREE.MeshStandardMaterial;
  private signalRedMaterial: THREE.MeshBasicMaterial;
  private signalYellowMaterial: THREE.MeshBasicMaterial;
  private signalGreenMaterial: THREE.MeshBasicMaterial;

  // Shared geometries
  private obstacleGeometry: THREE.CylinderGeometry;
  private beaconGeometry: THREE.TorusGeometry;

  // Tracked Three.js objects keyed by incident ID
  private closureObjects: Map<string, THREE.Object3D> = new Map();
  private congestionObjects: Map<string, THREE.Object3D> = new Map();
  private obstacleObjects: Map<string, THREE.Object3D> = new Map();
  private signalOverrideObjects: Map<string, THREE.Object3D> = new Map();

  // Animation phase for pulsating overlays
  private pulsePhase = 0.0;

  constructor() {
    this.rootGroup.name = "IncidentOverlayRoot";
    this.closuresGroup.name = "IncidentClosuresGroup";
    this.congestionGroup.name = "IncidentCongestionGroup";
    this.obstaclesGroup.name = "IncidentObstaclesGroup";
    this.signalOverridesGroup.name = "IncidentSignalOverridesGroup";

    this.rootGroup.add(this.closuresGroup);
    this.rootGroup.add(this.congestionGroup);
    this.rootGroup.add(this.obstaclesGroup);
    this.rootGroup.add(this.signalOverridesGroup);

    // High-visibility crimson for authoritative road closures
    this.closureLineMaterial = new THREE.LineBasicMaterial({
      color: 0xef4444,
      linewidth: 6,
      depthWrite: false,
    });

    // Warm amber glow for localized congestion
    this.congestionLineMaterial = new THREE.LineBasicMaterial({
      color: 0xf97316,
      linewidth: 5,
      depthWrite: false,
      transparent: true,
      opacity: 0.85,
    });

    // Safety orange cone/cylinder for obstacles
    this.obstacleMarkerMaterial = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      roughness: 0.3,
      metalness: 0.2,
      emissive: 0xd97706,
      emissiveIntensity: 0.4,
    });

    // Signal override beacon rings
    this.signalRedMaterial = new THREE.MeshBasicMaterial({
      color: 0xef4444,
      transparent: true,
      opacity: 0.8,
    });
    this.signalYellowMaterial = new THREE.MeshBasicMaterial({
      color: 0xeab308,
      transparent: true,
      opacity: 0.8,
    });
    this.signalGreenMaterial = new THREE.MeshBasicMaterial({
      color: 0x22c55e,
      transparent: true,
      opacity: 0.8,
    });

    this.obstacleGeometry = new THREE.CylinderGeometry(0.3, 0.6, 0.9, 8);
    this.beaconGeometry = new THREE.TorusGeometry(1.2, 0.15, 8, 24);
  }

  public getOptions(): IncidentOverlayOptions {
    return { ...this.options };
  }

  public setOptions(newOptions: Partial<IncidentOverlayOptions>): void {
    this.options = { ...this.options, ...newOptions };
    this.applyVisibility();
  }

  private applyVisibility(): void {
    this.closuresGroup.visible = this.options.showRoadClosures;
    this.congestionGroup.visible = this.options.showCongestion;
    this.obstaclesGroup.visible = this.options.showObstacles;
    this.signalOverridesGroup.visible = this.options.showSignalOverrides;
  }

  /**
   * Update visual incident representations from active authoritative incident records.
   */
  public update(
    incidents: IncidentRecord[] | null | undefined,
    geometry?: RoadNetworkGeometry | null
  ): void {
    if (!incidents || incidents.length === 0 || !geometry) {
      this.clear();
      return;
    }

    this.applyVisibility();

    // Map road edges and nodes for fast lookup
    const edgeMap = new Map<string, { u: string; v: string }>();
    if (geometry.edges) {
      for (const e of geometry.edges) {
        if (e && e.id && e.start_node_id && e.end_node_id) {
          edgeMap.set(e.id, { u: e.start_node_id, v: e.end_node_id });
        }
      }
    }

    const nodeMap = new Map<string, { x: number; y: number }>();
    if (geometry.nodes) {
      for (const n of geometry.nodes) {
        if (n && n.id && Number.isFinite(n.x) && Number.isFinite(n.y)) {
          nodeMap.set(n.id, { x: n.x, y: n.y });
        }
      }
    }

    const currentClosures = new Map<string, THREE.Object3D>();
    const currentCongestion = new Map<string, THREE.Object3D>();
    const currentObstacles = new Map<string, THREE.Object3D>();
    const currentSignalOverrides = new Map<string, THREE.Object3D>();

    for (const inc of incidents) {
      if (inc.status !== "active") continue;

      if (inc.incident_type === "road_closure" && inc.affected_edge_id) {
        const edge = edgeMap.get(inc.affected_edge_id);
        if (!edge) continue;
        const uNode = nodeMap.get(edge.u);
        const vNode = nodeMap.get(edge.v);
        if (!uNode || !vNode) continue;

        let obj = this.closureObjects.get(inc.id);
        if (!obj) {
          const p1 = simToWorldCoordinates(uNode.x, uNode.y, INCIDENT_OVERLAY_ELEVATION_M);
          const p2 = simToWorldCoordinates(vNode.x, vNode.y, INCIDENT_OVERLAY_ELEVATION_M);
          const points = [
            new THREE.Vector3(p1.x, p1.y, p1.z),
            new THREE.Vector3(p2.x, p2.y, p2.z),
          ];
          const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
          const line = new THREE.Line(lineGeo, this.closureLineMaterial);
          line.name = `Closure_${inc.id}`;

          // Add barrier cross marker at edge midpoint
          const midX = (p1.x + p2.x) / 2;
          const midY = (p1.y + p2.y) / 2 + 0.2;
          const midZ = (p1.z + p2.z) / 2;
          const crossGroup = new THREE.Group();
          crossGroup.position.set(midX, midY, midZ);

          const barGeo = new THREE.BoxGeometry(0.8, 0.2, 0.2);
          const bar1 = new THREE.Mesh(barGeo, this.closureLineMaterial);
          bar1.rotation.y = Math.PI / 4;
          const bar2 = new THREE.Mesh(barGeo, this.closureLineMaterial);
          bar2.rotation.y = -Math.PI / 4;
          crossGroup.add(bar1);
          crossGroup.add(bar2);

          const closureContainer = new THREE.Group();
          closureContainer.add(line);
          closureContainer.add(crossGroup);
          this.closuresGroup.add(closureContainer);
          obj = closureContainer;
        }
        currentClosures.set(inc.id, obj);
      } else if (inc.incident_type === "congestion" && inc.affected_edge_id) {
        const edge = edgeMap.get(inc.affected_edge_id);
        if (!edge) continue;
        const uNode = nodeMap.get(edge.u);
        const vNode = nodeMap.get(edge.v);
        if (!uNode || !vNode) continue;

        let obj = this.congestionObjects.get(inc.id);
        if (!obj) {
          const p1 = simToWorldCoordinates(uNode.x, uNode.y, INCIDENT_OVERLAY_ELEVATION_M);
          const p2 = simToWorldCoordinates(vNode.x, vNode.y, INCIDENT_OVERLAY_ELEVATION_M);
          const points = [
            new THREE.Vector3(p1.x, p1.y, p1.z),
            new THREE.Vector3(p2.x, p2.y, p2.z),
          ];
          const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
          const line = new THREE.Line(lineGeo, this.congestionLineMaterial);
          line.name = `Congestion_${inc.id}`;
          this.congestionGroup.add(line);
          obj = line;
        }
        currentCongestion.set(inc.id, obj);
      } else if (
        (inc.incident_type === "obstacle" ||
          inc.incident_type === "hazard" ||
          inc.incident_type === "accident")
      ) {
        let posX = 0;
        let posZ = 0;

        if (inc.position && Number.isFinite(inc.position.x) && Number.isFinite(inc.position.y)) {
          const w = simToWorldCoordinates(inc.position.x, inc.position.y, INCIDENT_MARKER_ELEVATION_M);
          posX = w.x;
          posZ = w.z;
        } else if (inc.affected_edge_id) {
          const edge = edgeMap.get(inc.affected_edge_id);
          if (edge) {
            const uNode = nodeMap.get(edge.u);
            const vNode = nodeMap.get(edge.v);
            if (uNode && vNode) {
              const w = simToWorldCoordinates(
                (uNode.x + vNode.x) / 2,
                (uNode.y + vNode.y) / 2,
                INCIDENT_MARKER_ELEVATION_M
              );
              posX = w.x;
              posZ = w.z;
            }
          }
        }

        let obj = this.obstacleObjects.get(inc.id);
        if (!obj) {
          const mesh = new THREE.Mesh(this.obstacleGeometry, this.obstacleMarkerMaterial);
          mesh.name = `Obstacle_${inc.id}`;
          mesh.position.set(posX, INCIDENT_MARKER_ELEVATION_M, posZ);
          this.obstaclesGroup.add(mesh);
          obj = mesh;
        } else {
          obj.position.set(posX, INCIDENT_MARKER_ELEVATION_M, posZ);
        }
        currentObstacles.set(inc.id, obj);
      } else if (inc.incident_type === "signal_override" && inc.affected_node_id) {
        const node = nodeMap.get(inc.affected_node_id);
        if (!node) continue;

        let obj = this.signalOverrideObjects.get(inc.id);
        let mat = this.signalRedMaterial;
        if (inc.target_signal_phase === "yellow") mat = this.signalYellowMaterial;
        else if (inc.target_signal_phase === "green") mat = this.signalGreenMaterial;

        if (!obj) {
          const w = simToWorldCoordinates(node.x, node.y, 0.15);
          const ring = new THREE.Mesh(this.beaconGeometry, mat);
          ring.rotation.x = Math.PI / 2;
          ring.position.set(w.x, 0.15, w.z);
          ring.name = `SignalOverride_${inc.id}`;
          this.signalOverridesGroup.add(ring);
          obj = ring;
        } else {
          (obj as THREE.Mesh).material = mat;
        }
        currentSignalOverrides.set(inc.id, obj);
      }
    }

    // Prune removed objects
    this.pruneRemoved(this.closureObjects, currentClosures, this.closuresGroup);
    this.closureObjects = currentClosures;

    this.pruneRemoved(this.congestionObjects, currentCongestion, this.congestionGroup);
    this.congestionObjects = currentCongestion;

    this.pruneRemoved(this.obstacleObjects, currentObstacles, this.obstaclesGroup);
    this.obstacleObjects = currentObstacles;

    this.pruneRemoved(this.signalOverrideObjects, currentSignalOverrides, this.signalOverridesGroup);
    this.signalOverrideObjects = currentSignalOverrides;
  }

  private pruneRemoved(
    oldMap: Map<string, THREE.Object3D>,
    newMap: Map<string, THREE.Object3D>,
    group: THREE.Group
  ): void {
    for (const [id, obj] of oldMap.entries()) {
      if (!newMap.has(id)) {
        group.remove(obj);
        obj.traverse((child) => {
          if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
            child.geometry?.dispose();
          }
        });
      }
    }
  }

  /**
   * Animation tick to pulse active congestion and signal override rings.
   */
  public animate(deltaSeconds: number): void {
    this.pulsePhase += deltaSeconds * 2.5;
    const pulseFactor = 0.65 + 0.35 * Math.sin(this.pulsePhase);

    this.congestionLineMaterial.opacity = 0.5 + 0.45 * pulseFactor;

    for (const obj of this.signalOverrideObjects.values()) {
      const scale = 1.0 + 0.15 * Math.sin(this.pulsePhase);
      obj.scale.set(scale, scale, scale);
    }
  }

  public clear(): void {
    for (const obj of this.closureObjects.values()) {
      this.closuresGroup.remove(obj);
    }
    this.closureObjects.clear();

    for (const obj of this.congestionObjects.values()) {
      this.congestionGroup.remove(obj);
    }
    this.congestionObjects.clear();

    for (const obj of this.obstacleObjects.values()) {
      this.obstaclesGroup.remove(obj);
    }
    this.obstacleObjects.clear();

    for (const obj of this.signalOverrideObjects.values()) {
      this.signalOverridesGroup.remove(obj);
    }
    this.signalOverrideObjects.clear();
  }

  public dispose(): void {
    this.clear();
    this.closureLineMaterial.dispose();
    this.congestionLineMaterial.dispose();
    this.obstacleMarkerMaterial.dispose();
    this.signalRedMaterial.dispose();
    this.signalYellowMaterial.dispose();
    this.signalGreenMaterial.dispose();
    this.obstacleGeometry.dispose();
    this.beaconGeometry.dispose();
  }
}
