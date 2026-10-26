"""Scenario orchestration and simulation configuration subsystem for AMAPP.

Provides typed scenario definitions, structural/semantic validation, runtime object builders,
deterministic execution runners, and structured result summaries.
"""

from typing import Optional

from apps.core.scenarios.builder import ScenarioBuilder, ScenarioRunContext
from apps.core.scenarios.examples import (
    create_adaptive_reroute_closure_scenario,
    create_adaptive_reroute_congestion_scenario,
    create_adaptive_reroute_cooldown_scenario,
    create_adaptive_reroute_current_edge_continuation_scenario,
    create_adaptive_reroute_delayed_network_scenario,
    create_adaptive_reroute_hazard_scenario,
    create_adaptive_reroute_insufficient_benefit_scenario,
    create_adaptive_reroute_no_alternative_scenario,
    create_adaptive_reroute_stale_report_scenario,
    create_burst_loss_scenario,
    create_congestion_sharing_scenario,
    create_degraded_network_scenario,
    create_hazard_dissemination_scenario,
    create_latency_scenario,
    create_multi_vehicle_scenario,
    create_packet_loss_scenario,
    create_road_closure_sharing_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
    create_tick_limited_scenario,
    create_unreachable_vehicle_scenario,
    create_luxembourg_rush_hour_scenario,
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
    TERMINAL_LIFECYCLE_STATES,
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    RunConfig,
    RunLifecycleState,
    RunMetadata,
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
    "RunConfig",
    "RunLifecycleState",
    "TERMINAL_LIFECYCLE_STATES",
    "RunMetadata",
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
    "create_adaptive_reroute_closure_scenario",
    "create_adaptive_reroute_cooldown_scenario",
    "create_adaptive_reroute_congestion_scenario",
    "create_adaptive_reroute_current_edge_continuation_scenario",
    "create_adaptive_reroute_delayed_network_scenario",
    "create_adaptive_reroute_hazard_scenario",
    "create_adaptive_reroute_insufficient_benefit_scenario",
    "create_adaptive_reroute_no_alternative_scenario",
    "create_adaptive_reroute_stale_report_scenario",
    "create_burst_loss_scenario",
    "create_congestion_sharing_scenario",
    "create_degraded_network_scenario",
    "create_hazard_dissemination_scenario",
    "create_latency_scenario",
    "create_multi_vehicle_scenario",
    "create_packet_loss_scenario",
    "create_road_closure_sharing_scenario",
    "create_signalized_scenario",
    "create_single_vehicle_scenario",
    "create_tick_limited_scenario",
    "create_unreachable_vehicle_scenario",
    "create_luxembourg_rush_hour_scenario",
]
