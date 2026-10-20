"""Routing exceptions for the AMAPP route planning subsystem."""

from typing import Optional

from apps.core.domain.exceptions import DomainException
from apps.core.graph.exceptions import NodeNotFoundError


class RoutingError(DomainException):
    """Base exception for all route planning operations."""

    pass


class RoutingNodeNotFoundError(RoutingError, NodeNotFoundError):
    """Raised when a requested start or destination node is missing from the road graph."""

    def __init__(self, node_id: str, role: str = "node", message: Optional[str] = None) -> None:
        msg = message or f"Routing {role} node '{node_id}' does not exist in the road graph."
        super().__init__(node_id=node_id, message=msg)
        self.role = role


class NoPathFoundError(RoutingError):
    """Raised when no traversable path exists from start to destination."""

    def __init__(
        self,
        start_node_id: str,
        destination_node_id: str,
        message: Optional[str] = None,
        closed_edge_count: int = 0,
    ) -> None:
        closure_info = (
            f" ({closed_edge_count} closed edges active)" if closed_edge_count > 0 else ""
        )
        msg = (
            message
            or f"No path found from '{start_node_id}' to '{destination_node_id}'{closure_info}."
        )
        super().__init__(msg, field="path")
        self.start_node_id = start_node_id
        self.destination_node_id = destination_node_id
        self.closed_edge_count = closed_edge_count


class InvalidRoutingRequestError(RoutingError, ValueError):
    """Raised when routing parameters or graph configuration violate invariants."""

    pass


class AdaptiveRoutingError(RoutingError):
    """Base exception for adaptive dynamic routing and route adjustment operations."""

    pass


class RouteReplacementError(AdaptiveRoutingError):
    """Raised when active route replacement violates continuity or connectivity."""

    def __init__(
        self,
        message: str,
        vehicle_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(message, field="route")
        self.vehicle_id = vehicle_id
        self.reason = reason


class InvalidReroutePolicyError(AdaptiveRoutingError, ValueError):
    """Raised when adaptive rerouting policy configuration violates validation invariants."""

    pass
