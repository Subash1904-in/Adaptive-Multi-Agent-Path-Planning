"""Integration tests for VehicleAgent with synthetic city grids and OSM-normalized graphs."""

import math

import networkx as nx
import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import Vehicle
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.osm_models import BoundingBox
from apps.core.graph.osm_normalizer import normalize_osm_graph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.models import CostMode, RoutingAlgorithm
from apps.core.routing.planner import find_route


class TestKinematicsSyntheticCityIntegration:
    """Test integration: synthetic grid generation -> routing -> kinematics."""

    @pytest.fixture
    def grid_graph(self):
        config = CityGridConfig(rows=4, cols=4, spacing_m=100.0, speed_limit_mps=15.0, seed=42)
        return generate_synthetic_city_grid(config)

    def test_vehicle_follows_astar_route_across_grid(self, grid_graph) -> None:
        start_id = "node_r0_c0"
        dest_id = "node_r3_c3"

        # Plan optimal route using Phase 6 A*
        route_result = find_route(
            road_graph=grid_graph,
            start_node_id=start_id,
            destination_node_id=dest_id,
            algorithm=RoutingAlgorithm.ASTAR,
            cost_mode=CostMode.DISTANCE,
        )
        assert route_result.route is not None
        route = route_result.route

        vehicle = Vehicle(
            id="veh_grid_1",
            position=grid_graph.get_node(start_id).position,
            speed_mps=0.0,
            max_speed_mps=20.0,
            state=VehicleState.IDLE,
        )

        agent = VehicleAgent(
            vehicle=vehicle,
            road_graph=grid_graph,
            route=route,
            config=KinematicsConfig(max_speed_mps=15.0, max_acceleration_mps2=3.0),
        )

        agent.start()
        assert agent.is_en_route

        # Step until destination is reached
        steps = 0
        total_dist_traveled = 0.0
        while not agent.is_arrived and steps < 100:
            res = agent.step(dt=1.0)
            total_dist_traveled += res.distance_traveled_m
            steps += 1

        assert agent.is_arrived
        dest_pos = grid_graph.get_node(dest_id).position
        assert math.isclose(agent.vehicle.position.x, dest_pos.x, abs_tol=1e-3)
        assert math.isclose(agent.vehicle.position.y, dest_pos.y, abs_tol=1e-3)
        assert math.isclose(total_dist_traveled, route_result.total_distance_m, abs_tol=1e-3)

    def test_kinematics_stepping_is_strictly_deterministic(self, grid_graph) -> None:
        """Run identical simulations twice and assert identical positions at every step."""
        route_res = find_route(
            road_graph=grid_graph,
            start_node_id="node_r0_c0",
            destination_node_id="node_r2_c2",
            algorithm=RoutingAlgorithm.DIJKSTRA,
            cost_mode=CostMode.TRAVEL_TIME,
        )
        route = route_res.route
        assert route is not None

        def run_simulation():
            v = Vehicle(
                id="veh_det",
                position=grid_graph.get_node("node_r0_c0").position,
                speed_mps=0.0,
                max_speed_mps=15.0,
            )
            a = VehicleAgent(
                vehicle=v,
                road_graph=grid_graph,
                route=route,
                config=KinematicsConfig(max_speed_mps=15.0, max_acceleration_mps2=2.5),
            )
            a.start()
            trajectory = []
            for _ in range(25):
                res = a.step(dt=0.5)
                trajectory.append(
                    (
                        res.new_position.x,
                        res.new_position.y,
                        res.new_speed_mps,
                        res.distance_traveled_m,
                    )
                )
            return trajectory

        traj1 = run_simulation()
        traj2 = run_simulation()
        assert traj1 == traj2


class TestKinematicsOSMNormalizedGraphIntegration:
    """Test vehicle movement over an offline OSM-normalized road graph."""

    @pytest.fixture
    def osm_road_graph(self):
        """Construct a minimal offline OSMnx-like MultiDiGraph and normalize it."""
        raw = nx.MultiDiGraph(crs="EPSG:4326")
        # 3 nodes: A (0,0), B (0.001, 0), C (0.002, 0) in lon/lat
        raw.add_node(101, x=-122.400, y=37.780)
        raw.add_node(102, x=-122.399, y=37.780)
        raw.add_node(103, x=-122.398, y=37.780)

        raw.add_edge(
            101, 102, 0, osmid=1001, highway="residential", oneway=True, length=88.5, maxspeed="30"
        )
        raw.add_edge(
            102, 103, 0, osmid=1002, highway="residential", oneway=True, length=88.5, maxspeed="30"
        )

        bounds = BoundingBox(
            north=37.79,
            south=37.77,
            east=-122.39,
            west=-122.41,
        )
        road_graph, _ = normalize_osm_graph(raw, bounds=bounds)
        return road_graph

    def test_vehicle_traverses_osm_normalized_streets(self, osm_road_graph) -> None:
        start_node = "osm_node_101"
        end_node = "osm_node_103"

        route_res = find_route(
            road_graph=osm_road_graph,
            start_node_id=start_node,
            destination_node_id=end_node,
            algorithm=RoutingAlgorithm.ASTAR,
            cost_mode=CostMode.DISTANCE,
        )
        assert route_res.route is not None

        vehicle = Vehicle(
            id="veh_osm",
            position=osm_road_graph.get_node(start_node).position,
            speed_mps=0.0,
            max_speed_mps=15.0,
        )

        agent = VehicleAgent(
            vehicle=vehicle,
            road_graph=osm_road_graph,
            route=route_res.route,
            config=KinematicsConfig(max_speed_mps=12.0, max_acceleration_mps2=3.0),
        )

        agent.start()
        while not agent.is_arrived:
            agent.step(dt=1.0)

        assert agent.is_arrived
        dest_pos = osm_road_graph.get_node(end_node).position
        assert math.isclose(agent.vehicle.position.x, dest_pos.x, abs_tol=1e-3)
        assert math.isclose(agent.vehicle.position.y, dest_pos.y, abs_tol=1e-3)
