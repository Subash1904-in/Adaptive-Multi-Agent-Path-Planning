"""Unit tests for SimulatedCommunicationNetwork, delivery semantics, and failure models."""

import pytest

from apps.core.communication.exceptions import (
    DuplicateRegistrationError,
    UnknownReceiverError,
    UnknownSenderError,
)
from apps.core.communication.models import (
    CommunicationConfig,
    DeliveryPolicy,
    V2VMessagePacket,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D


class TestSimulatedCommunicationNetwork:
    """Test suite for SimulatedCommunicationNetwork operations."""

    @pytest.fixture
    def default_network(self):
        config = CommunicationConfig(
            enabled=True,
            range_m=50.0,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
        )
        net = SimulatedCommunicationNetwork(config=config)
        net.register_participant("v1")
        net.register_participant("v2")
        net.register_participant("v3")
        return net

    def _create_packet(self, sender_id: str, x: float = 0.0, y: float = 0.0, **kwargs):
        defaults = {
            "message_id": f"msg_{sender_id}_{kwargs.get('sequence_number', 0)}",
            "sender_id": sender_id,
            "sequence_number": 0,
            "timestamp_s": 1.0,
            "sender_position": Position2D(x=x, y=y),
            "sender_heading_rad": 0.0,
            "sender_speed_mps": 10.0,
            "message_type": V2VMessageType.HEARTBEAT,
        }
        defaults.update(kwargs)
        return V2VMessagePacket(**defaults)

    def test_registration_and_duplicate_error(self):
        net = SimulatedCommunicationNetwork()
        net.register_participant("agent_a")
        assert net.is_participant_registered("agent_a") is True
        assert net.is_participant_registered("agent_b") is False

        with pytest.raises(DuplicateRegistrationError):
            net.register_participant("agent_a")

    def test_unregistration(self):
        net = SimulatedCommunicationNetwork()
        net.register_participant("v1")
        net.unregister_participant("v1")
        assert net.is_participant_registered("v1") is False

    def test_broadcast_next_tick_delivery_policy(self, default_network):
        """Under NEXT_TICK delivery, messages are in transit until advance_tick is called."""
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=20.0, y=0.0),   # in range (20m <= 50m)
            "v3": Position2D(x=100.0, y=0.0),  # out of range (100m > 50m)
        }
        msg = self._create_packet("v1", x=0.0, y=0.0)

        # Broadcast dispatched at t=1.0s
        receivers = default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers == ["v2"]
        assert default_network.metrics.broadcasts_attempted == 1
        assert default_network.metrics.broadcasts_successful == 1
        assert default_network.metrics.successful_deliveries == 1
        assert default_network.metrics.dropped_out_of_range == 1

        # At t=1.0s, message is in transit (NEXT_TICK policy) - inbox should be empty
        assert default_network.get_inbox("v2") == []

        # Advance tick to t=1.1s
        default_network.advance_tick(current_time_s=1.1)

        # Now message is in v2's inbox
        inbox = default_network.get_inbox("v2")
        assert len(inbox) == 1
        assert inbox[0].message_id == msg.message_id

        # Sender must never receive its own broadcast
        assert default_network.get_inbox("v1") == []

        # Drain inbox
        drained = default_network.clear_inbox("v2")
        assert len(drained) == 1
        assert default_network.get_inbox("v2") == []

    def test_broadcast_same_tick_delivery_policy(self):
        config = CommunicationConfig(
            enabled=True,
            range_m=50.0,
            delivery_policy=DeliveryPolicy.SAME_TICK,
        )
        net = SimulatedCommunicationNetwork(config=config)
        net.register_participant("v1")
        net.register_participant("v2")

        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        msg = self._create_packet("v1", x=0.0, y=0.0)
        receivers = net.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers == ["v2"]

        # Delivered immediately in SAME_TICK
        assert len(net.get_inbox("v2")) == 1

    def test_broadcast_no_peers_in_range(self, default_network):
        """Broadcasting with zero peers in range is a valid non-error operation."""
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=200.0, y=0.0),
            "v3": Position2D(x=300.0, y=0.0),
        }
        msg = self._create_packet("v1", x=0.0, y=0.0)
        receivers = default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers == []
        assert default_network.metrics.broadcasts_attempted == 1
        assert default_network.metrics.broadcasts_successful == 0
        assert default_network.metrics.dropped_out_of_range == 2

    def test_unknown_sender_raises(self, default_network):
        msg = self._create_packet("unregistered_sender", x=0.0, y=0.0)
        with pytest.raises(UnknownSenderError):
            default_network.broadcast(msg, {}, current_time_s=1.0)

    def test_targeted_unicast_delivery(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=15.0, y=0.0),
            "v3": Position2D(x=20.0, y=0.0),
        }
        msg = self._create_packet(
            "v1",
            x=0.0,
            y=0.0,
            recipient_id="v2",
            message_type=V2VMessageType.ROUTE_ADVISORY,
        )

        ok = default_network.send_unicast(msg, candidates, current_time_s=1.0)
        assert ok is True
        assert default_network.metrics.unicasts_attempted == 1
        assert default_network.metrics.unicasts_successful == 1

        default_network.advance_tick(1.1)
        assert len(default_network.get_inbox("v2")) == 1
        assert default_network.get_inbox("v3") == []

    def test_unicast_to_unknown_receiver_raises(self, default_network):
        candidates = {"v1": Position2D(x=0.0, y=0.0)}
        msg = self._create_packet("v1", recipient_id="ghost_receiver")
        with pytest.raises(UnknownReceiverError):
            default_network.send_unicast(msg, candidates, current_time_s=1.0)

    def test_unicast_out_of_range_fails(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=200.0, y=0.0),  # > 50m
        }
        msg = self._create_packet("v1", recipient_id="v2")
        ok = default_network.send_unicast(msg, candidates, current_time_s=1.0)
        assert ok is False
        assert default_network.metrics.dropped_out_of_range == 1

    def test_duplicate_message_rejected(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        msg = self._create_packet("v1", message_id="identical_msg")

        # First transmission succeeds
        receivers1 = default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers1 == ["v2"]

        # Duplicate transmission of same message_id is dropped
        receivers2 = default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers2 == []
        assert default_network.metrics.dropped_duplicate == 1

    def test_expired_message_dropped(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        # Message expired at t=2.0s
        msg = self._create_packet("v1", timestamp_s=1.0, expiry_timestamp_s=2.0)

        # Transmitted at t=3.0s (already expired)
        receivers = default_network.broadcast(msg, candidates, current_time_s=3.0)
        assert receivers == []
        assert default_network.metrics.dropped_expired == 1

    def test_participant_availability_failure_simulation(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        # Mark receiver v2 as unavailable (e.g. antenna damage or offline)
        default_network.set_participant_availability("v2", available=False)
        assert default_network.is_participant_available("v2") is False

        msg = self._create_packet("v1")
        receivers = default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers == []
        assert default_network.metrics.dropped_unavailable == 1

        # Re-enable receiver v2
        default_network.set_participant_availability("v2", available=True)
        msg2 = self._create_packet("v1", message_id="msg_v1_retry")
        receivers2 = default_network.broadcast(msg2, candidates, current_time_s=1.1)
        assert receivers2 == ["v2"]

    def test_deterministic_packet_loss(self):
        """A configured packet loss rate must drop packets deterministically."""
        config = CommunicationConfig(
            enabled=True,
            range_m=50.0,
            packet_loss_rate=0.5,
            packet_loss_seed=12345,
            delivery_policy=DeliveryPolicy.SAME_TICK,
        )
        net = SimulatedCommunicationNetwork(config=config)
        net.register_participant("v1")
        net.register_participant("v2")

        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }

        # Transmit 10 messages and record drop count
        for i in range(10):
            msg = V2VMessagePacket(
                message_id=f"loss_test_{i}",
                sender_id="v1",
                sequence_number=i,
                timestamp_s=float(i),
                sender_position=Position2D(x=0.0, y=0.0),
                sender_heading_rad=0.0,
                sender_speed_mps=5.0,
            )
            net.broadcast(msg, candidates, current_time_s=float(i))

        # With 50% loss, some packets must be delivered and some dropped
        delivered = net.metrics.successful_deliveries
        dropped_loss = net.metrics.dropped_packet_loss
        assert delivered + dropped_loss == 10
        assert delivered > 0
        assert dropped_loss > 0

    def test_state_capture_and_rollback(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        # Capture baseline state
        state_snapshot = default_network.capture_state()

        # Send a message
        msg = self._create_packet("v1", message_id="pre_rollback")
        default_network.broadcast(msg, candidates, current_time_s=1.0)
        assert default_network.metrics.broadcasts_attempted == 1

        # Restore state
        default_network.restore_state(state_snapshot)

        # Verified rolled back
        assert default_network.metrics.broadcasts_attempted == 0
        assert default_network.metrics.successful_deliveries == 0
        assert default_network._transit_queue["v2"] == []
        assert "pre_rollback" not in default_network._received_message_ids["v2"]

    def test_reset(self, default_network):
        candidates = {
            "v1": Position2D(x=0.0, y=0.0),
            "v2": Position2D(x=10.0, y=0.0),
        }
        msg = self._create_packet("v1")
        default_network.broadcast(msg, candidates, current_time_s=1.0)
        default_network.advance_tick(1.1)
        assert len(default_network.get_inbox("v2")) == 1

        default_network.reset()
        assert default_network.get_inbox("v2") == []
        assert default_network.metrics.broadcasts_attempted == 0
        assert default_network.metrics.successful_deliveries == 0

    def test_snapshot_generation(self, default_network):
        candidates = {"v1": Position2D(x=0.0, y=0.0), "v2": Position2D(x=10.0, y=0.0)}
        msg = self._create_packet("v1")
        default_network.broadcast(msg, candidates, current_time_s=1.0)

        snap = default_network.get_snapshot()
        assert snap.enabled is True
        assert snap.range_m == 50.0
        assert snap.delivery_policy == "next_tick"
        assert snap.total_broadcasts == 1
        d = snap.to_dict()
        assert d["total_broadcasts"] == 1
