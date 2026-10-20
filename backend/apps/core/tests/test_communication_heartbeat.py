"""Unit and timing tests for Phase 12 Heartbeat and Neighbor Loss Detection."""

from apps.core.communication.models import (
    NeighborStatus,
    StaleNeighborPolicy,
    V2VMessagePacket,
)
from apps.core.communication.neighbors import (
    NeighborManager,
    NeighborMetrics,
    NeighborTable,
)
from apps.core.domain.values import Position2D


def _packet(
    sender_id: str = "peer_1",
    seq: int = 1,
    time_s: float = 1.0,
    msg_id: str = "msg_1",
) -> V2VMessagePacket:
    return V2VMessagePacket(
        message_id=msg_id,
        sender_id=sender_id,
        sequence_number=seq,
        timestamp_s=time_s,
        sender_position=Position2D(x=10.0, y=10.0),
        sender_heading_rad=0.0,
        sender_speed_mps=10.0,
    )


class TestHeartbeatTimeoutAndLoss:
    """Test suite for exact heartbeat timeout boundaries and stale policies."""

    def test_exact_timeout_boundary(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        # Heartbeat at t = 1.0s, timeout = 0.5s
        p = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        timeout_s = 0.5

        # Just before timeout (1.499s): elapsed = 0.499s < 0.5s -> Remains ACTIVE
        table.perform_maintenance(
            current_time_s=1.499,
            timeout_s=timeout_s,
            grace_period_s=1.0,
            policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            metrics=metrics,
        )
        assert table.get_neighbor("peer_1").status == NeighborStatus.ACTIVE
        assert metrics.neighbors_marked_stale == 0

        # Exact boundary (1.500s): elapsed = 0.5s >= 0.5s -> Transitions to STALE
        table.perform_maintenance(
            current_time_s=1.500,
            timeout_s=timeout_s,
            grace_period_s=1.0,
            policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            metrics=metrics,
        )
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE
        assert metrics.neighbors_marked_stale == 1

    def test_grace_period_removal_boundary(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        # Heartbeat at t = 1.0s, timeout = 0.5s, grace = 1.0s (removal at 2.5s)
        p = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        timeout_s = 0.5
        grace_s = 1.0

        # Transition to stale at 1.5s
        table.perform_maintenance(
            current_time_s=1.5,
            timeout_s=timeout_s,
            grace_period_s=grace_s,
            policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            metrics=metrics,
        )
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE

        # Just before grace expiration (2.499s): remains STALE in table
        table.perform_maintenance(
            current_time_s=2.499,
            timeout_s=timeout_s,
            grace_period_s=grace_s,
            policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            metrics=metrics,
        )
        assert table.has_neighbor("peer_1") is True
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE
        assert metrics.neighbors_removed == 0

        # Exact removal boundary (2.500s): removed from table
        table.perform_maintenance(
            current_time_s=2.500,
            timeout_s=timeout_s,
            grace_period_s=grace_s,
            policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            metrics=metrics,
        )
        assert table.has_neighbor("peer_1") is False
        assert table.count == 0
        assert metrics.neighbors_removed == 1

    def test_policy_remove_immediately(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        p = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Timeout reached: immediately removed without STALE phase
        table.perform_maintenance(
            current_time_s=1.5,
            timeout_s=0.5,
            policy=StaleNeighborPolicy.REMOVE_IMMEDIATELY,
            metrics=metrics,
        )
        assert table.has_neighbor("peer_1") is False
        assert metrics.neighbors_marked_stale == 0
        assert metrics.neighbors_removed == 1

    def test_policy_mark_stale_retains_indefinitely(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        p = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Reach timeout -> marked stale
        table.perform_maintenance(
            current_time_s=1.5,
            timeout_s=0.5,
            policy=StaleNeighborPolicy.MARK_STALE,
            metrics=metrics,
        )
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE

        # Far into the future -> still retained as stale
        table.perform_maintenance(
            current_time_s=100.0,
            timeout_s=0.5,
            policy=StaleNeighborPolicy.MARK_STALE,
            metrics=metrics,
        )
        assert table.has_neighbor("peer_1") is True
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE
        assert metrics.neighbors_removed == 0

    def test_fresh_heartbeat_restores_stale_neighbor(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        # Initial heartbeat at 1.0s
        p1 = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Becomes stale at 1.6s
        table.perform_maintenance(
            current_time_s=1.6,
            timeout_s=0.5,
            grace_period_s=1.0,
            metrics=metrics,
        )
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE

        # Fresh heartbeat arrives at 1.8s (seq 2 > 1)
        p2 = _packet(sender_id="peer_1", seq=2, time_s=1.8, msg_id="p2")
        restored = table.add_or_refresh(
            p2, Position2D(x=0.0, y=0.0), current_time_s=1.8, metrics=metrics
        )
        assert restored is True
        rec = table.get_neighbor("peer_1")
        assert rec.status == NeighborStatus.ACTIVE
        assert rec.last_sequence_number == 2
        assert rec.last_heartbeat_timestamp_s == 1.8
        assert rec.last_seen_timestamp_s == 1.8

    def test_reconnection_after_removal(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        p1 = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Removed after 2.6s (timeout 0.5s + grace 1.0s = 1.5s -> at 2.6s elapsed is 1.6s)
        table.perform_maintenance(
            current_time_s=2.6,
            timeout_s=0.5,
            grace_period_s=1.0,
            metrics=metrics,
        )
        assert table.has_neighbor("peer_1") is False

        # Reappearance: vehicle starts broadcasting again with higher sequence
        p2 = _packet(sender_id="peer_1", seq=10, time_s=3.0, msg_id="p2")
        added = table.add_or_refresh(
            p2, Position2D(x=0.0, y=0.0), current_time_s=3.0, metrics=metrics
        )
        assert added is True
        assert table.has_neighbor("peer_1") is True
        assert table.get_neighbor("peer_1").status == NeighborStatus.ACTIVE
        assert table.get_neighbor("peer_1").last_sequence_number == 10

    def test_maintenance_idempotence(self) -> None:
        table = NeighborTable(owner_vehicle_id="host")
        metrics = NeighborMetrics()

        p1 = _packet(sender_id="peer_1", seq=1, time_s=1.0, msg_id="p1")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Call maintenance 3 times at identical simulation timestamp
        for _ in range(3):
            table.perform_maintenance(
                current_time_s=1.6,
                timeout_s=0.5,
                grace_period_s=1.0,
                metrics=metrics,
            )

        # Marked stale exactly once
        assert metrics.neighbors_marked_stale == 1
        assert table.get_neighbor("peer_1").status == NeighborStatus.STALE

    def test_neighbor_manager_maintenance_cycle(self) -> None:
        mgr = NeighborManager(heartbeat_timeout_s=0.5, stale_grace_period_s=0.5)
        mgr.register_participant("v1")
        mgr.register_participant("v2")

        # v1 receives message from v2 at t=0.1
        p = _packet(sender_id="v2", seq=1, time_s=0.1, msg_id="m1")
        mgr.process_inbox("v1", [p], Position2D(x=0.0, y=0.0), current_time_s=0.1)

        assert mgr.get_table("v1").get_neighbor("v2").status == NeighborStatus.ACTIVE

        # t=0.7s: 0.7 - 0.1 = 0.6s >= 0.5s -> v2 should be marked stale
        mgr.perform_maintenance(current_time_s=0.7)
        assert mgr.get_table("v1").get_neighbor("v2").status == NeighborStatus.STALE
        assert mgr.metrics.update_cycles_executed == 1
        assert mgr.metrics.neighbors_marked_stale == 1

        # t=1.2s: 1.2 - 0.1 = 1.1s >= 1.0s (0.5+0.5) -> v2 should be removed
        mgr.perform_maintenance(current_time_s=1.2)
        assert mgr.get_table("v1").has_neighbor("v2") is False
        assert mgr.metrics.update_cycles_executed == 2
        assert mgr.metrics.neighbors_removed == 1
