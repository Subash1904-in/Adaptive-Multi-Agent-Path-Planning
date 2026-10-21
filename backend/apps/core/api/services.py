"""Domain service layer and in-memory registries for the REST API.

Provides thread-safe registries for ScenarioDefinitions and ScenarioRunners,
and high-level simulation orchestration services.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Optional

from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_ambulance_corridor_scenario,
    create_congestion_sharing_scenario,
    create_multi_vehicle_scenario,
    create_pedestrian_crossing_permitted_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.models import (
    RunConfig,
    RunLifecycleState,
    ScenarioDefinition,
    TerminationReason,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import validate_scenario
from apps.core.telemetry.aggregation import MetricsAggregator
from apps.core.telemetry.exceptions import DuplicateRunIdError, RunStateTransitionError
from apps.core.telemetry.models import TelemetryConfig

from .exceptions import (
    ConcurrentStepExecutionError,
    DuplicateScenarioIdError,
    RunNotFoundError,
    ScenarioNotFoundError,
)

logger = logging.getLogger("amapp.api")

EDUCATIONAL_DISCLAIMER: str = (
    "AMAPP is an educational simulation framework and is not intended for "
    "real-world autonomous vehicle safety-critical control."
)


class ScenarioRegistry:
    """Thread-safe in-memory registry for ScenarioDefinitions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scenarios: dict[str, ScenarioDefinition] = {}

    def register(
        self,
        scenario: ScenarioDefinition,
        overwrite: bool = False,
    ) -> ScenarioDefinition:
        """Register a scenario definition.

        Args:
            scenario: The ScenarioDefinition to register.
            overwrite: If True, replace existing scenario with the same ID.

        Returns:
            The registered ScenarioDefinition.

        Raises:
            DuplicateScenarioIdError: If scenario ID exists and overwrite is False.
        """
        with self._lock:
            scenario_id = scenario.metadata.id
            if scenario_id in self._scenarios and not overwrite:
                raise DuplicateScenarioIdError(scenario_id)
            self._scenarios[scenario_id] = scenario
            logger.info("Registered scenario '%s' in ScenarioRegistry.", scenario_id)
            return scenario

    def get(self, scenario_id: str) -> ScenarioDefinition:
        """Retrieve a scenario definition by ID.

        Args:
            scenario_id: Unique scenario identifier.

        Returns:
            The ScenarioDefinition.

        Raises:
            ScenarioNotFoundError: If scenario_id is not registered.
        """
        with self._lock:
            if scenario_id not in self._scenarios:
                raise ScenarioNotFoundError(scenario_id)
            return self._scenarios[scenario_id]

    def list_all(self) -> list[ScenarioDefinition]:
        """Return all registered scenario definitions sorted by ID."""
        with self._lock:
            return [self._scenarios[k] for k in sorted(self._scenarios.keys())]

    def exists(self, scenario_id: str) -> bool:
        """Check if a scenario exists in the registry."""
        with self._lock:
            return scenario_id in self._scenarios

    def delete(self, scenario_id: str) -> bool:
        """Delete a scenario from the registry.

        Args:
            scenario_id: Unique scenario identifier.

        Returns:
            True if deleted.

        Raises:
            ScenarioNotFoundError: If scenario_id is not registered.
        """
        with self._lock:
            if scenario_id not in self._scenarios:
                raise ScenarioNotFoundError(scenario_id)
            del self._scenarios[scenario_id]
            logger.info("Deleted scenario '%s' from ScenarioRegistry.", scenario_id)
            return True

    def clear(self) -> None:
        """Remove all scenarios from the registry."""
        with self._lock:
            self._scenarios.clear()

    def preload_defaults(self) -> None:
        """Preload standard example scenarios into the registry."""
        defaults = [
            ("scn_single_veh", create_single_vehicle_scenario()),
            ("scn_multi_veh", create_multi_vehicle_scenario()),
            ("scn_signalized", create_signalized_scenario()),
            ("scn_congestion", create_congestion_sharing_scenario()),
            ("scn_ambulance", create_ambulance_corridor_scenario()),
            ("scn_pedestrian", create_pedestrian_crossing_permitted_scenario()),
        ]
        with self._lock:
            for scn_id, scn in defaults:
                if scn_id not in self._scenarios:
                    self._scenarios[scn_id] = scn
            logger.info("Preloaded %d default scenarios into registry.", len(defaults))


class RunRegistry:
    """Thread-safe in-memory registry for ScenarioRunners."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, ScenarioRunner] = {}

    def register(self, runner: ScenarioRunner) -> ScenarioRunner:
        """Register an active simulation runner.

        Args:
            runner: The ScenarioRunner instance.

        Returns:
            The registered ScenarioRunner.

        Raises:
            DuplicateRunIdError: If run_id already exists.
        """
        with self._lock:
            run_id = runner.run_id
            if run_id in self._runs:
                raise DuplicateRunIdError(
                    f"Simulation run with ID '{run_id}' already exists in registry.",
                    run_id=run_id,
                )
            self._runs[run_id] = runner
            from apps.core.realtime.broadcaster import SimulationEventBroadcaster

            SimulationEventBroadcaster.get_instance().attach_runner(runner)
            logger.info("Registered simulation run '%s' in RunRegistry.", run_id)
            return runner

    def get(self, run_id: str) -> ScenarioRunner:
        """Retrieve a simulation runner by ID.

        Args:
            run_id: Unique run identifier.

        Returns:
            The ScenarioRunner instance.

        Raises:
            RunNotFoundError: If run_id is not registered.
        """
        with self._lock:
            if run_id not in self._runs:
                raise RunNotFoundError(run_id)
            return self._runs[run_id]

    def list_all(self) -> list[ScenarioRunner]:
        """Return all registered simulation runners."""
        with self._lock:
            return list(self._runs.values())

    def exists(self, run_id: str) -> bool:
        """Check if a run exists in the registry."""
        with self._lock:
            return run_id in self._runs

    def delete(self, run_id: str) -> bool:
        """Delete a simulation runner from the registry.

        Args:
            run_id: Unique run identifier.

        Returns:
            True if deleted.

        Raises:
            RunNotFoundError: If run_id is not registered.
        """
        with self._lock:
            if run_id not in self._runs:
                raise RunNotFoundError(run_id)
            runner = self._runs.pop(run_id)
            from apps.core.realtime.broadcaster import SimulationEventBroadcaster

            SimulationEventBroadcaster.get_instance().detach_runner(runner)
            if hasattr(runner, "telemetry") and not runner.telemetry.is_closed:
                runner.telemetry.close()
            logger.info("Deleted simulation run '%s' from RunRegistry.", run_id)
            return True

    def clear(self) -> None:
        """Remove all runners and close open telemetry collectors."""
        with self._lock:
            from apps.core.realtime.broadcaster import SimulationEventBroadcaster

            broadcaster = SimulationEventBroadcaster.get_instance()
            for runner in self._runs.values():
                broadcaster.detach_runner(runner)
                if hasattr(runner, "telemetry") and not runner.telemetry.is_closed:
                    runner.telemetry.close()
            self._runs.clear()


# Default singleton registries for the application runtime
default_scenario_registry = ScenarioRegistry()
default_scenario_registry.preload_defaults()
default_run_registry = RunRegistry()


class SimulationService:
    """High-level application service orchestrating scenario and run management."""

    def __init__(
        self,
        scenario_registry: Optional[ScenarioRegistry] = None,
        run_registry: Optional[RunRegistry] = None,
    ) -> None:
        self.scenario_registry = scenario_registry or default_scenario_registry
        self.run_registry = run_registry or default_run_registry

    def list_scenarios(self) -> list[ScenarioDefinition]:
        """List all available scenario definitions."""
        return self.scenario_registry.list_all()

    def get_scenario(self, scenario_id: str) -> ScenarioDefinition:
        """Retrieve a scenario definition by ID."""
        return self.scenario_registry.get(scenario_id)

    def register_scenario(
        self,
        scenario: ScenarioDefinition,
        overwrite: bool = False,
    ) -> ScenarioDefinition:
        """Validate and register a new scenario definition."""
        validate_scenario(scenario)
        return self.scenario_registry.register(scenario, overwrite=overwrite)

    def validate_scenario_definition(self, scenario: ScenarioDefinition) -> dict[str, Any]:
        """Validate a scenario definition without registering it."""
        validate_scenario(scenario)
        # Verify builder compatibility
        builder = ScenarioBuilder(scenario)
        builder.build()
        return {
            "valid": True,
            "scenario_id": scenario.metadata.id,
            "scenario_name": scenario.metadata.name,
            "disclaimer": EDUCATIONAL_DISCLAIMER,
        }

    def create_run(
        self,
        scenario_id: Optional[str] = None,
        scenario: Optional[ScenarioDefinition] = None,
        run_id: Optional[str] = None,
        max_ticks: Optional[int] = None,
        max_duration_s: Optional[float] = None,
        stop_on_all_arrived: Optional[bool] = None,
        time_step_s: Optional[float] = None,
        seed: Optional[int] = None,
        telemetry_config: Optional[TelemetryConfig] = None,
    ) -> ScenarioRunner:
        """Create and initialize a new simulation run in the READY state."""
        target_scenario: ScenarioDefinition
        if scenario is not None:
            target_scenario = scenario
        elif scenario_id is not None:
            target_scenario = self.scenario_registry.get(scenario_id)
        else:
            raise ScenarioNotFoundError("Missing scenario_id or scenario definition.")

        resolved_run_id = run_id or f"run_{target_scenario.metadata.id}_{uuid.uuid4().hex[:8]}"

        if self.run_registry.exists(resolved_run_id):
            raise DuplicateRunIdError(
                f"Simulation run with ID '{resolved_run_id}' already exists.",
                run_id=resolved_run_id,
            )

        run_cfg = RunConfig(
            run_id=resolved_run_id,
            max_ticks=max_ticks if max_ticks is not None else target_scenario.effective_max_ticks,
            max_duration_s=(
                max_duration_s if max_duration_s is not None else target_scenario.max_duration_s
            ),
            stop_on_all_arrived=(
                stop_on_all_arrived
                if stop_on_all_arrived is not None
                else target_scenario.stop_on_all_arrived
            ),
            time_step_s=time_step_s if time_step_s is not None else target_scenario.time_step_s,
            seed=seed if seed is not None else target_scenario.seed,
            telemetry_config=telemetry_config,
        )

        runner = ScenarioRunner.create(
            scenario=target_scenario,
            run_config=run_cfg,
            telemetry_config=telemetry_config,
        )
        return self.run_registry.register(runner)

    def get_run(self, run_id: str) -> ScenarioRunner:
        """Retrieve an active or completed simulation runner."""
        return self.run_registry.get(run_id)

    def list_runs(self) -> list[ScenarioRunner]:
        """List all registered simulation runners."""
        return self.run_registry.list_all()

    def step_run(
        self,
        run_id: str,
        ticks: int = 1,
        target_accels: Optional[dict[str, float]] = None,
        run_to_completion: bool = False,
    ) -> dict[str, Any]:
        """Advance a simulation run by ticks or to completion.

        Raises:
            RunStateTransitionError: If the run is already terminal.
        """
        runner = self.run_registry.get(run_id)

        if runner.is_terminal:
            raise RunStateTransitionError(
                f"Cannot step simulation run '{run_id}' in terminal state "
                f"'{runner.lifecycle_state.value}'.",
                current_state=runner.lifecycle_state.value,
                target_state=RunLifecycleState.RUNNING.value,
                run_id=run_id,
            )

        if not hasattr(runner, "_execution_lock"):
            runner._execution_lock = threading.Lock()

        if not runner._execution_lock.acquire(blocking=False):
            raise ConcurrentStepExecutionError(
                f"Simulation run '{run_id}' is already actively executing a step operation.",
                run_id=run_id,
            )

        try:
            if run_to_completion:
                exec_result = runner.run_to_completion()
            else:
                accels_by_tick = [target_accels] if target_accels else None
                exec_result = runner.run(ticks=ticks, target_accels_by_tick=accels_by_tick)
        finally:
            runner._execution_lock.release()

        agents = runner.world.get_agents()
        arrived_cnt = sum(1 for a in agents if a.is_arrived)
        last_tick_res = runner.tick_history[-1].to_dict() if runner.tick_history else None

        return {
            "run_id": runner.run_id,
            "lifecycle_state": runner.lifecycle_state.value,
            "current_tick": runner.current_tick,
            "elapsed_time_s": round(runner.elapsed_time_s, 4),
            "is_terminal": runner.is_terminal,
            "is_success": exec_result.is_success,
            "termination_reason": (
                exec_result.termination_reason.value
                if hasattr(exec_result.termination_reason, "value")
                else str(exec_result.termination_reason)
            ),
            "total_vehicles": exec_result.total_vehicles,
            "arrived_count": arrived_cnt,
            "active_count": len(agents) - arrived_cnt,
            "advanced_ticks": ticks,
            "tick_result": last_tick_res,
            "last_tick_result": last_tick_res,
            "disclaimer": EDUCATIONAL_DISCLAIMER,
        }

    def cancel_run(
        self,
        run_id: str,
        reason: str = "User requested cancellation",
    ) -> dict[str, Any]:
        """Request cooperative cancellation of a simulation run."""
        runner = self.run_registry.get(run_id)
        runner.cancel(reason=reason)
        if runner.lifecycle_state == RunLifecycleState.RUNNING:
            runner._transition_to(RunLifecycleState.CANCELLED)
        return {
            "run_id": runner.run_id,
            "lifecycle_state": runner.lifecycle_state.value,
            "current_tick": runner.current_tick,
            "elapsed_time_s": round(runner.elapsed_time_s, 4),
            "is_terminal": runner.is_terminal,
            "cancellation_reason": reason,
            "disclaimer": EDUCATIONAL_DISCLAIMER,
        }

    def get_run_result(self, run_id: str) -> dict[str, Any]:
        """Retrieve full execution result for a run (final or intermediate)."""
        runner = self.run_registry.get(run_id)
        if runner._last_result is None:
            runner._last_result = runner._build_result(TerminationReason.STOPPED)
        result_dict = runner._last_result.to_dict()
        result_dict["disclaimer"] = EDUCATIONAL_DISCLAIMER
        return result_dict

    def get_run_metrics(self, run_id: str) -> dict[str, Any]:
        """Retrieve computed metrics summary for a run."""
        runner = self.run_registry.get(run_id)
        if runner._last_result and runner._last_result.metrics_summary:
            metrics = runner._last_result.metrics_summary
        else:
            agents = runner.world.get_agents()
            arrived = [a for a in agents if a.is_arrived]
            active = [a for a in agents if not a.is_arrived]
            reason = (
                runner._last_result.termination_reason.value
                if runner._last_result
                else TerminationReason.STOPPED.value
            )
            agg = MetricsAggregator.aggregate(
                tick_history=runner.tick_history,
                world=runner.world,
                total_vehicles=len(agents),
                arrived_vehicles=len(arrived),
                active_vehicles=len(active),
                terminal_state=runner.lifecycle_state.value,
                termination_reason=reason,
                elapsed_time_s=runner.engine.elapsed_time_s,
                time_step_s=runner.engine.time_step_s,
            )
            metrics = agg.to_dict()

        return {
            "run_id": runner.run_id,
            "lifecycle_state": runner.lifecycle_state.value,
            "current_tick": runner.current_tick,
            "metrics": metrics,
            "disclaimer": EDUCATIONAL_DISCLAIMER,
        }

    def query_run_telemetry(
        self,
        run_id: str,
        record_type: Optional[str] = None,
        name: Optional[str] = None,
        tick_start: Optional[int] = None,
        tick_end: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Query bounded telemetry stream records for a run."""
        runner = self.run_registry.get(run_id)
        categories = [record_type] if record_type else None
        records = runner.telemetry.filter_records(
            min_tick=tick_start,
            max_tick=tick_end,
            categories=categories,
        )
        if name:
            records = [r for r in records if r.name == name]
        if limit is not None:
            records = records[:limit]
        return {
            "run_id": runner.run_id,
            "total_records_buffered": runner.telemetry.record_count,
            "query_returned_count": len(records),
            "drop_stats": runner.telemetry.drop_stats.to_dict(),
            "records": [r.to_dict() for r in records],
            "disclaimer": EDUCATIONAL_DISCLAIMER,
        }

    def export_run(
        self,
        run_id: str,
        max_bytes: int = 10_000_000,
        indent: Optional[int] = None,
        max_telemetry_records: Optional[int] = None,
    ) -> str:
        """Export serialized simulation run results as RFC 8259 JSON."""
        runner = self.run_registry.get(run_id)
        return runner.export_result(
            indent=indent,
            max_size_bytes=max_bytes,
            max_telemetry_records=max_telemetry_records,
        )


default_simulation_service = SimulationService()
