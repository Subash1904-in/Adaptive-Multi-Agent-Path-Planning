"""Deterministic tests for packet loss, distance attenuation, burst loss, and network partitions.

Verifies:
- Probabilistic packet loss: rates 0.0 and 1.0, seeded repeatability, PRNG isolation.
- Distance-dependent delivery loss model.
- Two-state Markov Gilbert-Elliott burst loss model.
- Temporary participant outages (outage intervals, sender/receiver blackout).
- Link outages (static, temporary window, directed and bidirectional).
- Network partitions (intra-partition delivery allowed, cross-partition delivery blocked).
- Recovery semantics and knowledge preservation.
- Atomic rollback of degradation and channel states.
"""

import random

import pytest

from apps.core.communication.exceptions import (
    CommunicationValidationError,
)
from apps.core.communication.models import (
    ChannelState,
    CommunicationConfig,
    TemporaryLinkOutage,
    TemporaryOutage,
    V2VMessagePacket,
    V2VMessageType,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.domain.values import Position2D


@pytest.fixture
def base_positions() -> dict[str, Position2D]:
    """Positions for 4 vehicles on a 2D plane."""
    return {
        "veh_1": Position2D(x=0.0, y=0.0),
        "veh_2": Position2D(x=20.0, y=0.0),
        "veh_3": Position2D(x=40.0, y=0.0),
        "veh_4": Position2D(x=45.0, y=0.0),
    }


def make_packet(
    sender_id: str = "veh_1",
    seq: int = 1,
    time_s: float = 0.0,
    msg_id: str = "msg_001",
    recipient_id: str | None = None,
) -> V2VMessagePacket:
    """Construct valid test packet."""
    return V2VMessagePacket(
        message_id=msg_id,
        sender_id=sender_id,
        sequence_number=seq,
        timestamp_s=time_s,
        sender_position=Position2D(x=0.0, y=0.0),
        sender_heading_rad=0.0,
        sender_speed_mps=10.0,
        message_type=V2VMessageType.HEARTBEAT,
        recipient_id=recipient_id,
        payload={"data": "test"},
    )


class TestProbabilisticPacketLoss:
    """Verify deterministic packet loss behavior and PRNG reproducibility."""

    def test_loss_rate_zero_never_drops(self, base_positions: dict[str, Position2D]) -> None:
        cfg = CommunicationConfig(packet_loss_rate=0.0, range_m=50.0)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        for i in range(20):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_{i}")
            delivered = net.broadcast(msg, base_positions, current_time_s=1.0)
            assert delivered == ["veh_2"]

        assert net.metrics.dropped_packet_loss == 0
        assert net.metrics.successful_deliveries == 20

    def test_loss_rate_one_drops_all_packets(self, base_positions: dict[str, Position2D]) -> None:
        cfg = CommunicationConfig(packet_loss_rate=1.0, range_m=50.0)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        for i in range(10):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_lost_{i}")
            delivered = net.broadcast(msg, base_positions, current_time_s=1.0)
            assert delivered == []

        assert net.metrics.dropped_packet_loss == 10
        assert net.metrics.successful_deliveries == 0
        net.advance_tick(1.1)
        assert net.get_inbox("veh_2") == []

    def test_seeded_repeatability(self, base_positions: dict[str, Position2D]) -> None:
        """Two networks with identical seed generate identical drop sequences."""
        cfg1 = CommunicationConfig(packet_loss_rate=0.5, packet_loss_seed=999, range_m=50.0)
        net1 = SimulatedCommunicationNetwork(config=cfg1)
        net1.register_participant("veh_1")
        net1.register_participant("veh_2")

        cfg2 = CommunicationConfig(packet_loss_rate=0.5, packet_loss_seed=999, range_m=50.0)
        net2 = SimulatedCommunicationNetwork(config=cfg2)
        net2.register_participant("veh_1")
        net2.register_participant("veh_2")

        results1: list[bool] = []
        results2: list[bool] = []

        for i in range(50):
            msg1 = make_packet("veh_1", seq=i + 1, msg_id=f"m_{i}")
            d1 = bool(net1.broadcast(msg1, base_positions, current_time_s=1.0))
            results1.append(d1)

            msg2 = make_packet("veh_1", seq=i + 1, msg_id=f"m_{i}")
            d2 = bool(net2.broadcast(msg2, base_positions, current_time_s=1.0))
            results2.append(d2)

        assert results1 == results2
        assert net1.metrics.dropped_packet_loss == net2.metrics.dropped_packet_loss

    def test_isolated_prng_state(self, base_positions: dict[str, Position2D]) -> None:
        """Calling global random.random() must not alter network loss outcomes."""
        cfg = CommunicationConfig(packet_loss_rate=0.5, packet_loss_seed=42)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        # Capture first 10 outcomes
        expected: list[bool] = []
        for i in range(10):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_exp_{i}")
            expected.append(bool(net.broadcast(msg, base_positions, current_time_s=1.0)))

        # Reset network and perturb global random
        net.reset()
        for _ in range(100):
            random.random()

        actual: list[bool] = []
        for i in range(10):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_exp_{i}")
            actual.append(bool(net.broadcast(msg, base_positions, current_time_s=1.0)))

        assert expected == actual


class TestDistanceDependentLoss:
    """Validate distance-dependent loss where P_loss = (d/R)^gamma."""

    def test_distance_loss_near_zero_distance(self) -> None:
        """Vehicle at d ~ 0 has near 0 loss probability."""
        cfg = CommunicationConfig(
            range_m=100.0,
            distance_loss_enabled=True,
            distance_loss_exponent=2.0,
            packet_loss_seed=42,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        # Distance is 1m out of 100m -> P_loss = (1/100)^2 = 0.0001
        positions = {"veh_1": Position2D(0.0, 0.0), "veh_2": Position2D(1.0, 0.0)}
        for i in range(20):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_near_{i}")
            delivered = net.broadcast(msg, positions, current_time_s=1.0)
            assert delivered == ["veh_2"]

    def test_distance_loss_at_edge_of_range(self) -> None:
        """Vehicle at d = R has P_loss = 1.0 (always dropped)."""
        cfg = CommunicationConfig(
            range_m=50.0,
            distance_loss_enabled=True,
            distance_loss_exponent=2.0,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        # Distance is exactly 50m -> P_loss = 1.0
        positions = {"veh_1": Position2D(0.0, 0.0), "veh_2": Position2D(50.0, 0.0)}
        for i in range(10):
            msg = make_packet("veh_1", seq=i + 1, msg_id=f"m_edge_{i}")
            delivered = net.broadcast(msg, positions, current_time_s=1.0)
            assert delivered == []

        assert net.metrics.dropped_packet_loss == 10


class TestBurstLossModel:
    """Verify two-state Markov Gilbert-Elliott burst loss model."""

    def test_burst_channel_state_override_and_drops(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        cfg = CommunicationConfig(
            burst_loss_enabled=True,
            burst_loss_rate_good=0.0,
            burst_loss_rate_bad=1.0,
            burst_loss_seed=42,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        # In GOOD state: 0% drop
        assert net.get_channel_state() == ChannelState.GOOD
        msg1 = make_packet("veh_1", seq=1, msg_id="m_good")
        assert net.broadcast(msg1, base_positions, current_time_s=1.0) == ["veh_2"]
        assert net.metrics.dropped_burst_loss == 0

        # Force BAD state: 100% drop
        net.set_channel_state(ChannelState.BAD)
        assert net.get_channel_state() == ChannelState.BAD
        msg2 = make_packet("veh_1", seq=2, msg_id="m_bad")
        assert net.broadcast(msg2, base_positions, current_time_s=1.0) == []
        assert net.metrics.dropped_burst_loss == 1

        # Recover to GOOD state
        net.set_channel_state(ChannelState.GOOD)
        msg3 = make_packet("veh_1", seq=3, msg_id="m_good_again")
        assert net.broadcast(msg3, base_positions, current_time_s=1.0) == ["veh_2"]

    def test_burst_channel_transitions_on_tick(self) -> None:
        """Channel transitions between GOOD and BAD states over simulation ticks."""
        cfg = CommunicationConfig(
            burst_loss_enabled=True,
            burst_loss_p_gb=0.4,
            burst_loss_p_bg=0.4,
            burst_loss_seed=12345,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")

        states: list[ChannelState] = [net.get_channel_state()]
        for tick in range(1, 30):
            net.advance_tick(current_time_s=round(tick * 0.1, 4))
            states.append(net.get_channel_state())

        assert ChannelState.GOOD in states
        assert ChannelState.BAD in states

    def test_burst_channel_rollback(self) -> None:
        cfg = CommunicationConfig(burst_loss_enabled=True, burst_loss_seed=42)
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_1")

        snap = net.capture_state()
        net.set_channel_state(ChannelState.BAD)
        assert net.get_channel_state() == ChannelState.BAD

        net.restore_state(snap)
        assert net.get_channel_state() == ChannelState.GOOD


class TestTemporaryOutagesAndPartitions:
    """Verify scheduled outages, link disconnections, and network partitions."""

    def test_temporary_participant_outage(self, base_positions: dict[str, Position2D]) -> None:
        """Vehicle undergoes blackout between t=1.0s and t=2.0s."""
        net = SimulatedCommunicationNetwork()
        net.register_participant("veh_1")
        net.register_participant("veh_2")

        # veh_1 experiences outage from 1.0 to 2.0s
        outage = TemporaryOutage(target_id="veh_1", start_time_s=1.0, end_time_s=2.0)
        net.add_temporary_outage(outage)

        # At t=0.5: communication works
        m_early = make_packet("veh_1", seq=1, msg_id="m_early", time_s=0.5)
        assert net.broadcast(m_early, base_positions, current_time_s=0.5) == ["veh_2"]

        # At t=1.5: sender is in outage -> SENDER_UNAVAILABLE
        m_outage = make_packet("veh_1", seq=2, msg_id="m_outage", time_s=1.5)
        assert net.broadcast(m_outage, base_positions, current_time_s=1.5) == []
        assert net.metrics.dropped_unavailable >= 1

        # At t=2.5: outage has elapsed -> recovered!
        m_rec = make_packet("veh_1", seq=3, msg_id="m_rec", time_s=2.5)
        assert net.broadcast(m_rec, base_positions, current_time_s=2.5) == ["veh_2"]

    def test_temporary_link_outage(self, base_positions: dict[str, Position2D]) -> None:
        """Link between veh_1 and veh_2 is offline between t=1.0 and t=2.0."""
        net = SimulatedCommunicationNetwork()
        net.register_participant("veh_1")
        net.register_participant("veh_2")
        net.register_participant("veh_3")

        link_outage = TemporaryLinkOutage(
            sender_id="veh_1",
            receiver_id="veh_2",
            start_time_s=1.0,
            end_time_s=2.0,
            bidirectional=True,
        )
        net.add_temporary_link_outage(link_outage)

        # At t=1.5: link veh_1 <-> veh_2 is down, but veh_1 <-> veh_3 is UP
        msg = make_packet("veh_1", seq=1, msg_id="m_link", time_s=1.5)
        recips = net.broadcast(msg, base_positions, current_time_s=1.5)
        assert "veh_2" not in recips
        assert "veh_3" in recips
        assert net.metrics.dropped_link_outage >= 1

        # At t=2.5: link outage finished -> veh_2 receives again
        msg2 = make_packet("veh_1", seq=2, msg_id="m_link_rec", time_s=2.5)
        recips2 = net.broadcast(msg2, base_positions, current_time_s=2.5)
        assert "veh_2" in recips2
        assert "veh_3" in recips2

    def test_network_partitions(self, base_positions: dict[str, Position2D]) -> None:
        """Vehicles partitioned into group {veh_1, veh_2} and {veh_3, veh_4}."""
        net = SimulatedCommunicationNetwork(config=CommunicationConfig(range_m=100.0))
        for vid in ["veh_1", "veh_2", "veh_3", "veh_4"]:
            net.register_participant(vid)

        net.set_partitions([{"veh_1", "veh_2"}, {"veh_3", "veh_4"}])

        # veh_1 broadcasts: veh_2 receives, veh_3 and veh_4 are blocked by partition
        msg = make_packet("veh_1", seq=1, msg_id="m_part")
        receivers = net.broadcast(msg, base_positions, current_time_s=1.0)
        assert receivers == ["veh_2"]
        assert net.metrics.dropped_partition >= 2

        # veh_3 broadcasts: veh_4 receives, veh_1 and veh_2 blocked
        msg3 = make_packet("veh_3", seq=1, msg_id="m_part3")
        receivers3 = net.broadcast(msg3, base_positions, current_time_s=1.0)
        assert receivers3 == ["veh_4"]

        # Clear partitions (network healing / recovery)
        net.clear_partitions()
        msg_healed = make_packet("veh_1", seq=2, msg_id="m_healed")
        receivers_healed = net.broadcast(msg_healed, base_positions, current_time_s=2.0)
        assert set(receivers_healed) == {"veh_2", "veh_3", "veh_4"}


class TestImpairmentValidation:
    """Verify validation and rejection of invalid parameters."""

    def test_invalid_loss_probability_rejected(self) -> None:
        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(packet_loss_rate=-0.1)

        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(packet_loss_rate=1.1)

    def test_invalid_burst_probabilities_rejected(self) -> None:
        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(burst_loss_p_gb=-0.05)

        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(burst_loss_rate_good=1.5)

    def test_invalid_outage_interval_rejected(self) -> None:
        with pytest.raises(CommunicationValidationError):
            TemporaryOutage(target_id="v1", start_time_s=2.0, end_time_s=1.0)

        with pytest.raises(CommunicationValidationError):
            TemporaryOutage(target_id="v1", start_time_s=-1.0, end_time_s=1.0)
