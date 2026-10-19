"""Unit tests for the RoadGraph abstraction and invariants."""

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import RoadEdge, RoadNode, TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.graph.exceptions import (
    DuplicateEntityError,
    EdgeNotFoundError,
    GraphValidationError,
    NodeNotFoundError,
)
from apps.core.graph.road_graph import RoadGraph


class TestRoadGraphNodes:
    """Tests for RoadNode storage and queries in RoadGraph."""

    def test_add_and_retrieve_node(self) -> None:
        graph = RoadGraph()
        node = RoadNode(id="n1", position=Position2D(10.0, 20.0))
        graph.add_node(node)

        assert graph.node_count == 1
        assert graph.has_node("n1")
        assert not graph.has_node("n2")
        retrieved = graph.get_node("n1")
        assert retrieved == node
        assert graph.node_ids() == ["n1"]
        assert graph.nodes() == [node]

    def test_get_nonexistent_node_raises_node_not_found(self) -> None:
        graph = RoadGraph()
        with pytest.raises(NodeNotFoundError) as exc_info:
            graph.get_node("ghost_node")
        assert "ghost_node" in str(exc_info.value)
        assert exc_info.value.node_id == "ghost_node"

    def test_add_duplicate_node_id_raises_duplicate_error(self) -> None:
        graph = RoadGraph()
        n1 = RoadNode(id="n1", position=Position2D(0.0, 0.0))
        n2 = RoadNode(id="n1", position=Position2D(5.0, 5.0))
        graph.add_node(n1)

        with pytest.raises(DuplicateEntityError) as exc_info:
            graph.add_node(n2)
        assert "RoadNode with ID 'n1' already exists" in str(exc_info.value)

    def test_add_invalid_node_type_raises_validation_error(self) -> None:
        graph = RoadGraph()
        with pytest.raises(GraphValidationError):
            graph.add_node("not-a-node")  # type: ignore[arg-type]


class TestRoadGraphEdges:
    """Tests for RoadEdge storage, directed topology, and invariants."""

    @pytest.fixture
    def triangle_graph(self) -> RoadGraph:
        """Create a simple 3-node graph: n1 -> n2 -> n3 -> n1."""
        graph = RoadGraph(name="triangle")
        graph.add_node(RoadNode(id="n1", position=Position2D(0.0, 0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(100.0, 0.0)))
        graph.add_node(RoadNode(id="n3", position=Position2D(100.0, 100.0)))
        return graph

    def test_add_and_retrieve_edge(self, triangle_graph: RoadGraph) -> None:
        edge = RoadEdge(
            id="e1_2",
            start_node_id="n1",
            end_node_id="n2",
            length_m=100.0,
            speed_limit_mps=13.89,
        )
        triangle_graph.add_edge(edge)

        assert triangle_graph.edge_count == 1
        assert triangle_graph.has_edge("e1_2")
        assert not triangle_graph.has_edge("e_unknown")
        assert triangle_graph.get_edge("e1_2") == edge
        assert triangle_graph.get_edge_between("n1", "n2") == edge
        assert triangle_graph.get_edge_between("n2", "n1") is None

    def test_edge_with_missing_start_node_raises_node_not_found(self) -> None:
        graph = RoadGraph()
        graph.add_node(RoadNode(id="n2", position=Position2D(10.0, 0.0)))
        edge = RoadEdge(
            id="e_orphan",
            start_node_id="n1",
            end_node_id="n2",
            length_m=10.0,
            speed_limit_mps=10.0,
        )
        with pytest.raises(NodeNotFoundError) as exc_info:
            graph.add_edge(edge)
        assert "start node 'n1' does not exist" in str(exc_info.value)

    def test_edge_with_missing_end_node_raises_node_not_found(self) -> None:
        graph = RoadGraph()
        graph.add_node(RoadNode(id="n1", position=Position2D(0.0, 0.0)))
        edge = RoadEdge(
            id="e_orphan",
            start_node_id="n1",
            end_node_id="n2",
            length_m=10.0,
            speed_limit_mps=10.0,
        )
        with pytest.raises(NodeNotFoundError) as exc_info:
            graph.add_edge(edge)
        assert "end node 'n2' does not exist" in str(exc_info.value)

    def test_duplicate_edge_id_raises_duplicate_error(self, triangle_graph: RoadGraph) -> None:
        e1 = RoadEdge(
            id="e1",
            start_node_id="n1",
            end_node_id="n2",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        e2 = RoadEdge(
            id="e1",
            start_node_id="n2",
            end_node_id="n3",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        triangle_graph.add_edge(e1)
        with pytest.raises(DuplicateEntityError):
            triangle_graph.add_edge(e2)

    def test_duplicate_directed_connection_raises_duplicate_error(
        self, triangle_graph: RoadGraph
    ) -> None:
        e1 = RoadEdge(
            id="e_first",
            start_node_id="n1",
            end_node_id="n2",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        e2 = RoadEdge(
            id="e_second",
            start_node_id="n1",
            end_node_id="n2",
            length_m=100.0,
            speed_limit_mps=15.0,
        )
        triangle_graph.add_edge(e1)
        with pytest.raises(DuplicateEntityError) as exc_info:
            triangle_graph.add_edge(e2)
        assert "Directed edge with ID 'n1 -> n2' already exists" in str(exc_info.value)

    def test_distinct_reverse_directed_edge_is_permitted(
        self, triangle_graph: RoadGraph
    ) -> None:
        forward = RoadEdge(
            id="e_fwd",
            start_node_id="n1",
            end_node_id="n2",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        reverse = RoadEdge(
            id="e_rev",
            start_node_id="n2",
            end_node_id="n1",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        triangle_graph.add_edge(forward)
        triangle_graph.add_edge(reverse)

        assert triangle_graph.edge_count == 2
        assert triangle_graph.get_edge_between("n1", "n2") == forward
        assert triangle_graph.get_edge_between("n2", "n1") == reverse

    def test_get_nonexistent_edge_raises_edge_not_found(self) -> None:
        graph = RoadGraph()
        with pytest.raises(EdgeNotFoundError) as exc_info:
            graph.get_edge("ghost_edge")
        assert exc_info.value.edge_id == "ghost_edge"


class TestRoadGraphTopologyAndNeighbors:
    """Tests for adjacency, neighborhoods, connectivity, and reachability."""

    @pytest.fixture
    def linear_graph(self) -> RoadGraph:
        """Create a directed linear chain: n1 -> n2 -> n3."""
        graph = RoadGraph()
        graph.add_node(RoadNode(id="n1", position=Position2D(0.0, 0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(50.0, 0.0)))
        graph.add_node(RoadNode(id="n3", position=Position2D(100.0, 0.0)))
        graph.add_edge(
            RoadEdge(
                id="e1_2",
                start_node_id="n1",
                end_node_id="n2",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e2_3",
                start_node_id="n2",
                end_node_id="n3",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        return graph

    def test_incoming_and_outgoing_neighbors(self, linear_graph: RoadGraph) -> None:
        assert linear_graph.get_outgoing_neighbors("n1") == ["n2"]
        assert linear_graph.get_incoming_neighbors("n1") == []

        assert linear_graph.get_outgoing_neighbors("n2") == ["n3"]
        assert linear_graph.get_incoming_neighbors("n2") == ["n1"]

        assert linear_graph.get_outgoing_neighbors("n3") == []
        assert linear_graph.get_incoming_neighbors("n3") == ["n2"]

    def test_incoming_and_outgoing_edges(self, linear_graph: RoadGraph) -> None:
        out_edges = linear_graph.get_outgoing_edges("n2")
        assert len(out_edges) == 1
        assert out_edges[0].id == "e2_3"

        in_edges = linear_graph.get_incoming_edges("n2")
        assert len(in_edges) == 1
        assert in_edges[0].id == "e1_2"

    def test_weak_vs_strong_connectivity(self, linear_graph: RoadGraph) -> None:
        # Linear directed chain is weakly connected, but NOT strongly connected
        assert linear_graph.is_weakly_connected()
        assert not linear_graph.is_strongly_connected()

        # Add back edge n3 -> n1 to make it a directed cycle
        linear_graph.add_edge(
            RoadEdge(
                id="e3_1",
                start_node_id="n3",
                end_node_id="n1",
                length_m=100.0,
                speed_limit_mps=10.0,
            )
        )
        assert linear_graph.is_strongly_connected()

    def test_reachability(self, linear_graph: RoadGraph) -> None:
        assert linear_graph.is_reachable("n1", "n3")
        assert not linear_graph.is_reachable("n3", "n1")

    def test_reachability_missing_nodes_raise(self, linear_graph: RoadGraph) -> None:
        with pytest.raises(NodeNotFoundError):
            linear_graph.is_reachable("n1", "ghost")
        with pytest.raises(NodeNotFoundError):
            linear_graph.is_reachable("ghost", "n1")

    def test_isolated_nodes(self) -> None:
        graph = RoadGraph()
        graph.add_node(RoadNode(id="n1", position=Position2D(0.0, 0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(10.0, 0.0)))
        graph.add_node(RoadNode(id="isolated", position=Position2D(100.0, 100.0)))
        graph.add_edge(
            RoadEdge(
                id="e1_2",
                start_node_id="n1",
                end_node_id="n2",
                length_m=10.0,
                speed_limit_mps=10.0,
            )
        )

        assert graph.get_isolated_nodes() == ["isolated"]
        assert not graph.is_weakly_connected()


class TestRoadGraphSignalsAndExport:
    """Tests for traffic signals and dictionary export."""

    def test_traffic_signal_management(self) -> None:
        graph = RoadGraph()
        node = RoadNode(id="n_sig", position=Position2D(50.0, 50.0))
        graph.add_node(node)

        signal = TrafficSignal(
            id="sig_1",
            node_id="n_sig",
            state=TrafficSignalState.GREEN,
            cycle_duration_s=60.0,
            remaining_phase_s=20.0,
        )
        graph.add_traffic_signal(signal)

        assert graph.signal_count == 1
        assert graph.get_traffic_signal("n_sig") == signal
        assert graph.get_traffic_signal("other_node") is None

    def test_signal_on_missing_node_raises_node_not_found(self) -> None:
        graph = RoadGraph()
        signal = TrafficSignal(
            id="sig_1",
            node_id="missing_node",
        )
        with pytest.raises(NodeNotFoundError):
            graph.add_traffic_signal(signal)

    def test_duplicate_signal_on_node_raises_duplicate_error(self) -> None:
        graph = RoadGraph()
        graph.add_node(RoadNode(id="n1", position=Position2D(0.0, 0.0)))
        s1 = TrafficSignal(id="sig_1", node_id="n1")
        s2 = TrafficSignal(id="sig_2", node_id="n1")

        graph.add_traffic_signal(s1)
        with pytest.raises(DuplicateEntityError):
            graph.add_traffic_signal(s2)

    def test_to_dict_export(self) -> None:
        graph = RoadGraph(name="test_city")
        n1 = RoadNode(id="n1", position=Position2D(0.0, 0.0))
        n2 = RoadNode(id="n2", position=Position2D(50.0, 0.0))
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(
            RoadEdge(
                id="e1_2",
                start_node_id="n1",
                end_node_id="n2",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        graph.add_traffic_signal(TrafficSignal(id="sig_n1", node_id="n1"))

        data = graph.to_dict()
        assert data["name"] == "test_city"
        assert data["metadata"]["node_count"] == 2
        assert data["metadata"]["edge_count"] == 1
        assert data["metadata"]["signal_count"] == 1
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert len(data["signals"]) == 1
