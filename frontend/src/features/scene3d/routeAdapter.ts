/**
 * Data adapter and transformation utilities for adaptive routing visualization.
 * Transforms backend routing telemetry, scenario definitions, and rerouting decisions
 * into normalized 3D path coordinates and decision explanation models.
 */

import type { RoadNetworkGeometry } from "../../types/graph";
import type {
  ActiveRoute,
  CandidateRoute,
  PlannedRoute,
  RerouteDecisionClassification,
  RerouteEvent,
  RoutePoint3D,
  RouteSubsystemSnapshot,
} from "../../types/routing";
import type { ScenarioDefinition, VehicleScenarioDefinition, VehicleState } from "../../types/simulation";
import { simToWorldCoordinates } from "./geometry";

export const ROUTE_LINE_ELEVATION_M = 0.12; // Above asphalt (0.0), road markings (0.035), sidewalks (0.06), V2V range (0.08)
export const REROUTE_MARKER_ELEVATION_M = 0.5; // Elevated diamond marker

/**
 * Resolve ordered node IDs into 3D world coordinates using the road network geometry.
 * Safely handles missing nodes, disconnected graphs, or empty sequences without crashing.
 */
export function resolveRouteWorldPoints(
  nodeIds: string[],
  geometry?: RoadNetworkGeometry | null,
  elevation = ROUTE_LINE_ELEVATION_M
): RoutePoint3D[] {
  if (!nodeIds || !Array.isArray(nodeIds) || nodeIds.length < 2 || !geometry || !geometry.nodes) {
    return [];
  }

  const nodeMap = new Map<string, { x: number; y: number }>();
  for (const n of geometry.nodes) {
    if (n && typeof n.id === "string" && Number.isFinite(n.x) && Number.isFinite(n.y)) {
      nodeMap.set(n.id, { x: n.x, y: n.y });
    }
  }

  const points: RoutePoint3D[] = [];
  for (const nodeId of nodeIds) {
    const node = nodeMap.get(nodeId);
    if (node) {
      const p = simToWorldCoordinates(node.x, node.y, elevation);
      points.push({ x: p.x, y: p.y, z: p.z });
    }
  }

  return points.length >= 2 ? points : [];
}

/**
 * Deterministically compute total distance along an ordered sequence of node IDs.
 * Uses exact road edge lengths where available, falling back to Euclidean distance between nodes.
 */
export function computeRouteDistance(
  nodeIds: string[],
  geometry?: RoadNetworkGeometry | null
): number | null {
  if (!nodeIds || nodeIds.length < 2 || !geometry) {
    return null;
  }

  const nodeMap = new Map<string, { x: number; y: number }>();
  for (const n of geometry.nodes) {
    if (n && typeof n.id === "string") {
      nodeMap.set(n.id, { x: n.x, y: n.y });
    }
  }

  const edgeMap = new Map<string, number>(); // "u->v" => length_m
  if (geometry.edges) {
    for (const e of geometry.edges) {
      if (e && e.start_node_id && e.end_node_id && Number.isFinite(e.length_m)) {
        edgeMap.set(`${e.start_node_id}->${e.end_node_id}`, e.length_m);
      }
    }
  }

  let totalDist = 0;
  for (let i = 0; i < nodeIds.length - 1; i++) {
    const u = nodeIds[i];
    const v = nodeIds[i + 1];
    const edgeLen = edgeMap.get(`${u}->${v}`);
    if (edgeLen !== undefined) {
      totalDist += edgeLen;
    } else {
      const uNode = nodeMap.get(u);
      const vNode = nodeMap.get(v);
      if (uNode && vNode) {
        totalDist += Math.hypot(vNode.x - uNode.x, vNode.y - uNode.y);
      }
    }
  }

  return totalDist > 0 ? Number(totalDist.toFixed(2)) : null;
}

/**
 * Extract active route for a vehicle from vehicle state, scenario definition, and geometry.
 */
export function extractActiveRoute(
  vehicleId: string,
  vehicleState: VehicleState | null | undefined,
  scenario: ScenarioDefinition | null | undefined,
  geometry: RoadNetworkGeometry | null | undefined,
  currentRouteId?: string | null
): ActiveRoute | null {
  if (!vehicleId) return null;

  // 1. Determine node sequence from vehicleState.route if present
  let nodeIds: string[] = [];
  if (vehicleState?.route && Array.isArray(vehicleState.route) && vehicleState.route.length >= 2) {
    nodeIds = [...vehicleState.route];
  } else if (scenario?.vehicles) {
    const vDef = scenario.vehicles.find((v: VehicleScenarioDefinition) => v.vehicle_id === vehicleId);
    if (vDef && vDef.start_node_id && vDef.destination_node_id) {
      nodeIds = [vDef.start_node_id, vDef.destination_node_id];
    }
  }

  if (nodeIds.length < 2) {
    return null;
  }

  const worldPoints = resolveRouteWorldPoints(nodeIds, geometry, ROUTE_LINE_ELEVATION_M);
  const routeId = currentRouteId || (vehicleState as Record<string, unknown> | null | undefined)?.route_id as string || `${vehicleId}_route`;
  const totalDist = computeRouteDistance(nodeIds, geometry);

  // Authoritative remaining distance: strictly read from vehicleState if provided
  const rawRemDist = (vehicleState as Record<string, unknown> | null | undefined)?.remaining_route_distance_m;
  const remainingDistanceM =
    typeof rawRemDist === "number" && Number.isFinite(rawRemDist) && rawRemDist >= 0
      ? Number(rawRemDist.toFixed(2))
      : null;

  const currentEdgeId = vehicleState?.current_edge_id || null;
  const currentNodeId = (vehicleState as Record<string, unknown> | null | undefined)?.current_node_id as string || null;

  return {
    vehicleId,
    routeId: String(routeId),
    nodeIds,
    edgeIds: [],
    worldPoints,
    totalDistanceM: totalDist,
    remainingDistanceM,
    currentEdgeId,
    currentNodeId,
    isRerouted: Boolean(currentRouteId && currentRouteId.includes("reroute")),
  };
}

/**
 * Extract initial planned route for a vehicle from the scenario definition.
 */
export function extractPlannedRoute(
  vehicleId: string,
  scenario: ScenarioDefinition | null | undefined,
  geometry: RoadNetworkGeometry | null | undefined,
  initialNodeIds?: string[]
): PlannedRoute | null {
  if (!vehicleId) return null;

  let nodeIds: string[] = [];
  if (initialNodeIds && initialNodeIds.length >= 2) {
    nodeIds = [...initialNodeIds];
  } else if (scenario?.vehicles) {
    const vDef = scenario.vehicles.find((v: VehicleScenarioDefinition) => v.vehicle_id === vehicleId);
    if (vDef && vDef.start_node_id && vDef.destination_node_id) {
      nodeIds = [vDef.start_node_id, vDef.destination_node_id];
    }
  }

  if (nodeIds.length < 2) return null;

  const worldPoints = resolveRouteWorldPoints(nodeIds, geometry, ROUTE_LINE_ELEVATION_M - 0.01);
  const totalDist = computeRouteDistance(nodeIds, geometry);

  return {
    vehicleId,
    routeId: `${vehicleId}_initial_planned`,
    nodeIds,
    edgeIds: [],
    worldPoints,
    totalDistanceM: totalDist,
  };
}

/**
 * Ingest and normalize a backend reroute decision dictionary into a validated RerouteEvent.
 * Distinguishes explicit backend reasons from neutral fallback text. Never invents causes.
 */
export function extractRerouteEvent(
  rawDecision: Record<string, unknown>,
  tick: number,
  simulationTimeS: number,
  geometry?: RoadNetworkGeometry | null,
  vehiclePositions?: Map<string, { x: number; y: number }>
): RerouteEvent | null {
  if (!rawDecision || typeof rawDecision !== "object") return null;

  const vehicleId = String(rawDecision.vehicle_id || "");
  if (!vehicleId) return null;

  const decisionType = String(
    rawDecision.decision_type || "unknown"
  ) as RerouteDecisionClassification;
  const isAccepted = decisionType === "reroute_accepted";

  const oldRouteId = rawDecision.old_route_id ? String(rawDecision.old_route_id) : null;
  const newRouteId = rawDecision.new_route_id ? String(rawDecision.new_route_id) : null;

  const rawCurrCost = rawDecision.current_cost;
  const currentCost =
    typeof rawCurrCost === "number" && Number.isFinite(rawCurrCost)
      ? Number(rawCurrCost.toFixed(4))
      : null;

  const rawCandCost = rawDecision.candidate_cost;
  const candidateCost =
    typeof rawCandCost === "number" && Number.isFinite(rawCandCost)
      ? Number(rawCandCost.toFixed(4))
      : null;

  const rawImprovement = rawDecision.cost_improvement;
  const costImprovement =
    typeof rawImprovement === "number" && Number.isFinite(rawImprovement)
      ? Number(rawImprovement.toFixed(4))
      : null;

  const candidateNodeIds = Array.isArray(rawDecision.candidate_node_ids)
    ? rawDecision.candidate_node_ids.map(String)
    : [];
  const candidateEdgeIds = Array.isArray(rawDecision.candidate_edge_ids)
    ? rawDecision.candidate_edge_ids.map(String)
    : [];

  // Reason extraction: strictly use backend reason if provided; otherwise neutral phrasing
  const rawReason = typeof rawDecision.reason === "string" ? rawDecision.reason.trim() : "";
  const hasExplicitReason = rawReason.length > 0;
  const reason = hasExplicitReason ? rawReason : `Route updated at tick ${tick}`;

  // Canonical event ID
  const eventId = `reroute_${vehicleId}_t${tick}_${oldRouteId || "orig"}_${newRouteId || "alt"}`;

  // Marker 3D position
  let markerPos: RoutePoint3D | null = null;
  const vPos = vehiclePositions?.get(vehicleId);
  if (vPos && Number.isFinite(vPos.x) && Number.isFinite(vPos.y)) {
    const p = simToWorldCoordinates(vPos.x, vPos.y, REROUTE_MARKER_ELEVATION_M);
    markerPos = { x: p.x, y: p.y, z: p.z };
  } else if (candidateNodeIds.length > 0 && geometry?.nodes) {
    const firstNode = geometry.nodes.find((n) => n.id === candidateNodeIds[0]);
    if (firstNode) {
      const p = simToWorldCoordinates(firstNode.x, firstNode.y, REROUTE_MARKER_ELEVATION_M);
      markerPos = { x: p.x, y: p.y, z: p.z };
    }
  }

  const diagnostics =
    rawDecision.diagnostics && typeof rawDecision.diagnostics === "object"
      ? (rawDecision.diagnostics as Record<string, unknown>)
      : undefined;

  return {
    id: eventId,
    vehicleId,
    tick,
    simulationTimeS,
    decisionType,
    isAccepted,
    oldRouteId,
    newRouteId,
    currentCost,
    candidateCost,
    costImprovement,
    reason,
    hasExplicitReason,
    candidateNodeIds,
    candidateEdgeIds,
    markerPosition: markerPos,
    diagnostics,
  };
}

/**
 * Extract evaluated candidate alternative paths from a rerouting decision.
 * Returns empty array if no alternative candidates were evaluated by the backend.
 * Zero fabrication!
 */
export function extractCandidateRoutes(
  rawDecision: Record<string, unknown>,
  tick: number,
  geometry?: RoadNetworkGeometry | null
): CandidateRoute[] {
  if (!rawDecision || typeof rawDecision !== "object") return [];

  const vehicleId = String(rawDecision.vehicle_id || "");
  const candidateNodeIds = Array.isArray(rawDecision.candidate_node_ids)
    ? rawDecision.candidate_node_ids.map(String)
    : [];

  if (!vehicleId || candidateNodeIds.length < 2) {
    return [];
  }

  const candidateEdgeIds = Array.isArray(rawDecision.candidate_edge_ids)
    ? rawDecision.candidate_edge_ids.map(String)
    : [];

  const rawCandCost = rawDecision.candidate_cost;
  const objectiveCost =
    typeof rawCandCost === "number" && Number.isFinite(rawCandCost)
      ? Number(rawCandCost.toFixed(4))
      : null;

  const rawImprovement = rawDecision.cost_improvement;
  const costImprovement =
    typeof rawImprovement === "number" && Number.isFinite(rawImprovement)
      ? Number(rawImprovement.toFixed(4))
      : null;

  const isAccepted = rawDecision.decision_type === "reroute_accepted";
  const worldPoints = resolveRouteWorldPoints(
    candidateNodeIds,
    geometry,
    ROUTE_LINE_ELEVATION_M + 0.02
  );

  return [
    {
      id: `cand_${vehicleId}_t${tick}_1`,
      vehicleId,
      nodeIds: candidateNodeIds,
      edgeIds: candidateEdgeIds,
      worldPoints,
      objectiveCost,
      costImprovement,
      isAccepted,
      evaluationTick: tick,
    },
  ];
}

/**
 * Deduplicate and sort rerouting events with a bounded history limit.
 */
export function deduplicateRerouteEvents(
  existingEvents: RerouteEvent[],
  newEvents: RerouteEvent[],
  maxEvents = 100
): RerouteEvent[] {
  const map = new Map<string, RerouteEvent>();

  for (const ev of existingEvents) {
    if (ev && ev.id) map.set(ev.id, ev);
  }
  for (const ev of newEvents) {
    if (ev && ev.id) map.set(ev.id, ev);
  }

  const sorted = Array.from(map.values()).sort((a, b) => {
    if (a.tick !== b.tick) return a.tick - b.tick;
    if (a.simulationTimeS !== b.simulationTimeS) return a.simulationTimeS - b.simulationTimeS;
    return a.id.localeCompare(b.id);
  });

  // Retain only latest maxEvents
  if (sorted.length > maxEvents) {
    return sorted.slice(sorted.length - maxEvents);
  }
  return sorted;
}

/**
 * Create a point-in-time RouteSubsystemSnapshot.
 */
export function createRouteSubsystemSnapshot(params: {
  tick: number;
  timestampS: number;
  activeRoutes?: Map<string, ActiveRoute>;
  plannedRoutes?: Map<string, PlannedRoute>;
  candidateRoutes?: Map<string, CandidateRoute[]>;
  rerouteEvents?: RerouteEvent[];
}): RouteSubsystemSnapshot {
  return {
    tick: params.tick,
    timestampS: params.timestampS,
    activeRoutes: new Map(params.activeRoutes || []),
    plannedRoutes: new Map(params.plannedRoutes || []),
    candidateRoutes: new Map(params.candidateRoutes || []),
    rerouteEvents: params.rerouteEvents ? [...params.rerouteEvents] : [],
  };
}
