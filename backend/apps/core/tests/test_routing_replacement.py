"""Unit tests for safe active route replacement, continuity, and invariant preservation."""

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.exceptions import RouteReplacementError


@pytest.fixture
def multi_path_graph() -> RoadGraph:
    """Road graph supporting multiple branching paths.

    n0 -> n1 -> n2 -> n4
          |     ^
          v     |
          n3 ---+
    """
    g = RoadGraph(name="multi_path")
    g.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
    g.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=0.0)))
    g.add_node(RoadNode(id="n2", position=Position2D(x=200.0, y=0.0)))
    g.add_node(RoadNode(id="n3", position=Position2D(x=100.0, y=100.0)))
    g.add_node(RoadNode(id="n4", position=Position2D(x=300.0, y=0.0)))

    g.add_edge(
        RoadEdge(
            id="e01", start_node_id="n0", end_node_id="n1", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e12", start_node_id="n1", end_node_id="n2", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e13", start_node_id="n1", end_node_id="n3", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e32", start_node_id="n3", end_node_id="n2", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e24", start_node_id="n2", end_node_id="n4", length_m=100.0, speed_limit_mps=10.0
        )
    )
    return g


@pytest.fixture
def active_agent(multi_path_graph: RoadGraph) -> VehicleAgent:
    """Agent traveling n0 -> n1 -> n2 -> n4."""
    initial_route = Route(
        id="orig_route",
        node_ids=["n0", "n1", "n2", "n4"],
        edge_ids=["e01", "e12", "e24"],
        total_distance_m=300.0,
        estimated_duration_s=30.0,
    )
    v = Vehicle(
        id="veh_01",
        position=Position2D(x=0.0, y=0.0),
        speed_mps=5.0,
        heading_rad=0.0,
        target_node_id="n4",
    )
    agent = VehicleAgent(vehicle=v, road_graph=multi_path_graph, route=initial_route)
    agent.start()
    return agent


class TestRouteReplacement:
    """Test suite for VehicleAgent.replace_remaining_route."""

    def test_safe_replacement_preserves_position_speed_and_heading(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Replacing untraversed suffix preserves current kinematic position, speed, and heading."""
        # Vehicle is on e01 (n0 -> n1), halfway across
        active_agent.current_edge_index = 0
        active_agent.distance_along_segment_m = 50.0
        active_agent.vehicle.position = Position2D(x=50.0, y=0.0)
        active_agent.vehicle.speed_mps = 7.5
        active_agent.vehicle.heading_rad = 0.123

        initial_pos = active_agent.vehicle.position
        initial_speed = active_agent.vehicle.speed_mps
        initial_heading = active_agent.vehicle.heading_rad

        # Candidate route starts at end of current edge (n1) and detours via n3 -> n2 -> n4
        candidate = Route(
            id="detour_route",
            node_ids=["n1", "n3", "n2", "n4"],
            edge_ids=["e13", "e32", "e24"],
            total_distance_m=300.0,
            estimated_duration_s=30.0,
        )

        new_route = active_agent.replace_remaining_route(
            candidate_route=candidate,
            resume_node_id="n1",
            new_route_id="detour_route",
        )

        assert new_route.id == "detour_route"
        assert active_agent.vehicle.position == initial_pos
        assert active_agent.vehicle.speed_mps == initial_speed
        assert active_agent.vehicle.heading_rad == initial_heading
        assert active_agent.current_edge_index == 0
        assert active_agent.distance_along_segment_m == 50.0

        # Segment chain: [e01, e13, e32, e24]
        assert [s.edge_id for s in active_agent._segments] == ["e01", "e13", "e32", "e24"]
        assert active_agent.total_route_distance_m == 400.0

    def test_replacement_rejects_mismatched_resume_node(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Candidate starting node must match current edge endpoint under finish_edge policy."""
        active_agent.current_edge_index = 0  # current edge ends at n1

        candidate = Route(
            id="bad_resume",
            node_ids=["n2", "n4"],
            edge_ids=["e24"],
            total_distance_m=100.0,
        )

        with pytest.raises(RouteReplacementError) as exc_info:
            active_agent.replace_remaining_route(candidate, resume_node_id="n2")
        assert "does not match current edge endpoint" in str(exc_info.value)

    def test_replacement_rejects_altered_destination(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Candidate route terminating at a different node is rejected."""
        active_agent.current_edge_index = 0

        # Vehicle destination is n4, but candidate ends at n2
        candidate = Route(
            id="wrong_dest",
            node_ids=["n1", "n2"],
            edge_ids=["e12"],
            total_distance_m=100.0,
        )

        with pytest.raises(RouteReplacementError) as exc_info:
            active_agent.replace_remaining_route(candidate, resume_node_id="n1")
        assert "does not match vehicle target" in str(exc_info.value)

    def test_replacement_rejects_disconnected_candidate_edge(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Candidate specifying edge not connecting successive nodes is rejected."""
        active_agent.current_edge_index = 0

        # Invalid hop: n1 -> n2 using e24 (which connects n2 -> n4)
        candidate = Route(
            id="invalid_conn",
            node_ids=["n1", "n2", "n4"],
            edge_ids=["e24", "e24"],
            total_distance_m=200.0,
        )

        with pytest.raises(RouteReplacementError) as exc_info:
            active_agent.replace_remaining_route(candidate, resume_node_id="n1")
        assert "does not connect" in str(exc_info.value)

    def test_replacement_rejects_arrived_vehicle(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Vehicles in ARRIVED state cannot have their routes replaced."""
        active_agent.vehicle.state = VehicleState.ARRIVED

        candidate = Route(
            id="post_arrival",
            node_ids=["n1", "n4"],
            edge_ids=[],
            total_distance_m=100.0,
        )

        with pytest.raises(RouteReplacementError) as exc_info:
            active_agent.replace_remaining_route(candidate, resume_node_id="n1")
        assert "arrived" in str(exc_info.value).lower()

    def test_replacement_at_origin_before_motion_starts(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """When vehicle is at origin with 0 progress, entire route can be replaced from origin."""
        active_agent.current_edge_index = 0
        active_agent.distance_along_segment_m = 0.0

        # Candidate replaces from n0 via a hypothetical path (n0 -> n1 -> n3 -> n2 -> n4)
        new_full_route = Route(
            id="full_detour",
            node_ids=["n0", "n1", "n3", "n2", "n4"],
            edge_ids=["e01", "e13", "e32", "e24"],
            total_distance_m=400.0,
        )

        res = active_agent.replace_remaining_route(new_full_route, resume_node_id="n0")
        assert res.id == "full_detour"
        assert [s.edge_id for s in active_agent._segments] == ["e01", "e13", "e32", "e24"]
        assert active_agent.current_edge_index == 0
        assert active_agent.distance_along_segment_m == 0.0

    def test_replacement_preserves_multiple_completed_segments(
        self, multi_path_graph: RoadGraph, active_agent: VehicleAgent
    ) -> None:
        """Segments already completed in route history remain in _segments."""
        # Advance vehicle to edge index 1 (e12: n1 -> n2)
        active_agent.current_edge_index = 1
        active_agent.distance_along_segment_m = 30.0

        candidate = Route(
            id="suffix_n2_n4",
            node_ids=["n2", "n4"],
            edge_ids=["e24"],
            total_distance_m=100.0,
        )

        active_agent.replace_remaining_route(candidate, resume_node_id="n2")

        # e01 (completed) and e12 (active) are retained; e24 is appended
        assert [s.edge_id for s in active_agent._segments] == ["e01", "e12", "e24"]
        assert active_agent.current_edge_index == 1
        assert active_agent.distance_along_segment_m == 30.0
