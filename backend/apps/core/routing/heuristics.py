"""A* heuristics and admissibility verification for AMAPP road networks."""

from typing import Callable, Optional

from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.models import CostMode


def check_heuristic_admissibility(road_graph: RoadGraph) -> tuple[bool, float]:
    """Verify whether Euclidean distance heuristics are admissible on the graph.

    For Euclidean distance heuristics to be admissible:
    1. Every directed edge length must be >= straight-line Euclidean distance
       between its start and end nodes (allowing 1e-5 numerical tolerance).
    2. For travel time, a valid positive maximum speed limit must exist across all edges.

    Returns:
        tuple[bool, float]: (is_admissible, max_speed_limit_mps)
    """
    if road_graph.edge_count == 0:
        return True, 1.0

    max_speed_limit_mps = 0.0

    for edge in road_graph.edges():
        if edge.speed_limit_mps > max_speed_limit_mps:
            max_speed_limit_mps = edge.speed_limit_mps

        start_node = road_graph.get_node(edge.start_node_id)
        end_node = road_graph.get_node(edge.end_node_id)
        euclidean_dist = start_node.position.distance_to(end_node.position)

        # If edge length is strictly smaller than straight-line distance,
        # the metric space is non-Euclidean/inadmissible
        if edge.length_m < (euclidean_dist - 1e-5):
            return False, max_speed_limit_mps

    if max_speed_limit_mps <= 0.0:
        return False, 1.0

    return True, max_speed_limit_mps


def get_heuristic_function(
    road_graph: RoadGraph,
    destination_node_id: str,
    cost_mode: CostMode,
    force_zero: bool = False,
    cached_admissibility: Optional[tuple[bool, float]] = None,
) -> tuple[Callable[[str], float], bool]:
    """Build an admissible A* heuristic function for the target destination.

    Args:
        road_graph: The RoadGraph being navigated.
        destination_node_id: Target destination node.
        cost_mode: Optimization objective (DISTANCE or TRAVEL_TIME).
        force_zero: If True, explicitly return a zero heuristic (Dijkstra equivalence).
        cached_admissibility: Optional pre-computed (is_admissible, max_speed) tuple.

    Returns:
        tuple[Callable[[str], float], bool]: (heuristic_function, is_admissible)
    """
    if force_zero:
        return (lambda _: 0.0), True

    if cached_admissibility is not None:
        is_admissible, max_speed_mps = cached_admissibility
    else:
        is_admissible, max_speed_mps = check_heuristic_admissibility(road_graph)

    if not is_admissible:
        # Fall back safely to h=0 to guarantee optimal solution
        return (lambda _: 0.0), False

    dest_node = road_graph.get_node(destination_node_id)
    dest_pos = dest_node.position

    if cost_mode == CostMode.DISTANCE:

        def distance_heuristic(node_id: str) -> float:
            node = road_graph.get_node(node_id)
            return node.position.distance_to(dest_pos)

        return distance_heuristic, True

    elif cost_mode == CostMode.TRAVEL_TIME:

        def travel_time_heuristic(node_id: str) -> float:
            node = road_graph.get_node(node_id)
            return node.position.distance_to(dest_pos) / max_speed_mps

        return travel_time_heuristic, True

    return (lambda _: 0.0), False
