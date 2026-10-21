"""Comprehensive deterministic unit tests for V2V communication latency and multi-tick queues.

Verifies:
- Zero-latency backward compatibility (SAME_TICK and NEXT_TICK).
- Fixed latency across discrete simulation ticks.
- Multi-tick transit queue scheduling and boundary enforcement.
- Early delivery prevention.
- In-flight packet expiration before delivery boundary.
- Receiver unavailability at delivery boundary.
- Deterministic queue ordering and canonical tie-breaking.
- In-transit queue inspection, reset, and atomic rollback.
- Cumulative metrics for queued vs delivered latency packets.
"""

import pytest

from apps.core.communication.models import (
    CommunicationConfig,
    DeliveryPolicy,
    V2VMessagePacket,
    V2VMessageType,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.domain.values import Position2D


@pytest.fixture
def base_positions() -> dict[str, Position2D]:
    """Spatial coordinates for two vehicles in direct 20m communication range."""
    return {
        "veh_a": Position2D(x=0.0, y=0.0),
        "veh_b": Position2D(x=20.0, y=0.0),
        "veh_c": Position2D(x=30.0, y=0.0),
    }


def make_packet(
    sender_id: str = "veh_a",
    seq: int = 1,
    time_s: float = 0.0,
    msg_id: str = "msg_001",
    ttl_s: float | None = 2.0,
    mtype: V2VMessageType = V2VMessageType.HEARTBEAT,
    payload: dict | None = None,
) -> V2VMessagePacket:
    """Helper to construct valid V2V message packets."""
    expiry = (time_s + ttl_s) if ttl_s is not None else None
    return V2VMessagePacket(
        message_id=msg_id,
        sender_id=sender_id,
        sequence_number=seq,
        timestamp_s=time_s,
        sender_position=Position2D(x=0.0, y=0.0),
        sender_heading_rad=0.0,
        sender_speed_mps=10.0,
        message_type=mtype,
        expiry_timestamp_s=expiry,
        payload=dict(payload or {"test": True}),
    )


class TestZeroLatencyCompatibility:
    """Validate zero-latency default behavior matches Phase 11-13 semantics exactly."""

    def test_same_tick_zero_latency_delivers_immediately(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        cfg = CommunicationConfig(
            min_latency_s=0.0,
            max_latency_s=0.0,
            delivery_policy=DeliveryPolicy.SAME_TICK,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m1", time_s=1.0)
        delivered = net.broadcast(msg, base_positions, current_time_s=1.0)

        assert delivered == ["veh_b"]
        assert len(net.get_inbox("veh_b")) == 1
        assert net.get_inbox("veh_b")[0].message_id == "m1"
        assert net.get_in_transit_count() == 0
        assert net.metrics.packets_queued_latency == 0
        assert net.metrics.successful_deliveries == 1

    def test_next_tick_zero_latency_delivers_on_next_tick(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        cfg = CommunicationConfig(
            min_latency_s=0.0,
            max_latency_s=0.0,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m1", time_s=1.0)
        accepted = net.broadcast(msg, base_positions, current_time_s=1.0)

        assert accepted == ["veh_b"]
        # In transit at t=1.0
        assert net.get_inbox("veh_b") == []
        assert net.get_in_transit_count() == 1
        assert len(net._transit_queue["veh_b"]) == 1

        # Advance to t=1.1
        net.advance_tick(current_time_s=1.1)
        assert len(net.get_inbox("veh_b")) == 1
        assert net.get_in_transit_count() == 0
        assert len(net._transit_queue["veh_b"]) == 0


class TestMultiTickLatencyQueues:
    """Validate multi-tick transit delay scheduling and delivery boundary enforcement."""

    def test_fixed_latency_multi_tick_delivery(self, base_positions: dict[str, Position2D]) -> None:
        """With latency=0.2s and step=0.1s, packet sent at t=1.0 is delivered at t=1.2."""
        cfg = CommunicationConfig(
            min_latency_s=0.2,
            max_latency_s=0.2,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m_lat", time_s=1.0)
        accepted = net.broadcast(msg, base_positions, current_time_s=1.0)

        assert accepted == ["veh_b"]
        assert net.metrics.packets_queued_latency == 1
        assert net.metrics.successful_deliveries == 0
        assert net.get_in_transit_count() == 1

        in_transit = net.get_in_transit_packets()[0]
        assert in_transit.send_timestamp_s == 1.0
        assert pytest.approx(in_transit.scheduled_delivery_time_s) == 1.2

        # Tick 1: t = 1.1s (1.1 < 1.2: must NOT be delivered yet)
        net.advance_tick(current_time_s=1.1)
        assert net.get_inbox("veh_b") == []
        assert net.get_in_transit_count() == 1
        assert net.metrics.successful_deliveries == 0
        assert net.metrics.packets_delivered_latency == 0

        # Tick 2: t = 1.2s (1.2 >= 1.2: delivery boundary reached)
        net.advance_tick(current_time_s=1.2)
        inbox = net.get_inbox("veh_b")
        assert len(inbox) == 1
        assert inbox[0].message_id == "m_lat"
        assert net.get_in_transit_count() == 0
        assert net.metrics.successful_deliveries == 1
        assert net.metrics.packets_delivered_latency == 1

    def test_sub_tick_positive_latency_delivers_at_first_boundary(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """Latency of 0.03s sent at t=1.0 has delivery time 1.03s; delivered at tick 1.1s."""
        cfg = CommunicationConfig(min_latency_s=0.03, max_latency_s=0.03)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m_sub", time_s=1.0)
        net.broadcast(msg, base_positions, current_time_s=1.0)

        # Before boundary at t=1.0
        assert net.get_inbox("veh_b") == []

        # Advance to boundary t=1.1 (1.1 >= 1.03)
        net.advance_tick(current_time_s=1.1)
        assert len(net.get_inbox("veh_b")) == 1

    def test_packet_expires_while_in_transit_is_dropped(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """Packet with TTL=0.15s (expiry 1.15s) and latency 0.3s (scheduled 1.3s) expires."""
        cfg = CommunicationConfig(min_latency_s=0.3, max_latency_s=0.3)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        # Expiry timestamp = 1.0 + 0.15 = 1.15s
        msg = make_packet(sender_id="veh_a", msg_id="m_exp", time_s=1.0, ttl_s=0.15)
        net.broadcast(msg, base_positions, current_time_s=1.0)

        # At t=1.1, packet is still in transit (1.1 < 1.3) and not expired (1.1 < 1.15)
        net.advance_tick(current_time_s=1.1)
        assert net.get_inbox("veh_b") == []
        assert net.get_in_transit_count() == 1

        # At t=1.3, scheduled delivery arrives, but message is expired (1.3 >= 1.15)
        net.advance_tick(current_time_s=1.3)
        assert net.get_inbox("veh_b") == []
        assert net.get_in_transit_count() == 0
        assert net.metrics.dropped_expired >= 1
        assert net.metrics.successful_deliveries == 0

    def test_receiver_unavailable_at_delivery_boundary_drops_packet(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """Receiver available at transmission but disabled before delivery boundary."""
        cfg = CommunicationConfig(min_latency_s=0.2, max_latency_s=0.2)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m_unavail", time_s=1.0)
        net.broadcast(msg, base_positions, current_time_s=1.0)
        assert net.get_in_transit_count() == 1

        # Turn off receiver at t=1.15
        net.set_participant_availability("veh_b", available=False)

        # Advance to delivery boundary t=1.2
        net.advance_tick(current_time_s=1.2)
        assert net.get_inbox("veh_b") == []
        assert net.get_in_transit_count() == 0
        assert net.metrics.dropped_unavailable >= 1
        assert net.metrics.successful_deliveries == 0

    def test_deterministic_queue_ordering_tie_breaking(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """Multiple packets arriving at the exact same delivery boundary sort deterministically."""
        cfg = CommunicationConfig(min_latency_s=0.1, max_latency_s=0.1)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        # Send packets in arbitrary ID order
        p3 = make_packet(sender_id="veh_a", seq=3, time_s=1.0, msg_id="pkt_c")
        p1 = make_packet(sender_id="veh_a", seq=1, time_s=1.0, msg_id="pkt_a")
        p2 = make_packet(sender_id="veh_a", seq=2, time_s=1.0, msg_id="pkt_b")

        net.broadcast(p3, base_positions, current_time_s=1.0)
        net.broadcast(p1, base_positions, current_time_s=1.0)
        net.broadcast(p2, base_positions, current_time_s=1.0)

        # In transit packets are returned in sorted order by sort_key
        sorted_in_transit = net.get_in_transit_packets()
        assert [pkt.packet.message_id for pkt in sorted_in_transit] == ["pkt_a", "pkt_b", "pkt_c"]

        # Advance to delivery
        net.advance_tick(current_time_s=1.1)
        inbox = net.get_inbox("veh_b")
        assert [msg.message_id for msg in inbox] == ["pkt_a", "pkt_b", "pkt_c"]


class TestLatencyRollbackAndReset:
    """Verify state capture, rollback, and reset with multi-tick in-transit queues."""

    def test_atomic_rollback_restores_in_transit_queue(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        cfg = CommunicationConfig(min_latency_s=0.2, max_latency_s=0.2)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        snap_initial = net.capture_state()

        # Send packet
        msg = make_packet(sender_id="veh_a", msg_id="m_roll", time_s=1.0)
        net.broadcast(msg, base_positions, current_time_s=1.0)
        assert net.get_in_transit_count() == 1
        assert net.metrics.packets_queued_latency == 1

        # Rollback
        net.restore_state(snap_initial)
        assert net.get_in_transit_count() == 0
        assert net.metrics.packets_queued_latency == 0
        assert net.get_inbox("veh_b") == []
        assert "m_roll" not in net._received_message_ids["veh_b"]

    def test_reset_clears_in_transit_packets(self, base_positions: dict[str, Position2D]) -> None:
        cfg = CommunicationConfig(min_latency_s=0.5, max_latency_s=0.5)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        msg = make_packet(sender_id="veh_a", msg_id="m_reset", time_s=1.0)
        net.broadcast(msg, base_positions, current_time_s=1.0)
        assert net.get_in_transit_count() == 1

        net.reset()
        assert net.get_in_transit_count() == 0
        assert net.get_inbox("veh_b") == []
        assert net.metrics.packets_queued_latency == 0


class TestLatencyConfigurationValidation:
    """Validate invalid latency settings are rejected."""

    def test_negative_min_latency_raises(self) -> None:
        with pytest.raises(Exception):
            CommunicationConfig(min_latency_s=-0.1)

    def test_max_latency_less_than_min_raises(self) -> None:
        with pytest.raises(Exception):
            CommunicationConfig(min_latency_s=0.5, max_latency_s=0.2)
