/**
 * Interactive 3D Simulation Viewport for AMAPP.
 * Built with Three.js rendering road networks, vehicles, pedestrians, traffic signals, and routes.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import type { RoadNetworkGeometry, RoadNodeGeometry } from "../../types/graph";
import type {
  PedestrianState,
  ScenarioDefinition,
  TrafficSignalState,
  VehicleState,
} from "../../types/simulation";
import { computeNetworkBounds, extractRoadNetworkFromScenario, simToWorldCoordinates } from "./geometry";

export interface SimulationViewer3DProps {
  scenario: ScenarioDefinition | null;
  vehicles: Map<string, VehicleState>;
  pedestrians: Map<string, PedestrianState>;
  signals: Map<string, TrafficSignalState>;
  activeRoute?: string[];
  selectedEntityId?: string | null;
  onSelectEntity?: (entityId: string, entityType: "vehicle" | "pedestrian") => void;
  isLoading?: boolean;
}

export const SimulationViewer3D: React.FC<SimulationViewer3DProps> = ({
  scenario,
  vehicles,
  pedestrians,
  signals,
  activeRoute,
  selectedEntityId,
  onSelectEntity,
  isLoading = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Three.js internal references
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const animFrameIdRef = useRef<number | null>(null);

  // Rendering object pools
  const roadGroupRef = useRef<THREE.Group>(new THREE.Group());
  const vehicleMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const pedestrianMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const signalMeshesRef = useRef<Map<string, THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>>>(new Map());
  const routeLineRef = useRef<THREE.Line | null>(null);

  // Mouse interaction state for camera orbit / pan / zoom
  const isDraggingRef = useRef(false);
  const dragButtonRef = useRef<number>(0);
  const prevMousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const cameraTargetRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const cameraDistanceRef = useRef<number>(200);
  const cameraAngleRef = useRef<{ theta: number; phi: number }>({
    theta: Math.PI / 4,
    phi: Math.PI / 3,
  });

  const [activeGeometry, setActiveGeometry] = useState<RoadNetworkGeometry>(() =>
    extractRoadNetworkFromScenario(scenario)
  );

  // 1. Update Road Network Geometry when scenario changes
  useEffect(() => {
    const geom = extractRoadNetworkFromScenario(scenario);
    setActiveGeometry(geom);
  }, [scenario]);

  // 2. Camera position updater helper
  const updateCameraPosition = useCallback(() => {
    if (!cameraRef.current) return;
    const { theta, phi } = cameraAngleRef.current;
    const r = cameraDistanceRef.current;
    const target = cameraTargetRef.current;

    cameraRef.current.position.set(
      target.x + r * Math.sin(phi) * Math.sin(theta),
      target.y + r * Math.cos(phi),
      target.z + r * Math.sin(phi) * Math.cos(theta)
    );
    cameraRef.current.lookAt(target);
  }, []);

  // 3. Reset Camera View
  const handleResetCamera = useCallback(() => {
    const bounds = computeNetworkBounds(activeGeometry);
    cameraTargetRef.current.set(bounds.center.x, 0, bounds.center.z);
    cameraDistanceRef.current = Math.max(bounds.size.width, bounds.size.depth) * 1.5;
    cameraAngleRef.current = { theta: Math.PI / 4, phi: Math.PI / 3.5 };
    updateCameraPosition();
  }, [activeGeometry, updateCameraPosition]);

  // 4. Initialize Three.js Scene and Renderer
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f1d);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
    cameraRef.current = camera;

    // Renderer
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      rendererRef.current = renderer;
    } catch (err) {
      console.warn("WebGL initialization note:", err);
      return;
    }

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight.position.set(150, 300, 150);
    scene.add(dirLight);

    // Ground Grid Helper
    const grid = new THREE.GridHelper(1000, 50, 0x1e293b, 0x0f172a);
    grid.position.y = -0.1;
    scene.add(grid);

    // Road network group
    scene.add(roadGroupRef.current);

    // Initial camera placement
    handleResetCamera();

    // Render loop
    const animate = () => {
      animFrameIdRef.current = requestAnimationFrame(animate);
      if (rendererRef.current && sceneRef.current && cameraRef.current) {
        rendererRef.current.render(sceneRef.current, cameraRef.current);
      }
    };
    animate();

    // Resize observer
    const handleResize = () => {
      if (!container || !rendererRef.current || !cameraRef.current) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) return;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
      renderer.dispose();
    };
  }, [handleResetCamera]);

  // 5. Rebuild Road Network Meshes when activeGeometry changes
  useEffect(() => {
    const roadGroup = roadGroupRef.current;
    // Clear old children
    while (roadGroup.children.length > 0) {
      const child = roadGroup.children.pop();
      if (child) roadGroup.remove(child);
    }

    const nodeMap = new Map<string, RoadNodeGeometry>();
    for (const node of activeGeometry.nodes) {
      nodeMap.set(node.id, node);

      // Node junction pad
      const nodePos = simToWorldCoordinates(node.x, node.y, 0.05);
      const junctionGeo = new THREE.CylinderGeometry(6, 6, 0.1, 16);
      const junctionMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
      const junctionMesh = new THREE.Mesh(junctionGeo, junctionMat);
      junctionMesh.position.set(nodePos.x, nodePos.y, nodePos.z);
      roadGroup.add(junctionMesh);
    }

    // Edges
    const roadMat = new THREE.MeshLambertMaterial({ color: 0x111827 });
    const lineMat = new THREE.LineBasicMaterial({ color: 0x475569 });

    const processedSegments = new Set<string>();

    for (const edge of activeGeometry.edges) {
      const u = nodeMap.get(edge.start_node_id);
      const v = nodeMap.get(edge.end_node_id);
      if (!u || !v) continue;

      const segKey = [u.id, v.id].sort().join("<->");
      if (processedSegments.has(segKey)) continue;
      processedSegments.add(segKey);

      const p1 = simToWorldCoordinates(u.x, u.y, 0.02);
      const p2 = simToWorldCoordinates(v.x, v.y, 0.02);

      const dx = p2.x - p1.x;
      const dz = p2.z - p1.z;
      const len = Math.sqrt(dx * dx + dz * dz);
      const midX = (p1.x + p2.x) / 2;
      const midZ = (p1.z + p2.z) / 2;
      const angle = Math.atan2(dx, dz);

      const roadGeo = new THREE.PlaneGeometry(8, len);
      const roadMesh = new THREE.Mesh(roadGeo, roadMat);
      roadMesh.position.set(midX, 0.02, midZ);
      roadMesh.rotation.x = -Math.PI / 2;
      roadMesh.rotation.z = angle;
      roadGroup.add(roadMesh);

      // Centerline
      const lineGeo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(p1.x, 0.03, p1.z),
        new THREE.Vector3(p2.x, 0.03, p2.z),
      ]);
      const lineMesh = new THREE.Line(lineGeo, lineMat);
      roadGroup.add(lineMesh);
    }

    // Signals from scenario if defined
    if (scenario?.signals) {
      for (const sig of scenario.signals) {
        const node = nodeMap.get(sig.node_id);
        if (!node) continue;
        const pos = simToWorldCoordinates(node.x, node.y, 0);

        const poleGeo = new THREE.CylinderGeometry(0.3, 0.3, 8, 8);
        const poleMat = new THREE.MeshLambertMaterial({ color: 0x334155 });
        const pole = new THREE.Mesh(poleGeo, poleMat);
        pole.position.set(pos.x + 5, 4, pos.z + 5);
        roadGroup.add(pole);
      }
    }

    // Crosswalks from scenario if defined
    if (scenario?.crosswalks) {
      const cwMat = new THREE.MeshBasicMaterial({ color: 0xe2e8f0 });
      for (const cw of scenario.crosswalks) {
        const p1 = simToWorldCoordinates(cw.entry_point[0], cw.entry_point[1], 0.04);
        const p2 = simToWorldCoordinates(cw.exit_point[0], cw.exit_point[1], 0.04);

        const dx = p2.x - p1.x;
        const dz = p2.z - p1.z;
        const len = Math.sqrt(dx * dx + dz * dz);
        const midX = (p1.x + p2.x) / 2;
        const midZ = (p1.z + p2.z) / 2;
        const angle = Math.atan2(dx, dz);

        const cwGeo = new THREE.PlaneGeometry(cw.width_m || 3.0, Math.max(len, 2));
        const cwMesh = new THREE.Mesh(cwGeo, cwMat);
        cwMesh.position.set(midX, 0.04, midZ);
        cwMesh.rotation.x = -Math.PI / 2;
        cwMesh.rotation.z = angle;
        roadGroup.add(cwMesh);
      }
    }
  }, [activeGeometry, scenario]);

  // 6. Update Vehicle Meshes
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentMeshes = vehicleMeshesRef.current;
    const activeVehicleIds = new Set<string>();

    for (const [vId, vState] of vehicles.entries()) {
      activeVehicleIds.add(vId);
      const isSelected = selectedEntityId === vId;
      const isEmergency =
        vState.is_emergency ||
        vState.vehicle_type === "emergency" ||
        vId.toLowerCase().startsWith("amb_") ||
        vId.toLowerCase().startsWith("emerg_");

      let vGroup = currentMeshes.get(vId);
      if (!vGroup) {
        vGroup = new THREE.Group();

        // Chassis body
        const bodyGeo = new THREE.BoxGeometry(2.4, 1.0, 4.6);
        const bodyMat = new THREE.MeshLambertMaterial({
          color: isEmergency ? 0xef4444 : 0x3b82f6,
        });
        const bodyMesh = new THREE.Mesh(bodyGeo, bodyMat);
        bodyMesh.position.y = 0.5;
        vGroup.add(bodyMesh);

        // Roof cabin
        const cabinGeo = new THREE.BoxGeometry(2.0, 0.8, 2.6);
        const cabinMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
        const cabinMesh = new THREE.Mesh(cabinGeo, cabinMat);
        cabinMesh.position.set(0, 1.4, -0.2);
        vGroup.add(cabinMesh);

        // Emergency beacon
        if (isEmergency) {
          const beaconGeo = new THREE.SphereGeometry(0.3, 8, 8);
          const beaconMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
          const beaconMesh = new THREE.Mesh(beaconGeo, beaconMat);
          beaconMesh.position.set(0, 1.9, 0);
          vGroup.add(beaconMesh);
        }

        // Headlights indicator
        const lightGeo = new THREE.BoxGeometry(2.0, 0.2, 0.1);
        const lightMat = new THREE.MeshBasicMaterial({ color: 0xfef08a });
        const lightMesh = new THREE.Mesh(lightGeo, lightMat);
        lightMesh.position.set(0, 0.5, 2.31);
        vGroup.add(lightMesh);

        scene.add(vGroup);
        currentMeshes.set(vId, vGroup);
      }

      // Update position & heading
      const worldPos = simToWorldCoordinates(vState.position.x, vState.position.y, 0.5);
      vGroup.position.set(worldPos.x, worldPos.y, worldPos.z);
      // In Three.js, rotation.y rotates around vertical axis
      vGroup.rotation.y = vState.heading_rad;

      // Selection indicator scale
      vGroup.scale.setScalar(isSelected ? 1.25 : 1.0);
    }

    // Remove deleted vehicles
    for (const [id, mesh] of currentMeshes.entries()) {
      if (!activeVehicleIds.has(id)) {
        scene.remove(mesh);
        currentMeshes.delete(id);
      }
    }
  }, [vehicles, selectedEntityId]);

  // 7. Update Pedestrian Meshes
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentMeshes = pedestrianMeshesRef.current;
    const activePedIds = new Set<string>();

    for (const [pId, pState] of pedestrians.entries()) {
      activePedIds.add(pId);
      const isSelected = selectedEntityId === pId;

      let pGroup = currentMeshes.get(pId);
      if (!pGroup) {
        pGroup = new THREE.Group();

        // Pedestrian body (capsule/cylinder)
        const bodyGeo = new THREE.CylinderGeometry(0.4, 0.4, 1.6, 8);
        const bodyMat = new THREE.MeshLambertMaterial({ color: 0x06b6d4 });
        const bodyMesh = new THREE.Mesh(bodyGeo, bodyMat);
        bodyMesh.position.y = 0.8;
        pGroup.add(bodyMesh);

        // Head
        const headGeo = new THREE.SphereGeometry(0.3, 8, 8);
        const headMat = new THREE.MeshLambertMaterial({ color: 0xfed7aa });
        const headMesh = new THREE.Mesh(headGeo, headMat);
        headMesh.position.y = 1.8;
        pGroup.add(headMesh);

        scene.add(pGroup);
        currentMeshes.set(pId, pGroup);
      }

      const worldPos = simToWorldCoordinates(pState.position.x, pState.position.y, 0);
      pGroup.position.set(worldPos.x, 0, worldPos.z);
      pGroup.scale.setScalar(isSelected ? 1.3 : 1.0);
    }

    for (const [id, mesh] of currentMeshes.entries()) {
      if (!activePedIds.has(id)) {
        scene.remove(mesh);
        currentMeshes.delete(id);
      }
    }
  }, [pedestrians, selectedEntityId]);

  // 8. Update Traffic Signals
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentMeshes = signalMeshesRef.current;
    for (const [sigId, sigState] of signals.entries()) {
      const sigMesh = currentMeshes.get(sigId);
      const color =
        sigState.state === "GREEN"
          ? 0x10b981
          : sigState.state === "YELLOW"
          ? 0xf59e0b
          : 0xef4444;

      if (!sigMesh) {
        const headGeo = new THREE.SphereGeometry(1.0, 12, 12);
        const headMat = new THREE.MeshBasicMaterial({ color });
        const mesh = new THREE.Mesh(headGeo, headMat);

        // Position near node
        const node = activeGeometry.nodes.find((n) => n.id === sigState.node_id);
        if (node) {
          const pos = simToWorldCoordinates(node.x, node.y, 8.5);
          mesh.position.set(pos.x + 5, 8.5, pos.z + 5);
          scene.add(mesh);
          currentMeshes.set(sigId, mesh);
        }
      } else {
        sigMesh.material.color.setHex(color);
      }

    }
  }, [signals, activeGeometry]);

  // 9. Update Active Route Line
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    if (routeLineRef.current) {
      scene.remove(routeLineRef.current);
      routeLineRef.current = null;
    }

    if (!activeRoute || activeRoute.length < 2) return;

    const nodeMap = new Map<string, RoadNodeGeometry>();
    for (const n of activeGeometry.nodes) {
      nodeMap.set(n.id, n);
    }

    const points: THREE.Vector3[] = [];
    for (const nodeId of activeRoute) {
      const node = nodeMap.get(nodeId);
      if (node) {
        const p = simToWorldCoordinates(node.x, node.y, 0.4);
        points.push(new THREE.Vector3(p.x, p.y, p.z));
      }
    }

    if (points.length >= 2) {
      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({
        color: 0x10b981,
        linewidth: 4,
      });
      const line = new THREE.Line(lineGeo, lineMat);
      scene.add(line);
      routeLineRef.current = line;
    }
  }, [activeRoute, activeGeometry]);

  // 10. Mouse Drag & Orbit Controls
  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    dragButtonRef.current = e.button;
    prevMousePosRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - prevMousePosRef.current.x;
    const dy = e.clientY - prevMousePosRef.current.y;
    prevMousePosRef.current = { x: e.clientX, y: e.clientY };

    if (dragButtonRef.current === 0) {
      // Orbit (Left click)
      cameraAngleRef.current.theta -= dx * 0.008;
      cameraAngleRef.current.phi = Math.max(
        0.1,
        Math.min(Math.PI / 2 - 0.05, cameraAngleRef.current.phi - dy * 0.008)
      );
    } else if (dragButtonRef.current === 2 || dragButtonRef.current === 1) {
      // Pan (Right or Middle click)
      const { theta } = cameraAngleRef.current;
      const panSpeed = cameraDistanceRef.current * 0.0015;
      cameraTargetRef.current.x -= (Math.cos(theta) * dx - Math.sin(theta) * dy) * panSpeed;
      cameraTargetRef.current.z -= (Math.sin(theta) * dx + Math.cos(theta) * dy) * panSpeed;
    }

    updateCameraPosition();
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    cameraDistanceRef.current = Math.max(
      20,
      Math.min(1000, cameraDistanceRef.current * zoomFactor)
    );
    updateCameraPosition();
  };

  // 11. Click to select vehicle/pedestrian
  const handleClick = (e: React.MouseEvent) => {
    if (!onSelectEntity) return;
    const container = containerRef.current;
    const camera = cameraRef.current;
    const scene = sceneRef.current;
    if (!container || !camera || !scene) return;

    const rect = container.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);

    // Test vehicles
    for (const [vId, vGroup] of vehicleMeshesRef.current.entries()) {
      const intersects = raycaster.intersectObjects(vGroup.children, true);
      if (intersects.length > 0) {
        onSelectEntity(vId, "vehicle");
        return;
      }
    }

    // Test pedestrians
    for (const [pId, pGroup] of pedestrianMeshesRef.current.entries()) {
      const intersects = raycaster.intersectObjects(pGroup.children, true);
      if (intersects.length > 0) {
        onSelectEntity(pId, "pedestrian");
        return;
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className="simulation-viewport-container"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onClick={handleClick}
      onContextMenu={(e) => e.preventDefault()}
      tabIndex={0}
      aria-label="3D Simulation Viewport"
      role="region"
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        minHeight: "450px",
        overflow: "hidden",
        backgroundColor: "#0a0f1d",
        cursor: "grab",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: "block", width: "100%", height: "100%" }}
      />

      {/* Loading Overlay */}
      {isLoading && (
        <div
          className="viewport-overlay-loading"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(10, 15, 29, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#38bdf8",
            fontSize: "1rem",
            fontWeight: 500,
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 10,
          }}
        >
          Loading 3D Simulation Environment...
        </div>
      )}

      {/* Floating HUD: Controls & Legend */}
      <div
        className="viewport-hud-top-right"
        style={{
          position: "absolute",
          top: "16px",
          right: "16px",
          display: "flex",
          gap: "8px",
          zIndex: 5,
        }}
      >
        <button
          type="button"
          onClick={handleResetCamera}
          className="hud-button"
          title="Reset Camera View"
          aria-label="Reset Camera View"
          style={{
            backgroundColor: "#1e293b",
            color: "#f8fafc",
            border: "1px solid #334155",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.85rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 2px 4px rgba(0,0,0,0.4)",
          }}
        >
          Reset View
        </button>
      </div>

      {/* Floating HUD: Scene Legend */}
      <div
        className="viewport-hud-legend"
        style={{
          position: "absolute",
          bottom: "16px",
          left: "16px",
          backgroundColor: "rgba(15, 23, 42, 0.85)",
          backdropFilter: "blur(4px)",
          border: "1px solid #334155",
          borderRadius: "6px",
          padding: "8px 14px",
          fontSize: "0.75rem",
          color: "#94a3b8",
          display: "flex",
          gap: "16px",
          alignItems: "center",
          fontFamily: "Space Grotesk, sans-serif",
          zIndex: 5,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#3b82f6", borderRadius: "2px" }} />
          <span>Vehicle</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#ef4444", borderRadius: "2px" }} />
          <span>Emergency</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#06b6d4", borderRadius: "50%" }} />
          <span>Pedestrian</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#10b981", borderRadius: "50%" }} />
          <span>Signal</span>
        </div>
      </div>
    </div>
  );
};
