/**
 * Three.js visualization overlay for V2V communication links, range rings,
 * transmission/delivery pulses, dropped packets, and network degradation states.
 * Reuses geometries and materials to avoid allocations during animation loops.
 */

import * as THREE from "three";
import type {
  V2VLink,
  V2VMessageAnimation,
  V2VOverlayOptions,
} from "../../types/v2v";
import { DEFAULT_V2V_OVERLAY_OPTIONS } from "../../types/v2v";

export interface V2VOverlayCallbacks {
  getVehicleWorldPosition: (vehicleId: string) => THREE.Vector3 | null;
}

export class V2VOverlayManager {
  public readonly rootGroup: THREE.Group = new THREE.Group();
  public readonly linksGroup: THREE.Group = new THREE.Group();
  public readonly rangeGroup: THREE.Group = new THREE.Group();
  public readonly animationsGroup: THREE.Group = new THREE.Group();
  public readonly degradationGroup: THREE.Group = new THREE.Group();
  public readonly messageLabelsGroup: THREE.Group = new THREE.Group();

  private options: V2VOverlayOptions = { ...DEFAULT_V2V_OVERLAY_OPTIONS };

  // Reusable materials
  private activeLinkMaterial: THREE.LineBasicMaterial;
  private staleLinkMaterial: THREE.LineDashedMaterial;
  private rangeFillMaterial: THREE.MeshBasicMaterial;
  private rangeOutlineMaterial: THREE.LineBasicMaterial;
  private pulseSphereMaterial: THREE.MeshBasicMaterial;
  private dropMarkerMaterial: THREE.MeshBasicMaterial;

  // Active object maps
  private linkMeshes: Map<string, THREE.Line> = new Map();
  private rangeRingMesh: THREE.Mesh | null = null;
  private rangeOutlineLine: THREE.LineLoop | null = null;
  private currentRangeRadius: number | null = null;

  // Bounded animation queue
  private activeAnimations: V2VMessageAnimation[] = [];
  private animationMeshes: Map<string, THREE.Object3D> = new Map();
  private messageLabels: Map<string, THREE.Sprite> = new Map();
  private maxActiveAnimations = 20;

  // Reusable shared geometries
  private pulseSphereGeo: THREE.SphereGeometry;
  private dropBoxGeo: THREE.BoxGeometry;

  constructor() {
    this.rootGroup.name = "V2VOverlayRoot";
    this.rootGroup.add(this.linksGroup);
    this.rootGroup.add(this.rangeGroup);
    this.rootGroup.add(this.animationsGroup);
    this.rootGroup.add(this.degradationGroup);
    this.degradationGroup.add(this.messageLabelsGroup);

    // Initialize shared reusable materials
    this.activeLinkMaterial = new THREE.LineBasicMaterial({
      color: 0x06b6d4, // Cyan / Teal
      transparent: true,
      opacity: 0.85,
      linewidth: 3,
    });

    this.staleLinkMaterial = new THREE.LineDashedMaterial({
      color: 0xf59e0b, // Amber / Orange
      transparent: true,
      opacity: 0.75,
      dashSize: 2.5,
      gapSize: 1.5,
      linewidth: 2,
    });

    this.rangeFillMaterial = new THREE.MeshBasicMaterial({
      color: 0x06b6d4,
      transparent: true,
      opacity: 0.12,
      side: THREE.DoubleSide,
      depthWrite: false,
    });

    this.rangeOutlineMaterial = new THREE.LineBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.7,
      linewidth: 2,
    });

    this.pulseSphereMaterial = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.9,
    });

    this.dropMarkerMaterial = new THREE.MeshBasicMaterial({
      color: 0xef4444, // Red
      transparent: true,
      opacity: 0.95,
    });

    this.pulseSphereGeo = new THREE.SphereGeometry(0.7, 8, 8);
    this.dropBoxGeo = new THREE.BoxGeometry(1.2, 1.2, 1.2);
  }

  public getOptions(): V2VOverlayOptions {
    return { ...this.options };
  }

  public setOptions(opts: Partial<V2VOverlayOptions>): void {
    this.options = { ...this.options, ...opts };
    this.linksGroup.visible = this.options.showLinks;
    this.rangeGroup.visible = this.options.showRangeRing;
    this.animationsGroup.visible = this.options.showAnimations;
    this.degradationGroup.visible = this.options.showDegradation;
  }

  /**
   * Synchronize active and stale communication links between vehicles.
   */
  public updateLinks(
    links: V2VLink[],
    getVehicleWorldPos: (id: string) => THREE.Vector3 | null
  ): void {
    if (!this.options.showLinks) {
      this.linksGroup.visible = false;
      return;
    }

    this.linksGroup.visible = true;

    const currentKeys = new Set<string>();

    for (const link of links) {
      currentKeys.add(link.id);

      const posA = getVehicleWorldPos(link.vehicleA);
      const posB = getVehicleWorldPos(link.vehicleB);

      // If either vehicle is missing from active scene, skip rendering this link
      if (!posA || !posB) {
        const existing = this.linkMeshes.get(link.id);
        if (existing) {
          existing.visible = false;
        }
        continue;
      }

      // Elevate link slightly above vehicle roof level (y + 1.2m)
      const p1 = new THREE.Vector3(posA.x, posA.y + 1.2, posA.z);
      const p2 = new THREE.Vector3(posB.x, posB.y + 1.2, posB.z);

      let line = this.linkMeshes.get(link.id);
      const isStale = link.status === "stale";
      const targetMaterial = isStale ? this.staleLinkMaterial : this.activeLinkMaterial;

      if (!line) {
        const geo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        line = new THREE.Line(geo, targetMaterial);
        if (isStale) {
          line.computeLineDistances();
        }
        this.linksGroup.add(line);
        this.linkMeshes.set(link.id, line);
      } else {
        line.visible = true;
        line.material = targetMaterial;

        // Efficiently update line buffer positions without rebuilding geometry
        const posAttr = line.geometry.getAttribute("position") as THREE.BufferAttribute;
        if (posAttr && posAttr.count >= 2) {
          posAttr.setXYZ(0, p1.x, p1.y, p1.z);
          posAttr.setXYZ(1, p2.x, p2.y, p2.z);
          posAttr.needsUpdate = true;
        } else {
          line.geometry.dispose();
          line.geometry = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        }

        if (isStale) {
          line.computeLineDistances();
        }
      }

    }

    // Remove obsolete links
    for (const [id, mesh] of this.linkMeshes.entries()) {
      if (!currentKeys.has(id)) {
        this.linksGroup.remove(mesh);
        mesh.geometry.dispose();
        this.linkMeshes.delete(id);
      }
    }
  }

  /**
   * Render the latest V2V exchange as a compact chat label over each sender.
   */
  public updateMessageLabels(
    links: V2VLink[],
    getVehicleWorldPos: (id: string) => THREE.Vector3 | null,
    timestampS: number
  ): void {
    const currentIds = new Set<string>();
    for (const link of links) {
      const position = getVehicleWorldPos(link.vehicleA);
      if (!position) continue;
      const id = `${link.id}:${link.lastMessageId ?? "heartbeat"}`;
      currentIds.add(id);
      let sprite = this.messageLabels.get(id);
      if (!sprite) {
        const canvas = document.createElement("canvas");
        canvas.width = 512;
        canvas.height = 128;
        const context = canvas.getContext("2d");
        if (!context) continue;
        context.fillStyle = "rgba(15, 23, 42, 0.92)";
        context.roundRect(4, 4, 504, 120, 18);
        context.fill();
        context.fillStyle = "#67e8f9";
        context.font = "bold 26px sans-serif";
        context.fillText(`${link.vehicleA}  ->  ${link.vehicleB}`, 20, 42);
        context.fillStyle = "#e2e8f0";
        context.font = "22px sans-serif";
        context.fillText(
          link.lastMessageId ? `V2V ${link.lastMessageId}` : "V2V heartbeat - autonomous",
          20,
          78
        );
        context.fillStyle = link.status === "active" ? "#34d399" : "#fbbf24";
        context.fillText(
          `${link.status.toUpperCase()} - ${Math.max(0, Math.round(timestampS))}s`,
          20,
          108
        );
        const texture = new THREE.CanvasTexture(canvas);
        texture.minFilter = THREE.LinearFilter;
        sprite = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            depthTest: false,
            depthWrite: false,
          })
        );
        sprite.scale.set(10, 2.5, 1);
        this.messageLabelsGroup.add(sprite);
        this.messageLabels.set(id, sprite);
      }
      sprite.position.set(position.x, position.y + 5.5, position.z);
    }

    for (const [id, sprite] of this.messageLabels.entries()) {
      if (!currentIds.has(id)) {
        this.messageLabelsGroup.remove(sprite);
        sprite.material.map?.dispose();
        sprite.material.dispose();
        this.messageLabels.delete(id);
      }
    }
  }

  /**
   * Update communication range ring on the selected vehicle.
   */
  public updateRangeRing(
    selectedVehicleId: string | null | undefined,
    rangeM: number | null,
    getVehicleWorldPos: (id: string) => THREE.Vector3 | null
  ): void {
    if (
      !this.options.showRangeRing ||
      !selectedVehicleId ||
      rangeM === null ||
      !Number.isFinite(rangeM) ||
      rangeM <= 0
    ) {
      this.rangeGroup.visible = false;
      return;
    }

    const pos = getVehicleWorldPos(selectedVehicleId);
    if (!pos) {
      this.rangeGroup.visible = false;
      return;
    }

    this.rangeGroup.visible = true;

    // Check if range geometry needs rebuilding
    if (this.currentRangeRadius !== rangeM || !this.rangeRingMesh || !this.rangeOutlineLine) {
      if (this.rangeRingMesh) {
        this.rangeGroup.remove(this.rangeRingMesh);
        this.rangeRingMesh.geometry.dispose();
      }
      if (this.rangeOutlineLine) {
        this.rangeGroup.remove(this.rangeOutlineLine);
        this.rangeOutlineLine.geometry.dispose();
      }

      this.currentRangeRadius = rangeM;

      // Disc for filled circle on ground plane
      const ringGeo = new THREE.CircleGeometry(rangeM, 48);
      this.rangeRingMesh = new THREE.Mesh(ringGeo, this.rangeFillMaterial);
      this.rangeRingMesh.rotation.x = -Math.PI / 2;
      this.rangeGroup.add(this.rangeRingMesh);

      // Boundary outline
      const outlinePoints: THREE.Vector3[] = [];
      const segments = 64;
      for (let i = 0; i <= segments; i++) {
        const theta = (i / segments) * Math.PI * 2;
        outlinePoints.push(
          new THREE.Vector3(Math.cos(theta) * rangeM, 0, Math.sin(theta) * rangeM)
        );
      }
      const outlineGeo = new THREE.BufferGeometry().setFromPoints(outlinePoints);
      this.rangeOutlineLine = new THREE.LineLoop(outlineGeo, this.rangeOutlineMaterial);
      this.rangeGroup.add(this.rangeOutlineLine);
    }

    // Place at vehicle planar position slightly above asphalt (y = 0.05m)
    this.rangeRingMesh.position.set(pos.x, 0.05, pos.z);
    this.rangeOutlineLine.position.set(pos.x, 0.055, pos.z);
  }

  /**
   * Queue a new message animation or dropped packet marker.
   */
  public triggerAnimation(anim: V2VMessageAnimation): void {
    if (!this.options.showAnimations) return;

    // Prevent unbounded memory growth by evicting oldest
    if (this.activeAnimations.length >= this.maxActiveAnimations) {
      const evicted = this.activeAnimations.shift();
      if (evicted) {
        const mesh = this.animationMeshes.get(evicted.id);
        if (mesh) {
          this.animationsGroup.remove(mesh);
          this.animationMeshes.delete(evicted.id);
        }
      }
    }

    this.activeAnimations.push(anim);

    // Create visual mesh for animation
    if (anim.type === "dropped") {
      const dropMesh = new THREE.Mesh(this.dropBoxGeo, this.dropMarkerMaterial);
      dropMesh.position.set(
        anim.startWorldPos.x,
        anim.startWorldPos.y + 1.5,
        anim.startWorldPos.z
      );
      this.animationsGroup.add(dropMesh);
      this.animationMeshes.set(anim.id, dropMesh);
    } else {
      const pulseMesh = new THREE.Mesh(this.pulseSphereGeo, this.pulseSphereMaterial);
      pulseMesh.position.set(
        anim.startWorldPos.x,
        anim.startWorldPos.y + 1.2,
        anim.startWorldPos.z
      );
      this.animationsGroup.add(pulseMesh);
      this.animationMeshes.set(anim.id, pulseMesh);
    }
  }

  /**
   * Advance animations in sync with simulation playback speed and pause state.
   */
  public updateAnimations(
    deltaS: number,
    playbackSpeed: number,
    isPaused: boolean,
    prefersReducedMotion: boolean
  ): void {
    if (!this.options.showAnimations) {
      this.animationsGroup.visible = false;
      return;
    }
    this.animationsGroup.visible = true;

    // Pausing freezes presentation animations
    if (isPaused) {
      return;
    }

    const completedIds: string[] = [];
    const speedFactor = Math.max(0.1, playbackSpeed);

    for (let i = 0; i < this.activeAnimations.length; i++) {
      const anim = this.activeAnimations[i];
      const mesh = this.animationMeshes.get(anim.id);

      // Advance progress
      const step = (deltaS * speedFactor) / Math.max(0.1, anim.durationS);
      anim.elapsedS += deltaS * speedFactor;
      anim.progress = Math.min(1.0, anim.progress + step);

      if (mesh) {
        if (anim.type === "dropped") {
          // Subtle pulse and fade for dropped packet
          const scale = 1.0 + anim.progress * 0.8;
          mesh.scale.set(scale, scale, scale);
          if (mesh instanceof THREE.Mesh && mesh.material instanceof THREE.MeshBasicMaterial) {
            mesh.material.opacity = Math.max(0, 0.95 * (1.0 - anim.progress));
          }
        } else if (anim.endWorldPos) {
          // Traveling pulse along link trajectory
          const t = anim.progress;
          const x = anim.startWorldPos.x + (anim.endWorldPos.x - anim.startWorldPos.x) * t;
          const y = (anim.startWorldPos.y + (anim.endWorldPos.y - anim.startWorldPos.y) * t) + 1.2;
          const z = anim.startWorldPos.z + (anim.endWorldPos.z - anim.startWorldPos.z) * t;
          mesh.position.set(x, y, z);

          // Subtle pulse scale if not reduced motion
          if (!prefersReducedMotion) {
            const pulseScale = 1.0 + 0.3 * Math.sin(t * Math.PI);
            mesh.scale.set(pulseScale, pulseScale, pulseScale);
          }
        } else {
          // Broadcast expanding radius from sender
          const radiusScale = 1.0 + anim.progress * 3.0;
          mesh.scale.set(radiusScale, 1.0, radiusScale);
          if (mesh instanceof THREE.Mesh && mesh.material instanceof THREE.MeshBasicMaterial) {
            mesh.material.opacity = Math.max(0, 0.9 * (1.0 - anim.progress));
          }
        }
      }

      if (anim.progress >= 1.0) {
        completedIds.push(anim.id);
      }
    }

    // Clean up finished animations
    for (const id of completedIds) {
      const mesh = this.animationMeshes.get(id);
      if (mesh) {
        this.animationsGroup.remove(mesh);
        this.animationMeshes.delete(id);
      }
      this.activeAnimations = this.activeAnimations.filter((a) => a.id !== id);
    }
  }

  /**
   * Reset and clear all active link meshes and animation objects on run change.
   */
  public clear(): void {
    // Clear links
    for (const mesh of this.linkMeshes.values()) {
      this.linksGroup.remove(mesh);
      mesh.geometry.dispose();
    }
    this.linkMeshes.clear();

    // Clear range ring
    if (this.rangeRingMesh) {
      this.rangeGroup.remove(this.rangeRingMesh);
      this.rangeRingMesh.geometry.dispose();
      this.rangeRingMesh = null;
    }
    if (this.rangeOutlineLine) {
      this.rangeGroup.remove(this.rangeOutlineLine);
      this.rangeOutlineLine.geometry.dispose();
      this.rangeOutlineLine = null;
    }
    this.currentRangeRadius = null;

    // Clear animations
    for (const mesh of this.animationMeshes.values()) {
      this.animationsGroup.remove(mesh);
    }
    this.animationMeshes.clear();
    this.activeAnimations = [];

    for (const sprite of this.messageLabels.values()) {
      this.messageLabelsGroup.remove(sprite);
      sprite.material.map?.dispose();
      sprite.material.dispose();
    }
    this.messageLabels.clear();
  }

  /**
   * Full teardown and disposal of materials and shared geometries.
   */
  public dispose(): void {
    this.clear();
    this.activeLinkMaterial.dispose();
    this.staleLinkMaterial.dispose();
    this.rangeFillMaterial.dispose();
    this.rangeOutlineMaterial.dispose();
    this.pulseSphereMaterial.dispose();
    this.dropMarkerMaterial.dispose();
    this.pulseSphereGeo.dispose();
    this.dropBoxGeo.dispose();
  }
}
