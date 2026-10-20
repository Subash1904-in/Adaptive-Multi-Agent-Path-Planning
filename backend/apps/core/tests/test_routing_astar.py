"""Unit tests for custom A* shortest-path pathfinding on directed RoadGraph."""

import pytest

from apps.core.domain.models import Position2D, RoadEdge, RoadNode
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.astar import astar_search
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


class TestAStarSearch:
    """Comprehensive test suite for custom A* route planning."""

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

        g.add_edge(_make_edge("e_AB", "A", "B", length_m=250.0, speed_limit_mps=5.0))
        g.add_edge(_make_edge("e_BD", "B", "D", length_m=250.0, speed_limit_mps=5.0))
        g.add_edge(_make_edge("e_AC", "A", "C", length_m=500.0, speed_limit_mps=25.0))
        g.add_edge(_make_edge("e_CD", "C", "D", length_m=500.0, speed_limit_mps=25.0))
        return g

    def test_astar_finds_optimal_distance_path(self, diamond_graph: RoadGraph) -> None:
        result = astar_search(diamond_graph, "A", "D", cost_mode=CostMode.DISTANCE)
        assert result.success is True
        assert result.algorithm == RoutingAlgorithm.ASTAR
        assert result.node_ids == ["A", "B", "D"]
        assert result.edge_ids == ["e_AB", "e_BD"]
        assert result.objective_cost == pytest.approx(500.0)

    def test_astar_finds_optimal_travel_time_path(self, diamond_graph: RoadGraph) -> None:
        result = astar_search(diamond_graph, "A", "D", cost_mode=CostMode.TRAVEL_TIME)
        assert result.success is True
        assert result.algorithm == RoutingAlgorithm.ASTAR
        assert result.node_ids == ["A", "C", "D"]
        assert result.edge_ids == ["e_AC", "e_CD"]
        assert result.objective_cost == pytest.approx(40.0)

    def test_astar_optimality_matches_dijkstra_on_synthetic_city(self) -> None:
        grid = generate_synthetic_city_grid(
            CityGridConfig(rows=4, cols=4, spacing_m=100.0, seed=42)
        )
        nodes = grid.node_ids()
        # Test multiple origin-destination pairs
        test_pairs = [
            (nodes[0], nodes[-1]),
            (nodes[0], nodes[5]),
            (nodes[3], nodes[12]),
            (nodes[2], nodes[14]),
        ]

        for u, v in test_pairs:
            for mode in (CostMode.DISTANCE, CostMode.TRAVEL_TIME):
                res_dijkstra = dijkstra_search(grid, u, v, cost_mode=mode)
                res_astar = astar_search(grid, u, v, cost_mode=mode)

                # Objective cost must be identical within floating point tolerance
                assert res_astar.objective_cost == pytest.approx(
                    res_dijkstra.objective_cost, abs=1e-5
                ), f"Cost mismatch between Dijkstra and A* for {u} -> {v} in mode {mode}"
                assert res_astar.total_distance_m == pytest.approx(
                    res_dijkstra.total_distance_m, abs=1e-5
                )
                assert res_astar.estimated_duration_s == pytest.approx(
                    res_dijkstra.estimated_duration_s, abs=1e-5
                )

    def test_astar_respects_one_way_restrictions(self, diamond_graph: RoadGraph) -> None:
        with pytest.raises(NoPathFoundError):
            astar_search(diamond_graph, "D", "A")

    def test_astar_start_equals_destination(self, diamond_graph: RoadGraph) -> None:
        res = astar_search(diamond_graph, "B", "B")
        assert res.success is True
        assert res.node_ids == ["B"]
        assert res.edge_ids == []
        assert res.objective_cost == 0.0
        assert res.nodes_expanded == 0
        assert res.edges_examined == 0
        assert res.route is None

    def test_astar_missing_nodes_raise(self, diamond_graph: RoadGraph) -> None:
        with pytest.raises(RoutingNodeNotFoundError, match="start node 'UNKNOWN'"):
            astar_search(diamond_graph, "UNKNOWN", "D")
        with pytest.raises(RoutingNodeNotFoundError, match="destination node 'UNKNOWN'"):
            astar_search(diamond_graph, "A", "UNKNOWN")

    def test_astar_closed_edges_rerouting(self, diamond_graph: RoadGraph) -> None:
        res = astar_search(
            diamond_graph, "A", "D", CostMode.TRAVEL_TIME, closed_edge_ids={"e_AC"}
        )
        assert res.success is True
        assert res.node_ids == ["A", "B", "D"]

    def test_astar_all_paths_blocked_raises(self, diamond_graph: RoadGraph) -> None:
        with pytest.raises(NoPathFoundError):
            astar_search(
                diamond_graph, "A", "D", closed_edge_ids={"e_AB", "e_AC"}
            )

    def test_astar_safe_zero_heuristic_fallback(self) -> None:
        # Create an inadmissible graph where edge length < Euclidean distance
        g = RoadGraph("inadmissible")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 100.0, 0.0))
        g.add_node(_make_node("C", 200.0, 0.0))
        g.add_edge(_make_edge("e_AB", "A", "B", length_m=50.0, speed_limit_mps=10.0))
        g.add_edge(_make_edge("e_BC", "B", "C", length_m=50.0, speed_limit_mps=10.0))

        # A* should automatically fall back to h=0 and still return the optimal path
        res_d = dijkstra_search(g, "A", "C", CostMode.DISTANCE)
        res_a = astar_search(g, "A", "C", CostMode.DISTANCE)

        assert res_a.objective_cost == pytest.approx(res_d.objective_cost)
        assert res_a.node_ids == ["A", "B", "C"]

    def test_astar_stale_queue_entries_handled_cleanly(self) -> None:
        # Topology where a node is pushed multiple times with improving costs
        g = RoadGraph("stale_test")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 10.0, 0.0))
        g.add_node(_make_node("C", 20.0, 0.0))
        g.add_node(_make_node("D", 30.0, 0.0))

        # Direct slow edge A -> C
        g.add_edge(_make_edge("e_AC", "A", "C", length_m=500.0, speed_limit_mps=5.0))
        # Faster path A -> B -> C
        g.add_edge(_make_edge("e_AB", "A", "B", length_m=100.0, speed_limit_mps=20.0))
        g.add_edge(_make_edge("e_BC", "B", "C", length_m=100.0, speed_limit_mps=20.0))
        # Final leg C -> D
        g.add_edge(_make_edge("e_CD", "C", "D", length_m=100.0, speed_limit_mps=20.0))

        res = astar_search(g, "A", "D", CostMode.TRAVEL_TIME)
        assert res.success is True
        assert res.node_ids == ["A", "B", "C", "D"]

    def test_astar_deterministic_tie_breaking(self) -> None:
        grid = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=100.0, seed=123)
        )
        nodes = grid.node_ids()
        res1 = astar_search(grid, nodes[0], nodes[-1], CostMode.DISTANCE)
        res2 = astar_search(grid, nodes[0], nodes[-1], CostMode.DISTANCE)
        assert res1.node_ids == res2.node_ids
        assert res1.edge_ids == res2.edge_ids
        assert res1.nodes_expanded == res2.nodes_expanded
