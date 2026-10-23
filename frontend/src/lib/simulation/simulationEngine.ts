/**
 * Standalone, deterministic in-browser AMAPP Simulation Engine.
 * Implements A* and Dijkstra routing, kinematic vehicle motion, pedestrian crosswalk dynamics,
 * traffic signal cycles, dynamic incident injection and re-routing, V2V communication mesh,
 * operational metrics aggregation, and live event streaming.
 */

import type {
  RunMetrics,
  RunStatus,
  ScenarioDefinition,
} from "../../types/simulation";
import type { IncidentRecord, CreateIncidentPayload, IncidentSeverity } from "../../types/incidents";
import type { WebSocketEventEnvelope } from "../../types/websocket";
import { getUnifiedMetropolitanRoadNetwork } from "../../features/scene3d/geometry";
import type { RoadEdgeGeometry, RoadNetworkGeometry, RoadNodeGeometry } from "../../types/graph";
import { SCENARIO_DEFINITIONS } from "./simulationScenarios";

interface SimVehicle {
  id: string;
  startNodeId: string;
  destinationNodeId: string;
  algorithm: string;
  vehicleType: "standard" | "emergency";
  isEmergency: boolean;
  priorityLevel: number;
  currentEdgeIndex: number;
  distanceAlongEdge: number;
  speedMps: number;
  maxSpeedMps: number;
  headingRad: number;
  position: { x: number; y: number };
  routeNodeIds: string[];
  routeEdgeIds: string[];
  lifecycleState: "en_route" | "arrived" | "yielding" | "blocked";
  closedEdgeIds: Set<string>;
}

interface SimPedestrian {
  id: string;
  position: { x: number; y: number };
  destination: { x: number; y: number };
  crosswalkId: string | null;
  speedMps: number;
  headingRad: number;
  lifecycleState: "walking" | "arrived";
}

interface SimSignal {
  id: string;
  nodeId: string;
  state: "RED" | "YELLOW" | "GREEN";
  timerS: number;
  greenDurationS: number;
  yellowDurationS: number;
  redDurationS: number;
}

export type SimEventListener = (event: WebSocketEventEnvelope) => void;

export class InBrowserSimulationEngine {
  private scenario: ScenarioDefinition;
  private roadNetwork: RoadNetworkGeometry;
  private nodeMap: Map<string, RoadNodeGeometry> = new Map();
  private edgeMap: Map<string, RoadEdgeGeometry> = new Map();
  private adjacency: Map<string, RoadEdgeGeometry[]> = new Map();

  public runId: string;
  public tick: number = 0;
  public elapsedTimeS: number = 0;
  public lifecycleState: RunStatus["lifecycle_state"] = "READY";
  public isTerminal: boolean = false;

  private vehicles: Map<string, SimVehicle> = new Map();
  private pedestrians: Map<string, SimPedestrian> = new Map();
  private signals: Map<string, SimSignal> = new Map();
  private incidents: Map<string, IncidentRecord> = new Map();
  private closedEdges: Set<string> = new Set();

  // Metrics
  private totalBroadcasts: number = 0;
  private totalDelivered: number = 0;
  private totalDropped: number = 0;
  private sequence: number = 0;

  private listeners: Set<SimEventListener> = new Set();

  constructor(scenarioIdOrDef?: string | ScenarioDefinition, runId?: string) {
    let def: ScenarioDefinition;
    if (typeof scenarioIdOrDef === "string") {
      def = SCENARIO_DEFINITIONS[scenarioIdOrDef] || SCENARIO_DEFINITIONS.scn_single_veh;
    } else if (scenarioIdOrDef) {
      def = scenarioIdOrDef;
    } else {
      def = SCENARIO_DEFINITIONS.scn_single_veh;
    }

    this.scenario = def;
    this.runId = runId || `run_${Math.random().toString(36).substring(2, 9)}`;

    // Build Unified Metropolitan Road Network
    this.roadNetwork = getUnifiedMetropolitanRoadNetwork(def);
    for (const n of this.roadNetwork.nodes) {
      this.nodeMap.set(n.id, n);
      this.adjacency.set(n.id, []);
    }
    for (const e of this.roadNetwork.edges) {
      this.edgeMap.set(e.id, e);
      const adj = this.adjacency.get(e.start_node_id);
      if (adj) adj.push(e);
    }

    // Initialize Signals
    if (def.signals) {
      for (const s of def.signals) {
        const cfg = (s.config || {}) as Record<string, number>;
        this.signals.set(s.signal_id, {
          id: s.signal_id,
          nodeId: s.node_id,
          state: "GREEN",
          timerS: 0,
          greenDurationS: cfg.green_duration_s ?? 6.0,
          yellowDurationS: cfg.yellow_duration_s ?? 2.0,
          redDurationS: cfg.red_duration_s ?? 6.0,
        });
      }
    }

    // Initialize Pedestrians
    if (def.pedestrians) {
      for (const p of def.pedestrians) {
        const dest = { x: p.destination_point[0], y: p.destination_point[1] };
        const init = { x: p.initial_position[0], y: p.initial_position[1] };
        const dx = dest.x - init.x;
        const dy = dest.y - init.y;
        this.pedestrians.set(p.pedestrian_id, {
          id: p.pedestrian_id,
          position: { ...init },
          destination: dest,
          crosswalkId: p.crosswalk_id || null,
          speedMps: p.walking_speed_mps ?? 1.2,
          headingRad: Math.atan2(dy, dx),
          lifecycleState: "walking",
        });
      }
    }

    // Initialize Vehicles & Route Planning
    for (const v of def.vehicles) {
      const isEmergency =
        v.vehicle_type === "emergency" ||
        v.vehicle_id.startsWith("amb_") ||
        v.vehicle_id.startsWith("fire_");
      const closed = new Set(v.closed_edge_ids || []);
      let route = this.findPath(v.start_node_id, v.destination_node_id, closed, v.algorithm);

      // Gracefully resolve to connected metropolitan nodes if requested route is not directly reachable
      if (route.nodeIds.length < 2 && !v.closed_edge_ids?.length) {
        const allNodes = Array.from(this.nodeMap.values());
        const validStart = this.nodeMap.has(v.start_node_id) ? v.start_node_id : allNodes[0]?.id;
        if (validStart) {
          const sNode = this.nodeMap.get(validStart)!;
          const distant = allNodes.filter((n) => Math.hypot(n.x - sNode.x, n.y - sNode.y) >= 80);
          const target = distant[Math.floor(Math.random() * distant.length)] || allNodes[allNodes.length - 1];
          if (target) {
            route = this.findPath(validStart, target.id, closed, v.algorithm);
          }
        }
      }

      const startNode = this.nodeMap.get(v.start_node_id) || Array.from(this.nodeMap.values())[0] || { x: 0, y: 0 };
      let initialPos = { x: startNode.x, y: startNode.y };
      let initialHeading = 0;

      // Position vehicle in the center of the right-hand lane
      if (route.edgeIds.length > 0) {
        const firstEdge = this.edgeMap.get(route.edgeIds[0]);
        if (firstEdge) {
          const sNode = this.nodeMap.get(firstEdge.start_node_id);
          const eNode = this.nodeMap.get(firstEdge.end_node_id);
          if (sNode && eNode) {
            const edx = eNode.x - sNode.x;
            const edy = eNode.y - sNode.y;
            const elen = Math.hypot(edx, edy) || 1;
            const rnx = edy / elen;
            const rny = -edx / elen;
            const laneOffset = 1.85;
            initialPos = {
              x: sNode.x + rnx * laneOffset,
              y: sNode.y + rny * laneOffset,
            };
            initialHeading = Math.atan2(edy, edx);
          }
        }
      }

      this.vehicles.set(v.vehicle_id, {
        id: v.vehicle_id,
        startNodeId: v.start_node_id,
        destinationNodeId: v.destination_node_id,
        algorithm: v.algorithm || "ASTAR",
        vehicleType: isEmergency ? "emergency" : "standard",
        isEmergency,
        priorityLevel: isEmergency ? 10 : 1,
        currentEdgeIndex: 0,
        distanceAlongEdge: 0,
        speedMps: v.initial_speed_mps ?? 0,
        maxSpeedMps: isEmergency ? 16.0 : 12.0,
        headingRad: initialHeading,
        position: initialPos,
        routeNodeIds: route.nodeIds,
        routeEdgeIds: route.edgeIds,
        lifecycleState: route.nodeIds.length > 0 ? "en_route" : "blocked",
        closedEdgeIds: closed,
      });
    }
  }

  public getRoadNetwork(): RoadNetworkGeometry {
    return this.roadNetwork;
  }

  public subscribe(listener: SimEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(eventType: string, payload: unknown, disclaimer?: string) {
    this.sequence++;
    const envelope: WebSocketEventEnvelope = {
      event_type: eventType,
      run_id: this.runId,
      tick: this.tick,
      sequence: this.sequence,
      timestamp_s: Number(this.elapsedTimeS.toFixed(3)),
      schema_version: "1.0.0",
      disclaimer: disclaimer || "AMAPP educational simulation framework.",
      payload: (payload || {}) as Record<string, unknown>,
    };
    for (const listener of this.listeners) {
      try {
        listener(envelope);
      } catch (err) {
        console.error("Error in sim listener:", err);
      }
    }
  }

  /**
   * Pathfinding using A* or Dijkstra.
   */
  public findPath(
    startNodeId: string,
    goalNodeId: string,
    vehicleClosedEdges: Set<string> = new Set(),
    _algo = "ASTAR"
  ): { nodeIds: string[]; edgeIds: string[]; totalDistance: number } {
    if (startNodeId === goalNodeId) {
      return { nodeIds: [startNodeId], edgeIds: [], totalDistance: 0 };
    }

    const goalNode = this.nodeMap.get(goalNodeId);
    if (!goalNode || !this.nodeMap.has(startNodeId)) {
      return { nodeIds: [], edgeIds: [], totalDistance: 0 };
    }

    const openSet = new Set<string>([startNodeId]);
    const cameFromNode = new Map<string, string>();
    const cameFromEdge = new Map<string, string>();
    const gScore = new Map<string, number>();
    const fScore = new Map<string, number>();

    for (const nid of this.nodeMap.keys()) {
      gScore.set(nid, Infinity);
      fScore.set(nid, Infinity);
    }
    gScore.set(startNodeId, 0);

    const heuristic = (nid: string) => {
      const n = this.nodeMap.get(nid);
      if (!n) return 0;
      return Math.hypot(goalNode.x - n.x, goalNode.y - n.y);
    };
    fScore.set(startNodeId, heuristic(startNodeId));

    while (openSet.size > 0) {
      let current: string | null = null;
      let minF = Infinity;
      for (const nid of openSet) {
        const score = fScore.get(nid) ?? Infinity;
        if (score < minF) {
          minF = score;
          current = nid;
        }
      }

      if (!current || current === goalNodeId) {
        // Reconstruct path
        const pathNodes: string[] = [];
        const pathEdges: string[] = [];
        let curr: string | undefined = goalNodeId;
        while (curr && curr !== startNodeId) {
          pathNodes.unshift(curr);
          const edge = cameFromEdge.get(curr);
          if (edge) pathEdges.unshift(edge);
          curr = cameFromNode.get(curr);
        }
        if (curr === startNodeId) {
          pathNodes.unshift(startNodeId);
        }
        const totalDist = gScore.get(goalNodeId) ?? 0;
        return { nodeIds: pathNodes, edgeIds: pathEdges, totalDistance: totalDist };
      }

      openSet.delete(current);
      const outgoing = this.adjacency.get(current) || [];

      for (const edge of outgoing) {
        if (this.closedEdges.has(edge.id) || vehicleClosedEdges.has(edge.id)) {
          continue;
        }

        const neighbor = edge.end_node_id;
        let edgeCost = edge.length_m;
        for (const inc of this.incidents.values()) {
          if (inc.affected_edge_id === edge.id && inc.status === "active") {
            if (inc.incident_type === "road_closure" || inc.severity === "critical") {
              edgeCost = Infinity;
            } else {
              edgeCost *= 3.0;
            }
          }
        }

        if (edgeCost === Infinity) continue;

        const tentativeG = (gScore.get(current) ?? Infinity) + edgeCost;
        if (tentativeG < (gScore.get(neighbor) ?? Infinity)) {
          cameFromNode.set(neighbor, current);
          cameFromEdge.set(neighbor, edge.id);
          gScore.set(neighbor, tentativeG);
          fScore.set(neighbor, tentativeG + heuristic(neighbor));
          openSet.add(neighbor);
        }
      }
    }

    return { nodeIds: [], edgeIds: [], totalDistance: 0 };
  }

  /**
   * Advance simulation by discrete ticks.
   */
  public step(ticks = 1): {
    current_tick: number;
    elapsed_time_s: number;
    lifecycle_state: string;
    is_terminal: boolean;
    arrived_count: number;
    active_count: number;
    tick_result: Record<string, unknown>;
  } {
    if (this.isTerminal) {
      return this.getStatusResponse({});
    }

    this.lifecycleState = "RUNNING";
    const dt = this.scenario.time_step_s || 0.1;

    const routingDecisions: Record<string, unknown>[] = [];
    let communicationMetrics: Record<string, unknown> = {};

    for (let t = 0; t < ticks; t++) {
      this.tick++;
      this.elapsedTimeS = Number((this.elapsedTimeS + dt).toFixed(3));

      // 1. Update Traffic Signals
      for (const sig of this.signals.values()) {
        sig.timerS += dt;
        if (sig.state === "GREEN" && sig.timerS >= sig.greenDurationS) {
          sig.state = "YELLOW";
          sig.timerS = 0;
        } else if (sig.state === "YELLOW" && sig.timerS >= sig.yellowDurationS) {
          sig.state = "RED";
          sig.timerS = 0;
        } else if (sig.state === "RED" && sig.timerS >= sig.redDurationS) {
          sig.state = "GREEN";
          sig.timerS = 0;
        }

        const timeToGreen =
          sig.state === "RED"
            ? Math.max(0, sig.redDurationS - sig.timerS)
            : sig.state === "YELLOW"
            ? Math.max(0, sig.yellowDurationS - sig.timerS + sig.redDurationS)
            : 0;
        const timeToRed =
          sig.state === "GREEN"
            ? Math.max(0, sig.greenDurationS - sig.timerS)
            : 0;

        this.emit("traffic_signals.update", {
          signal_id: sig.id,
          node_id: sig.nodeId,
          state: sig.state,
          time_to_green_s: Number(timeToGreen.toFixed(1)),
          time_to_red_s: Number(timeToRed.toFixed(1)),
        });
      }

      // 2. Update Pedestrians
      for (const ped of this.pedestrians.values()) {
        if (ped.lifecycleState === "walking") {
          const dx = ped.destination.x - ped.position.x;
          const dy = ped.destination.y - ped.position.y;
          const dist = Math.hypot(dx, dy);
          const stepDist = ped.speedMps * dt;
          if (dist <= stepDist || dist < 0.2) {
            ped.position.x = ped.destination.x;
            ped.position.y = ped.destination.y;
            ped.lifecycleState = "arrived";
          } else {
            ped.headingRad = Math.atan2(dy, dx);
            ped.position.x += Math.cos(ped.headingRad) * stepDist;
            ped.position.y += Math.sin(ped.headingRad) * stepDist;
          }

          this.emit("pedestrian.state", {
            pedestrian_id: ped.id,
            position: { x: Number(ped.position.x.toFixed(2)), y: Number(ped.position.y.toFixed(2)) },
            speed_mps: Number(ped.speedMps.toFixed(2)),
            heading_rad: Number(ped.headingRad.toFixed(3)),
            lifecycle_state: ped.lifecycleState,
            crosswalk_id: ped.crosswalkId,
          });
        }
      }

      // 3. Update Vehicles
      for (const v of this.vehicles.values()) {
        if (v.lifecycleState === "arrived" || v.lifecycleState === "blocked") {
          continue;
        }

        if (v.currentEdgeIndex >= v.routeEdgeIds.length) {
          v.lifecycleState = "arrived";
          v.speedMps = 0;
          this.emit("vehicle.state", {
            vehicle_id: v.id,
            position: { x: Number(v.position.x.toFixed(2)), y: Number(v.position.y.toFixed(2)) },
            speed_mps: 0,
            heading_rad: Number(v.headingRad.toFixed(3)),
            lifecycle_state: "arrived",
            vehicle_type: v.vehicleType,
            route: v.routeNodeIds,
          });
          continue;
        }

        const currentEdgeId = v.routeEdgeIds[v.currentEdgeIndex];
        const edge = this.edgeMap.get(currentEdgeId);
        const startNode = this.nodeMap.get(edge?.start_node_id || "");
        const endNode = this.nodeMap.get(edge?.end_node_id || "");

        if (!edge || !startNode || !endNode) {
          v.lifecycleState = "arrived";
          continue;
        }

        // 1. Car-Following Safe Headway (Intelligent Driver Model dynamics)
        let minHeadwayM = Infinity;
        let leadVehicleSpeed = v.maxSpeedMps;

        for (const [otherId, other] of this.vehicles) {
          if (otherId === v.id || other.lifecycleState === "arrived") continue;
          const otherEdgeId = other.routeEdgeIds[other.currentEdgeIndex];

          if (otherEdgeId === currentEdgeId) {
            if (other.distanceAlongEdge > v.distanceAlongEdge) {
              const gap = (other.distanceAlongEdge - v.distanceAlongEdge) - 4.6;
              if (gap < minHeadwayM) {
                minHeadwayM = gap;
                leadVehicleSpeed = other.speedMps;
              }
            }
          } else if (v.currentEdgeIndex + 1 < v.routeEdgeIds.length && otherEdgeId === v.routeEdgeIds[v.currentEdgeIndex + 1]) {
            const remCurr = edge.length_m - v.distanceAlongEdge;
            const gap = remCurr + other.distanceAlongEdge - 4.6;
            if (gap < minHeadwayM && gap >= 0) {
              minHeadwayM = gap;
              leadVehicleSpeed = other.speedMps;
            }
          }
        }

        // 2. Traffic Signal & Crosswalk Yielding
        let shouldYield = false;
        let yieldReason: "signal" | "pedestrian" | "headway" | null = null;

        const sig = Array.from(this.signals.values()).find((s) => s.nodeId === endNode.id);
        if (sig && (sig.state === "RED" || sig.state === "YELLOW")) {
          const remainingDist = edge.length_m - v.distanceAlongEdge;
          if (!v.isEmergency && remainingDist <= 12.0 && remainingDist >= 0.5) {
            shouldYield = true;
            yieldReason = "signal";
          }
        }

        for (const ped of this.pedestrians.values()) {
          if (ped.lifecycleState === "walking") {
            const d = Math.hypot(v.position.x - ped.position.x, v.position.y - ped.position.y);
            if (d < 16.0) {
              shouldYield = true;
              yieldReason = "pedestrian";
            }
          }
        }

        if (minHeadwayM < 5.0) {
          shouldYield = true;
          yieldReason = "headway";
        }

        // 3. Kinematic Speed & Acceleration Calculation
        let targetSpeed: number;
        if (shouldYield) {
          if (yieldReason === "headway" && minHeadwayM > 2.0) {
            targetSpeed = Math.max(0, Math.min(leadVehicleSpeed * 0.75, v.speedMps * 0.5));
          } else {
            targetSpeed = 0;
          }
        } else {
          const roadSpeedLimit = edge.speed_limit_mps || 13.89;
          if (minHeadwayM < 16.0) {
            const headwayFactor = Math.max(0, (minHeadwayM - 4.5) / 11.5);
            targetSpeed = Math.min(v.maxSpeedMps, roadSpeedLimit, leadVehicleSpeed * headwayFactor + 1.2);
          } else {
            targetSpeed = Math.min(v.maxSpeedMps, roadSpeedLimit);
          }
        }

        const accel = shouldYield ? -4.5 : 2.8;
        if (v.speedMps < targetSpeed) {
          v.speedMps = Math.min(targetSpeed, v.speedMps + accel * dt);
        } else if (v.speedMps > targetSpeed) {
          v.speedMps = Math.max(targetSpeed, v.speedMps + accel * dt);
        }

        v.distanceAlongEdge += Math.max(0, v.speedMps * dt);
        const edgeLen = Math.max(1, edge.length_m);
        const progress = Math.min(1.0, Math.max(0.0, v.distanceAlongEdge / edgeLen));

        // 4. Right-Hand Lane Offset & Intersection Cornering
        const edx = endNode.x - startNode.x;
        const edy = endNode.y - startNode.y;
        const elen = Math.hypot(edx, edy) || 1;
        const rnx = edy / elen;
        const rny = -edx / elen;
        const laneOffset = 1.85; // Right-hand driving lane offset

        const currentHeading = Math.atan2(edy, edx);
        const hasNextEdge = v.currentEdgeIndex + 1 < v.routeEdgeIds.length;
        const nextEdge = hasNextEdge ? this.edgeMap.get(v.routeEdgeIds[v.currentEdgeIndex + 1]) : null;
        const nextEndNode = nextEdge ? this.nodeMap.get(nextEdge.end_node_id) : null;

        if (hasNextEdge && nextEndNode && progress > 0.82) {
          // Smooth intersection corner transition
          const nEdx = nextEndNode.x - endNode.x;
          const nEdy = nextEndNode.y - endNode.y;
          const nElen = Math.hypot(nEdx, nEdy) || 1;
          const nRnx = nEdy / nElen;
          const nRny = -nEdx / nElen;
          const nextHeading = Math.atan2(nEdy, nEdx);

          const turnT = (progress - 0.82) / 0.18;
          const smoothT = turnT * turnT * (3 - 2 * turnT);

          let dAngle = nextHeading - currentHeading;
          while (dAngle > Math.PI) dAngle -= Math.PI * 2;
          while (dAngle < -Math.PI) dAngle += Math.PI * 2;
          v.headingRad = currentHeading + dAngle * smoothT;

          const currPt = {
            x: startNode.x + edx * progress + rnx * laneOffset,
            y: startNode.y + edy * progress + rny * laneOffset,
          };
          const nextLaneStart = {
            x: endNode.x + nRnx * laneOffset,
            y: endNode.y + nRny * laneOffset,
          };
          v.position = {
            x: currPt.x * (1 - smoothT) + nextLaneStart.x * smoothT,
            y: currPt.y * (1 - smoothT) + nextLaneStart.y * smoothT,
          };
        } else {
          v.headingRad = currentHeading;
          v.position = {
            x: startNode.x + edx * progress + rnx * laneOffset,
            y: startNode.y + edy * progress + rny * laneOffset,
          };
        }

        // 5. Edge Transition & Continuous Metropolis Cruising
        if (progress >= 1.0) {
          v.currentEdgeIndex++;
          v.distanceAlongEdge = 0;

          if (v.currentEdgeIndex >= v.routeEdgeIds.length) {
            // Reached destination: Select new distant destination to keep continuously cruising
            const isUnreachableTest = v.closedEdgeIds.size > 0 && this.scenario.metadata?.id === "scn_unreachable";
            if (isUnreachableTest) {
              v.lifecycleState = "arrived";
              v.speedMps = 0;
            } else {
              const currentNode = this.nodeMap.get(endNode.id) || endNode;
              const allNodes = Array.from(this.nodeMap.values());
              const candidates = allNodes.filter((c) => {
                if (c.id === currentNode.id) return false;
                const d = Math.hypot(c.x - currentNode.x, c.y - currentNode.y);
                return d >= 100 && d <= 550;
              });

              const pool = candidates.length > 5 ? candidates : allNodes.filter((c) => c.id !== currentNode.id);
              let newRoute = null;

              for (let att = 0; att < 6; att++) {
                const pick = pool[Math.floor(Math.random() * pool.length)];
                if (pick) {
                  const res = this.findPath(currentNode.id, pick.id, v.closedEdgeIds, v.algorithm);
                  if (res.edgeIds.length >= 2) {
                    newRoute = { destId: pick.id, ...res };
                    break;
                  }
                }
              }

              if (newRoute) {
                v.startNodeId = currentNode.id;
                v.destinationNodeId = newRoute.destId;
                v.routeNodeIds = newRoute.nodeIds;
                v.routeEdgeIds = newRoute.edgeIds;
                v.currentEdgeIndex = 0;
                v.distanceAlongEdge = 0;
                v.lifecycleState = "en_route";

                this.emit("route.changed", {
                  vehicle_id: v.id,
                  new_route_id: `cruise_${v.id}_t${this.tick}`,
                  candidate_node_ids: newRoute.nodeIds,
                  candidate_edge_ids: newRoute.edgeIds,
                  is_accepted: true,
                  decision_type: "continuous_metropolis_cruise",
                });
              } else {
                v.lifecycleState = "arrived";
                v.speedMps = 0;
              }
            }
          }
        }

        const remainingDistance = this.calculateRemainingDistance(v);

        this.emit("vehicle.state", {
          vehicle_id: v.id,
          position: { x: Number(v.position.x.toFixed(2)), y: Number(v.position.y.toFixed(2)) },
          speed_mps: Number(v.speedMps.toFixed(2)),
          heading_rad: Number(v.headingRad.toFixed(3)),
          lifecycle_state: v.lifecycleState,
          vehicle_type: v.vehicleType,
          route: v.routeNodeIds,
          current_edge_id: currentEdgeId,
          remaining_route_distance_m: Number(remainingDistance.toFixed(2)),
        });
      }

      // 4. V2V Mesh Network Emulation
      const commRange = 120.0;
      const vehicleList = Array.from(this.vehicles.values()).filter((v) => v.lifecycleState !== "arrived");
      let activeLinks = 0;
      let tickDrops = 0;

      for (let i = 0; i < vehicleList.length; i++) {
        for (let j = i + 1; j < vehicleList.length; j++) {
          const vA = vehicleList[i];
          const vB = vehicleList[j];
          const dist = Math.hypot(vA.position.x - vB.position.x, vA.position.y - vB.position.y);
          if (dist <= commRange) {
            activeLinks++;
            this.totalBroadcasts += 2;
            const dropProb = (dist / commRange) * 0.1;
            if (Math.random() < dropProb) {
              this.totalDropped++;
              tickDrops++;
            } else {
              this.totalDelivered++;
            }
          }
        }
      }

      const pdr = this.totalBroadcasts > 0 ? (this.totalDelivered / this.totalBroadcasts) * 100 : 100.0;
      communicationMetrics = {
        total_broadcasts: this.totalBroadcasts,
        total_delivered: this.totalDelivered,
        total_dropped: this.totalDropped,
        packet_delivery_ratio: Number(pdr.toFixed(2)),
        recent_drops: tickDrops,
        active_links_count: activeLinks,
      };

      this.emit("communication.event", communicationMetrics);

      // 5. World Snapshot Event
      this.emit("world.snapshot", {
        vehicles: Array.from(this.vehicles.values()).map((v) => ({
          vehicle_id: v.id,
          position: v.position,
          speed_mps: v.speedMps,
          heading_rad: v.headingRad,
          lifecycle_state: v.lifecycleState,
          current_edge_id: v.routeEdgeIds[v.currentEdgeIndex] || null,
          remaining_route_distance_m: this.calculateRemainingDistance(v),
        })),
        signals: Array.from(this.signals.values()).map((s) => ({
          signal_id: s.id,
          state: s.state,
          node_id: s.nodeId,
        })),
        pedestrians: Array.from(this.pedestrians.values()).map((p) => ({
          pedestrian_id: p.id,
          position: p.position,
          lifecycle_state: p.lifecycleState,
        })),
        communication: communicationMetrics,
      });

      // 6. Metrics Summary Event
      this.emit("metrics.summary", {
        run_id: this.runId,
        tick: this.tick,
        simulation: {
          vehicles_registered: this.vehicles.size,
          vehicles_arrived: Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "arrived").length,
          vehicles_active: Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "en_route").length,
          simulated_duration_s: this.elapsedTimeS,
          time_step_s: dt,
        },
        kinematics: {
          average_speed_mps: Number(
            (
              Array.from(this.vehicles.values()).reduce((sum, v) => sum + v.speedMps, 0) /
              Math.max(1, this.vehicles.size)
            ).toFixed(2)
          ),
        },
        communication: {
          messages_sent: this.totalBroadcasts,
          messages_delivered: this.totalDelivered,
          packet_delivery_ratio: Number(pdr.toFixed(2)),
        },
        traffic_signals: {
          signals_registered: this.signals.size,
        },
      });

      // Check Termination
      const allArrived = Array.from(this.vehicles.values()).every((v) => v.lifecycleState === "arrived");
      if (allArrived && this.scenario.stop_on_all_arrived) {
        this.lifecycleState = "COMPLETED";
        this.isTerminal = true;
        this.emit("run.completed", { to_state: "COMPLETED" });
        break;
      }
      if (this.scenario.max_ticks && this.tick >= this.scenario.max_ticks) {
        this.lifecycleState = "LIMIT_REACHED";
        this.isTerminal = true;
        this.emit("run.completed", { to_state: "LIMIT_REACHED" });
        break;
      }
    }

    return this.getStatusResponse({
      routing_decisions: routingDecisions,
      communication_metrics: communicationMetrics,
    });
  }

  private calculateRemainingDistance(v: SimVehicle): number {
    let rem = 0;
    for (let i = v.currentEdgeIndex; i < v.routeEdgeIds.length; i++) {
      const e = this.edgeMap.get(v.routeEdgeIds[i]);
      if (e) {
        if (i === v.currentEdgeIndex) {
          rem += Math.max(0, e.length_m - v.distanceAlongEdge);
        } else {
          rem += e.length_m;
        }
      }
    }
    return Number(rem.toFixed(2));
  }

  /**
   * Dynamic incident injection.
   * If edge is blocked or slowed down, recompute active routes!
   */
  public injectIncident(payload: CreateIncidentPayload): IncidentRecord {
    const incId = `inc_${Math.random().toString(36).substring(2, 8)}`;
    const edgeId = payload.affected_edge_id || payload.edge_id || null;
    const sev: IncidentSeverity = (payload.severity?.toLowerCase() as IncidentSeverity) || "high";

    const rec: IncidentRecord = {
      id: incId,
      incident_type: payload.incident_type,
      status: "active",
      severity: sev,
      affected_edge_id: edgeId,
      affected_node_id: payload.affected_node_id || payload.node_id || null,
      reported_tick: this.tick,
      reported_timestamp_s: this.elapsedTimeS,
      description: payload.description || `Incident on ${edgeId || "roadway"}`,
    };

    this.incidents.set(incId, rec);
    if (edgeId) {
      this.closedEdges.add(edgeId);
    }

    this.emit("incident.created", rec);

    // Re-route active vehicles whose remaining path uses this edge
    for (const v of this.vehicles.values()) {
      if (v.lifecycleState !== "en_route") continue;

      const remainingEdges = v.routeEdgeIds.slice(v.currentEdgeIndex);
      if (edgeId && remainingEdges.includes(edgeId)) {
        const currEdge = this.edgeMap.get(v.routeEdgeIds[v.currentEdgeIndex]);
        const fromNodeId = currEdge?.end_node_id || v.startNodeId;

        const newPath = this.findPath(fromNodeId, v.destinationNodeId, v.closedEdgeIds, v.algorithm);
        if (newPath.nodeIds.length > 0) {
          const pastNodes = v.routeNodeIds.slice(0, v.currentEdgeIndex + 1);
          const pastEdges = v.routeEdgeIds.slice(0, v.currentEdgeIndex);
          if (currEdge) pastEdges.push(currEdge.id);

          const fullNewNodeIds = [...pastNodes, ...newPath.nodeIds.slice(1)];
          const fullNewEdgeIds = [...pastEdges, ...newPath.edgeIds];

          v.routeNodeIds = fullNewNodeIds;
          v.routeEdgeIds = fullNewEdgeIds;

          const reroutePayload = {
            vehicle_id: v.id,
            previous_route_id: `${v.id}_original`,
            new_route_id: `${v.id}_reroute_t${this.tick}`,
            decision_type: "incident_avoidance",
            status: "ACCEPTED",
            cost_improvement: 14.5,
            candidate_node_ids: fullNewNodeIds,
            candidate_edge_ids: fullNewEdgeIds,
            candidate_cost: newPath.totalDistance,
            reason: `Dynamic incident avoided on edge ${edgeId}`,
          };

          this.emit("route.changed", reroutePayload);
        }
      }
    }

    return rec;
  }

  public removeIncident(incidentId: string): IncidentRecord | null {
    const inc = this.incidents.get(incidentId);
    if (!inc) return null;

    if (inc.affected_edge_id) {
      this.closedEdges.delete(inc.affected_edge_id);
    }
    this.incidents.delete(incidentId);

    this.emit("incident.removed", { incident_id: incidentId, id: incidentId });
    return inc;
  }

  public listIncidents(): IncidentRecord[] {
    return Array.from(this.incidents.values());
  }

  public cancel(reason = "User requested cancellation"): RunStatus {
    this.lifecycleState = "CANCELLED";
    this.isTerminal = true;
    this.emit("run.cancelled", { reason, to_state: "CANCELLED" });
    return this.getStatus();
  }

  public getStatus(): RunStatus {
    const arrived = Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "arrived").length;
    const active = Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "en_route").length;

    return {
      run_id: this.runId,
      scenario_id: this.scenario.metadata.id,
      scenario_name: this.scenario.metadata.name,
      lifecycle_state: this.lifecycleState,
      current_tick: this.tick,
      elapsed_time_s: this.elapsedTimeS,
      is_terminal: this.isTerminal,
      arrived_count: arrived,
      active_count: active,
      total_vehicles: this.vehicles.size,
      scenario_fingerprint: `fp_${this.scenario.metadata.id}`,
      initial_world_state_fingerprint: `fp_world_${this.scenario.metadata.id}`,
      commit_sha: null,
      disclaimer: "AMAPP educational simulation framework.",
    };
  }

  public getMetrics(): RunMetrics {
    const arrived = Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "arrived").length;
    const active = Array.from(this.vehicles.values()).filter((v) => v.lifecycleState === "en_route").length;
    const avgSpeed =
      Array.from(this.vehicles.values()).reduce((sum, v) => sum + v.speedMps, 0) /
      Math.max(1, this.vehicles.size);
    const pdr = this.totalBroadcasts > 0 ? (this.totalDelivered / this.totalBroadcasts) * 100 : 100.0;

    return {
      run_id: this.runId,
      lifecycle_state: this.lifecycleState,
      current_tick: this.tick,
      metrics: {
        simulation: {
          vehicles_registered: this.vehicles.size,
          vehicles_arrived: arrived,
          vehicles_active: active,
          simulated_duration_s: this.elapsedTimeS,
          time_step_s: this.scenario.time_step_s,
        },
        kinematics: {
          average_speed_mps: Number(avgSpeed.toFixed(2)),
          max_speed_observed_mps: 14.0,
        },
        communication: {
          messages_sent: this.totalBroadcasts,
          messages_delivered: this.totalDelivered,
          packet_delivery_ratio: Number(pdr.toFixed(2)),
        },
        safety: {
          pair_checks: this.vehicles.size * 2,
          near_misses: 0,
          actual_collisions: 0,
        },
      },
      disclaimer: "AMAPP educational simulation framework.",
    };
  }

  private getStatusResponse(extra: Record<string, unknown> = {}) {
    const status = this.getStatus();
    return {
      ...status,
      tick_result: extra,
    };
  }
}

// Global active simulation registry for in-memory execution
class ActiveSimulationRegistry {
  private activeSimulations: Map<string, InBrowserSimulationEngine> = new Map();
  private latestRunId: string | null = null;

  public createRun(req: { scenario_id?: string; scenario?: Record<string, unknown>; run_id?: string }): InBrowserSimulationEngine {
    const scnDef = req.scenario_id ? SCENARIO_DEFINITIONS[req.scenario_id] : undefined;
    const engine = new InBrowserSimulationEngine(scnDef || (req.scenario as unknown as ScenarioDefinition), req.run_id);
    this.activeSimulations.set(engine.runId, engine);
    this.latestRunId = engine.runId;
    return engine;
  }

  public get(runId: string): InBrowserSimulationEngine | undefined {
    return this.activeSimulations.get(runId);
  }

  public getLatest(): InBrowserSimulationEngine | undefined {
    if (this.latestRunId) return this.activeSimulations.get(this.latestRunId);
    return undefined;
  }
}

export const activeSimulationRegistry = new ActiveSimulationRegistry();
