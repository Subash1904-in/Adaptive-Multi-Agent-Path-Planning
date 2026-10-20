"""Unit tests for VehicleAgent lifecycle, route tracking, and deterministic stepping."""

import math

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.exceptions import (
    InvalidLifecycleTransitionError,
    InvalidRouteError,
)
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import VehicleAgent


@pytest.fixture
def sample_road_graph() -> RoadGraph:
    """Create a 4-node linear/branching road network for route testing.

    Topology:
        n1 (0, 0) --[e1: 100m, 10 m/s]--> n2 (100, 0)
        n2 (100, 0) --[e2: 100m, 15 m/s]--> n3 (200, 0)
        n3 (200, 0) --[e3: 100m, 20 m/s]--> n4 (300, 0)
    """
    rg = RoadGraph(name="test_kinematics_network")
    n1 = RoadNode(id="n1", position=Position2D(x=0.0, y=0.0))
    n2 = RoadNode(id="n2", position=Position2D(x=100.0, y=0.0))
    n3 = RoadNode(id="n3", position=Position2D(x=200.0, y=0.0))
    n4 = RoadNode(id="n4", position=Position2D(x=300.0, y=0.0))
    for n in [n1, n2, n3, n4]:
        rg.add_node(n)

    e1 = RoadEdge(
        id="e1", start_node_id="n1", end_node_id="n2", length_m=100.0, speed_limit_mps=10.0
    )
    e2 = RoadEdge(
        id="e2", start_node_id="n2", end_node_id="n3", length_m=100.0, speed_limit_mps=15.0
    )
    e3 = RoadEdge(
        id="e3", start_node_id="n3", end_node_id="n4", length_m=100.0, speed_limit_mps=20.0
    )
    for e in [e1, e2, e3]:
        rg.add_edge(e)

    return rg


@pytest.fixture
def sample_vehicle() -> Vehicle:
    """Create a vehicle initially at origin in IDLE state."""
    return Vehicle(
        id="veh_001",
        position=Position2D(x=0.0, y=0.0),
        speed_mps=0.0,
        max_speed_mps=25.0,
        state=VehicleState.IDLE,
    )


class TestVehicleAgentInitializationAndRouteValidation:
    """Test initialization, type requirements, and route validation rules."""

    def test_invalid_constructor_types_raise(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        with pytest.raises(TypeError, match="Expected Vehicle instance"):
            VehicleAgent(vehicle="not_a_vehicle", road_graph=sample_road_graph)  # type: ignore

        with pytest.raises(TypeError, match="Expected RoadGraph instance"):
            VehicleAgent(vehicle=sample_vehicle, road_graph="not_a_graph")  # type: ignore

    def test_assign_valid_route_with_edge_ids(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2", "n3"], edge_ids=["e1", "e2"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route)

        assert agent.route is route
        assert agent.total_route_distance_m == 200.0
        assert agent.remaining_route_distance_m == 200.0
        assert agent.current_edge_index == 0
        assert agent.vehicle.route_id == "r1"
        assert agent.vehicle.target_node_id == "n3"
        assert agent.vehicle.current_node_id == "n1"
        assert agent.vehicle.current_edge_id == "e1"

    def test_assign_valid_route_resolving_edges_automatically(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r2", node_ids=["n2", "n3", "n4"], edge_ids=[])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route)
        assert len(agent._segments) == 2
        assert agent._segments[0].edge_id == "e2"
        assert agent._segments[1].edge_id == "e3"
        assert agent.total_route_distance_m == 200.0

    def test_assign_route_with_missing_node_raises(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r_bad_node", node_ids=["n1", "nonexistent_node"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph)
        with pytest.raises(InvalidRouteError, match="does not exist in the road graph"):
            agent.assign_route(route)

    def test_assign_route_with_missing_directed_edge_raises(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        # Reverse edge n2 -> n1 does not exist in directed graph
        route = Route(id="r_reverse", node_ids=["n2", "n1"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph)
        with pytest.raises(InvalidRouteError, match="No directed edge connects"):
            agent.assign_route(route)

    def test_assign_route_with_mismatched_edge_endpoints_raises(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        # e2 connects n2 -> n3, but route specifies n1 -> n2
        route = Route(id="r_mismatch", node_ids=["n1", "n2"], edge_ids=["e2"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph)
        with pytest.raises(
            InvalidRouteError, match="connects 'n2' -> 'n3', but route specifies 'n1' -> 'n2'"
        ):
            agent.assign_route(route)

    def test_assign_non_route_raises(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph)
        with pytest.raises(InvalidRouteError, match="Expected Route instance"):
            agent.assign_route("not_a_route")  # type: ignore


class TestVehicleAgentLifecycleTransitions:
    """Test state machine transitions across IDLE, EN_ROUTE, BLOCKED, and ARRIVED."""

    def test_idle_vehicle_remains_stationary_on_step(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route)
        assert agent.is_idle

        res = agent.step(dt=1.0)
        assert res.distance_traveled_m == 0.0
        assert res.new_position == Position2D(x=0.0, y=0.0)
        assert agent.is_idle

    def test_start_without_route_raises(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph)
        with pytest.raises(InvalidLifecycleTransitionError, match="without a valid assigned route"):
            agent.start()

    def test_start_transitions_to_en_route(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route)
        agent.start()
        assert agent.is_en_route
        assert agent.vehicle.state == VehicleState.EN_ROUTE

    def test_pause_and_resume_preserves_position_and_progress(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        config = KinematicsConfig(max_speed_mps=10.0, max_acceleration_mps2=5.0)
        agent = VehicleAgent(
            vehicle=sample_vehicle,
            road_graph=sample_road_graph,
            route=route,
            config=config,
        )
        agent.start()

        # Step 1: Advance 2.5 m (v0=0, a=5, dt=1 => v=5, d=2.5)
        _ = agent.step(dt=1.0)
        pos_before_pause = agent.vehicle.position
        dist_before_pause = agent.distance_along_segment_m
        assert math.isclose(dist_before_pause, 2.5)

        # Pause / Block
        agent.pause()
        assert agent.is_blocked
        assert agent.vehicle.speed_mps == 0.0
        assert agent.vehicle.position == pos_before_pause

        # Step while blocked => no movement
        res_blocked = agent.step(dt=2.0)
        assert res_blocked.distance_traveled_m == 0.0
        assert res_blocked.new_speed_mps == 0.0
        assert agent.vehicle.position == pos_before_pause
        assert agent.distance_along_segment_m == dist_before_pause

        # Resume => back to EN_ROUTE
        agent.resume()
        assert agent.is_en_route
        assert agent.vehicle.state == VehicleState.EN_ROUTE

        # Step again => accelerates from 0.0 at the preserved 2.5m mark
        res2 = agent.step(dt=1.0)
        assert res2.distance_traveled_m > 0.0
        assert agent.distance_along_segment_m == dist_before_pause + res2.distance_traveled_m

    def test_invalid_lifecycle_transitions_raise(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route)

        # Cannot pause while IDLE
        with pytest.raises(InvalidLifecycleTransitionError, match="must be en_route"):
            agent.pause()

        # Cannot resume while IDLE
        with pytest.raises(InvalidLifecycleTransitionError, match="must be blocked"):
            agent.resume()

        # Start => now EN_ROUTE
        agent.start()

        # Cannot start again while EN_ROUTE is allowed or tested? Let's check start() when blocked
        agent.block()
        with pytest.raises(
            InvalidLifecycleTransitionError, match="Call resume\\(\\) instead of start\\(\\)"
        ):
            agent.start()


class TestRouteFollowingAndOvershootPrevention:
    """Test longitudinal advancement, segment transitions, multi-segment crossing, and arrival."""

    def test_single_segment_progression_to_arrival(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        config = KinematicsConfig(max_speed_mps=10.0, max_acceleration_mps2=5.0)
        agent = VehicleAgent(
            vehicle=sample_vehicle,
            road_graph=sample_road_graph,
            route=route,
            config=config,
        )
        agent.start()

        # Advance along the 100m segment until arrival
        step_count = 0
        while not agent.is_arrived and step_count < 20:
            agent.step(dt=1.0)
            step_count += 1

        assert agent.is_arrived
        assert agent.vehicle.state == VehicleState.ARRIVED
        assert agent.vehicle.speed_mps == 0.0
        assert math.isclose(agent.vehicle.position.x, 100.0)
        assert math.isclose(agent.vehicle.position.y, 0.0)
        assert agent.remaining_route_distance_m == 0.0

        # Further stepping after arrival produces 0 movement
        res_post = agent.step(dt=1.0)
        assert res_post.distance_traveled_m == 0.0
        assert res_post.arrived is True
        assert agent.vehicle.position.x == 100.0

    def test_multi_segment_crossing_in_single_timestep(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        # Route across 3 segments: n1 -> n2 (100m) -> n3 (100m) -> n4 (100m), total 300m
        route = Route(id="r_long", node_ids=["n1", "n2", "n3", "n4"], edge_ids=["e1", "e2", "e3"])
        config = KinematicsConfig(
            max_speed_mps=100.0,
            max_acceleration_mps2=100.0,
            enforce_road_speed_limits=False,
        )
        sample_vehicle.speed_mps = 50.0  # High initial speed
        agent = VehicleAgent(
            vehicle=sample_vehicle,
            road_graph=sample_road_graph,
            route=route,
            config=config,
        )
        agent.start()

        # Move 150m in a single time step (dt = 3.0 s at constant 50 m/s => 150 m)
        # Should fully cross e1 (100m) and end up 50m along e2!
        res = agent.step(dt=3.0, target_accel=0.0)
        assert math.isclose(res.distance_traveled_m, 150.0)
        assert agent.current_edge_index == 1
        assert math.isclose(agent.distance_along_segment_m, 50.0)
        assert math.isclose(agent.vehicle.position.x, 150.0)
        assert math.isclose(agent.vehicle.position.y, 0.0)
        assert math.isclose(agent.remaining_route_distance_m, 150.0)
        assert agent.vehicle.current_edge_id == "e2"

    def test_large_step_overshoot_clamps_at_destination(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        # Total distance is 100m (n1 -> n2)
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        config = KinematicsConfig(max_speed_mps=50.0, max_acceleration_mps2=10.0)
        sample_vehicle.speed_mps = 50.0
        agent = VehicleAgent(
            vehicle=sample_vehicle,
            road_graph=sample_road_graph,
            route=route,
            config=config,
        )
        agent.start()

        # Step of dt = 10.0 s would travel 500m, but route is only 100m
        res = agent.step(dt=10.0, target_accel=0.0)
        assert math.isclose(res.distance_traveled_m, 100.0)
        assert res.arrived is True
        assert agent.is_arrived
        assert math.isclose(agent.vehicle.position.x, 100.0)
        assert agent.vehicle.speed_mps == 0.0
        assert agent.remaining_route_distance_m == 0.0

    def test_reset_and_route_reassignment(
        self, sample_vehicle: Vehicle, sample_road_graph: RoadGraph
    ) -> None:
        route1 = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        route2 = Route(id="r2", node_ids=["n2", "n3"], edge_ids=["e2"])
        agent = VehicleAgent(vehicle=sample_vehicle, road_graph=sample_road_graph, route=route1)
        agent.start()

        # Complete route 1
        agent.step(dt=100.0)
        assert agent.is_arrived

        # Reassign route 2 via reset
        agent.reset(route=route2)
        assert agent.is_idle
        assert agent.vehicle.state == VehicleState.IDLE
        assert agent.vehicle.position == Position2D(x=100.0, y=0.0)
        assert agent.remaining_route_distance_m == 100.0

        # Can start route 2
        agent.start()
        assert agent.is_en_route
        agent.step(dt=100.0)
        assert agent.is_arrived
        assert math.isclose(agent.vehicle.position.x, 200.0)
