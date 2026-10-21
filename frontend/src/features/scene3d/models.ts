/**
 * Procedural Low-Poly Vehicle & Pedestrian Model Factories for AMAPP 3D Viewport.
 *
 * Implements reusable geometry and material caching for Sedan, Truck, Bus, Ambulance,
 * Fire Engine, Unknown fallback, and Pedestrian models.
 * Supports subtle presentation-only emergency beacon pulsing and pedestrian walking cues.
 */

import * as THREE from "three";

export type VehicleModelType =
  | "sedan"
  | "truck"
  | "bus"
  | "ambulance"
  | "fire_engine"
  | "unknown";

/**
 * Maps vehicle identifiers, domain types, and scenario parameters to appropriate 3D model categories.
 */
export function determineVehicleModelType(
  vehicleId: string,
  vehicleType?: string,
  emergencyType?: string,
  explicitModelType?: string
): VehicleModelType {
  if (
    explicitModelType === "sedan" ||
    explicitModelType === "truck" ||
    explicitModelType === "bus" ||
    explicitModelType === "ambulance" ||
    explicitModelType === "fire_engine" ||
    explicitModelType === "unknown"
  ) {
    return explicitModelType;
  }

  const vIdLower = (vehicleId || "").toLowerCase();

  // Check emergency type classifications first
  if (emergencyType === "ambulance") return "ambulance";
  if (emergencyType === "fire_engine") return "fire_engine";
  if (emergencyType === "police") return "ambulance";

  // Check ID prefixes/patterns
  if (vIdLower.startsWith("amb_") || vIdLower.includes("ambulance")) return "ambulance";
  if (vIdLower.startsWith("fire_") || vIdLower.includes("fire")) return "fire_engine";
  if (vIdLower.startsWith("truck_") || vIdLower.includes("truck")) return "truck";
  if (vIdLower.startsWith("bus_") || vIdLower.includes("bus")) return "bus";
  if (vIdLower.startsWith("emerg_") || vehicleType === "emergency") return "ambulance";

  if (vehicleType === "standard") return "sedan";

  return "sedan";
}

/**
 * Singleton cache for reusable geometries and materials to avoid allocations per frame.
 */
class ModelAssetCache {
  private static instance: ModelAssetCache;

  // Geometries
  public wheelGeo!: THREE.CylinderGeometry;
  public headlightGeo!: THREE.BoxGeometry;
  public taillightGeo!: THREE.BoxGeometry;
  public beaconGeo!: THREE.BoxGeometry;

  // Sedan
  public sedanBodyGeo!: THREE.BoxGeometry;
  public sedanCabinGeo!: THREE.BoxGeometry;

  // Truck
  public truckChassisGeo!: THREE.BoxGeometry;
  public truckCabGeo!: THREE.BoxGeometry;
  public truckCargoGeo!: THREE.BoxGeometry;

  // Bus
  public busBodyGeo!: THREE.BoxGeometry;
  public busWindowsGeo!: THREE.BoxGeometry;

  // Ambulance
  public ambulanceBodyGeo!: THREE.BoxGeometry;
  public ambulanceCrossHGeo!: THREE.BoxGeometry;
  public ambulanceCrossVGeo!: THREE.BoxGeometry;

  // Fire Engine
  public fireChassisGeo!: THREE.BoxGeometry;
  public fireCabGeo!: THREE.BoxGeometry;
  public fireLadderGeo!: THREE.BoxGeometry;

  // Pedestrian
  public pedTorsoGeo!: THREE.BoxGeometry;
  public pedHeadGeo!: THREE.SphereGeometry;
  public pedLegGeo!: THREE.BoxGeometry;

  // Materials
  public sedanBodyMat!: THREE.MeshLambertMaterial;
  public truckBodyMat!: THREE.MeshLambertMaterial;
  public busBodyMat!: THREE.MeshLambertMaterial;
  public ambulanceBodyMat!: THREE.MeshLambertMaterial;
  public ambulanceCrossMat!: THREE.MeshLambertMaterial;
  public fireEngineBodyMat!: THREE.MeshLambertMaterial;
  public fireLadderMat!: THREE.MeshLambertMaterial;
  public fallbackBodyMat!: THREE.MeshLambertMaterial;
  public windowDarkMat!: THREE.MeshLambertMaterial;
  public wheelMat!: THREE.MeshLambertMaterial;
  public headlightMat!: THREE.MeshBasicMaterial;
  public taillightMat!: THREE.MeshBasicMaterial;

  // Beacon Materials
  public beaconBlueActiveMat!: THREE.MeshBasicMaterial;
  public beaconRedActiveMat!: THREE.MeshBasicMaterial;
  public beaconAmberActiveMat!: THREE.MeshBasicMaterial;
  public beaconInactiveMat!: THREE.MeshLambertMaterial;

  // Pedestrian Materials
  public pedShirtMat!: THREE.MeshLambertMaterial;
  public pedShirtCrossingMat!: THREE.MeshLambertMaterial;
  public pedSkinMat!: THREE.MeshLambertMaterial;
  public pedPantsMat!: THREE.MeshLambertMaterial;

  private isInitialized = false;

  public static getInstance(): ModelAssetCache {
    if (!ModelAssetCache.instance) {
      ModelAssetCache.instance = new ModelAssetCache();
    }
    return ModelAssetCache.instance;
  }

  public init(): void {
    if (this.isInitialized) return;

    // Common Geometries
    this.wheelGeo = new THREE.CylinderGeometry(0.35, 0.35, 0.22, 12);
    this.headlightGeo = new THREE.BoxGeometry(0.45, 0.18, 0.08);
    this.taillightGeo = new THREE.BoxGeometry(0.45, 0.18, 0.08);
    this.beaconGeo = new THREE.BoxGeometry(0.35, 0.2, 0.25);

    // Sedan: ~4.4m L x 2.0m W x 1.4m H
    this.sedanBodyGeo = new THREE.BoxGeometry(2.0, 0.7, 4.4);
    this.sedanCabinGeo = new THREE.BoxGeometry(1.75, 0.65, 2.3);

    // Truck: ~7.4m L x 2.4m W x 2.8m H
    this.truckChassisGeo = new THREE.BoxGeometry(2.4, 0.7, 7.4);
    this.truckCabGeo = new THREE.BoxGeometry(2.3, 1.8, 1.8);
    this.truckCargoGeo = new THREE.BoxGeometry(2.4, 2.1, 5.2);

    // Bus: ~9.6m L x 2.5m W x 2.9m H
    this.busBodyGeo = new THREE.BoxGeometry(2.5, 2.6, 9.6);
    this.busWindowsGeo = new THREE.BoxGeometry(2.54, 0.85, 8.8);

    // Ambulance: ~5.6m L x 2.2m W x 2.3m H
    this.ambulanceBodyGeo = new THREE.BoxGeometry(2.2, 1.9, 5.6);
    this.ambulanceCrossHGeo = new THREE.BoxGeometry(0.65, 0.2, 0.04);
    this.ambulanceCrossVGeo = new THREE.BoxGeometry(0.2, 0.65, 0.04);

    // Fire Engine: ~8.0m L x 2.6m W x 2.8m H
    this.fireChassisGeo = new THREE.BoxGeometry(2.6, 1.8, 8.0);
    this.fireCabGeo = new THREE.BoxGeometry(2.5, 1.9, 2.2);
    this.fireLadderGeo = new THREE.BoxGeometry(1.1, 0.2, 5.2);

    // Pedestrian: ~1.75m H, 0.45m W
    this.pedTorsoGeo = new THREE.BoxGeometry(0.45, 0.65, 0.28);
    this.pedHeadGeo = new THREE.SphereGeometry(0.2, 8, 8);
    this.pedLegGeo = new THREE.BoxGeometry(0.18, 0.75, 0.2);

    // Materials
    this.sedanBodyMat = new THREE.MeshLambertMaterial({ color: 0x2563eb }); // Vibrant royal blue
    this.truckBodyMat = new THREE.MeshLambertMaterial({ color: 0x0d9488 }); // Commercial teal
    this.busBodyMat = new THREE.MeshLambertMaterial({ color: 0x059669 }); // Emerald green
    this.ambulanceBodyMat = new THREE.MeshLambertMaterial({ color: 0xf8fafc }); // Clean white
    this.ambulanceCrossMat = new THREE.MeshLambertMaterial({ color: 0xdc2626 }); // Emergency red
    this.fireEngineBodyMat = new THREE.MeshLambertMaterial({ color: 0xdc2626 }); // Fire red
    this.fireLadderMat = new THREE.MeshLambertMaterial({ color: 0x94a3b8 }); // Metallic silver
    this.fallbackBodyMat = new THREE.MeshLambertMaterial({ color: 0x64748b }); // Neutral slate

    this.windowDarkMat = new THREE.MeshLambertMaterial({ color: 0x0f172a }); // Tinted glass
    this.wheelMat = new THREE.MeshLambertMaterial({ color: 0x1e293b }); // Dark rubber
    this.headlightMat = new THREE.MeshBasicMaterial({ color: 0xfef08a }); // Light yellow beam
    this.taillightMat = new THREE.MeshBasicMaterial({ color: 0xef4444 }); // Tail red

    // Beacons
    this.beaconBlueActiveMat = new THREE.MeshBasicMaterial({ color: 0x0284c7 });
    this.beaconRedActiveMat = new THREE.MeshBasicMaterial({ color: 0xdc2626 });
    this.beaconAmberActiveMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b });
    this.beaconInactiveMat = new THREE.MeshLambertMaterial({ color: 0x334155 });

    // Pedestrian Materials
    this.pedShirtMat = new THREE.MeshLambertMaterial({ color: 0x06b6d4 }); // Cyan shirt
    this.pedShirtCrossingMat = new THREE.MeshLambertMaterial({ color: 0xf59e0b }); // Amber high-visibility
    this.pedSkinMat = new THREE.MeshLambertMaterial({ color: 0xfed7aa });
    this.pedPantsMat = new THREE.MeshLambertMaterial({ color: 0x334155 });

    this.isInitialized = true;
  }

  public dispose(): void {
    if (!this.isInitialized) return;

    const geos: THREE.BufferGeometry[] = [
      this.wheelGeo,
      this.headlightGeo,
      this.taillightGeo,
      this.beaconGeo,
      this.sedanBodyGeo,
      this.sedanCabinGeo,
      this.truckChassisGeo,
      this.truckCabGeo,
      this.truckCargoGeo,
      this.busBodyGeo,
      this.busWindowsGeo,
      this.ambulanceBodyGeo,
      this.ambulanceCrossHGeo,
      this.ambulanceCrossVGeo,
      this.fireChassisGeo,
      this.fireCabGeo,
      this.fireLadderGeo,
      this.pedTorsoGeo,
      this.pedHeadGeo,
      this.pedLegGeo,
    ];
    geos.forEach((g) => g?.dispose());

    const mats: THREE.Material[] = [
      this.sedanBodyMat,
      this.truckBodyMat,
      this.busBodyMat,
      this.ambulanceBodyMat,
      this.ambulanceCrossMat,
      this.fireEngineBodyMat,
      this.fireLadderMat,
      this.fallbackBodyMat,
      this.windowDarkMat,
      this.wheelMat,
      this.headlightMat,
      this.taillightMat,
      this.beaconBlueActiveMat,
      this.beaconRedActiveMat,
      this.beaconAmberActiveMat,
      this.beaconInactiveMat,
      this.pedShirtMat,
      this.pedShirtCrossingMat,
      this.pedSkinMat,
      this.pedPantsMat,
    ];
    mats.forEach((m) => m?.dispose());

    this.isInitialized = false;
  }
}

/**
 * Helper to add standard 4 or 6 wheels to a vehicle group.
 */
function addWheels(
  group: THREE.Group,
  cache: ModelAssetCache,
  halfWidth: number,
  wheelZPositions: number[],
  wheelRadius = 0.35
): void {
  for (const z of wheelZPositions) {
    // Left wheel
    const leftWheel = new THREE.Mesh(cache.wheelGeo, cache.wheelMat);
    leftWheel.rotation.z = Math.PI / 2;
    leftWheel.position.set(-halfWidth, wheelRadius, z);
    group.add(leftWheel);

    // Right wheel
    const rightWheel = new THREE.Mesh(cache.wheelGeo, cache.wheelMat);
    rightWheel.rotation.z = Math.PI / 2;
    rightWheel.position.set(halfWidth, wheelRadius, z);
    group.add(rightWheel);
  }
}

/**
 * Helper to add front headlights and rear taillights.
 */
function addLights(
  group: THREE.Group,
  cache: ModelAssetCache,
  halfWidth: number,
  frontZ: number,
  rearZ: number,
  lightY: number
): void {
  const xOffset = halfWidth * 0.65;

  // Front Left Headlight
  const flLight = new THREE.Mesh(cache.headlightGeo, cache.headlightMat);
  flLight.position.set(-xOffset, lightY, frontZ + 0.04);
  group.add(flLight);

  // Front Right Headlight
  const frLight = new THREE.Mesh(cache.headlightGeo, cache.headlightMat);
  frLight.position.set(xOffset, lightY, frontZ + 0.04);
  group.add(frLight);

  // Rear Left Taillight
  const rlLight = new THREE.Mesh(cache.taillightGeo, cache.taillightMat);
  rlLight.position.set(-xOffset, lightY, rearZ - 0.04);
  group.add(rlLight);

  // Rear Right Taillight
  const rrLight = new THREE.Mesh(cache.taillightGeo, cache.taillightMat);
  rrLight.position.set(xOffset, lightY, rearZ - 0.04);
  group.add(rrLight);
}

export interface CreateVehicleModelOptions {
  vehicleId?: string;
  isEmergency?: boolean;
}

/**
 * Creates a reusable Three.js Group representing a low-poly vehicle based on its visual category.
 * Geometries and materials are shared from the ModelAssetCache.
 */
export function createVehicleModel(
  modelType: VehicleModelType,
  options: CreateVehicleModelOptions = {}
): THREE.Group {
  const cache = ModelAssetCache.getInstance();
  cache.init();

  const group = new THREE.Group();
  group.name = options.vehicleId || `veh_${modelType}`;
  group.userData = {
    entityType: "vehicle",
    modelType,
    vehicleId: options.vehicleId,
    isEmergency: options.isEmergency ?? (modelType === "ambulance" || modelType === "fire_engine"),
    beacons: [] as THREE.Mesh[],
  };

  switch (modelType) {
    case "truck": {
      // Lower chassis
      const chassis = new THREE.Mesh(cache.truckChassisGeo, cache.truckBodyMat);
      chassis.position.y = 0.7;
      group.add(chassis);

      // Front cab
      const cab = new THREE.Mesh(cache.truckCabGeo, cache.windowDarkMat);
      cab.position.set(0, 1.8, 2.6);
      group.add(cab);

      // Cargo bed / container
      const cargo = new THREE.Mesh(cache.truckCargoGeo, cache.truckBodyMat);
      cargo.position.set(0, 2.0, -1.0);
      group.add(cargo);

      addWheels(group, cache, 1.2, [2.5, -1.2, -2.6]);
      addLights(group, cache, 1.15, 3.7, -3.7, 0.7);
      break;
    }

    case "bus": {
      // Main elongated body
      const body = new THREE.Mesh(cache.busBodyGeo, cache.busBodyMat);
      body.position.y = 1.6;
      group.add(body);

      // Dark passenger windows stripe
      const windows = new THREE.Mesh(cache.busWindowsGeo, cache.windowDarkMat);
      windows.position.set(0, 2.0, 0);
      group.add(windows);

      addWheels(group, cache, 1.25, [3.2, -2.0, -3.4]);
      addLights(group, cache, 1.2, 4.8, -4.8, 0.75);
      break;
    }

    case "ambulance": {
      // Boxy van body
      const body = new THREE.Mesh(cache.ambulanceBodyGeo, cache.ambulanceBodyMat);
      body.position.y = 1.25;
      group.add(body);

      // Cabin windshield accent
      const windshield = new THREE.Mesh(
        new THREE.BoxGeometry(2.0, 0.65, 0.1),
        cache.windowDarkMat
      );
      windshield.position.set(0, 1.6, 2.81);
      group.add(windshield);

      // Medical red cross on Left Side
      const crossLeftH = new THREE.Mesh(cache.ambulanceCrossHGeo, cache.ambulanceCrossMat);
      crossLeftH.position.set(-1.11, 1.4, -0.4);
      crossLeftH.rotation.y = Math.PI / 2;
      group.add(crossLeftH);

      const crossLeftV = new THREE.Mesh(cache.ambulanceCrossVGeo, cache.ambulanceCrossMat);
      crossLeftV.position.set(-1.11, 1.4, -0.4);
      crossLeftV.rotation.y = Math.PI / 2;
      group.add(crossLeftV);

      // Medical red cross on Right Side
      const crossRightH = new THREE.Mesh(cache.ambulanceCrossHGeo, cache.ambulanceCrossMat);
      crossRightH.position.set(1.11, 1.4, -0.4);
      crossRightH.rotation.y = -Math.PI / 2;
      group.add(crossRightH);

      const crossRightV = new THREE.Mesh(cache.ambulanceCrossVGeo, cache.ambulanceCrossMat);
      crossRightV.position.set(1.11, 1.4, -0.4);
      crossRightV.rotation.y = -Math.PI / 2;
      group.add(crossRightV);

      // Roof emergency light bar (Blue Left, Red Right)
      const beaconL = new THREE.Mesh(cache.beaconGeo, cache.beaconBlueActiveMat);
      beaconL.position.set(-0.45, 2.3, 1.0);
      beaconL.userData = { beaconColor: "blue" };
      group.add(beaconL);

      const beaconR = new THREE.Mesh(cache.beaconGeo, cache.beaconRedActiveMat);
      beaconR.position.set(0.45, 2.3, 1.0);
      beaconR.userData = { beaconColor: "red" };
      group.add(beaconR);

      group.userData.beacons = [beaconL, beaconR];

      addWheels(group, cache, 1.1, [1.8, -1.8]);
      addLights(group, cache, 1.05, 2.8, -2.8, 0.65);
      break;
    }

    case "fire_engine": {
      // Heavy chassis
      const chassis = new THREE.Mesh(cache.fireChassisGeo, cache.fireEngineBodyMat);
      chassis.position.y = 1.1;
      group.add(chassis);

      // Front cab
      const cab = new THREE.Mesh(cache.fireCabGeo, cache.windowDarkMat);
      cab.position.set(0, 1.8, 2.8);
      group.add(cab);

      // Roof metallic ladder
      const ladder = new THREE.Mesh(cache.fireLadderGeo, cache.fireLadderMat);
      ladder.position.set(0, 2.15, -0.8);
      group.add(ladder);

      // Roof light bar (Red Left, Amber Right)
      const beaconL = new THREE.Mesh(cache.beaconGeo, cache.beaconRedActiveMat);
      beaconL.position.set(-0.6, 2.85, 2.6);
      beaconL.userData = { beaconColor: "red" };
      group.add(beaconL);

      const beaconR = new THREE.Mesh(cache.beaconGeo, cache.beaconAmberActiveMat);
      beaconR.position.set(0.6, 2.85, 2.6);
      beaconR.userData = { beaconColor: "amber" };
      group.add(beaconR);

      group.userData.beacons = [beaconL, beaconR];

      addWheels(group, cache, 1.3, [2.7, -1.4, -2.8]);
      addLights(group, cache, 1.25, 4.0, -4.0, 0.7);
      break;
    }

    case "unknown":
    case "sedan":
    default: {
      // Lower body
      const bodyMat = modelType === "unknown" ? cache.fallbackBodyMat : cache.sedanBodyMat;
      const body = new THREE.Mesh(cache.sedanBodyGeo, bodyMat);
      body.position.y = 0.55;
      group.add(body);

      // Cabin / Greenhouse
      const cabin = new THREE.Mesh(cache.sedanCabinGeo, cache.windowDarkMat);
      cabin.position.set(0, 1.2, -0.2);
      group.add(cabin);

      addWheels(group, cache, 1.0, [1.4, -1.4]);
      addLights(group, cache, 0.95, 2.2, -2.2, 0.55);
      break;
    }
  }

  return group;
}

export interface CreatePedestrianModelOptions {
  pedestrianId?: string;
  isCrossing?: boolean;
}

/**
 * Creates a low-poly pedestrian avatar (torso, head, left/right animated legs).
 * Placed at ground/curb elevation with realistic human proportions (~1.75m).
 */
export function createPedestrianModel(
  options: CreatePedestrianModelOptions = {}
): THREE.Group {
  const cache = ModelAssetCache.getInstance();
  cache.init();

  const group = new THREE.Group();
  group.name = options.pedestrianId || "pedestrian";

  // Torso
  const shirtMat = options.isCrossing ? cache.pedShirtCrossingMat : cache.pedShirtMat;
  const torso = new THREE.Mesh(cache.pedTorsoGeo, shirtMat);
  torso.position.y = 1.05;
  group.add(torso);

  // Head
  const head = new THREE.Mesh(cache.pedHeadGeo, cache.pedSkinMat);
  head.position.y = 1.58;
  group.add(head);

  // Left Leg
  const leftLegPivot = new THREE.Group();
  leftLegPivot.position.set(-0.13, 0.75, 0);
  const leftLeg = new THREE.Mesh(cache.pedLegGeo, cache.pedPantsMat);
  leftLeg.position.y = -0.375;
  leftLegPivot.add(leftLeg);
  group.add(leftLegPivot);

  // Right Leg
  const rightLegPivot = new THREE.Group();
  rightLegPivot.position.set(0.13, 0.75, 0);
  const rightLeg = new THREE.Mesh(cache.pedLegGeo, cache.pedPantsMat);
  rightLeg.position.y = -0.375;
  rightLegPivot.add(rightLeg);
  group.add(rightLegPivot);

  group.userData = {
    entityType: "pedestrian",
    pedestrianId: options.pedestrianId,
    torso,
    leftLegPivot,
    rightLegPivot,
  };

  return group;
}

/**
 * Updates dynamic visual presentation for vehicles (e.g. subtle emergency beacon pulsation).
 * Does NOT mutate simulation state.
 */
export function updateVehicleVisuals(
  group: THREE.Group,
  state: {
    isEmergency?: boolean;
    isSelected?: boolean;
    speed_mps?: number;
  },
  elapsedS: number,
  prefersReducedMotion = false
): void {
  const cache = ModelAssetCache.getInstance();
  const beacons = group.userData.beacons as THREE.Mesh[] | undefined;

  if (beacons && beacons.length > 0) {
    const isEmergencyActive = !!state.isEmergency;

    if (!isEmergencyActive) {
      // Inactive emergency state: dim beacons to unlit material
      for (const b of beacons) {
        b.material = cache.beaconInactiveMat;
        b.visible = true;
      }
    } else if (prefersReducedMotion) {
      // Accessible static glow without strobing/flashing
      for (const b of beacons) {
        const color = b.userData.beaconColor;
        b.material =
          color === "blue"
            ? cache.beaconBlueActiveMat
            : color === "amber"
            ? cache.beaconAmberActiveMat
            : cache.beaconRedActiveMat;
        b.visible = true;
      }
    } else {
      // Subtle alternating 2.5 Hz pulse (left/right alternating)
      // Flash cycle period ~0.4s
      const flashPhase = (elapsedS * 2.5) % 1.0;
      const leftLit = flashPhase < 0.5;

      if (beacons.length >= 2) {
        const [bLeft, bRight] = beacons;
        bLeft.material = leftLit
          ? (bLeft.userData.beaconColor === "blue"
              ? cache.beaconBlueActiveMat
              : cache.beaconRedActiveMat)
          : cache.beaconInactiveMat;

        bRight.material = !leftLit
          ? (bRight.userData.beaconColor === "amber"
              ? cache.beaconAmberActiveMat
              : cache.beaconRedActiveMat)
          : cache.beaconInactiveMat;
      }
    }
  }

  // Visual selection outline scale
  const targetScale = state.isSelected ? 1.25 : 1.0;
  if (Math.abs(group.scale.x - targetScale) > 0.01) {
    group.scale.setScalar(targetScale);
  }
}

/**
 * Updates dynamic presentation for pedestrians (subtle procedural walking swing).
 * Does NOT mutate simulation state.
 */
export function updatePedestrianVisuals(
  group: THREE.Group,
  state: {
    speed_mps?: number;
    lifecycle_state?: string;
    isSelected?: boolean;
  },
  elapsedS: number,
  prefersReducedMotion = false
): void {
  const cache = ModelAssetCache.getInstance();
  const leftLeg = group.userData.leftLegPivot as THREE.Group | undefined;
  const rightLeg = group.userData.rightLegPivot as THREE.Group | undefined;
  const torso = group.userData.torso as THREE.Mesh | undefined;

  // Update shirt material based on crossing state
  if (torso) {
    const isCrossing = state.lifecycle_state === "crossing";
    torso.material = isCrossing ? cache.pedShirtCrossingMat : cache.pedShirtMat;
  }

  // Procedural leg swing when moving
  const speed = state.speed_mps ?? 0;
  const isMoving = speed > 0.05 && state.lifecycle_state !== "idle" && state.lifecycle_state !== "arrived";

  if (leftLeg && rightLeg) {
    if (!isMoving || prefersReducedMotion) {
      leftLeg.rotation.x = 0;
      rightLeg.rotation.x = 0;
    } else {
      // Cadence proportional to speed (clamped ~2 to 5 Hz)
      const cadence = Math.min(6.0, Math.max(2.0, speed * 2.8));
      const swingAngle = Math.sin(elapsedS * cadence * Math.PI * 2) * 0.45;
      leftLeg.rotation.x = swingAngle;
      rightLeg.rotation.x = -swingAngle;
    }
  }

  const targetScale = state.isSelected ? 1.3 : 1.0;
  if (Math.abs(group.scale.x - targetScale) > 0.01) {
    group.scale.setScalar(targetScale);
  }
}

/**
 * Cleanly disposes all cached geometries and materials on unmount.
 */
export function disposeModelAssets(): void {
  ModelAssetCache.getInstance().dispose();
}
