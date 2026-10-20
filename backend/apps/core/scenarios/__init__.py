"""Scenario orchestration and simulation configuration subsystem for AMAPP.

Provides typed scenario definitions, structural/semantic validation, runtime object builders,
deterministic execution runners, and structured result summaries.
"""

from typing import Optional

from apps.core.scenarios.builder import ScenarioBuilder, ScenarioRunContext
from apps.core.scenarios.examples import (
    create_multi_vehicle_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
    create_tick_limited_scenario,
    create_unreachable_vehicle_scenario,
)
from apps.core.scenarios.exceptions import (
    ScenarioBuilderError,
    ScenarioError,
    ScenarioExecutionError,
    ScenarioResetError,
    ScenarioValidationError,
    UnreachableDestinationError,
)
from apps.core.scenarios.models import (
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioExecutionResult,
    ScenarioMetadata,
    TerminationReason,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import (
    validate_graph_compatibility,
    validate_scenario,
)


def run_scenario(
    scenario: ScenarioDefinition,
    ticks: Optional[int] = None,
) -> ScenarioExecutionResult:
    """Convenience function to build and execute a scenario to completion or specified ticks.

    Args:
        scenario: Authoritative ScenarioDefinition.
        ticks: Optional tick limit for this run invocation.

    Returns:
        ScenarioExecutionResult detailing execution outcome and final world state.
    """
    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()
    runner = ScenarioRunner(context=context)
    return runner.run(ticks=ticks)


__all__ = [
    # Models & Enums
    "ScenarioDefinition",
    "ScenarioMetadata",
    "VehicleScenarioDefinition",
    "TrafficSignalScenarioDefinition",
    "RoadNetworkDefinition",
    "RoadNetworkSourceType",
    "ScenarioExecutionResult",
    "TerminationReason",
    # Exceptions
    "ScenarioError",
    "ScenarioValidationError",
    "UnreachableDestinationError",
    "ScenarioBuilderError",
    "ScenarioExecutionError",
    "ScenarioResetError",
    # Validation
    "validate_scenario",
    "validate_graph_compatibility",
    # Builder & Context
    "ScenarioBuilder",
    "ScenarioRunContext",
    # Runner & Entrypoint
    "ScenarioRunner",
    "run_scenario",
    # Examples
    "create_single_vehicle_scenario",
    "create_multi_vehicle_scenario",
    "create_signalized_scenario",
    "create_unreachable_vehicle_scenario",
    "create_tick_limited_scenario",
]
