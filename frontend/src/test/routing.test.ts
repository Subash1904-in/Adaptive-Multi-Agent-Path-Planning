import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { RoadNetworkGeometry } from "../types/graph";
import type {
  ActiveRoute,
  CandidateRoute,
  PlannedRoute,
  RerouteEvent,
} from "../types/routing";
import type { ScenarioDefinition, VehicleState } from "../types/simulation";
import {
  computeRouteDistance,
  createRouteSubsystemSnapshot,
  deduplicateRerouteEvents,
  extractActiveRoute,
  extractCandidateRoutes,
  extractPlannedRoute,
  extractRerouteEvent,
  resolveRouteWorldPoints,
  ROUTE_LINE_ELEVATION_M,
} from "../features/scene3d/routeAdapter";
import { RouteOverlayManager } from "../features/scene3d/routeOverlay";
import { SimulationHistoryBuffer } from "../features/playback/historyBuffer";

const mockGeometry: RoadNetworkGeometry = {
  nodes: [
    { id: "n0", x: 0, y: 0 },
    { id: "n1", x: 100, y: 0 },
    { id: "n2", x: 100, y: 100 },
    { id: "n3", x: 0, y: 100 },
  ],
  edges: [
    { id: "e01", start_node_id: "n0", end_node_id: "n1", length_m: 100, speed_limit_mps: 15, lanes: 1 },
    { id: "e12", start_node_id: "n1", end_node_id: "n2", length_m: 100, speed_limit_mps: 15, lanes: 1 },
    { id: "e23", start_node_id: "n2", end_node_id: "n3", length_m: 100, speed_limit_mps: 15, lanes: 1 },
    { id: "e03", start_node_id: "n0", end_node_id: "n3", length_m: 100, speed_limit_mps: 15, lanes: 1 },
  ],
};

const mockScenario: ScenarioDefinition = {
  metadata: { id: "test_scn", name: "Test Scenario", description: "", version: "1.0", author: "AMAPP" },
  road_network: { source_type: "synthetic_grid" },
  vehicles: [
    {
      vehicle_id: "veh_01",
      start_node_id: "n0",
      destination_node_id: "n2",
    },
  ],
  time_step_s: 0.1,
};

describe("Adaptive Route Adapter (routeAdapter.ts)", () => {
  it("resolves route world coordinates at correct elevation without z-fighting", () => {
    const points = resolveRouteWorldPoints(["n0", "n1", "n2"], mockGeometry);
    expect(points.length).toBe(3);
    // Standard mapping: X = simX, Y = elevation (0.12m), Z = -simY
    expect(points[0]).toEqual({ x: 0, y: ROUTE_LINE_ELEVATION_M, z: -0 });
    expect(points[1]).toEqual({ x: 100, y: ROUTE_LINE_ELEVATION_M, z: -0 });
    expect(points[2]).toEqual({ x: 100, y: ROUTE_LINE_ELEVATION_M, z: -100 });
  });

  it("safely handles missing or disconnected nodes without crashing", () => {
    // Missing node "n_missing"
    const points = resolveRouteWorldPoints(["n0", "n_missing", "n2"], mockGeometry);
    expect(points.length).toBe(2);
    expect(points[0].x).toBe(0);
    expect(points[1].x).toBe(100);

    // Empty or single-node sequence
    expect(resolveRouteWorldPoints([], mockGeometry)).toEqual([]);
    expect(resolveRouteWorldPoints(["n0"], mockGeometry)).toEqual([]);
    expect(resolveRouteWorldPoints(["n0", "n1"], null)).toEqual([]);
  });

  it("computes exact route distance using road network edge lengths", () => {
    const dist = computeRouteDistance(["n0", "n1", "n2"], mockGeometry);
    expect(dist).toBe(200); // 100m + 100m
  });

  it("falls back to Euclidean node distance when edge is unmapped", () => {
    const dist = computeRouteDistance(["n0", "n2"], mockGeometry);
    // hypot(100, 100) = 141.42
    expect(dist).toBeCloseTo(141.42, 1);
  });

  it("extracts planned baseline route from scenario definition", () => {
    const planned = extractPlannedRoute("veh_01", mockScenario, mockGeometry);
    expect(planned).not.toBeNull();
    expect(planned?.vehicleId).toBe("veh_01");
    expect(planned?.nodeIds).toEqual(["n0", "n2"]);
    expect(planned?.worldPoints.length).toBe(2);
  });

  it("extracts active route and strictly preserves authoritative backend remaining distance", () => {
    const vState: VehicleState = {
      vehicle_id: "veh_01",
      position: { x: 50, y: 0 },
      speed_mps: 10,
      heading_rad: 0,
      lifecycle_state: "en_route",
      route: ["n0", "n1", "n2"],
      remaining_route_distance_m: 150.5,
      route_id: "route_upper_01",
    };

    const active = extractActiveRoute("veh_01", vState, mockScenario, mockGeometry);
    expect(active).not.toBeNull();
    expect(active?.routeId).toBe("route_upper_01");
    expect(active?.nodeIds).toEqual(["n0", "n1", "n2"]);
    expect(active?.remainingDistanceM).toBe(150.5);
    expect(active?.totalDistanceM).toBe(200);
  });

  it("returns null for remaining distance when backend does not provide it (no fabrication)", () => {
    const vState: VehicleState = {
      vehicle_id: "veh_01",
      position: { x: 0, y: 0 },
      speed_mps: 0,
      heading_rad: 0,
      lifecycle_state: "ready",
      route: ["n0", "n1"],
      remaining_route_distance_m: undefined, // Absent from backend
    };

    const active = extractActiveRoute("veh_01", vState, mockScenario, mockGeometry);
    expect(active?.remainingDistanceM).toBeNull(); // Strict zero fabrication
  });

  it("extracts reroute event and preserves authoritative backend reason", () => {
    const rawDecision = {
      decision_type: "reroute_accepted",
      vehicle_id: "veh_01",
      timestamp_s: 12.5,
      current_cost: 45.2,
      candidate_cost: 32.1,
      cost_improvement: 13.1,
      old_route_id: "route_orig",
      new_route_id: "route_rerouted_2",
      candidate_node_ids: ["n0", "n3", "n2"],
      candidate_edge_ids: ["e03", "e23"],
      reason: "Avoided road closure on e01 with 29.0% cost improvement",
    };

    const ev = extractRerouteEvent(rawDecision, 125, 12.5, mockGeometry);
    expect(ev).not.toBeNull();
    expect(ev?.vehicleId).toBe("veh_01");
    expect(ev?.tick).toBe(125);
    expect(ev?.isAccepted).toBe(true);
    expect(ev?.currentCost).toBe(45.2);
    expect(ev?.candidateCost).toBe(32.1);
    expect(ev?.costImprovement).toBe(13.1);
    expect(ev?.reason).toBe("Avoided road closure on e01 with 29.0% cost improvement");
    expect(ev?.hasExplicitReason).toBe(true);
    expect(ev?.candidateNodeIds).toEqual(["n0", "n3", "n2"]);
  });

  it("uses neutral fallback phrasing when backend does not provide explicit reason", () => {
    const rawDecision = {
      decision_type: "insufficient_benefit",
      vehicle_id: "veh_01",
      timestamp_s: 5.0,
      current_cost: 20.0,
      candidate_cost: 19.5,
      cost_improvement: 0.5,
      reason: "", // Empty reason
    };

    const ev = extractRerouteEvent(rawDecision, 50, 5.0, mockGeometry);
    expect(ev?.reason).toBe("Route updated at tick 50");
    expect(ev?.hasExplicitReason).toBe(false);
  });

  it("extracts candidate alternative paths only when supplied by backend (zero fabrication)", () => {
    // When candidate nodes are supplied
    const rawWithCandidates = {
      vehicle_id: "veh_01",
      decision_type: "reroute_accepted",
      candidate_node_ids: ["n0", "n3", "n2"],
      candidate_edge_ids: ["e03", "e23"],
      candidate_cost: 32.1,
      cost_improvement: 13.1,
    };
    const cands = extractCandidateRoutes(rawWithCandidates, 125, mockGeometry);
    expect(cands.length).toBe(1);
    expect(cands[0].nodeIds).toEqual(["n0", "n3", "n2"]);
    expect(cands[0].objectiveCost).toBe(32.1);
    expect(cands[0].costImprovement).toBe(13.1);
    expect(cands[0].worldPoints.length).toBe(3);

    // When candidate nodes are empty: returns empty array (zero fabrication)
    const rawEmpty = {
      vehicle_id: "veh_01",
      decision_type: "no_change",
      candidate_node_ids: [],
    };
    expect(extractCandidateRoutes(rawEmpty, 125, mockGeometry)).toEqual([]);
  });

  it("deduplicates overlapping reroute events and bounds history", () => {
    const ev1: RerouteEvent = {
      id: "ev1",
      vehicleId: "veh_01",
      tick: 10,
      simulationTimeS: 1.0,
      decisionType: "reroute_accepted",
      isAccepted: true,
      oldRouteId: "r1",
      newRouteId: "r2",
      currentCost: 30,
      candidateCost: 20,
      costImprovement: 10,
      reason: "Avoided closure",
      hasExplicitReason: true,
      candidateNodeIds: ["n0", "n3"],
      candidateEdgeIds: ["e03"],
      markerPosition: null,
    };
    const ev2: RerouteEvent = { ...ev1, id: "ev2", tick: 20, simulationTimeS: 2.0 };
    const evDuplicate: RerouteEvent = { ...ev1, reason: "Duplicate delivery" };

    const deduplicated = deduplicateRerouteEvents([ev1], [evDuplicate, ev2], 100);
    expect(deduplicated.length).toBe(2);
    expect(deduplicated.map((e) => e.id)).toEqual(["ev1", "ev2"]);

    // Bounded limit test
    const bounded = deduplicateRerouteEvents([ev1, ev2], [], 1);
    expect(bounded.length).toBe(1);
    expect(bounded[0].id).toBe("ev2"); // Retains latest
  });
});

describe("Three.js Route Overlay Manager (routeOverlay.ts)", () => {
  it("initializes groups and reusable materials cleanly", () => {
    const manager = new RouteOverlayManager();
    expect(manager.rootGroup).toBeInstanceOf(THREE.Group);
    expect(manager.activeRouteGroup).toBeInstanceOf(THREE.Group);
    expect(manager.plannedRouteGroup).toBeInstanceOf(THREE.Group);
    expect(manager.candidatesGroup).toBeInstanceOf(THREE.Group);
    expect(manager.markersGroup).toBeInstanceOf(THREE.Group);

    manager.dispose();
  });

  it("renders active, planned, and candidate lines into their respective groups", () => {
    const manager = new RouteOverlayManager();
    const activeRoute: ActiveRoute = {
      vehicleId: "veh_01",
      routeId: "r_active",
      nodeIds: ["n0", "n1"],
      edgeIds: ["e01"],
      worldPoints: [
        { x: 0, y: 0.12, z: 0 },
        { x: 100, y: 0.12, z: 0 },
      ],
      totalDistanceM: 100,
      remainingDistanceM: 100,
      currentEdgeId: "e01",
      currentNodeId: "n0",
      isRerouted: false,
    };

    const plannedRoute: PlannedRoute = {
      vehicleId: "veh_01",
      routeId: "r_planned",
      nodeIds: ["n0", "n3", "n2"],
      edgeIds: [],
      worldPoints: [
        { x: 0, y: 0.11, z: 0 },
        { x: 0, y: 0.11, z: -100 },
        { x: 100, y: 0.11, z: -100 },
      ],
      totalDistanceM: 200,
    };

    const candidateRoute: CandidateRoute = {
      id: "cand_1",
      vehicleId: "veh_01",
      nodeIds: ["n0", "n1", "n2"],
      edgeIds: [],
      worldPoints: [
        { x: 0, y: 0.14, z: 0 },
        { x: 100, y: 0.14, z: -100 },
      ],
      objectiveCost: 25,
      costImprovement: 5,
      isAccepted: false,
      evaluationTick: 10,
    };

    const rerouteEv: RerouteEvent = {
      id: "reroute_marker_1",
      vehicleId: "veh_01",
      tick: 10,
      simulationTimeS: 1.0,
      decisionType: "reroute_accepted",
      isAccepted: true,
      oldRouteId: "r_planned",
      newRouteId: "r_active",
      currentCost: 30,
      candidateCost: 25,
      costImprovement: 5,
      reason: "Faster path",
      hasExplicitReason: true,
      candidateNodeIds: ["n0", "n1"],
      candidateEdgeIds: [],
      markerPosition: { x: 50, y: 0.5, z: 0 },
    };

    const snapshot = createRouteSubsystemSnapshot({
      tick: 10,
      timestampS: 1.0,
      activeRoutes: new Map([["veh_01", activeRoute]]),
      plannedRoutes: new Map([["veh_01", plannedRoute]]),
      candidateRoutes: new Map([["veh_01", [candidateRoute]]]),
      rerouteEvents: [rerouteEv],
    });

    manager.update(snapshot, "veh_01", null);

    // Verify Three.js scene graph objects
    expect(manager.activeRouteGroup.children.length).toBe(1);
    expect(manager.plannedRouteGroup.children.length).toBe(1);
    expect(manager.candidatesGroup.children.length).toBe(1);
    expect(manager.markersGroup.children.length).toBe(1);

    // Test candidate path inspection highlighting
    manager.update(snapshot, "veh_01", "cand_1");
    const candMesh = manager.candidatesGroup.children[0] as THREE.Line;
    expect(candMesh).toBeDefined();

    manager.dispose();
    expect(manager.activeRouteGroup.children.length).toBe(0);
  });

  it("toggles layer visibility through overlay options", () => {
    const manager = new RouteOverlayManager();
    expect(manager.activeRouteGroup.visible).toBe(true);

    manager.setOptions({ showActiveRoutes: false, showRerouteMarkers: false });
    expect(manager.activeRouteGroup.visible).toBe(false);
    expect(manager.markersGroup.visible).toBe(false);
    expect(manager.plannedRouteGroup.visible).toBe(true);

    manager.dispose();
  });

  it("freezes presentation marker animation on pause and scales with playback speed", () => {
    const manager = new RouteOverlayManager();
    const rerouteEv: RerouteEvent = {
      id: "marker_anim",
      vehicleId: "veh_01",
      tick: 5,
      simulationTimeS: 0.5,
      decisionType: "reroute_accepted",
      isAccepted: true,
      oldRouteId: null,
      newRouteId: null,
      currentCost: null,
      candidateCost: null,
      costImprovement: null,
      reason: "Tick",
      hasExplicitReason: false,
      candidateNodeIds: [],
      candidateEdgeIds: [],
      markerPosition: { x: 10, y: 0.5, z: 10 },
    };

    const snap = createRouteSubsystemSnapshot({
      tick: 5,
      timestampS: 0.5,
      rerouteEvents: [rerouteEv],
    });
    manager.update(snap, null, null);

    const marker = manager.markersGroup.children[0] as THREE.Mesh;
    const initialRot = marker.rotation.y;

    // Normal tick advances rotation
    manager.tick(0.1, 1, false);
    expect(marker.rotation.y).toBeGreaterThan(initialRot);

    // Paused tick freezes rotation
    const pausedRot = marker.rotation.y;
    manager.tick(0.1, 1, true);
    expect(marker.rotation.y).toBe(pausedRot);

    // Higher playback speed rotates faster
    manager.tick(0.1, 2, false);
    expect(marker.rotation.y).toBeGreaterThan(pausedRot);

    manager.dispose();
  });
});

describe("History Buffer Route Integration (historyBuffer.ts)", () => {
  it("deep-clones route subsystem snapshot to guarantee historical immutability", () => {
    const buffer = new SimulationHistoryBuffer(10);
    const activeRoute: ActiveRoute = {
      vehicleId: "veh_01",
      routeId: "route_tick_5",
      nodeIds: ["n0", "n1"],
      edgeIds: ["e01"],
      worldPoints: [{ x: 0, y: 0.12, z: 0 }],
      totalDistanceM: 100,
      remainingDistanceM: 80,
      currentEdgeId: "e01",
      currentNodeId: "n0",
      isRerouted: false,
    };

    const routingSnap = createRouteSubsystemSnapshot({
      tick: 5,
      timestampS: 0.5,
      activeRoutes: new Map([["veh_01", activeRoute]]),
      rerouteEvents: [],
    });

    buffer.addSnapshot({
      tick: 5,
      simulation_time_s: 0.5,
      timestamp_ms: 1000,
      vehicles: new Map(),
      pedestrians: new Map(),
      signals: new Map(),
      routing: routingSnap,
    });

    // Mutate live routingSnap after buffering
    activeRoute.nodeIds.push("n2");
    activeRoute.remainingDistanceM = 0;
    routingSnap.activeRoutes.delete("veh_01");

    // Retrieve historical snapshot from buffer
    const buffered = buffer.getSnapshot(5);
    expect(buffered).toBeDefined();
    expect(buffered?.routing).toBeDefined();
    const histActive = buffered?.routing?.activeRoutes.get("veh_01");

    expect(histActive).toBeDefined();
    expect(histActive?.nodeIds).toEqual(["n0", "n1"]); // Preserved without "n2"
    expect(histActive?.remainingDistanceM).toBe(80); // Preserved without mutation
  });
});
