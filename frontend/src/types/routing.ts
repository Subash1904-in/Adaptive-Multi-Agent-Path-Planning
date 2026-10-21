/**
 * Type contracts and data schemas for adaptive routing visualization,
 * route alternatives (candidate paths), rerouting explanations, and historical route review.
 */

export interface RoutePoint3D {
  x: number;
  y: number;
  z: number;
}

export interface ActiveRoute {
  vehicleId: string;
  routeId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  totalDistanceM: number | null;
  remainingDistanceM: number | null;
  currentEdgeId: string | null;
  currentNodeId: string | null;
  isRerouted: boolean;
}

export interface PlannedRoute {
  vehicleId: string;
  routeId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  totalDistanceM: number | null;
}

export interface CandidateRoute {
  id: string; // e.g. "cand_veh01_tick12_opt1"
  vehicleId: string;
  nodeIds: string[];
  edgeIds: string[];
  worldPoints: RoutePoint3D[];
  objectiveCost: number | null;
  costImprovement: number | null;
  isAccepted: boolean;
  evaluationTick: number;
}

export type RerouteDecisionClassification =
  | "no_change"
  | "reroute_accepted"
  | "insufficient_benefit"
  | "cooldown_active"
  | "no_alternative_route"
  | "current_route_invalid"
  | "no_fresh_information"
  | "destination_reached"
  | "reroute_rejected"
  | "unknown";

export interface RerouteEvent {
  id: string; // Deterministic canonical ID: "reroute_${vehicle_id}_${tick}_${seq}"
  vehicleId: string;
  tick: number;
  simulationTimeS: number;
  decisionType: RerouteDecisionClassification;
  isAccepted: boolean;
  oldRouteId: string | null;
  newRouteId: string | null;
  currentCost: number | null;
  candidateCost: number | null;
  costImprovement: number | null;
  reason: string; // Authoritative backend reason or neutral fallback: "Route updated at tick N"
  hasExplicitReason: boolean; // True if backend provided non-empty reason; false if fallback was used
  candidateNodeIds: string[];
  candidateEdgeIds: string[];
  markerPosition: RoutePoint3D | null;
  diagnostics?: Record<string, unknown>;
}

export interface RouteSubsystemSnapshot {
  tick: number;
  timestampS: number;
  activeRoutes: Map<string, ActiveRoute>;
  plannedRoutes: Map<string, PlannedRoute>;
  candidateRoutes: Map<string, CandidateRoute[]>; // vehicleId -> candidates
  rerouteEvents: RerouteEvent[]; // Bounded historical list
}

export interface RouteOverlayOptions {
  showActiveRoutes: boolean;
  showPlannedRoutes: boolean;
  showCandidateRoutes: boolean;
  showRerouteMarkers: boolean;
}

export const DEFAULT_ROUTE_OVERLAY_OPTIONS: RouteOverlayOptions = {
  showActiveRoutes: true,
  showPlannedRoutes: true,
  showCandidateRoutes: true,
  showRerouteMarkers: true,
};
