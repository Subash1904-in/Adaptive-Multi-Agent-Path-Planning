/**
 * Interactive 3D Simulation Viewport for AMAPP in Luxembourg City.
 *
 * Combines high-fidelity Three.js OSM city rendering (terrain elevation, merged buildings
 * with procedural facade shaders, real road network, day/night lighting, weather) with
 * autonomous multi-agent path planning, 3D glowing route ribbons, holographic V2V links,
 * dynamic incident markers, drivable hero vehicle mode, chase camera, minimap radar,
 * and fullscreen big map.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { buildWorld } from "../../city/world/model.js";
import {
  configureTerrain,
  groundHeight,
  surfaceHeight,
  surfaceNormal,
} from "../../city/world/terrain.js";
import { setGroundSampler, setNormalSampler } from "../../city/world/ground.js";
import { createScene, makeCar as makeCityCar } from "../../city/render/scene.js";
import {
  createBirdCamera,
  createChaseCamera,
  resetChase,
  restoreUp,
  updateBird,
  updateChase,
  zoomBird,
} from "../../city/game/camera.js";
import { createCar, stepCar } from "../../city/game/car.js";
import { createCarVisual, updateCarVisual } from "../../city/game/carvisual.js";
import { createAudio } from "../../city/game/audio.js";
import { createBigMap } from "../../city/game/bigmap.js";
import { createMinimap } from "../../city/game/minimap.js";
import {
  createPedestrianModel,
  createVehicleModel,
  determineVehicleModelType,
  disposeModelAssets,
  updatePedestrianVisuals,
  updateVehicleVisuals,
} from "./models";
import { RouteOverlayManager } from "./routeOverlay";
import { V2VOverlayManager } from "./v2vOverlay";
import { IncidentOverlayManager } from "./incidentOverlay";
import { LuxembourgCitySimulation } from "../simulation/citySimulation";
import type {
  PedestrianState,
  RunMetrics,
  ScenarioDefinition,
  TrafficSignalState,
  VehicleState,
} from "../../types/simulation";
import {
  type RouteSubsystemSnapshot,
  type RouteOverlayOptions,
  DEFAULT_ROUTE_OVERLAY_OPTIONS,
} from "../../types/routing";
import {
  type V2VSubsystemSnapshot,
  type V2VOverlayOptions,
  DEFAULT_V2V_OVERLAY_OPTIONS,
} from "../../types/v2v";
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
  onSimulationUpdate?: (data: {
    vehicles: Map<string, VehicleState>;
    pedestrians: Map<string, PedestrianState>;
    signals: Map<string, TrafficSignalState>;
    v2vSnapshot: V2VSubsystemSnapshot;
    routeSnapshot: RouteSubsystemSnapshot;
    incidents: IncidentRecord[];
    metrics: RunMetrics;
  }) => void;
}

export const SimulationViewer3D: React.FC<SimulationViewer3DProps> = ({
  scenario,
  vehicles: externalVehicles,
  pedestrians: externalPedestrians,
  selectedEntityId,
  onSelectEntity,
  isLoading = false,
  isReviewing = false,
  reviewTick = null,
  onReturnToLive,
  communicationSnapshot,
  routeSnapshot: externalRouteSnapshot,
  selectedCandidateId,
  playbackSpeed = 1,
  isPaused = false,
  incidents: externalIncidents,
  onSimulationUpdate,
}) => {
  const externalV2VSnapshot = communicationSnapshot;
  const containerRef = useRef<HTMLDivElement>(null);

  // Core Simulation & City Engine Refs
  const simRef = useRef<LuxembourgCitySimulation>(new LuxembourgCitySimulation());
  const sceneHandlesRef = useRef<any>(null);
  const heroCarRef = useRef<any>(null);
  const heroMeshRef = useRef<THREE.Group | null>(null);
  const heroCarVisualRef = useRef<any>(null);
  const chaseCameraRef = useRef<any>(null);
  const birdCameraRef = useRef<any>(null);
  const bigmapRef = useRef<any>(null);
  const minimapRef = useRef<any>(null);
  const audioRef = useRef<any>(null);

  // 3D Visual Mesh Pools
  const vehicleMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const pedestrianMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const selectionMarkerRef = useRef<THREE.Mesh | null>(null);

  // AMAPP 3D Overlays
  const routeOverlayRef = useRef<RouteOverlayManager>(new RouteOverlayManager());
  const v2vOverlayRef = useRef<V2VOverlayManager>(new V2VOverlayManager());
  const incidentOverlayRef = useRef<IncidentOverlayManager>(new IncidentOverlayManager());

  // Game UI & Interaction State
  const [cameraMode, setCameraMode] = useState<"chase" | "bird" | "free">("chase");
  const [timeOfDayHours, setTimeOfDayHours] = useState<number>(20.4); // Start at atmospheric blue hour
  const [isRaining, setIsRaining] = useState<boolean>(false);
  const [isHeroDriveMode, setIsHeroDriveMode] = useState<boolean>(false);
  const [speedKmh, setSpeedKmh] = useState<number>(38);
  const [currentStreetName, setCurrentStreetName] = useState<string>("Boulevard Royal");
  const [isMapOpen, setIsMapOpen] = useState<boolean>(false);
  const [cityLoadingState, setCityLoadingState] = useState<string>("Loading Luxembourg 3D City…");
  const [cityLoaded, setCityLoaded] = useState<boolean>(false);
  // Viewport Lighting & Projection Controls
  const [lightingMode, setLightingMode] = useState<"day" | "night">("day");
  const [projectionMode, setProjectionMode] = useState<"perspective" | "orthographic">("perspective");
  const [showBuildings, setShowBuildings] = useState<boolean>(true);

  // AMAPP Overlays & Legend State
  const [v2vOptions, setV2vOptions] = useState<V2VOverlayOptions>(DEFAULT_V2V_OVERLAY_OPTIONS);
  const [showV2VLegend, setShowV2VLegend] = useState<boolean>(false);
  const [routeOptions, setRouteOptions] = useState<RouteOverlayOptions>(DEFAULT_ROUTE_OVERLAY_OPTIONS);
  const [showRouteLegend, setShowRouteLegend] = useState<boolean>(false);

  // Manual driving input state
  const inputKeysRef = useRef({
    forward: false,
    backward: false,
    left: false,
    right: false,
    handbrake: false,
  });

  // Selected Entity Ref for frame loop
  const selectedEntityIdRef = useRef<string | null | undefined>(selectedEntityId);
  useEffect(() => {
    selectedEntityIdRef.current = selectedEntityId;
  }, [selectedEntityId]);

  // Sync buildings visibility
  useEffect(() => {
    if (sceneHandlesRef.current?.buildings) {
      sceneHandlesRef.current.buildings.visible = showBuildings;
    }
  }, [showBuildings]);

  // Sync external scenario change
  useEffect(() => {
    if (scenario?.metadata?.id) {
      simRef.current.loadScenario(scenario.metadata.id);
    }
  }, [scenario]);

  // Keyboard navigation & controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      const code = e.code;
      if (code === "KeyW" || code === "ArrowUp") inputKeysRef.current.forward = true;
      if (code === "KeyS" || code === "ArrowDown") inputKeysRef.current.backward = true;
      if (code === "KeyA" || code === "ArrowLeft") inputKeysRef.current.left = true;
      if (code === "KeyD" || code === "ArrowRight") inputKeysRef.current.right = true;
      if (code === "Space") inputKeysRef.current.handbrake = true;

      // 'M' toggles the fullscreen map
      if (code === "KeyM") {
        if (bigmapRef.current) {
          bigmapRef.current.toggle();
          setIsMapOpen(bigmapRef.current.isOpen());
        }
      }
      if (code === "Escape") {
        if (bigmapRef.current && bigmapRef.current.isOpen()) {
          bigmapRef.current.close();
          setIsMapOpen(false);
        }
      }

      // 'C' cycles camera mode
      if (code === "KeyC") {
        setCameraMode((prev) => (prev === "chase" ? "bird" : prev === "bird" ? "free" : "chase"));
      }

      // 'R' resets/recovers hero car
      if (code === "KeyR" && heroCarRef.current) {
        heroCarRef.current.vx = 0;
        heroCarRef.current.vy = 0;
        heroCarRef.current.speed = 0;
        if (chaseCameraRef.current) resetChase(chaseCameraRef.current);
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const code = e.code;
      if (code === "KeyW" || code === "ArrowUp") inputKeysRef.current.forward = false;
      if (code === "KeyS" || code === "ArrowDown") inputKeysRef.current.backward = false;
      if (code === "KeyA" || code === "ArrowLeft") inputKeysRef.current.left = false;
      if (code === "KeyD" || code === "ArrowRight") inputKeysRef.current.right = false;
      if (code === "Space") inputKeysRef.current.handbrake = false;
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, []);

  // Wheel zoom for Bird camera
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (cameraMode === "bird" && birdCameraRef.current) {
        e.preventDefault();
        zoomBird(birdCameraRef.current, e.deltaY > 0 ? 1.15 : 1 / 1.15);
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener("wheel", handleWheel, { passive: false });
      return () => container.removeEventListener("wheel", handleWheel);
    }
  }, [cameraMode]);

  // Main 3D City Initialization & Animation Loop
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let isDisposed = false;
    let animationFrameId: number;

    async function bootCityEngine() {
      try {
        setCityLoadingState("Loading Luxembourg OSM data & 3D buildings…");

        // 1. Fetch real city geometry & airport
        const [cityRes, findelRes] = await Promise.all([
          fetch("/data/city.json").then((r) => r.json()),
          fetch("/data/findel.json")
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null),
        ]);

        if (isDisposed) return;

        setCityLoadingState("Synthesizing road network & elevation terrain…");
        const world = buildWorld(cityRes, findelRes) as any;
        world.findel = findelRes;
        configureTerrain(world);
        world.parcels = cityRes.parcels ?? [];

        // Ground elevation samplers
        setGroundSampler((x: number, y: number, ref?: number) => surfaceHeight(x, -y, ref));
        setNormalSampler((x: number, y: number, ref?: number) => surfaceNormal(x, -y, ref));

        setCityLoadingState("Compiling shaders, sky dome & illumination…");
        const handles = createScene(world);
        sceneHandlesRef.current = handles;

        const { scene, camera, renderer } = handles;
        renderer.domElement.style.position = "absolute";
        renderer.domElement.style.inset = "0";
        renderer.domElement.style.width = "100%";
        renderer.domElement.style.height = "100%";
        renderer.domElement.style.display = "block";
        renderer.domElement.style.zIndex = "1";
        container?.appendChild(renderer.domElement);

        // 2. Setup Cameras & Hero Car
        chaseCameraRef.current = createChaseCamera();
        birdCameraRef.current = createBirdCamera();

        // Spawn hero car on Boulevard Royal
        const spawnEdge =
          world.edges.find((e: any) => e.name && e.name.includes("Boulevard Royal")) || world.edges[0];
        const midIdx = Math.max(1, Math.floor(spawnEdge.pts.length / 2));
        const p0 = spawnEdge.pts[midIdx - 1];
        const p1 = spawnEdge.pts[midIdx];
        const initialHeading = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);

        const heroCar = createCar(p0[0], p0[1], initialHeading);
        heroCarRef.current = heroCar;

        const heroMesh = makeCityCar(0x2563eb);
        heroMesh.name = "hero_car";
        heroMesh.userData = { isHero: true, vehicleId: "hero_car" };
        scene.add(heroMesh);
        heroMeshRef.current = heroMesh;
        heroCarVisualRef.current = createCarVisual(heroMesh);
        handles.follow(heroMesh);

        // Selection 3D Halo Marker
        const haloGeo = new THREE.RingGeometry(2.4, 2.9, 32);
        haloGeo.rotateX(-Math.PI / 2);
        const haloMat = new THREE.MeshBasicMaterial({
          color: 0x38bdf8,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.85,
        });
        const haloMesh = new THREE.Mesh(haloGeo, haloMat);
        haloMesh.visible = false;
        scene.add(haloMesh);
        selectionMarkerRef.current = haloMesh;

        // 3. Mount AMAPP 3D Overlays to Scene
        scene.add(routeOverlayRef.current.rootGroup);
        scene.add(v2vOverlayRef.current.rootGroup);
        scene.add(incidentOverlayRef.current.rootGroup);

        // 4. Initialize Big Map & Minimap
        bigmapRef.current = createBigMap(world);
        minimapRef.current = createMinimap(world);
        audioRef.current = createAudio();

        // 5. Initialize Multi-Agent Luxembourg Simulation Engine
        simRef.current.init(world, (x, z) => surfaceHeight(x, z));

        setCityLoaded(true);

        // Window & Container resize handler
        const handleResize = () => {
          if (!container) return;
          const w = Math.max(container.clientWidth || window.innerWidth || 800, 100);
          const h = Math.max(container.clientHeight || window.innerHeight || 600, 100);
          handles.resize(w, h);
        };
        window.addEventListener("resize", handleResize);
        const resizeObserver = new ResizeObserver(() => handleResize());
        if (container) resizeObserver.observe(container);
        handleResize();

        // 6. Main 60 FPS Render & Simulation Loop
        let lastTimestamp = performance.now();
        let simAccumulator = 0;
        const SIM_STEP = 0.05; // 20Hz physics / routing step

        const renderFrame = (timestamp: number) => {
          if (isDisposed) return;
          const dt = Math.min((timestamp - lastTimestamp) / 1000, 0.1);
          lastTimestamp = timestamp;

          // Step Autonomous Multi-Agent Simulation
          if (!isPaused) {
            simAccumulator += dt * playbackSpeed;
            while (simAccumulator >= SIM_STEP) {
              simRef.current.tick(SIM_STEP);
              simAccumulator -= SIM_STEP;
            }
          }

          // Step Hero Drivable Car Physics
          const keys = inputKeysRef.current;
          let throttle = 0;
          let steer = 0;
          let reverse = false;

          if (keys.forward) throttle = 1.0;
          if (keys.backward) {
            if (heroCar.speed > 0.5) throttle = -1.0; // Brake
            else reverse = true; // Reverse
          }
          if (keys.left) steer = -1.0;
          if (keys.right) steer = 1.0;

          stepCar(
            heroCar,
            {
              throttle: reverse ? -0.6 : throttle,
              steer,
              handbrake: keys.handbrake,
            },
            dt,
            world
          );

          // Update Hero 3D Visual Mesh
          const heroY = surfaceHeight(heroCar.x, -heroCar.y);
          heroMesh.position.set(heroCar.x, heroY, -heroCar.y);
          heroMesh.rotation.y = heroCar.heading;
          if (heroCarVisualRef.current) {
            updateCarVisual(heroCarVisualRef.current, heroCar, dt);
          }

          // Query Simulation State
          const simVehicles = simRef.current.getVehiclesState();
          const simPedestrians = simRef.current.getPedestriansState();
          const simSignals = simRef.current.getSignalsState();
          const simV2VSnapshot = simRef.current.getV2VSnapshot();
          const simRouteSnapshot = simRef.current.getRouteSnapshot(selectedEntityIdRef.current);
          const simIncidents = simRef.current.getIncidentsList();
          const simMetrics = simRef.current.getMetrics();
          const activeVehicles = externalVehicles.size > 0 ? externalVehicles : simVehicles;

          // Update Camera based on Mode & Target
          const activeCameraTarget =
            selectedEntityIdRef.current && vehicleMeshesRef.current.has(selectedEntityIdRef.current)
              ? vehicleMeshesRef.current.get(selectedEntityIdRef.current)!
              : heroMesh;

          // Target car object for camera in 2D world coords (x, y, heading, speed)
          let targetCar: any = heroCar;
          if (selectedEntityIdRef.current && activeVehicles.has(selectedEntityIdRef.current)) {
            const v = activeVehicles.get(selectedEntityIdRef.current)!;
            targetCar = {
              x: v.position.x,
              y: v.position.y,
              heading: v.heading_rad,
              speed: v.speed_mps,
              elevation: surfaceHeight(v.position.x, -v.position.y),
            };
          }

          if (cameraMode === "chase") {
            restoreUp(camera);
            updateChase(chaseCameraRef.current, targetCar, camera, dt, world);
          } else if (cameraMode === "bird") {
            updateBird(birdCameraRef.current, targetCar, camera, dt);
          } else if (cameraMode === "free") {
            restoreUp(camera);
            const elev = surfaceHeight(targetCar.x, -targetCar.y);
            camera.position.set(targetCar.x - 70, elev + 55, -targetCar.y + 70);
            camera.lookAt(targetCar.x, elev + 2, -targetCar.y);
          }

          if (activeCameraTarget) {
            handles.follow(activeCameraTarget);
          }

          // Sync data with React parent (App.tsx)
          if (onSimulationUpdate && Math.random() < 0.25) {
            onSimulationUpdate({
              vehicles: simVehicles,
              pedestrians: simPedestrians,
              signals: simSignals,
              v2vSnapshot: simV2VSnapshot,
              routeSnapshot: simRouteSnapshot,
              incidents: simIncidents,
              metrics: simMetrics,
            });
          }

          // Update 3D Vehicle Meshes
          activeVehicles.forEach((vehState, vehId) => {
            let mesh = vehicleMeshesRef.current.get(vehId);
            if (!mesh) {
              const modelType = determineVehicleModelType(
                vehId,
                vehState.vehicle_type,
                vehState.emergency_type,
                vehState.model_type
              );
              mesh = createVehicleModel(modelType, {
                vehicleId: vehId,
                isEmergency: vehState.is_emergency,
              });
              scene.add(mesh);
              vehicleMeshesRef.current.set(vehId, mesh);
            }

            const elev = surfaceHeight(vehState.position.x, -vehState.position.y);
            mesh.position.set(vehState.position.x, elev, -vehState.position.y);
            mesh.rotation.y = vehState.heading_rad;

            updateVehicleVisuals(
              mesh,
              {
                isEmergency: vehState.is_emergency,
                isSelected: vehId === selectedEntityIdRef.current,
                speed_mps: vehState.speed_mps,
              },
              timestamp / 1000
            );
          });

          // Clean up removed vehicle meshes
          vehicleMeshesRef.current.forEach((mesh, id) => {
            if (!activeVehicles.has(id)) {
              scene.remove(mesh);
              vehicleMeshesRef.current.delete(id);
            }
          });

          // Update 3D Pedestrian Meshes
          const activePeds = externalPedestrians.size > 0 ? externalPedestrians : simPedestrians;
          activePeds.forEach((pedState, pedId) => {
            let pMesh = pedestrianMeshesRef.current.get(pedId);
            if (!pMesh) {
              pMesh = createPedestrianModel({
                pedestrianId: pedId,
                isCrossing: pedState.lifecycle_state === "crossing",
              });
              scene.add(pMesh);
              pedestrianMeshesRef.current.set(pedId, pMesh);
            }

            const elev = groundHeight(pedState.position.x, -pedState.position.y);
            pMesh.position.set(pedState.position.x, elev, -pedState.position.y);
            pMesh.rotation.y = pedState.heading_rad;

            updatePedestrianVisuals(
              pMesh,
              {
                speed_mps: pedState.speed_mps,
                lifecycle_state: pedState.lifecycle_state,
                isSelected: pedId === selectedEntityIdRef.current,
              },
              timestamp / 1000
            );
          });

          // Update Selection Halo
          if (selectionMarkerRef.current) {
            if (selectedEntityIdRef.current && vehicleMeshesRef.current.has(selectedEntityIdRef.current)) {
              const target = vehicleMeshesRef.current.get(selectedEntityIdRef.current)!;
              selectionMarkerRef.current.position.set(
                target.position.x,
                target.position.y + 0.15,
                target.position.z
              );
              selectionMarkerRef.current.visible = true;
            } else {
              selectionMarkerRef.current.visible = false;
            }
          }

          // Update AMAPP 3D Overlays
          const v2vSnap = externalV2VSnapshot || simV2VSnapshot;
          v2vOverlayRef.current.updateLinks(v2vSnap.links, (id) => {
            if (id === "hero_car" && heroMeshRef.current) {
              return heroMeshRef.current.position;
            }
            const m = vehicleMeshesRef.current.get(id);
            return m ? m.position : null;
          });
          v2vOverlayRef.current.updateAnimations(dt, playbackSpeed, isPaused, false);

          const routeSnap = externalRouteSnapshot || simRouteSnapshot;
          routeOverlayRef.current.update(routeSnap, selectedEntityIdRef.current, selectedCandidateId);

          const incidentList = externalIncidents || simIncidents;
          incidentOverlayRef.current.update(incidentList);
          incidentOverlayRef.current.animate(dt);

          // Update Game HUD State
          const currentSpeedVal = Math.round(
            (isHeroDriveMode ? heroCar.speed : activeCameraTarget.userData?.speed ?? 11.2) * 3.6
          );
          setSpeedKmh(Math.max(0, currentSpeedVal));

          // Set active street name
          if (activeCameraTarget.userData?.currentStreet) {
            setCurrentStreetName(activeCameraTarget.userData.currentStreet);
          } else {
            setCurrentStreetName("Boulevard Royal");
          }

          // Scene daylight and weather updates
          const activeHours = lightingMode === "night" ? 22.0 : timeOfDayHours;
          handles.update(dt, activeHours);

          // Render Scene
          handles.render();

          // Update Minimap & Big Map
          if (minimapRef.current) {
            minimapRef.current.update(dt, heroCar, null, {
              cars: Array.from(activeVehicles.values()).map((v) => ({
                x: v.position.x,
                y: v.position.y,
              })),
            });
          }

          if (bigmapRef.current && bigmapRef.current.isOpen()) {
            bigmapRef.current.update(heroCar, null, {
              cars: Array.from(activeVehicles.values()).map((v) => ({
                x: v.position.x,
                y: v.position.y,
              })),
            });
          }

          animationFrameId = requestAnimationFrame(renderFrame);
        };

        animationFrameId = requestAnimationFrame(renderFrame);
      } catch (err) {
        console.error("Failed to boot 3D Luxembourg City Engine:", err);
        setCityLoadingState("Error initializing 3D city scene.");
      }
    }

    bootCityEngine();

    return () => {
      isDisposed = true;
      cancelAnimationFrame(animationFrameId);
      disposeModelAssets();
      if (sceneHandlesRef.current?.renderer?.domElement) {
        container?.removeChild(sceneHandlesRef.current.renderer.domElement);
      }
    };
  }, []);

  // Raycasting for interactive vehicle & road clicks
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const container = containerRef.current;
      const handles = sceneHandlesRef.current;
      if (!container || !handles) return;

      const rect = container.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );

      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(mouse, handles.camera);

      // Check vehicle clicks
      const vehicleMeshes = Array.from(vehicleMeshesRef.current.values());
      const intersects = raycaster.intersectObjects(vehicleMeshes, true);

      if (intersects.length > 0) {
        let current: THREE.Object3D | null = intersects[0].object;
        while (current && !current.userData.vehicleId && current.parent) {
          current = current.parent;
        }
        if (current && current.userData.vehicleId) {
          const vehId = current.userData.vehicleId;
          onSelectEntity?.(vehId, "vehicle");
          return;
        }
      }
    },
    [onSelectEntity]
  );

  return (
    <div
      ref={containerRef}
      className="city-viewport-container"
      aria-label="3D Simulation Viewport"
      onClick={handleCanvasClick}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        backgroundColor: "#0b0e1a",
      }}
    >
      {/* Loading Overlay */}
      {isLoading && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(15, 23, 42, 0.7)",
            backdropFilter: "blur(4px)",
            color: "#f8fafc",
            fontFamily: "Space Grotesk, sans-serif",
            fontSize: "1.1rem",
            zIndex: 200,
          }}
        >
          Loading 3D Simulation Environment...
        </div>
      )}

      {/* Historical Review Banner */}
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
            zIndex: 100,
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

      {/* Floating HUD: Camera and Viewport Controls */}
      <div
        className="viewport-hud-controls"
        role="toolbar"
        aria-label="Camera and Viewport Controls"
        style={{
          position: "absolute",
          top: "16px",
          right: "24px",
          display: "flex",
          gap: "8px",
          zIndex: 35,
          alignItems: "center",
        }}
      >
        {/* Day / Night Mode Toggle */}
        <button
          type="button"
          onClick={() => {
            const next = lightingMode === "day" ? "night" : "day";
            setLightingMode(next);
            setTimeOfDayHours(next === "night" ? 20.4 : 14);
          }}
          className="hud-button"
          title={`Switch to ${lightingMode === "day" ? "Night" : "Day"} Mode`}
          aria-label={`Switch to ${lightingMode === "day" ? "Night" : "Day"} Mode`}
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
          }}
        >
          {lightingMode === "day" ? "☀️ Day" : "🌙 Night"}
        </button>

        {/* Perspective / Orthographic Camera Toggle */}
        <button
          type="button"
          onClick={() => {
            const next = projectionMode === "perspective" ? "orthographic" : "perspective";
            setProjectionMode(next);
            setCameraMode(next === "orthographic" ? "bird" : "chase");
          }}
          className="hud-button"
          title={`Switch to ${projectionMode === "perspective" ? "Orthographic" : "Perspective"} Projection`}
          aria-label={`Switch to ${projectionMode === "perspective" ? "Orthographic" : "Perspective"} Projection`}
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
          }}
        >
          {projectionMode === "perspective" ? "📷 3D Persp" : "📐 2D Ortho"}
        </button>

        {/* Procedural Buildings Toggle */}
        <button
          type="button"
          onClick={() => {
            setShowBuildings((b) => !b);
          }}
          className="hud-button"
          title={`${showBuildings ? "Hide" : "Show"} Procedural Buildings`}
          aria-label={`${showBuildings ? "Hide" : "Show"} Procedural Buildings`}
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
          }}
        >
          {`🏢 Buildings ${showBuildings ? "ON" : "OFF"}`}
        </button>

        {/* Reset Camera View */}
        <button
          type="button"
          onClick={() => {
            setProjectionMode("perspective");
            setLightingMode("day");
            setTimeOfDayHours(14);
            setCameraMode("chase");
            setShowBuildings(true);
          }}
          className="hud-button"
          aria-label="Reset Camera View"
          title="Reset Camera View"
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#cbd5e1",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "0.82rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
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
          right: "24px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: "8px",
          zIndex: 35,
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
            backgroundColor: v2vOptions.showLinks ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: v2vOptions.showRangeRing ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
          aria-label="Reset V2V Overlays to Defaults"
          title="Reset V2V Overlays to Defaults"
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#cbd5e1",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: showV2VLegend ? "#0369a1" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            right: "24px",
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255, 255, 255, 0.15)",
            borderRadius: "8px",
            padding: "12px 16px",
            fontSize: "0.78rem",
            color: "#f8fafc",
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 40,
            maxWidth: "320px",
            boxShadow: "0 10px 25px -5px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              V2V Visual Legend
            </span>
            <button
              type="button"
              onClick={() => setShowV2VLegend(false)}
              aria-label="Dismiss V2V Legend Panel"
              style={{
                background: "none",
                border: "none",
                color: "#94a3b8",
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

          <div style={{ marginTop: "10px", paddingTop: "8px", borderTop: "1px solid rgba(255,255,255,0.1)", fontSize: "0.75rem", color: "#94a3b8" }}>
            <div>Channel State: <span style={{ fontWeight: 600, color: communicationSnapshot?.networkState?.channelState === "bad" ? "#ef4444" : communicationSnapshot?.networkState?.channelState === "good" ? "#10b981" : "#94a3b8" }}>{communicationSnapshot?.networkState?.channelState ? communicationSnapshot.networkState.channelState.toUpperCase() : "Unavailable"}</span></div>
            <div>Packet Delivery Ratio: <span style={{ fontWeight: 600, color: "#38bdf8" }}>{communicationSnapshot?.networkState?.packetDeliveryRatio !== null && communicationSnapshot?.networkState?.packetDeliveryRatio !== undefined ? `${(communicationSnapshot.networkState.packetDeliveryRatio * 100).toFixed(1)}%` : "Unavailable"}</span></div>
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
          right: "24px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: "8px",
          zIndex: 35,
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
            backgroundColor: routeOptions.showActiveRoutes ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: routeOptions.showPlannedRoutes ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: routeOptions.showCandidateRoutes ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: routeOptions.showRerouteMarkers ? "#0284c7" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            color: "#cbd5e1",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            backgroundColor: showRouteLegend ? "#0369a1" : "rgba(15, 23, 42, 0.8)",
            color: "#ffffff",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "6px",
            padding: "5px 10px",
            fontSize: "0.78rem",
            fontFamily: "Space Grotesk, sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
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
            top: "145px",
            right: "24px",
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255, 255, 255, 0.15)",
            borderRadius: "8px",
            padding: "12px 16px",
            fontSize: "0.78rem",
            color: "#f8fafc",
            fontFamily: "Space Grotesk, sans-serif",
            zIndex: 40,
            maxWidth: "320px",
            boxShadow: "0 10px 25px -5px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Route Visual Legend
            </span>
            <button
              type="button"
              onClick={() => setShowRouteLegend(false)}
              aria-label="Dismiss Route Legend Panel"
              style={{
                background: "none",
                border: "none",
                color: "#94a3b8",
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
          bottom: "24px",
          left: "24px",
          backgroundColor: "rgba(11, 15, 25, 0.8)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: "8px",
          padding: "8px 14px",
          fontSize: "0.75rem",
          color: "#94a3b8",
          display: "flex",
          gap: "16px",
          alignItems: "center",
          fontFamily: "Space Grotesk, sans-serif",
          zIndex: 30,
          boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
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

      {/* City Boot Overlay */}
      {!cityLoaded && !isLoading && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 100,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "18px",
            background: "#0b0e1a",
            color: "#fff",
            fontFamily: "system-ui, -apple-system, sans-serif",
          }}
        >
          <div style={{ fontSize: "28px", fontWeight: "700", letterSpacing: "0.3em" }}>
            LUXEMBOURG
          </div>
          <div
            style={{
              fontSize: "12px",
              color: "#38bdf8",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
            }}
          >
            Adaptive Multi-Agent Path Planning
          </div>
          <div
            style={{
              width: "280px",
              height: "4px",
              borderRadius: "4px",
              background: "rgba(255,255,255,0.12)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: "60%",
                height: "100%",
                background: "linear-gradient(90deg, #0284c7, #38bdf8)",
                borderRadius: "4px",
                animation: "pulse 1.5s infinite",
              }}
            />
          </div>
          <div style={{ color: "#94a3b8", fontSize: "13px" }}>{cityLoadingState}</div>
        </div>
      )}

      {/* Game City HUD: Speedometer & Street Name */}
      {cityLoaded && (
        <>
          {/* Top-Left Street Name Badge */}
          <div
            style={{
              position: "absolute",
              top: "20px",
              left: "24px",
              zIndex: 30,
              display: "flex",
              flexDirection: "column",
              gap: "4px",
              background: "rgba(11, 15, 25, 0.75)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: "12px",
              padding: "10px 18px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
            }}
          >
            <div
              style={{
                fontSize: "10px",
                fontWeight: "700",
                color: "#38bdf8",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              Current Arterial Corridor
            </div>
            <div
              style={{
                fontSize: "18px",
                fontWeight: "700",
                color: "#f8fafc",
                letterSpacing: "0.02em",
              }}
            >
              {currentStreetName}
            </div>
            <div style={{ fontSize: "11px", color: "#94a3b8", display: "flex", gap: "10px" }}>
              <span>Lat: 49.6125°N</span>
              <span>Lon: 6.1300°E</span>
              <span style={{ color: "#10b981" }}>OSM Real Network</span>
            </div>
          </div>

          {/* Top-Right Quick Environment & Camera Controls */}
          <div
            style={{
              position: "absolute",
              top: "20px",
              right: "24px",
              zIndex: 30,
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "rgba(11, 15, 25, 0.75)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: "12px",
              padding: "8px 14px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
            }}
          >
            {/* Camera Mode Selector */}
            <button
              type="button"
              onClick={() =>
                setCameraMode((prev) => (prev === "chase" ? "bird" : prev === "bird" ? "free" : "chase"))
              }
              style={{
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.15)",
                borderRadius: "8px",
                padding: "6px 12px",
                color: "#f8fafc",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
              title="Switch Camera View (C)"
            >
              <span style={{ color: "#38bdf8" }}>📷</span>
              {cameraMode === "chase" ? "Chase Cam" : cameraMode === "bird" ? "Bird Eye" : "Free View"}
            </button>

            {/* Time of Day Toggle */}
            <button
              type="button"
              onClick={() => {
                const nextHour = timeOfDayHours < 12 ? 14 : timeOfDayHours < 19 ? 20.4 : 6.5;
                setTimeOfDayHours(nextHour);
              }}
              style={{
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.15)",
                borderRadius: "8px",
                padding: "6px 12px",
                color: "#f8fafc",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
              title="Cycle Day/Night Illumination"
            >
              {timeOfDayHours > 18 || timeOfDayHours < 6 ? "🌙 Night" : "☀️ Day"}
            </button>

            {/* Rain Weather Toggle */}
            <button
              type="button"
              onClick={() => setIsRaining((prev) => !prev)}
              style={{
                background: isRaining ? "rgba(56, 189, 248, 0.25)" : "rgba(255,255,255,0.08)",
                border: isRaining ? "1px solid #38bdf8" : "1px solid rgba(255,255,255,0.15)",
                borderRadius: "8px",
                padding: "6px 12px",
                color: isRaining ? "#38bdf8" : "#f8fafc",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
              title="Toggle Atmospheric Rain"
            >
              🌧️ Rain
            </button>

            {/* Big Map Button (M) */}
            <button
              type="button"
              onClick={() => {
                if (bigmapRef.current) {
                  bigmapRef.current.toggle();
                  setIsMapOpen(bigmapRef.current.isOpen());
                }
              }}
              style={{
                background: isMapOpen ? "rgba(56, 189, 248, 0.25)" : "rgba(255,255,255,0.08)",
                border: isMapOpen ? "1px solid #38bdf8" : "1px solid rgba(255,255,255,0.15)",
                borderRadius: "8px",
                padding: "6px 12px",
                color: "#f8fafc",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
              title="Fullscreen City Map (M)"
            >
              🗺️ Map (M)
            </button>

            {/* Hero Drive Mode Toggle */}
            <button
              type="button"
              onClick={() => setIsHeroDriveMode((prev) => !prev)}
              style={{
                background: isHeroDriveMode ? "rgba(16, 185, 129, 0.25)" : "rgba(255,255,255,0.08)",
                border: isHeroDriveMode ? "1px solid #10b981" : "1px solid rgba(255,255,255,0.15)",
                borderRadius: "8px",
                padding: "6px 12px",
                color: isHeroDriveMode ? "#10b981" : "#f8fafc",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
              title="WASD Drivable Car Mode"
            >
              🎮 {isHeroDriveMode ? "Hero Driving" : "Fleet View"}
            </button>
          </div>

          {/* Bottom-Right Speedometer */}
          <div
            style={{
              position: "absolute",
              bottom: "96px",
              right: "24px",
              zIndex: 30,
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              pointerEvents: "none",
            }}
          >
            {/* Digital Speedometer Gauge */}
            <div
              style={{
                background: "rgba(11, 15, 25, 0.8)",
                backdropFilter: "blur(12px)",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "14px",
                padding: "12px 20px",
                textAlign: "right",
                boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
                marginBottom: "12px",
              }}
            >
              <div
                style={{
                  fontSize: "38px",
                  fontWeight: "800",
                  lineHeight: 1,
                  color: "#f8fafc",
                  fontVariantNumeric: "tabular-nums",
                  letterSpacing: "-0.03em",
                }}
              >
                {speedKmh}
              </div>
              <div
                style={{
                  fontSize: "11px",
                  fontWeight: "700",
                  letterSpacing: "0.15em",
                  color: "#38bdf8",
                  marginTop: "4px",
                }}
              >
                KM/H
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
