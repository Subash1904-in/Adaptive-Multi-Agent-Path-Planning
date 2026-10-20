"""Dijkstra shortest-path algorithm for AMAPP directed road networks."""

import heapq
import itertools
import time
from typing import Callable, Optional

from apps.core.domain.models import RoadEdge, Route
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.costs import (
    calculate_edge_cost,
    calculate_route_metrics,
    is_edge_traversable,
)
from apps.core.routing.exceptions import NoPathFoundError, RoutingNodeNotFoundError
from apps.core.routing.models import CostMode, RoutingAlgorithm, RoutingResult


def dijkstra_search(
    road_graph: RoadGraph,
    start_node_id: str,
    destination_node_id: str,
    cost_mode: CostMode = CostMode.TRAVEL_TIME,
    closed_edge_ids: Optional[set[str]] = None,
    edge_cost_fn: Optional[Callable[[RoadEdge, CostMode], float]] = None,
) -> RoutingResult:
    """Execute Dijkstra search to find the optimal path in a directed RoadGraph.

    Args:
        road_graph: The directed RoadGraph instance to navigate.
        start_node_id: Source road node identifier.
        destination_node_id: Target road node identifier.
        cost_mode: Optimization objective (DISTANCE in meters or TRAVEL_TIME in seconds).
        closed_edge_ids: Optional set of directed edge IDs temporarily excluded from routing.

    Returns:
        RoutingResult: Typed result containing the optimal route, metrics, and domain Route.

    Raises:
        RoutingNodeNotFoundError: If start_node_id or destination_node_id is not in graph.
        NoPathFoundError: If destination is unreachable or all paths are blocked by closures.
    """
    t0 = time.perf_counter()

    if not road_graph.has_node(start_node_id):
        raise RoutingNodeNotFoundError(start_node_id, role="start")
    if not road_graph.has_node(destination_node_id):
        raise RoutingNodeNotFoundError(destination_node_id, role="destination")

    closed_edges = set(closed_edge_ids) if closed_edge_ids else set()

    # Documented policy for identical start and destination
    if start_node_id == destination_node_id:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return RoutingResult(
            success=True,
            algorithm=RoutingAlgorithm.DIJKSTRA,
            cost_mode=cost_mode,
            start_node_id=start_node_id,
            destination_node_id=destination_node_id,
            node_ids=[start_node_id],
            edge_ids=[],
            total_distance_m=0.0,
            estimated_duration_s=0.0,
            objective_cost=0.0,
            nodes_expanded=0,
            edges_examined=0,
            execution_time_ms=elapsed_ms,
            route=None,
        )

    # Priority queue: (cost, counter, node_id)
    tie_breaker = itertools.count()
    pq: list[tuple[float, int, str]] = []
    heapq.heappush(pq, (0.0, next(tie_breaker), start_node_id))

    distances: dict[str, float] = {start_node_id: 0.0}
    came_from: dict[str, tuple[str, str]] = {}  # node -> (pred_node, edge_id)
    visited: set[str] = set()

    nodes_expanded = 0
    edges_examined = 0

    while pq:
        current_cost, _, u = heapq.heappop(pq)

        # Handle stale priority queue entries
        if current_cost > distances.get(u, float("inf")) + 1e-12:
            continue

        if u == destination_node_id:
            break

        if u in visited:
            continue
        visited.add(u)
        nodes_expanded += 1

        for edge in road_graph.get_outgoing_edges(u):
            edges_examined += 1

            if not is_edge_traversable(edge.id, closed_edges):
                continue

            v = edge.end_node_id
            if v in visited:
                continue

            if edge_cost_fn is not None:
                edge_cost = edge_cost_fn(edge, cost_mode)
            else:
                edge_cost = calculate_edge_cost(edge, cost_mode)
            new_cost = current_cost + edge_cost

            if new_cost < distances.get(v, float("inf")) - 1e-12:
                distances[v] = new_cost
                came_from[v] = (u, edge.id)
                heapq.heappush(pq, (new_cost, next(tie_breaker), v))

    if destination_node_id not in came_from:
        raise NoPathFoundError(
            start_node_id=start_node_id,
            destination_node_id=destination_node_id,
            closed_edge_count=len(closed_edges),
        )

    # Reconstruct path
    curr = destination_node_id
    reversed_nodes = [curr]
    reversed_edges: list[str] = []

    while curr != start_node_id:
        pred, edge_id = came_from[curr]
        reversed_edges.append(edge_id)
        reversed_nodes.append(pred)
        curr = pred

    node_ids = list(reversed(reversed_nodes))
    edge_ids = list(reversed(reversed_edges))

    edge_objects: list[RoadEdge] = [road_graph.get_edge(eid) for eid in edge_ids]
    total_distance_m, estimated_duration_s = calculate_route_metrics(edge_objects)
    objective_cost = distances[destination_node_id]

    route_entity = Route(
        id=f"route_{start_node_id}_{destination_node_id}",
        node_ids=node_ids,
        edge_ids=edge_ids,
        total_distance_m=total_distance_m,
        estimated_duration_s=estimated_duration_s,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return RoutingResult(
        success=True,
        algorithm=RoutingAlgorithm.DIJKSTRA,
        cost_mode=cost_mode,
        start_node_id=start_node_id,
        destination_node_id=destination_node_id,
        node_ids=node_ids,
        edge_ids=edge_ids,
        total_distance_m=total_distance_m,
        estimated_duration_s=estimated_duration_s,
        objective_cost=objective_cost,
        nodes_expanded=nodes_expanded,
        edges_examined=edges_examined,
        execution_time_ms=elapsed_ms,
        route=route_entity,
    )
