import { config } from './config.js';

/** A* path search using estimated travel time as its cost. */
export function findRoute(graph, start, goal) {
  const startNode = graph.node(start);
  const goalNode = graph.node(goal);
  const radius = Math.max(
    config.world.graphSearchRadius,
    Math.abs(startNode.x), Math.abs(startNode.z),
    Math.abs(goalNode.x), Math.abs(goalNode.z),
  ) + 1;
  graph.ensure(radius);

  const fastestRoadSpeed = Math.max(...Object.values(config.world.roadSpeedKmh));
  const heuristic = (id) => {
    const node = graph.node(id);
    const distance = Math.hypot(
      (node.x - goalNode.x) * config.world.roadSpacing,
      (node.y ?? 0) - (goalNode.y ?? 0),
      (node.z - goalNode.z) * config.world.roadSpacing,
    );
    return distance / (fastestRoadSpeed / 3.6);
  };

  const open = new Set([start]);
  const previous = new Map();
  const travelTime = new Map([[start, 0]]);
  const estimatedTotal = new Map([[start, heuristic(start)]]);

  while (open.size > 0) {
    let current;
    for (const candidate of open) {
      if (current === undefined
        || estimatedTotal.get(candidate) < estimatedTotal.get(current)) current = candidate;
    }

    if (current === goal) {
      const route = [current];
      while (previous.has(current)) {
        current = previous.get(current);
        route.unshift(current);
      }
      return route;
    }

    open.delete(current);
    for (const edge of graph.neighbors(current)) {
      const edgeTime = edge.length / (edge.speedKmh / 3.6);
      const nextTime = travelTime.get(current) + edgeTime;
      if (nextTime >= (travelTime.get(edge.to) ?? Infinity)) continue;
      previous.set(edge.to, current);
      travelTime.set(edge.to, nextTime);
      estimatedTotal.set(edge.to, nextTime + heuristic(edge.to));
      open.add(edge.to);
    }
  }

  return [];
}
