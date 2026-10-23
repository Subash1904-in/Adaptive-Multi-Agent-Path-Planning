import { config, destinations } from './config.js';
import { RoadGraph } from './graph.js';
import { findRoute } from './routing.js';
import { VehicleAgent } from './vehicle.js';
import { V2VCommunication } from './communication.js';
import { ScenarioManager } from './scenarios.js';

function distanceToRouteNode(graph, agent, nodeIndex) {
  let distance = 0;
  for (let index = agent.index; index < nodeIndex; index += 1) {
    const from = graph.node(agent.route[index]);
    const edge = from?.edges.find((candidate) => candidate.to === agent.route[index + 1]);
    if (!edge) return Infinity;
    distance += edge.length * (index === agent.index ? 1 - agent.progress : 1);
  }
  return distance;
}

function axisForEdge(from, to) {
  return Math.abs(to.x - from.x) >= Math.abs(to.z - from.z) ? 'horizontal' : 'vertical';
}

function movementAtNode(graph, agent, nodeId) {
  const index = agent.index;
  let incomingId, outgoingId;
  if (nodeId === agent.route[index] && index > 0) {
    incomingId = agent.route[index - 1];
    outgoingId = agent.route[index + 1];
  } else if (nodeId === agent.route[index + 1]) {
    incomingId = agent.route[index];
    outgoingId = agent.route[index + 2] ?? nodeId;
  } else return null;

  const node = graph.node(nodeId);
  const incoming = graph.node(incomingId);
  const outgoing = graph.node(outgoingId);
  if (!node || !incoming || !outgoing) return null;
  const incomingAxis = axisForEdge(incoming, node);
  const hasOutgoingLeg = nodeId === agent.route[index + 1]
    && index + 2 < agent.route.length;
  const outgoingAxis = hasOutgoingLeg ? axisForEdge(node, outgoing) : incomingAxis;
  const direction = (from, to, axis) => Math.sign(axis === 'horizontal' ? to.x - from.x : to.z - from.z);
  return {
    incomingAxis,
    outgoingAxis,
    incomingDirection: direction(incoming, node, incomingAxis),
    outgoingDirection: hasOutgoingLeg
      ? direction(node, outgoing, outgoingAxis)
      : direction(incoming, node, incomingAxis),
    turning: incomingAxis !== outgoingAxis,
  };
}

function movementsConflict(a, b) {
  const sameMovement = a.incomingAxis === b.incomingAxis
    && a.outgoingAxis === b.outgoingAxis
    && a.incomingDirection === b.incomingDirection
    && a.outgoingDirection === b.outgoingDirection;
  if (sameMovement) return false;
  if (!a.turning && !b.turning && a.incomingAxis === b.incomingAxis) return false;
  return true;
}

const PRESENTATION_STAGES = ['vehicle-encounter', 'emergency', 'blockage', 'conflict', 'no-conflict'];
const QUICK_PRESENTATION_STAGES = PRESENTATION_STAGES;

/** Owns shared simulation state and coordinates the domain modules each tick. */
export class Simulation {
  constructor() {
    this.scenarios = new ScenarioManager();
    this.reset();
  }

  reset() {
    this.graph = new RoadGraph();
    this.time = 0;
    this.running = true;
    this.rate = 1;
    this.events = [];
    this.totalReroutes = 0;
    this.completed = 0;
    this.nextMessageId = 1;
    this.mode = 'normal';
    this.modeExpiresAt = 0;
    this.automaticScenarioIndex = 0;
    this.nextAutomaticScenarioAt = config.scenarios.automaticScenarioIntervalSeconds > 0
      ? config.scenarios.automaticScenarioIntervalSeconds
      : Infinity;
    this.blockage = null;
    this.traffic = null;
    this.suddenBraking = null;
    this.pendingSuddenBrakingAt = null;
    this.suddenBrakingAttempted = false;
    this.totalSuddenBrakingEvents = 0;
    this.featureJourney = null;
    this.vehicleEncounter = null;
    this.noConflictPair = null;
    this.intersectionConflict = null;
    this.intersectionReservations = new Map();
    this.emergencyExpiresAt = 0;
    this.conflictPredictions = 0;
    this.presentationSequence = null;
    this.event = 'Normal traffic flow';
    this.eventDetail = 'Vehicles are following assigned routes.';
    this.communication = new V2VCommunication();
    this.agents = Array.from(
      { length: config.vehicles.count },
      (_, index) => new VehicleAgent(index, this.graph, findRoute),
    );
  }

  tick(frameSeconds) {
    if (!this.running) return;
    const dt = Math.min(Math.max(frameSeconds, 0), config.vehicles.maxFrameSeconds) * this.rate;
    this.time += dt;
    this.communication.pruneLinks(this.time);

    if (this.blockage && this.time >= this.blockage.expires) {
      this.graph.setBlocked(...this.blockage.edge, false);
      this.blockage = null;
      this.mode = 'normal';
      this.event = 'Road reopened';
      this.eventDetail = 'The temporary road closure has ended.';
      this.log('Road blockage cleared; the segment is open again.');
    }

    if (this.traffic && this.time + 1e-9 >= this.traffic.expires) {
      const [fromId, toId] = this.traffic.edge;
      const edges = [
        ...this.graph.node(fromId).edges.filter((edge) => edge.to === toId),
        ...this.graph.node(toId).edges.filter((edge) => edge.to === fromId),
      ];
      edges.forEach((edge, index) => { edge.speedKmh = this.traffic.originalSpeeds[index]; });
      this.traffic = null;
      this.mode = 'normal';
      this.event = 'Traffic clearing';
      this.eventDetail = 'The temporary congestion has eased and normal road speeds are restored.';
      this.log('Congestion cleared; road speeds returned to their configured limits.');
    }

    if (this.mode !== 'normal' && this.time >= this.modeExpiresAt && !this.blockage) {
      this.mode = 'normal';
    }
    this.updateIntersectionConflict();
    this.advancePresentationSequence();

    const scenarioInterval = config.scenarios.automaticScenarioIntervalSeconds;
    if (scenarioInterval > 0 && this.mode === 'normal' && this.time >= this.nextAutomaticScenarioAt) {
      const automaticScenarios = [
        () => this.triggerBlockage(),
        () => this.triggerEmergency(),
        () => this.triggerConflict(),
      ];
      automaticScenarios[this.automaticScenarioIndex % automaticScenarios.length]();
      this.automaticScenarioIndex += 1;
      this.nextAutomaticScenarioAt = this.time + scenarioInterval;
    }

    this.resolveCrossTraffic();
    for (const agent of this.agents) this.advanceAgent(agent, dt);
    if (this.pendingSuddenBrakingAt !== null && this.time >= this.pendingSuddenBrakingAt) {
      this.pendingSuddenBrakingAt = null;
      this.triggerSuddenBraking();
    }
  }

  startPresentationSequence({ quick = false } = {}) {
    this.presentationSequence = {
      stage: 'baseline',
      index: -1,
      stages: quick ? QUICK_PRESENTATION_STAGES : PRESENTATION_STAGES,
      quick,
      startedAt: this.time,
      finished: false,
    };
    this.mode = 'normal';
    this.event = 'Normal traffic baseline';
    this.eventDetail = quick
      ? 'A short run will show a vehicle encounter, emergency priority, road blockage, intersection coordination, and a no-conflict control.'
      : 'The full fleet is moving on independent routes before the everyday-city traffic scenarios begin.';
    this.log(`Presentation run started with normal traffic${quick ? ' (quick demo)' : ''}.`);
  }

  startSuddenBraking() {
    this.suddenBraking = null;
    this.suddenBrakingAttempted = false;
    this.pendingSuddenBrakingAt = this.time + config.scenarios.suddenBrakingLeadInSeconds;
    this.event = 'Traffic moving · sudden-braking scenario armed';
    this.eventDetail = `Vehicles establish moving traffic; a following vehicle will receive a sudden-braking alert in ${config.scenarios.suddenBrakingLeadInSeconds} seconds if it is within V2V range.`;
    this.log('Sudden-braking scenario armed; waiting for traffic to move.');
  }

  triggerSuddenBraking() {
    this.scenarios.triggerSuddenBraking(this);
  }

  skipPresentationStage() {
    const sequence = this.presentationSequence;
    if (!sequence || sequence.finished) return false;
    const stage = sequence.stage;
    this.log(`Presenter skipped the ${stage} stage.`);
    if (sequence.index < 0) {
      this.startPresentationStage(0);
      return true;
    }

    sequence.skipRequested = true;
    if (stage === 'traffic') {
      if (this.traffic) this.traffic.expires = this.time;
      sequence.startedAt = this.time - 2;
    } else if (stage === 'emergency') {
      this.emergencyExpiresAt = this.time;
      for (const agent of this.agents) {
        if (agent.status !== 'Yielding to emergency unit') continue;
        agent.yieldUntil = this.time;
        agent.moveAsideForEmergency = false;
        agent.status = 'Following assigned route';
      }
    } else if (stage === 'conflict') {
      this.modeExpiresAt = this.time;
      sequence.startedAt = this.time - config.scenarios.intersectionHoldSeconds;
    } else if (stage === 'sudden-braking') {
      this.pendingSuddenBrakingAt = null;
      this.suddenBrakingAttempted = true;
      this.modeExpiresAt = this.time;
      for (const agent of this.agents) {
        if (!agent.status.startsWith('Braking')) continue;
        agent.suddenBrakeUntil = this.time;
        agent.suddenBrakeTargetSpeedKmh = 0;
        agent.status = 'Following assigned route';
      }
      this.suddenBraking = null;
    } else if (stage === 'vehicle-encounter') {
      const follower = this.agents.find((agent) => agent.id === this.vehicleEncounter?.followerId);
      if (follower) follower.encounterUntil = this.time;
      sequence.startedAt = this.time - (sequence.quick
        ? config.scenarios.quickPresentationEncounterSeconds
        : config.scenarios.presentationEncounterSeconds);
    } else if (stage === 'no-conflict') {
      sequence.startedAt = this.time - (sequence.quick
        ? config.scenarios.quickPresentationNoConflictSeconds
        : config.scenarios.presentationNoConflictSeconds);
    } else if (stage === 'blockage' && this.blockage) this.blockage.expires = this.time;
    if (stage === 'blockage') sequence.startedAt = this.time - 2;
    else if (['flyover', 'ring', 'uturn'].includes(stage)) {
      const timeoutSeconds = sequence.quick
        ? config.scenarios.quickFeatureStageTimeoutSeconds
        : config.scenarios.featureStageTimeoutSeconds;
      sequence.startedAt = this.time - timeoutSeconds;
    }
    return true;
  }

  advancePresentationSequence() {
    const sequence = this.presentationSequence;
    if (!sequence || sequence.finished) return;
    const elapsed = this.time - sequence.startedAt;
    if (sequence.index < 0) {
      const baselineSeconds = sequence.quick
        ? config.scenarios.quickPresentationBaselineSeconds
        : config.scenarios.presentationBaselineSeconds;
      if (elapsed < baselineSeconds) return;
      this.startPresentationStage(0);
      return;
    }

    const current = sequence.stage;
    let complete = false;
    let timedOutFocus = null;
    if (current === 'vehicle-encounter') {
      const duration = sequence.quick
        ? config.scenarios.quickPresentationEncounterSeconds
        : config.scenarios.presentationEncounterSeconds;
      complete = elapsed >= duration;
    } else if (current === 'no-conflict') {
      const duration = sequence.quick
        ? config.scenarios.quickPresentationNoConflictSeconds
        : config.scenarios.presentationNoConflictSeconds;
      complete = elapsed >= duration;
    } else if (current === 'traffic') complete = !this.traffic && elapsed >= 2;
    else if (current === 'emergency') complete = this.time >= this.emergencyExpiresAt;
    else if (current === 'conflict') {
      complete = !this.intersectionConflict && elapsed >= config.scenarios.intersectionHoldSeconds;
    } else if (current === 'sudden-braking') {
      complete = this.suddenBrakingAttempted
        && (!this.suddenBraking || this.time >= this.modeExpiresAt);
    } else if (current === 'blockage') complete = !this.blockage && elapsed >= 2;
    else if (['flyover', 'ring', 'uturn'].includes(current)) {
      const focus = this.agents.find((agent) => agent.id === this.featureJourney?.agentId);
      complete = Boolean(focus?.arrived);
      const timeoutSeconds = sequence.quick
        ? config.scenarios.quickFeatureStageTimeoutSeconds
        : config.scenarios.featureStageTimeoutSeconds;
      if (!complete && elapsed >= timeoutSeconds) {
        timedOutFocus = focus;
        if (sequence.skipRequested) {
          this.log(`${current} presentation stage skipped; the vehicle journey continues.`);
        } else {
          this.log(`${current} presentation stage timed out; the vehicle journey continues.`);
        }
        complete = true;
      }
    }
    if (!complete) return;
    if (sequence.index + 1 < sequence.stages.length) {
      this.startPresentationStage(sequence.index + 1);
      if (timedOutFocus) timedOutFocus.status = 'Journey continues after presentation timeout';
      return;
    }
    if (timedOutFocus) timedOutFocus.status = 'Journey continues after presentation timeout';
    sequence.finished = true;
    this.running = false;
    this.event = 'Presentation run complete';
    this.eventDetail = sequence.quick
      ? 'The quick demo finished after showing normal traffic, a vehicle encounter, emergency priority, blockage rerouting, intersection coordination, and a no-conflict control.'
      : 'The fleet finished the everyday-city traffic scenarios and the no-conflict control.';
    this.log(`Presentation scenario sequence completed${sequence.quick ? ' (quick demo)' : ''}.`);
  }

  startPresentationStage(index) {
    const sequence = this.presentationSequence;
    const stage = sequence.stages[index];
    sequence.index = index;
    sequence.stage = stage;
    sequence.startedAt = this.time;
    sequence.skipRequested = false;
    this.featureJourney = null;
    if (stage !== 'vehicle-encounter') this.vehicleEncounter = null;
    if (stage !== 'no-conflict') this.noConflictPair = null;
    const trafficDuration = sequence.quick ? config.scenarios.quickTrafficDurationSeconds : undefined;
    const emergencyDuration = sequence.quick ? config.scenarios.quickEmergencyPrioritySeconds : undefined;
    const blockageDuration = sequence.quick ? config.scenarios.quickBlockageDurationSeconds : undefined;
    if (stage === 'vehicle-encounter') this.triggerVehicleEncounter();
    else if (stage === 'no-conflict') this.triggerNoConflict();
    else if (stage === 'traffic') this.triggerTraffic(trafficDuration);
    else if (stage === 'emergency') this.triggerEmergency(emergencyDuration);
    else if (stage === 'conflict') this.triggerConflict();
    else if (stage === 'sudden-braking') this.startSuddenBraking();
    else if (stage === 'blockage') this.triggerBlockage(blockageDuration);
    else this.startJourney(stage);
    if (stage === 'traffic' && !this.traffic) {
      sequence.startedAt -= trafficDuration ?? config.scenarios.trafficDurationSeconds;
    }
    if (stage === 'blockage' && !this.blockage) {
      sequence.startedAt -= blockageDuration ?? config.scenarios.blockageDurationSeconds;
    }
    if (stage === 'conflict' && sequence.quick) {
      this.modeExpiresAt = Math.min(
        this.modeExpiresAt,
        this.time + config.scenarios.quickConflictHoldSeconds,
      );
    }
  }

  resolveCrossTraffic() {
    const candidatesByNode = new Map();
    const guardDistance = config.scenarios.intersectionGuardDistanceMeters;
    const occupancyRadius = config.scenarios.intersectionOccupancyRadiusMeters;

    for (const agent of this.agents) {
      if (agent.arrived || agent.index >= agent.route.length - 1) continue;
      const fromId = agent.route[agent.index];
      const toId = agent.route[agent.index + 1];
      const from = this.graph.node(fromId);
      const to = this.graph.node(toId);
      const edge = this.graph.neighbors(fromId).find((candidate) => candidate.to === toId);
      if (!from || !to || !edge) continue;
      const endpoints = [
        { nodeId: fromId, distance: agent.progress * edge.length, inside: agent.index > 0 },
        { nodeId: toId, distance: (1 - agent.progress) * edge.length, inside: false },
      ];
      for (const endpoint of endpoints) {
        if (endpoint.distance > guardDistance) continue;
        // An agent leaving a junction should reserve it only while its body is
        // still inside the conflict area; otherwise it can hold stale priority
        // while queued on the road beyond the crossing.
        if (endpoint.inside && endpoint.distance > occupancyRadius) continue;
        const node = this.graph.node(endpoint.nodeId);
        if (!node || Math.abs((node.y ?? 0) - (from.y ?? 0)) > 2) continue;
        const movement = movementAtNode(this.graph, agent, endpoint.nodeId);
        if (!movement) continue;
        const candidate = {
          agent,
          ...movement,
          // Vehicles cannot pass one another in a lane. Give the whole
          // approach queue the lead vehicle's junction priority decision.
          approachKey: `${movement.incomingAxis}:${movement.incomingDirection}`,
          distance: endpoint.distance,
          inside: endpoint.inside && endpoint.distance <= occupancyRadius,
          eta: endpoint.distance / Math.max(agent.speed / 3.6, 2),
        };
        if (!candidatesByNode.has(endpoint.nodeId)) candidatesByNode.set(endpoint.nodeId, []);
        candidatesByNode.get(endpoint.nodeId).push(candidate);
      }
    }

    this.crossTrafficYields = new Map();
    const reservations = new Map();
    for (const [nodeId, candidates] of candidatesByNode) {
      const approaches = new Map();
      for (const candidate of candidates) {
        if (!approaches.has(candidate.approachKey)) approaches.set(candidate.approachKey, []);
        approaches.get(candidate.approachKey).push(candidate);
      }
      const queues = [...approaches].map(([key, queue]) => {
        queue.sort((a, b) => a.distance - b.distance);
        return { key, candidates: queue, lead: queue[0] };
      });
      const existing = this.intersectionReservations.get(nodeId);
      const owner = existing && queues.find((queue) => queue.key === existing.approachKey
        || queue.candidates.some((candidate) => candidate.agent.id === existing.ownerId));
      const scenarioPriority = this.intersectionConflict?.nodeId === nodeId
        ? queues.find((queue) => queue.candidates.some((candidate) => candidate.agent.id
          === this.intersectionConflict.priorityVehicleId)) : null;
      const occupying = queues.flatMap((queue) => queue.candidates
        .filter((candidate) => candidate.inside))
        .sort((a, b) => a.distance - b.distance)[0];
      const priority = scenarioPriority ?? owner
        ?? queues.find((queue) => queue.candidates.includes(occupying))
        ?? queues.sort((a, b) => a.lead.eta - b.lead.eta
          || a.lead.agent.id.localeCompare(b.lead.agent.id))[0];
      if (!priority) continue;
      reservations.set(nodeId, { ownerId: priority.lead.agent.id, approachKey: priority.key });
      for (const queue of queues) {
        if (queue.key === priority.key || !movementsConflict(priority.lead, queue.lead)) continue;
        for (const candidate of queue.candidates) {
          if (candidate.inside) continue;
          const previous = this.crossTrafficYields.get(candidate.agent.id);
          if (!previous || candidate.distance < previous.distance) {
            this.crossTrafficYields.set(candidate.agent.id, candidate);
          }
        }
      }
    }
    this.intersectionReservations = reservations;
    if (this.intersectionConflict) {
      this.crossTrafficYields.delete(this.intersectionConflict.priorityVehicleId);
    }
  }

  advanceAgent(agent, dt) {
    if (agent.arrived) return;
    const desiredLaneOffset = agent.yieldUntil > this.time && agent.moveAsideForEmergency
      ? config.vehicles.yieldLaneOffsetMeters
      : config.vehicles.laneOffsetMeters;
    const lateralStep = config.vehicles.laneChangeRateMps * dt;
    const lateralDifference = desiredLaneOffset - agent.laneOffsetMeters;
    agent.laneOffsetMeters += Math.sign(lateralDifference)
      * Math.min(Math.abs(lateralDifference), lateralStep);
    let edge = agent.route.slice(agent.index, agent.index + 2);
    if (edge.length === 2 && this.graph.isBlocked(...edge)) {
      const edgeKey = this.graph.edgeKey(...edge);
      if (agent.lastBlockedEdge !== edgeKey) {
        agent.lastBlockedEdge = edgeKey;
        this.replan(agent, 'local blockage detection');
        edge = agent.route.slice(agent.index, agent.index + 2);
      }
    } else {
      agent.lastBlockedEdge = null;
    }

    const currentEdge = edge.length === 2
      ? this.graph.neighbors(edge[0]).find((candidate) => candidate.to === edge[1])
      : null;
    let targetSpeed = currentEdge?.speedKmh ?? 0;
    if (agent.type === 'Ambulance' && currentEdge?.type === 'arterial') {
      targetSpeed = agent.maxSpeed;
    } else {
      targetSpeed = Math.min(targetSpeed, agent.maxSpeed);
    }

    // Respect the next junction: compute a safe approach speed from remaining
    // braking distance so the vehicle slows before a turn, not at the corner.
    const nextEdge = agent.route.length - agent.index > 2
      ? this.graph.neighbors(agent.route[agent.index + 1])
        .find((candidate) => candidate.to === agent.route[agent.index + 2])
      : null;
    if (currentEdge && nextEdge) {
      const from = this.graph.node(agent.route[agent.index]);
      const junction = this.graph.node(agent.route[agent.index + 1]);
      const onward = this.graph.node(agent.route[agent.index + 2]);
      const incoming = { x: junction.x - from.x, z: junction.z - from.z };
      const outgoing = { x: onward.x - junction.x, z: onward.z - junction.z };
      const directionDot = (incoming.x * outgoing.x + incoming.z * outgoing.z)
        / (Math.hypot(incoming.x, incoming.z) * Math.hypot(outgoing.x, outgoing.z));
      const isTurn = directionDot < 0 || Math.abs(directionDot) < 0.95;
      if (isTurn) {
        const distanceToJunction = (1 - agent.progress) * currentEdge.length;
        const turnSpeedMps = config.vehicles.turnSpeedKmh / 3.6;
        const safeSpeedKmh = Math.sqrt(
          turnSpeedMps ** 2 + 2 * config.vehicles.turnDecelerationMps2 * distanceToJunction,
        ) * 3.6;
        targetSpeed = Math.min(targetSpeed, safeSpeedKmh);
      }
    }

    const position = agent.position(this.graph);
    if (position) {
      for (const other of this.agents) {
        if (other === agent || other.arrived) continue;
        const sameDirectedEdge = agent.route[agent.index] === other.route[other.index]
          && agent.route[agent.index + 1] === other.route[other.index + 1];
        const samePathAcrossJunction = agent.route[agent.index + 1] === other.route[other.index]
          && agent.route[agent.index + 2] === other.route[other.index + 1];
        if (!sameDirectedEdge && !samePathAcrossJunction) continue;
        if (sameDirectedEdge && agent.progress >= other.progress) continue;
        const otherPosition = other.position(this.graph);
        if (!otherPosition) continue;
        const separation = Math.hypot(position.x - otherPosition.x, position.z - otherPosition.z);
        if (separation >= config.vehicles.followingDistanceMeters) continue;
        const gapFactor = Math.max(0, (separation - config.vehicles.minimumFollowingGapMeters)
          / (config.vehicles.followingDistanceMeters - config.vehicles.minimumFollowingGapMeters));
        targetSpeed = Math.min(targetSpeed, other.speed * gapFactor);
      }
    }

    const crossTrafficYield = this.crossTrafficYields?.get(agent.id);
    if (crossTrafficYield) {
      const stopOffset = config.scenarios.intersectionStopLineOffsetMeters
        + (crossTrafficYield.turning ? config.vehicles.turnRadiusMeters + 3 : 0);
      const metersToStopLine = Math.max(
        0,
        crossTrafficYield.distance - stopOffset,
      );
      const safeApproachSpeed = Math.sqrt(
        2 * config.vehicles.brakingMps2 * metersToStopLine,
      ) * 3.6;
      targetSpeed = Math.min(targetSpeed, safeApproachSpeed);
      agent.status = 'Waiting for cross traffic';
    } else if (agent.status === 'Waiting for cross traffic') {
      agent.status = 'Following assigned route';
    }

    const conflict = this.intersectionConflict;
    if (conflict?.yieldingVehicleId === agent.id) {
      const metersToJunction = distanceToRouteNode(this.graph, agent, conflict.yieldingNodeIndex);
      const metersToStopLine = Math.max(0, metersToJunction - config.scenarios.intersectionStopLineOffsetMeters);
      const safeApproachSpeed = Math.sqrt(2 * config.vehicles.brakingMps2 * metersToStopLine) * 3.6;
      targetSpeed = Math.min(targetSpeed, safeApproachSpeed);
    } else if (agent.yieldUntil > this.time) {
      targetSpeed = Math.min(targetSpeed, config.scenarios.emergencyYieldSpeedKmh);
    } else if (agent.status.startsWith('Yielding')) {
      agent.status = 'Following assigned route';
    }

    if (agent.suddenBrakeUntil > this.time) {
      targetSpeed = Math.min(targetSpeed, agent.suddenBrakeTargetSpeedKmh);
    } else if (agent.status.startsWith('Braking')) {
      agent.status = 'Following assigned route';
    }

    if (agent.encounterLeaderId && agent.encounterUntil > this.time) {
      const leader = this.agents.find((candidate) => candidate.id === agent.encounterLeaderId);
      if (leader && !leader.arrived) {
        targetSpeed = Math.min(
          targetSpeed,
          Math.max(8, leader.speed * config.scenarios.vehicleEncounterSpeedFactor),
        );
        agent.status = `V2V headway response behind ${leader.id}`;
      }
    } else if (agent.encounterLeaderId) {
      if (agent.status.startsWith('V2V headway response')) agent.status = 'Following assigned route';
      agent.encounterLeaderId = null;
      agent.encounterUntil = 0;
    }

    const previousIndex = agent.index;
    const previousProgress = agent.progress;
    const previousEdge = this.graph.node(agent.route[previousIndex])?.edges
      .find((candidate) => candidate.to === agent.route[previousIndex + 1]);
    const arrived = agent.advance(this.graph, dt, targetSpeed);
    if (arrived) {
      this.completed += 1;
      agent.completedTripTimeSeconds = agent.tripElapsedSeconds + dt;
      this.log(`${agent.id} arrived at ${agent.destination.name}.`);
    }
    agent.tripElapsedSeconds += dt;
    let distanceThisStep = 0;
    if (previousEdge) {
      if (agent.index === previousIndex) {
        distanceThisStep = (agent.progress - previousProgress) * previousEdge.length;
      } else if (agent.index === previousIndex + 1) {
        distanceThisStep = (1 - previousProgress) * previousEdge.length;
      }
    }
    agent.distanceTravelledMeters += Math.max(0, distanceThisStep);
    this.enforceFollowingGap(agent);
  }

  enforceFollowingGap(agent) {
    if (agent.arrived || agent.index >= agent.route.length - 1) return;
    const fromId = agent.route[agent.index];
    const toId = agent.route[agent.index + 1];
    const from = this.graph.node(fromId);
    const edge = from.edges.find((candidate) => candidate.to === toId);
    if (!edge) return;
    const minimumProgressGap = config.vehicles.minimumFollowingGapMeters / edge.length;
    for (const other of this.agents) {
      if (other === agent || other.arrived
        || other.route[other.index] !== fromId
        || other.route[other.index + 1] !== toId) continue;
      if (agent.progress >= other.progress) continue;
      const maximumProgress = other.progress - minimumProgressGap;
      if (agent.progress <= maximumProgress) continue;
      agent.progress = Math.max(0, maximumProgress);
      agent.speed = Math.min(agent.speed, other.speed);
    }
  }

  updateIntersectionConflict() {
    const conflict = this.intersectionConflict;
    if (!conflict) return;
    const priority = this.agents.find((agent) => agent.id === conflict.priorityVehicleId);
    const yielding = this.agents.find((agent) => agent.id === conflict.yieldingVehicleId);
    const priorityPassed = !priority
      || priority.route.indexOf(conflict.nodeId) < 0
      || priority.index > conflict.priorityNodeIndex;
    const expired = this.time >= this.modeExpiresAt;
    if (!priorityPassed && !expired) return;
    if (yielding) {
      yielding.yieldUntil = 0;
      if (yielding.status === 'Yielding at intersection') yielding.status = 'Intersection clear · proceeding';
    }
    this.intersectionConflict = null;
    if (priorityPassed) {
      this.event = 'Intersection clear';
      this.eventDetail = `${conflict.priorityVehicleId} passed junction ${conflict.nodeId}; ${conflict.yieldingVehicleId} may proceed.`;
    }
  }

  position(agent) {
    return agent.position(this.graph);
  }

  replan(agent, reason) {
    const currentNode = agent.route[agent.index];
    const nextNode = agent.route[agent.index + 1];
    const currentEdge = nextNode
      && this.graph.neighbors(currentNode).find((edge) => edge.to === nextNode);
    let route;
    let keepCurrentEdge = false;
    if (currentEdge && !this.graph.isBlocked(currentNode, nextNode)) {
      const continuation = findRoute(this.graph, nextNode, agent.destination.node);
      if (continuation.length) {
        route = [
          ...agent.route.slice(0, agent.index + 2),
          ...continuation.slice(1),
        ];
        keepCurrentEdge = true;
      }
    }
    route ??= findRoute(this.graph, currentNode, agent.destination.node);
    if (route.length > 1) {
      const plannedRoute = [...agent.route.slice(0, agent.index), ...route];
      const routeUnchanged = plannedRoute.length === agent.route.length
        && plannedRoute.every((nodeId, index) => nodeId === agent.route[index]);
      if (routeUnchanged && reason.toLowerCase().includes('traffic')) {
        agent.status = 'Delay accepted · current route remains faster';
        return false;
      }
      agent.route = plannedRoute;
      if (!keepCurrentEdge) {
        agent.progress = 0;
        agent.speed = 0;
      }
      agent.replans += 1;
      agent.routeChangedAt = this.time;
      agent.replanningVisualAt = this.time + config.communication.roleHighlightSeconds;
      agent.replanningVisualUntil = this.time + config.rendering.adaptiveRouteDisplaySeconds;
      agent.lastBlockedEdge = null;
      agent.status = `Route updated · ${reason}`;
      this.totalReroutes += 1;
      this.log(`${agent.id} recalculated a valid route to ${agent.destination.name}.`);
      return true;
    }

    agent.status = 'No safe route · holding';
    return false;
  }

  log(text) {
    this.events.unshift({ time: this.time, text });
    this.events.length = Math.min(this.events.length, 24);
  }

  triggerBlockage(durationSeconds) {
    this.scenarios.triggerBlockage(this, durationSeconds);
  }

  triggerEmergency(durationSeconds) {
    this.scenarios.triggerEmergency(this, durationSeconds);
  }

  triggerConflict() {
    this.scenarios.triggerConflict(this);
  }

  triggerVehicleEncounter() {
    return this.scenarios.triggerVehicleEncounter(this);
  }

  triggerNoConflict() {
    this.scenarios.triggerNoConflict(this);
  }

  startJourney(scenario) {
    this.scenarios.startJourney(this, scenario);
  }

  triggerTraffic(durationSeconds) {
    this.scenarios.triggerTraffic(this, durationSeconds);
  }

  get messages() {
    return this.communication.messages;
  }

  get links() {
    return this.communication.links;
  }

  get metrics() {
    const active = this.agents.filter((agent) => !agent.arrived);
    const completedTrips = this.agents.filter((agent) => (
      agent.arrived && Number.isFinite(agent.completedTripTimeSeconds)
    ));
    return {
      active: active.length,
      arrived: this.completed,
      mean: active.length
        ? active.reduce((sum, agent) => sum + agent.speed, 0) / active.length
        : 0,
      reroutes: this.totalReroutes,
      distanceTravelledKm: this.agents.reduce(
        (sum, agent) => sum + agent.distanceTravelledMeters, 0,
      ) / 1000,
      meanTripSeconds: completedTrips.length
        ? completedTrips.reduce((sum, agent) => sum + agent.completedTripTimeSeconds, 0) / completedTrips.length
        : null,
      deliveredHops: this.communication.deliveredHops,
      sentHops: this.communication.sentHops,
      receivedHops: this.communication.receivedHops,
      meanLatencyMs: this.communication.deliveredHops
        ? this.communication.totalLatencyMs / this.communication.deliveredHops
        : null,
      conflictPredictions: this.conflictPredictions,
      suddenBrakingEvents: this.totalSuddenBrakingEvents,
    };
  }
}
