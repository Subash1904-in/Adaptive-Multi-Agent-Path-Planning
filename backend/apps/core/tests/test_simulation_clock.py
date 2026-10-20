"""Unit tests for the authoritative SimulationClock.

Verifies discrete fixed time-step progression, pause/resume/single-step semantics,
reset operations, floating-point accumulation drift elimination, and wall-clock independence.
"""

import math
import time

import pytest

from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.exceptions import ClockStateError, InvalidTimeStepError


class TestSimulationClockBasics:
    """Test clock initialization, default parameters, and property accessors."""

    def test_default_initialization(self) -> None:
        clock = SimulationClock()
        assert clock.time_step_s == 0.1
        assert clock.tick_count == 0
        assert clock.current_tick == 0
        assert clock.elapsed_time_s == 0.0
        assert clock.is_paused is False
        assert clock.is_running is True

    def test_custom_time_step_and_initial_tick(self) -> None:
        clock = SimulationClock(time_step_s=0.05, initial_tick=10)
        assert clock.time_step_s == 0.05
        assert clock.tick_count == 10
        assert clock.elapsed_time_s == 0.5
        assert clock.is_running is True

    def test_string_representation(self) -> None:
        clock = SimulationClock(time_step_s=0.2, initial_tick=5)
        repr_str = repr(clock)
        assert "tick=5" in repr_str
        assert "elapsed=1.0000s" in repr_str
        assert "dt=0.2s" in repr_str
        assert "state='running'" in repr_str


class TestSimulationClockValidation:
    """Test strict validation of discrete step durations and initial ticks."""

    @pytest.mark.parametrize("invalid_dt", [0.0, -0.1, -1.0])
    def test_non_positive_time_step_raises(self, invalid_dt: float) -> None:
        with pytest.raises(InvalidTimeStepError, match="strictly positive"):
            SimulationClock(time_step_s=invalid_dt)

    @pytest.mark.parametrize("invalid_dt", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_time_step_raises(self, invalid_dt: float) -> None:
        with pytest.raises(InvalidTimeStepError, match="finite"):
            SimulationClock(time_step_s=invalid_dt)

    @pytest.mark.parametrize("invalid_dt", ["0.1", None, True, False, [0.1]])
    def test_non_numeric_time_step_raises(self, invalid_dt: object) -> None:
        with pytest.raises(InvalidTimeStepError, match="numeric float"):
            SimulationClock(time_step_s=invalid_dt)  # type: ignore

    def test_out_of_bounds_time_step_raises(self) -> None:
        with pytest.raises(InvalidTimeStepError, match="outside allowable bounds"):
            SimulationClock(time_step_s=0.00001)

        with pytest.raises(InvalidTimeStepError, match="outside allowable bounds"):
            SimulationClock(time_step_s=15.0)

    @pytest.mark.parametrize("invalid_tick", [-1, -100, "0", 1.5, None])
    def test_invalid_initial_tick_raises(self, invalid_tick: object) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            SimulationClock(initial_tick=invalid_tick)  # type: ignore


class TestSimulationClockSteppingAndPause:
    """Test advancing ticks, pausing, resuming, and single-step operations."""

    def test_consecutive_ticks_advance_deterministically(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        for i in range(1, 11):
            new_tick = clock.tick()
            assert new_tick == i
            assert clock.tick_count == i
            assert math.isclose(clock.elapsed_time_s, i * 0.1, abs_tol=1e-9)

    def test_pause_prevents_normal_tick(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        clock.tick()
        clock.pause()
        assert clock.is_paused is True
        assert clock.is_running is False

        with pytest.raises(ClockStateError, match="Cannot advance a paused simulation clock"):
            clock.tick()

        # Tick and elapsed time remain unchanged
        assert clock.tick_count == 1
        assert clock.elapsed_time_s == 0.1

    def test_single_step_while_paused_with_force(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        clock.pause()

        # Explicit forced single step advances exactly one tick
        new_tick = clock.tick(force=True)
        assert new_tick == 1
        assert clock.tick_count == 1
        assert clock.elapsed_time_s == 0.1
        assert clock.is_paused is True  # Still paused

    def test_resume_allows_normal_tick(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        clock.pause()
        clock.resume()
        assert clock.is_running is True

        new_tick = clock.tick()
        assert new_tick == 1
        assert clock.tick_count == 1
        assert clock.elapsed_time_s == 0.1

    def test_idempotent_pause_and_resume(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        clock.pause()
        clock.pause()
        assert clock.is_paused is True

        clock.resume()
        clock.resume()
        assert clock.is_running is True


class TestSimulationClockResetAndDrift:
    """Test reset operations and precision retention over extended stepping."""

    def test_reset_restores_initial_state(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        for _ in range(50):
            clock.tick()
        clock.pause()

        assert clock.tick_count == 50
        assert clock.elapsed_time_s == 5.0
        assert clock.is_paused is True

        clock.reset()
        assert clock.tick_count == 0
        assert clock.elapsed_time_s == 0.0
        assert clock.is_paused is False
        assert clock.is_running is True

    def test_reset_with_custom_initial_tick(self) -> None:
        clock = SimulationClock(time_step_s=0.2)
        clock.tick()
        clock.reset(initial_tick=15)
        assert clock.tick_count == 15
        assert clock.elapsed_time_s == 3.0

    def test_reset_with_negative_tick_raises(self) -> None:
        clock = SimulationClock()
        with pytest.raises(ValueError, match="non-negative integer"):
            clock.reset(initial_tick=-5)

    def test_elimination_of_floating_point_drift(self) -> None:
        # 1000 steps of 0.1s in standard cumulative addition yields 100.00000000000014
        clock = SimulationClock(time_step_s=0.1)
        for _ in range(1000):
            clock.tick()

        assert clock.tick_count == 1000
        assert clock.elapsed_time_s == 100.0

    def test_wall_clock_delays_do_not_alter_simulated_time(self) -> None:
        clock = SimulationClock(time_step_s=0.1)
        clock.tick()
        time.sleep(0.01)  # 10ms real time
        # Simulated time is strictly governed by tick * dt, completely unaffected by real time
        assert clock.tick_count == 1
        assert clock.elapsed_time_s == 0.1
