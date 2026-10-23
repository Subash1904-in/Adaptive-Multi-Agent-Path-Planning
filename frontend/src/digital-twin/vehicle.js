import { config, vehicleColors, vehicleStarts, destinations } from './config.js';

function turnGeometry(graph, path, nodeIndex) {
  if (nodeIndex <= 0 || nodeIndex >= path.length - 1) return null;
  const before = graph.node(path[nodeIndex - 1]);
  const corner = graph.node(path[nodeIndex]);
  const after = graph.node(path[nodeIndex + 1]);
  const incoming = { x: corner.x - before.x, z: corner.z - before.z };
  const outgoing = { x: after.x - corner.x, z: after.z - corner.z };
  const inLength = Math.hypot(incoming.x, incoming.z);
  const outLength = Math.hypot(outgoing.x, outgoing.z);
  if (!inLength || !outLength) return null;
  incoming.x /= inLength;
  incoming.z /= inLength;
  outgoing.x /= outLength;
  outgoing.z /= outLength;
  const dot = incoming.x * outgoing.x + incoming.z * outgoing.z;
  const inEdge = graph.nodes.get(before.id)?.edges.find((edge) => edge.to === corner.id);
  const outEdge = graph.nodes.get(corner.id)?.edges.find((edge) => edge.to === after.id);
  const radius = config.vehicles.turnRadiusMeters;
  if (Math.abs(dot) > 0.05 || !inEdge || !outEdge
    || inEdge.length <= radius * 2 || outEdge.length <= radius * 2) return null;
  const spacing = config.world.roadSpacing;
  const point = {
    x: corner.x * spacing,
    y: corner.y ?? 0,
    z: corner.z * spacing,
  };
  return {
    radius,
    inEdge,
    outEdge,
    entry: { x: point.x - incoming.x * radius, y: point.y, z: point.z - incoming.z * radius },
    exit: { x: point.x + outgoing.x * radius, y: point.y, z: point.z + outgoing.z * radius },
    point,
    incoming,
    outgoing,
  };
}

function curvePosition(turn, t) {
  const oneMinus = 1 - t;
  const x = oneMinus * oneMinus * turn.entry.x
    + 2 * oneMinus * t * turn.point.x + t * t * turn.exit.x;
  const z = oneMinus * oneMinus * turn.entry.z
    + 2 * oneMinus * t * turn.point.z + t * t * turn.exit.z;
  const dx = 2 * oneMinus * (turn.point.x - turn.entry.x)
    + 2 * t * (turn.exit.x - turn.point.x);
  const dz = 2 * oneMinus * (turn.point.z - turn.entry.z)
    + 2 * t * (turn.exit.z - turn.point.z);
  return { x, y: turn.point.y, z, dx, dz };
}

/** Centerline points for route overlays, rounding perpendicular street turns. */
export function getRoutePolyline(graph, path, lift = 0.32) {
  if (!path.length) return [];
  const spacing = config.world.roadSpacing;
  const turns = new Map();
  for (let index = 1; index < path.length - 1; index += 1) {
    const turn = turnGeometry(graph, path, index);
    if (turn) turns.set(index, turn);
  }
  const points = [];
  const first = graph.node(path[0]);
  points.push({ x: first.x * spacing, y: (first.y ?? 0) + lift, z: first.z * spacing });
  for (let edgeIndex = 0; edgeIndex < path.length - 1; edgeIndex += 1) {
    const from = graph.node(path[edgeIndex]);
    const to = graph.node(path[edgeIndex + 1]);
    const fromTurn = turns.get(edgeIndex);
    const toTurn = turns.get(edgeIndex + 1);
    const start = fromTurn?.exit ?? { x: from.x * spacing, y: from.y ?? 0, z: from.z * spacing };
    const end = toTurn?.entry ?? { x: to.x * spacing, y: to.y ?? 0, z: to.z * spacing };
    points.push({ x: start.x, y: start.y + lift, z: start.z });
    if (toTurn) {
      points.push({ x: end.x, y: end.y + lift, z: end.z });
      for (let sample = 1; sample <= 12; sample += 1) {
        const curve = curvePosition(toTurn, sample / 12);
        points.push({ x: curve.x, y: curve.y + lift, z: curve.z });
      }
    } else {
      points.push({ x: end.x, y: end.y + lift, z: end.z });
    }
  }
  return points;
}

/** Runtime state and movement integration for one road-following vehicle. */
export class VehicleAgent {
  constructor(index, graph, findRoute) {
    const destination = destinations[index % destinations.length];
    const start = vehicleStarts[index % vehicleStarts.length];
    const emergency = index === config.vehicles.emergencyIndex;

    this.id = `V${index + 1}`;
    this.type = emergency ? 'Ambulance' : 'Passenger vehicle';
    this.start = start;
    this.destination = destination;
    this.route = findRoute(graph, start, destination.node);
    this.index = 0;
    let positionInTrafficPack = 0;
    for (let previousIndex = 0; previousIndex < index; previousIndex += 1) {
      const previousStart = vehicleStarts[previousIndex % vehicleStarts.length];
      if (previousStart !== start) continue;
      const previousDestination = destinations[previousIndex % destinations.length];
      const previousRoute = findRoute(graph, previousStart, previousDestination.node);
      if (previousRoute[1] === this.route[1]) positionInTrafficPack += 1;
    }
    this.progress = 0.06 + positionInTrafficPack * config.vehicles.initialProgressStep;
    this.speed = 0;
    this.tripElapsedSeconds = 0;
    this.completedTripTimeSeconds = null;
    this.distanceTravelledMeters = 0;
    this.maxSpeed = emergency
      ? config.vehicles.emergencySpeedKmh
      : config.vehicles.passengerSpeedKmh[index % config.vehicles.passengerSpeedKmh.length];
    this.color = vehicleColors[index % vehicleColors.length];
    this.laneOffsetMeters = config.vehicles.laneOffsetMeters;
    this.moveAsideForEmergency = false;
    this.replans = 0;
    this.arrived = false;
    this.alerts = 0;
    this.alertExpiresAt = 0;
    this.lastAlertType = '';
    this.lastAlertDecision = '';
    this.messageRole = '';
    this.messageRoleExpiresAt = 0;
    this.replanningVisualAt = 0;
    this.replanningVisualUntil = 0;
    this.status = 'Following assigned route';
    this.suddenBrakeUntil = 0;
    this.suddenBrakeTargetSpeedKmh = 0;
    this.encounterUntil = 0;
    this.encounterLeaderId = null;
    this.yieldUntil = 0;
    this.lastBlockedEdge = null;
  }

  position(graph) {
    if (this.arrived || this.index >= this.route.length - 1) return null;
    const from = graph.node(this.route[this.index]);
    const to = graph.node(this.route[this.index + 1]);
    const spacing = config.world.roadSpacing;
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const fromTurn = turnGeometry(graph, this.route, this.index);
    const toTurn = turnGeometry(graph, this.route, this.index + 1);
    const edge = from.edges.find((candidate) => candidate.to === to.id);
    const edgeLength = edge?.length ?? Math.hypot(dx * spacing, dz * spacing);
    const distance = edgeLength * this.progress;
    let center;
    if (fromTurn && distance < fromTurn.radius) {
      center = curvePosition(fromTurn, 0.5 + (distance / fromTurn.radius) * 0.5);
    } else if (toTurn && distance > edgeLength - toTurn.radius) {
      center = curvePosition(toTurn, ((distance - (edgeLength - toTurn.radius)) / toTurn.radius) * 0.5);
    } else {
      const start = fromTurn?.exit ?? { x: from.x * spacing, y: from.y ?? 0, z: from.z * spacing };
      const end = toTurn?.entry ?? { x: to.x * spacing, y: to.y ?? 0, z: to.z * spacing };
      const pathStart = fromTurn ? fromTurn.radius : 0;
      const pathEnd = toTurn ? edgeLength - toTurn.radius : edgeLength;
      const t = pathEnd <= pathStart ? 0 : Math.max(0, Math.min(1, (distance - pathStart) / (pathEnd - pathStart)));
      center = {
        x: start.x + (end.x - start.x) * t,
        y: start.y + (end.y - start.y) * t,
        z: start.z + (end.z - start.z) * t,
        dx: end.x - start.x,
        dz: end.z - start.z,
      };
    }
    const tangentLength = Math.hypot(center.dx, center.dz) || 1;
    const laneOffset = edge?.type.startsWith('uturn') ? 0 : this.laneOffsetMeters;
    return {
      x: center.x + (center.dz / tangentLength) * laneOffset,
      y: center.y,
      z: center.z - (center.dx / tangentLength) * laneOffset,
      heading: Math.atan2(-center.dx, -center.dz),
    };
  }

  advance(graph, dt, targetSpeedKmh) {
    const acceleration = targetSpeedKmh > this.speed
      ? config.vehicles.accelerationMps2
      : config.vehicles.brakingMps2;
    // speed is stored in km/h, while acceleration and braking are configured in m/s².
    const delta = Math.min(Math.abs(targetSpeedKmh - this.speed), acceleration * dt * 3.6);
    this.speed += Math.sign(targetSpeedKmh - this.speed) * delta;

    if (this.index >= this.route.length - 1) return false;
    const from = graph.node(this.route[this.index]);
    const to = graph.node(this.route[this.index + 1]);
    const edge = from.edges.find((candidate) => candidate.to === to.id);
    const edgeLength = edge?.length ?? Math.hypot(
      (to.x - from.x) * config.world.roadSpacing,
      (to.y ?? 0) - (from.y ?? 0),
      (to.z - from.z) * config.world.roadSpacing,
    );
    if (edgeLength <= 0.001) {
      this.progress = 1;
    } else {
    this.progress += (this.speed / 3.6 * dt) / edgeLength;
    }

    if (this.progress < 1) return false;
    this.progress = 0;
    this.index += 1;
    if (this.index < this.route.length - 1) return false;

    this.arrived = true;
    this.speed = 0;
    this.status = 'Destination reached';
    return true;
  }
}
