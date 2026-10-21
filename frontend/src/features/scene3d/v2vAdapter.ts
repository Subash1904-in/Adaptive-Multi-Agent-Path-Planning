/**
 * Data adapter and extraction utilities for V2V communication states.
 * Transforms backend telemetry and snapshots into normalized, deduplicated visual models.
 */

import type {
  V2VDropMetrics,
  V2VLink,
  V2VLinkStatus,
  V2VNetworkState,
  V2VSubsystemSnapshot,
} from "../../types/v2v";

/**
 * Extract verified communication range in meters.
 * Strictly uses backend values; returns null if unavailable (does not fabricate a default).
 */
export function extractV2VRange(
  commSnapshot?: unknown,
  scenario?: unknown
): number | null {
  const snap = commSnapshot as Record<string, unknown> | undefined;
  if (snap && typeof snap.range_m === "number" && Number.isFinite(snap.range_m) && snap.range_m > 0) {
    return snap.range_m;
  }

  const scn = scenario as Record<string, unknown> | undefined;
  const v2vCfg = scn?.v2v_config as Record<string, unknown> | undefined;
  if (v2vCfg && typeof v2vCfg.range_m === "number" && Number.isFinite(v2vCfg.range_m) && v2vCfg.range_m > 0) {
    return v2vCfg.range_m;
  }

  return null;
}

/**
 * Extract confirmed V2V communication links from backend neighbor tables.
 * Deduplicates symmetric links (A<->B and B<->A) and marks status based on freshness.
 */
export function extractV2VLinks(
  neighborTables?: Record<string, unknown> | null,
  vehiclePositions?: Map<string, { x: number; y: number }>
): V2VLink[] {
  if (!neighborTables || typeof neighborTables !== "object") {
    return [];
  }

  const linksMap = new Map<string, V2VLink>();

  for (const [ownerId, rawTable] of Object.entries(neighborTables)) {
    if (!ownerId || typeof ownerId !== "string" || !rawTable || typeof rawTable !== "object") {
      continue;
    }

    const table = rawTable as Record<string, unknown>;
    const neighbors = table.neighbors as Record<string, unknown> | undefined;
    const activeIds = Array.isArray(table.active_neighbor_ids) ? table.active_neighbor_ids : [];
    const staleIds = Array.isArray(table.stale_neighbor_ids) ? table.stale_neighbor_ids : [];

    // Helper to process an individual neighbor relationship
    const processNeighbor = (
      neighborId: string,
      status: V2VLinkStatus,
      distance_m?: number,
      lastSeen?: number,
      lastMsgId?: string | null
    ) => {
      if (!neighborId || neighborId === ownerId) return;

      // Canonical canonical ID sorted alphabetically: "vehA<->vehB"
      const [u, v] = [ownerId, neighborId].sort();
      const linkId = `${u}<->${v}`;

      const existing = linksMap.get(linkId);
      if (!existing) {
        // Compute distance from vehicle positions if not provided in record
        let dist = distance_m;
        if ((dist === undefined || !Number.isFinite(dist)) && vehiclePositions) {
          const posA = vehiclePositions.get(u);
          const posB = vehiclePositions.get(v);
          if (posA && posB) {
            dist = Math.hypot(posB.x - posA.x, posB.y - posA.y);
          }
        }

        linksMap.set(linkId, {
          id: linkId,
          vehicleA: u,
          vehicleB: v,
          status,
          distance_m: dist !== undefined && Number.isFinite(dist) ? Number(dist.toFixed(2)) : undefined,
          lastSeenTimestampS: lastSeen,
          lastMessageId: lastMsgId,
        });
      } else {
        // If either side considers the relationship stale, mark as stale
        if (status === "stale") {
          existing.status = "stale";
        }
        if (distance_m !== undefined && Number.isFinite(distance_m)) {
          existing.distance_m = Number(distance_m.toFixed(2));
        }
        if (lastSeen !== undefined && (existing.lastSeenTimestampS === undefined || lastSeen > existing.lastSeenTimestampS)) {
          existing.lastSeenTimestampS = lastSeen;
        }
        if (lastMsgId) {
          existing.lastMessageId = lastMsgId;
        }
      }
    };

    // 1. Process from neighbors map if available
    if (neighbors && typeof neighbors === "object") {
      for (const [nbrId, rawRecord] of Object.entries(neighbors)) {
        if (!rawRecord || typeof rawRecord !== "object") continue;
        const rec = rawRecord as Record<string, unknown>;
        const recStatus = rec.status === "stale" ? "stale" : "active";
        const dist = typeof rec.last_distance_m === "number" ? rec.last_distance_m : undefined;
        const seen = typeof rec.last_seen_timestamp_s === "number" ? rec.last_seen_timestamp_s : undefined;
        const msgId = typeof rec.last_message_id === "string" ? rec.last_message_id : null;
        processNeighbor(nbrId, recStatus, dist, seen, msgId);
      }
    } else {
      // 2. Fallback to active/stale ID lists if detailed neighbors map is absent
      for (const activeId of activeIds) {
        if (typeof activeId === "string") {
          processNeighbor(activeId, "active");
        }
      }
      for (const staleId of staleIds) {
        if (typeof staleId === "string") {
          processNeighbor(staleId, "stale");
        }
      }
    }
  }

  // Sort links deterministically by canonical ID
  return Array.from(linksMap.values()).sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * Extract discrete packet drop telemetry breakdown.
 */
export function extractV2VDropMetrics(
  commMetrics?: unknown,
  commSnapshot?: unknown
): V2VDropMetrics {
  const m = (commMetrics || {}) as Record<string, unknown>;
  const s = (commSnapshot || {}) as Record<string, unknown>;

  const getNum = (key: string): number => {
    if (typeof m[key] === "number" && Number.isFinite(m[key])) return m[key] as number;
    if (typeof s[key] === "number" && Number.isFinite(s[key])) return s[key] as number;
    return 0;
  };

  return {
    outOfRange: getNum("dropped_out_of_range"),
    packetLoss: getNum("dropped_packet_loss"),
    burstLoss: getNum("dropped_burst_loss"),
    linkOutage: getNum("dropped_link_outage"),
    partition: getNum("dropped_partition"),
    unavailable: getNum("dropped_unavailable"),
    expired: getNum("dropped_expired"),
    duplicate: getNum("dropped_duplicate"),
    invalid: getNum("dropped_invalid"),
  };
}

/**
 * Extract comprehensive V2V network health state.
 */
export function extractV2VNetworkState(
  commSnapshot?: unknown,
  commMetrics?: unknown,
  scenario?: unknown
): V2VNetworkState {
  const snap = commSnapshot as Record<string, unknown> | undefined;
  const metrics = commMetrics as Record<string, unknown> | undefined;
  const scn = scenario as Record<string, unknown> | undefined;
  const v2vCfg = scn?.v2v_config as Record<string, unknown> | undefined;

  const enabled = Boolean(snap?.enabled ?? v2vCfg?.enabled ?? false);
  const rangeM = extractV2VRange(commSnapshot, scenario);

  let channelState: "good" | "bad" | null = null;
  if (snap?.channel_state === "good") channelState = "good";
  else if (snap?.channel_state === "bad") channelState = "bad";

  let activePartitions: string[][] | null = null;
  if (Array.isArray(snap?.active_partitions)) {
    activePartitions = (snap.active_partitions as unknown[])
      .filter((p): p is string[] => Array.isArray(p))
      .map((p) => p.map(String));
  }

  const totalBroadcasts = Number(
    snap?.total_broadcasts ?? metrics?.broadcasts_attempted ?? 0
  );
  const totalDelivered = Number(
    snap?.total_delivered ?? metrics?.successful_deliveries ?? 0
  );
  const inTransitCount = Number(
    snap?.in_transit_count ?? metrics?.packets_queued_latency ?? 0
  );

  const drops = extractV2VDropMetrics(commMetrics, commSnapshot);
  const totalDropped = Number(
    snap?.total_dropped ??
      (drops.outOfRange +
        drops.packetLoss +
        drops.burstLoss +
        drops.linkOutage +
        drops.partition +
        drops.unavailable +
        drops.expired +
        drops.duplicate +
        drops.invalid)
  );

  // Calculate packet delivery ratio
  let pdr: number | null = null;
  const totalAttempts = totalDelivered + totalDropped;
  if (totalAttempts > 0) {
    pdr = Number((totalDelivered / totalAttempts).toFixed(4));
  } else if (metrics && typeof metrics.delivery_attempts === "number" && metrics.delivery_attempts > 0) {
    pdr = Number(((metrics.successful_deliveries as number) / metrics.delivery_attempts).toFixed(4));
  }

  return {
    enabled,
    rangeM,
    channelState,
    activePartitions,
    totalBroadcasts,
    totalDelivered,
    totalDropped,
    inTransitCount,
    packetDeliveryRatio: pdr,
    recentDrops: drops,
  };
}

/**
 * Assemble a unified, immutable V2V subsystem snapshot for the given simulation tick.
 */
export function createV2VSubsystemSnapshot(params: {
  tick: number;
  timestampS: number;
  commSnapshot?: unknown;
  commMetrics?: unknown;
  scenario?: unknown;
  vehiclePositions?: Map<string, { x: number; y: number }>;
}): V2VSubsystemSnapshot {
  const rangeM = extractV2VRange(params.commSnapshot, params.scenario);
  const snap = params.commSnapshot as Record<string, unknown> | undefined;
  const neighborTables = snap?.neighbor_tables as Record<string, unknown> | undefined;
  const links = extractV2VLinks(neighborTables, params.vehiclePositions);
  const networkState = extractV2VNetworkState(
    params.commSnapshot,
    params.commMetrics,
    params.scenario
  );

  return {
    tick: params.tick,
    timestampS: params.timestampS,
    rangeM,
    links,
    networkState,
  };
}
