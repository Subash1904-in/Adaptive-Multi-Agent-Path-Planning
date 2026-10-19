"""Graph-level exceptions for AMAPP road network topology."""

from typing import Optional

from apps.core.domain.exceptions import DomainException


class GraphException(DomainException):
    """Base exception for all road graph operations."""

    pass


class GraphValidationError(GraphException, ValueError):
    """Raised when road graph structural or topological invariants are violated."""

    pass


class NodeNotFoundError(GraphException, KeyError):
    """Raised when a requested road node identifier does not exist in the graph."""

    def __init__(self, node_id: str, message: Optional[str] = None) -> None:
        msg = message or f"RoadNode with ID '{node_id}' does not exist in the graph."
        super().__init__(msg, field="node_id")
        self.node_id = node_id


class EdgeNotFoundError(GraphException, KeyError):
    """Raised when a requested road edge identifier does not exist in the graph."""

    def __init__(self, edge_id: str, message: Optional[str] = None) -> None:
        msg = message or f"RoadEdge with ID '{edge_id}' does not exist in the graph."
        super().__init__(msg, field="edge_id")
        self.edge_id = edge_id


class DuplicateEntityError(GraphException, ValueError):
    """Raised when attempting to insert a node or edge with an ID that already exists."""

    def __init__(self, entity_type: str, identifier: str) -> None:
        msg = f"{entity_type} with ID '{identifier}' already exists in the graph."
        super().__init__(msg, field="id")
        self.entity_type = entity_type
        self.identifier = identifier
