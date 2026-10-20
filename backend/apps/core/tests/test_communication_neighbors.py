"""Unit tests for Phase 12 NeighborRecord, NeighborTable, NeighborManager, and metrics."""

import pytest

from apps.core.communication.exceptions import (
    CommunicationValidationError,
    InvalidNeighborDataError,
    NeighborNotFoundError,
    SelfNeighborError,
)
from apps.core.communication.models import (
    CommunicationConfig,
    NeighborStatus,
    StaleNeighborPolicy,
    V2VMessagePacket,
)
from apps.core.communication.neighbors import (
    NeighborManager,
    NeighborMetrics,
    NeighborRecord,
    NeighborTable,
    NeighborTableSnapshot,
)
from apps.core.domain.values import Position2D


def _create_packet(
    sender_id: str = "v1",
    seq: int = 1,
    time_s: float = 1.0,
    x: float = 10.0,
    y: float = 20.0,
    speed: float = 15.0,
    heading: float = 0.5,
    expiry_s: float = 10.0,
    msg_id: str = "msg-1",
) -> V2VMessagePacket:
    return V2VMessagePacket(
        message_id=msg_id,
        sender_id=sender_id,
        sequence_number=seq,
        timestamp_s=time_s,
        sender_position=Position2D(x=x, y=y),
        sender_heading_rad=heading,
        sender_speed_mps=speed,
        expiry_timestamp_s=expiry_s,
    )


class TestNeighborRecord:
    """Test suite for immutable NeighborRecord contract and invariants."""

    def test_valid_record_creation(self) -> None:
        rec = NeighborRecord(
            vehicle_id="veh_b",
            last_position=Position2D(x=10.0, y=20.0),
            last_distance_m=25.0,
            last_speed_mps=12.5,
            last_heading_rad=1.57,
            last_seen_timestamp_s=5.0,
            last_heartbeat_timestamp_s=5.0,
            last_sequence_number=3,
            status=NeighborStatus.ACTIVE,
            last_message_id="msg_42",
        )
        assert rec.vehicle_id == "veh_b"
        assert rec.last_distance_m == 25.0
        assert rec.last_speed_mps == 12.5
        assert rec.status == NeighborStatus.ACTIVE
        assert rec.last_message_id == "msg_42"

    def test_invalid_fields_raise(self) -> None:
        pos = Position2D(x=0.0, y=0.0)
        # Empty vehicle_id
        with pytest.raises(InvalidNeighborDataError):
            NeighborRecord(
                vehicle_id="",
                last_position=pos,
                last_distance_m=1.0,
                last_speed_mps=1.0,
                last_heading_rad=0.0,
                last_seen_timestamp_s=1.0,
                last_heartbeat_timestamp_s=1.0,
                last_sequence_number=1,
            )

        # Negative distance
        with pytest.raises(InvalidNeighborDataError):
            NeighborRecord(
                vehicle_id="v1",
                last_position=pos,
                last_distance_m=-5.0,
                last_speed_mps=1.0,
                last_heading_rad=0.0,
                last_seen_timestamp_s=1.0,
                last_heartbeat_timestamp_s=1.0,
                last_sequence_number=1,
            )

        # Negative speed
        with pytest.raises(InvalidNeighborDataError):
            NeighborRecord(
                vehicle_id="v1",
                last_position=pos,
                last_distance_m=5.0,
                last_speed_mps=-1.0,
                last_heading_rad=0.0,
                last_seen_timestamp_s=1.0,
                last_heartbeat_timestamp_s=1.0,
                last_sequence_number=1,
            )

        # Negative sequence number
        with pytest.raises(InvalidNeighborDataError):
            NeighborRecord(
                vehicle_id="v1",
                last_position=pos,
                last_distance_m=5.0,
                last_speed_mps=1.0,
                last_heading_rad=0.0,
                last_seen_timestamp_s=1.0,
                last_heartbeat_timestamp_s=1.0,
                last_sequence_number=-1,
            )

    def test_time_until_expiration(self) -> None:
        rec = NeighborRecord(
            vehicle_id="v1",
            last_position=Position2D(x=0.0, y=0.0),
            last_distance_m=10.0,
            last_speed_mps=5.0,
            last_heading_rad=0.0,
            last_seen_timestamp_s=2.0,
            last_heartbeat_timestamp_s=2.0,
            last_sequence_number=1,
        )
        # Timeout 0.5s: expires at 2.5s. At current_time=2.2s -> 0.3s remaining
        assert pytest.approx(rec.time_until_expiration(current_time_s=2.2, timeout_s=0.5)) == 0.3
        # At current_time=2.6s -> 0.0s remaining
        assert rec.time_until_expiration(current_time_s=2.6, timeout_s=0.5) == 0.0

    def test_serialization_round_trip(self) -> None:
        rec = NeighborRecord(
            vehicle_id="v_x",
            last_position=Position2D(x=12.3456, y=78.9012),
            last_distance_m=15.1234,
            last_speed_mps=8.5,
            last_heading_rad=0.785398,
            last_seen_timestamp_s=3.5,
            last_heartbeat_timestamp_s=3.4,
            last_sequence_number=7,
            status=NeighborStatus.STALE,
            last_message_id="msg_99",
        )
        d = rec.to_dict()
        assert d["vehicle_id"] == "v_x"
        assert d["status"] == "stale"
        restored = NeighborRecord.from_dict(d)
        assert restored == rec


class TestNeighborTable:
    """Test suite for per-vehicle NeighborTable operations and invariants."""

    def test_empty_table(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        assert table.owner_vehicle_id == "host_1"
        assert table.count == 0
        assert table.get_all_neighbors() == []
        assert table.get_active_neighbors() == []
        assert table.get_stale_neighbors() == []
        assert table.get_known_ids() == []

    def test_self_neighbor_rejection(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        packet = _create_packet(sender_id="host_1", msg_id="self_msg")
        with pytest.raises(SelfNeighborError):
            table.add_or_refresh(
                message=packet,
                observer_position=Position2D(x=0.0, y=0.0),
                current_time_s=1.0,
            )

    def test_add_and_retrieve_neighbor(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()
        packet = _create_packet(
            sender_id="peer_a",
            seq=1,
            time_s=2.0,
            x=30.0,
            y=40.0,
            speed=10.0,
            heading=1.0,
            msg_id="pkt_1",
        )
        added = table.add_or_refresh(
            message=packet,
            observer_position=Position2D(x=0.0, y=0.0),
            current_time_s=2.1,
            metrics=metrics,
        )
        assert added is True
        assert table.count == 1
        assert table.has_neighbor("peer_a") is True
        assert metrics.new_neighbors_discovered == 1
        assert metrics.heartbeats_received == 1

        rec = table.get_neighbor("peer_a")
        assert rec.vehicle_id == "peer_a"
        assert pytest.approx(rec.last_distance_m) == 50.0  # sqrt(30^2 + 40^2)
        assert rec.last_speed_mps == 10.0
        assert rec.last_seen_timestamp_s == 2.1
        assert rec.last_heartbeat_timestamp_s == 2.0
        assert rec.status == NeighborStatus.ACTIVE

    def test_get_nonexistent_neighbor_raises(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        with pytest.raises(NeighborNotFoundError):
            table.get_neighbor("peer_missing")

    def test_refresh_existing_neighbor(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()

        p1 = _create_packet(sender_id="peer_a", seq=1, time_s=1.0, x=10.0, y=0.0, msg_id="m1")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=1.1, metrics=metrics)

        p2 = _create_packet(
            sender_id="peer_a", seq=2, time_s=1.5, x=15.0, y=0.0, speed=20.0, msg_id="m2"
        )
        refreshed = table.add_or_refresh(
            p2, Position2D(x=0.0, y=0.0), current_time_s=1.6, metrics=metrics
        )

        assert refreshed is True
        assert table.count == 1
        assert metrics.new_neighbors_discovered == 1
        assert metrics.neighbor_records_refreshed == 1
        assert metrics.heartbeats_received == 2

        rec = table.get_neighbor("peer_a")
        assert rec.last_sequence_number == 2
        assert rec.last_distance_m == 15.0
        assert rec.last_speed_mps == 20.0
        assert rec.last_seen_timestamp_s == 1.6

    def test_older_or_duplicate_sequence_number_rejected(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()

        p1 = _create_packet(sender_id="peer_a", seq=5, time_s=2.0, msg_id="m5")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=2.0, metrics=metrics)

        # Older sequence number
        p_old = _create_packet(sender_id="peer_a", seq=4, time_s=1.9, msg_id="m4")
        accepted_old = table.add_or_refresh(
            p_old, Position2D(x=0.0, y=0.0), current_time_s=2.1, metrics=metrics
        )
        assert accepted_old is False
        assert metrics.duplicate_or_out_of_order_rejected == 1
        assert table.get_neighbor("peer_a").last_sequence_number == 5

        # Same sequence number
        p_same = _create_packet(sender_id="peer_a", seq=5, time_s=2.1, msg_id="m5_dupe")
        accepted_same = table.add_or_refresh(
            p_same, Position2D(x=0.0, y=0.0), current_time_s=2.2, metrics=metrics
        )
        assert accepted_same is False
        assert metrics.duplicate_or_out_of_order_rejected == 2

    def test_duplicate_message_id_rejected(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()

        p = _create_packet(sender_id="peer_a", seq=1, msg_id="unique_id")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        # Same packet presented again
        accepted = table.add_or_refresh(
            p, Position2D(x=0.0, y=0.0), current_time_s=1.1, metrics=metrics
        )
        assert accepted is False
        assert metrics.duplicate_or_out_of_order_rejected == 1

    def test_expired_message_rejected(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()

        p = _create_packet(sender_id="peer_a", seq=1, time_s=1.0, expiry_s=1.5, msg_id="exp_msg")
        accepted = table.add_or_refresh(
            p, Position2D(x=0.0, y=0.0), current_time_s=2.0, metrics=metrics
        )
        assert accepted is False
        assert table.count == 0
        assert metrics.invalid_or_expired_heartbeats_rejected == 1

    def test_deterministic_sorting(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        # Add out of sorted order
        for vid in ["peer_z", "peer_a", "peer_m", "peer_b"]:
            p = _create_packet(sender_id=vid, msg_id=f"msg_{vid}")
            table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0)

        assert table.get_known_ids() == ["peer_a", "peer_b", "peer_m", "peer_z"]
        enumerated_ids = [rec.vehicle_id for rec in table.get_all_neighbors()]
        assert enumerated_ids == ["peer_a", "peer_b", "peer_m", "peer_z"]

    def test_mark_stale_and_removal(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        metrics = NeighborMetrics()
        p = _create_packet(sender_id="peer_a", msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0, metrics=metrics)

        assert len(table.get_active_neighbors()) == 1
        assert len(table.get_stale_neighbors()) == 0

        table.mark_stale("peer_a", metrics=metrics)
        assert len(table.get_active_neighbors()) == 0
        assert len(table.get_stale_neighbors()) == 1
        assert metrics.neighbors_marked_stale == 1

        removed = table.remove_neighbor("peer_a", metrics=metrics)
        assert removed is not None
        assert removed.vehicle_id == "peer_a"
        assert table.count == 0
        assert metrics.neighbors_removed == 1

    def test_immutable_snapshot_isolation(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        p = _create_packet(sender_id="peer_a", msg_id="p1")
        table.add_or_refresh(p, Position2D(x=0.0, y=0.0), current_time_s=1.0)

        snap = table.get_snapshot(current_time_s=1.0)
        assert isinstance(snap, NeighborTableSnapshot)
        assert snap.known_neighbor_ids == ("peer_a",)
        assert snap.active_neighbor_ids == ("peer_a",)
        assert snap.stale_neighbor_ids == ()

        # Mutating table does not affect returned snapshot
        table.clear()
        assert table.count == 0
        assert snap.known_neighbor_ids == ("peer_a",)

    def test_capture_and_restore_state(self) -> None:
        table = NeighborTable(owner_vehicle_id="host_1")
        p1 = _create_packet(sender_id="peer_a", seq=1, msg_id="p1")
        p2 = _create_packet(sender_id="peer_b", seq=2, msg_id="p2")
        table.add_or_refresh(p1, Position2D(x=0.0, y=0.0), current_time_s=1.0)
        table.add_or_refresh(p2, Position2D(x=0.0, y=0.0), current_time_s=1.0)
        table.mark_stale("peer_b")

        captured = table.capture_state()

        # Modify table
        table.clear()
        assert table.count == 0

        # Restore
        table.restore_state(captured)
        assert table.count == 2
        assert table.get_neighbor("peer_a").status == NeighborStatus.ACTIVE
        assert table.get_neighbor("peer_b").status == NeighborStatus.STALE


class TestNeighborManager:
    """Test suite for multi-vehicle NeighborManager coordinator."""

    def test_register_and_unregister(self) -> None:
        mgr = NeighborManager()
        mgr.register_participant("veh_1")
        mgr.register_participant("veh_2")

        assert mgr.has_table("veh_1") is True
        assert mgr.has_table("veh_2") is True
        assert mgr.has_table("veh_3") is False

        mgr.unregister_participant("veh_1")
        assert mgr.has_table("veh_1") is False

    def test_inbox_processing(self) -> None:
        mgr = NeighborManager()
        mgr.register_participant("veh_1")
        mgr.register_participant("veh_2")

        p = _create_packet(sender_id="veh_2", msg_id="msg_v2")
        accepted = mgr.process_inbox(
            vehicle_id="veh_1",
            messages=[p],
            observer_position=Position2D(x=0.0, y=0.0),
            current_time_s=1.0,
        )
        assert accepted == 1
        table = mgr.get_table("veh_1")
        assert table.has_neighbor("veh_2") is True
        assert table.get_neighbor("veh_2").status == NeighborStatus.ACTIVE

    def test_unregister_cleans_peers(self) -> None:
        mgr = NeighborManager()
        mgr.register_participant("veh_1")
        mgr.register_participant("veh_2")

        p = _create_packet(sender_id="veh_2", msg_id="msg_v2")
        mgr.process_inbox("veh_1", [p], Position2D(x=0.0, y=0.0), current_time_s=1.0)
        assert mgr.get_table("veh_1").has_neighbor("veh_2") is True

        # Unregister veh_2 -> should be purged from veh_1's table
        mgr.unregister_participant("veh_2")
        assert mgr.get_table("veh_1").has_neighbor("veh_2") is False

    def test_capture_and_restore(self) -> None:
        mgr = NeighborManager()
        mgr.register_participant("veh_1")
        p = _create_packet(sender_id="veh_2", seq=1, msg_id="m1")
        mgr.process_inbox("veh_1", [p], Position2D(x=0.0, y=0.0), current_time_s=1.0)

        state = mgr.capture_state()
        mgr.reset()
        assert mgr.get_table("veh_1").count == 0

        mgr.restore_state(state)
        assert mgr.get_table("veh_1").count == 1
        assert mgr.get_table("veh_1").has_neighbor("veh_2") is True


class TestCommunicationConfigExtensions:
    """Test validation and serialization for new Phase 12 configuration fields."""

    def test_default_config_values(self) -> None:
        cfg = CommunicationConfig()
        assert cfg.neighbor_tracking_enabled is True
        assert cfg.neighbor_update_interval_s == 0.1
        assert cfg.heartbeat_timeout_s == 0.5
        assert cfg.stale_grace_period_s == 1.0
        assert cfg.stale_policy == StaleNeighborPolicy.STALE_THEN_REMOVE

    def test_custom_valid_config(self) -> None:
        cfg = CommunicationConfig(
            neighbor_tracking_enabled=False,
            neighbor_update_interval_s=0.2,
            heartbeat_timeout_s=1.0,
            stale_grace_period_s=2.0,
            stale_policy=StaleNeighborPolicy.MARK_STALE,
        )
        assert cfg.neighbor_tracking_enabled is False
        assert cfg.neighbor_update_interval_s == 0.2
        assert cfg.heartbeat_timeout_s == 1.0
        assert cfg.stale_grace_period_s == 2.0
        assert cfg.stale_policy == StaleNeighborPolicy.MARK_STALE

    def test_invalid_config_raises(self) -> None:
        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(neighbor_update_interval_s=-0.1)

        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(heartbeat_timeout_s=0.0)

        with pytest.raises(CommunicationValidationError):
            CommunicationConfig(stale_grace_period_s=-1.0)

    def test_config_serialization_round_trip(self) -> None:
        cfg = CommunicationConfig(
            neighbor_update_interval_s=0.05,
            heartbeat_timeout_s=0.75,
            stale_grace_period_s=1.5,
            stale_policy=StaleNeighborPolicy.REMOVE_IMMEDIATELY,
        )
        d = cfg.to_dict()
        assert d["neighbor_update_interval_s"] == 0.05
        assert d["heartbeat_timeout_s"] == 0.75
        assert d["stale_policy"] == "remove_immediately"

        restored = CommunicationConfig.from_dict(d)
        assert restored == cfg
