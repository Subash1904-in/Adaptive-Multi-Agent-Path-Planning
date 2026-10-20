"""Domain models and value types for the AMAPP route planning subsystem."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from apps.core.domain.models import Route
from apps.core.domain.serialization import to_dict as domain_to_dict
from apps.core.routing.exceptions import InvalidRoutingRequestError


class CostMode(str, Enum):
    """Optimization objectives supported by AMAPP route planners."""

    DISTANCE = "distance"
    TRAVEL_TIME = "travel_time"


class RoutingAlgorithm(str, Enum):
    """Shortest-path search algorithms supported by AMAPP route planners."""

    DIJKSTRA = "dijkstra"
    ASTAR = "astar"


@dataclass
class RoutingRequest:
    """Configuration parameters for a single-agent route planning query."""

    start_node_id: str
    destination_node_id: str
    cost_mode: CostMode = CostMode.TRAVEL_TIME
    algorithm: RoutingAlgorithm = RoutingAlgorithm.ASTAR
    closed_edge_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.start_node_id or not isinstance(self.start_node_id, str):
            raise InvalidRoutingRequestError(
                "start_node_id must be a non-empty string.", field="start_node_id"
            )
        if not self.destination_node_id or not isinstance(self.destination_node_id, str):
            raise InvalidRoutingRequestError(
                "destination_node_id must be a non-empty string.", field="destination_node_id"
            )
        if not isinstance(self.cost_mode, CostMode):
            try:
                self.cost_mode = CostMode(self.cost_mode)
            except ValueError:
                valid_modes = [m.value for m in CostMode]
                raise InvalidRoutingRequestError(
                    f"Invalid cost_mode '{self.cost_mode}'. Must be one of {valid_modes}.",
                    field="cost_mode",
                )
        if not isinstance(self.algorithm, RoutingAlgorithm):
            try:
                self.algorithm = RoutingAlgorithm(self.algorithm)
            except ValueError:
                valid_algos = [a.value for a in RoutingAlgorithm]
                raise InvalidRoutingRequestError(
                    f"Invalid algorithm '{self.algorithm}'. Must be one of {valid_algos}.",
                    field="algorithm",
                )
        if not isinstance(self.closed_edge_ids, (set, list, tuple)):
            raise InvalidRoutingRequestError(
                "closed_edge_ids must be a set, list, or tuple of edge IDs.",
                field="closed_edge_ids",
            )
        self.closed_edge_ids = set(self.closed_edge_ids)


@dataclass
class RoutingResult:
    """Comprehensive, typed output produced by Dijkstra and A* path planners."""

    success: bool
    algorithm: RoutingAlgorithm
    cost_mode: CostMode
    start_node_id: str
    destination_node_id: str
    node_ids: list[str]
    edge_ids: list[str]
    total_distance_m: float
    estimated_duration_s: float
    objective_cost: float
    nodes_expanded: int
    edges_examined: int
    execution_time_ms: float
    route: Optional[Route] = None

    def __post_init__(self) -> None:
        if self.total_distance_m < 0.0:
            raise InvalidRoutingRequestError("total_distance_m must be non-negative.")
        if self.estimated_duration_s < 0.0:
            raise InvalidRoutingRequestError("estimated_duration_s must be non-negative.")
        if self.objective_cost < 0.0:
            raise InvalidRoutingRequestError("objective_cost must be non-negative.")
        if self.nodes_expanded < 0:
            raise InvalidRoutingRequestError("nodes_expanded must be non-negative.")
        if self.edges_examined < 0:
            raise InvalidRoutingRequestError("edges_examined must be non-negative.")
        if self.execution_time_ms < 0.0:
            raise InvalidRoutingRequestError("execution_time_ms must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        """Convert routing result to a JSON-serializable dictionary."""
        return {
            "success": self.success,
            "algorithm": self.algorithm.value,
            "cost_mode": self.cost_mode.value,
            "start_node_id": self.start_node_id,
            "destination_node_id": self.destination_node_id,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "total_distance_m": round(self.total_distance_m, 3),
            "estimated_duration_s": round(self.estimated_duration_s, 3),
            "objective_cost": round(self.objective_cost, 4),
            "nodes_expanded": self.nodes_expanded,
            "edges_examined": self.edges_examined,
            "execution_time_ms": round(self.execution_time_ms, 3),
            "route": domain_to_dict(self.route) if self.route is not None else None,
        }
