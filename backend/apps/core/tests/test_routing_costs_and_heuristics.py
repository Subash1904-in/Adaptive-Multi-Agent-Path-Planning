"""Unit tests for AMAPP routing cost policies, traversability, and heuristics."""

import pytest

from apps.core.domain.models import Position2D, RoadEdge, RoadNode
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.costs import (
    calculate_edge_cost,
    calculate_route_metrics,
    is_edge_traversable,
)
from apps.core.routing.exceptions import InvalidRoutingRequestError
from apps.core.routing.heuristics import (
    check_heuristic_admissibility,
    get_heuristic_function,
)
from apps.core.routing.models import CostMode


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


class TestRoutingCosts:
    """Tests for edge cost calculation and edge traversability checks."""

    def test_distance_cost_returns_length_in_meters(self) -> None:
        edge = _make_edge("e1", "n1", "n2", length_m=250.5, speed_limit_mps=25.0)
        cost = calculate_edge_cost(edge, CostMode.DISTANCE)
        assert cost == pytest.approx(250.5)

    def test_travel_time_cost_returns_seconds(self) -> None:
        edge = _make_edge("e1", "n1", "n2", length_m=300.0, speed_limit_mps=15.0)
        cost = calculate_edge_cost(edge, CostMode.TRAVEL_TIME)
        # 300 meters / 15 m/s = 20.0 seconds
        assert cost == pytest.approx(20.0)

    def test_invalid_cost_mode_raises(self) -> None:
        edge = _make_edge("e1", "n1", "n2")
        with pytest.raises(InvalidRoutingRequestError, match="Unsupported cost mode"):
            calculate_edge_cost(edge, "invalid_mode")  # type: ignore

    def test_non_positive_length_raises(self) -> None:
        edge = _make_edge("e1", "n1", "n2")
        edge.length_m = -10.0  # bypass post-init for defensive test
        with pytest.raises(InvalidRoutingRequestError, match="invalid length_m"):
            calculate_edge_cost(edge, CostMode.DISTANCE)

    def test_non_positive_speed_raises(self) -> None:
        edge = _make_edge("e1", "n1", "n2")
        edge.speed_limit_mps = 0.0  # bypass post-init for defensive test
        with pytest.raises(InvalidRoutingRequestError, match="invalid speed_limit_mps"):
            calculate_edge_cost(edge, CostMode.TRAVEL_TIME)

    def test_calculate_route_metrics_sums_totals(self) -> None:
        edges = [
            _make_edge("e1", "n1", "n2", length_m=100.0, speed_limit_mps=10.0),  # 10s
            _make_edge("e2", "n2", "n3", length_m=200.0, speed_limit_mps=20.0),  # 10s
        ]
        dist, dur = calculate_route_metrics(edges)
        assert dist == pytest.approx(300.0)
        assert dur == pytest.approx(20.0)

    def test_is_edge_traversable_checks_closed_set(self) -> None:
        assert is_edge_traversable("e1", None) is True
        assert is_edge_traversable("e1", set()) is True
        assert is_edge_traversable("e1", {"e2", "e3"}) is True
        assert is_edge_traversable("e1", {"e1", "e2"}) is False


class TestRoutingHeuristics:
    """Tests for A* heuristic admissibility and distance/time calculations."""

    @pytest.fixture
    def triangle_graph(self) -> RoadGraph:
        """Right triangle: (0,0) -> (300,0) -> (300,400) -> (0,0)."""
        g = RoadGraph("triangle")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 300.0, 0.0))
        g.add_node(_make_node("C", 300.0, 400.0))

        # A -> B: 300m at 10 m/s
        g.add_edge(_make_edge("e_AB", "A", "B", length_m=300.0, speed_limit_mps=10.0))
        # B -> C: 400m at 20 m/s
        g.add_edge(_make_edge("e_BC", "B", "C", length_m=400.0, speed_limit_mps=20.0))
        # A -> C: 500m hypotenuse at 25 m/s
        g.add_edge(_make_edge("e_AC", "A", "C", length_m=500.0, speed_limit_mps=25.0))
        return g

    def test_admissibility_on_euclidean_graph(self, triangle_graph: RoadGraph) -> None:
        is_admissible, max_speed = check_heuristic_admissibility(triangle_graph)
        assert is_admissible is True
        assert max_speed == pytest.approx(25.0)

    def test_admissibility_fails_when_edge_shorter_than_euclidean(self) -> None:
        g = RoadGraph("inadmissible")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 100.0, 0.0))
        # Euclidean distance is 100m, but edge declared as 50m!
        g.add_edge(_make_edge("e1", "A", "B", length_m=50.0, speed_limit_mps=10.0))

        is_admissible, max_speed = check_heuristic_admissibility(g)
        assert is_admissible is False
        assert max_speed == pytest.approx(10.0)

    def test_distance_heuristic_values(self, triangle_graph: RoadGraph) -> None:
        h_func, admissible = get_heuristic_function(
            triangle_graph, destination_node_id="C", cost_mode=CostMode.DISTANCE
        )
        assert admissible is True
        # Dist(A, C) = 500m
        assert h_func("A") == pytest.approx(500.0)
        # Dist(B, C) = 400m
        assert h_func("B") == pytest.approx(400.0)
        # Dist(C, C) = 0m
        assert h_func("C") == pytest.approx(0.0)

    def test_travel_time_heuristic_values(self, triangle_graph: RoadGraph) -> None:
        h_func, admissible = get_heuristic_function(
            triangle_graph, destination_node_id="C", cost_mode=CostMode.TRAVEL_TIME
        )
        assert admissible is True
        # Max speed is 25.0 m/s
        # Dist(A, C) / 25 = 500 / 25 = 20.0 seconds
        assert h_func("A") == pytest.approx(20.0)
        # Dist(B, C) / 25 = 400 / 25 = 16.0 seconds
        assert h_func("B") == pytest.approx(16.0)
        assert h_func("C") == pytest.approx(0.0)

    def test_inadmissible_graph_falls_back_to_zero(self) -> None:
        g = RoadGraph("inadmissible")
        g.add_node(_make_node("A", 0.0, 0.0))
        g.add_node(_make_node("B", 100.0, 0.0))
        g.add_edge(_make_edge("e1", "A", "B", length_m=50.0, speed_limit_mps=10.0))

        h_func, admissible = get_heuristic_function(
            g, destination_node_id="B", cost_mode=CostMode.DISTANCE
        )
        assert admissible is False
        assert h_func("A") == 0.0
        assert h_func("B") == 0.0

    def test_force_zero_heuristic(self, triangle_graph: RoadGraph) -> None:
        h_func, admissible = get_heuristic_function(
            triangle_graph,
            destination_node_id="C",
            cost_mode=CostMode.DISTANCE,
            force_zero=True,
        )
        assert admissible is True
        assert h_func("A") == 0.0
        assert h_func("B") == 0.0


class TestRoutingModelsValidation:
    """Tests for RoutingRequest and RoutingResult parameter validation and serialization."""

    def test_routing_request_valid_string_coercion(self) -> None:
        from apps.core.routing.models import RoutingAlgorithm, RoutingRequest

        req = RoutingRequest(
            start_node_id="A",
            destination_node_id="B",
            cost_mode="distance",  # type: ignore
            algorithm="dijkstra",  # type: ignore
            closed_edge_ids=["e1", "e2"],  # type: ignore
        )
        assert req.cost_mode == CostMode.DISTANCE
        assert req.algorithm == RoutingAlgorithm.DIJKSTRA
        assert req.closed_edge_ids == {"e1", "e2"}

    def test_routing_request_invalid_fields(self) -> None:
        from apps.core.routing.models import RoutingRequest

        with pytest.raises(InvalidRoutingRequestError, match="start_node_id"):
            RoutingRequest(start_node_id="", destination_node_id="B")
        with pytest.raises(InvalidRoutingRequestError, match="destination_node_id"):
            RoutingRequest(start_node_id="A", destination_node_id="")
        with pytest.raises(InvalidRoutingRequestError, match="Invalid cost_mode"):
            RoutingRequest(start_node_id="A", destination_node_id="B", cost_mode="bad_mode")  # type: ignore
        with pytest.raises(InvalidRoutingRequestError, match="Invalid algorithm"):
            RoutingRequest(start_node_id="A", destination_node_id="B", algorithm="bad_algo")  # type: ignore
        with pytest.raises(InvalidRoutingRequestError, match="closed_edge_ids"):
            RoutingRequest(start_node_id="A", destination_node_id="B", closed_edge_ids=123)  # type: ignore

    def test_routing_result_validation(self) -> None:
        from apps.core.routing.models import RoutingAlgorithm, RoutingResult

        valid_kwargs = dict(
            success=True,
            algorithm=RoutingAlgorithm.ASTAR,
            cost_mode=CostMode.TRAVEL_TIME,
            start_node_id="A",
            destination_node_id="B",
            node_ids=["A", "B"],
            edge_ids=["e1"],
            total_distance_m=100.0,
            estimated_duration_s=10.0,
            objective_cost=10.0,
            nodes_expanded=2,
            edges_examined=1,
            execution_time_ms=1.5,
        )

        with pytest.raises(InvalidRoutingRequestError, match="total_distance_m"):
            RoutingResult(**{**valid_kwargs, "total_distance_m": -1.0})
        with pytest.raises(InvalidRoutingRequestError, match="estimated_duration_s"):
            RoutingResult(**{**valid_kwargs, "estimated_duration_s": -1.0})
        with pytest.raises(InvalidRoutingRequestError, match="objective_cost"):
            RoutingResult(**{**valid_kwargs, "objective_cost": -1.0})
        with pytest.raises(InvalidRoutingRequestError, match="nodes_expanded"):
            RoutingResult(**{**valid_kwargs, "nodes_expanded": -1})
        with pytest.raises(InvalidRoutingRequestError, match="edges_examined"):
            RoutingResult(**{**valid_kwargs, "edges_examined": -1})
        with pytest.raises(InvalidRoutingRequestError, match="execution_time_ms"):
            RoutingResult(**{**valid_kwargs, "execution_time_ms": -1.0})
