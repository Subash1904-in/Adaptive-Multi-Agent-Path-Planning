"""Unit tests for Dijkstra shortest-path pathfinding on directed RoadGraph."""

import pytest

from apps.core.domain.models import Position2D, RoadEdge, RoadNode, Route
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.exceptions import NoPathFoundError, RoutingNodeNotFoundError
from apps.core.routing.models import CostMode, RoutingAlgorithm


def _make_node(node_id: str, x: float, y: float) -> RoadNode:
    return RoadNode(id=node_id, position=Position2D(x=x, y=y))


def _make_edge(
    edge_id: str,
    u: str,
    v: str,
    length_m: float = 100.0,
    speed_limit_mps: float = 10.0,
) -> RoadEdge:
    return RoadEdge(
        id=edge_id,
        start_node_id=u,
        end_node_id=v,
        length_m=length_m,
        speed_limit_mps=speed_limit_mps,
    )


class TestDijkstraSearch:
    """Comprehensive test suite for Dijkstra shortest-path routing."""

    @pytest.fixture
    def diamond_graph(self) -> RoadGraph:
        """Diamond topology:
                 B (slow short: 500m @ 5 m/s = 100s)
               /   \
             A       D
               \\   /
                 C (fast long: 1000m @ 25 m/s = 40s)
        """
        g = RoadGraph("diamond")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 500.0, 100.0))
        g.add_node(_make_node("C", 500.0, -100.0))
        g.add_node(_make_node("D", 1000.0, 0.0))

        # Upper path via B: total length = 250 + 250 = 500m; time = 50 + 50 = 100s
        g.add_edge(_make_edge("e_AB", "A", "B", length_m=250.0, speed_limit_mps=5.0))
        g.add_edge(_make_edge("e_BD", "B", "D", length_m=250.0, speed_limit_mps=5.0))

        # Lower path via C: total length = 500 + 500 = 1000m; time = 20 + 20 = 40s
        g.add_edge(_make_edge("e_AC", "A", "C", length_m=500.0, speed_limit_mps=25.0))
        g.add_edge(_make_edge("e_CD", "C", "D", length_m=500.0, speed_limit_mps=25.0))

        return g

    def test_known_shortest_distance_selects_shorter_path(
        self, diamond_graph: RoadGraph
    ) -> None:
        result = dijkstra_search(
            diamond_graph, "A", "D", cost_mode=CostMode.DISTANCE
        )
        assert result.success is True
        assert result.algorithm == RoutingAlgorithm.DIJKSTRA
        assert result.cost_mode == CostMode.DISTANCE
        assert result.node_ids == ["A", "B", "D"]
        assert result.edge_ids == ["e_AB", "e_BD"]
        assert result.total_distance_m == pytest.approx(500.0)
        assert result.estimated_duration_s == pytest.approx(100.0)
        assert result.objective_cost == pytest.approx(500.0)
        assert result.nodes_expanded > 0
        assert result.edges_examined > 0
        assert isinstance(result.route, Route)
        assert result.route.node_ids == ["A", "B", "D"]

    def test_known_fastest_time_selects_faster_path(
        self, diamond_graph: RoadGraph
    ) -> None:
        result = dijkstra_search(
            diamond_graph, "A", "D", cost_mode=CostMode.TRAVEL_TIME
        )
        assert result.success is True
        assert result.algorithm == RoutingAlgorithm.DIJKSTRA
        assert result.cost_mode == CostMode.TRAVEL_TIME
        assert result.node_ids == ["A", "C", "D"]
        assert result.edge_ids == ["e_AC", "e_CD"]
        assert result.total_distance_m == pytest.approx(1000.0)
        assert result.estimated_duration_s == pytest.approx(40.0)
        assert result.objective_cost == pytest.approx(40.0)

    def test_one_way_restrictions_respected(self, diamond_graph: RoadGraph) -> None:
        # D -> A has no reverse edges in diamond_graph
        with pytest.raises(NoPathFoundError, match="No path found from 'D' to 'A'"):
            dijkstra_search(diamond_graph, "D", "A")

    def test_start_equals_destination_returns_zero_cost(
        self, diamond_graph: RoadGraph
    ) -> None:
        result = dijkstra_search(diamond_graph, "A", "A")
        assert result.success is True
        assert result.node_ids == ["A"]
        assert result.edge_ids == []
        assert result.total_distance_m == 0.0
        assert result.estimated_duration_s == 0.0
        assert result.objective_cost == 0.0
        assert result.nodes_expanded == 0
        assert result.edges_examined == 0
        assert result.route is None

    def test_missing_start_node_raises(self, diamond_graph: RoadGraph) -> None:
        with pytest.raises(RoutingNodeNotFoundError, match="start node 'Z'"):
            dijkstra_search(diamond_graph, "Z", "D")

    def test_missing_destination_node_raises(self, diamond_graph: RoadGraph) -> None:
        with pytest.raises(RoutingNodeNotFoundError, match="destination node 'Z'"):
            dijkstra_search(diamond_graph, "A", "Z")

    def test_disconnected_destination_raises(self) -> None:
        g = RoadGraph("disconnected")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 100.0, 0.0))
        # No edges connecting A and B
        with pytest.raises(NoPathFoundError, match="No path found from 'A' to 'B'"):
            dijkstra_search(g, "A", "B")

    def test_closed_edge_reroutes_to_alternative(
        self, diamond_graph: RoadGraph
    ) -> None:
        # In travel time mode, normal path is A -> C -> D.
        # Closing e_AC forces reroute via A -> B -> D.
        result = dijkstra_search(
            diamond_graph,
            "A",
            "D",
            cost_mode=CostMode.TRAVEL_TIME,
            closed_edge_ids={"e_AC"},
        )
        assert result.success is True
        assert result.node_ids == ["A", "B", "D"]
        assert result.edge_ids == ["e_AB", "e_BD"]

    def test_all_paths_blocked_by_closures_raises(
        self, diamond_graph: RoadGraph
    ) -> None:
        # Closing e_AB and e_AC leaves no traversable path from A to D
        with pytest.raises(NoPathFoundError, match="2 closed edges active"):
            dijkstra_search(
                diamond_graph,
                "A",
                "D",
                closed_edge_ids={"e_AB", "e_AC"},
            )

    def test_closed_edge_directionality_preserved(self) -> None:
        g = RoadGraph("two_way")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 100.0, 0.0))
        g.add_edge(_make_edge("e_forward", "A", "B"))
        g.add_edge(_make_edge("e_backward", "B", "A"))

        # Closing e_forward blocks A -> B
        with pytest.raises(NoPathFoundError):
            dijkstra_search(g, "A", "B", closed_edge_ids={"e_forward"})

        # But B -> A is still open!
        res = dijkstra_search(g, "B", "A", closed_edge_ids={"e_forward"})
        assert res.success is True
        assert res.edge_ids == ["e_backward"]

    def test_deterministic_results_across_runs(
        self, diamond_graph: RoadGraph
    ) -> None:
        res1 = dijkstra_search(diamond_graph, "A", "D", CostMode.TRAVEL_TIME)
        res2 = dijkstra_search(diamond_graph, "A", "D", CostMode.TRAVEL_TIME)
        assert res1.node_ids == res2.node_ids
        assert res1.edge_ids == res2.edge_ids
        assert res1.objective_cost == res2.objective_cost
        assert res1.nodes_expanded == res2.nodes_expanded
        assert res1.edges_examined == res2.edges_examined
