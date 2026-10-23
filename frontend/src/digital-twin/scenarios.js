import { config } from './config.js';
import { findRoute } from './routing.js';

function routeDistanceToNode(simulation, agent, nodeIndex) {
  if (nodeIndex <= agent.index) return 0;
  let distance = 0;
  for (let index = agent.index; index < nodeIndex; index += 1) {
    const from = simulation.graph.node(agent.route[index]);
    const edge = from?.edges.find((candidate) => candidate.to === agent.route[index + 1]);
    if (!edge) return Infinity;
    distance += edge.length * (index === agent.index ? 1 - agent.progress : 1);
  }
  return distance;
}

function predictedSpeed(simulation, agent) {
  const from = simulation.graph.node(agent.route[agent.index]);
  const edge = from?.edges.find((candidate) => candidate.to === agent.route[agent.index + 1]);
  return Math.max(18, agent.speed, Math.min(agent.maxSpeed, edge?.speedKmh ?? 40) * 0.65);
}

function pointSegmentDistance(point, from, to) {
  const dx = to.x - from.x;
  const dz = to.z - from.z;
  const denominator = dx * dx + dz * dz;
  const t = denominator ? Math.max(0, Math.min(1, ((point.x - from.x) * dx + (point.z - from.z) * dz) / denominator)) : 0;
  return Math.hypot(point.x - (from.x + dx * t), point.z - (from.z + dz * t));
}

function predictedIntersections(simulation, first, second, lookAhead, maxEtaDifference) {
  const candidates = [];
  const firstEnd = Math.min(first.route.length - 1, first.index + lookAhead);
  const secondEnd = Math.min(second.route.length - 1, second.index + lookAhead);
  for (let firstIndex = first.index + 1; firstIndex <= firstEnd; firstIndex += 1) {
    for (let secondIndex = second.index + 1; secondIndex <= secondEnd; secondIndex += 1) {
      if (first.route[firstIndex] !== second.route[secondIndex]) continue;
      const junction = simulation.graph.node(first.route[firstIndex]);
      const firstBefore = simulation.graph.node(first.route[firstIndex - 1]);
      const secondBefore = simulation.graph.node(second.route[secondIndex - 1]);
      const firstDirection = { x: junction.x - firstBefore.x, z: junction.z - firstBefore.z };
      const secondDirection = { x: junction.x - secondBefore.x, z: junction.z - secondBefore.z };
      const cross = Math.abs(firstDirection.x * secondDirection.z - firstDirection.z * secondDirection.x);
      if (cross < 0.05) continue;
      const firstDistance = routeDistanceToNode(simulation, first, firstIndex);
      const secondDistance = routeDistanceToNode(simulation, second, secondIndex);
      const firstEta = firstDistance / (predictedSpeed(simulation, first) / 3.6);
      const secondEta = secondDistance / (predictedSpeed(simulation, second) / 3.6);
      const etaDifference = Math.abs(firstEta - secondEta);
      if (etaDifference <= maxEtaDifference) {
        candidates.push({
          nodeId: junction.id,
          firstEta,
          secondEta,
          etaDifference,
          firstIndex,
          secondIndex,
          score: Math.max(firstEta, secondEta) + etaDifference * 2,
        });
      }
    }
  }
  return candidates.sort((a, b) => a.score - b.score);
}

function updateRecipientMessage(receiver, message, decision, content) {
  message.decision = decision;
  message.content = content;
  message.payload = { ...message.payload, content };
  receiver.lastAlertDecision = decision;
}

/** Applies scenario events to simulation state and real road/vehicle decisions. */
export class ScenarioManager {
  triggerVehicleEncounter(simulation) {
    const candidates = [];
    for (const leader of simulation.agents) {
      if (leader.arrived || leader.index >= leader.route.length - 1) continue;
      for (const follower of simulation.agents) {
        if (leader === follower || follower.arrived
          || leader.route[leader.index] !== follower.route[follower.index]
          || leader.route[leader.index + 1] !== follower.route[follower.index + 1]
          || leader.progress <= follower.progress) continue;
        const leaderPosition = simulation.position(leader);
        const followerPosition = simulation.position(follower);
        if (!leaderPosition || !followerPosition) continue;
        const gap = Math.hypot(
          leaderPosition.x - followerPosition.x,
          leaderPosition.z - followerPosition.z,
        );
        if (gap < config.vehicles.minimumFollowingGapMeters
          || gap >= config.vehicles.followingDistanceMeters
          || !simulation.communication.canReach(simulation.graph, leader, follower)) continue;
        candidates.push({ leader, follower, gap, leaderPosition, followerPosition });
      }
    }

    candidates.sort((a, b) => Math.abs(a.gap - config.vehicles.followingDistanceMeters * 0.75)
      - Math.abs(b.gap - config.vehicles.followingDistanceMeters * 0.75));
    const encounter = candidates[0];
    if (!encounter) {
      simulation.vehicleEncounter = null;
      simulation.event = 'No close same-lane pair available';
      simulation.eventDetail = 'The encounter alert was not triggered because no same-lane pair was within the configured following gap and V2V range.';
      simulation.log('Vehicle encounter not triggered; no eligible same-lane pair was available.');
      return false;
    }

    const { leader, follower, gap, leaderPosition, followerPosition } = encounter;
    const delivered = simulation.communication.send(
      simulation,
      leader,
      follower,
      'Vehicle encounter alert',
      `Slowing behind ${leader.id} to maintain following distance`,
      {
        eventLocation: {
          x: (leaderPosition.x + followerPosition.x) / 2,
          y: (leaderPosition.y + followerPosition.y) / 2,
          z: (leaderPosition.z + followerPosition.z) / 2,
        },
        content: `${follower.id} received ${leader.id}'s close-traffic alert at a ${gap.toFixed(1)} m gap and is easing speed to maintain headway.`,
      },
    );
    if (!delivered) return false;

    follower.encounterLeaderId = leader.id;
    follower.encounterUntil = simulation.time + config.scenarios.vehicleEncounterResponseSeconds;
    follower.status = `V2V headway response behind ${leader.id}`;
    simulation.vehicleEncounter = {
      leaderId: leader.id,
      followerId: follower.id,
      gap,
      point: {
        x: (leaderPosition.x + followerPosition.x) / 2,
        y: (leaderPosition.y + followerPosition.y) / 2,
        z: (leaderPosition.z + followerPosition.z) / 2,
      },
    };
    simulation.event = 'Close vehicle encounter · following response';
    simulation.eventDetail = `${leader.id} alerted ${follower.id} at ${gap.toFixed(1)} m; the receiver is easing speed behind the lead vehicle.`;
    simulation.log(`${follower.id} received a close-traffic alert from ${leader.id} and began a headway response.`);
    return true;
  }

  triggerNoConflict(simulation) {
    const nearbyPairs = [];
    for (let firstIndex = 0; firstIndex < simulation.agents.length; firstIndex += 1) {
      const first = simulation.agents[firstIndex];
      if (first.arrived) continue;
      for (let secondIndex = firstIndex + 1; secondIndex < simulation.agents.length; secondIndex += 1) {
        const second = simulation.agents[secondIndex];
        if (second.arrived || !simulation.communication.canReach(simulation.graph, first, second)) continue;
        if (predictedIntersections(
          simulation,
          first,
          second,
          config.scenarios.emergencyLookAheadNodes,
          config.scenarios.intersectionConflictWindowSeconds,
        ).length) continue;
        nearbyPairs.push({
          first,
          second,
          gap: simulation.communication.distanceBetween(simulation.graph, first, second),
        });
      }
    }
    nearbyPairs.sort((a, b) => a.gap - b.gap);
    const pair = nearbyPairs[0];
    simulation.noConflictPair = pair ? {
      firstId: pair.first.id,
      secondId: pair.second.id,
    } : null;
    simulation.mode = 'normal';
    simulation.event = 'No conflict predicted · no intervention';
    simulation.eventDetail = pair
      ? `${pair.first.id} and ${pair.second.id} have no overlapping crossing prediction in the current look-ahead; no alert or route change is issued.`
      : 'No overlapping crossing prediction is present in the current look-ahead; vehicles continue on their assigned routes without an alert.';
    simulation.log(pair
      ? `No conflict predicted for ${pair.first.id} and ${pair.second.id}; both continue on their assigned routes.`
      : 'No conflict predicted; vehicles continue on their assigned routes without an alert.');
  }

  startJourney(simulation, scenario) {
    const agent = simulation.agents[0];
    if (!agent || scenario === 'normal') {
      simulation.mode = 'normal';
      simulation.event = 'Normal city traffic';
      simulation.eventDetail = 'Vehicles follow their own destinations through the connected street network.';
      return;
    }

    const graph = simulation.graph;
    let start;
    let required = [];
    let focusNodeId;
    const ring = (index) => `ring:${index}`;
    if (scenario === 'flyover') {
      start = '2,-2';
      required = [
        ...Array.from({ length: config.world.flyoverGraphSegments - 1 }, (_, index) => `flyover:${index + 1}`),
        '2,2',
      ];
      focusNodeId = 'flyover:10';
    } else if (scenario === 'ring') {
      start = ring(0);
      required = [ring(0), ...Array.from({ length: config.world.ringRoadSegments }, (_, index) => ring(index + 1))];
      required[required.length - 1] = ring(0);
      focusNodeId = ring(0);
    } else if (scenario === 'uturn') {
      // Follow the dedicated median-opening pocket and return to the junction
      // on the opposite heading before continuing to the assigned destination.
      start = '0,0';
      required = ['0,-1', ...Array.from(
        { length: config.world.uTurnSegments + 1 }, (_, index) => `uturn:${index}`,
      ), '0,-1'];
      focusNodeId = `uturn:${Math.floor(config.world.uTurnSegments / 2)}`;
    } else if (scenario === 'underpass') {
      const x = config.world.underpassLocationBlocks;
      start = `${x},-2`;
      required = Array.from(
        { length: config.world.underpassGraphSegments - 1 },
        (_, index) => `underpass:${index + 1}`,
      );
      required.push(`${x},2`);
      focusNodeId = `underpass:${Math.floor(config.world.underpassGraphSegments / 2)}`;
    } else if (scenario === 'traffic') {
      this.triggerTraffic(simulation);
      return;
    } else {
      return;
    }

    const destination = agent.destination.node;
    if (agent.arrived) {
      agent.arrived = false;
      simulation.completed = Math.max(0, simulation.completed - 1);
    }
    let route = [start];
    let cursor = start;
    for (const waypoint of required) {
      const leg = findRoute(graph, cursor, waypoint);
      if (!leg.length) break;
      route.push(...leg.slice(1));
      cursor = waypoint;
    }
    const finalLeg = findRoute(graph, cursor, destination);
    if (finalLeg.length) route.push(...finalLeg.slice(1));
    if (route.length < 2 || route.at(-1) !== destination) {
      simulation.event = 'Scenario route unavailable';
      simulation.eventDetail = `No connected route currently reaches ${agent.destination.name}.`;
      return;
    }

    agent.start = start;
    agent.route = route;
    agent.index = 0;
    agent.progress = 0.04;
    agent.speed = 0;
    agent.tripElapsedSeconds = 0;
    agent.completedTripTimeSeconds = null;
    agent.arrived = false;
    agent.status = `Following route via ${scenario === 'uturn' ? 'U-turn' : scenario}`;
    simulation.featureJourney = { scenario, agentId: agent.id, focusNodeId };
    simulation.mode = scenario;
    simulation.modeExpiresAt = Infinity;
    simulation.event = scenario === 'uturn'
      ? 'U-turn maneuver'
      : scenario === 'ring' ? 'Ring-road journey'
        : scenario === 'underpass' ? 'Underpass journey' : 'Flyover journey';
    simulation.eventDetail = scenario === 'uturn'
      ? `${agent.id} follows the marked U-turn pocket at ${config.world.uTurnSpeedKmh} km/h, rejoins the junction, then continues to ${agent.destination.name}.`
      : scenario === 'underpass'
        ? `${agent.id} descends below the crossing street, follows the connected underpass, and rises back to street level toward ${agent.destination.name}.`
      : `${agent.id} follows connected roads via the ${scenario} toward ${agent.destination.name}.`;
    simulation.log(`${agent.id} began a destination route via ${scenario}.`);
  }

  triggerTraffic(simulation, durationSeconds = config.scenarios.trafficDurationSeconds) {
    if (simulation.traffic) return;
    const usage = new Map();
    for (const agent of simulation.agents) {
      if (agent.arrived) continue;
      // Pick congestion where cars are physically present. Upcoming route
      // demand helps break ties, but must not pull the camera toward an empty
      // segment that vehicles only plan to use later.
      for (let index = agent.index; index < Math.min(agent.route.length - 1, agent.index + 3); index += 1) {
        const a = agent.route[index];
        const b = agent.route[index + 1];
        const key = simulation.graph.edgeKey(a, b);
        const item = usage.get(key) ?? { edge: [a, b], occupied: 0, approaching: 0 };
        if (index === agent.index) item.occupied += 1;
        else item.approaching += 1;
        usage.set(key, item);
      }
    }
    const busiest = [...usage.values()]
      .filter((item) => item.occupied > 0)
      .sort((a, b) => (b.occupied * 3 + b.approaching) - (a.occupied * 3 + a.approaching)
        || b.occupied - a.occupied)[0];
    if (!busiest) return;
    const [fromId, toId] = busiest.edge;
    const segmentKey = simulation.graph.edgeKey(fromId, toId);
    const vehiclesOnSegment = simulation.agents.filter((agent) => !agent.arrived
      && simulation.graph.edgeKey(agent.route[agent.index], agent.route[agent.index + 1]) === segmentKey).length;
    const matchingEdges = [
      ...simulation.graph.node(fromId).edges.filter((edge) => edge.to === toId),
      ...simulation.graph.node(toId).edges.filter((edge) => edge.to === fromId),
    ];
    const originalSpeeds = matchingEdges.map((edge) => edge.speedKmh);
    for (const edge of matchingEdges) edge.speedKmh = config.scenarios.trafficSpeedKmh;
    const from = simulation.graph.node(fromId);
    const to = simulation.graph.node(toId);
    const point = { x: (from.x + to.x) / 2, y: ((from.y ?? 0) + (to.y ?? 0)) / 2, z: (from.z + to.z) / 2 };
    simulation.traffic = {
      edge: busiest.edge,
      point,
      originalSpeeds,
      vehiclesOnSegment,
      expires: simulation.time + durationSeconds,
    };
    simulation.mode = 'traffic';
    simulation.modeExpiresAt = simulation.traffic.expires;
    simulation.event = 'Congestion detected';
    simulation.eventDetail = `${vehiclesOnSegment} vehicles occupy segment ${fromId} to ${toId}; speed is reduced to ${config.scenarios.trafficSpeedKmh} km/h while nearby vehicles receive route advice.`;
    const sender = simulation.agents.find((agent) => agent.route.slice(agent.index).some((node, index, route) => (
      index < route.length - 1 && simulation.graph.edgeKey(node, route[index + 1]) === simulation.graph.edgeKey(...busiest.edge)
    )));
    if (sender) {
      sender.status = 'Traffic detected · broadcasting delay';
      const targets = [];
      for (const receiver of simulation.agents) {
        if (receiver === sender || receiver.arrived) continue;
        const route = receiver.route.slice(receiver.index);
        const affected = route.some((node, index) => index < route.length - 1
          && simulation.graph.edgeKey(node, route[index + 1]) === simulation.graph.edgeKey(...busiest.edge));
        const approaches = route.slice(0, config.scenarios.trafficLookAheadNodes)
          .some((node, index, route) => index < route.length - 1
            && simulation.graph.edgeKey(node, route[index + 1]) === simulation.graph.edgeKey(...busiest.edge));
        if (!approaches) continue;
        targets.push({
          agent: receiver,
          replan: affected,
          decision: affected ? 'Replanning around congestion' : 'Approaching with caution',
          content: affected
            ? `${receiver.id} received the delay alert for ${fromId} to ${toId}; ${vehiclesOnSegment} vehicles are moving at ${config.scenarios.trafficSpeedKmh} km/h, so it is checking an alternate route.`
            : `${receiver.id} is near congestion on ${fromId} to ${toId}, but its route avoids the segment; it continues on its assigned route.`,
        });
      }
      simulation.communication.propagate(
        simulation,
        sender,
        'Traffic delay alert',
        { edge: busiest.edge, eventLocation: point },
        targets,
        (receiver, target, message) => {
          if (!target.replan) return;
          const replanned = simulation.replan(receiver, 'V2V traffic update');
          if (replanned) {
            updateRecipientMessage(
              receiver,
              message,
              'Rerouting around congestion',
              `${receiver.id} received the congestion alert and recalculated a route that avoids ${fromId} to ${toId}.`,
            );
          } else if (receiver.status.startsWith('Delay accepted')) {
            const decision = 'Staying on route · detour would take longer';
            updateRecipientMessage(
              receiver,
              message,
              decision,
              `${receiver.id} compared the detour with the congested route and is staying because it is quicker.`,
            );
            simulation.log(`${receiver.id} stayed on its route because the detour would take longer.`);
          } else {
            updateRecipientMessage(
              receiver,
              message,
              'Holding · no safe detour',
              `${receiver.id} could not find a safe alternate route around ${fromId} to ${toId} and is holding.`,
            );
          }
        },
      );
      simulation.log(`${sender.id} shared a congestion warning for ${busiest.edge.join(' → ')}.`);
    }
    simulation.featureJourney = { scenario: 'traffic', agentId: sender?.id ?? null, focusNodeId: fromId };
  }

  triggerBlockage(simulation, durationSeconds = config.scenarios.blockageDurationSeconds) {
    if (simulation.blockage) return;
    const sender = simulation.agents.find((agent) => !agent.arrived && agent.route.length > agent.index + 2);
    if (!sender) return;

    const edge = [sender.route[sender.index + 1], sender.route[sender.index + 2]];
    const [from, to] = edge.map((id) => simulation.graph.node(id));
    if (!from || !to) return;

    simulation.graph.setBlocked(...edge);
    simulation.blockage = {
      edge,
      point: { x: (from.x + to.x) / 2, y: ((from.y ?? 0) + (to.y ?? 0)) / 2, z: (from.z + to.z) / 2 },
      expires: simulation.time + durationSeconds,
      senderId: sender.id,
      replannedVehicleIds: [],
      focusVehicleId: null,
    };
    simulation.mode = 'blockage';
    simulation.modeExpiresAt = simulation.blockage.expires;
    simulation.event = 'Road blockage detected';
    simulation.eventDetail = `Road segment ${edge.join(' → ')} is closed; nearby affected vehicles are being alerted.`;
    sender.status = 'Hazard detected · broadcasting alert';
    simulation.log(`${sender.id} detected a blockage on road segment ${edge.join(' → ')}.`);

    const targets = [];
    for (const receiver of simulation.agents) {
      if (receiver === sender || receiver.arrived) continue;
      const affected = receiver.route.slice(receiver.index).some((nodeId, index, route) => (
        index < route.length - 1
        && simulation.graph.edgeKey(nodeId, route[index + 1]) === simulation.graph.edgeKey(...edge)
      ));
      const approaching = receiver.route
        .slice(receiver.index, receiver.index + config.scenarios.blockageAlertLookAheadNodes)
        .includes(edge[0]);
      if (!affected && !approaching) continue;

      targets.push({
        agent: receiver,
        replan: affected,
        decision: affected ? 'Replanning around closed segment' : 'Approaching with caution',
        content: affected
          ? `${receiver.id} received a closure alert for ${edge.join(' → ')} and is checking a route around it.`
          : `${receiver.id} is approaching ${edge[0]}, but its route avoids the closed segment; it continues on its assigned route.`,
      });
    }

    simulation.communication.propagate(
      simulation,
      sender,
      'Road blockage alert',
      { edge, eventLocation: simulation.blockage.point },
      targets,
      (receiver, target, message) => {
        if (!target.replan) return;
        if (simulation.replan(receiver, 'V2V blockage alert')) {
          updateRecipientMessage(
            receiver,
            message,
            'Rerouting around road closure',
            `${receiver.id} recalculated a valid route that avoids closed segment ${edge.join(' → ')}.`,
          );
          simulation.blockage.replannedVehicleIds.push(receiver.id);
        } else {
          updateRecipientMessage(
            receiver,
            message,
            'Holding · no safe detour',
            `${receiver.id} could not find a safe alternate route around ${edge.join(' → ')} and is holding.`,
          );
        }
      },
    );

    if (simulation.replan(sender, 'local hazard detection')) {
      simulation.blockage.replannedVehicleIds.push(sender.id);
    }
    const hazardX = simulation.blockage.point.x * config.world.roadSpacing;
    const hazardZ = simulation.blockage.point.z * config.world.roadSpacing;
    const focus = simulation.blockage.replannedVehicleIds
      .map((id) => simulation.agents.find((agent) => agent.id === id))
      .filter(Boolean)
      .map((agent) => ({
        agent,
        position: simulation.position(agent),
      }))
      .filter((item) => item.position)
      .sort((a, b) => Math.hypot(a.position.x - hazardX, a.position.z - hazardZ)
        - Math.hypot(b.position.x - hazardX, b.position.z - hazardZ))[0];
    simulation.blockage.focusVehicleId = focus?.agent.id ?? sender.id;
    simulation.blockage.replannedVehicleIds = [...new Set(simulation.blockage.replannedVehicleIds)];
  }

  triggerEmergency(simulation, durationSeconds = config.scenarios.emergencyPrioritySeconds) {
    const emergency = simulation.agents[config.vehicles.emergencyIndex];
    if (!emergency) return;
    simulation.mode = 'emergency';
    simulation.emergencyExpiresAt = simulation.time + durationSeconds;
    simulation.modeExpiresAt = simulation.emergencyExpiresAt;
    simulation.event = 'Emergency vehicle approaching';
    simulation.eventDetail = 'Nearby vehicles receive the ambulance approach and yield only when their route is affected.';

    if (emergency.arrived) {
      emergency.arrived = false;
      simulation.completed = Math.max(0, simulation.completed - 1);
      emergency.start = '-4,0';
      emergency.route = findRoute(simulation.graph, emergency.start, emergency.destination.node);
      emergency.index = 0;
      emergency.progress = 0;
      emergency.tripElapsedSeconds = 0;
      emergency.completedTripTimeSeconds = null;
    }
    emergency.status = 'Emergency response · priority route active';
    simulation.log(`${emergency.id} broadcast its approach and intended route.`);

    const live = simulation.agents.filter((agent) => !agent.arrived);
    const targets = [];
    for (const receiver of live) {
      if (receiver === emergency) continue;
      const corridorDistance = this.distanceToEmergencyCorridor(simulation, emergency, receiver);
      const crossing = predictedIntersections(
        simulation,
        emergency,
        receiver,
        config.scenarios.emergencyLookAheadNodes,
        config.scenarios.intersectionConflictWindowSeconds,
      )[0];
      const shouldYield = corridorDistance <= config.scenarios.emergencyCorridorWidthMeters || Boolean(crossing);
      if (!shouldYield) continue;
      const holdSeconds = crossing
        ? Math.min(config.scenarios.intersectionMaxHoldSeconds, crossing.firstEta + 5)
        : config.scenarios.emergencyPrioritySeconds;
      targets.push({
        agent: receiver,
        decision: corridorDistance <= config.scenarios.emergencyCorridorWidthMeters
          ? 'Moving aside for ambulance'
          : 'Waiting at crossing for ambulance',
        content: corridorDistance <= config.scenarios.emergencyCorridorWidthMeters
          ? `${receiver.id} received ${emergency.id}'s approach alert and is moving toward the road edge to clear its route.`
          : `${receiver.id} received ${emergency.id}'s approach alert and is holding before the crossing until it passes.`,
        eventLocation: crossing ? simulation.graph.node(crossing.nodeId) : null,
        holdSeconds,
        moveAside: corridorDistance <= config.scenarios.emergencyCorridorWidthMeters,
      });
    }
    simulation.communication.propagate(
      simulation,
      emergency,
      'Emergency approach',
      { route: emergency.route, eventLocation: null },
      targets,
      (receiver, target) => {
        receiver.yieldUntil = simulation.time + target.holdSeconds;
        receiver.moveAsideForEmergency = target.moveAside;
        receiver.status = 'Yielding to emergency unit';
      },
    );
  }

  triggerSuddenBraking(simulation) {
    simulation.suddenBrakingAttempted = true;
    const candidates = [];
    for (const leader of simulation.agents) {
      if (leader.arrived || leader.index >= leader.route.length - 1) continue;
      for (const follower of simulation.agents) {
        if (leader === follower || follower.arrived
          || leader.route[leader.index] !== follower.route[follower.index]
          || leader.route[leader.index + 1] !== follower.route[follower.index + 1]
          || leader.progress <= follower.progress) continue;
        const leaderPosition = simulation.position(leader);
        const followerPosition = simulation.position(follower);
        if (!leaderPosition || !followerPosition) continue;
        const gap = Math.hypot(
          leaderPosition.x - followerPosition.x,
          leaderPosition.z - followerPosition.z,
        );
        if (gap < config.vehicles.minimumFollowingGapMeters
          || gap > config.communication.rangeMeters) continue;
        candidates.push({ leader, follower, gap });
      }
    }

    candidates.sort((a, b) => Math.abs(a.gap - 20) - Math.abs(b.gap - 20));
    const pair = candidates[0];
    if (!pair) {
      simulation.modeExpiresAt = simulation.time;
      simulation.event = 'No connected following pair available';
      simulation.eventDetail = 'The sudden-braking event was not triggered because no same-lane follower was within V2V range.';
      simulation.log('Sudden-braking event not triggered; no eligible connected following pair was available.');
      return;
    }

    const { leader, follower, gap } = pair;
    const delivered = simulation.communication.send(
      simulation,
      leader,
      follower,
      'Sudden braking alert',
      'Braking after lead vehicle deceleration',
      {
        content: `${leader.id} is braking in-lane; ${follower.id} is reducing speed at a ${gap.toFixed(1)} m gap.`,
      },
    );
    if (!delivered) {
      simulation.modeExpiresAt = simulation.time;
      simulation.event = 'Sudden-braking alert not delivered';
      simulation.eventDetail = 'The selected vehicles are no longer within direct V2V range; no receiver response was applied.';
      simulation.log(`${leader.id}'s sudden-braking alert could not reach ${follower.id}.`);
      return;
    }

    leader.suddenBrakeUntil = simulation.time + config.scenarios.suddenBrakingHoldSeconds;
    leader.suddenBrakeTargetSpeedKmh = 0;
    leader.status = 'Braking suddenly';
    follower.suddenBrakeUntil = simulation.time + config.scenarios.suddenBrakingResponseSeconds;
    follower.suddenBrakeTargetSpeedKmh = Math.max(
      8,
      leader.speed * config.scenarios.suddenBrakingResponseSpeedFactor,
    );
    follower.status = `Braking after ${leader.id} V2V warning`;
    simulation.suddenBraking = { leaderId: leader.id, followerId: follower.id, gap };
    simulation.totalSuddenBrakingEvents += 1;
    simulation.mode = 'sudden-braking';
    simulation.modeExpiresAt = follower.suddenBrakeUntil;
    simulation.event = 'Sudden braking · following vehicle responding';
    simulation.eventDetail = `${leader.id} braked in-lane; ${follower.id} received the alert at ${gap.toFixed(1)} m and is slowing.`;
    simulation.log(`${leader.id} braked suddenly; ${follower.id} received the V2V alert and reduced its target speed.`);
  }

  distanceToEmergencyCorridor(simulation, emergency, receiver) {
    const vehicle = receiver.position(simulation.graph);
    if (!vehicle) return Infinity;
    const route = emergency.route.slice(emergency.index, emergency.index + config.scenarios.emergencyLookAheadNodes + 1);
    let minimum = Infinity;
    for (let index = 0; index < route.length - 1; index += 1) {
      const from = simulation.graph.node(route[index]);
      const to = simulation.graph.node(route[index + 1]);
      if (!from || !to) continue;
      minimum = Math.min(minimum, pointSegmentDistance(
        vehicle,
        { x: from.x * config.world.roadSpacing, z: from.z * config.world.roadSpacing },
        { x: to.x * config.world.roadSpacing, z: to.z * config.world.roadSpacing },
      ));
    }
    return minimum;
  }

  triggerConflict(simulation) {
    simulation.intersectionConflict = null;
    const live = simulation.agents.filter((agent) => !agent.arrived);
    const candidates = [];
    for (let firstIndex = 0; firstIndex < live.length; firstIndex += 1) {
      for (let secondIndex = firstIndex + 1; secondIndex < live.length; secondIndex += 1) {
        const first = live[firstIndex];
        const second = live[secondIndex];
        for (const crossing of predictedIntersections(
          simulation,
          first,
          second,
          4,
          config.scenarios.intersectionConflictWindowSeconds,
        )) {
          if (!simulation.communication.canReach(simulation.graph, first, second)) continue;
          candidates.push({ first, second, crossing });
          break;
        }
      }
    }

    candidates.sort((a, b) => a.crossing.score - b.crossing.score);
    const candidate = candidates[0];
    if (!candidate) {
      simulation.mode = 'conflict';
      simulation.modeExpiresAt = simulation.time + config.scenarios.intersectionHoldSeconds;
      simulation.event = 'No immediate intersection conflict predicted';
      simulation.eventDetail = 'Vehicles continue because no connected pair has overlapping arrival windows.';
      simulation.log('Intersection prediction found no immediate crossing conflict.');
      return;
    }

    const { first, second, crossing } = candidate;
    const firstArrivesFirst = crossing.firstEta <= crossing.secondEta;
    const priorityVehicle = firstArrivesFirst ? first : second;
    const yieldingVehicle = firstArrivesFirst ? second : first;
    const priorityNodeIndex = firstArrivesFirst ? crossing.firstIndex : crossing.secondIndex;
    const yieldingNodeIndex = firstArrivesFirst ? crossing.secondIndex : crossing.firstIndex;
    const junction = simulation.graph.node(crossing.nodeId);
    const delivered = simulation.communication.send(
      simulation,
      priorityVehicle,
      yieldingVehicle,
      'Intersection conflict prediction',
      `Yield at ${junction.id} · estimated arrival separation ${crossing.etaDifference.toFixed(1)} s`,
      {
        eventLocation: { x: junction.x, y: junction.y ?? 0, z: junction.z },
        content: `Crossing conflict predicted at junction ${junction.id}. Hold before the stop line while ${priorityVehicle.id} proceeds.`,
      },
    );
    if (!delivered) return;

    simulation.conflictPredictions += 1;
    yieldingVehicle.status = 'Yielding at intersection';
    yieldingVehicle.yieldUntil = Infinity;
    simulation.intersectionConflict = {
      nodeId: junction.id,
      priorityVehicleId: priorityVehicle.id,
      yieldingVehicleId: yieldingVehicle.id,
      priorityNodeIndex,
      yieldingNodeIndex,
    };
    simulation.mode = 'conflict';
    simulation.modeExpiresAt = simulation.time + config.scenarios.intersectionMaxHoldSeconds;
    simulation.event = 'Intersection conflict predicted';
    simulation.eventDetail = `${priorityVehicle.id} has right of way; ${yieldingVehicle.id} is slowing for the stop line at ${junction.id}.`;
    simulation.log(`Crossing conflict predicted at ${junction.id}; ${yieldingVehicle.id} yielded to ${priorityVehicle.id}.`);
  }
}
