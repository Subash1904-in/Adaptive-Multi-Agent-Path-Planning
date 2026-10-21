/**
 * Comprehensive test suite for Phase 27:
 * V2V Communication Links, Message Animations, Network-State Overlays,
 * Data Adapters, and Historical Playback Buffer Integration.
 */

import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  createV2VSubsystemSnapshot,
  extractV2VDropMetrics,
  extractV2VLinks,
  extractV2VNetworkState,
  extractV2VRange,
} from "../features/scene3d/v2vAdapter";
import { V2VOverlayManager } from "../features/scene3d/v2vOverlay";
import { SimulationHistoryBuffer } from "../features/playback/historyBuffer";
import type { V2VSubsystemSnapshot } from "../types/v2v";

describe("Phase 27 — V2V Data Adapter", () => {
  describe("extractV2VRange", () => {
    it("extracts verified range_m from communication snapshot", () => {
      const snap = { range_m: 60.0 };
      expect(extractV2VRange(snap)).toBe(60.0);
    });

    it("extracts verified range_m from scenario v2v_config", () => {
      const scenario = { v2v_config: { range_m: 75.5 } };
      expect(extractV2VRange(undefined, scenario)).toBe(75.5);
    });

    it("prefers snapshot range_m over scenario definition when both exist", () => {
      const snap = { range_m: 45.0 };
      const scenario = { v2v_config: { range_m: 100.0 } };
      expect(extractV2VRange(snap, scenario)).toBe(45.0);
    });

    it("returns null when range is missing, undefined, zero, or negative (no fabricated default)", () => {
      expect(extractV2VRange(null, null)).toBeNull();
      expect(extractV2VRange({}, {})).toBeNull();
      expect(extractV2VRange({ range_m: 0 })).toBeNull();
      expect(extractV2VRange({ range_m: -10 })).toBeNull();
      expect(extractV2VRange({ range_m: "invalid" })).toBeNull();
    });
  });

  describe("extractV2VLinks", () => {
    it("extracts and deduplicates symmetric active neighbor links", () => {
      const neighborTables = {
        veh_1: {
          neighbors: {
            veh_2: {
              status: "active",
              last_distance_m: 18.5,
              last_seen_timestamp_s: 1.2,
              last_message_id: "msg_101",
            },
          },
        },
        veh_2: {
          neighbors: {
            veh_1: {
              status: "active",
              last_distance_m: 18.5,
              last_seen_timestamp_s: 1.25,
              last_message_id: "msg_102",
            },
          },
        },
      };

      const links = extractV2VLinks(neighborTables);
      expect(links).toHaveLength(1);
      expect(links[0].id).toBe("veh_1<->veh_2");
      expect(links[0].vehicleA).toBe("veh_1");
      expect(links[0].vehicleB).toBe("veh_2");
      expect(links[0].status).toBe("active");
      expect(links[0].distance_m).toBe(18.5);
      expect(links[0].lastSeenTimestampS).toBe(1.25);
    });

    it("marks link as stale if either peer reports stale status", () => {
      const neighborTables = {
        veh_1: {
          neighbors: {
            veh_2: {
              status: "active",
              last_distance_m: 25.0,
            },
          },
        },
        veh_2: {
          neighbors: {
            veh_1: {
              status: "stale",
              last_distance_m: 25.0,
            },
          },
        },
      };

      const links = extractV2VLinks(neighborTables);
      expect(links).toHaveLength(1);
      expect(links[0].status).toBe("stale");
    });

    it("computes distance from vehicle positions when not present in record", () => {
      const neighborTables = {
        veh_A: {
          neighbors: {
            veh_B: { status: "active" },
          },
        },
      };
      const positions = new Map<string, { x: number; y: number }>([
        ["veh_A", { x: 0, y: 0 }],
        ["veh_B", { x: 30, y: 40 }],
      ]);

      const links = extractV2VLinks(neighborTables, positions);
      expect(links).toHaveLength(1);
      expect(links[0].distance_m).toBe(50.0);
    });

    it("supports fallback parsing via active_neighbor_ids and stale_neighbor_ids lists", () => {
      const neighborTables = {
        veh_1: {
          active_neighbor_ids: ["veh_2"],
          stale_neighbor_ids: ["veh_3"],
        },
      };

      const links = extractV2VLinks(neighborTables);
      expect(links).toHaveLength(2);
      expect(links[0].id).toBe("veh_1<->veh_2");
      expect(links[0].status).toBe("active");
      expect(links[1].id).toBe("veh_1<->veh_3");
      expect(links[1].status).toBe("stale");
    });

    it("ignores self-neighbors and malformed entries safely", () => {
      const neighborTables = {
        veh_1: {
          neighbors: {
            veh_1: { status: "active" }, // self link ignored
            "": null, // malformed entry ignored
          },
        },
      };

      const links = extractV2VLinks(neighborTables);
      expect(links).toHaveLength(0);
      expect(extractV2VLinks(null)).toEqual([]);
      expect(extractV2VLinks(undefined)).toEqual([]);
    });
  });

  describe("extractV2VNetworkState and drop metrics", () => {
    it("computes packet delivery ratio (PDR) correctly", () => {
      const snap = {
        enabled: true,
        total_delivered: 90,
        total_dropped: 10,
        in_transit_count: 3,
        channel_state: "good",
        active_partitions: [["veh_1", "veh_2"], ["veh_3"]],
      };

      const state = extractV2VNetworkState(snap);
      expect(state.enabled).toBe(true);
      expect(state.totalDelivered).toBe(90);
      expect(state.totalDropped).toBe(10);
      expect(state.inTransitCount).toBe(3);
      expect(state.channelState).toBe("good");
      expect(state.packetDeliveryRatio).toBe(0.9); // 90 / (90 + 10)
      expect(state.activePartitions).toEqual([["veh_1", "veh_2"], ["veh_3"]]);
    });

    it("returns null PDR when no delivery attempts have occurred", () => {
      const snap = {
        enabled: true,
        total_delivered: 0,
        total_dropped: 0,
      };

      const state = extractV2VNetworkState(snap);
      expect(state.packetDeliveryRatio).toBeNull();
    });

    it("extracts discrete drop metrics accurately", () => {
      const commMetrics = {
        dropped_out_of_range: 5,
        dropped_packet_loss: 3,
        dropped_burst_loss: 2,
        dropped_link_outage: 1,
        dropped_partition: 4,
        dropped_unavailable: 1,
        dropped_expired: 0,
        dropped_duplicate: 0,
        dropped_invalid: 0,
      };

      const drops = extractV2VDropMetrics(commMetrics);
      expect(drops.outOfRange).toBe(5);
      expect(drops.packetLoss).toBe(3);
      expect(drops.burstLoss).toBe(2);
      expect(drops.linkOutage).toBe(1);
      expect(drops.partition).toBe(4);
      expect(drops.unavailable).toBe(1);
    });
  });

  describe("createV2VSubsystemSnapshot", () => {
    it("assembles a full immutable snapshot", () => {
      const snapshot = createV2VSubsystemSnapshot({
        tick: 14,
        timestampS: 1.4,
        commSnapshot: {
          enabled: true,
          range_m: 50.0,
          total_broadcasts: 20,
          total_delivered: 18,
          total_dropped: 2,
          channel_state: "good",
          neighbor_tables: {
            v1: { neighbors: { v2: { status: "active" } } },
          },
        },
      });

      expect(snapshot.tick).toBe(14);
      expect(snapshot.timestampS).toBe(1.4);
      expect(snapshot.rangeM).toBe(50.0);
      expect(snapshot.links).toHaveLength(1);
      expect(snapshot.links[0].id).toBe("v1<->v2");
      expect(snapshot.networkState.totalDelivered).toBe(18);
      expect(snapshot.networkState.packetDeliveryRatio).toBe(0.9);
    });
  });
});

describe("Phase 27 — V2V Three.js Overlay Manager", () => {
  it("initializes scene groups and default options", () => {
    const overlay = new V2VOverlayManager();
    expect(overlay.rootGroup.children).toHaveLength(4);
    const opts = overlay.getOptions();
    expect(opts.showLinks).toBe(true);
    expect(opts.showRangeRing).toBe(true);
    expect(opts.showAnimations).toBe(true);
    expect(opts.showDegradation).toBe(true);
    overlay.dispose();
  });

  it("updates and reuses communication link meshes between vehicles", () => {
    const overlay = new V2VOverlayManager();
    const links = [
      { id: "v1<->v2", vehicleA: "v1", vehicleB: "v2", status: "active" as const },
    ];
    const getPos = (id: string) => {
      if (id === "v1") return new THREE.Vector3(0, 0, 0);
      if (id === "v2") return new THREE.Vector3(20, 0, 0);
      return null;
    };

    overlay.updateLinks(links, getPos);
    expect(overlay.linksGroup.children).toHaveLength(1);

    // Update with vehicle movement (reuses line mesh buffer attribute)
    const getMovedPos = (id: string) => {
      if (id === "v1") return new THREE.Vector3(5, 0, 0);
      if (id === "v2") return new THREE.Vector3(25, 0, 0);
      return null;
    };
    overlay.updateLinks(links, getMovedPos);
    expect(overlay.linksGroup.children).toHaveLength(1);

    // Update with removed link
    overlay.updateLinks([], getPos);
    expect(overlay.linksGroup.children).toHaveLength(0);

    overlay.dispose();
  });

  it("attaches range ring to selected vehicle using verified range", () => {
    const overlay = new V2VOverlayManager();
    const getPos = (id: string) => (id === "v1" ? new THREE.Vector3(10, 0, 20) : null);

    overlay.updateRangeRing("v1", 50.0, getPos);
    expect(overlay.rangeGroup.visible).toBe(true);
    expect(overlay.rangeGroup.children).toHaveLength(2); // disc fill and outline

    // Deselect vehicle hides range ring
    overlay.updateRangeRing(null, 50.0, getPos);
    expect(overlay.rangeGroup.visible).toBe(false);

    // Unavailable range hides range ring
    overlay.updateRangeRing("v1", null, getPos);
    expect(overlay.rangeGroup.visible).toBe(false);

    overlay.dispose();
  });

  it("handles animation lifecycle, pause freezing, and speed scaling", () => {
    const overlay = new V2VOverlayManager();
    overlay.triggerAnimation({
      id: "anim_1",
      type: "delivery",
      senderId: "v1",
      receiverId: "v2",
      startWorldPos: { x: 0, y: 0, z: 0 },
      endWorldPos: { x: 20, y: 0, z: 0 },
      progress: 0,
      durationS: 1.0,
      elapsedS: 0,
      timestampS: 0,
    });

    expect(overlay.animationsGroup.children).toHaveLength(1);

    // Paused state freezes progress
    overlay.updateAnimations(0.5, 1.0, true, false);
    expect(overlay.animationsGroup.children).toHaveLength(1);

    // Speed multiplier scales progression
    overlay.updateAnimations(0.3, 2.0, false, false); // 0.3 * 2.0 = 0.6 advance
    overlay.updateAnimations(0.3, 2.0, false, false); // finishes and evicts
    expect(overlay.animationsGroup.children).toHaveLength(0);

    overlay.dispose();
  });

  it("bounds maximum active animations to prevent memory leaks", () => {
    const overlay = new V2VOverlayManager();

    // Trigger 25 animations when cap is 20
    for (let i = 0; i < 25; i++) {
      overlay.triggerAnimation({
        id: `anim_${i}`,
        type: "dropped",
        senderId: "v1",
        startWorldPos: { x: 0, y: 0, z: 0 },
        progress: 0,
        durationS: 1.0,
        elapsedS: 0,
        timestampS: 0,
      });
    }

    expect(overlay.animationsGroup.children.length).toBeLessThanOrEqual(20);
    overlay.dispose();
  });

  it("clears and disposes all overlay resources cleanly", () => {
    const overlay = new V2VOverlayManager();
    overlay.clear();
    expect(overlay.linksGroup.children).toHaveLength(0);
    expect(overlay.animationsGroup.children).toHaveLength(0);
    overlay.dispose();
  });
});

describe("Phase 27 — Playback & History Buffer V2V Integration", () => {
  it("stores and retrieves immutable V2V subsystem snapshots across scrubbed ticks", () => {
    const history = new SimulationHistoryBuffer(100);

    const v2vSnap: V2VSubsystemSnapshot = {
      tick: 5,
      timestampS: 0.5,
      rangeM: 50.0,
      links: [
        { id: "v1<->v2", vehicleA: "v1", vehicleB: "v2", status: "active" },
      ],
      networkState: {
        enabled: true,
        rangeM: 50.0,
        channelState: "good",
        activePartitions: [["v1", "v2"]],
        totalBroadcasts: 5,
        totalDelivered: 5,
        totalDropped: 0,
        inTransitCount: 0,
        packetDeliveryRatio: 1.0,
        recentDrops: {
          outOfRange: 0,
          packetLoss: 0,
          burstLoss: 0,
          linkOutage: 0,
          partition: 0,
          unavailable: 0,
          expired: 0,
          duplicate: 0,
          invalid: 0,
        },
      },
    };

    history.addSnapshot({
      tick: 5,
      simulation_time_s: 0.5,
      timestamp_ms: 1000,
      vehicles: new Map(),
      pedestrians: new Map(),
      signals: new Map(),
      metrics: null,
      communication: v2vSnap,
    });

    const retrieved = history.getSnapshot(5);
    expect(retrieved).toBeDefined();
    expect(retrieved?.communication).toBeDefined();
    expect(retrieved?.communication?.rangeM).toBe(50.0);
    expect(retrieved?.communication?.links).toHaveLength(1);
    expect(retrieved?.communication?.networkState.channelState).toBe("good");

    // Verify immutability: mutating local original object does not corrupt stored snapshot
    v2vSnap.links[0].status = "stale";
    v2vSnap.networkState.channelState = "bad";
    const postMutation = history.getSnapshot(5);
    expect(postMutation?.communication?.links[0].status).toBe("active");
    expect(postMutation?.communication?.networkState.channelState).toBe("good");
  });
});
