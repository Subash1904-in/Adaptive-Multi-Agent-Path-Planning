"""Unit tests for BroadcastScheduler periodic dispatch and deterministic timing."""

import pytest

from apps.core.communication.exceptions import InvalidBroadcastIntervalError
from apps.core.communication.scheduler import BroadcastScheduler
from apps.core.domain.enums import VehicleType
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D


class TestBroadcastScheduler:
    """Test suite for BroadcastScheduler."""

    @pytest.fixture
    def sample_vehicle(self):
        return Vehicle(
            id="v_sched",
            vehicle_type=VehicleType.STANDARD,
            position=Position2D(x=10.0, y=20.0),
            speed_mps=10.0,
            heading_rad=1.0,
        )

    def test_default_initialization(self):
        sched = BroadcastScheduler()
        assert sched.broadcast_interval_s == 0.1
        assert sched.message_ttl_s == 1.0

    @pytest.mark.parametrize(
        "invalid_interval", [0.0, -0.1, -5.0, float("nan"), float("inf"), "0.1"]
    )
    def test_invalid_interval_raises(self, invalid_interval):
        with pytest.raises(InvalidBroadcastIntervalError):
            BroadcastScheduler(broadcast_interval_s=invalid_interval)

    def test_first_broadcast_immediately_due(self, sample_vehicle):
        sched = BroadcastScheduler(broadcast_interval_s=0.2)
        assert sched.is_broadcast_due("v_sched", current_time_s=0.0) is True

    def test_monotonic_sequence_numbers(self, sample_vehicle):
        sched = BroadcastScheduler(broadcast_interval_s=0.1)

        msg0 = sched.create_broadcast(sample_vehicle, current_time_s=0.0)
        assert msg0.sequence_number == 0

        # Next broadcast at t=0.1
        assert sched.is_broadcast_due("v_sched", current_time_s=0.05) is False
        assert sched.is_broadcast_due("v_sched", current_time_s=0.1) is True

        msg1 = sched.create_broadcast(sample_vehicle, current_time_s=0.1)
        assert msg1.sequence_number == 1

        # Next broadcast at t=0.2
        assert sched.is_broadcast_due("v_sched", current_time_s=0.15) is False
        assert sched.is_broadcast_due("v_sched", current_time_s=0.2) is True

        msg2 = sched.create_broadcast(sample_vehicle, current_time_s=0.2)
        assert msg2.sequence_number == 2

    def test_no_duplicate_broadcast_at_same_boundary(self, sample_vehicle):
        sched = BroadcastScheduler(broadcast_interval_s=0.1)

        # Broadcast at t=0.0
        assert sched.is_broadcast_due("v_sched", current_time_s=0.0) is True
        sched.create_broadcast(sample_vehicle, current_time_s=0.0)

        # Immediately check again at t=0.0: should NOT be due
        assert sched.is_broadcast_due("v_sched", current_time_s=0.0) is False

    def test_non_divisible_broadcast_intervals(self, sample_vehicle):
        """Scheduler handles steps that do not align perfectly with the broadcast interval."""
        sched = BroadcastScheduler(broadcast_interval_s=0.25)

        # Step dt = 0.1s
        # t=0.0: due
        assert sched.is_broadcast_due("v_sched", 0.0) is True
        sched.create_broadcast(sample_vehicle, 0.0)

        # t=0.1: not due (next is 0.25)
        assert sched.is_broadcast_due("v_sched", 0.1) is False

        # t=0.2: not due
        assert sched.is_broadcast_due("v_sched", 0.2) is False

        # t=0.3: due (0.3 >= 0.25)
        assert sched.is_broadcast_due("v_sched", 0.3) is True
        msg = sched.create_broadcast(sample_vehicle, 0.3)
        assert msg.sequence_number == 1

    def test_state_capture_and_rollback(self, sample_vehicle):
        sched = BroadcastScheduler(broadcast_interval_s=0.1)

        # Capture baseline
        baseline = sched.capture_state()

        # Emit broadcast at t=0.0
        sched.create_broadcast(sample_vehicle, current_time_s=0.0)
        assert sched._sequence_numbers["v_sched"] == 0

        # Roll back to baseline
        sched.restore_state(baseline)
        assert "v_sched" not in sched._sequence_numbers
        assert sched.is_broadcast_due("v_sched", current_time_s=0.0) is True

    def test_reset(self, sample_vehicle):
        sched = BroadcastScheduler(broadcast_interval_s=0.1)
        sched.create_broadcast(sample_vehicle, current_time_s=0.0)
        assert len(sched._sequence_numbers) == 1

        sched.reset()
        assert len(sched._sequence_numbers) == 0
        assert len(sched._next_broadcast_time) == 0

    def test_deterministic_independent_agent_ordering(self):
        """Scheduling two agents yields identical sequence numbers and timestamps."""
        v_a = Vehicle(id="vA", position=Position2D(x=0.0, y=0.0), speed_mps=10.0)
        v_b = Vehicle(id="vB", position=Position2D(x=5.0, y=5.0), speed_mps=10.0)

        sched1 = BroadcastScheduler(broadcast_interval_s=0.1)
        m1_a = sched1.create_broadcast(v_a, current_time_s=0.0)
        m1_b = sched1.create_broadcast(v_b, current_time_s=0.0)

        sched2 = BroadcastScheduler(broadcast_interval_s=0.1)
        # Reverse order of calling
        m2_b = sched2.create_broadcast(v_b, current_time_s=0.0)
        m2_a = sched2.create_broadcast(v_a, current_time_s=0.0)

        assert m1_a.sequence_number == m2_a.sequence_number == 0
        assert m1_b.sequence_number == m2_b.sequence_number == 0
        assert m1_a.timestamp_s == m2_a.timestamp_s == 0.0
        assert m1_b.timestamp_s == m2_b.timestamp_s == 0.0
