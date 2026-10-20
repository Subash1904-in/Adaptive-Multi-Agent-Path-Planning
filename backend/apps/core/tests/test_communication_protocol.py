"""Unit tests for V2V communication message protocol, validation, and serialization."""

import json

import pytest

from apps.core.communication.exceptions import (
    CommunicationValidationError,
    MessageSerializationError,
)
from apps.core.communication.models import (
    V2VMessagePacket,
    VehicleStatusPayload,
)
from apps.core.communication.protocol import (
    create_status_message,
    deserialize_message,
    serialize_message,
)
from apps.core.domain.enums import V2VMessageType, VehicleState, VehicleType
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.simulation.models import VehicleSnapshot


class TestVehicleStatusPayload:
    """Tests for VehicleStatusPayload construction and serialization."""

    def test_payload_to_dict_and_from_dict(self):
        payload = VehicleStatusPayload(
            current_edge_id="edge_1",
            target_node_id="node_5",
            route_id="route_42",
            remaining_distance_m=123.45678,
            acceleration_mps2=1.5,
            custom_data={"battery_pct": 95},
        )
        d = payload.to_dict()
        assert d["current_edge_id"] == "edge_1"
        assert d["target_node_id"] == "node_5"
        assert d["route_id"] == "route_42"
        assert d["remaining_distance_m"] == 123.4568
        assert d["acceleration_mps2"] == 1.5
        assert d["custom_data"] == {"battery_pct": 95}

        reconstructed = VehicleStatusPayload.from_dict(d)
        assert reconstructed.current_edge_id == payload.current_edge_id
        assert reconstructed.target_node_id == payload.target_node_id
        assert reconstructed.route_id == payload.route_id
        assert reconstructed.custom_data == {"battery_pct": 95}

    def test_payload_invalid_dict_raises(self):
        with pytest.raises(CommunicationValidationError):
            VehicleStatusPayload.from_dict("not_a_dict")  # type: ignore[arg-type]


class TestV2VMessagePacketValidation:
    """Validation invariant tests for V2VMessagePacket."""

    @pytest.fixture
    def valid_packet_kwargs(self):
        return {
            "message_id": "msg_001",
            "sender_id": "veh_alpha",
            "sequence_number": 0,
            "timestamp_s": 10.5,
            "sender_position": Position2D(x=100.0, y=200.0),
            "sender_heading_rad": 1.57,
            "sender_speed_mps": 13.4,
            "message_type": V2VMessageType.HEARTBEAT,
            "protocol_version": "1.0.0",
        }

    def test_valid_packet_creation(self, valid_packet_kwargs):
        pkt = V2VMessagePacket(**valid_packet_kwargs)
        assert pkt.message_id == "msg_001"
        assert pkt.sender_id == "veh_alpha"
        assert pkt.sequence_number == 0
        assert pkt.timestamp_s == 10.5
        assert pkt.sender_position == Position2D(x=100.0, y=200.0)
        assert pkt.sender_heading_rad == 1.57
        assert pkt.sender_speed_mps == 13.4
        assert pkt.recipient_id is None
        assert pkt.expiry_timestamp_s is None
        assert pkt.is_expired(10.5) is False
        assert pkt.is_expired(100.0) is False

    @pytest.mark.parametrize("invalid_id", ["", "   ", None, 123])
    def test_invalid_message_id_raises(self, valid_packet_kwargs, invalid_id):
        valid_packet_kwargs["message_id"] = invalid_id
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "message_id"

    @pytest.mark.parametrize("invalid_sender", ["", "   ", None, 456])
    def test_invalid_sender_id_raises(self, valid_packet_kwargs, invalid_sender):
        valid_packet_kwargs["sender_id"] = invalid_sender
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "sender_id"

    @pytest.mark.parametrize("invalid_seq", [-1, -10, 1.5, "0", True, False])
    def test_invalid_sequence_number_raises(self, valid_packet_kwargs, invalid_seq):
        valid_packet_kwargs["sequence_number"] = invalid_seq
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "sequence_number"

    @pytest.mark.parametrize("invalid_time", [-0.1, -10.0, float("nan"), float("inf"), "10.0"])
    def test_invalid_timestamp_raises(self, valid_packet_kwargs, invalid_time):
        valid_packet_kwargs["timestamp_s"] = invalid_time
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "timestamp_s"

    @pytest.mark.parametrize("invalid_speed", [-0.1, -5.0, float("nan"), float("inf"), "zero"])
    def test_invalid_speed_raises(self, valid_packet_kwargs, invalid_speed):
        valid_packet_kwargs["sender_speed_mps"] = invalid_speed
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "sender_speed_mps"

    @pytest.mark.parametrize("invalid_heading", [float("nan"), float("inf"), "north"])
    def test_invalid_heading_raises(self, valid_packet_kwargs, invalid_heading):
        valid_packet_kwargs["sender_heading_rad"] = invalid_heading
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "sender_heading_rad"

    def test_invalid_position_raises(self, valid_packet_kwargs):
        valid_packet_kwargs["sender_position"] = (100.0, 200.0)
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "sender_position"

    def test_invalid_recipient_id_raises(self, valid_packet_kwargs):
        valid_packet_kwargs["recipient_id"] = ""
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "recipient_id"

    def test_expiry_timestamp_validation_and_check(self, valid_packet_kwargs):
        # Expiry earlier than timestamp raises
        valid_packet_kwargs["expiry_timestamp_s"] = 9.0
        with pytest.raises(CommunicationValidationError) as exc:
            V2VMessagePacket(**valid_packet_kwargs)
        assert exc.value.field == "expiry_timestamp_s"

        # Valid expiry
        valid_packet_kwargs["expiry_timestamp_s"] = 12.0
        pkt = V2VMessagePacket(**valid_packet_kwargs)
        assert pkt.is_expired(11.9) is False
        assert pkt.is_expired(12.0) is True
        assert pkt.is_expired(15.0) is True


class TestStatusMessageFactory:
    """Tests for create_status_message helper."""

    def test_create_from_vehicle_entity(self):
        v = Vehicle(
            id="v_100",
            vehicle_type=VehicleType.STANDARD,
            position=Position2D(x=50.0, y=75.0),
            speed_mps=12.0,
            heading_rad=0.785,
        )
        msg = create_status_message(
            vehicle=v,
            sequence_number=1,
            timestamp_s=5.0,
            ttl_s=2.0,
        )
        assert msg.sender_id == "v_100"
        assert msg.sequence_number == 1
        assert msg.timestamp_s == 5.0
        assert msg.expiry_timestamp_s == 7.0
        assert msg.sender_position == Position2D(x=50.0, y=75.0)
        assert msg.sender_speed_mps == 12.0
        assert msg.message_type == V2VMessageType.HEARTBEAT

    def test_create_from_vehicle_snapshot(self):
        snap = VehicleSnapshot(
            vehicle_id="v_snap",
            state=VehicleState.EN_ROUTE,
            position=Position2D(x=10.0, y=20.0),
            heading_rad=1.5,
            speed_mps=8.5,
            current_edge_id="edge_A",
            current_node_id="node_B",
            distance_along_segment_m=15.0,
            remaining_route_distance_m=85.0,
            route_id="route_1",
            target_node_id="node_Z",
        )
        msg = create_status_message(
            vehicle=snap,
            sequence_number=5,
            timestamp_s=2.5,
            ttl_s=1.0,
            custom_payload={"status": "normal"},
        )
        assert msg.sender_id == "v_snap"
        assert msg.sequence_number == 5
        assert msg.payload["current_edge_id"] == "edge_A"
        assert msg.payload["target_node_id"] == "node_Z"
        assert msg.payload["custom_data"] == {"status": "normal"}

    def test_create_from_invalid_object_raises(self):
        with pytest.raises(CommunicationValidationError):
            create_status_message(vehicle="not_a_vehicle", sequence_number=0, timestamp_s=0.0)  # type: ignore[arg-type]


class TestMessageSerialization:
    """Tests for JSON serialization round-tripping."""

    def test_serialization_round_trip(self):
        pkt = V2VMessagePacket(
            message_id="msg_42",
            sender_id="veh_01",
            sequence_number=10,
            timestamp_s=3.14159,
            sender_position=Position2D(x=12.34, y=56.78),
            sender_heading_rad=0.5,
            sender_speed_mps=15.2,
            message_type=V2VMessageType.HAZARD_WARNING,
            recipient_id="veh_02",
            expiry_timestamp_s=5.0,
            payload={"hazard": "ice_patch", "severity": "high"},
            correlation_id="corr_99",
        )

        json_str = serialize_message(pkt)
        assert isinstance(json_str, str)
        parsed_dict = json.loads(json_str)
        assert parsed_dict["message_id"] == "msg_42"
        assert parsed_dict["sender_id"] == "veh_01"
        assert parsed_dict["message_type"] == "hazard_warning"

        restored = deserialize_message(json_str)
        assert restored.message_id == pkt.message_id
        assert restored.sender_id == pkt.sender_id
        assert restored.sequence_number == pkt.sequence_number
        assert restored.sender_position == pkt.sender_position
        assert restored.message_type == pkt.message_type
        assert restored.recipient_id == pkt.recipient_id
        assert restored.payload == pkt.payload
        assert restored.correlation_id == pkt.correlation_id

    def test_deserialize_malformed_json_raises(self):
        with pytest.raises(MessageSerializationError):
            deserialize_message("{invalid_json: true")

    def test_deserialize_missing_fields_raises(self):
        with pytest.raises(MessageSerializationError):
            deserialize_message(json.dumps({"message_id": "test"}))

    def test_serialize_non_packet_raises(self):
        with pytest.raises(MessageSerializationError):
            serialize_message({"not": "a_packet"})  # type: ignore[arg-type]
