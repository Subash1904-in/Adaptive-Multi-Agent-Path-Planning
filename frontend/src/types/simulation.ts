/**
 * Domain types matching the AMAPP simulation REST API and domain models.
 */

import type { OperationalAnalytics } from "./analytics";

export interface Position2D {
  x: number;
  y: number;
}

export interface ScenarioMetadata {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  vehicle_count: number;
  road_network_source: string;
  time_step_s: number;
  max_ticks: number | null;
  effective_max_ticks: number | null;
}

export interface GridConfig {
  rows: number;
  cols: number;
  spacing_m: number;
  speed_limit_mps?: number;
  lanes?: number;
  bidirectional?: boolean;
  seed?: number;
}

export interface RoadNetworkDefinition {
  source_type: "synthetic_grid" | "supplied_graph" | "osm_import";
  grid_config?: GridConfig | null;
  supplied_graph_name?: string | null;
  osm_config?: Record<string, unknown> | null;
  allow_osm_fallback?: boolean;
}

export interface VehicleScenarioDefinition {
  vehicle_id: string;
  start_node_id: string;
  destination_node_id: string;
  algorithm?: string;
  cost_mode?: string;
  closed_edge_ids?: string[];
  initial_speed_mps?: number;
  vehicle_type?: "standard" | "emergency";
  metadata?: Record<string, unknown>;
}

export interface TrafficSignalScenarioDefinition {
  signal_id: string;
  node_id: string;
  config?: Record<string, unknown>;
  incoming_edge_ids?: string[];
}

export interface CrosswalkScenarioDefinition {
  crosswalk_id: string;
  entry_point: [number, number];
  exit_point: [number, number];
  width_m?: number;
  associated_intersection_id?: string | null;
  signal_controller_id?: string | null;
}

export interface PedestrianScenarioDefinition {
  pedestrian_id: string;
  initial_position: [number, number];
  destination_point: [number, number];
  crosswalk_id?: string | null;
  initial_heading_rad?: number;
  initial_speed_mps?: number;
  walking_speed_mps?: number;
}

export interface EmergencyVehicleScenarioDefinition {
  vehicle_id: string;
  emergency_type: "ambulance" | "fire_engine" | "police";
  start_node_id: string;
  destination_node_id: string;
  priority_level?: number | null;
  activate_at_time_s?: number;
}

export interface ScenarioDefinition {
  metadata: ScenarioMetadata;
  road_network: RoadNetworkDefinition;
  vehicles: VehicleScenarioDefinition[];
  signals?: TrafficSignalScenarioDefinition[];
  pedestrians?: PedestrianScenarioDefinition[];
  crosswalks?: CrosswalkScenarioDefinition[];
  emergency_vehicles?: EmergencyVehicleScenarioDefinition[];
  time_step_s: number;
  max_ticks?: number | null;
  max_duration_s?: number | null;
  stop_on_all_arrived?: boolean;
  seed?: number | null;
  disclaimer?: string;
}

export type RunLifecycleState =
  | "CREATED"
  | "VALIDATING"
  | "READY"
  | "RUNNING"
  | "COMPLETED"
  | "CANCELLED"
  | "FAILED"
  | "LIMIT_REACHED";

export interface RunStatus {
  run_id: string;
  scenario_id: string;
  scenario_name: string;
  lifecycle_state: RunLifecycleState;
  current_tick: number;
  elapsed_time_s: number;
  is_terminal: boolean;
  arrived_count: number;
  active_count: number;
  total_vehicles: number;
  scenario_fingerprint: string;
  initial_world_state_fingerprint: string;
  commit_sha: string | null;
  disclaimer: string;
}

export interface RunCreateRequest {
  scenario_id?: string;
  scenario?: Record<string, unknown>;
  run_id?: string;
  max_ticks?: number | null;
  max_duration_s?: number | null;
  stop_on_all_arrived?: boolean;
  time_step_s?: number | null;
  seed?: number | null;
}

export interface RunMetrics {
  run_id: string;
  lifecycle_state: string;
  current_tick: number;
  metrics: {
    simulation?: {
      vehicles_registered?: number;
      vehicles_arrived?: number;
      vehicles_active?: number;
      simulated_duration_s?: number;
      time_step_s?: number;
    };
    kinematics?: {
      total_distance_traveled_m?: number;
      max_speed_observed_mps?: number;
      average_speed_mps?: number;
    };
    routing?: {
      reroutes_evaluated?: number;
      reroutes_accepted?: number;
    };
    communication?: {
      messages_sent?: number;
      messages_delivered?: number;
      packet_delivery_ratio?: number;
    };
    coordination?: {
      conflicts_detected?: number;
      conflicts_resolved?: number;
    };
    safety?: {
      pair_checks?: number;
      near_misses?: number;
      actual_collisions?: number;
    };
    pedestrians?: {
      crosswalk_waits?: number;
      crosswalk_crossings_completed?: number;
    };
    emergency?: {
      corridors_created?: number;
      corridors_active_final?: number;
    };
    decision?: {
      evaluations_total?: number;
      decisions_accepted?: number;
    };
  };
  analytics?: OperationalAnalytics;
  disclaimer: string;
}

export interface VehicleState {
  vehicle_id: string;
  position: Position2D;
  speed_mps: number;
  heading_rad: number;
  lifecycle_state: string;
  vehicle_type?: "standard" | "emergency";
  route?: string[];
  route_id?: string | null;
  current_edge_id?: string;
  current_node_id?: string | null;
  target_node_id?: string | null;
  remaining_route_distance_m?: number | null;
  is_emergency?: boolean;
  model_type?: "sedan" | "truck" | "bus" | "ambulance" | "fire_engine" | "unknown";
  emergency_type?: "ambulance" | "fire_engine" | "police";
  priority_level?: number | null;
  tick?: number;
  simulation_time_s?: number;
  is_stale?: boolean;
}

export interface PedestrianState {
  pedestrian_id: string;
  position: Position2D;
  speed_mps: number;
  heading_rad: number;
  lifecycle_state: string;
  crosswalk_id?: string;
  tick?: number;
  simulation_time_s?: number;
  is_stale?: boolean;
}

export interface TrafficSignalState {
  signal_id: string;
  node_id: string;
  state: "RED" | "YELLOW" | "GREEN";
  time_to_green_s?: number;
  time_to_red_s?: number;
}
