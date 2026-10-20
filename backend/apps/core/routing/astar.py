"""Custom A* shortest-path algorithm for AMAPP directed road networks."""

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
from apps.core.routing.heuristics import get_heuristic_function
from apps.core.routing.models import CostMode, RoutingAlgorithm, RoutingResult


def astar_search(
    road_graph: RoadGraph,
    start_node_id: str,
    destination_node_id: str,
    cost_mode: CostMode = CostMode.TRAVEL_TIME,
    closed_edge_ids: Optional[set[str]] = None,
    heuristic_func: Optional[Callable[[str], float]] = None,
    force_zero_heuristic: bool = False,
    edge_cost_fn: Optional[Callable[[RoadEdge, CostMode], float]] = None,
) -> RoutingResult:
    """Execute custom A* search to find the optimal path in a directed RoadGraph.

    Maintains:
    - g_score: Best-known cumulative cost from start to node.
    - f_score: Estimated total cost (g_score + heuristic).
    - came_from: Predecessor pointers for path reconstruction.
    - pq: Min-heap with deterministic tie-breaking.

    Args:
        road_graph: The directed RoadGraph instance to navigate.
        start_node_id: Source road node identifier.
        destination_node_id: Target road node identifier.
        cost_mode: Optimization objective (DISTANCE or TRAVEL_TIME).
        closed_edge_ids: Optional set of directed edge IDs temporarily excluded from routing.
        heuristic_func: Optional custom heuristic function h(node_id) -> float.
        force_zero_heuristic: If True, uses h=0 fallback (ensuring Dijkstra equivalence).

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
            algorithm=RoutingAlgorithm.ASTAR,
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

    # Resolve heuristic function and verify admissibility
    if heuristic_func is not None:
        h = heuristic_func
    else:
        h, _ = get_heuristic_function(
            road_graph=road_graph,
            destination_node_id=destination_node_id,
            cost_mode=cost_mode,
            force_zero=force_zero_heuristic,
        )

    g_score: dict[str, float] = {start_node_id: 0.0}
    f_score: dict[str, float] = {start_node_id: h(start_node_id)}
    came_from: dict[str, tuple[str, str]] = {}  # node -> (pred_node, edge_id)

    # Priority queue tuple: (f_score, h_score, tie_breaker_counter, g_score, node_id)
    # Secondary sort on h_score prioritizes nodes closer to goal on equal f_score
    tie_breaker = itertools.count()
    pq: list[tuple[float, float, int, float, str]] = []
    heapq.heappush(
        pq,
        (f_score[start_node_id], h(start_node_id), next(tie_breaker), 0.0, start_node_id),
    )

    closed_set: set[str] = set()
    nodes_expanded = 0
    edges_examined = 0

    while pq:
        current_f, current_h, _, current_g, u = heapq.heappop(pq)

        # Handle stale priority queue entries
        if current_g > g_score.get(u, float("inf")) + 1e-12:
            continue

        if u == destination_node_id:
            break

        if u in closed_set:
            continue
        closed_set.add(u)
        nodes_expanded += 1

        for edge in road_graph.get_outgoing_edges(u):
            edges_examined += 1

            if not is_edge_traversable(edge.id, closed_edges):
                continue

            v = edge.end_node_id
            if v in closed_set:
                continue

            if edge_cost_fn is not None:
                edge_cost = edge_cost_fn(edge, cost_mode)
            else:
                edge_cost = calculate_edge_cost(edge, cost_mode)
            tentative_g = current_g + edge_cost

            if tentative_g < g_score.get(v, float("inf")) - 1e-12:
                came_from[v] = (u, edge.id)
                g_score[v] = tentative_g
                h_val = h(v)
                new_f = tentative_g + h_val
                f_score[v] = new_f
                heapq.heappush(pq, (new_f, h_val, next(tie_breaker), tentative_g, v))

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
    objective_cost = g_score[destination_node_id]

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
        algorithm=RoutingAlgorithm.ASTAR,
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
