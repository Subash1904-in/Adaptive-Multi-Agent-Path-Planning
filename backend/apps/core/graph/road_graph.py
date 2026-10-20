"""RoadGraph abstraction wrapping NetworkX directed graph for AMAPP.

Provides type-safe storage, indexed lookup, topological queries,
connectivity checks, and export for RoadNode, RoadEdge, and TrafficSignal entities.
"""

from typing import Any, Optional

import networkx as nx

from apps.core.domain.models import RoadEdge, RoadNode, TrafficSignal
from apps.core.domain.serialization import to_dict
from apps.core.graph.exceptions import (
    DuplicateEntityError,
    EdgeNotFoundError,
    GraphValidationError,
    NodeNotFoundError,
)


class RoadGraph:
    """Directed road network graph for autonomous vehicle simulation.

    Wraps a `networkx.DiGraph` with authoritative storage of typed domain
    models (RoadNode, RoadEdge, TrafficSignal) and domain invariant validation.
    """

    def __init__(self, name: str = "road_network") -> None:
        self.name = name
        self._graph: nx.DiGraph = nx.DiGraph(name=name)
        self._nodes: dict[str, RoadNode] = {}
        self._edges: dict[str, RoadEdge] = {}
        self._edges_by_endpoints: dict[tuple[str, str], RoadEdge] = {}
        self._signals: dict[str, TrafficSignal] = {}

    @property
    def node_count(self) -> int:
        """Total number of road nodes in the network."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Total number of directed road edges in the network."""
        return len(self._edges)

    @property
    def signal_count(self) -> int:
        """Total number of traffic signals in the network."""
        return len(self._signals)

    @property
    def networkx_graph(self) -> nx.DiGraph:
        """Access the underlying NetworkX directed graph."""
        return self._graph

    # -------------------------------------------------------------------------
    # Node Operations
    # -------------------------------------------------------------------------
    def add_node(self, node: RoadNode) -> None:
        """Add a typed RoadNode to the graph.

        Raises:
            GraphValidationError: If node is not an instance of RoadNode.
            DuplicateEntityError: If a node with the same ID already exists.
        """
        if not isinstance(node, RoadNode):
            raise GraphValidationError(
                f"Expected RoadNode instance, got {type(node).__name__}.",
                field="node",
            )
        if node.id in self._nodes:
            raise DuplicateEntityError("RoadNode", node.id)

        self._nodes[node.id] = node
        self._graph.add_node(
            node.id,
            data=node,
            x=node.position.x,
            y=node.position.y,
        )

    def has_node(self, node_id: str) -> bool:
        """Check if a node identifier exists in the graph."""
        return node_id in self._nodes

    def get_node(self, node_id: str) -> RoadNode:
        """Retrieve a RoadNode by identifier.

        Raises:
            NodeNotFoundError: If node_id does not exist.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return self._nodes[node_id]

    def node_ids(self) -> list[str]:
        """Return a list of all node identifiers."""
        return list(self._nodes.keys())

    def nodes(self) -> list[RoadNode]:
        """Return a list of all RoadNode domain objects."""
        return list(self._nodes.values())

    # -------------------------------------------------------------------------
    # Edge Operations
    # -------------------------------------------------------------------------
    def add_edge(self, edge: RoadEdge) -> None:
        """Add a directed RoadEdge connecting two existing nodes.

        Raises:
            GraphValidationError: If edge is not RoadEdge or endpoints are invalid.
            DuplicateEntityError: If edge ID or directed connection already exists.
            NodeNotFoundError: If start_node_id or end_node_id is not in graph.
        """
        if not isinstance(edge, RoadEdge):
            raise GraphValidationError(
                f"Expected RoadEdge instance, got {type(edge).__name__}.",
                field="edge",
            )
        if edge.id in self._edges:
            raise DuplicateEntityError("RoadEdge", edge.id)

        if edge.start_node_id not in self._nodes:
            raise NodeNotFoundError(
                edge.start_node_id,
                message=(
                    f"Cannot add edge '{edge.id}': start node '{edge.start_node_id}' "
                    "does not exist in graph."
                ),
            )
        if edge.end_node_id not in self._nodes:
            raise NodeNotFoundError(
                edge.end_node_id,
                message=(
                    f"Cannot add edge '{edge.id}': end node '{edge.end_node_id}' "
                    "does not exist in graph."
                ),
            )

        endpoint_pair = (edge.start_node_id, edge.end_node_id)
        if endpoint_pair in self._edges_by_endpoints:
            raise DuplicateEntityError(
                "Directed edge",
                f"{edge.start_node_id} -> {edge.end_node_id}",
            )

        self._edges[edge.id] = edge
        self._edges_by_endpoints[endpoint_pair] = edge
        self._graph.add_edge(
            edge.start_node_id,
            edge.end_node_id,
            id=edge.id,
            data=edge,
            weight=edge.length_m,
            length_m=edge.length_m,
            speed_limit_mps=edge.speed_limit_mps,
        )

    def has_edge(self, edge_id: str) -> bool:
        """Check if an edge identifier exists in the graph."""
        return edge_id in self._edges

    def get_edge(self, edge_id: str) -> RoadEdge:
        """Retrieve a RoadEdge by identifier.

        Raises:
            EdgeNotFoundError: If edge_id does not exist.
        """
        if edge_id not in self._edges:
            raise EdgeNotFoundError(edge_id)
        return self._edges[edge_id]

    def get_edge_between(self, start_node_id: str, end_node_id: str) -> Optional[RoadEdge]:
        """Retrieve the directed RoadEdge between two nodes, or None if no edge exists."""
        return self._edges_by_endpoints.get((start_node_id, end_node_id))

    def has_edge_between(self, start_node_id: str, end_node_id: str) -> bool:
        """Check if a directed edge exists from start_node_id to end_node_id."""
        return (start_node_id, end_node_id) in self._edges_by_endpoints

    def edge_ids(self) -> list[str]:
        """Return a list of all edge identifiers."""
        return list(self._edges.keys())

    def edges(self) -> list[RoadEdge]:
        """Return a list of all RoadEdge domain objects."""
        return list(self._edges.values())

    # -------------------------------------------------------------------------
    # Traffic Signal Operations
    # -------------------------------------------------------------------------
    def add_traffic_signal(self, signal: TrafficSignal) -> None:
        """Associate a TrafficSignal with an existing node in the graph.

        Raises:
            GraphValidationError: If signal is not an instance of TrafficSignal.
            NodeNotFoundError: If signal.node_id does not exist in graph.
            DuplicateEntityError: If a signal already exists at this node.
        """
        if not isinstance(signal, TrafficSignal):
            raise GraphValidationError(
                f"Expected TrafficSignal instance, got {type(signal).__name__}.",
                field="signal",
            )
        if signal.node_id not in self._nodes:
            raise NodeNotFoundError(
                signal.node_id,
                message=(
                    f"Cannot add traffic signal '{signal.id}': node '{signal.node_id}' "
                    "does not exist in graph."
                ),
            )
        if signal.node_id in self._signals:
            raise DuplicateEntityError("TrafficSignal at node", signal.node_id)

        self._signals[signal.node_id] = signal

    def get_traffic_signal(self, node_id: str) -> Optional[TrafficSignal]:
        """Retrieve the traffic signal governing the given node, or None."""
        return self._signals.get(node_id)

    def get_traffic_signals(self) -> dict[str, TrafficSignal]:
        """Return all traffic signals mapped by node_id."""
        return dict(self._signals)

    # -------------------------------------------------------------------------
    # Neighbors & Adjacency
    # -------------------------------------------------------------------------
    def get_outgoing_neighbors(self, node_id: str) -> list[str]:
        """Return IDs of nodes reachable via a single outgoing directed edge."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return list(self._graph.successors(node_id))

    def get_incoming_neighbors(self, node_id: str) -> list[str]:
        """Return IDs of nodes that have a directed edge into node_id."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return list(self._graph.predecessors(node_id))

    def get_outgoing_edges(self, node_id: str) -> list[RoadEdge]:
        """Return RoadEdge objects emanating from node_id."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return [
            self._edges_by_endpoints[(node_id, succ)] for succ in self._graph.successors(node_id)
        ]

    def get_incoming_edges(self, node_id: str) -> list[RoadEdge]:
        """Return RoadEdge objects pointing into node_id."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return [
            self._edges_by_endpoints[(pred, node_id)] for pred in self._graph.predecessors(node_id)
        ]

    # -------------------------------------------------------------------------
    # Connectivity & Reachability
    # -------------------------------------------------------------------------
    def is_weakly_connected(self) -> bool:
        """Check if the graph is weakly connected (ignoring edge directionality)."""
        if self.node_count <= 1:
            return True
        return nx.is_weakly_connected(self._graph)

    def is_strongly_connected(self) -> bool:
        """Check if every node is mutually reachable via directed paths."""
        if self.node_count <= 1:
            return True
        return nx.is_strongly_connected(self._graph)

    def is_reachable(self, source_id: str, target_id: str) -> bool:
        """Check if a directed path exists from source_id to target_id."""
        if source_id not in self._nodes:
            raise NodeNotFoundError(source_id)
        if target_id not in self._nodes:
            raise NodeNotFoundError(target_id)
        return nx.has_path(self._graph, source_id, target_id)

    def has_alternative_paths(self, source_id: str, target_id: str) -> bool:
        """Check if at least two distinct simple paths exist between source and target."""
        if source_id not in self._nodes:
            raise NodeNotFoundError(source_id)
        if target_id not in self._nodes:
            raise NodeNotFoundError(target_id)
        paths_generator = nx.all_simple_paths(self._graph, source_id, target_id)
        first_path = next(paths_generator, None)
        if first_path is None:
            return False
        second_path = next(paths_generator, None)
        return second_path is not None

    def get_isolated_nodes(self) -> list[str]:
        """Return identifiers of nodes with no incoming or outgoing edges."""
        return [
            node_id
            for node_id in self._nodes
            if self._graph.in_degree(node_id) == 0 and self._graph.out_degree(node_id) == 0
        ]

    # -------------------------------------------------------------------------
    # Validation & Integrity
    # -------------------------------------------------------------------------
    def validate_topology(self) -> None:
        """Validate internal integrity between domain storage and NetworkX graph.

        Raises:
            GraphValidationError: If any inconsistency is identified.
        """
        if len(self._nodes) != self._graph.number_of_nodes():
            raise GraphValidationError(
                f"Node count mismatch: storage has {len(self._nodes)}, "
                f"NetworkX has {self._graph.number_of_nodes()}."
            )
        if len(self._edges) != self._graph.number_of_edges():
            raise GraphValidationError(
                f"Edge count mismatch: storage has {len(self._edges)}, "
                f"NetworkX has {self._graph.number_of_edges()}."
            )

        for edge_id, edge in self._edges.items():
            if edge.start_node_id not in self._nodes:
                raise GraphValidationError(
                    f"Edge '{edge_id}' start node '{edge.start_node_id}' not in nodes."
                )
            if edge.end_node_id not in self._nodes:
                raise GraphValidationError(
                    f"Edge '{edge_id}' end node '{edge.end_node_id}' not in nodes."
                )
            if not self._graph.has_edge(edge.start_node_id, edge.end_node_id):
                raise GraphValidationError(
                    f"Edge '{edge_id}' ({edge.start_node_id} -> {edge.end_node_id}) "
                    "missing from NetworkX graph."
                )

        for node_id, signal in self._signals.items():
            if node_id not in self._nodes:
                raise GraphValidationError(
                    f"Traffic signal '{signal.id}' references non-existent node '{node_id}'."
                )

    # -------------------------------------------------------------------------
    # Export / Serialization
    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Export the road graph to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "metadata": {
                "node_count": self.node_count,
                "edge_count": self.edge_count,
                "signal_count": self.signal_count,
                "is_strongly_connected": self.is_strongly_connected(),
                "is_weakly_connected": self.is_weakly_connected(),
            },
            "nodes": [to_dict(node) for node in self._nodes.values()],
            "edges": [to_dict(edge) for edge in self._edges.values()],
            "signals": [to_dict(sig) for sig in self._signals.values()],
        }
