/**
 * Bounded, session-local history buffer storing immutable simulation frame snapshots.
 *
 * Supports deduplication across REST step responses and WebSocket broadcasts,
 * FIFO eviction when capacity is reached, and random-access tick querying for scrubbing.
 */

import type { SimulationFrameSnapshot } from "../../types/playback";
import type { PedestrianState, TrafficSignalState, VehicleState } from "../../types/simulation";

export class SimulationHistoryBuffer {
  private readonly capacity: number;
  private readonly snapshotsByTick: Map<number, SimulationFrameSnapshot> = new Map();
  private orderedTicks: number[] = [];

  constructor(capacity = 500) {
    this.capacity = Math.max(1, capacity);
  }

  public getCapacity(): number {
    return this.capacity;
  }

  public size(): number {
    return this.snapshotsByTick.size;
  }

  public clear(): void {
    this.snapshotsByTick.clear();
    this.orderedTicks = [];
  }

  public has(tick: number): boolean {
    return this.snapshotsByTick.has(tick);
  }

  public getSnapshot(tick: number): SimulationFrameSnapshot | undefined {
    return this.snapshotsByTick.get(tick);
  }

  public getEarliestTick(): number | null {
    if (this.orderedTicks.length === 0) return null;
    return this.orderedTicks[0];
  }

  public getLatestTick(): number | null {
    if (this.orderedTicks.length === 0) return null;
    return this.orderedTicks[this.orderedTicks.length - 1];
  }

  public getAllTicks(): number[] {
    return [...this.orderedTicks];
  }

  /**
   * Insert or merge a simulation snapshot at a given tick.
   * Entities are cloned to guarantee historical immutability.
   */
  public addSnapshot(raw: SimulationFrameSnapshot): void {
    if (!Number.isFinite(raw.tick) || raw.tick < 0) {
      return;
    }

    // 1. Deep-clone entity maps to guarantee historical immutability
    const clonedVehicles = new Map<string, VehicleState>();
    for (const [id, v] of raw.vehicles.entries()) {
      clonedVehicles.set(id, {
        ...v,
        position: { ...v.position },
        route: v.route ? [...v.route] : undefined,
      });
    }

    const clonedPedestrians = new Map<string, PedestrianState>();
    for (const [id, p] of raw.pedestrians.entries()) {
      clonedPedestrians.set(id, {
        ...p,
        position: { ...p.position },
      });
    }

    const clonedSignals = new Map<string, TrafficSignalState>();
    for (const [id, s] of raw.signals.entries()) {
      clonedSignals.set(id, { ...s });
    }

    let clonedComm: import("../../types/v2v").V2VSubsystemSnapshot | null = null;
    if (raw.communication) {
      clonedComm = {
        timestampS: raw.communication.timestampS,
        tick: raw.communication.tick,
        rangeM: raw.communication.rangeM,
        links: raw.communication.links.map((link) => ({ ...link })),
        networkState: {
          ...raw.communication.networkState,
          activePartitions: raw.communication.networkState.activePartitions
            ? raw.communication.networkState.activePartitions.map((p) => [...p])
            : null,
          recentDrops: { ...raw.communication.networkState.recentDrops },
        },
      };
    }

    let clonedRouting: import("../../types/routing").RouteSubsystemSnapshot | null = null;
    if (raw.routing) {
      const clonedActive = new Map<string, import("../../types/routing").ActiveRoute>();
      for (const [k, v] of raw.routing.activeRoutes.entries()) {
        clonedActive.set(k, {
          ...v,
          nodeIds: [...v.nodeIds],
          edgeIds: [...v.edgeIds],
          worldPoints: v.worldPoints.map((pt) => ({ ...pt })),
        });
      }
      const clonedPlanned = new Map<string, import("../../types/routing").PlannedRoute>();
      for (const [k, v] of raw.routing.plannedRoutes.entries()) {
        clonedPlanned.set(k, {
          ...v,
          nodeIds: [...v.nodeIds],
          edgeIds: [...v.edgeIds],
          worldPoints: v.worldPoints.map((pt) => ({ ...pt })),
        });
      }
      const clonedCandidates = new Map<string, import("../../types/routing").CandidateRoute[]>();
      for (const [k, arr] of raw.routing.candidateRoutes.entries()) {
        clonedCandidates.set(
          k,
          arr.map((c) => ({
            ...c,
            nodeIds: [...c.nodeIds],
            edgeIds: [...c.edgeIds],
            worldPoints: c.worldPoints.map((pt) => ({ ...pt })),
          }))
        );
      }
      const clonedEvents = raw.routing.rerouteEvents.map((ev) => ({
        ...ev,
        candidateNodeIds: [...ev.candidateNodeIds],
        candidateEdgeIds: [...ev.candidateEdgeIds],
        markerPosition: ev.markerPosition ? { ...ev.markerPosition } : null,
        diagnostics: ev.diagnostics ? { ...ev.diagnostics } : undefined,
      }));

      clonedRouting = {
        tick: raw.routing.tick,
        timestampS: raw.routing.timestampS,
        activeRoutes: clonedActive,
        plannedRoutes: clonedPlanned,
        candidateRoutes: clonedCandidates,
        rerouteEvents: clonedEvents,
      };
    }

    let clonedIncidents: import("../../types/incidents").IncidentSubsystemSnapshot | null = null;
    if (raw.incidents) {
      clonedIncidents = {
        active_incidents: raw.incidents.active_incidents.map((inc) => ({
          ...inc,
          position: inc.position ? { ...inc.position } : null,
          metadata: inc.metadata ? { ...inc.metadata } : undefined,
        })),
        closed_edges: [...raw.incidents.closed_edges],
        congested_edges: { ...raw.incidents.congested_edges },
        hazard_edges: { ...raw.incidents.hazard_edges },
        active_count: raw.incidents.active_count,
      };
    }

    const immutableSnapshot: SimulationFrameSnapshot = {
      tick: raw.tick,
      simulation_time_s: raw.simulation_time_s,
      timestamp_ms: raw.timestamp_ms || Date.now(),
      vehicles: clonedVehicles,
      pedestrians: clonedPedestrians,
      signals: clonedSignals,
      metrics: raw.metrics ? { ...raw.metrics } : null,
      communication: clonedComm,
      routing: clonedRouting,
      incidents: clonedIncidents,
    };

    // 2. Check if tick already exists (deduplication)
    if (this.snapshotsByTick.has(raw.tick)) {
      this.snapshotsByTick.set(raw.tick, immutableSnapshot);
      return;
    }

    // 3. New tick insertion with binary search insertion for sorted order
    const insertIdx = this.findInsertionIndex(raw.tick);
    this.orderedTicks.splice(insertIdx, 0, raw.tick);
    this.snapshotsByTick.set(raw.tick, immutableSnapshot);

    // 4. Bounded eviction: FIFO when capacity is exceeded
    while (this.orderedTicks.length > this.capacity) {
      const evictedTick = this.orderedTicks.shift();
      if (evictedTick !== undefined) {
        this.snapshotsByTick.delete(evictedTick);
      }
    }
  }

  private findInsertionIndex(tick: number): number {
    let low = 0;
    let high = this.orderedTicks.length;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (this.orderedTicks[mid] < tick) {
        low = mid + 1;
      } else {
        high = mid;
      }
    }
    return low;
  }
}
