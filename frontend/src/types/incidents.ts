/**
 * Type definitions for interactive roadway incident management and scenario controls.
 */

export type IncidentType =
  | "road_closure"
  | "congestion"
  | "obstacle"
  | "signal_override"
  | "hazard"
  | "accident";

export type IncidentSeverity = "low" | "medium" | "high" | "critical";

export type IncidentStatus = "active" | "resolved";

export type SignalOverridePhase = "red" | "yellow" | "green";

export type ObstacleType =
  | "construction"
  | "debris"
  | "stalled_vehicle"
  | "static_barrier";

export interface IncidentRecord {
  id: string;
  incident_type: IncidentType;
  status: IncidentStatus;
  severity: IncidentSeverity;
  affected_edge_id?: string | null;
  affected_node_id?: string | null;
  position?: { x: number; y: number } | null;
  reported_timestamp_s: number;
  reported_tick: number;
  resolved_timestamp_s?: number | null;
  resolved_tick?: number | null;
  duration_s?: number | null;
  description?: string | null;
  congestion_factor?: number | null;
  target_signal_phase?: SignalOverridePhase | null;
  metadata?: Record<string, unknown>;
}

export interface CreateIncidentPayload {
  incident_type: IncidentType;
  affected_edge_id?: string;
  edge_id?: string;
  affected_node_id?: string;
  node_id?: string;
  signal_id?: string;
  severity?: IncidentSeverity;
  duration_s?: number;
  description?: string;
  congestion_factor?: number;
  delay_multiplier?: number;
  target_signal_phase?: SignalOverridePhase;
  override_phase?: "RED" | "YELLOW" | "GREEN" | SignalOverridePhase;
  obstacle_type?: ObstacleType | string;
  metadata?: Record<string, unknown>;
}

export interface IncidentListResponse {
  run_id: string;
  total_count: number;
  active_count: number;
  resolved_count: number;
  incidents: IncidentRecord[];
  disclaimer?: string;
}

export interface IncidentSubsystemSnapshot {
  active_incidents: IncidentRecord[];
  closed_edges: string[];
  congested_edges: Record<string, number>;
  hazard_edges: Record<string, number>;
  active_count: number;
}

/**
 * Creates an authoritative snapshot of the incident subsystem.
 */
export function createIncidentSubsystemSnapshot(
  incidents: IncidentRecord[]
): IncidentSubsystemSnapshot {
  const closed_edges: string[] = [];
  const congested_edges: Record<string, number> = {};
  const hazard_edges: Record<string, number> = {};

  for (const inc of incidents) {
    if (inc.status === "active") {
      if (inc.incident_type === "road_closure" && inc.affected_edge_id) {
        closed_edges.push(inc.affected_edge_id);
      } else if (inc.incident_type === "congestion" && inc.affected_edge_id) {
        congested_edges[inc.affected_edge_id] = inc.congestion_factor ?? 2.0;
      } else if (
        (inc.incident_type === "hazard" || inc.incident_type === "obstacle") &&
        inc.affected_edge_id
      ) {
        hazard_edges[inc.affected_edge_id] = 1.0;
      }
    }
  }

  return {
    active_incidents: incidents,
    closed_edges,
    congested_edges,
    hazard_edges,
    active_count: incidents.filter((i) => i.status === "active").length,
  };
}
