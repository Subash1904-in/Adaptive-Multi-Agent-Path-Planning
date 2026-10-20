"""Tests for ScenarioRunner execution, limits, termination, and reset lifecycle."""

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.scenarios import (
    ScenarioBuilder,
    ScenarioRunner,
    TerminationReason,
    create_multi_vehicle_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
    create_tick_limited_scenario,
    create_unreachable_vehicle_scenario,
    run_scenario,
)
from apps.core.scenarios.exceptions import UnreachableDestinationError
from apps.core.simulation.models import EngineStatus


def test_runner_single_step():
    scenario = create_single_vehicle_scenario(time_step_s=0.1, max_ticks=50)
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    assert runner.current_tick == 0
    assert runner.elapsed_time_s == 0.0

    tick_res = runner.step()
    assert tick_res.tick == 1
    assert runner.current_tick == 1
    assert len(runner.tick_history) == 1


def test_runner_run_specified_ticks():
    scenario = create_single_vehicle_scenario(time_step_s=0.1, max_ticks=100)
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    result = runner.run(ticks=10)
    assert result.is_success
    assert result.completed_ticks == 10
    assert result.final_tick == 10
    assert result.termination_reason == TerminationReason.TARGET_TICKS_COMPLETED


def test_runner_stop_on_all_arrived():
    scenario = create_single_vehicle_scenario(time_step_s=0.2, max_ticks=500)
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    result = runner.run_to_completion()
    assert result.is_success
    assert result.termination_reason == TerminationReason.ALL_ARRIVED
    assert result.arrived_count == 1
    assert result.arrived_vehicle_ids == ("veh_01",)
    assert result.active_count == 0


def test_runner_stop_at_max_ticks_with_active_vehicles():
    scenario = create_tick_limited_scenario(max_ticks=5)
    result = run_scenario(scenario)

    assert result.is_success
    assert result.termination_reason == TerminationReason.MAX_TICKS_REACHED
    assert result.completed_ticks == 5
    assert result.active_count == 1
    assert result.arrived_count == 0


def test_runner_paused_engine_behavior():
    scenario = create_single_vehicle_scenario()
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    # Pause engine
    runner.engine.pause()
    assert runner.engine.is_paused

    # run() should immediately return PAUSED result without advancing
    res = runner.run(ticks=10)
    assert res.termination_reason == TerminationReason.PAUSED
    assert res.completed_ticks == 0

    # Single-step while paused is permitted by SimulationEngine
    tick_res = runner.step()
    assert tick_res.tick == 1

    # Resume and run to completion
    runner.engine.resume()
    res2 = runner.run_to_completion()
    assert res2.termination_reason == TerminationReason.ALL_ARRIVED


def test_runner_engine_failure_handling(monkeypatch):
    scenario = create_single_vehicle_scenario()
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    # Cause engine.step to raise an unexpected runtime error
    def failing_step(*args, **kwargs):
        runner.engine.status = EngineStatus.FAILED
        raise RuntimeError("Simulated actuator hardware fault")

    monkeypatch.setattr(runner.engine, "step", failing_step)

    result = runner.run(ticks=5)
    assert not result.is_success
    assert result.termination_reason == TerminationReason.FAILED
    assert "Simulated actuator hardware fault" in (result.error_message or "")


def test_runner_reset_and_replay():
    scenario = create_single_vehicle_scenario(time_step_s=0.2, max_ticks=200)
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)

    # First run
    res1 = runner.run_to_completion()
    assert res1.termination_reason == TerminationReason.ALL_ARRIVED
    first_completed_ticks = res1.completed_ticks
    first_snapshot = res1.final_world_snapshot

    # Reset
    runner.reset()
    assert runner.current_tick == 0
    assert runner.elapsed_time_s == 0.0
    assert len(runner.tick_history) == 0

    # Ensure vehicle agent restored to EN_ROUTE at start
    agent = runner.world.get_agent("veh_01")
    assert agent.state == VehicleState.EN_ROUTE
    assert agent.current_edge_index == 0

    # Second run
    res2 = runner.run_to_completion()
    assert res2.termination_reason == TerminationReason.ALL_ARRIVED
    assert res2.completed_ticks == first_completed_ticks
    assert res2.final_world_snapshot.to_dict() == first_snapshot.to_dict()


def test_examples_suite():
    # Multi-vehicle
    mv_scn = create_multi_vehicle_scenario(max_ticks=250)
    mv_res = run_scenario(mv_scn)
    assert mv_res.is_success
    assert mv_res.total_vehicles == 3
    assert mv_res.arrived_count == 3

    # Signalized
    sig_scn = create_signalized_scenario(max_ticks=150)
    sig_res = run_scenario(sig_scn)
    assert sig_res.is_success
    assert sig_res.diagnostics["signal_count"] == 1

    # Unreachable destination rejection
    unreach_reject = create_unreachable_vehicle_scenario(allow_unreachable=False)
    with pytest.raises(UnreachableDestinationError):
        run_scenario(unreach_reject)

    # Unreachable destination allowed
    unreach_allowed = create_unreachable_vehicle_scenario(allow_unreachable=True)
    unreach_res = run_scenario(unreach_allowed)
    assert unreach_res.is_success
    assert unreach_res.diagnostics["excluded_vehicle_ids"] == ["veh_trapped"]
    assert unreach_res.total_vehicles == 1


def test_runner_stopped_and_failed_engine_behavior():
    scenario = create_single_vehicle_scenario()
    runner = ScenarioRunner(ScenarioBuilder(scenario).build())

    runner.engine.stop()
    res_stopped = runner.run(ticks=5)
    assert res_stopped.termination_reason == TerminationReason.STOPPED

    runner.engine.status = EngineStatus.FAILED
    res_failed = runner.run(ticks=5)
    assert res_failed.termination_reason == TerminationReason.FAILED
    assert not res_failed.is_success


def test_runner_reset_failure_raises(monkeypatch):
    from apps.core.scenarios.exceptions import ScenarioResetError

    scenario = create_single_vehicle_scenario()
    runner = ScenarioRunner(ScenarioBuilder(scenario).build())

    def bad_reset():
        raise RuntimeError("Reset failure")

    monkeypatch.setattr(runner.engine, "reset", bad_reset)
    with pytest.raises(ScenarioResetError):
        runner.reset()
