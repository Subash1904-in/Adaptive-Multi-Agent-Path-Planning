"""Unit tests for AMAPP domain entities and validation rules."""

import math

import pytest

from apps.core.domain.enums import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    ObstacleType,
    PedestrianState,
    TrafficSignalState,
    V2VMessageType,
    VehicleState,
    VehicleType,
)
from apps.core.domain.exceptions import DomainValidationError
from apps.core.domain.models import (
    Incident,
    Obstacle,
    Pedestrian,
    RoadEdge,
    RoadNode,
    Route,
    SimulationConfig,
    TrafficSignal,
    V2VMessage,
    Vehicle,
)
from apps.core.domain.values import Dimensions2D, GeoCoordinate, Position2D


class TestRoadNode:
    """Validation tests for RoadNode."""

    def test_valid_node(self) -> None:
        node = RoadNode(
            id="node_100",
            position=Position2D(100.0, 200.0),
            geo_coordinate=GeoCoordinate(37.77, -122.41),
            attributes={"osm_id": 12345},
        )
        assert node.id == "node_100"
        assert node.position.x == 100.0
        assert node.geo_coordinate is not None
        assert node.attributes["osm_id"] == 12345

    def test_default_attributes_is_empty_dict(self) -> None:
        node = RoadNode(id="node_1", position=Position2D(0.0, 0.0))
        assert node.attributes == {}
        assert node.geo_coordinate is None

    @pytest.mark.parametrize("invalid_id", ["", "   ", None, 123])
    def test_invalid_node_id_raises(self, invalid_id: object) -> None:
        with pytest.raises(DomainValidationError):
            RoadNode(id=invalid_id, position=Position2D(0.0, 0.0))  # type: ignore[arg-type]

    def test_invalid_position_type_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            RoadNode(id="node_1", position=(0.0, 0.0))  # type: ignore[arg-type]

    def test_invalid_geo_coordinate_type_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            RoadNode(
                id="node_1",
                position=Position2D(0.0, 0.0),
                geo_coordinate="37.77, -122.41",  # type: ignore[arg-type]
            )


class TestRoadEdge:
    """Validation tests for RoadEdge."""

    def test_valid_edge(self) -> None:
        edge = RoadEdge(
            id="edge_1_2",
            start_node_id="node_1",
            end_node_id="node_2",
            length_m=150.0,
            speed_limit_mps=13.89,
            lanes=2,
            name="Main St",
        )
        assert edge.id == "edge_1_2"
        assert edge.length_m == 150.0
        assert edge.lanes == 2
        assert edge.name == "Main St"

    def test_self_loop_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            RoadEdge(
                id="edge_loop",
                start_node_id="node_1",
                end_node_id="node_1",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        assert "cannot connect a node to itself" in str(exc_info.value)

    @pytest.mark.parametrize("length, speed", [
        (0.0, 10.0),
        (-10.0, 10.0),
        (50.0, 0.0),
        (50.0, -5.0),
    ])
    def test_non_positive_length_or_speed_rejected(self, length: float, speed: float) -> None:
        with pytest.raises(DomainValidationError):
            RoadEdge(
                id="edge_bad",
                start_node_id="node_1",
                end_node_id="node_2",
                length_m=length,
                speed_limit_mps=speed,
            )

    @pytest.mark.parametrize("lanes", [0, -1, 1.5, "2"])
    def test_invalid_lanes_rejected(self, lanes: object) -> None:
        with pytest.raises(DomainValidationError):
            RoadEdge(
                id="edge_bad_lanes",
                start_node_id="node_1",
                end_node_id="node_2",
                length_m=100.0,
                speed_limit_mps=10.0,
                lanes=lanes,  # type: ignore[arg-type]
            )


class TestRoute:
    """Validation tests for Route."""

    def test_valid_route(self) -> None:
        route = Route(
            id="route_alpha",
            node_ids=["node_1", "node_2", "node_3"],
            edge_ids=["edge_1_2", "edge_2_3"],
            total_distance_m=350.0,
            estimated_duration_s=25.2,
        )
        assert route.id == "route_alpha"
        assert len(route.node_ids) == 3
        assert route.total_distance_m == 350.0
        assert route.estimated_duration_s == 25.2

    @pytest.mark.parametrize("bad_nodes", [
        [],
        ["node_1"],
    ])
    def test_route_fewer_than_two_nodes_rejected(self, bad_nodes: list[str]) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            Route(id="route_bad", node_ids=bad_nodes)
        assert "at least 2 nodes" in str(exc_info.value)

    def test_empty_node_in_list_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Route(id="route_bad", node_ids=["node_1", ""])

    @pytest.mark.parametrize("dist, dur", [
        (-1.0, 10.0),
        (100.0, -5.0),
    ])
    def test_negative_distance_or_duration_rejected(self, dist: float, dur: float) -> None:
        with pytest.raises(DomainValidationError):
            Route(
                id="route_bad_metrics",
                node_ids=["node_1", "node_2"],
                total_distance_m=dist,
                estimated_duration_s=dur,
            )


class TestVehicle:
    """Validation tests for Vehicle."""

    def test_valid_vehicle_defaults(self) -> None:
        veh = Vehicle(
            id="veh_01",
            position=Position2D(10.0, 20.0),
        )
        assert veh.id == "veh_01"
        assert veh.position == Position2D(10.0, 20.0)
        assert veh.speed_mps == 0.0
        assert veh.max_speed_mps == 13.89
        assert veh.heading_rad == 0.0
        assert veh.state == VehicleState.IDLE
        assert veh.vehicle_type == VehicleType.STANDARD
        assert veh.dimensions == Dimensions2D(4.5, 2.0)
        assert veh.current_node_id is None

    def test_vehicle_heading_normalization(self) -> None:
        veh = Vehicle(
            id="veh_heading",
            position=Position2D(0.0, 0.0),
            heading_rad=3.0 * math.pi,  # > 2pi
        )
        assert math.isclose(veh.heading_rad, math.pi)

    def test_speed_exceeding_max_speed_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            Vehicle(
                id="veh_speed",
                position=Position2D(0.0, 0.0),
                speed_mps=20.0,
                max_speed_mps=15.0,
            )
        assert "cannot exceed max speed" in str(exc_info.value)

    def test_negative_speed_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Vehicle(
                id="veh_neg_speed",
                position=Position2D(0.0, 0.0),
                speed_mps=-1.0,
            )

    def test_invalid_state_enum_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Vehicle(
                id="veh_state",
                position=Position2D(0.0, 0.0),
                state="invalid_state",  # type: ignore[arg-type]
            )

    def test_invalid_vehicle_type_enum_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Vehicle(
                id="veh_type",
                position=Position2D(0.0, 0.0),
                vehicle_type="hovercraft",  # type: ignore[arg-type]
            )


class TestPedestrian:
    """Validation tests for Pedestrian."""

    def test_valid_pedestrian(self) -> None:
        ped = Pedestrian(
            id="ped_01",
            position=Position2D(5.0, 15.0),
            state=PedestrianState.CROSSING,
            speed_mps=1.2,
            crossing_node_id="node_cross_1",
            target_position=Position2D(5.0, 25.0),
        )
        assert ped.id == "ped_01"
        assert ped.state == PedestrianState.CROSSING
        assert ped.speed_mps == 1.2
        assert ped.crossing_node_id == "node_cross_1"

    def test_pedestrian_speed_exceeding_max_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Pedestrian(
                id="ped_fast",
                position=Position2D(0.0, 0.0),
                speed_mps=3.0,
                max_speed_mps=1.5,
            )

    def test_invalid_pedestrian_state_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Pedestrian(
                id="ped_state",
                position=Position2D(0.0, 0.0),
                state="flying",  # type: ignore[arg-type]
            )


class TestTrafficSignal:
    """Validation tests for TrafficSignal."""

    def test_valid_traffic_signal(self) -> None:
        sig = TrafficSignal(
            id="sig_10",
            node_id="node_10",
            state=TrafficSignalState.GREEN,
            cycle_duration_s=45.0,
            remaining_phase_s=15.0,
        )
        assert sig.id == "sig_10"
        assert sig.node_id == "node_10"
        assert sig.state == TrafficSignalState.GREEN
        assert sig.cycle_duration_s == 45.0
        assert sig.remaining_phase_s == 15.0

    def test_remaining_phase_exceeding_cycle_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            TrafficSignal(
                id="sig_bad",
                node_id="node_1",
                cycle_duration_s=60.0,
                remaining_phase_s=75.0,
            )
        assert "cannot exceed cycle_duration_s" in str(exc_info.value)

    def test_negative_remaining_phase_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            TrafficSignal(
                id="sig_bad_phase",
                node_id="node_1",
                cycle_duration_s=60.0,
                remaining_phase_s=-1.0,
            )


class TestObstacle:
    """Validation tests for Obstacle."""

    def test_valid_obstacle(self) -> None:
        obs = Obstacle(
            id="obs_01",
            position=Position2D(50.0, 60.0),
            obstacle_type=ObstacleType.CONSTRUCTION,
            dimensions=Dimensions2D(3.0, 2.0),
            edge_id="edge_1_2",
            description="Road work ahead",
        )
        assert obs.id == "obs_01"
        assert obs.obstacle_type == ObstacleType.CONSTRUCTION
        assert obs.dimensions.length_m == 3.0
        assert obs.edge_id == "edge_1_2"

    def test_invalid_obstacle_type_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Obstacle(
                id="obs_bad",
                position=Position2D(0.0, 0.0),
                obstacle_type="monster",  # type: ignore[arg-type]
            )


class TestIncident:
    """Validation tests for Incident."""

    def test_valid_incident(self) -> None:
        inc = Incident(
            id="inc_01",
            position=Position2D(120.0, 180.0),
            incident_type=IncidentType.ACCIDENT,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.ACTIVE,
            affected_edge_id="edge_1_2",
            reported_timestamp_s=125.0,
            description="Two car collision",
        )
        assert inc.id == "inc_01"
        assert inc.severity == IncidentSeverity.HIGH
        assert inc.status == IncidentStatus.ACTIVE
        assert inc.reported_timestamp_s == 125.0

    def test_negative_reported_timestamp_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Incident(
                id="inc_bad",
                position=Position2D(0.0, 0.0),
                reported_timestamp_s=-10.0,
            )


class TestV2VMessage:
    """Validation tests for V2VMessage."""

    def test_valid_v2v_broadcast(self) -> None:
        msg = V2VMessage(
            id="v2v_001",
            sender_id="veh_01",
            message_type=V2VMessageType.HAZARD_WARNING,
            timestamp_s=10.5,
            expiry_timestamp_s=25.0,
            sender_position=Position2D(50.0, 50.0),
            payload={"hazard_type": "accident", "edge_id": "edge_1_2"},
        )
        assert msg.id == "v2v_001"
        assert msg.recipient_id is None  # broadcast
        assert msg.expiry_timestamp_s == 25.0
        assert msg.payload["hazard_type"] == "accident"

    def test_expiry_before_timestamp_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            V2VMessage(
                id="v2v_bad_expiry",
                sender_id="veh_01",
                message_type=V2VMessageType.CONGESTION_ALERT,
                timestamp_s=50.0,
                expiry_timestamp_s=40.0,
            )
        assert "cannot be earlier than timestamp_s" in str(exc_info.value)

    def test_negative_timestamp_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            V2VMessage(
                id="v2v_neg_time",
                sender_id="veh_01",
                message_type=V2VMessageType.HEARTBEAT,
                timestamp_s=-1.0,
            )


class TestSimulationConfig:
    """Validation tests for SimulationConfig."""

    def test_default_config(self) -> None:
        cfg = SimulationConfig()
        assert cfg.time_step_s == 0.1
        assert cfg.random_seed == 42
        assert cfg.communication_radius_m == 150.0
        assert cfg.max_simulation_time_s == 3600.0
        assert cfg.max_vehicles == 100
        assert cfg.enable_v2v is True
        assert cfg.grid_width_m == 1000.0
        assert cfg.grid_height_m == 1000.0

    @pytest.mark.parametrize("dt", [0.0, -0.1, 2.5, float("inf"), float("nan")])
    def test_invalid_timestep_rejected(self, dt: float) -> None:
        with pytest.raises(DomainValidationError):
            SimulationConfig(time_step_s=dt)

    @pytest.mark.parametrize("comm_r", [0.0, -50.0])
    def test_invalid_comm_radius_rejected(self, comm_r: float) -> None:
        with pytest.raises(DomainValidationError):
            SimulationConfig(communication_radius_m=comm_r)

    @pytest.mark.parametrize("max_v", [0, -10])
    def test_invalid_max_vehicles_rejected(self, max_v: int) -> None:
        with pytest.raises(DomainValidationError):
            SimulationConfig(max_vehicles=max_v)
