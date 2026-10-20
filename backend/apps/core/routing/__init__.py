"""Routing package for AMAPP providing baseline shortest-path planning.

Exposes:
- RoutePlanner, find_route: Unified planning interfaces
- dijkstra_search: Baseline Dijkstra pathfinding
- astar_search: Custom A* heuristic pathfinding
- CostMode, RoutingAlgorithm, RoutingRequest, RoutingResult: Data models
- RoutingError, RoutingNodeNotFoundError, NoPathFoundError, InvalidRoutingRequestError: Exceptions
"""

from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.astar import astar_search
from apps.core.routing.costs import (
    calculate_edge_cost,
    calculate_route_metrics,
    is_edge_traversable,
)
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.evaluator import DynamicEdgeCostEvaluator
from apps.core.routing.exceptions import (
    AdaptiveRoutingError,
    InvalidReroutePolicyError,
    InvalidRoutingRequestError,
    NoPathFoundError,
    RouteReplacementError,
    RoutingError,
    RoutingNodeNotFoundError,
)
from apps.core.routing.heuristics import (
    check_heuristic_admissibility,
    get_heuristic_function,
)
from apps.core.routing.metrics import AdaptiveRoutingMetrics
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    CostMode,
    RerouteDecision,
    RerouteDecisionType,
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
    "AdaptiveRoutingConfig",
    "RerouteDecision",
    "RerouteDecisionType",
    "DynamicRouteAdapter",
    "DynamicEdgeCostEvaluator",
    "AdaptiveRoutingMetrics",
    "RoutingError",
    "RoutingNodeNotFoundError",
    "NoPathFoundError",
    "InvalidRoutingRequestError",
    "AdaptiveRoutingError",
    "RouteReplacementError",
    "InvalidReroutePolicyError",
]
