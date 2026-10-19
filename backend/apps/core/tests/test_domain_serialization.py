"""Unit tests for domain serialization contracts, round-trips, and error handling."""

import json

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
from apps.core.domain.exceptions import SerializationError
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
from apps.core.domain.serialization import from_dict, from_json, to_dict, to_json
from apps.core.domain.values import Dimensions2D, GeoCoordinate, Position2D


class TestDomainSerialization:
    """Test suite for domain serialization and deserialization contracts."""

    def test_road_node_round_trip(self) -> None:
        node = RoadNode(
            id="node_42",
            position=Position2D(12.34, 56.78),
            geo_coordinate=GeoCoordinate(37.77, -122.41),
            attributes={"speed_camera": True},
        )
        data = to_dict(node)
        assert data["id"] == "node_42"
        assert data["position"] == {"x": 12.34, "y": 56.78}
        assert data["geo_coordinate"] == {"latitude": 37.77, "longitude": -122.41}
        assert data["attributes"]["speed_camera"] is True

        restored = from_dict(RoadNode, data)
        assert restored == node

    def test_road_edge_round_trip(self) -> None:
        edge = RoadEdge(
            id="edge_1_2",
            start_node_id="node_1",
            end_node_id="node_2",
            length_m=200.0,
            speed_limit_mps=15.0,
            lanes=3,
            name="Boulevard",
            attributes={"surface": "asphalt"},
        )
        data = to_dict(edge)
        assert data["id"] == "edge_1_2"
        assert data["lanes"] == 3
        restored = from_dict(RoadEdge, data)
        assert restored == edge

    def test_route_round_trip(self) -> None:
        route = Route(
            id="route_1",
            node_ids=["n1", "n2", "n3", "n4"],
            edge_ids=["e1", "e2", "e3"],
            total_distance_m=450.0,
            estimated_duration_s=32.5,
        )
        data = to_dict(route)
        restored = from_dict(Route, data)
        assert restored == route

    def test_vehicle_round_trip(self) -> None:
        veh = Vehicle(
            id="veh_007",
            position=Position2D(100.0, 250.0),
            speed_mps=11.5,
            max_speed_mps=14.0,
            heading_rad=1.57,
            state=VehicleState.EN_ROUTE,
            vehicle_type=VehicleType.EMERGENCY,
            dimensions=Dimensions2D(5.0, 2.1),
            current_node_id="n1",
            current_edge_id="e1",
            route_id="route_1",
            target_node_id="n4",
        )
        data = to_dict(veh)
        assert data["state"] == "en_route"
        assert data["vehicle_type"] == "emergency"
        assert data["dimensions"] == {"length_m": 5.0, "width_m": 2.1}

        restored = from_dict(Vehicle, data)
        assert restored == veh

    def test_pedestrian_round_trip(self) -> None:
        ped = Pedestrian(
            id="ped_99",
            position=Position2D(50.0, 75.0),
            state=PedestrianState.WAITING,
            speed_mps=0.0,
            max_speed_mps=1.4,
            crossing_node_id="n2",
            target_position=Position2D(50.0, 85.0),
        )
        data = to_dict(ped)
        assert data["state"] == "waiting"
        restored = from_dict(Pedestrian, data)
        assert restored == ped

    def test_traffic_signal_round_trip(self) -> None:
        sig = TrafficSignal(
            id="sig_1",
            node_id="n1",
            state=TrafficSignalState.YELLOW,
            position=Position2D(10.0, 10.0),
            cycle_duration_s=60.0,
            remaining_phase_s=5.0,
        )
        data = to_dict(sig)
        assert data["state"] == "yellow"
        restored = from_dict(TrafficSignal, data)
        assert restored == sig

    def test_obstacle_round_trip(self) -> None:
        obs = Obstacle(
            id="obs_5",
            position=Position2D(30.0, 40.0),
            obstacle_type=ObstacleType.STALLED_VEHICLE,
            dimensions=Dimensions2D(4.2, 1.8),
            edge_id="e2",
            description="Broken down car",
        )
        data = to_dict(obs)
        assert data["obstacle_type"] == "stalled_vehicle"
        restored = from_dict(Obstacle, data)
        assert restored == obs

    def test_incident_round_trip(self) -> None:
        inc = Incident(
            id="inc_8",
            position=Position2D(90.0, 120.0),
            incident_type=IncidentType.ROAD_CLOSURE,
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.ACTIVE,
            affected_edge_id="e3",
            reported_timestamp_s=250.0,
            description="Emergency water main repair",
        )
        data = to_dict(inc)
        assert data["incident_type"] == "road_closure"
        assert data["severity"] == "critical"
        assert data["status"] == "active"
        restored = from_dict(Incident, data)
        assert restored == inc

    def test_v2v_message_round_trip(self) -> None:
        msg = V2VMessage(
            id="msg_101",
            sender_id="veh_1",
            recipient_id="veh_2",
            message_type=V2VMessageType.EMERGENCY_CORRIDOR,
            timestamp_s=12.0,
            expiry_timestamp_s=30.0,
            sender_position=Position2D(15.0, 20.0),
            payload={"corridor_edge": "e1", "priority": "high"},
        )
        data = to_dict(msg)
        assert data["message_type"] == "emergency_corridor"
        restored = from_dict(V2VMessage, data)
        assert restored == msg

    def test_simulation_config_round_trip(self) -> None:
        cfg = SimulationConfig(
            time_step_s=0.05,
            random_seed=123,
            communication_radius_m=200.0,
            max_simulation_time_s=1800.0,
            max_vehicles=50,
            enable_v2v=False,
            grid_width_m=800.0,
            grid_height_m=800.0,
        )
        data = to_dict(cfg)
        restored = from_dict(SimulationConfig, data)
        assert restored == cfg

    def test_to_json_and_from_json_string(self) -> None:
        veh = Vehicle(
            id="veh_json",
            position=Position2D(1.0, 2.0),
            speed_mps=5.0,
        )
        json_str = to_json(veh)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["id"] == "veh_json"

        restored = from_json(Vehicle, json_str)
        assert restored == veh

    def test_from_json_invalid_json_raises(self) -> None:
        with pytest.raises(SerializationError) as exc_info:
            from_json(Vehicle, "{invalid json")
        assert "Malformed JSON" in str(exc_info.value)

    def test_from_dict_non_dict_raises(self) -> None:
        with pytest.raises(SerializationError) as exc_info:
            from_dict(Vehicle, "not_a_dict")  # type: ignore[arg-type]
        assert "Expected a dictionary" in str(exc_info.value)

    def test_from_dict_missing_required_position_raises(self) -> None:
        with pytest.raises(SerializationError) as exc_info:
            from_dict(Vehicle, {"id": "veh_missing_pos"})
        assert "position" in str(exc_info.value)

    def test_from_dict_invalid_enum_string_raises(self) -> None:
        with pytest.raises(SerializationError) as exc_info:
            from_dict(Vehicle, {
                "id": "veh_bad_enum",
                "position": {"x": 0.0, "y": 0.0},
                "state": "teleporting",
            })
        assert "Invalid value 'teleporting' for VehicleState" in str(exc_info.value)

    def test_from_dict_invalid_domain_rule_raises_serialization_error(self) -> None:
        # e.g., negative speed
        with pytest.raises(SerializationError) as exc_info:
            from_dict(Vehicle, {
                "id": "veh_neg_speed",
                "position": {"x": 0.0, "y": 0.0},
                "speed_mps": -5.0,
            })
        assert "Validation failed during deserialization" in str(exc_info.value)

    def test_unsupported_class_raises(self) -> None:
        class Unsupported:
            pass

        with pytest.raises(SerializationError):
            from_dict(Unsupported, {})  # type: ignore[type-abstract]
