"""Unit and cross-algorithm tests for RoutePlanner and reference comparisons."""

import networkx as nx
import pytest

from apps.core.domain.models import Route
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.osm_normalizer import normalize_osm_graph
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing import (
    CostMode,
    InvalidRoutingRequestError,
    NoPathFoundError,
    RoutePlanner,
    RoutingAlgorithm,
    RoutingRequest,
    find_route,
)


def _make_osm_fixture() -> nx.MultiDiGraph:
    """Small offline NetworkX MultiDiGraph resembling OSMnx output for routing test."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"

    # 4 nodes in a small box near (13.0, 80.0)
    G.add_node(101, y=13.000, x=80.000)
    G.add_node(102, y=13.001, x=80.000)
    G.add_node(103, y=13.001, x=80.001)
    G.add_node(104, y=13.000, x=80.001)

    # Edge 101 -> 102 (one-way)
    G.add_edge(101, 102, 0, oneway=True, highway="primary", maxspeed="50", length=111.0)
    # Edge 102 -> 103 (two-way)
    G.add_edge(102, 103, 0, oneway=False, highway="secondary", maxspeed="40", length=108.0)
    # Edge 103 -> 104 (one-way)
    G.add_edge(103, 104, 0, oneway=True, highway="residential", maxspeed="30", length=111.0)
    # Edge 101 -> 104 (one-way direct)
    G.add_edge(101, 104, 0, oneway=True, highway="tertiary", maxspeed="30", length=108.0)

    return G


class TestRoutePlanner:
    """Tests for the unified RoutePlanner interface and edge-case behaviors."""

    @pytest.fixture
    def city_grid(self) -> RoadGraph:
        return generate_synthetic_city_grid(
            CityGridConfig(rows=4, cols=4, spacing_m=100.0, seed=10)
        )

    def test_planner_initialization_and_properties(self, city_grid: RoadGraph) -> None:
        planner = RoutePlanner(city_grid)
        assert planner.is_heuristic_admissible is True
        assert planner.max_speed_limit_mps > 0.0

    def test_planner_invalid_graph_type_raises(self) -> None:
        with pytest.raises(InvalidRoutingRequestError, match="Expected RoadGraph"):
            RoutePlanner("not_a_graph")  # type: ignore

    def test_find_route_convenience_function(self, city_grid: RoadGraph) -> None:
        nodes = city_grid.node_ids()
        res = find_route(
            city_grid,
            nodes[0],
            nodes[-1],
            algorithm="astar",
            cost_mode="travel_time",
        )
        assert res.success is True
        assert res.algorithm == RoutingAlgorithm.ASTAR
        assert res.cost_mode == CostMode.TRAVEL_TIME
        assert len(res.node_ids) >= 2
        assert len(res.edge_ids) == len(res.node_ids) - 1
        assert isinstance(res.route, Route)

    def test_routing_request_and_result_serialization(self, city_grid: RoadGraph) -> None:
        nodes = city_grid.node_ids()
        req = RoutingRequest(
            start_node_id=nodes[0],
            destination_node_id=nodes[1],
            cost_mode=CostMode.DISTANCE,
            algorithm=RoutingAlgorithm.DIJKSTRA,
            closed_edge_ids={"edge_closed_test"},
        )
        planner = RoutePlanner(city_grid)
        result = planner.find_route_from_request(req)

        data = result.to_dict()
        assert data["success"] is True
        assert data["algorithm"] == "dijkstra"
        assert data["cost_mode"] == "distance"
        assert data["start_node_id"] == nodes[0]
        assert data["destination_node_id"] == nodes[1]
        assert "route" in data
        assert data["route"]["id"] == f"route_{nodes[0]}_{nodes[1]}"

    def test_graph_immutability_during_routing(self, city_grid: RoadGraph) -> None:
        initial_node_count = city_grid.node_count
        initial_edge_count = city_grid.edge_count
        nodes = city_grid.node_ids()

        # Run multiple planning passes with closures
        find_route(city_grid, nodes[0], nodes[-1], algorithm="dijkstra")
        find_route(
            city_grid,
            nodes[0],
            nodes[-1],
            algorithm="astar",
            closed_edge_ids={city_grid.edge_ids()[0]},
        )

        assert city_grid.node_count == initial_node_count
        assert city_grid.edge_count == initial_edge_count

    def test_route_topological_integrity(self, city_grid: RoadGraph) -> None:
        nodes = city_grid.node_ids()
        res = find_route(city_grid, nodes[0], nodes[-1], algorithm="astar")

        # Verify edge continuity
        for i in range(len(res.edge_ids)):
            u = res.node_ids[i]
            v = res.node_ids[i + 1]
            edge_id = res.edge_ids[i]

            edge = city_grid.get_edge(edge_id)
            assert edge.start_node_id == u
            assert edge.end_node_id == v

        # Verify aggregate distance matches sum of parts
        edge_objs = [city_grid.get_edge(eid) for eid in res.edge_ids]
        expected_distance = sum(e.length_m for e in edge_objs)
        expected_duration = sum(e.length_m / e.speed_limit_mps for e in edge_objs)

        assert res.total_distance_m == pytest.approx(expected_distance)
        assert res.estimated_duration_s == pytest.approx(expected_duration)

    def test_cross_algorithm_reference_against_networkx(self, city_grid: RoadGraph) -> None:
        """Compare custom Dijkstra and A* against NetworkX ground-truth shortest path length."""
        nx_graph = city_grid.networkx_graph

        # Add travel_time attribute to nx_graph for independent reference computation
        for u, v, data in nx_graph.edges(data=True):
            data["travel_time"] = data["length_m"] / data["speed_limit_mps"]

        nodes = city_grid.node_ids()
        test_pairs = [
            (nodes[0], nodes[15]),
            (nodes[1], nodes[14]),
            (nodes[3], nodes[12]),
            (nodes[4], nodes[11]),
        ]

        for start, dest in test_pairs:
            # 1. Distance Mode Comparison
            nx_dist = nx.shortest_path_length(nx_graph, start, dest, weight="length_m")
            res_dijkstra_dist = find_route(
                city_grid, start, dest, algorithm="dijkstra", cost_mode="distance"
            )
            res_astar_dist = find_route(
                city_grid, start, dest, algorithm="astar", cost_mode="distance"
            )

            assert res_dijkstra_dist.objective_cost == pytest.approx(nx_dist, abs=1e-5)
            assert res_astar_dist.objective_cost == pytest.approx(nx_dist, abs=1e-5)

            # 2. Travel Time Mode Comparison
            nx_time = nx.shortest_path_length(nx_graph, start, dest, weight="travel_time")
            res_dijkstra_time = find_route(
                city_grid, start, dest, algorithm="dijkstra", cost_mode="travel_time"
            )
            res_astar_time = find_route(
                city_grid, start, dest, algorithm="astar", cost_mode="travel_time"
            )

            assert res_dijkstra_time.objective_cost == pytest.approx(nx_time, abs=1e-5)
            assert res_astar_time.objective_cost == pytest.approx(nx_time, abs=1e-5)

    def test_routing_on_osm_normalized_graph(self) -> None:
        """Verify routing on a real-world style OSM normalized road network."""
        from apps.core.graph.osm_models import BoundingBox

        osm_nx = _make_osm_fixture()
        bbox = BoundingBox(north=13.002, south=12.999, east=80.002, west=79.999)
        road_graph, skipped = normalize_osm_graph(osm_nx, bounds=bbox)
        assert road_graph.node_count == 4
        assert road_graph.edge_count >= 4

        # Route from osm_node_101 to osm_node_103
        res = find_route(
            road_graph,
            "osm_node_101",
            "osm_node_103",
            algorithm="astar",
            cost_mode="distance",
        )
        assert res.success is True
        assert res.node_ids == ["osm_node_101", "osm_node_102", "osm_node_103"]
        assert len(res.edge_ids) == 2
        assert res.total_distance_m > 0.0
        assert res.estimated_duration_s > 0.0

        # Reverse two-way leg: 103 -> 102 was generated because edge 102 <-> 103 was two-way
        res_rev = find_route(
            road_graph,
            "osm_node_103",
            "osm_node_102",
            algorithm="dijkstra",
            cost_mode="travel_time",
        )
        assert res_rev.success is True
        assert res_rev.node_ids == ["osm_node_103", "osm_node_102"]

        # One-way restriction check: 102 -> 101 has no reverse edge!
        with pytest.raises(NoPathFoundError):
            find_route(road_graph, "osm_node_102", "osm_node_101")
