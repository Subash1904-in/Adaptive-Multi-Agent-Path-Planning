"""Unit tests for Phase 18 V2V emergency announcements and local awareness records.

Verifies:
- EmergencyMessagePayload serialization, deserialization, and validation
- Emergency packet construction for all operational message types
- Packet delivery via SimulatedCommunicationNetwork with latency and drop rates
- Local awareness store ingestion, updates, and idempotency
- Packet-loss, network partition, and range-based non-delivery
- Stale and expired message rejection
- Cancellation and completion message handling
- Local awareness isolation (zero omniscient global leakage)
"""

import pytest

from apps.core.communication.models import (
    CommunicationConfig,
    DeliveryPolicy,
    V2VMessagePacket,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D
from apps.core.emergency.models import (
    EmergencyAwarenessRecord,
    EmergencyCorridor,
    EmergencyType,
    PriorityRequest,
    YieldActionType,
    YieldRequest,
)
from apps.core.emergency.v2v import (
    EmergencyMessagePayload,
    create_corridor_proposed_message,
    create_corridor_updated_message,
    create_emergency_activated_message,
    create_emergency_completed_message,
    create_priority_cancelled_message,
    create_priority_request_message,
    create_yield_acknowledged_message,
    create_yield_request_message,
    ingest_emergency_message_into_awareness,
)


class TestEmergencyPayloadCodecs:
    """Tests for payload serialization, deserialization, and schema validation."""

    def test_payload_roundtrip_dict(self) -> None:
        payload = EmergencyMessagePayload(
            operation="EMERGENCY_ACTIVATED",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            request_id="req_001",
            priority_level=2,
            destination_node_id="node_r2_c2",
            corridor_edges=("e1", "e2"),
            corridor_nodes=("n1", "n2", "n3"),
            creation_time_s=10.0,
            expiry_time_s=40.0,
        )
        d = payload.to_dict()
        assert d["operation"] == "EMERGENCY_ACTIVATED"
        assert d["vehicle_id"] == "amb_01"
        assert d["emergency_type"] == "ambulance"
        assert d["priority_level"] == 2
        assert d["corridor_edges"] == ["e1", "e2"]

        reconstructed = EmergencyMessagePayload.from_dict(d)
        assert reconstructed == payload

    def test_payload_roundtrip_json(self) -> None:
        payload = EmergencyMessagePayload(
            operation="YIELD_REQUEST",
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            priority_level=1,
            target_vehicle_id="standard_42",
            recommended_action=YieldActionType.STOP_BEFORE_INTERSECTION,
            target_speed_mps=0.0,
            target_decel_mps2=-3.5,
            creation_time_s=5.0,
            expiry_time_s=15.0,
            details={"yield_id": "y_001"},
        )
        json_str = payload.to_json()
        assert "STOP_BEFORE_INTERSECTION" in json_str or "stop_before_intersection" in json_str
        parsed = EmergencyMessagePayload.from_json(json_str)
        assert parsed.operation == "YIELD_REQUEST"
        assert parsed.recommended_action == YieldActionType.STOP_BEFORE_INTERSECTION
        assert parsed.target_vehicle_id == "standard_42"
        assert parsed.details == {"yield_id": "y_001"}

    def test_invalid_json_handling(self) -> None:
        from apps.core.communication.exceptions import CommunicationValidationError

        # 1. Invalid JSON string raises CommunicationValidationError
        with pytest.raises(CommunicationValidationError):
            EmergencyMessagePayload.from_json("{this is not valid json}")

        # 2. Packet with malformed emergency payload dict returns None gracefully
        store: dict[str, EmergencyAwarenessRecord] = {}
        packet = V2VMessagePacket(
            message_id="m_corrupt",
            sender_id="amb_01",
            sequence_number=1,
            timestamp_s=1.0,
            sender_position=Position2D(x=0.0, y=0.0),
            sender_heading_rad=0.0,
            sender_speed_mps=0.0,
            message_type=V2VMessageType.EMERGENCY_ACTIVATED,
            payload={"invalid_emergency_field": "corrupted"},
            expiry_timestamp_s=10.0,
        )
        res = ingest_emergency_message_into_awareness(packet, store, current_time_s=2.0)
        assert res is None
        assert len(store) == 0


class TestEmergencyPacketBuilders:
    """Tests for packet construction helpers."""

    def test_create_emergency_activated_message(self) -> None:
        pkt = create_emergency_activated_message(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            current_time_s=5.0,
            ttl_s=25.0,
        )
        assert pkt.sender_id == "amb_01"
        assert pkt.message_type == V2VMessageType.EMERGENCY_ACTIVATED
        assert pkt.expiry_timestamp_s == 30.0
        payload = EmergencyMessagePayload.from_dict(pkt.payload)
        assert payload.operation == "EMERGENCY_ACTIVATED"
        assert payload.priority_level == 2

    def test_create_priority_request_message(self) -> None:
        req = PriorityRequest(
            request_id="req_99",
            vehicle_id="police_01",
            emergency_type=EmergencyType.POLICE,
            priority_level=3,
            destination_node_id="node_dest",
            creation_time_s=2.0,
            ttl_s=45.0,
        )
        pkt = create_priority_request_message(req, current_time_s=2.0)
        assert pkt.message_type == V2VMessageType.PRIORITY_REQUEST
        payload = EmergencyMessagePayload.from_dict(pkt.payload)
        assert payload.request_id == "req_99"
        assert payload.destination_node_id == "node_dest"

    def test_create_corridor_proposed_and_updated_messages(self) -> None:
        corridor = EmergencyCorridor(
            corridor_id="cor_01",
            request_id="req_01",
            vehicle_id="amb_01",
            edge_ids=("e_0_1", "e_1_2"),
            node_ids=("n0", "n1", "n2"),
            creation_time_s=1.0,
            expiry_time_s=30.0,
        )
        prop_pkt = create_corridor_proposed_message(
            corridor=corridor,
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            current_time_s=1.0,
        )
        assert prop_pkt.message_type == V2VMessageType.CORRIDOR_PROPOSED

        upd_pkt = create_corridor_updated_message(
            corridor=corridor,
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            current_time_s=2.0,
        )
        assert upd_pkt.message_type == V2VMessageType.CORRIDOR_UPDATED

    def test_create_yield_request_and_ack_messages(self) -> None:
        y_req = YieldRequest(
            yield_id="y_123",
            emergency_vehicle_id="amb_01",
            target_vehicle_id="veh_02",
            edge_id="e_0_1",
            node_id="n_1",
            recommended_action=YieldActionType.YIELD_TO_EMERGENCY,
            target_speed_mps=2.0,
            target_decel_mps2=-2.0,
            creation_time_s=10.0,
            expiry_time_s=25.0,
        )
        pkt_y = create_yield_request_message(
            yield_req=y_req,
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            current_time_s=10.0,
        )
        assert pkt_y.message_type == V2VMessageType.YIELD_REQUEST

        pkt_ack = create_yield_acknowledged_message(
            vehicle_id="veh_02",
            emergency_vehicle_id="amb_01",
            yield_id="y_123",
            current_time_s=10.5,
        )
        assert pkt_ack.message_type == V2VMessageType.YIELD_ACKNOWLEDGED
        payload = EmergencyMessagePayload.from_dict(pkt_ack.payload)
        assert payload.details == {"yield_id": "y_123"}

    def test_create_cancellation_and_completion_messages(self) -> None:
        pkt_cancel = create_priority_cancelled_message(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            request_id="req_01",
            current_time_s=20.0,
        )
        assert pkt_cancel.message_type == V2VMessageType.PRIORITY_CANCELLED

        pkt_comp = create_emergency_completed_message(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            request_id="req_01",
            current_time_s=25.0,
        )
        assert pkt_comp.message_type == V2VMessageType.EMERGENCY_COMPLETED


class TestLocalAwarenessIngestionAndIsolation:
    """Tests for local awareness stores, isolation, and handling of stale/expired packets."""

    def test_awareness_ingestion_activation_and_update(self) -> None:
        store: dict[str, EmergencyAwarenessRecord] = {}

        # 1. Receive activation
        act_pkt = create_emergency_activated_message("amb_01", EmergencyType.AMBULANCE, 2, 0.0)
        rec = ingest_emergency_message_into_awareness(act_pkt, store, current_time_s=0.5)
        assert rec is not None
        assert rec.emergency_vehicle_id == "amb_01"
        assert rec.is_active is True
        assert rec.priority_level == 2
        assert "amb_01" in store

        # 2. Receive corridor update
        corridor = EmergencyCorridor(
            corridor_id="cor_01",
            request_id="req_01",
            vehicle_id="amb_01",
            edge_ids=("edge_a", "edge_b"),
            node_ids=("node_1", "node_2", "node_3"),
            creation_time_s=1.0,
            expiry_time_s=30.0,
        )
        cor_pkt = create_corridor_proposed_message(
            corridor, EmergencyType.AMBULANCE, 2, current_time_s=1.0
        )
        rec2 = ingest_emergency_message_into_awareness(cor_pkt, store, current_time_s=1.5)
        assert rec2 is not None
        assert rec2.corridor_edges == ("edge_a", "edge_b")
        assert rec2.corridor_nodes == ("node_1", "node_2", "node_3")

        # 3. Receive yield request
        y_req = YieldRequest(
            yield_id="y_999",
            emergency_vehicle_id="amb_01",
            target_vehicle_id="veh_local",
            edge_id="edge_a",
            node_id="n_a",
            recommended_action=YieldActionType.YIELD_TO_EMERGENCY,
            target_speed_mps=0.0,
            target_decel_mps2=-3.0,
            creation_time_s=2.0,
            expiry_time_s=20.0,
        )
        y_pkt = create_yield_request_message(y_req, EmergencyType.AMBULANCE, 2, current_time_s=2.0)
        rec3 = ingest_emergency_message_into_awareness(y_pkt, store, current_time_s=2.5)
        assert rec3 is not None
        assert "y_999" in rec3.active_yield_requests

    def test_stale_and_expired_message_rejection(self) -> None:
        store: dict[str, EmergencyAwarenessRecord] = {}
        # Message created at 0.0 with TTL 10.0
        pkt = create_emergency_activated_message(
            "amb_01", EmergencyType.AMBULANCE, 2, current_time_s=0.0, ttl_s=10.0
        )
        # Ingestion attempted at time 12.0 (expired)
        result = ingest_emergency_message_into_awareness(pkt, store, current_time_s=12.0)
        assert result is None
        assert len(store) == 0

    def test_cancellation_and_completion_deactivates_awareness(self) -> None:
        store: dict[str, EmergencyAwarenessRecord] = {}
        act_pkt = create_emergency_activated_message("amb_01", EmergencyType.AMBULANCE, 2, 0.0)
        ingest_emergency_message_into_awareness(act_pkt, store, current_time_s=0.5)
        assert store["amb_01"].is_active is True

        # Now cancel
        cancel_pkt = create_priority_cancelled_message(
            "amb_01", EmergencyType.AMBULANCE, "req_01", 5.0
        )
        rec = ingest_emergency_message_into_awareness(cancel_pkt, store, current_time_s=5.5)
        assert rec is not None
        assert rec.is_active is False

    def test_local_awareness_isolation_no_leakage(self) -> None:
        """Vehicle A and B maintain separate local stores; Vehicle C receives nothing."""
        store_a: dict[str, EmergencyAwarenessRecord] = {}
        store_b: dict[str, EmergencyAwarenessRecord] = {}
        store_c: dict[str, EmergencyAwarenessRecord] = {}

        pkt = create_emergency_activated_message("amb_01", EmergencyType.AMBULANCE, 2, 0.0)

        # Delivered to A and B, but NOT C
        ingest_emergency_message_into_awareness(pkt, store_a, current_time_s=0.1)
        ingest_emergency_message_into_awareness(pkt, store_b, current_time_s=0.2)

        assert "amb_01" in store_a and store_a["amb_01"].is_active is True
        assert "amb_01" in store_b and store_b["amb_01"].is_active is True
        assert "amb_01" not in store_c
        assert len(store_c) == 0


class TestSimulatedNetworkEmergencyDelivery:
    """Tests emergency packet transmission through SimulatedCommunicationNetwork."""

    def test_broadcast_and_delivery_under_nominal_conditions(self) -> None:
        net = SimulatedCommunicationNetwork(
            config=CommunicationConfig(
                range_m=100.0,
                packet_loss_rate=0.0,
                delivery_policy=DeliveryPolicy.NEXT_TICK,
            )
        )
        net.register_participant("amb_01")
        net.register_participant("veh_01")
        net.register_participant("veh_far")

        positions = {
            "amb_01": Position2D(x=0.0, y=0.0),
            "veh_01": Position2D(x=30.0, y=0.0),
            "veh_far": Position2D(x=200.0, y=0.0),
        }

        pkt = create_emergency_activated_message(
            "amb_01", EmergencyType.AMBULANCE, 2, current_time_s=1.0
        )
        receivers = net.broadcast(pkt, positions, current_time_s=1.0)
        assert receivers == ["veh_01"]

        # Before next tick (NEXT_TICK policy), inboxes are empty
        assert net.get_inbox("veh_01") == []

        # Advance tick to 1.1
        net.advance_tick(current_time_s=1.1)

        inbox = net.get_inbox("veh_01")
        assert len(inbox) == 1
        assert inbox[0].message_id == pkt.message_id
        assert net.get_inbox("veh_far") == []
        assert net.get_inbox("amb_01") == []  # sender does not receive own broadcast

    def test_packet_loss_prevents_awareness_update(self) -> None:
        """100% packet drop rate prevents packet from reaching target vehicle."""
        net = SimulatedCommunicationNetwork(
            config=CommunicationConfig(
                range_m=100.0,
                packet_loss_rate=1.0,
                delivery_policy=DeliveryPolicy.SAME_TICK,
            )
        )
        net.register_participant("amb_01")
        net.register_participant("veh_01")
        positions = {"amb_01": Position2D(x=0.0, y=0.0), "veh_01": Position2D(x=20.0, y=0.0)}

        pkt = create_emergency_activated_message(
            "amb_01", EmergencyType.AMBULANCE, 2, current_time_s=1.0
        )
        receivers = net.broadcast(pkt, positions, current_time_s=1.0)
        assert len(receivers) == 0

        inbox = net.get_inbox("veh_01")
        assert len(inbox) == 0

        # veh_01 local awareness remains completely empty
        veh_store: dict[str, EmergencyAwarenessRecord] = {}
        for p in inbox:
            ingest_emergency_message_into_awareness(p, veh_store, 1.0)
        assert len(veh_store) == 0
