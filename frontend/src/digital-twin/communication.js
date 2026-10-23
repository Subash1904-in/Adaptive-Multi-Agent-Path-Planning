import { config } from './config.js';

/** Range-limited V2V message delivery and the trace used by the UI/renderer. */
export class V2VCommunication {
  constructor() {
    this.messages = [];
    this.links = [];
    this.deliveredHops = 0;
    this.sentHops = 0;
    this.receivedHops = 0;
    this.totalLatencyMs = 0;
  }

  distanceBetween(graph, sender, receiver) {
    const from = sender.position(graph);
    const to = receiver.position(graph);
    if (!from || !to) return Infinity;
    return Math.hypot(from.x - to.x, from.z - to.z);
  }

  canReach(graph, sender, receiver) {
    return sender !== receiver
      && this.distanceBetween(graph, sender, receiver) <= config.communication.rangeMeters;
  }

  send(simulation, sender, receiver, type, decision, payload = {}) {
    if (!this.canReach(simulation.graph, sender, receiver)) return false;

    const senderPosition = sender.position(simulation.graph);
    sender.messageRole = 'sending';
    sender.messageRoleExpiresAt = simulation.time + config.communication.roleHighlightSeconds;
    receiver.messageRole = 'receiving';
    receiver.messageRoleExpiresAt = simulation.time + config.communication.roleHighlightSeconds;
    const latencyRange = config.communication.latencyMs;
    const latency = latencyRange[0]
      + ((this.messages.length * 31) % (latencyRange[1] - latencyRange[0] + 1));
    const message = {
      id: `M${String(simulation.nextMessageId++).padStart(4, '0')}`,
      sender: sender.id,
      receiver: receiver.id,
      originSender: payload.originSender ?? sender.id,
      hop: payload.hop ?? 1,
      type,
      timestamp: simulation.time,
      senderPosition: { x: senderPosition.x, z: senderPosition.z },
      eventLocation: payload.eventLocation ?? null,
      payload,
      deliveryStatus: 'delivered',
      latency,
      decision,
      content: payload.content ?? decision,
    };

    this.messages.unshift(message);
    this.messages.length = Math.min(this.messages.length, config.communication.messageHistoryLimit);
    this.deliveredHops += 1;
    this.sentHops += 1;
    this.receivedHops += 1;
    this.totalLatencyMs += latency;
    receiver.alerts += 1;
    receiver.alertExpiresAt = simulation.time + config.communication.alertHighlightSeconds;
    receiver.lastAlertType = type;
    receiver.lastAlertDecision = decision;
    this.links.push({
      from: sender.id,
      to: receiver.id,
      messageId: message.id,
      until: simulation.time + config.communication.linkDurationSeconds,
    });
    simulation.log(`${receiver.id} received ${type.toLowerCase()} from ${sender.id} · ${decision}`);
    return true;
  }

  /** Deliver an alert along shortest in-range vehicle chains to selected targets. */
  propagate(simulation, source, type, payload, targets, onTargetDelivered = () => {}) {
    const liveVehicles = simulation.agents.filter((agent) => !agent.arrived);
    const targetById = new Map(targets.map((target) => [target.agent.id, target]));
    const paths = [];
    const previous = new Map([[source.id, null]]);
    const queue = [source];

    while (queue.length) {
      const current = queue.shift();
      const hops = this.pathLength(previous, current.id);
      if (hops >= config.communication.maxRelayHops) continue;
      const neighbors = liveVehicles
        .filter((candidate) => !previous.has(candidate.id)
          && this.canReach(simulation.graph, current, candidate))
        .sort((a, b) => a.id.localeCompare(b.id));
      for (const neighbor of neighbors) {
        previous.set(neighbor.id, current.id);
        queue.push(neighbor);
      }
    }

    for (const target of targets) {
      if (target.agent === source) continue;
      if (!previous.has(target.agent.id)) continue;
      const path = [];
      for (let cursor = target.agent.id; cursor; cursor = previous.get(cursor)) path.push(cursor);
      paths.push(path.reverse());
    }

    const transmissions = new Map();
    for (const path of paths) {
      for (let index = 1; index < path.length; index += 1) {
        const fromId = path[index - 1], toId = path[index];
        const key = `${fromId}->${toId}`;
        if (!transmissions.has(key)) transmissions.set(key, { fromId, toId, hop: index });
      }
    }

    const ordered = [...transmissions.values()].sort((a, b) => a.hop - b.hop
      || a.fromId.localeCompare(b.fromId) || a.toId.localeCompare(b.toId));
    let deliveredCount = 0;
    for (const transmission of ordered) {
      const sender = simulation.agents.find((agent) => agent.id === transmission.fromId);
      const receiver = simulation.agents.find((agent) => agent.id === transmission.toId);
      const target = targetById.get(transmission.toId);
      const decision = target?.decision ?? `Forwarding ${type.toLowerCase()} to nearby vehicles`;
      const content = target?.content ?? `${source.id}'s alert relayed by ${sender.id}; checking routes toward the incident.`;
      const delivered = this.send(simulation, sender, receiver, type, decision, {
        ...payload,
        originSender: source.id,
        hop: transmission.hop,
        relayed: transmission.hop > 1,
        content,
      });
      if (!delivered) continue;
      deliveredCount += 1;
      if (target) onTargetDelivered(receiver, target, this.messages[0]);
    }
    return deliveredCount;
  }

  pathLength(previous, id) {
    let length = 0;
    for (let cursor = id; previous.get(cursor); cursor = previous.get(cursor)) length += 1;
    return length;
  }

  pruneLinks(time) {
    this.links = this.links.filter((link) => time < link.until);
  }
}
