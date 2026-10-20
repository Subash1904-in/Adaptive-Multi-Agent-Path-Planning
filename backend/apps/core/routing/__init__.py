"""Routing package for AMAPP providing baseline shortest-path planning.

Exposes:
- RoutePlanner, find_route: Unified planning interfaces
- dijkstra_search: Baseline Dijkstra pathfinding
- astar_search: Custom A* heuristic pathfinding
- CostMode, RoutingAlgorithm, RoutingRequest, RoutingResult: Data models
- RoutingError, RoutingNodeNotFoundError, NoPathFoundError, InvalidRoutingRequestError: Exceptions
"""

from apps.core.routing.astar import astar_search
from apps.core.routing.costs import (
    calculate_edge_cost,
    calculate_route_metrics,
    is_edge_traversable,
)
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.exceptions import (
    InvalidRoutingRequestError,
    NoPathFoundError,
    RoutingError,
    RoutingNodeNotFoundError,
)
from apps.core.routing.heuristics import (
    check_heuristic_admissibility,
    get_heuristic_function,
)
from apps.core.routing.models import (
    CostMode,
    RoutingAlgorithm,
    RoutingRequest,
    RoutingResult,
)
from apps.core.routing.planner import RoutePlanner, find_route

__all__ = [
    "RoutePlanner",
    "find_route",
    "dijkstra_search",
    "astar_search",
    "calculate_edge_cost",
    "calculate_route_metrics",
    "is_edge_traversable",
    "check_heuristic_admissibility",
    "get_heuristic_function",
    "CostMode",
    "RoutingAlgorithm",
    "RoutingRequest",
    "RoutingResult",
    "RoutingError",
    "RoutingNodeNotFoundError",
    "NoPathFoundError",
    "InvalidRoutingRequestError",
]
