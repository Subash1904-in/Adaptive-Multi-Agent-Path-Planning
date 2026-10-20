"""Scenario execution runner orchestrating SimulationEngine stepping and termination.

Controls scenario runs, partial stepping, completion criteria evaluation,
result generation, and deterministic state resets.
"""

from typing import Any, Optional

from apps.core.scenarios.builder import ScenarioRunContext
from apps.core.scenarios.exceptions import (
    ScenarioExecutionError,
    ScenarioResetError,
)
from apps.core.scenarios.models import (
    ScenarioExecutionResult,
    TerminationReason,
)
from apps.core.simulation.models import EngineStatus, TickResult


class ScenarioRunner:
    """Orchestrates the execution of a built simulation scenario."""

    def __init__(self, context: ScenarioRunContext) -> None:
        """Initialize runner with a built ScenarioRunContext.

        Args:
            context: The ScenarioRunContext containing engine, world, and scenario definition.
        """
        self.context: ScenarioRunContext = context
        self.scenario = context.scenario
        self.world = context.world
        self.engine = context.engine
        self.tick_history: list[TickResult] = []
        self._initial_tick: int = self.engine.current_tick

    @property
    def current_tick(self) -> int:
        """Current integer tick of the simulation engine."""
        return self.engine.current_tick

    @property
    def elapsed_time_s(self) -> float:
        """Current simulated elapsed time in seconds."""
        return self.engine.elapsed_time_s

    def step(self, target_accels: Optional[dict[str, float]] = None) -> TickResult:
        """Advance the simulation scenario by exactly one discrete time step dt.

        Args:
            target_accels: Optional commanded acceleration mapping per vehicle ID.

        Returns:
            TickResult from the SimulationEngine.

        Raises:
            ScenarioExecutionError: If stepping fails.
        """
        try:
            tick_result = self.engine.step(target_accels=target_accels)
            self.tick_history.append(tick_result)
            return tick_result
        except Exception as exc:
            raise ScenarioExecutionError(
                f"Scenario execution failed at tick {self.engine.current_tick + 1}: {exc}",
                scenario_id=self.scenario.metadata.id,
                tick=self.engine.current_tick + 1,
                cause=exc,
            ) from exc

    def run(
        self,
        ticks: Optional[int] = None,
        target_accels_by_tick: Optional[list[dict[str, float]]] = None,
    ) -> ScenarioExecutionResult:
        """Execute simulation ticks according to configured limits and arrival conditions.

        Args:
            ticks: Optional specific number of ticks to run in this call.
            target_accels_by_tick: Optional list of per-tick acceleration mappings.

        Returns:
            ScenarioExecutionResult summarizing execution results and agent states.
        """
        if self.engine.status == EngineStatus.PAUSED:
            return self._build_result(TerminationReason.PAUSED)
        if self.engine.status == EngineStatus.STOPPED:
            return self._build_result(TerminationReason.STOPPED)
        if self.engine.status == EngineStatus.FAILED:
            return self._build_result(
                TerminationReason.FAILED,
                error_message="Simulation engine is in FAILED state.",
            )

        start_tick = self.engine.current_tick
        max_configured_ticks = self.scenario.effective_max_ticks

        # Check pre-run termination conditions
        agents = self.world.get_agents()
        if (
            self.scenario.stop_on_all_arrived
            and len(agents) > 0
            and all(a.is_arrived for a in agents)
        ):
            return self._build_result(TerminationReason.ALL_ARRIVED)

        if max_configured_ticks is not None and self.engine.current_tick >= max_configured_ticks:
            return self._build_result(TerminationReason.MAX_TICKS_REACHED)

        # Determine target tick limit for this invocation
        ticks_to_run = ticks
        accel_idx = 0

        while True:
            # 1. Check if engine was externally paused or stopped
            if self.engine.status == EngineStatus.PAUSED:
                return self._build_result(TerminationReason.PAUSED)
            if self.engine.status == EngineStatus.STOPPED:
                return self._build_result(TerminationReason.STOPPED)

            # 2. Check if configured scenario max_ticks limit is reached
            if (
                max_configured_ticks is not None
                and self.engine.current_tick >= max_configured_ticks
            ):
                return self._build_result(TerminationReason.MAX_TICKS_REACHED)

            # 3. Check if specific requested tick count for this run call is satisfied
            if ticks_to_run is not None and (self.engine.current_tick - start_tick) >= ticks_to_run:
                return self._build_result(TerminationReason.TARGET_TICKS_COMPLETED)

            # 4. Perform step
            accels = None
            if target_accels_by_tick and accel_idx < len(target_accels_by_tick):
                accels = target_accels_by_tick[accel_idx]
                accel_idx += 1

            try:
                self.step(target_accels=accels)
            except Exception as exc:
                return self._build_result(
                    TerminationReason.FAILED,
                    error_message=str(exc),
                )

            # 5. Check post-step arrival condition
            agents = self.world.get_agents()
            if (
                self.scenario.stop_on_all_arrived
                and len(agents) > 0
                and all(a.is_arrived for a in agents)
            ):
                return self._build_result(TerminationReason.ALL_ARRIVED)

    def run_to_completion(self) -> ScenarioExecutionResult:
        """Run the scenario to completion (either all vehicles arrive or max_ticks reached)."""
        return self.run(ticks=None)

    def reset(self) -> None:
        """Reset scenario state and engine back to initial baseline.

        Raises:
            ScenarioResetError: If resetting the engine or world state fails.
        """
        try:
            self.engine.reset()
            self.tick_history.clear()
            self._initial_tick = self.engine.current_tick
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to reset scenario '{self.scenario.metadata.id}': {exc}",
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

    def _build_result(
        self,
        reason: TerminationReason,
        error_message: Optional[str] = None,
        diagnostics: Optional[dict[str, Any]] = None,
    ) -> ScenarioExecutionResult:
        """Construct the immutable ScenarioExecutionResult."""
        agents = self.world.get_agents()
        arrived = tuple(sorted([a.vehicle.id for a in agents if a.is_arrived]))
        active = tuple(sorted([a.vehicle.id for a in agents if not a.is_arrived]))

        diag = dict(diagnostics or {})
        diag["excluded_vehicle_ids"] = list(self.context.excluded_vehicle_ids)
        diag["engine_status"] = self.engine.status.value
        diag["signal_count"] = self.world.signal_count

        return ScenarioExecutionResult(
            scenario_id=self.scenario.metadata.id,
            scenario_name=self.scenario.metadata.name,
            scenario_version=self.scenario.metadata.version,
            termination_reason=reason,
            initial_tick=self._initial_tick,
            final_tick=self.engine.current_tick,
            completed_ticks=self.engine.current_tick - self._initial_tick,
            elapsed_time_s=self.engine.elapsed_time_s,
            time_step_s=self.engine.time_step_s,
            total_vehicles=len(agents),
            arrived_count=len(arrived),
            arrived_vehicle_ids=arrived,
            active_count=len(active),
            active_vehicle_ids=active,
            final_world_snapshot=self.world.get_snapshot(),
            tick_results=tuple(self.tick_history) if self.tick_history else None,
            is_success=(reason != TerminationReason.FAILED),
            error_message=error_message,
            diagnostics=diag,
        )
