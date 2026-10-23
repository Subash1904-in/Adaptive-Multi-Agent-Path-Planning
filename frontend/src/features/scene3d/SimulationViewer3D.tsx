/**
 * Interactive 3D Simulation Viewport for AMAPP.
 * Built with Three.js rendering realistic road networks, multi-lane markings,
 * clean intersection pads, zebra-style crosswalks, curbs/sidewalks,
 * deterministic procedural urban buildings, day/night lighting modes, and
 * perspective/orthographic camera projection modes.
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as THREE from "three";
import type {
  CameraProjectionMode,
  LightingMode,
  RoadNodeGeometry,
} from "../../types/graph";
import type {
  PedestrianState,
  ScenarioDefinition,
  TrafficSignalState,
  VehicleState,
} from "../../types/simulation";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import {
  computeNetworkBounds,
  computeRoadEdgeWidth,
  generateCurbsAndSidewalks,
  generateInferredCrosswalks,
  generateMultiLaneMarkings,
  generateProceduralBuildings,
  generateUrbanProps,
  generateZebraStripes,
  getUnifiedMetropolitanRoadNetwork,
  simToWorldCoordinates,
} from "./geometry";
import {
  createPedestrianModel,
  createVehicleModel,
  determineVehicleModelType,
  disposeModelAssets,
  updatePedestrianVisuals,
  updateVehicleVisuals,
} from "./models";
import {
  EntityInterpolationBuffer,
  simHeadingToWorldRotationY,
} from "./interpolation";
import { V2VOverlayManager } from "./v2vOverlay";
import type { V2VLink, V2VOverlayOptions, V2VSubsystemSnapshot } from "../../types/v2v";
import { DEFAULT_V2V_OVERLAY_OPTIONS } from "../../types/v2v";
import { RouteOverlayManager } from "./routeOverlay";
import type { RouteOverlayOptions, RouteSubsystemSnapshot } from "../../types/routing";
import { DEFAULT_ROUTE_OVERLAY_OPTIONS } from "../../types/routing";
import { IncidentOverlayManager, DEFAULT_INCIDENT_OVERLAY_OPTIONS } from "./incidentOverlay";
import type { IncidentOverlayOptions } from "./incidentOverlay";
import type { IncidentRecord, IncidentSubsystemSnapshot } from "../../types/incidents";
import type { PlaybackSpeed } from "../../types/playback";

export interface SimulationViewer3DProps {
  scenario: ScenarioDefinition | null;
  vehicles: Map<string, VehicleState>;
  pedestrians: Map<string, PedestrianState>;
  signals: Map<string, TrafficSignalState>;
  activeRoute?: string[];
  selectedEntityId?: string | null;
  onSelectEntity?: (entityId: string, entityType: "vehicle" | "pedestrian") => void;
  isLoading?: boolean;
  isReviewing?: boolean;
  reviewTick?: number | null;
  onReturnToLive?: () => void;
  communicationSnapshot?: V2VSubsystemSnapshot | null;
  routeSnapshot?: RouteSubsystemSnapshot | null;
  selectedCandidateId?: string | null;
  onSelectCandidate?: (candidateId: string | null) => void;
  playbackSpeed?: PlaybackSpeed;
  isPaused?: boolean;
  incidents?: IncidentRecord[] | null;
  incidentSnapshot?: IncidentSubsystemSnapshot | null;
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
  isReviewing = false,
  reviewTick = null,
  onReturnToLive,
  communicationSnapshot = null,
  routeSnapshot = null,
  selectedCandidateId = null,
  onSelectCandidate: _onSelectCandidate,
  playbackSpeed = 1,
  isPaused = false,
  incidents = null,
  incidentSnapshot = null,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Viewport Settings State
  const [lightingMode, setLightingMode] = useState<LightingMode>("day");
  const [projectionMode, setProjectionMode] = useState<CameraProjectionMode>("perspective");
  const [showBuildings, setShowBuildings] = useState<boolean>(true);
  const [webglError, setWebglError] = useState<string | null>(null);

  // V2V Overlay Settings & Legend State
  const [v2vOptions, setV2vOptions] = useState<V2VOverlayOptions>(DEFAULT_V2V_OVERLAY_OPTIONS);
  const [showV2VLegend, setShowV2VLegend] = useState<boolean>(false);

  // Route Overlay Settings & Legend State
  const [routeOptions, setRouteOptions] = useState<RouteOverlayOptions>(DEFAULT_ROUTE_OVERLAY_OPTIONS);
  const [showRouteLegend, setShowRouteLegend] = useState<boolean>(false);
  const incidentOptions: IncidentOverlayOptions = DEFAULT_INCIDENT_OVERLAY_OPTIONS;

  // Three.js internal references
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const perspectiveCameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const orthographicCameraRef = useRef<THREE.OrthographicCamera | null>(null);
  const animFrameIdRef = useRef<number | null>(null);

  // V2V Overlay Reference
  const v2vOverlayRef = useRef<V2VOverlayManager | null>(null);
  const communicationSnapshotRef = useRef<V2VSubsystemSnapshot | null | undefined>(communicationSnapshot);
  const playbackSpeedRef = useRef<PlaybackSpeed>(playbackSpeed);
  const isPausedRef = useRef<boolean>(isPaused);
  const v2vOptionsRef = useRef<V2VOverlayOptions>(v2vOptions);
  const vehiclesRef = useRef<Map<string, VehicleState>>(vehicles);

  // Route Overlay Reference
  const routeOverlayRef = useRef<RouteOverlayManager | null>(null);
  const routeSnapshotRef = useRef<RouteSubsystemSnapshot | null | undefined>(routeSnapshot);
  const routeOptionsRef = useRef<RouteOverlayOptions>(routeOptions);
  const selectedCandidateIdRef = useRef<string | null | undefined>(selectedCandidateId);

  useEffect(() => {
    vehiclesRef.current = vehicles;
  }, [vehicles]);

  useEffect(() => {
    v2vOptionsRef.current = v2vOptions;
  }, [v2vOptions]);

  useEffect(() => {
    communicationSnapshotRef.current = communicationSnapshot;
  }, [communicationSnapshot]);

  useEffect(() => {
    playbackSpeedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    routeOptionsRef.current = routeOptions;
    routeOverlayRef.current?.setOptions(routeOptions);
  }, [routeOptions]);

  useEffect(() => {
    routeSnapshotRef.current = routeSnapshot;
    routeOverlayRef.current?.update(
      routeSnapshot,
      selectedEntityId,
      selectedCandidateId
    );
  }, [routeSnapshot, selectedEntityId, selectedCandidateId]);

  useEffect(() => {
    selectedCandidateIdRef.current = selectedCandidateId;
  }, [selectedCandidateId]);

  // Incident Overlay Reference
  const incidentOverlayRef = useRef<IncidentOverlayManager | null>(null);
  const incidentOptionsRef = useRef<IncidentOverlayOptions>(incidentOptions);

  useEffect(() => {
    incidentOptionsRef.current = incidentOptions;
    incidentOverlayRef.current?.setOptions(incidentOptions);
  }, [incidentOptions]);

  // Lighting references
  const ambientLightRef = useRef<THREE.AmbientLight | null>(null);
  const hemiLightRef = useRef<THREE.HemisphereLight | null>(null);
  const dirLightRef = useRef<THREE.DirectionalLight | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  // Rendering object groups
  const roadGroupRef = useRef<THREE.Group>(new THREE.Group());
  const buildingsGroupRef = useRef<THREE.Group>(new THREE.Group());
  const urbanPropsGroupRef = useRef<THREE.Group>(new THREE.Group());
  const vehicleMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const pedestrianMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const signalMeshesRef = useRef<Map<string, THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>>>(new Map());
  const routeLineRef = useRef<THREE.Line | null>(null);

  // Temporal interpolation and presentation animation references
  const interpolationBufferRef = useRef<EntityInterpolationBuffer>(
    new EntityInterpolationBuffer({
      maxSamples: 10,
      defaultTimeStepS: 0.1,
      staleThresholdS: 5.0,
      maxExtrapolationS: 0.15,
    })
  );
  const clockRef = useRef<THREE.Clock>(new THREE.Clock());
  const latestSimTimeRef = useRef<number>(0);
  const simTimeRef = useRef<number>(0);
  const selectedEntityIdRef = useRef<string | null | undefined>(selectedEntityId);

  useEffect(() => {
    selectedEntityIdRef.current = selectedEntityId;
  }, [selectedEntityId]);

  // Material Cache for resource reuse
  const materialsRef = useRef<{
    roadMat?: THREE.MeshStandardMaterial;
    junctionMat?: THREE.MeshStandardMaterial;
    sidewalkMat?: THREE.MeshStandardMaterial;
    curbMat?: THREE.MeshStandardMaterial;
    markingWhiteMat?: THREE.MeshBasicMaterial;
    markingYellowMat?: THREE.MeshBasicMaterial;
    crosswalkMat?: THREE.MeshBasicMaterial;
  }>({});

  // Mouse interaction state for camera orbit / pan / zoom
  const isDraggingRef = useRef(false);
  const dragButtonRef = useRef<number>(0);
  const prevMousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const cameraTargetRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const cameraDistanceRef = useRef<number>(200);
  const cameraAngleRef = useRef<{ theta: number; phi: number }>({
    theta: Math.PI / 4,
    phi: Math.PI / 3.5,
  });

  // Authoritative metropolitan road network (Arterials, Diagonals, Ring Road, District Streets)
  const metroGeometry = useMemo(() => {
    return getUnifiedMetropolitanRoadNetwork(scenario);
  }, [scenario]);

  useEffect(() => {
    const list = incidents || incidentSnapshot?.active_incidents || [];
    incidentOverlayRef.current?.update(list, metroGeometry);
  }, [incidents, incidentSnapshot, metroGeometry]);

  // 2. Camera position updater helper (synchronizes both Perspective and Orthographic cameras)
  const updateCameraPosition = useCallback(() => {
    const { theta, phi } = cameraAngleRef.current;
    const r = cameraDistanceRef.current;
    const target = cameraTargetRef.current;

    const posX = target.x + r * Math.sin(phi) * Math.sin(theta);
    const posY = target.y + r * Math.cos(phi);
    const posZ = target.z + r * Math.sin(phi) * Math.cos(theta);

    if (perspectiveCameraRef.current) {
      perspectiveCameraRef.current.position.set(posX, posY, posZ);
      perspectiveCameraRef.current.lookAt(target);
    }

    if (orthographicCameraRef.current) {
      const container = containerRef.current;
      const w = container?.clientWidth || 800;
      const h = container?.clientHeight || 500;
      const aspect = w / h;
      const frustumSize = r * 0.85;

      orthographicCameraRef.current.left = (-frustumSize * aspect) / 2;
      orthographicCameraRef.current.right = (frustumSize * aspect) / 2;
      orthographicCameraRef.current.top = frustumSize / 2;
      orthographicCameraRef.current.bottom = -frustumSize / 2;
      orthographicCameraRef.current.updateProjectionMatrix();

      orthographicCameraRef.current.position.set(posX, posY, posZ);
      orthographicCameraRef.current.lookAt(target);
    }
  }, []);

  // 3. Reset Camera View
  const handleResetCamera = useCallback(() => {
    const bounds = computeNetworkBounds(metroGeometry);
    cameraTargetRef.current.set(bounds.center.x, 0, bounds.center.z);
    cameraDistanceRef.current = 420;
    cameraAngleRef.current = { theta: Math.PI / 4, phi: Math.PI / 3.4 };
    updateCameraPosition();
  }, [metroGeometry, updateCameraPosition]);

  const handleSetCameraPreset = useCallback(
    (preset: "metropolis" | "downtown" | "street") => {
      const bounds = computeNetworkBounds(metroGeometry);
      const target = bounds.center;

      if (preset === "metropolis") {
        cameraTargetRef.current.set(target.x, 0, target.z);
        cameraDistanceRef.current = 680;
        cameraAngleRef.current = { theta: Math.PI / 4, phi: Math.PI / 3.3 };
      } else if (preset === "downtown") {
        cameraTargetRef.current.set(target.x, 0, target.z);
        cameraDistanceRef.current = 310;
        cameraAngleRef.current = { theta: Math.PI / 4, phi: Math.PI / 3.45 };
      } else if (preset === "street") {
        cameraTargetRef.current.set(target.x, 0, target.z);
        cameraDistanceRef.current = 85;
        cameraAngleRef.current = { theta: Math.PI / 4.8, phi: Math.PI / 2.35 };
      }
      updateCameraPosition();
    },
    [metroGeometry, updateCameraPosition]
  );

  // 4. Initialize Three.js Scene and Renderer
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    const aspect = width / height;

    // Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Perspective Camera
    const perspCamera = new THREE.PerspectiveCamera(45, aspect, 1, 3000);
    perspectiveCameraRef.current = perspCamera;

    // Orthographic Camera
    const orthoFrustum = 200;
    const orthoCamera = new THREE.OrthographicCamera(
      (-orthoFrustum * aspect) / 2,
      (orthoFrustum * aspect) / 2,
      orthoFrustum / 2,
      -orthoFrustum / 2,
      1,
      3000
    );
    orthographicCameraRef.current = orthoCamera;

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
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.15;
      rendererRef.current = renderer;
      setWebglError(null);
    } catch (err) {
      const isTestEnv =
        (globalThis as unknown as { process?: { env?: { NODE_ENV?: string } } }).process?.env?.NODE_ENV === "test";
      if (!isTestEnv) {
        console.warn("WebGL initialization note:", err);
      }
      setWebglError("Unable to initialize WebGL context on this device/display.");
      return;
    }

    // Studio Environment Reflections
    try {
      const pmremGenerator = new THREE.PMREMGenerator(renderer);
      scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
      pmremGenerator.dispose();
    } catch {
      // Graceful fallback if PMREM not available in headless/test environments
    }

    // Shared Materials Initialization with Standard PBR (Light Architectural Theme)
    materialsRef.current = {
      roadMat: new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.85, metalness: 0.1 }),
      junctionMat: new THREE.MeshStandardMaterial({ color: 0x3e4c5e, roughness: 0.8, metalness: 0.15 }),
      sidewalkMat: new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.75, metalness: 0.1 }),
      curbMat: new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.7, metalness: 0.15 }),
      markingWhiteMat: new THREE.MeshBasicMaterial({ color: 0xffffff }),
      markingYellowMat: new THREE.MeshBasicMaterial({ color: 0xf59e0b }),
      crosswalkMat: new THREE.MeshBasicMaterial({ color: 0xffffff }),
    };

    // Daytime Architectural Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    ambientLightRef.current = ambientLight;
    scene.add(ambientLight);

    const hemiLight = new THREE.HemisphereLight(0xffffff, 0xe2e8f0, 0.75);
    hemiLightRef.current = hemiLight;
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xfffbeb, 1.25);
    dirLight.position.set(240, 480, 240);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.camera.near = 10;
    dirLight.shadow.camera.far = 1600;
    const d = 450;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    dirLight.shadow.bias = -0.0005;
    dirLight.shadow.normalBias = 0.02;
    dirLightRef.current = dirLight;
    scene.add(dirLight);

    scene.background = new THREE.Color(0xf1f5f9);
    scene.fog = new THREE.FogExp2(0xf1f5f9, 0.0006);

    // Ground Grid Helper spanning the metropolitan area
    const grid = new THREE.GridHelper(2400, 80, 0xcbd5e1, 0xe2e8f0);
    grid.position.y = -0.1;
    gridHelperRef.current = grid;
    scene.add(grid);

    // Groups
    scene.add(roadGroupRef.current);
    scene.add(buildingsGroupRef.current);
    scene.add(urbanPropsGroupRef.current);

    // V2V Communication Overlay Group
    const v2vOverlay = new V2VOverlayManager();
    v2vOverlay.setOptions(v2vOptionsRef.current);
    v2vOverlayRef.current = v2vOverlay;
    scene.add(v2vOverlay.rootGroup);

    // Route Visualization Overlay Group
    const routeOverlay = new RouteOverlayManager();
    routeOverlay.setOptions(routeOptionsRef.current);
    routeOverlayRef.current = routeOverlay;
    scene.add(routeOverlay.rootGroup);

    // Incident Visualization Overlay Group
    const incidentOverlay = new IncidentOverlayManager();
    incidentOverlay.setOptions(incidentOptionsRef.current);
    incidentOverlayRef.current = incidentOverlay;
    scene.add(incidentOverlay.rootGroup);

    // Initial camera placement
    handleResetCamera();

    // Render loop with temporal interpolation and presentation animations
    const clock = clockRef.current;
    clock.start();

    const animate = () => {
      animFrameIdRef.current = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // Smoothly advance local presentation time towards latest telemetry timestamp
      const targetSimTime = latestSimTimeRef.current;
      if (simTimeRef.current < targetSimTime) {
        simTimeRef.current = Math.min(targetSimTime, simTimeRef.current + delta);
      } else {
        simTimeRef.current = targetSimTime;
      }
      const renderTime = simTimeRef.current;

      const prefersReducedMotion =
        typeof window !== "undefined" &&
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      // 1. Update vehicle mesh transforms from interpolation buffer
      for (const [vId, vGroup] of vehicleMeshesRef.current.entries()) {
        const interp = interpolationBufferRef.current.getInterpolatedState(vId, renderTime, 0.5);
        if (interp) {
          vGroup.position.set(interp.world_position.x, interp.world_position.y, interp.world_position.z);
          vGroup.rotation.y = interp.rotation_y;
          const isSelected = selectedEntityIdRef.current === vId;
          updateVehicleVisuals(
            vGroup,
            { isEmergency: interp.is_emergency, isSelected, speed_mps: interp.speed_mps },
            elapsed,
            prefersReducedMotion
          );
        }
      }

      // 2. Update pedestrian mesh transforms from interpolation buffer
      for (const [pId, pGroup] of pedestrianMeshesRef.current.entries()) {
        const interp = interpolationBufferRef.current.getInterpolatedState(pId, renderTime, 0.0);
        if (interp) {
          pGroup.position.set(interp.world_position.x, 0, interp.world_position.z);
          pGroup.rotation.y = interp.rotation_y;
          const isSelected = selectedEntityIdRef.current === pId;
          updatePedestrianVisuals(
            pGroup,
            { speed_mps: interp.speed_mps, lifecycle_state: interp.lifecycle_state, isSelected },
            elapsed,
            prefersReducedMotion
          );
        }
      }

      // 3. Update V2V communication overlay
      if (v2vOverlayRef.current) {
        const commSnap = communicationSnapshotRef.current;
        const getVehicleWorldPos = (id: string): THREE.Vector3 | null => {
          const mesh = vehicleMeshesRef.current.get(id);
          if (mesh) return mesh.position;
          const interp = interpolationBufferRef.current.getInterpolatedState(id, renderTime, 0.5);
          if (interp) return new THREE.Vector3(interp.world_position.x, interp.world_position.y, interp.world_position.z);
          const v = vehiclesRef.current.get(id);
          if (v) {
            const wp = simToWorldCoordinates(v.position.x, v.position.y, 0.5);
            return new THREE.Vector3(wp.x, wp.y, wp.z);
          }
          return null;
        };

        v2vOverlayRef.current.updateLinks(commSnap?.links ?? [], getVehicleWorldPos);
        v2vOverlayRef.current.updateRangeRing(
          selectedEntityIdRef.current,
          commSnap?.rangeM ?? null,
          getVehicleWorldPos
        );
        v2vOverlayRef.current.updateAnimations(
          delta,
          playbackSpeedRef.current ?? 1,
          isPausedRef.current ?? false,
          prefersReducedMotion
        );
      }

      // 4. Update Route visualization overlay animations
      if (routeOverlayRef.current) {
        routeOverlayRef.current.tick(
          delta,
          playbackSpeedRef.current ?? 1,
          isPausedRef.current ?? false
        );
      }

      // 5. Update Incident visualization overlay pulsation
      if (incidentOverlayRef.current) {
        incidentOverlayRef.current.animate(delta);
      }

      if (rendererRef.current && sceneRef.current) {
        const activeCam =
          projectionMode === "perspective"
            ? perspectiveCameraRef.current
            : orthographicCameraRef.current;
        if (activeCam) {
          rendererRef.current.render(sceneRef.current, activeCam);
        }
      }
    };
    animate();

    // Resize observer
    const handleResize = () => {
      if (!container || !rendererRef.current) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) return;
      const newAspect = w / h;

      if (perspectiveCameraRef.current) {
        perspectiveCameraRef.current.aspect = newAspect;
        perspectiveCameraRef.current.updateProjectionMatrix();
      }
      if (orthographicCameraRef.current) {
        const frustumSize = cameraDistanceRef.current * 0.85;
        orthographicCameraRef.current.left = (-frustumSize * newAspect) / 2;
        orthographicCameraRef.current.right = (frustumSize * newAspect) / 2;
        orthographicCameraRef.current.top = frustumSize / 2;
        orthographicCameraRef.current.bottom = -frustumSize / 2;
        orthographicCameraRef.current.updateProjectionMatrix();
      }
      rendererRef.current.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    const vehicleMeshes = vehicleMeshesRef.current;
    const pedestrianMeshes = pedestrianMeshesRef.current;
    const interpolationBuffer = interpolationBufferRef.current;

    return () => {
      window.removeEventListener("resize", handleResize);
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
      for (const vGroup of vehicleMeshes.values()) {
        scene.remove(vGroup);
      }
      vehicleMeshes.clear();
      for (const pGroup of pedestrianMeshes.values()) {
        scene.remove(pGroup);
      }
      pedestrianMeshes.clear();
      interpolationBuffer.clear();
      disposeModelAssets();

      if (v2vOverlayRef.current) {
        scene.remove(v2vOverlayRef.current.rootGroup);
        v2vOverlayRef.current.dispose();
        v2vOverlayRef.current = null;
      }

      if (routeOverlayRef.current) {
        scene.remove(routeOverlayRef.current.rootGroup);
        routeOverlayRef.current.dispose();
        routeOverlayRef.current = null;
      }

      if (incidentOverlayRef.current) {
        scene.remove(incidentOverlayRef.current.rootGroup);
        incidentOverlayRef.current.dispose();
        incidentOverlayRef.current = null;
      }

      if (rendererRef.current) {
        rendererRef.current.dispose();
        rendererRef.current = null;
      }
    };
  }, [handleResetCamera, projectionMode]);

  // 5. Update Lighting & Day/Night Mode colors
  useEffect(() => {
    const scene = sceneRef.current;
    const amb = ambientLightRef.current;
    const dir = dirLightRef.current;
    const hemi = hemiLightRef.current;
    const mats = materialsRef.current;
    if (!scene || !amb || !dir || !mats) return;

    // Light mode architectural atmospheric setup
    scene.background = new THREE.Color(lightingMode === "day" ? 0xf1f5f9 : 0xf8fafc);
    if (scene.fog) (scene.fog as THREE.FogExp2).color.setHex(lightingMode === "day" ? 0xf1f5f9 : 0xf8fafc);
    amb.color.setHex(0xffffff);
    amb.intensity = 0.85;
    if (hemi) {
      hemi.color.setHex(0xffffff);
      hemi.groundColor.setHex(0xe2e8f0);
      hemi.intensity = 0.75;
    }
    dir.color.setHex(0xfffbeb);
    dir.intensity = 1.25;
    dir.position.set(240, 480, 240);

    mats.roadMat?.color.setHex(0x334155);
    mats.junctionMat?.color.setHex(0x3e4c5e);
    mats.sidewalkMat?.color.setHex(0xe2e8f0);
    mats.curbMat?.color.setHex(0xcbd5e1);
  }, [lightingMode]);

  // 6. Update Building & Environmental Props Visibility
  useEffect(() => {
    buildingsGroupRef.current.visible = showBuildings;
    urbanPropsGroupRef.current.visible = showBuildings;
  }, [showBuildings]);

  // 7. Rebuild Road Network Meshes, Markings, Crosswalks, Procedural Skyscrapers and Urban Props
  useEffect(() => {
    const roadGroup = roadGroupRef.current;
    const buildingsGroup = buildingsGroupRef.current;
    const urbanGroup = urbanPropsGroupRef.current;
    const mats = materialsRef.current;

    // Helper for recursive disposal of meshes, geometries, and nested groups
    const disposeGroup = (group: THREE.Group) => {
      while (group.children.length > 0) {
        const child = group.children.pop();
        if (child) {
          if (child instanceof THREE.InstancedMesh) {
            child.geometry?.dispose();
            if (Array.isArray(child.material)) {
              child.material.forEach((m) => m.dispose());
            } else {
              child.material?.dispose();
            }
          } else if (child instanceof THREE.Mesh) {
            child.geometry?.dispose();
          } else if (child instanceof THREE.Group) {
            disposeGroup(child);
          }
          group.remove(child);
        }
      }
    };

    disposeGroup(roadGroup);
    disposeGroup(buildingsGroup);
    disposeGroup(urbanGroup);

    if (metroGeometry.nodes.length === 0) return;

    const nodeMap = new Map<string, RoadNodeGeometry>();
    for (const node of metroGeometry.nodes) {
      nodeMap.set(node.id, node);
    }

    // Determine max connected road width per node to size junction pads correctly
    const nodeMaxWidth = new Map<string, number>();
    for (const edge of metroGeometry.edges) {
      const width = computeRoadEdgeWidth(edge);
      const curU = nodeMaxWidth.get(edge.start_node_id) || 8.0;
      nodeMaxWidth.set(edge.start_node_id, Math.max(curU, width));
      const curV = nodeMaxWidth.get(edge.end_node_id) || 8.0;
      nodeMaxWidth.set(edge.end_node_id, Math.max(curV, width));
    }

    // A. Node junction pads (smooth disc/cylinder connecting adjoining roads without holes)
    for (const node of metroGeometry.nodes) {
      const nodePos = simToWorldCoordinates(node.x, node.y, 0.022);
      const maxWidth = nodeMaxWidth.get(node.id) || 8.0;
      const padRadius = Math.max(5.5, maxWidth / 2 + 0.5);

      const junctionGeo = new THREE.CylinderGeometry(padRadius, padRadius, 0.04, 24);
      const junctionMesh = new THREE.Mesh(junctionGeo, mats.junctionMat);
      junctionMesh.position.set(nodePos.x, nodePos.y, nodePos.z);
      junctionMesh.receiveShadow = true;
      roadGroup.add(junctionMesh);
    }

    // B. Road Edges, Surfaces, Multi-Lane Markings, Curbs and Sidewalks
    const processedSegments = new Set<string>();

    for (const edge of metroGeometry.edges) {
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
      const len = Math.hypot(dx, dz);
      if (len < 0.5) continue;

      const midX = (p1.x + p2.x) / 2;
      const midZ = (p1.z + p2.z) / 2;
      const angle = Math.atan2(dx, dz);

      const roadWidth = computeRoadEdgeWidth(edge);

      // B1. Drivable Asphalt Surface
      const roadGeo = new THREE.PlaneGeometry(roadWidth, len);
      const roadMesh = new THREE.Mesh(roadGeo, mats.roadMat);
      roadMesh.position.set(midX, 0.02, midZ);
      roadMesh.rotation.x = -Math.PI / 2;
      roadMesh.rotation.z = angle;
      roadMesh.receiveShadow = true;
      roadGroup.add(roadMesh);

      // B2. Multi-lane Markings (Edge borders, dashed dividers, solid centerlines)
      const isOneWay = Boolean(edge.attributes?.one_way);
      const markings = generateMultiLaneMarkings(edge, u, v, !isOneWay);

      for (const m of markings) {
        const mx = (m.start.x + m.end.x) / 2;
        const mz = (m.start.z + m.end.z) / 2;
        const mlen = Math.hypot(m.end.x - m.start.x, m.end.z - m.start.z);

        const markMat =
          m.colorHex === 0xfacc15 ? mats.markingYellowMat : mats.markingWhiteMat;

        if (m.type === "dashed") {
          // Render dashed strip via multiple small segments
          const dashLen = 3.0;
          const gapLen = 3.0;
          const pitch = dashLen + gapLen;
          const numDashes = Math.max(1, Math.floor(mlen / pitch));
          const udx = (m.end.x - m.start.x) / mlen;
          const udz = (m.end.z - m.start.z) / mlen;

          for (let d = 0; d < numDashes; d++) {
            const centerDist = (d + 0.5) * pitch;
            if (centerDist > mlen - dashLen * 0.5) break;

            const dashGeo = new THREE.PlaneGeometry(m.width, dashLen);
            const dashMesh = new THREE.Mesh(dashGeo, markMat);
            dashMesh.position.set(
              m.start.x + udx * centerDist,
              0.035,
              m.start.z + udz * centerDist
            );
            dashMesh.rotation.x = -Math.PI / 2;
            dashMesh.rotation.z = angle;
            roadGroup.add(dashMesh);
          }
        } else {
          // Solid line (centerline or outer border)
          const lineGeo = new THREE.PlaneGeometry(m.width, mlen);
          const lineMesh = new THREE.Mesh(lineGeo, markMat);
          lineMesh.position.set(mx, 0.035, mz);
          lineMesh.rotation.x = -Math.PI / 2;
          lineMesh.rotation.z = angle;
          roadGroup.add(lineMesh);
        }
      }

      // B3. Curbs and Sidewalks
      const sidewalks = generateCurbsAndSidewalks(edge, u, v, 2.2, 0.12, 5.5);
      for (const sw of sidewalks) {
        const swLen = Math.hypot(sw.end.x - sw.start.x, sw.end.z - sw.start.z);
        if (swLen <= 1.0) continue;

        const swMidX = (sw.start.x + sw.end.x) / 2;
        const swMidZ = (sw.start.z + sw.end.z) / 2;

        const swGeo = new THREE.BoxGeometry(sw.width, sw.curbHeight, swLen);
        const swMesh = new THREE.Mesh(swGeo, mats.sidewalkMat);
        swMesh.position.set(swMidX, 0.06, swMidZ);
        swMesh.rotation.y = angle;
        swMesh.castShadow = true;
        swMesh.receiveShadow = true;
        roadGroup.add(swMesh);
      }
    }

    // B4. Central Park Landmark Features (Lush Green Lawn, Reflecting Pool & Promenade)
    const parkBounds = computeNetworkBounds(metroGeometry);
    const parkMinX = parkBounds.center.x - 110;
    const parkMaxX = parkBounds.center.x - 30;
    const parkMinZ = parkBounds.center.z + 30;
    const parkMaxZ = parkBounds.center.z + 120;
    const parkCenterX = (parkMinX + parkMaxX) / 2;
    const parkCenterZ = (parkMinZ + parkMaxZ) / 2;
    const parkWidth = parkMaxX - parkMinX;
    const parkDepth = parkMaxZ - parkMinZ;

    // 1. Lush Green Park Lawn
    const lawnGeo = new THREE.BoxGeometry(parkWidth, 0.05, parkDepth);
    const lawnMat = new THREE.MeshStandardMaterial({
      color: 0x1f4728,
      roughness: 0.9,
      metalness: 0.05,
    });
    const lawnMesh = new THREE.Mesh(lawnGeo, lawnMat);
    lawnMesh.position.set(parkCenterX, 0.024, parkCenterZ);
    lawnMesh.receiveShadow = true;
    roadGroup.add(lawnMesh);

    // 2. Central Reflecting Pool / Fountain Monument
    const poolGeo = new THREE.CylinderGeometry(14, 14, 0.32, 32);
    const poolMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      roughness: 0.1,
      metalness: 0.85,
    });
    const poolMesh = new THREE.Mesh(poolGeo, poolMat);
    poolMesh.position.set(parkCenterX, 0.18, parkCenterZ);
    poolMesh.receiveShadow = true;
    roadGroup.add(poolMesh);

    // Pool Granite Coping Rim
    const rimGeo = new THREE.RingGeometry(13.5, 15.2, 32);
    const rimMat = new THREE.MeshStandardMaterial({
      color: 0x64748b,
      roughness: 0.7,
      metalness: 0.2,
    });
    const rimMesh = new THREE.Mesh(rimGeo, rimMat);
    rimMesh.position.set(parkCenterX, 0.36, parkCenterZ);
    rimMesh.rotation.x = -Math.PI / 2;
    roadGroup.add(rimMesh);

    // 3. Stone Promenade Walkways
    const walkMat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.8,
      metalness: 0.1,
    });
    const walkEWGeo = new THREE.PlaneGeometry(parkWidth, 3.5);
    const walkEWMesh = new THREE.Mesh(walkEWGeo, walkMat);
    walkEWMesh.position.set(parkCenterX, 0.052, parkCenterZ);
    walkEWMesh.rotation.x = -Math.PI / 2;
    walkEWMesh.receiveShadow = true;
    roadGroup.add(walkEWMesh);

    const walkNSGeo = new THREE.PlaneGeometry(3.5, parkDepth);
    const walkNSMesh = new THREE.Mesh(walkNSGeo, walkMat);
    walkNSMesh.position.set(parkCenterX, 0.052, parkCenterZ);
    walkNSMesh.rotation.x = -Math.PI / 2;
    walkNSMesh.receiveShadow = true;
    roadGroup.add(walkNSMesh);

    // C. Crosswalks (Explicit from scenario or Inferred at intersections)
    if (scenario?.crosswalks && scenario.crosswalks.length > 0) {
      for (const cw of scenario.crosswalks) {
        const stripes = generateZebraStripes(
          cw.entry_point as [number, number],
          cw.exit_point as [number, number],
          cw.width_m || 3.0,
          0.6,
          0.6
        );
        for (const s of stripes) {
          const sGeo = new THREE.PlaneGeometry(s.width, s.length);
          const sMesh = new THREE.Mesh(sGeo, mats.crosswalkMat);
          sMesh.position.set(s.position.x, 0.04, s.position.z);
          sMesh.rotation.x = -Math.PI / 2;
          sMesh.rotation.z = s.rotationY;
          roadGroup.add(sMesh);
        }
      }
    } else {
      // Inferred zebra crosswalks at intersection approaches
      const inferredStripes = generateInferredCrosswalks(metroGeometry, 3.2, 7.5);
      for (const s of inferredStripes) {
        const sGeo = new THREE.PlaneGeometry(s.width, s.length);
        const sMesh = new THREE.Mesh(sGeo, mats.crosswalkMat);
        sMesh.position.set(s.position.x, 0.04, s.position.z);
        sMesh.rotation.x = -Math.PI / 2;
        sMesh.rotation.z = s.rotationY;
        roadGroup.add(sMesh);
      }
    }

    // D. Traffic Signals
    if (scenario?.signals) {
      for (const sig of scenario.signals) {
        const node = nodeMap.get(sig.node_id);
        if (!node) continue;
        const pos = simToWorldCoordinates(node.x, node.y, 0);

        const poleGeo = new THREE.CylinderGeometry(0.2, 0.28, 8.5, 12);
        const poleMat = new THREE.MeshStandardMaterial({
          color: 0x334155,
          roughness: 0.4,
          metalness: 0.8,
        });
        const pole = new THREE.Mesh(poleGeo, poleMat);
        pole.position.set(pos.x + 6, 4.25, pos.z + 6);
        pole.castShadow = true;
        roadGroup.add(pole);
      }
    }

    // E. Procedural Urban Buildings (Modern downtown high-rises, podiums, setbacks, plazas)
    const buildings = generateProceduralBuildings(metroGeometry, {
      seed: scenario?.seed ?? 42,
      minHeight: 22,
      maxHeight: 110,
      minFootprint: 14,
      maxFootprint: 28,
      roadClearanceM: 4.0,
    });

    const trimMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      roughness: 0.35,
      metalness: 0.85,
    });
    const plazaMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      roughness: 0.8,
      metalness: 0.15,
    });
    const helipadMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.6,
      metalness: 0.3,
    });
    const helipadMarkingMat = new THREE.MeshBasicMaterial({ color: 0xfacc15 });
    const beaconMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });

    for (const b of buildings) {
      const bGroup = new THREE.Group();
      bGroup.position.set(b.position.x, 0, b.position.z);
      bGroup.rotation.y = b.rotationY;

      // Paved plaza courtyard base
      if (b.hasPlaza) {
        const plazaW = b.width + 6.0;
        const plazaD = b.depth + 6.0;
        const plazaGeo = new THREE.BoxGeometry(plazaW, 0.08, plazaD);
        const plazaMesh = new THREE.Mesh(plazaGeo, plazaMat);
        plazaMesh.position.set(0, 0.04, 0);
        plazaMesh.receiveShadow = true;
        bGroup.add(plazaMesh);
      }

      // High-grade glass/metallic curtain wall material for this building
      const glassMat = new THREE.MeshStandardMaterial({
        color: b.colorHex,
        roughness: 0.18,
        metalness: 0.82,
        envMapIntensity: 1.25,
      });

      const tiers =
        b.tiers && b.tiers.length > 0
          ? b.tiers
          : [
              {
                width: b.width,
                depth: b.depth,
                height: b.height,
                offsetY: b.height / 2,
                style: "glass_tower" as const,
              },
            ];

      for (const tier of tiers) {
        const tierGeo = new THREE.BoxGeometry(tier.width, tier.height, tier.depth);
        const tierMesh = new THREE.Mesh(tierGeo, glassMat);
        tierMesh.position.set(0, tier.offsetY, 0);
        tierMesh.castShadow = true;
        tierMesh.receiveShadow = true;
        bGroup.add(tierMesh);

        // Architectural cornice / floor band trim
        const bandGeo = new THREE.BoxGeometry(tier.width * 1.015, 0.35, tier.depth * 1.015);
        const bandMesh = new THREE.Mesh(bandGeo, trimMat);
        bandMesh.position.set(0, tier.offsetY + tier.height / 2, 0);
        bandMesh.castShadow = true;
        bGroup.add(bandMesh);
      }

      const topTier = tiers[tiers.length - 1];
      const topY = topTier.offsetY + topTier.height / 2;

      // Rooftop Spire with Aviation Warning Beacon
      if (b.hasSpire) {
        const spireH = 10.0;
        const spireGeo = new THREE.CylinderGeometry(0.08, 0.5, spireH, 8);
        const spireMesh = new THREE.Mesh(spireGeo, trimMat);
        spireMesh.position.set(0, topY + spireH / 2, 0);
        spireMesh.castShadow = true;
        bGroup.add(spireMesh);

        // Blinking beacon sphere at tip
        const beaconGeo = new THREE.SphereGeometry(0.3, 8, 8);
        const beaconMesh = new THREE.Mesh(beaconGeo, beaconMat);
        beaconMesh.position.set(0, topY + spireH, 0);
        bGroup.add(beaconMesh);
      }

      // Rooftop Helipad
      if (b.hasHelipad) {
        const padRadius = Math.min(topTier.width, topTier.depth) * 0.38;
        const padGeo = new THREE.CylinderGeometry(padRadius, padRadius, 0.2, 16);
        const padMesh = new THREE.Mesh(padGeo, helipadMat);
        padMesh.position.set(0, topY + 0.1, 0);
        bGroup.add(padMesh);

        // Helipad Ring Accent
        const ringGeo = new THREE.RingGeometry(padRadius * 0.75, padRadius * 0.9, 24);
        const ringMesh = new THREE.Mesh(ringGeo, helipadMarkingMat);
        ringMesh.position.set(0, topY + 0.22, 0);
        ringMesh.rotation.x = -Math.PI / 2;
        bGroup.add(ringMesh);
      }

      buildingsGroup.add(bGroup);
    }

    // F. Urban Environmental Props (Street Trees & LED Streetlamps via InstancedMesh)
    const { trees, streetlamps } = generateUrbanProps(
      metroGeometry,
      buildings,
      scenario?.seed ?? 42
    );

    // F1. Instanced Street Trees (Trunks + Dodecahedron Foliage Canopies)
    if (trees.length > 0) {
      const trunkGeo = new THREE.CylinderGeometry(0.2, 0.32, 2.2, 7);
      const trunkMat = new THREE.MeshStandardMaterial({
        color: 0x3d2817,
        roughness: 0.9,
        metalness: 0.05,
      });
      const trunkInst = new THREE.InstancedMesh(trunkGeo, trunkMat, trees.length);
      trunkInst.castShadow = true;
      trunkInst.receiveShadow = true;

      const canopyGeo = new THREE.DodecahedronGeometry(1.5, 1);
      const canopyMat = new THREE.MeshStandardMaterial({
        roughness: 0.65,
        metalness: 0.05,
        flatShading: true,
      });
      const canopyInst = new THREE.InstancedMesh(canopyGeo, canopyMat, trees.length);
      canopyInst.castShadow = true;
      canopyInst.receiveShadow = true;

      const dummy = new THREE.Object3D();
      const colorHelper = new THREE.Color();

      for (let i = 0; i < trees.length; i++) {
        const t = trees[i];
        const trunkH = t.height * 0.42;
        const canopyY = trunkH + t.canopyRadius * 0.85;

        // Trunk transform
        dummy.position.set(t.position.x, trunkH / 2, t.position.z);
        dummy.scale.set(1, trunkH / 2.2, 1);
        dummy.rotation.set(0, (i * 0.77) % (Math.PI * 2), 0);
        dummy.updateMatrix();
        trunkInst.setMatrixAt(i, dummy.matrix);

        // Canopy transform
        dummy.position.set(t.position.x, canopyY, t.position.z);
        dummy.scale.set(
          t.canopyRadius / 1.5,
          (t.height - trunkH) / 2.0,
          t.canopyRadius / 1.5
        );
        dummy.rotation.set(0, (i * 1.33) % (Math.PI * 2), 0);
        dummy.updateMatrix();
        canopyInst.setMatrixAt(i, dummy.matrix);

        // Foliage color tint variation
        colorHelper.setHex(t.canopyColorHex);
        canopyInst.setColorAt(i, colorHelper);
      }

      trunkInst.instanceMatrix.needsUpdate = true;
      canopyInst.instanceMatrix.needsUpdate = true;
      if (canopyInst.instanceColor) canopyInst.instanceColor.needsUpdate = true;

      trunkInst.computeBoundingSphere();
      canopyInst.computeBoundingSphere();

      urbanGroup.add(trunkInst);
      urbanGroup.add(canopyInst);
    }

    // F2. Instanced Modern LED Streetlamps
    if (streetlamps.length > 0) {
      const poleGeo = new THREE.CylinderGeometry(0.12, 0.16, 5.5, 8);
      const poleMat = new THREE.MeshStandardMaterial({
        color: 0x475569,
        roughness: 0.35,
        metalness: 0.8,
      });
      const poleInst = new THREE.InstancedMesh(poleGeo, poleMat, streetlamps.length);
      poleInst.castShadow = true;

      const headGeo = new THREE.BoxGeometry(0.35, 0.15, 0.7);
      const headMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        roughness: 0.4,
        metalness: 0.85,
        emissive: 0xfef08a,
        emissiveIntensity: lightingMode === "night" ? 0.9 : 0.2,
      });
      const headInst = new THREE.InstancedMesh(headGeo, headMat, streetlamps.length);

      const dummy = new THREE.Object3D();

      for (let i = 0; i < streetlamps.length; i++) {
        const l = streetlamps[i];

        // Pole
        dummy.position.set(l.position.x, 2.75, l.position.z);
        dummy.rotation.set(0, l.rotationY, 0);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        poleInst.setMatrixAt(i, dummy.matrix);

        // Lamp head extending toward road
        const headOffset = 0.55;
        const hx = l.position.x + Math.sin(l.rotationY) * headOffset;
        const hz = l.position.z + Math.cos(l.rotationY) * headOffset;
        dummy.position.set(hx, 5.4, hz);
        dummy.rotation.set(0, l.rotationY, 0);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        headInst.setMatrixAt(i, dummy.matrix);
      }

      poleInst.instanceMatrix.needsUpdate = true;
      headInst.instanceMatrix.needsUpdate = true;
      poleInst.computeBoundingSphere();
      headInst.computeBoundingSphere();

      urbanGroup.add(poleInst);
      urbanGroup.add(headInst);
    }
  }, [metroGeometry, scenario, lightingMode]);

  // 8. Update Vehicle Meshes & Ingest Telemetry into Interpolation Buffer
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentMeshes = vehicleMeshesRef.current;
    const activeVehicleIds = new Set<string>();

    for (const [vId, vState] of vehicles.entries()) {
      activeVehicleIds.add(vId);

      const isEmergency =
        vState.is_emergency ||
        vState.vehicle_type === "emergency" ||
        vState.emergency_type !== undefined ||
        vId.toLowerCase().startsWith("amb_") ||
        vId.toLowerCase().startsWith("fire_") ||
        vId.toLowerCase().startsWith("emerg_");

      // Push sample to temporal interpolation buffer
      interpolationBufferRef.current.pushSample(vId, {
        position: vState.position,
        heading_rad: vState.heading_rad,
        speed_mps: vState.speed_mps,
        tick: vState.tick,
        timestamp_s: vState.simulation_time_s,
        lifecycle_state: vState.lifecycle_state,
        is_emergency: isEmergency,
        vehicle_type: vState.vehicle_type,
        route: vState.route,
        current_edge_id: vState.current_edge_id,
      });

      if (Number.isFinite(vState.simulation_time_s)) {
        latestSimTimeRef.current = Math.max(
          latestSimTimeRef.current,
          Number(vState.simulation_time_s)
        );
      } else if (Number.isFinite(vState.tick)) {
        latestSimTimeRef.current = Math.max(
          latestSimTimeRef.current,
          Number(vState.tick) * 0.1
        );
      }

      let vGroup = currentMeshes.get(vId);
      if (!vGroup) {
        const modelType = determineVehicleModelType(
          vId,
          vState.vehicle_type,
          vState.emergency_type,
          vState.model_type
        );
        vGroup = createVehicleModel(modelType, {
          vehicleId: vId,
          isEmergency,
        });

        // Set initial world coordinates
        const worldPos = simToWorldCoordinates(vState.position.x, vState.position.y, 0.5);
        vGroup.position.set(worldPos.x, worldPos.y, worldPos.z);
        vGroup.rotation.y = simHeadingToWorldRotationY(vState.heading_rad);
        scene.add(vGroup);
        currentMeshes.set(vId, vGroup);
      }
    }

    // Remove deleted vehicles
    for (const [id, mesh] of currentMeshes.entries()) {
      if (!activeVehicleIds.has(id)) {
        scene.remove(mesh);
        currentMeshes.delete(id);
        interpolationBufferRef.current.removeEntity(id);
      }
    }
  }, [vehicles]);

  // 9. Update Pedestrian Meshes & Ingest Telemetry into Interpolation Buffer
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentMeshes = pedestrianMeshesRef.current;
    const activePedIds = new Set<string>();

    for (const [pId, pState] of pedestrians.entries()) {
      activePedIds.add(pId);

      // Push sample to temporal interpolation buffer
      interpolationBufferRef.current.pushSample(pId, {
        position: pState.position,
        heading_rad: pState.heading_rad,
        speed_mps: pState.speed_mps,
        tick: pState.tick,
        timestamp_s: pState.simulation_time_s,
        lifecycle_state: pState.lifecycle_state,
      });

      if (Number.isFinite(pState.simulation_time_s)) {
        latestSimTimeRef.current = Math.max(
          latestSimTimeRef.current,
          Number(pState.simulation_time_s)
        );
      } else if (Number.isFinite(pState.tick)) {
        latestSimTimeRef.current = Math.max(
          latestSimTimeRef.current,
          Number(pState.tick) * 0.1
        );
      }

      let pGroup = currentMeshes.get(pId);
      if (!pGroup) {
        pGroup = createPedestrianModel({
          pedestrianId: pId,
          isCrossing: pState.lifecycle_state === "crossing",
        });

        const worldPos = simToWorldCoordinates(pState.position.x, pState.position.y, 0);
        pGroup.position.set(worldPos.x, 0, worldPos.z);
        pGroup.rotation.y = simHeadingToWorldRotationY(pState.heading_rad);
        scene.add(pGroup);
        currentMeshes.set(pId, pGroup);
      }
    }

    // Remove deleted pedestrians
    for (const [id, mesh] of currentMeshes.entries()) {
      if (!activePedIds.has(id)) {
        scene.remove(mesh);
        currentMeshes.delete(id);
        interpolationBufferRef.current.removeEntity(id);
      }
    }
  }, [pedestrians]);

  // 10. Scenario or Run Reset: Clean up dynamic entities and interpolation buffers
  useEffect(() => {
    const scene = sceneRef.current;
    if (scene) {
      for (const group of vehicleMeshesRef.current.values()) {
        scene.remove(group);
      }
      vehicleMeshesRef.current.clear();
      for (const group of pedestrianMeshesRef.current.values()) {
        scene.remove(group);
      }
      pedestrianMeshesRef.current.clear();
    }
    interpolationBufferRef.current.clear();
    latestSimTimeRef.current = 0;
    simTimeRef.current = 0;
    v2vOverlayRef.current?.clear();
    routeOverlayRef.current?.clear();
    prevDeliveredRef.current = 0;
    prevDroppedRef.current = 0;
  }, [scenario?.metadata?.id]);

  // Message pulse & drop animation trigger tracking
  const prevDeliveredRef = useRef<number>(0);
  const prevDroppedRef = useRef<number>(0);

  useEffect(() => {
    if (!communicationSnapshot) return;
    const { totalDelivered, totalDropped } = communicationSnapshot.networkState;
    const links = communicationSnapshot.links;

    // Trigger delivery pulse along a confirmed active link
    if (totalDelivered > prevDeliveredRef.current && prevDeliveredRef.current > 0 && links.length > 0) {
      const activeLinks = links.filter((l: V2VLink) => l.status === "active");
      const candLinks = activeLinks.length > 0 ? activeLinks : links;
      const link = candLinks[Math.floor(Math.random() * candLinks.length)];
      const posA = vehicleMeshesRef.current.get(link.vehicleA)?.position;
      const posB = vehicleMeshesRef.current.get(link.vehicleB)?.position;
      if (posA && posB) {
        v2vOverlayRef.current?.triggerAnimation({
          id: `pulse_${Date.now()}_${Math.random()}`,
          type: "delivery",
          senderId: link.vehicleA,
          receiverId: link.vehicleB,
          startWorldPos: { x: posA.x, y: posA.y, z: posA.z },
          endWorldPos: { x: posB.x, y: posB.y, z: posB.z },
          progress: 0,
          durationS: 0.8,
          elapsedS: 0,
          timestampS: communicationSnapshot.timestampS,
        });
      }
    }
    prevDeliveredRef.current = totalDelivered;

    // Trigger dropped packet marker at transmission location
    if (totalDropped > prevDroppedRef.current && prevDroppedRef.current > 0) {
      const vId = selectedEntityId && vehicleMeshesRef.current.has(selectedEntityId)
        ? selectedEntityId
        : vehicleMeshesRef.current.keys().next().value;
      if (vId) {
        const mesh = vehicleMeshesRef.current.get(vId);
        if (mesh) {
          v2vOverlayRef.current?.triggerAnimation({
            id: `drop_${Date.now()}_${Math.random()}`,
            type: "dropped",
            senderId: vId,
            startWorldPos: { x: mesh.position.x, y: mesh.position.y, z: mesh.position.z },
            progress: 0,
            durationS: 1.0,
            elapsedS: 0,
            timestampS: communicationSnapshot.timestampS,
            dropReason: "packet_loss",
          });
        }
      }
    }
    prevDroppedRef.current = totalDropped;
  }, [communicationSnapshot, selectedEntityId]);

  // 11. Update Traffic Signals
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

        const node = metroGeometry.nodes.find((n) => n.id === sigState.node_id);
        if (node) {
          const pos = simToWorldCoordinates(node.x, node.y, 8.5);
          mesh.position.set(pos.x + 6, 8.5, pos.z + 6);
          scene.add(mesh);
          currentMeshes.set(sigId, mesh);
        }
      } else {
        sigMesh.material.color.setHex(color);
      }
    }
  }, [signals, metroGeometry]);

  // 12. Update Active Route Line
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    if (routeLineRef.current) {
      scene.remove(routeLineRef.current);
      routeLineRef.current = null;
    }

    if (!activeRoute || activeRoute.length < 2) return;

    const nodeMap = new Map<string, RoadNodeGeometry>();
    for (const n of metroGeometry.nodes) {
      nodeMap.set(n.id, n);
    }

    const points: THREE.Vector3[] = [];
    const laneOffset = 1.85;

    for (let i = 0; i < activeRoute.length; i++) {
      const curr = nodeMap.get(activeRoute[i]);
      if (!curr) continue;

      let rnx = 0;
      let rny = 0;

      if (i < activeRoute.length - 1) {
        const next = nodeMap.get(activeRoute[i + 1]);
        if (next) {
          const dx = next.x - curr.x;
          const dy = next.y - curr.y;
          const len = Math.hypot(dx, dy) || 1;
          rnx = dy / len;
          rny = -dx / len;
        }
      } else if (i > 0) {
        const prev = nodeMap.get(activeRoute[i - 1]);
        if (prev) {
          const dx = curr.x - prev.x;
          const dy = curr.y - prev.y;
          const len = Math.hypot(dx, dy) || 1;
          rnx = dy / len;
          rny = -dx / len;
        }
      }

      const p = simToWorldCoordinates(curr.x + rnx * laneOffset, curr.y + rny * laneOffset, 0.45);
      points.push(new THREE.Vector3(p.x, p.y, p.z));
    }

    if (points.length >= 2) {
      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({
        color: 0x06b6d4, // High-visibility cyan ribbon
        linewidth: 4,
      });
      const line = new THREE.Line(lineGeo, lineMat);
      scene.add(line);
      routeLineRef.current = line;
    }
  }, [activeRoute, metroGeometry]);

  // 12. Mouse Drag & Orbit Controls
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

  // 13. Click to select vehicle/pedestrian
  const handleClick = (e: React.MouseEvent) => {
    if (!onSelectEntity) return;
    const container = containerRef.current;
    const scene = sceneRef.current;
    const activeCam =
      projectionMode === "perspective"
        ? perspectiveCameraRef.current
        : orthographicCameraRef.current;
    if (!container || !activeCam || !scene) return;

    const rect = container.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, activeCam);

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
        backgroundColor: "#f1f5f9",
        cursor: "grab",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: "block", width: "100%", height: "100%" }}
      />

      {/* WebGL Error Banner */}
      {webglError && (
        <div
          role="alert"
          style={{
            position: "absolute",
            top: "16px",
            left: "16px",
            right: "16px",
            backgroundColor: "#fef2f2",
            color: "#991b1b",
            padding: "12px 16px",
            borderRadius: "6px",
            fontSize: "0.85rem",
            fontWeight: 500,
            zIndex: 20,
            border: "1px solid #fecaca",
          }}
        >
          {webglError}
        </div>
      )}

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
            backgroundColor: "rgba(241, 245, 249, 0.85)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#0f172a",
            fontSize: "1rem",
            fontWeight: 500,
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 10,
          }}
        >
          Loading 3D Simulation Environment...
        </div>
      )}

      {/* Floating HUD: Historical Review Banner */}
      {isReviewing && (
        <div
          className="viewport-hud-review-banner"
          role="status"
          style={{
            position: "absolute",
            top: "16px",
            left: "50%",
            transform: "translateX(-50%)",
            backgroundColor: "rgba(255, 251, 235, 0.95)",
            backdropFilter: "blur(6px)",
            border: "1px solid #fde68a",
            borderRadius: "8px",
            padding: "8px 16px",
            color: "#92400e",
            fontFamily: "Space Grotesk, sans-serif",
            fontSize: "0.85rem",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "12px",
            zIndex: 10,
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
          }}
        >
          <span>🕒 HISTORICAL REVIEW — TICK {reviewTick ?? 0}</span>
          {onReturnToLive && (
            <button
              type="button"
              onClick={onReturnToLive}
              aria-label="Return to Live Simulation View"
              style={{
                backgroundColor: "#d97706",
                color: "#ffffff",
                border: "none",
                borderRadius: "4px",
                padding: "4px 10px",
                fontSize: "0.75rem",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Return to Live ➔
            </button>
          )}
        </div>
      )}

      {/* Floating HUD: Controls (Projection, Lighting, Buildings, Reset) */}
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
        {/* Day / Night Mode Toggle */}
        <button
          type="button"
          onClick={() => setLightingMode((m) => (m === "day" ? "night" : "day"))}
          className="hud-button"
          title={`Switch to ${lightingMode === "day" ? "Night" : "Day"} Mode`}
          aria-label={`Switch to ${lightingMode === "day" ? "Night" : "Day"} Mode`}
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          {lightingMode === "day" ? "☀️ Day" : "🌙 Night"}
        </button>

        {/* Perspective / Orthographic Camera Toggle */}
        <button
          type="button"
          onClick={() =>
            setProjectionMode((p) => (p === "perspective" ? "orthographic" : "perspective"))
          }
          className="hud-button"
          title={`Switch to ${projectionMode === "perspective" ? "Orthographic" : "Perspective"} Projection`}
          aria-label={`Switch to ${projectionMode === "perspective" ? "Orthographic" : "Perspective"} Projection`}
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          {projectionMode === "perspective" ? "📷 3D Persp" : "📐 2D Ortho"}
        </button>

        {/* Buildings ON / OFF Toggle */}
        <button
          type="button"
          onClick={() => setShowBuildings((b) => !b)}
          className="hud-button"
          title={`${showBuildings ? "Hide" : "Show"} Procedural Buildings`}
          aria-label={`${showBuildings ? "Hide" : "Show"} Procedural Buildings`}
          style={{
            backgroundColor: showBuildings ? "#0f172a" : "#ffffff",
            color: showBuildings ? "#ffffff" : "#64748b",
            border: showBuildings ? "1px solid #0f172a" : "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          {showBuildings ? "🏢 Buildings ON" : "🏢 Buildings OFF"}
        </button>

        {/* Camera View Presets */}
        <button
          type="button"
          onClick={() => handleSetCameraPreset("metropolis")}
          className="hud-button"
          title="Wide Metropolis Overview"
          aria-label="Wide Metropolis Overview"
          style={{
            backgroundColor: "#ffffff",
            color: "#0284c7",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          Metropolis
        </button>

        <button
          type="button"
          onClick={() => handleSetCameraPreset("downtown")}
          className="hud-button"
          title="Downtown Core View"
          aria-label="Downtown Core View"
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          Downtown
        </button>

        <button
          type="button"
          onClick={() => handleSetCameraPreset("street")}
          className="hud-button"
          title="Street-Level View"
          aria-label="Street-Level View"
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          Street
        </button>

        {/* Reset View Button */}
        <button
          type="button"
          onClick={handleResetCamera}
          className="hud-button"
          title="Reset Camera View"
          aria-label="Reset Camera View"
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          Reset View
        </button>
      </div>

      {/* Floating HUD: V2V Overlay Controls */}
      <div
        className="viewport-hud-v2v-controls"
        role="toolbar"
        aria-label="V2V Overlay Controls"
        style={{
          position: "absolute",
          top: "60px",
          right: "16px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: "8px",
          zIndex: 5,
          maxWidth: "480px",
        }}
      >
        <button
          type="button"
          onClick={() => {
            const next = !v2vOptions.showLinks;
            setV2vOptions((prev) => ({ ...prev, showLinks: next }));
            v2vOverlayRef.current?.setOptions({ showLinks: next });
          }}
          className={`hud-button hud-v2v-toggle ${v2vOptions.showLinks ? "active" : ""}`}
          aria-pressed={v2vOptions.showLinks}
          aria-label={v2vOptions.showLinks ? "Hide V2V Links" : "Show V2V Links"}
          title={v2vOptions.showLinks ? "Hide V2V Links" : "Show V2V Links"}
          style={{
            backgroundColor: v2vOptions.showLinks ? "#0284c7" : "#ffffff",
            color: v2vOptions.showLinks ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          V2V Links {v2vOptions.showLinks ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            const next = !v2vOptions.showRangeRing;
            setV2vOptions((prev) => ({ ...prev, showRangeRing: next }));
            v2vOverlayRef.current?.setOptions({ showRangeRing: next });
          }}
          className={`hud-button hud-v2v-toggle ${v2vOptions.showRangeRing ? "active" : ""}`}
          aria-pressed={v2vOptions.showRangeRing}
          aria-label={v2vOptions.showRangeRing ? "Hide Range Ring" : "Show Range Ring"}
          title={v2vOptions.showRangeRing ? "Hide Range Ring" : "Show Range Ring"}
          style={{
            backgroundColor: v2vOptions.showRangeRing ? "#0284c7" : "#ffffff",
            color: v2vOptions.showRangeRing ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Radio Range {v2vOptions.showRangeRing ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            setV2vOptions(DEFAULT_V2V_OVERLAY_OPTIONS);
            v2vOverlayRef.current?.setOptions(DEFAULT_V2V_OVERLAY_OPTIONS);
          }}
          className="hud-button"
          aria-label="Reset V2V overlays to defaults"
          title="Reset V2V Overlays to Defaults"
          style={{
            backgroundColor: "#ffffff",
            color: "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Reset V2V
        </button>

        <button
          type="button"
          onClick={() => setShowV2VLegend((s) => !s)}
          className={`hud-button ${showV2VLegend ? "active" : ""}`}
          aria-expanded={showV2VLegend}
          aria-controls="v2v-legend-panel"
          aria-label={showV2VLegend ? "Close V2V Legend" : "Open V2V Legend"}
          title={showV2VLegend ? "Close V2V Legend" : "Open V2V Legend"}
          style={{
            backgroundColor: showV2VLegend ? "#0f172a" : "#ffffff",
            color: showV2VLegend ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          V2V Legend
        </button>
      </div>

      {/* Collapsible V2V Visual Legend */}
      {showV2VLegend && (
        <div
          id="v2v-legend-panel"
          className="viewport-v2v-legend-panel"
          role="region"
          aria-label="V2V Visual Legend and Network State"
          style={{
            position: "absolute",
            top: "105px",
            right: "16px",
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            backdropFilter: "blur(8px)",
            border: "1px solid #e2e8f0",
            borderRadius: "8px",
            padding: "12px 16px",
            fontSize: "0.78rem",
            color: "#0f172a",
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 6,
            maxWidth: "320px",
            boxShadow: "0 10px 25px -5px rgba(0,0,0,0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontWeight: 700, color: "#0284c7", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              V2V Visual Legend
            </span>
            <button
              type="button"
              onClick={() => setShowV2VLegend(false)}
              aria-label="Dismiss V2V Legend Panel"
              style={{
                background: "none",
                border: "none",
                color: "#64748b",
                cursor: "pointer",
                fontWeight: "bold",
                fontSize: "0.9rem",
              }}
            >
              ✕
            </button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", backgroundColor: "#0284c7", display: "inline-block" }} />
              <span>Active Neighbor Link (Confirmed)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", borderTop: "2px dashed #f59e0b", display: "inline-block" }} />
              <span>Stale / Degraded Link (Timeout)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "12px", height: "12px", borderRadius: "50%", border: "2px solid #0284c7", display: "inline-block" }} />
              <span>Radio Range: {communicationSnapshot?.rangeM !== null && communicationSnapshot?.rangeM !== undefined ? `${communicationSnapshot.rangeM.toFixed(1)} m` : "Unavailable"}</span>
            </div>
          </div>

          <div style={{ marginTop: "10px", paddingTop: "8px", borderTop: "1px solid #e2e8f0", fontSize: "0.75rem", color: "#64748b" }}>
            <div>Channel State: <span style={{ fontWeight: 600, color: communicationSnapshot?.networkState.channelState === "bad" ? "#dc2626" : communicationSnapshot?.networkState.channelState === "good" ? "#059669" : "#64748b" }}>{communicationSnapshot?.networkState.channelState ? communicationSnapshot.networkState.channelState.toUpperCase() : "Unavailable"}</span></div>
            <div>Packet Delivery Ratio: <span style={{ fontWeight: 600, color: "#0284c7" }}>{communicationSnapshot?.networkState.packetDeliveryRatio !== null && communicationSnapshot?.networkState.packetDeliveryRatio !== undefined ? `${(communicationSnapshot.networkState.packetDeliveryRatio * 100).toFixed(1)}%` : "Unavailable"}</span></div>
          </div>
        </div>
      )}

      {/* Floating HUD: Adaptive Routing Controls */}
      <div
        className="viewport-hud-route-controls"
        role="toolbar"
        aria-label="Route Overlay Controls"
        style={{
          position: "absolute",
          top: "105px",
          right: "16px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: "8px",
          zIndex: 5,
          maxWidth: "480px",
        }}
      >
        <button
          type="button"
          onClick={() => {
            const next = !routeOptions.showActiveRoutes;
            setRouteOptions((prev) => ({ ...prev, showActiveRoutes: next }));
            routeOverlayRef.current?.setOptions({ showActiveRoutes: next });
          }}
          className={`hud-button hud-route-toggle ${routeOptions.showActiveRoutes ? "active" : ""}`}
          aria-pressed={routeOptions.showActiveRoutes}
          aria-label={routeOptions.showActiveRoutes ? "Hide Active Route" : "Show Active Route"}
          title={routeOptions.showActiveRoutes ? "Hide Active Route" : "Show Active Route"}
          style={{
            backgroundColor: routeOptions.showActiveRoutes ? "#0284c7" : "#ffffff",
            color: routeOptions.showActiveRoutes ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Active Route {routeOptions.showActiveRoutes ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            const next = !routeOptions.showPlannedRoutes;
            setRouteOptions((prev) => ({ ...prev, showPlannedRoutes: next }));
            routeOverlayRef.current?.setOptions({ showPlannedRoutes: next });
          }}
          className={`hud-button hud-route-toggle ${routeOptions.showPlannedRoutes ? "active" : ""}`}
          aria-pressed={routeOptions.showPlannedRoutes}
          aria-label={routeOptions.showPlannedRoutes ? "Hide Planned Route" : "Show Planned Route"}
          title={routeOptions.showPlannedRoutes ? "Hide Planned Route" : "Show Planned Route"}
          style={{
            backgroundColor: routeOptions.showPlannedRoutes ? "#0284c7" : "#ffffff",
            color: routeOptions.showPlannedRoutes ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Planned Route {routeOptions.showPlannedRoutes ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            const next = !routeOptions.showCandidateRoutes;
            setRouteOptions((prev) => ({ ...prev, showCandidateRoutes: next }));
            routeOverlayRef.current?.setOptions({ showCandidateRoutes: next });
          }}
          className={`hud-button hud-route-toggle ${routeOptions.showCandidateRoutes ? "active" : ""}`}
          aria-pressed={routeOptions.showCandidateRoutes}
          aria-label={routeOptions.showCandidateRoutes ? "Hide Candidate Paths" : "Show Candidate Paths"}
          title={routeOptions.showCandidateRoutes ? "Hide Candidate Paths" : "Show Candidate Paths"}
          style={{
            backgroundColor: routeOptions.showCandidateRoutes ? "#0284c7" : "#ffffff",
            color: routeOptions.showCandidateRoutes ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Candidates {routeOptions.showCandidateRoutes ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            const next = !routeOptions.showRerouteMarkers;
            setRouteOptions((prev) => ({ ...prev, showRerouteMarkers: next }));
            routeOverlayRef.current?.setOptions({ showRerouteMarkers: next });
          }}
          className={`hud-button hud-route-toggle ${routeOptions.showRerouteMarkers ? "active" : ""}`}
          aria-pressed={routeOptions.showRerouteMarkers}
          aria-label={routeOptions.showRerouteMarkers ? "Hide Reroute Markers" : "Show Reroute Markers"}
          title={routeOptions.showRerouteMarkers ? "Hide Reroute Markers" : "Show Reroute Markers"}
          style={{
            backgroundColor: routeOptions.showRerouteMarkers ? "#0284c7" : "#ffffff",
            color: routeOptions.showRerouteMarkers ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Markers {routeOptions.showRerouteMarkers ? "ON" : "OFF"}
        </button>

        <button
          type="button"
          onClick={() => {
            setRouteOptions(DEFAULT_ROUTE_OVERLAY_OPTIONS);
            routeOverlayRef.current?.setOptions(DEFAULT_ROUTE_OVERLAY_OPTIONS);
          }}
          className="hud-button"
          aria-label="Reset Route Overlays to Defaults"
          title="Reset Route Overlays to Defaults"
          style={{
            backgroundColor: "#ffffff",
            color: "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Reset Routes
        </button>

        <button
          type="button"
          onClick={() => setShowRouteLegend((s) => !s)}
          className={`hud-button ${showRouteLegend ? "active" : ""}`}
          aria-expanded={showRouteLegend}
          aria-controls="route-legend-panel"
          aria-label={showRouteLegend ? "Close Route Legend" : "Open Route Legend"}
          title={showRouteLegend ? "Close Route Legend" : "Open Route Legend"}
          style={{
            backgroundColor: showRouteLegend ? "#0f172a" : "#ffffff",
            color: showRouteLegend ? "#ffffff" : "#475569",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Route Legend
        </button>
      </div>

      {/* Collapsible Route Visual Legend */}
      {showRouteLegend && (
        <div
          id="route-legend-panel"
          className="viewport-route-legend-panel"
          role="region"
          aria-label="Route Visual Legend and Alternative Paths"
          style={{
            position: "absolute",
            top: "150px",
            right: "16px",
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            backdropFilter: "blur(8px)",
            border: "1px solid #e2e8f0",
            borderRadius: "8px",
            padding: "12px 16px",
            fontSize: "0.78rem",
            color: "#0f172a",
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 6,
            maxWidth: "320px",
            boxShadow: "0 10px 25px -5px rgba(0,0,0,0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontWeight: 700, color: "#0284c7", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Route Visual Legend
            </span>
            <button
              type="button"
              onClick={() => setShowRouteLegend(false)}
              aria-label="Dismiss Route Legend Panel"
              style={{
                background: "none",
                border: "none",
                color: "#64748b",
                cursor: "pointer",
                fontWeight: "bold",
                fontSize: "0.9rem",
              }}
            >
              ✕
            </button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", backgroundColor: "#0284c7", display: "inline-block" }} />
              <span>Active Route (Authoritative Path)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", borderTop: "2px dashed #94a3b8", display: "inline-block" }} />
              <span>Planned Route (Baseline Comparison)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", borderTop: "2px dashed #a855f7", display: "inline-block" }} />
              <span>Alternative Candidate (Evaluated)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "20px", height: "3px", backgroundColor: "#f43f5e", display: "inline-block" }} />
              <span>Inspected Candidate Path</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "10px", height: "10px", transform: "rotate(45deg)", backgroundColor: "#059669", display: "inline-block" }} />
              <span>Accepted Reroute Decision</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "10px", height: "10px", transform: "rotate(45deg)", backgroundColor: "#f59e0b", display: "inline-block" }} />
              <span>Rejected / Insufficient Benefit</span>
            </div>
          </div>
        </div>
      )}

      {/* Floating HUD: Scene Legend */}
      <div
        className="viewport-hud-legend"
        style={{
          position: "absolute",
          bottom: "16px",
          left: "16px",
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          backdropFilter: "blur(6px)",
          border: "1px solid #e2e8f0",
          borderRadius: "8px",
          padding: "8px 14px",
          fontSize: "0.75rem",
          color: "#475569",
          display: "flex",
          gap: "16px",
          alignItems: "center",
          fontFamily: "Space Grotesk, sans-serif",
          zIndex: 5,
          boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#0284c7", borderRadius: "2px" }} />
          <span>Vehicle</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#dc2626", borderRadius: "2px" }} />
          <span>Emergency</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#0891b2", borderRadius: "50%" }} />
          <span>Pedestrian</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#059669", borderRadius: "50%" }} />
          <span>Signal</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "#f59e0b", borderRadius: "2px" }} />
          <span>Lane Marking</span>
        </div>
      </div>
    </div>
  );
};
