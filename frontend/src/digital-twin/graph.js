import { config } from './config.js';

const nodeKey = (x, z) => `${x},${z}`;

/** Expandable orthogonal road network. Coordinates are grid indices, not metres. */
export class RoadGraph {
  constructor() {
    this.nodes = new Map();
    this.blockedEdges = new Set();
    this.generatedRadius = -1;
    this.topologyAdded = false;
    this.ensure(config.world.initialGraphRadius);
  }

  ensure(radius) {
    if (radius <= this.generatedRadius) return;
    for (let x = -radius; x <= radius; x += 1) {
      for (let z = -radius; z <= radius; z += 1) {
        const id = nodeKey(x, z);
        if (!this.nodes.has(id)) this.nodes.set(id, { id, x, z, edges: [] });
      }
    }

    for (const node of this.nodes.values()) {
      // Grade-separated ring/flyover nodes may share integer coordinates with
      // the street grid. Only canonical "x,z" grid nodes receive grid edges.
      if (node.id !== nodeKey(node.x, node.z)) continue;
      for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const to = nodeKey(node.x + dx, node.z + dz);
        if (!this.nodes.has(to) || node.edges.some((edge) => edge.to === to)) continue;
        const arterial = node.x === 0 || node.z === 0;
        node.edges.push({
          to,
          length: config.world.roadSpacing,
          speedKmh: arterial
            ? config.world.roadSpeedKmh.arterial
            : config.world.roadSpeedKmh.urban,
          type: arterial ? 'arterial' : 'urban',
        });
      }
    }
    this.generatedRadius = radius;
    if (!this.topologyAdded) this.addSpecialRoads();
  }

  node(id) {
    if (this.nodes.has(id)) return this.nodes.get(id);
    const [x, z] = id.split(',').map(Number);
    this.ensure(Math.max(config.world.initialGraphRadius, Math.abs(x), Math.abs(z)));
    return this.nodes.get(id);
  }

  addSpecialRoads() {
    this.topologyAdded = true;
    const spacing = config.world.roadSpacing;
    const addEdge = (fromId, toId, type, speedKmh) => {
      const from = this.nodes.get(fromId);
      const to = this.nodes.get(toId);
      if (!from || !to || from.edges.some((edge) => edge.to === toId)) return;
      const length = Math.hypot((to.x - from.x) * spacing, (to.y ?? 0) - (from.y ?? 0), (to.z - from.z) * spacing);
      from.edges.push({ to: toId, length, speedKmh, type });
    };
    const connectBothWays = (a, b, type, speedKmh) => {
      addEdge(a, b, type, speedKmh);
      addEdge(b, a, type, speedKmh);
    };

    // A continuous elevated ring with four valid junctions into the street grid.
    const ringRadius = config.world.ringRoadRadiusBlocks;
    const ringSegments = config.world.ringRoadSegments;
    for (let index = 0; index < ringSegments; index += 1) {
      const angle = (index / ringSegments) * Math.PI * 2;
      const id = `ring:${index}`;
      this.nodes.set(id, {
        id,
        x: Math.cos(angle) * ringRadius,
        z: Math.sin(angle) * ringRadius,
        y: 0,
        edges: [],
      });
    }
    for (let index = 0; index < ringSegments; index += 1) {
      connectBothWays(`ring:${index}`, `ring:${(index + 1) % ringSegments}`, 'ring', config.world.roadSpeedKmh.ring);
    }
    const cardinalConnections = [
      [0, `${ringRadius},0`],
      [ringSegments / 4, `0,${ringRadius}`],
      [ringSegments / 2, `${-ringRadius},0`],
      [(ringSegments * 3) / 4, `0,${-ringRadius}`],
    ];
    for (const [index, gridNode] of cardinalConnections) {
      connectBothWays(`ring:${index}`, gridNode, 'ring-connector', config.world.roadSpeedKmh.arterial);
    }

    // The flyover deck follows the same arch as its rendered structure.
    const flyoverX = 2;
    const startZ = -2;
    const endZ = 2;
    const segments = config.world.flyoverGraphSegments;
    const heightAt = (z) => Math.max(0, config.world.flyoverHeightMeters * (
      1 - Math.max(0, Math.abs(z * spacing) - spacing) / spacing
    ));
    for (let index = 1; index < segments; index += 1) {
      const z = startZ + ((endZ - startZ) * index) / segments;
      const id = `flyover:${index}`;
      this.nodes.set(id, { id, x: flyoverX, z, y: heightAt(z), edges: [] });
    }
    const flyoverPath = ['2,-2', ...Array.from({ length: segments - 1 }, (_, index) => `flyover:${index + 1}`), '2,2'];
    for (let index = 0; index < flyoverPath.length - 1; index += 1) {
      connectBothWays(flyoverPath[index], flyoverPath[index + 1], 'flyover', config.world.roadSpeedKmh.flyover);
    }

    // A grade-separated underpass follows a sunken road alignment and rejoins
    // the surface grid at both ends of the district segment.
    const underpassX = config.world.underpassLocationBlocks;
    const underpassSegments = config.world.underpassGraphSegments;
    const underpassDepth = config.world.underpassDepthMeters;
    const underpassY = (z) => -underpassDepth * Math.min(
      1,
      Math.max(0, (2 - Math.abs(z)) / 1.35),
    );
    for (let index = 1; index < underpassSegments; index += 1) {
      const z = -2 + (4 * index) / underpassSegments;
      const id = `underpass:${index}`;
      this.nodes.set(id, {
        id,
        x: underpassX,
        z,
        y: underpassY(z),
        edges: [],
      });
    }
    const underpassPath = [
      `${underpassX},-2`,
      ...Array.from({ length: underpassSegments - 1 }, (_, index) => `underpass:${index + 1}`),
      `${underpassX},2`,
    ];
    for (let index = 0; index < underpassPath.length - 1; index += 1) {
      connectBothWays(
        underpassPath[index],
        underpassPath[index + 1],
        'underpass',
        config.world.roadSpeedKmh.urban,
      );
    }

    // A dedicated U-turn pocket branches from and rejoins the central junction.
    // The sampled arc provides routable waypoints so vehicle kinematics follow
    // the bend instead of teleporting across a visual-only curve.
    const uTurnRadius = config.world.uTurnRadiusMeters / spacing;
    const uTurnCenterZ = config.world.uTurnLocationBlocks;
    const uTurnPath = ['0,-1'];
    for (let index = 0; index <= config.world.uTurnSegments; index += 1) {
      const angle = Math.PI + (Math.PI * index) / config.world.uTurnSegments;
      const id = `uturn:${index}`;
      this.nodes.set(id, {
        id,
        x: uTurnRadius * Math.cos(angle),
        z: uTurnCenterZ + uTurnRadius * Math.sin(angle),
        y: 0,
        edges: [],
      });
      uTurnPath.push(id);
    }
    uTurnPath.push('0,-1');
    for (let index = 0; index < uTurnPath.length - 1; index += 1) {
      const pocketArc = index > 0 && index < uTurnPath.length - 2;
      connectBothWays(
        uTurnPath[index], uTurnPath[index + 1],
        pocketArc ? 'uturn' : 'uturn-access',
        pocketArc ? config.world.uTurnSpeedKmh : config.world.roadSpeedKmh.arterial,
      );
    }
  }

  neighbors(id) {
    return this.node(id).edges.filter((edge) => !this.isBlocked(id, edge.to));
  }

  edgeKey(a, b) {
    return [a, b].sort().join('|');
  }

  isBlocked(a, b) {
    return this.blockedEdges.has(this.edgeKey(a, b));
  }

  setBlocked(a, b, blocked = true) {
    const key = this.edgeKey(a, b);
    if (blocked) this.blockedEdges.add(key);
    else this.blockedEdges.delete(key);
  }

  distance(path, index, progress) {
    if (path.length < 2 || index >= path.length - 1) return 0;
    const current = this.nodes.get(path[index]);
    const edge = current?.edges.find((candidate) => candidate.to === path[index + 1]);
    const remainingEdge = edge?.length ?? config.world.roadSpacing;
    let remaining = Math.max(0, (1 - progress) * remainingEdge);
    for (let pathIndex = index + 1; pathIndex < path.length - 1; pathIndex += 1) {
      const from = this.nodes.get(path[pathIndex]);
      const nextEdge = from?.edges.find((candidate) => candidate.to === path[pathIndex + 1]);
      remaining += nextEdge?.length ?? config.world.roadSpacing;
    }
    return remaining;
  }
}
