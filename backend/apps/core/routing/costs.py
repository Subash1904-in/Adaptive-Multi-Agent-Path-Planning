"""Cost functions and traversability policies for AMAPP road network routing."""

import math
from typing import Optional

from apps.core.domain.models import RoadEdge
from apps.core.routing.exceptions import InvalidRoutingRequestError
from apps.core.routing.models import CostMode


def calculate_edge_cost(edge: RoadEdge, cost_mode: CostMode) -> float:
    """Calculate the scalar traversal cost of a directed road edge.

    Args:
        edge: The directed RoadEdge domain model.
        cost_mode: The optimization objective (DISTANCE or TRAVEL_TIME).

    Returns:
        float: Traversal cost in meters (for distance) or seconds (for travel time).

    Raises:
        InvalidRoutingRequestError: If length or speed limit is non-positive or non-finite.
    """
    if not math.isfinite(edge.length_m) or edge.length_m <= 0.0:
        raise InvalidRoutingRequestError(
            f"RoadEdge '{edge.id}' has invalid length_m: {edge.length_m}. "
            "Must be positive and finite."
        )
    if not math.isfinite(edge.speed_limit_mps) or edge.speed_limit_mps <= 0.0:
        raise InvalidRoutingRequestError(
            f"RoadEdge '{edge.id}' has invalid speed_limit_mps: {edge.speed_limit_mps}. "
            "Must be positive and finite."
        )

    if cost_mode == CostMode.DISTANCE:
        return edge.length_m
    elif cost_mode == CostMode.TRAVEL_TIME:
        return edge.length_m / edge.speed_limit_mps
    else:
        raise InvalidRoutingRequestError(f"Unsupported cost mode: {cost_mode}")


def calculate_route_metrics(edges: list[RoadEdge]) -> tuple[float, float]:
    """Calculate aggregate distance and travel duration for a sequence of edges.

    Args:
        edges: Ordered list of RoadEdge objects comprising a route.

    Returns:
        tuple[float, float]: (total_distance_m, estimated_duration_s)
    """
    total_distance_m = 0.0
    estimated_duration_s = 0.0

    for edge in edges:
        total_distance_m += edge.length_m
        estimated_duration_s += edge.length_m / edge.speed_limit_mps

    return total_distance_m, estimated_duration_s


def is_edge_traversable(edge_id: str, closed_edge_ids: Optional[set[str]] = None) -> bool:
    """Check if a directed edge is currently open and traversable.

    Args:
        edge_id: Identifier of the edge to inspect.
        closed_edge_ids: Optional set of temporarily closed or disabled edge IDs.

    Returns:
        bool: True if edge is traversable, False if closed.
    """
    if not closed_edge_ids:
        return True
    return edge_id not in closed_edge_ids
