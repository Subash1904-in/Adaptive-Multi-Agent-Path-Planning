/**
 * Typed interfaces for AMAPP Operational Metrics Dashboard and Simulation Analytics.
 */

export interface HistogramBin {
  bin_start_s: number;
  bin_end_s: number;
  count: number;
}

export interface TravelTimeDistribution {
  sample_count: number;
  mean_s: number | null;
  median_s: number | null;
  p90_s: number | null;
  p95_s: number | null;
  min_s: number | null;
  max_s: number | null;
  bins: HistogramBin[];
}

export interface TripAnalytics {
  total_trips: number;
  completed_trips: number;
  active_trips: number;
  completion_rate_pct: number | null;
  travel_time: TravelTimeDistribution;
}

export interface TopIntersectionCrossing {
  node_id: string;
  crossings: number;
  is_signalized: boolean;
}

export interface ThroughputAnalytics {
  total_crossings: number;
  crossings_per_minute: number;
  signalized_crossings: number;
  unsignalized_crossings: number;
  top_intersections: TopIntersectionCrossing[];
  active_measurement_window_s?: number;
  node_crossings?: Array<{
    node_id: string;
    crossing_count: number;
    is_signalized?: boolean;
  }>;
}

export interface SafetyAnalytics {
  actual_collisions: number;
  near_misses: number;
  emergency_brakes: number;
  control_overrides: number;
  min_separation_observed_m: number | null;
  min_ttc_observed_s: number | null;
  collision_rate_per_minute: number;
  near_miss_rate_per_minute: number;
  near_miss_frequency_per_tick?: number | null;
}

export interface CommunicationAnalytics {
  messages_sent: number;
  messages_delivered: number;
  messages_lost: number;
  messages_expired: number;
  packet_delivery_ratio: number | null;
  pdr?: number | null;
  packet_loss_rate: number | null;
  loss_rate?: number | null;
  loss_by_reason: Record<string, number>;
  loss_breakdown?: Record<string, number>;
  latency_packets_queued: number;
  latency_packets_delivered: number;
  latency_continuous_ms: number | null;
  latency_ms_available: boolean;
  average_latency_ms?: number | null;
  channel_utilization_pct?: number | null;
  disclaimer: string;
}

export interface RoutingAnalytics {
  reroutes_evaluated: number;
  reroutes_accepted: number;
  reroutes_rejected: number;
  acceptance_rate_pct: number | null;
  reroutes_attempted?: number;
  reroute_acceptance_rate_pct?: number | null;
  active_rerouted_vehicles?: number;
}

export interface IncidentAnalytics {
  total_active_incidents: number;
  total_active?: number;
  active_count?: number;
  cumulative_count?: number;
  active_by_type: Record<string, number>;
  resolved_incidents: number;
}

export interface TimeSeriesPoint {
  tick: number;
  timestamp_s?: number;
  simulation_time_s?: number;
  completed_trips?: number;
  trips_completed?: number;
  active_vehicles?: number;
  total_distance_m?: number;
  avg_speed_mps?: number;
  intersection_crossings?: number;
  v2v_pdr: number | null;
  collisions: number;
  near_misses: number;
  reroutes_accepted: number;
  active_incidents?: number;
}

export interface OperationalAnalytics {
  trips: TripAnalytics;
  throughput: ThroughputAnalytics;
  safety: SafetyAnalytics;
  communication: CommunicationAnalytics;
  routing: RoutingAnalytics;
  incidents: IncidentAnalytics;
  time_series: TimeSeriesPoint[];
}

export type AnalyticsCategoryFilter =
  | "all"
  | "trips"
  | "throughput"
  | "safety"
  | "communication"
  | "routing"
  | "incidents";

export interface MetricsQueryParams {
  tick_start?: number;
  tick_end?: number;
  time_window_start_s?: number;
  time_window_end_s?: number;
  limit_samples?: number;
}
