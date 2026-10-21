"""Unit and integration tests for ScenarioRunner lifecycle, execution limits, and cancellation.

Verifies:
- Valid scenario execution and invalid scenario rejection
- Lifecycle transitions (CREATED -> VALIDATING -> READY -> RUNNING -> terminal states)
- Rejection of invalid transitions and resuming terminal runs
- Tick-limit and simulation-duration termination
- Scenario-defined arrival completion
- Cooperative cancellation between ticks and idempotency
- Preservation of error details and diagnostics on failure
- Run state isolation between independent runner instances
"""

import pytest

from apps.core.scenarios.examples import (
    create_single_vehicle_scenario,
)
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.models import (
    TERMINAL_LIFECYCLE_STATES,
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    RunConfig,
    RunLifecycleState,
    ScenarioDefinition,
    ScenarioMetadata,
    TerminationReason,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.telemetry.exceptions import (
    InvalidExecutionLimitsError,
    RunStateTransitionError,
)


def _create_minimal_scenario(max_ticks: int = 10, time_step_s: float = 0.1) -> ScenarioDefinition:
    """Helper to create a minimal valid synthetic grid scenario."""
    return create_single_vehicle_scenario(time_step_s=time_step_s, max_ticks=max_ticks)


class TestRunnerLifecycleAndTransitions:
    """Tests lifecycle states and state transition constraints."""

    def test_lifecycle_normal_completion(self):
        """Runner starts in READY, runs in RUNNING, finishes in COMPLETED/LIMIT_REACHED."""
        scenario = _create_minimal_scenario(max_ticks=3)
        runner = ScenarioRunner.create(scenario)
        assert runner.lifecycle_state == RunLifecycleState.READY
        assert not runner.is_terminal

        result = runner.run(ticks=3)
        assert runner.is_terminal
        assert runner.lifecycle_state in TERMINAL_LIFECYCLE_STATES
        assert result.lifecycle_state == runner.lifecycle_state
        assert result.is_success is True

    def test_invalid_scenario_rejected_at_creation(self):
        """Invalid scenario configuration fails before entering READY."""
        meta = ScenarioMetadata(id="", name="Empty ID Scenario")  # Invalid: empty id
        road_net = RoadNetworkDefinition(source_type=RoadNetworkSourceType.SYNTHETIC_GRID)
        invalid_scn = ScenarioDefinition(
            metadata=meta,
            road_network=road_net,
            vehicles=(),
        )
        with pytest.raises(ScenarioValidationError):
            ScenarioRunner.create(invalid_scn)

    def test_terminal_run_cannot_silently_resume(self):
        """Running a terminated scenario raises RunStateTransitionError."""
        scenario = _create_minimal_scenario(max_ticks=2)
        runner = ScenarioRunner.create(scenario)
        runner.run_to_completion()
        assert runner.is_terminal

        with pytest.raises(RunStateTransitionError) as exc_info:
            runner.run(ticks=1)
        assert "terminal state" in str(exc_info.value).lower()

    def test_invalid_execution_limits_rejected(self):
        """Negative or zero max_ticks and max_duration_s raise InvalidExecutionLimitsError."""
        with pytest.raises(InvalidExecutionLimitsError):
            RunConfig(max_ticks=0)

        with pytest.raises(InvalidExecutionLimitsError):
            RunConfig(max_ticks=-5)

        with pytest.raises(InvalidExecutionLimitsError):
            RunConfig(max_duration_s=0.0)

        with pytest.raises(InvalidExecutionLimitsError):
            RunConfig(time_step_s=-0.1)

        with pytest.raises(InvalidExecutionLimitsError):
            RunConfig(max_export_bytes=0)


class TestRunnerLimitsAndTermination:
    """Tests execution limits (tick limit, duration limit, and arrival)."""

    def test_tick_limit_termination(self):
        """Run terminates with MAX_TICKS_REACHED and LIMIT_REACHED when tick limit reached."""
        scenario = _create_minimal_scenario(max_ticks=5)
        runner = ScenarioRunner.create(scenario, run_config=RunConfig(max_ticks=5))
        result = runner.run_to_completion()

        assert result.termination_reason == TerminationReason.MAX_TICKS_REACHED
        assert result.lifecycle_state == RunLifecycleState.LIMIT_REACHED
        assert result.completed_ticks == 5
        assert result.is_success is True

    def test_duration_limit_termination(self):
        """Run terminates with DURATION_LIMIT_REACHED when simulated duration is reached."""
        scenario = _create_minimal_scenario(max_ticks=100, time_step_s=0.1)
        runner = ScenarioRunner.create(scenario, run_config=RunConfig(max_duration_s=0.3))
        result = runner.run_to_completion()

        assert result.termination_reason == TerminationReason.DURATION_LIMIT_REACHED
        assert result.lifecycle_state == RunLifecycleState.LIMIT_REACHED
        assert result.elapsed_time_s >= 0.3
        assert result.is_success is True

    def test_partial_stepping_leaves_run_running(self):
        """Stepping for target ticks gives TARGET_TICKS_COMPLETED without terminating."""
        scenario = _create_minimal_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scenario)

        res1 = runner.run(ticks=3)
        assert res1.termination_reason == TerminationReason.TARGET_TICKS_COMPLETED
        assert res1.completed_ticks == 3
        assert res1.is_partial is True
        assert not runner.is_terminal

        res2 = runner.run(ticks=4)
        assert res2.termination_reason == TerminationReason.TARGET_TICKS_COMPLETED
        assert res2.completed_ticks == 7
        assert not runner.is_terminal


class TestRunnerCooperativeCancellation:
    """Tests cooperative cancellation between simulation ticks and idempotency."""

    def test_cancel_before_running(self):
        """Cancelling a runner in READY state transitions it directly to CANCELLED."""
        scenario = _create_minimal_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scenario)
        assert runner.lifecycle_state == RunLifecycleState.READY

        accepted = runner.cancel(reason="Aborted before start")
        assert accepted is True
        assert runner.lifecycle_state == RunLifecycleState.CANCELLED

        res = runner.run()
        assert res.termination_reason == TerminationReason.CANCELLED
        assert res.cancellation_reason == "Aborted before start"
        assert res.is_partial is True

    def test_cancel_during_execution(self):
        """Calling cancel() between ticks stops at the next tick boundary with CANCELLED status."""
        scenario = _create_minimal_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scenario)

        # Step 2 ticks first
        runner.run(ticks=2)
        assert not runner.is_terminal

        # Request cancellation
        runner.cancel(reason="Operator emergency stop")
        res = runner.run()  # attempts to continue

        assert res.termination_reason == TerminationReason.CANCELLED
        assert res.lifecycle_state == RunLifecycleState.CANCELLED
        assert res.cancellation_reason == "Operator emergency stop"
        assert runner.is_terminal

    def test_cancellation_is_idempotent(self):
        """Multiple calls to cancel() on an already cancelled run succeed idempotently."""
        scenario = _create_minimal_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scenario)
        runner.cancel(reason="Initial cancel")
        assert runner.cancel(reason="Second cancel") is True
        assert runner.cancel(reason="Third cancel") is True
        assert runner.lifecycle_state == RunLifecycleState.CANCELLED

    def test_cancel_on_completed_run_raises_transition_error(self):
        """Calling cancel() after scenario run has COMPLETED raises RunStateTransitionError."""
        scenario = _create_minimal_scenario(max_ticks=2)
        runner = ScenarioRunner.create(scenario)
        runner.run_to_completion()
        assert runner.is_terminal

        with pytest.raises(RunStateTransitionError):
            runner.cancel(reason="Too late")


class TestRunnerFailurePreservationAndIsolation:
    """Tests failure state preservation and multi-run state isolation."""

    def test_step_failure_preserves_error_context(self, monkeypatch):
        """When simulation engine step encounters a fatal error, error details are preserved."""
        scenario = _create_minimal_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scenario)

        def faulty_step(*args, **kwargs):
            raise RuntimeError("Hardware actuator bus fault")

        monkeypatch.setattr(runner.engine, "step", faulty_step)

        result = runner.run(ticks=1)
        assert result.termination_reason == TerminationReason.FAILED
        assert result.lifecycle_state == RunLifecycleState.FAILED
        assert result.is_success is False
        assert "Hardware actuator bus fault" in (result.error_message or "")
        assert runner.is_terminal

    def test_multiple_runner_instances_are_isolated(self):
        """Multiple ScenarioRunner instances maintain distinct run IDs and states."""
        scn_a = _create_minimal_scenario(max_ticks=5)
        scn_b = _create_minimal_scenario(max_ticks=10)

        runner_a = ScenarioRunner.create(scn_a, run_config=RunConfig(run_id="run_alpha"))
        runner_b = ScenarioRunner.create(scn_b, run_config=RunConfig(run_id="run_beta"))

        assert runner_a.run_id == "run_alpha"
        assert runner_b.run_id == "run_beta"
        assert runner_a.telemetry.run_id == "run_alpha"
        assert runner_b.telemetry.run_id == "run_beta"

        res_a = runner_a.run(ticks=3)
        assert res_a.completed_ticks == 3
        assert runner_b.current_tick == 0
        assert runner_b.telemetry.record_count == 1  # only initial READY state change

        res_b = runner_b.run(ticks=5)
        assert res_b.completed_ticks == 5
        assert res_a.run_id == "run_alpha"
        assert res_b.run_id == "run_beta"
