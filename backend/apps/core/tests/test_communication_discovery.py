"""Unit tests for spatial peer discovery in V2V communication."""

import pytest

from apps.core.communication.discovery import SpatialPeerDiscovery, brute_force_reference
from apps.core.communication.exceptions import InvalidRangeError
from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.simulation.models import VehicleSnapshot, WorldSnapshot


class TestSpatialPeerDiscovery:
    """Test suite for spatial peer discovery rules and invariants."""

    def test_default_initialization_and_range(self):
        disc = SpatialPeerDiscovery()
        assert disc.range_m == 50.0
        assert disc.max_peers is None

    def test_custom_initialization(self):
        disc = SpatialPeerDiscovery(range_m=75.5, max_peers=3)
        assert disc.range_m == 75.5
        assert disc.max_peers == 3

    @pytest.mark.parametrize("invalid_range", [0.0, -10.0, -0.01, float("nan"), float("inf"), "50"])
    def test_invalid_range_raises(self, invalid_range):
        with pytest.raises(InvalidRangeError):
            SpatialPeerDiscovery(range_m=invalid_range)

    @pytest.mark.parametrize("invalid_max_peers", [0, -1, 1.5, "five", True])
    def test_invalid_max_peers_raises(self, invalid_max_peers):
        with pytest.raises(ValueError):
            SpatialPeerDiscovery(range_m=50.0, max_peers=invalid_max_peers)

    def test_self_exclusion_rule(self):
        disc = SpatialPeerDiscovery(range_m=100.0)
        sender_pos = Position2D(x=10.0, y=10.0)
        candidates = {
            "veh_sender": sender_pos,
            "veh_other": Position2D(x=15.0, y=10.0),
        }
        peers = disc.find_peers(
            sender_id="veh_sender",
            sender_position=sender_pos,
            candidates=candidates,
        )
        assert "veh_sender" not in peers
        assert peers == ["veh_other"]

    def test_exact_boundary_inclusion(self):
        """A peer at exactly distance d == R must be included."""
        disc = SpatialPeerDiscovery(range_m=50.0)
        sender_pos = Position2D(x=0.0, y=0.0)
        candidates = {
            "veh_boundary": Position2D(x=50.0, y=0.0),  # d = 50.0 == R
            "veh_inside": Position2D(x=30.0, y=0.0),    # d = 30.0 < R
            "veh_outside": Position2D(x=50.001, y=0.0), # d > R
        }
        peers = disc.find_peers("veh_sender", sender_pos, candidates)
        assert "veh_inside" in peers
        assert "veh_boundary" in peers
        assert "veh_outside" not in peers

    def test_deterministic_ordering_by_distance_then_id(self):
        """Peers must be sorted by distance ascending, ties broken by vehicle ID alphabetically."""
        disc = SpatialPeerDiscovery(range_m=100.0)
        sender_pos = Position2D(x=0.0, y=0.0)
        candidates = {
            "veh_z": Position2D(x=10.0, y=0.0),  # d = 10
            "veh_a": Position2D(x=10.0, y=0.0),  # d = 10 (same distance as z, tie break 'a' < 'z')
            "veh_m": Position2D(x=5.0, y=0.0),   # d = 5 (closest)
            "veh_far": Position2D(x=40.0, y=0.0),# d = 40
        }
        peers = disc.find_peers("veh_sender", sender_pos, candidates)
        assert peers == ["veh_m", "veh_a", "veh_z", "veh_far"]

    def test_max_peers_clamping(self):
        disc = SpatialPeerDiscovery(range_m=100.0, max_peers=2)
        sender_pos = Position2D(x=0.0, y=0.0)
        candidates = {
            "veh_1": Position2D(x=10.0, y=0.0),
            "veh_2": Position2D(x=20.0, y=0.0),
            "veh_3": Position2D(x=30.0, y=0.0),
        }
        peers = disc.find_peers("veh_sender", sender_pos, candidates)
        assert len(peers) == 2
        assert peers == ["veh_1", "veh_2"]

    def test_empty_candidates_returns_empty_list(self):
        disc = SpatialPeerDiscovery(range_m=50.0)
        peers = disc.find_peers("veh_sender", Position2D(x=0.0, y=0.0), {})
        assert peers == []

    def test_candidates_with_invalid_positions_skipped(self):
        disc = SpatialPeerDiscovery(range_m=50.0)
        sender_pos = Position2D(x=0.0, y=0.0)
        candidates = {
            "veh_valid": Position2D(x=10.0, y=0.0),
            "veh_tuple": (10.0, 0.0),  # type: ignore[dict-item]
            "veh_none": None,           # type: ignore[dict-item]
        }
        peers = disc.find_peers("veh_sender", sender_pos, candidates)
        assert peers == ["veh_valid"]

    def test_extreme_coordinate_values(self):
        disc = SpatialPeerDiscovery(range_m=50.0)
        sender_pos = Position2D(x=1_000_000.0, y=2_000_000.0)
        candidates = {
            "veh_close": Position2D(x=1_000_010.0, y=2_000_010.0),  # d = ~14.14m <= 50m
            "veh_far": Position2D(x=1_000_100.0, y=2_000_000.0),    # d = 100m > 50m
        }
        peers = disc.find_peers("veh_sender", sender_pos, candidates)
        assert peers == ["veh_close"]

    def test_position_movement_updates_peers(self):
        disc = SpatialPeerDiscovery(range_m=20.0)
        sender_pos = Position2D(x=0.0, y=0.0)

        # Initially at x=15 (in range)
        candidates = {"veh_moving": Position2D(x=15.0, y=0.0)}
        assert disc.find_peers("veh_sender", sender_pos, candidates) == ["veh_moving"]

        # Moves to x=25 (out of range)
        candidates["veh_moving"] = Position2D(x=25.0, y=0.0)
        assert disc.find_peers("veh_sender", sender_pos, candidates) == []

    def test_brute_force_reference_parity(self):
        """Verify SpatialPeerDiscovery matches brute_force_reference on arbitrary positions."""
        disc = SpatialPeerDiscovery(range_m=45.0, max_peers=3)
        sender_pos = Position2D(x=25.0, y=30.0)
        candidates = {
            "v1": Position2D(x=30.0, y=35.0),
            "v2": Position2D(x=10.0, y=10.0),
            "v3": Position2D(x=60.0, y=40.0),
            "v4": Position2D(x=20.0, y=25.0),
            "v5": Position2D(x=100.0, y=100.0),
            "sender": sender_pos,
        }

        discovered = disc.find_peers("sender", sender_pos, candidates)
        ref = brute_force_reference("sender", sender_pos, candidates, range_m=45.0, max_peers=3)

        assert discovered == ref

    def test_find_peers_from_snapshot(self):
        disc = SpatialPeerDiscovery(range_m=30.0)
        snap1 = VehicleSnapshot(
            vehicle_id="v1",
            state=VehicleState.EN_ROUTE,
            position=Position2D(x=0.0, y=0.0),
            heading_rad=0.0,
            speed_mps=10.0,
            current_edge_id=None,
            current_node_id=None,
            distance_along_segment_m=0.0,
            remaining_route_distance_m=100.0,
        )
        snap2 = VehicleSnapshot(
            vehicle_id="v2",
            state=VehicleState.EN_ROUTE,
            position=Position2D(x=20.0, y=0.0),
            heading_rad=0.0,
            speed_mps=10.0,
            current_edge_id=None,
            current_node_id=None,
            distance_along_segment_m=0.0,
            remaining_route_distance_m=100.0,
        )
        world_snap = WorldSnapshot(
            tick=1,
            elapsed_time_s=0.1,
            time_step_s=0.1,
            is_paused=False,
            agent_count=2,
            vehicles={"v1": snap1, "v2": snap2},
            metadata={},
        )
        peers = disc.find_peers_from_snapshot("v1", world_snap)
        assert peers == ["v2"]

    def test_find_peers_from_snapshot_unknown_sender_raises(self):
        disc = SpatialPeerDiscovery(range_m=30.0)
        world_snap = WorldSnapshot(
            tick=1,
            elapsed_time_s=0.1,
            time_step_s=0.1,
            is_paused=False,
            agent_count=0,
            vehicles={},
            metadata={},
        )
        with pytest.raises(KeyError):
            disc.find_peers_from_snapshot("nonexistent", world_snap)
