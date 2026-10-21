/**
 * WebSocket Protocol Types for AMAPP simulation live streaming.
 * Conforms to protocol schema 1.0.0.
 */

export type WebSocketConnectionStatus =
  | "DISCONNECTED"
  | "CONNECTING"
  | "CONNECTED"
  | "RECONNECTING"
  | "ERROR";

export type SimulationEventType =
  // Lifecycle
  | "run.state_change"
  | "run.step"
  | "run.completed"
  | "run.cancelled"
  | "run.failed"
  | "run.limit_reached"
  // Entities & Kinematics
  | "simulation.snapshot"
  | "vehicle.state"
  | "traffic_signals.update"
  | "pedestrian.state"
  // Domain subsystems
  | "safety.event"
  | "routing.reroute"
  | "communication.message"
  | "communication.impairment"
  | "coordination.report"
  | "emergency.event"
  | "decision.evaluated"
  // Diagnostics & Control
  | "connection.ack"
  | "telemetry.gap"
  | "metrics.summary"
  | "heartbeat"
  | "error";

export interface WebSocketEventEnvelope<T = Record<string, unknown>> {
  event_type: SimulationEventType | string;
  run_id: string;
  sequence: number;
  tick: number;
  timestamp_s: number;
  schema_version: string;
  payload: T;
  disclaimer?: string;
}

export interface ClientCommand {
  type: "subscribe" | "unsubscribe" | "step" | "cancel" | "heartbeat" | "ping";
  from_sequence?: number;
  from_tick?: number;
  ticks?: number;
  run_to_completion?: boolean;
  target_accels?: Record<string, number>;
  reason?: string;
}

export interface TelemetryGapPayload {
  reason: "buffer_overflow" | "expired_history" | string;
  dropped_count?: number;
  from_sequence?: number;
  to_sequence?: number;
  message?: string;
}

export interface ConnectionAckPayload {
  run_id: string;
  status: string;
  initial_tick: number;
}
