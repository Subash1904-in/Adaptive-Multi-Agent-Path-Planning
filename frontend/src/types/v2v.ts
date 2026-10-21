/**
 * Type contracts and data schemas for V2V communication links, message animations,
 * network state overlays, and historical snapshots.
 */

export type V2VLinkStatus = "active" | "stale";

export interface V2VLink {
  id: string; // Deterministic canonical key: "veh_A<->veh_B" (alphabetically sorted)
  vehicleA: string;
  vehicleB: string;
  status: V2VLinkStatus;
  distance_m?: number;
  lastSeenTimestampS?: number;
  lastMessageId?: string | null;
}

export type V2VMessageAnimationType =
  | "broadcast"
  | "delivery"
  | "queued_latency"
  | "dropped";

export interface V2VMessageAnimation {
  id: string;
  type: V2VMessageAnimationType;
  senderId: string;
  receiverId?: string;
  startWorldPos: { x: number; y: number; z: number };
  endWorldPos?: { x: number; y: number; z: number };
  progress: number; // 0.0 to 1.0
  durationS: number;
  elapsedS: number;
  timestampS: number;
  dropReason?: string | null;
}

export interface V2VDropMetrics {
  outOfRange: number;
  packetLoss: number;
  burstLoss: number;
  linkOutage: number;
  partition: number;
  unavailable: number;
  expired: number;
  duplicate: number;
  invalid: number;
}

export interface V2VNetworkState {
  enabled: boolean;
  rangeM: number | null; // null if unverified/unavailable
  channelState: "good" | "bad" | null;
  activePartitions: string[][] | null;
  totalBroadcasts: number;
  totalDelivered: number;
  totalDropped: number;
  inTransitCount: number;
  packetDeliveryRatio: number | null; // e.g. 0.95 (95%) or null if 0 attempts
  recentDrops: V2VDropMetrics;
}

export interface V2VSubsystemSnapshot {
  timestampS: number;
  tick: number;
  rangeM: number | null;
  links: V2VLink[];
  networkState: V2VNetworkState;
}

export interface V2VOverlayOptions {
  showLinks: boolean;
  showRangeRing: boolean;
  showAnimations: boolean;
  showDegradation: boolean;
}

export const DEFAULT_V2V_OVERLAY_OPTIONS: V2VOverlayOptions = {
  showLinks: true,
  showRangeRing: true,
  showAnimations: true,
  showDegradation: true,
};
