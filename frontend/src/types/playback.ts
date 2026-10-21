/**
 * Type contracts for interactive simulation playback, timeline scrubber,
 * and historical session-local buffering.
 */

import type {
  PedestrianState,
  RunMetrics,
  TrafficSignalState,
  VehicleState,
} from "./simulation";
import type { V2VSubsystemSnapshot } from "./v2v";
import type { RouteSubsystemSnapshot } from "./routing";

export type PlaybackState =
  | "idle"
  | "ready"
  | "playing"
  | "paused"
  | "stepping"
  | "reviewing"
  | "completed"
  | "cancelled"
  | "failed";

export type PlaybackSpeed = 0.5 | 1 | 2 | 5;

export interface SimulationFrameSnapshot {
  tick: number;
  simulation_time_s: number;
  timestamp_ms: number;
  vehicles: Map<string, VehicleState>;
  pedestrians: Map<string, PedestrianState>;
  signals: Map<string, TrafficSignalState>;
  metrics?: RunMetrics | null;
  communication?: V2VSubsystemSnapshot | null;
  routing?: RouteSubsystemSnapshot | null;
}

export interface TimelineRange {
  earliestTick: number;
  latestTick: number;
  currentTick: number;
  simulationTimeS: number;
  maxTicks?: number | null;
  isLive: boolean;
  activeReviewTick: number | null;
  bufferedCount: number;
}

export interface PlaybackSchedulerConfig {
  speed?: PlaybackSpeed;
  timeStepS?: number;
  minIntervalMs?: number;
}
