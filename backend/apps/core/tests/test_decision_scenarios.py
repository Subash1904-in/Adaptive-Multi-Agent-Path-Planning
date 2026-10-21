"""Automated tests for Phase 19 AI decision scenarios and validation rules."""

import pytest

from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_ai_decision_congestion_belief_preference_scenario,
    create_ai_decision_emergency_corridor_rejection_scenario,
    create_ai_decision_fastest_route_scenario,
    create_ai_decision_low_confidence_deferral_scenario,
    create_ai_decision_road_closure_rejection_scenario,
    create_ai_decision_route_stability_hysteresis_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import validate_scenario


def test_scenario_validation_with_valid_decision_config():
    """Verify validate_scenario accepts a ScenarioDefinition with valid DecisionConfig."""
    scn = create_ai_decision_fastest_route_scenario()
    # Should validate without raising
    validate_scenario(scn)
    assert scn.decision_config is not None
    assert scn.decision_config.enabled is True


def test_scenario_validation_with_invalid_decision_config():
    """Verify validate_scenario rejects invalid decision_config specifications."""
    bad_scn = create_single_vehicle_scenario()
    object.__setattr__(bad_scn, "decision_config", "not_a_decision_config")  # type: ignore

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_scenario(bad_scn)
    assert "decision_config" in str(exc_info.value.field)


def test_scenario_validation_backward_compatibility():
    """Verify scenarios omitting decision_config remain completely valid."""
    scn = create_single_vehicle_scenario()
    assert scn.decision_config is None
    validate_scenario(scn)


def test_scenario_builder_injects_decision_config():
    """Verify ScenarioBuilder constructs WorldState with properly injected DecisionManager."""
    scn = create_ai_decision_fastest_route_scenario()
    builder = ScenarioBuilder(scn)
    ctx = builder.build()

    assert ctx.world.decision_manager is not None
    assert ctx.world.decision_manager.config.enabled is True
    assert ctx.world.adaptive_routing_adapter.decision_manager is ctx.world.decision_manager


def test_execution_ai_decision_fastest_route_scenario():
    """Verify end-to-end execution of fastest route selection scenario."""
    scn = create_ai_decision_fastest_route_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15
    assert ctx.world.decision_manager.config.enabled is True


def test_execution_ai_decision_road_closure_rejection_scenario():
    """Verify end-to-end execution of road closure rejection scenario."""
    scn = create_ai_decision_road_closure_rejection_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15


def test_execution_ai_decision_congestion_belief_preference_scenario():
    """Verify end-to-end execution of low-congestion preference scenario."""
    scn = create_ai_decision_congestion_belief_preference_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15


def test_execution_ai_decision_low_confidence_deferral_scenario():
    """Verify end-to-end execution of low-confidence deferral scenario."""
    scn = create_ai_decision_low_confidence_deferral_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15


def test_execution_ai_decision_route_stability_hysteresis_scenario():
    """Verify end-to-end execution of route stability hysteresis scenario."""
    scn = create_ai_decision_route_stability_hysteresis_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15


def test_execution_ai_decision_emergency_corridor_rejection_scenario():
    """Verify end-to-end execution of emergency corridor hard constraint rejection scenario."""
    scn = create_ai_decision_emergency_corridor_rejection_scenario(max_ticks=20)
    builder = ScenarioBuilder(scn)
    ctx = builder.build()
    runner = ScenarioRunner(context=ctx)

    result = runner.run(ticks=15)
    assert result.is_success
    assert result.completed_ticks == 15
