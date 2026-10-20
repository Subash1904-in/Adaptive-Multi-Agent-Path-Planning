"""Unified route planner interface for AMAPP."""

from typing import Optional, Union

from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.astar import astar_search
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.exceptions import InvalidRoutingRequestError
from apps.core.routing.heuristics import check_heuristic_admissibility
from apps.core.routing.models import CostMode, RoutingAlgorithm, RoutingRequest, RoutingResult


class RoutePlanner:
    """Unified single-agent route planning engine for autonomous navigation.

    Dispatches shortest-path queries to Dijkstra or A* implementations, manages
    heuristic admissibility analysis, and returns typed RoutingResult objects.
    """

    def __init__(self, road_graph: RoadGraph) -> None:
        if not isinstance(road_graph, RoadGraph):
            raise InvalidRoutingRequestError(
                f"Expected RoadGraph instance, got {type(road_graph).__name__}.",
                field="road_graph",
            )
        self.road_graph = road_graph
        self._cached_admissibility = check_heuristic_admissibility(road_graph)

    @property
    def is_heuristic_admissible(self) -> bool:
        """Return whether Euclidean distance heuristics are admissible on this graph."""
        return self._cached_admissibility[0]

    @property
    def max_speed_limit_mps(self) -> float:
        """Return maximum speed limit across all edges in the graph."""
        return self._cached_admissibility[1]

    def find_route(
        self,
        start_node_id: str,
        destination_node_id: str,
        algorithm: Union[str, RoutingAlgorithm] = RoutingAlgorithm.ASTAR,
        cost_mode: Union[str, CostMode] = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> RoutingResult:
        """Find the optimal route between start and destination nodes.

        Args:
            start_node_id: Origin road node identifier.
            destination_node_id: Target road node identifier.
            algorithm: Routing algorithm to use (ASTAR or DIJKSTRA).
            cost_mode: Optimization objective (DISTANCE or TRAVEL_TIME).
            closed_edge_ids: Optional set of temporarily closed edge IDs.

        Returns:
            RoutingResult: Comprehensive pathfinding output.

        Raises:
            RoutingNodeNotFoundError: If start or destination node is absent.
            NoPathFoundError: If no traversable path connects the nodes.
            InvalidRoutingRequestError: If parameters are invalid.
        """
        req = RoutingRequest(
            start_node_id=start_node_id,
            destination_node_id=destination_node_id,
            algorithm=RoutingAlgorithm(algorithm) if isinstance(algorithm, str) else algorithm,
            cost_mode=CostMode(cost_mode) if isinstance(cost_mode, str) else cost_mode,
            closed_edge_ids=closed_edge_ids or set(),
        )
        return self.find_route_from_request(req)

    def find_route_from_request(self, request: RoutingRequest) -> RoutingResult:
        """Execute route planning from a validated RoutingRequest specification."""
        if request.algorithm == RoutingAlgorithm.DIJKSTRA:
            return dijkstra_search(
                road_graph=self.road_graph,
                start_node_id=request.start_node_id,
                destination_node_id=request.destination_node_id,
                cost_mode=request.cost_mode,
                closed_edge_ids=request.closed_edge_ids,
            )
        elif request.algorithm == RoutingAlgorithm.ASTAR:
            return astar_search(
                road_graph=self.road_graph,
                start_node_id=request.start_node_id,
                destination_node_id=request.destination_node_id,
                cost_mode=request.cost_mode,
                closed_edge_ids=request.closed_edge_ids,
            )
        else:
            raise InvalidRoutingRequestError(f"Unsupported routing algorithm: {request.algorithm}")


def find_route(
    road_graph: RoadGraph,
    start_node_id: str,
    destination_node_id: str,
    algorithm: Union[str, RoutingAlgorithm] = RoutingAlgorithm.ASTAR,
    cost_mode: Union[str, CostMode] = CostMode.TRAVEL_TIME,
    closed_edge_ids: Optional[set[str]] = None,
) -> RoutingResult:
    """Convenience function to plan a route on a RoadGraph without manually managing a planner.

    Args:
        road_graph: Directed road network.
        start_node_id: Origin road node.
        destination_node_id: Destination road node.
        algorithm: Shortest-path algorithm (ASTAR or DIJKSTRA).
        cost_mode: Optimization objective (DISTANCE or TRAVEL_TIME).
        closed_edge_ids: Optional set of closed edge IDs.

    Returns:
        RoutingResult: Resulting optimal path and metrics.
    """
    planner = RoutePlanner(road_graph)
    return planner.find_route(
        start_node_id=start_node_id,
        destination_node_id=destination_node_id,
        algorithm=algorithm,
        cost_mode=cost_mode,
        closed_edge_ids=closed_edge_ids,
    )
