"""Unit tests for TrafficSignalController and SignalCycleConfig.

Verifies deterministic cyclic state transitions (RED -> GREEN -> YELLOW -> RED),
cycle parameter validation, time calculations, boundary handling, and reset behavior.
"""

import math

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.signals.controller import TrafficSignalController
from apps.core.signals.exceptions import (
    InvalidSignalCycleError,
)
from apps.core.signals.models import SignalCycleConfig, SignalQueryResult, SignalSnapshot


class TestSignalCycleConfigValidation:
    """Tests for SignalCycleConfig validation rules and serialization."""

    def test_default_cycle_config(self) -> None:
        """Test default cycle parameters."""
        cfg = SignalCycleConfig()
        assert cfg.green_duration_s == 30.0
        assert cfg.yellow_duration_s == 5.0
        assert cfg.red_duration_s == 30.0
        assert cfg.initial_phase == TrafficSignalState.RED
        assert cfg.phase_offset_s == 0.0
        assert cfg.total_cycle_duration_s == 65.0

    def test_custom_cycle_config(self) -> None:
        """Test custom cycle configuration."""
        cfg = SignalCycleConfig(
            green_duration_s=20.0,
            yellow_duration_s=4.0,
            red_duration_s=25.0,
            initial_phase=TrafficSignalState.GREEN,
            phase_offset_s=5.0,
        )
        assert cfg.green_duration_s == 20.0
        assert cfg.yellow_duration_s == 4.0
        assert cfg.red_duration_s == 25.0
        assert cfg.initial_phase == TrafficSignalState.GREEN
        assert cfg.phase_offset_s == 5.0
        assert cfg.total_cycle_duration_s == 49.0

    def test_config_to_dict_serialization(self) -> None:
        """Test JSON-compatible dictionary serialization."""
        cfg = SignalCycleConfig(
            green_duration_s=15.0,
            yellow_duration_s=3.0,
            red_duration_s=12.0,
        )
        d = cfg.to_dict()
        assert d == {
            "green_duration_s": 15.0,
            "yellow_duration_s": 3.0,
            "red_duration_s": 12.0,
            "initial_phase": "red",
            "phase_offset_s": 0.0,
            "total_cycle_duration_s": 30.0,
        }

    @pytest.mark.parametrize(
        "param,value",
        [
            ("green_duration_s", 0.0),
            ("green_duration_s", -5.0),
            ("yellow_duration_s", 0.0),
            ("yellow_duration_s", -2.0),
            ("red_duration_s", 0.0),
            ("red_duration_s", -10.0),
        ],
    )
    def test_non_positive_durations_raise(self, param: str, value: float) -> None:
        """Test that zero or negative durations raise InvalidSignalCycleError."""
        kwargs = {param: value}
        with pytest.raises(InvalidSignalCycleError, match="strictly positive"):
            SignalCycleConfig(**kwargs)

    @pytest.mark.parametrize(
        "param,value",
        [
            ("green_duration_s", math.nan),
            ("green_duration_s", math.inf),
            ("yellow_duration_s", math.nan),
            ("yellow_duration_s", math.inf),
            ("red_duration_s", math.nan),
            ("red_duration_s", -math.inf),
        ],
    )
    def test_non_finite_durations_raise(self, param: str, value: float) -> None:
        """Test that non-finite durations raise InvalidSignalCycleError."""
        kwargs = {param: value}
        with pytest.raises(InvalidSignalCycleError, match="finite float"):
            SignalCycleConfig(**kwargs)

    @pytest.mark.parametrize(
        "param,value",
        [
            ("green_duration_s", "30.0"),
            ("yellow_duration_s", None),
            ("red_duration_s", True),
            ("red_duration_s", [30.0]),
        ],
    )
    def test_non_numeric_durations_raise(self, param: str, value: object) -> None:
        """Test that non-numeric durations raise InvalidSignalCycleError."""
        kwargs = {param: value}
        with pytest.raises(InvalidSignalCycleError, match="numeric float"):
            SignalCycleConfig(**kwargs)

    def test_invalid_initial_phase_type_raises(self) -> None:
        """Test that non-enum initial phase raises InvalidSignalCycleError."""
        with pytest.raises(InvalidSignalCycleError, match="TrafficSignalState enum"):
            SignalCycleConfig(initial_phase="RED")  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad_offset", [-1.0, -0.01])
    def test_negative_phase_offset_raises(self, bad_offset: float) -> None:
        """Test that negative phase offset raises InvalidSignalCycleError."""
        with pytest.raises(InvalidSignalCycleError, match="non-negative"):
            SignalCycleConfig(phase_offset_s=bad_offset)

    @pytest.mark.parametrize("bad_offset", [math.nan, math.inf, -math.inf])
    def test_non_finite_phase_offset_raises(self, bad_offset: float) -> None:
        """Test that non-finite phase offset raises InvalidSignalCycleError."""
        with pytest.raises(InvalidSignalCycleError, match="finite"):
            SignalCycleConfig(phase_offset_s=bad_offset)

    def test_offset_exceeding_or_equal_to_cycle_raises(self) -> None:
        """Test that phase_offset_s >= total_cycle_duration_s raises InvalidSignalCycleError."""
        # Total cycle is 30 + 5 + 30 = 65s
        with pytest.raises(
            InvalidSignalCycleError, match="strictly less than total cycle duration"
        ):
            SignalCycleConfig(phase_offset_s=65.0)

        with pytest.raises(
            InvalidSignalCycleError, match="strictly less than total cycle duration"
        ):
            SignalCycleConfig(phase_offset_s=100.0)


class TestTrafficSignalControllerTransitions:
    """Tests for deterministic state transitions in TrafficSignalController."""

    def _make_signal(
        self,
        sig_id: str = "sig_01",
        node_id: str = "node_int",
    ) -> TrafficSignal:
        return TrafficSignal(
            id=sig_id,
            node_id=node_id,
            state=TrafficSignalState.RED,
            position=Position2D(x=10.0, y=20.0),
        )

    def test_initialization_with_defaults(self) -> None:
        """Test controller initialization and baseline t=0 state."""
        signal = self._make_signal()
        ctrl = TrafficSignalController(signal=signal)
        assert ctrl.id == "sig_01"
        assert ctrl.node_id == "node_int"
        assert ctrl.state == TrafficSignalState.RED
        assert ctrl.remaining_phase_s == 30.0
        assert ctrl.incoming_edge_ids == []

    def test_invalid_signal_type_raises(self) -> None:
        """Test that non-TrafficSignal entity raises TypeError."""
        with pytest.raises(TypeError, match="Expected TrafficSignal instance"):
            TrafficSignalController(signal="not_a_signal")  # type: ignore[arg-type]

    def test_strict_cyclic_progression_red_green_yellow_red(self) -> None:
        """Verify strict sequence: RED (30s) -> GREEN (30s) -> YELLOW (5s) -> RED (30s)."""
        signal = self._make_signal()
        cfg = SignalCycleConfig(
            red_duration_s=30.0,
            green_duration_s=30.0,
            yellow_duration_s=5.0,
            initial_phase=TrafficSignalState.RED,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg)

        # 1. At t=0.0 -> RED (remaining 30.0s)
        state, elapsed, rem = ctrl.evaluate(0.0)
        assert state == TrafficSignalState.RED
        assert elapsed == pytest.approx(0.0)
        assert rem == pytest.approx(30.0)

        # 2. At t=15.0 -> still RED (remaining 15.0s)
        state, elapsed, rem = ctrl.evaluate(15.0)
        assert state == TrafficSignalState.RED
        assert elapsed == pytest.approx(15.0)
        assert rem == pytest.approx(15.0)

        # 3. At t=30.0 -> transitions to GREEN (remaining 30.0s)
        state, elapsed, rem = ctrl.evaluate(30.0)
        assert state == TrafficSignalState.GREEN
        assert elapsed == pytest.approx(0.0)
        assert rem == pytest.approx(30.0)

        # 4. At t=45.0 -> GREEN (remaining 15.0s)
        state, elapsed, rem = ctrl.evaluate(45.0)
        assert state == TrafficSignalState.GREEN
        assert elapsed == pytest.approx(15.0)
        assert rem == pytest.approx(15.0)

        # 5. At t=60.0 -> transitions to YELLOW (remaining 5.0s)
        state, elapsed, rem = ctrl.evaluate(60.0)
        assert state == TrafficSignalState.YELLOW
        assert elapsed == pytest.approx(0.0)
        assert rem == pytest.approx(5.0)

        # 6. At t=62.5 -> YELLOW (remaining 2.5s)
        state, elapsed, rem = ctrl.evaluate(62.5)
        assert state == TrafficSignalState.YELLOW
        assert elapsed == pytest.approx(2.5)
        assert rem == pytest.approx(2.5)

        # 7. At t=65.0 -> cycle rolls over back to RED (remaining 30.0s)
        state, elapsed, rem = ctrl.evaluate(65.0)
        assert state == TrafficSignalState.RED
        assert elapsed == pytest.approx(0.0)
        assert rem == pytest.approx(30.0)

    def test_multi_cycle_consistency_no_drift(self) -> None:
        """Verify cycle rollover across 100 complete cycles without floating-point drift."""
        signal = self._make_signal()
        cfg = SignalCycleConfig(
            red_duration_s=20.0,
            green_duration_s=20.0,
            yellow_duration_s=4.0,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg)
        cycle_len = 44.0

        for k in range(1, 101):
            t_base = k * cycle_len
            state_red, _, rem_red = ctrl.evaluate(t_base)
            assert state_red == TrafficSignalState.RED
            assert rem_red == pytest.approx(20.0, abs=1e-5)

            state_green, _, rem_green = ctrl.evaluate(t_base + 20.0)
            assert state_green == TrafficSignalState.GREEN
            assert rem_green == pytest.approx(20.0, abs=1e-5)

            state_yellow, _, rem_yellow = ctrl.evaluate(t_base + 40.0)
            assert state_yellow == TrafficSignalState.YELLOW
            assert rem_yellow == pytest.approx(4.0, abs=1e-5)

    def test_initial_phase_green(self) -> None:
        """Verify progression when initial phase is GREEN -> YELLOW -> RED -> GREEN."""
        signal = self._make_signal()
        cfg = SignalCycleConfig(
            green_duration_s=20.0,
            yellow_duration_s=4.0,
            red_duration_s=30.0,
            initial_phase=TrafficSignalState.GREEN,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg)

        state, _, rem = ctrl.evaluate(0.0)
        assert state == TrafficSignalState.GREEN
        assert rem == pytest.approx(20.0)

        state, _, rem = ctrl.evaluate(20.0)
        assert state == TrafficSignalState.YELLOW
        assert rem == pytest.approx(4.0)

        state, _, rem = ctrl.evaluate(24.0)
        assert state == TrafficSignalState.RED
        assert rem == pytest.approx(30.0)

        state, _, rem = ctrl.evaluate(54.0)
        assert state == TrafficSignalState.GREEN
        assert rem == pytest.approx(20.0)

    def test_initial_phase_yellow(self) -> None:
        """Verify progression when initial phase is YELLOW -> RED -> GREEN -> YELLOW."""
        signal = self._make_signal()
        cfg = SignalCycleConfig(
            yellow_duration_s=5.0,
            red_duration_s=25.0,
            green_duration_s=20.0,
            initial_phase=TrafficSignalState.YELLOW,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg)

        state, _, rem = ctrl.evaluate(0.0)
        assert state == TrafficSignalState.YELLOW
        assert rem == pytest.approx(5.0)

        state, _, rem = ctrl.evaluate(5.0)
        assert state == TrafficSignalState.RED
        assert rem == pytest.approx(25.0)

        state, _, rem = ctrl.evaluate(30.0)
        assert state == TrafficSignalState.GREEN
        assert rem == pytest.approx(20.0)

    def test_phase_offset_shift(self) -> None:
        """Verify phase offset shifts the entire schedule correctly."""
        signal = self._make_signal()
        # RED 30s, GREEN 30s, YELLOW 5s. Offset = 10s into RED.
        cfg = SignalCycleConfig(
            red_duration_s=30.0,
            green_duration_s=30.0,
            yellow_duration_s=5.0,
            phase_offset_s=10.0,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg)

        # At t=0, effective tau = 10s -> still RED, but only 20s remaining
        state, elapsed, rem = ctrl.evaluate(0.0)
        assert state == TrafficSignalState.RED
        assert elapsed == pytest.approx(10.0)
        assert rem == pytest.approx(20.0)

        # At t=20.0 -> transitions to GREEN
        state, elapsed, rem = ctrl.evaluate(20.0)
        assert state == TrafficSignalState.GREEN
        assert elapsed == pytest.approx(0.0)
        assert rem == pytest.approx(30.0)

    def test_negative_simulation_time_raises(self) -> None:
        """Test that negative simulation time raises ValueError."""
        signal = self._make_signal()
        ctrl = TrafficSignalController(signal=signal)
        with pytest.raises(ValueError, match="sim_time_s must be non-negative"):
            ctrl.evaluate(-1.0)


class TestTrafficSignalControllerQueriesAndSnapshots:
    """Tests for query() and get_snapshot() methods of TrafficSignalController."""

    def _make_controller(self) -> TrafficSignalController:
        signal = TrafficSignal(
            id="sig_test",
            node_id="int_01",
            state=TrafficSignalState.RED,
            position=Position2D(x=0.0, y=0.0),
        )
        cfg = SignalCycleConfig(
            red_duration_s=30.0,
            green_duration_s=25.0,
            yellow_duration_s=5.0,
        )
        return TrafficSignalController(signal=signal, config=cfg)

    def test_query_during_red_phase(self) -> None:
        """Test time_to_green_s and time_to_red_s during RED phase."""
        ctrl = self._make_controller()
        # At t=10.0: RED phase, remaining_phase_s = 20.0
        q = ctrl.query(sim_time_s=10.0)
        assert isinstance(q, SignalQueryResult)
        assert q.signal_id == "sig_test"
        assert q.node_id == "int_01"
        assert q.state == TrafficSignalState.RED
        assert q.remaining_phase_s == pytest.approx(20.0)
        assert q.time_to_green_s == pytest.approx(20.0)
        assert q.time_to_red_s == 0.0

    def test_query_during_green_phase(self) -> None:
        """Test time_to_green_s and time_to_red_s during GREEN phase."""
        ctrl = self._make_controller()
        # At t=40.0: GREEN phase (30 to 55), remaining_phase_s = 15.0
        # Yellow is 5.0s, so time_to_red_s = 15.0 + 5.0 = 20.0
        q = ctrl.query(sim_time_s=40.0)
        assert q.state == TrafficSignalState.GREEN
        assert q.remaining_phase_s == pytest.approx(15.0)
        assert q.time_to_green_s == 0.0
        assert q.time_to_red_s == pytest.approx(20.0)

    def test_query_during_yellow_phase(self) -> None:
        """Test time_to_green_s and time_to_red_s during YELLOW phase."""
        ctrl = self._make_controller()
        # At t=56.0: YELLOW phase (55 to 60), remaining_phase_s = 4.0
        # Red is 30.0s, so time_to_green_s = 4.0 + 30.0 = 34.0
        q = ctrl.query(sim_time_s=56.0)
        assert q.state == TrafficSignalState.YELLOW
        assert q.remaining_phase_s == pytest.approx(4.0)
        assert q.time_to_red_s == pytest.approx(4.0)
        assert q.time_to_green_s == pytest.approx(34.0)

    def test_query_to_dict_serialization(self) -> None:
        """Test query result dictionary serialization."""
        ctrl = self._make_controller()
        q = ctrl.query(sim_time_s=0.0)
        d = q.to_dict()
        assert d == {
            "signal_id": "sig_test",
            "node_id": "int_01",
            "state": "red",
            "remaining_phase_s": 30.0,
            "time_to_green_s": 30.0,
            "time_to_red_s": 0.0,
            "incoming_edge_ids": [],
        }

    def test_get_snapshot_and_serialization(self) -> None:
        """Test snapshot creation and serialization."""
        ctrl = self._make_controller()
        snap = ctrl.get_snapshot(sim_time_s=12.5)
        assert isinstance(snap, SignalSnapshot)
        assert snap.signal_id == "sig_test"
        assert snap.node_id == "int_01"
        assert snap.state == TrafficSignalState.RED
        assert snap.remaining_phase_s == pytest.approx(17.5)
        assert snap.elapsed_in_phase_s == pytest.approx(12.5)
        assert snap.cycle_duration_s == 60.0

        d = snap.to_dict()
        assert d["signal_id"] == "sig_test"
        assert d["state"] == "red"
        assert d["remaining_phase_s"] == 17.5
        assert d["elapsed_in_phase_s"] == 12.5

    def test_reset_restores_initial_state(self) -> None:
        """Test that reset() restores signal to t=0 state."""
        ctrl = self._make_controller()
        ctrl.update(45.0)
        assert ctrl.state == TrafficSignalState.GREEN

        ctrl.reset()
        assert ctrl.state == TrafficSignalState.RED
        assert ctrl.remaining_phase_s == pytest.approx(30.0)
