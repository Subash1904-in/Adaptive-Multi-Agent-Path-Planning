import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  createPedestrianModel,
  createVehicleModel,
  determineVehicleModelType,
  disposeModelAssets,
  updatePedestrianVisuals,
  updateVehicleVisuals,
} from "../features/scene3d/models";

describe("Vehicle & Pedestrian 3D Models", () => {
  describe("determineVehicleModelType", () => {
    it("identifies explicit model types accurately", () => {
      expect(determineVehicleModelType("v1", undefined, undefined, "truck")).toBe("truck");
      expect(determineVehicleModelType("v2", undefined, undefined, "bus")).toBe("bus");
      expect(determineVehicleModelType("v3", undefined, undefined, "unknown")).toBe("unknown");
    });

    it("identifies emergency types from metadata or ID naming", () => {
      expect(determineVehicleModelType("amb_01")).toBe("ambulance");
      expect(determineVehicleModelType("ambulance_unit_4")).toBe("ambulance");
      expect(determineVehicleModelType("fire_truck_02")).toBe("fire_engine");
      expect(determineVehicleModelType("v_em", "emergency")).toBe("ambulance");
      expect(determineVehicleModelType("v_em", undefined, "fire_engine")).toBe("fire_engine");
      expect(determineVehicleModelType("v_em", undefined, "ambulance")).toBe("ambulance");
    });

    it("identifies standard vehicle types", () => {
      expect(determineVehicleModelType("truck_heavy")).toBe("truck");
      expect(determineVehicleModelType("bus_line_5")).toBe("bus");
      expect(determineVehicleModelType("veh_01", "standard")).toBe("sedan");
      expect(determineVehicleModelType("car_test")).toBe("sedan");
    });
  });

  describe("Vehicle Model Creation & Structure", () => {
    it("creates a sedan with cabin, 4 wheels, and lights", () => {
      const sedan = createVehicleModel("sedan", { vehicleId: "veh_sedan_1" });
      expect(sedan).toBeInstanceOf(THREE.Group);
      expect(sedan.name).toBe("veh_sedan_1");
      expect(sedan.userData.modelType).toBe("sedan");

      // Verify child meshes (chassis, cabin, 4 wheels, 4 lights = 10 meshes)
      const meshes = sedan.children.filter((c) => c instanceof THREE.Mesh);
      expect(meshes.length).toBeGreaterThanOrEqual(10);
    });

    it("creates a truck with cab, cargo bed, and 6 wheels", () => {
      const truck = createVehicleModel("truck", { vehicleId: "veh_truck_1" });
      expect(truck.userData.modelType).toBe("truck");

      // Chassis, cab, cargo bed, 6 wheels, 4 lights = 13 meshes
      const meshes = truck.children.filter((c) => c instanceof THREE.Mesh);
      expect(meshes.length).toBeGreaterThanOrEqual(13);
    });

    it("creates a bus with elongated body, window stripe, and 6 wheels", () => {
      const bus = createVehicleModel("bus", { vehicleId: "veh_bus_1" });
      expect(bus.userData.modelType).toBe("bus");

      const meshes = bus.children.filter((c) => c instanceof THREE.Mesh);
      expect(meshes.length).toBeGreaterThanOrEqual(12);
    });

    it("creates an ambulance with medical cross markings and emergency beacons", () => {
      const amb = createVehicleModel("ambulance", { vehicleId: "amb_01" });
      expect(amb.userData.modelType).toBe("ambulance");
      expect(amb.userData.beacons?.length).toBe(2);

      // Verify medical cross meshes exist
      const crossMeshes = amb.children.filter(
        (c) => c instanceof THREE.Mesh && (c.material as THREE.MeshLambertMaterial)?.color?.getHex() === 0xdc2626
      );
      expect(crossMeshes.length).toBeGreaterThanOrEqual(2);
    });

    it("creates a fire engine with heavy chassis, cab, ladder, and beacons", () => {
      const fire = createVehicleModel("fire_engine", { vehicleId: "fire_01" });
      expect(fire.userData.modelType).toBe("fire_engine");
      expect(fire.userData.beacons?.length).toBe(2);

      // Verify silver ladder exists
      const ladder = fire.children.find(
        (c) => c instanceof THREE.Mesh && (c.material as THREE.MeshLambertMaterial)?.color?.getHex() === 0x94a3b8
      );
      expect(ladder).toBeDefined();
    });

    it("creates an unknown fallback vehicle with neutral styling", () => {
      const unknown = createVehicleModel("unknown", { vehicleId: "veh_unknown" });
      expect(unknown.userData.modelType).toBe("unknown");
      const bodyMesh = unknown.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh;
      expect(bodyMesh).toBeDefined();
      expect((bodyMesh.material as THREE.MeshLambertMaterial)?.color?.getHex()).toBe(0x64748b);
    });

    it("reuses geometry and material instances across multiple vehicle instances", () => {
      const sedan1 = createVehicleModel("sedan", { vehicleId: "s1" });
      const sedan2 = createVehicleModel("sedan", { vehicleId: "s2" });

      const body1 = sedan1.children[0] as THREE.Mesh;
      const body2 = sedan2.children[0] as THREE.Mesh;

      // Geometries and materials MUST be identical references in memory
      expect(body1.geometry).toBe(body2.geometry);
      expect(body1.material).toBe(body2.material);
    });
  });

  describe("Pedestrian Model Creation & Structure", () => {
    it("creates a low-poly pedestrian avatar with torso, head, and articulated legs", () => {
      const ped = createPedestrianModel({ pedestrianId: "ped_01" });
      expect(ped).toBeInstanceOf(THREE.Group);
      expect(ped.name).toBe("ped_01");
      expect(ped.userData.entityType).toBe("pedestrian");
      expect(ped.userData.torso).toBeDefined();
      expect(ped.userData.leftLegPivot).toBeDefined();
      expect(ped.userData.rightLegPivot).toBeDefined();
    });

    it("reuses geometry and materials between pedestrian instances", () => {
      const ped1 = createPedestrianModel({ pedestrianId: "p1" });
      const ped2 = createPedestrianModel({ pedestrianId: "p2" });

      const torso1 = ped1.userData.torso as THREE.Mesh;
      const torso2 = ped2.userData.torso as THREE.Mesh;
      expect(torso1.geometry).toBe(torso2.geometry);
      expect(torso1.material).toBe(torso2.material);
    });
  });

  describe("Dynamic Visual Updates (Animation & Emergency Lighting)", () => {
    it("alternates emergency beacon materials when emergency is active", () => {
      const amb = createVehicleModel("ambulance", { vehicleId: "amb_01", isEmergency: true });
      const beacons = amb.userData.beacons as THREE.Mesh[];

      // Phase 1 (elapsed 0.0s)
      updateVehicleVisuals(amb, { isEmergency: true }, 0.0, false);
      const b0MatPhase1 = beacons[0].material;

      // Phase 2 (elapsed 0.25s: half cycle for 2.5Hz cadence)
      updateVehicleVisuals(amb, { isEmergency: true }, 0.25, false);
      const b0MatPhase2 = beacons[0].material;

      // Left beacon material toggles between active and inactive
      expect(b0MatPhase1).not.toBe(b0MatPhase2);
    });

    it("dims emergency beacons when emergency is inactive", () => {
      const amb = createVehicleModel("ambulance", { vehicleId: "amb_01" });
      const beacons = amb.userData.beacons as THREE.Mesh[];

      updateVehicleVisuals(amb, { isEmergency: false }, 1.0, false);
      for (const b of beacons) {
        expect((b.material as THREE.MeshLambertMaterial)?.color?.getHex()).toBe(0x334155); // beaconInactiveMat
      }
    });

    it("respects prefers-reduced-motion for emergency beacons", () => {
      const amb = createVehicleModel("ambulance", { vehicleId: "amb_01" });
      const beacons = amb.userData.beacons as THREE.Mesh[];

      updateVehicleVisuals(amb, { isEmergency: true }, 0.1, true);
      const mat1 = beacons[0].material;

      updateVehicleVisuals(amb, { isEmergency: true }, 0.3, true);
      const mat2 = beacons[0].material;

      // Beacon does NOT alternate/flash when reduced motion is preferred
      expect(mat1).toBe(mat2);
    });

    it("animates pedestrian legs during movement and resets when stopped", () => {
      const ped = createPedestrianModel({ pedestrianId: "ped_01" });
      const leftLeg = ped.userData.leftLegPivot as THREE.Group;
      const rightLeg = ped.userData.rightLegPivot as THREE.Group;

      // Moving pedestrian
      updatePedestrianVisuals(ped, { speed_mps: 1.4, lifecycle_state: "walking" }, 0.25, false);
      expect(leftLeg.rotation.x).not.toBe(0);
      expect(rightLeg.rotation.x).not.toBe(0);
      // Legs swing in opposite phases
      expect(leftLeg.rotation.x).toBeCloseTo(-rightLeg.rotation.x, 5);

      // Stopped pedestrian
      updatePedestrianVisuals(ped, { speed_mps: 0.0, lifecycle_state: "waiting_to_cross" }, 0.25, false);
      expect(leftLeg.rotation.x).toBe(0);
      expect(rightLeg.rotation.x).toBe(0);
    });

    it("updates pedestrian shirt to high-visibility amber when crossing", () => {
      const ped = createPedestrianModel({ pedestrianId: "ped_01" });
      const torso = ped.userData.torso as THREE.Mesh;

      updatePedestrianVisuals(ped, { lifecycle_state: "crossing" }, 0.0);
      expect((torso.material as THREE.MeshLambertMaterial)?.color?.getHex()).toBe(0xf59e0b); // amber

      updatePedestrianVisuals(ped, { lifecycle_state: "walking" }, 0.0);
      expect((torso.material as THREE.MeshLambertMaterial)?.color?.getHex()).toBe(0x06b6d4); // cyan
    });
  });

  describe("Resource Disposal", () => {
    it("disposes cached assets without throwing", () => {
      expect(() => disposeModelAssets()).not.toThrow();
    });
  });
});
