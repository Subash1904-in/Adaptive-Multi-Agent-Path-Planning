"""Scenario execution runner orchestrating SimulationEngine stepping and termination.

Controls scenario runs, partial stepping, completion criteria evaluation,
result generation, deterministic state resets, explicit lifecycle management,
bounded telemetry collection, and cross-subsystem metrics aggregation.
"""

from typing import Any, Optional

from apps.core.scenarios.builder import ScenarioBuilder, ScenarioRunContext
from apps.core.scenarios.exceptions import (
    ScenarioExecutionError,
    ScenarioResetError,
)
from apps.core.scenarios.models import (
    TERMINAL_LIFECYCLE_STATES,
    RunConfig,
    RunLifecycleState,
    RunMetadata,
    ScenarioDefinition,
    ScenarioExecutionResult,
    TerminationReason,
)
from apps.core.scenarios.validation import validate_scenario
from apps.core.simulation.models import EngineStatus, TickResult
from apps.core.telemetry.aggregation import MetricsAggregator
from apps.core.telemetry.collector import TelemetryCollector
from apps.core.telemetry.exceptions import RunStateTransitionError
from apps.core.telemetry.fingerprint import (
    compute_scenario_fingerprint,
    compute_world_state_fingerprint,
    get_git_commit_sha,
)
from apps.core.telemetry.models import TelemetryConfig, TelemetryRecordType


class ScenarioRunner:
    """Orchestrates the execution of a built simulation scenario with explicit lifecycle,
    bounded telemetry, deterministic reproducibility metadata, and metrics aggregation.
    """

    def __init__(
        self,
        context: ScenarioRunContext,
        run_config: Optional[RunConfig] = None,
        telemetry_config: Optional[TelemetryConfig] = None,
    ) -> None:
        """Initialize runner with a built ScenarioRunContext.

        Args:
            context: The ScenarioRunContext containing engine, world, and scenario definition.
            run_config: Optional RunConfig governing execution limits and telemetry.
            telemetry_config: Optional TelemetryConfig governing stream collection.
        """
        self.context: ScenarioRunContext = context
        self.scenario: ScenarioDefinition = context.scenario
        self.world = context.world
        self.engine = context.engine
        self.tick_history: list[TickResult] = []
        self._initial_tick: int = self.engine.current_tick

        # Initialize run configuration
        self.run_config: RunConfig = run_config or RunConfig(
            run_id=None,
            max_ticks=self.scenario.effective_max_ticks,
            max_duration_s=self.scenario.max_duration_s,
            stop_on_all_arrived=self.scenario.stop_on_all_arrived,
            time_step_s=self.scenario.time_step_s,
            seed=self.scenario.seed,
            telemetry_config=telemetry_config,
        )

        self.run_id: str = self.run_config.run_id or f"run_{self.scenario.metadata.id}"
        self._lifecycle_state: RunLifecycleState = RunLifecycleState.READY
        self._cancellation_requested: bool = False
        self._cancellation_reason: Optional[str] = None
        self._last_result: Optional[ScenarioExecutionResult] = None

        # Telemetry collector
        t_cfg = self.run_config.telemetry_config or telemetry_config or TelemetryConfig()
        self.telemetry: TelemetryCollector = TelemetryCollector(run_id=self.run_id, config=t_cfg)

        # Reproducibility metadata
        self.scenario_fingerprint: str = compute_scenario_fingerprint(self.scenario)
        self.initial_world_state_fingerprint: str = compute_world_state_fingerprint(
            self.world.get_snapshot()
        )
        self.commit_sha: Optional[str] = get_git_commit_sha()

        self._record_lifecycle_change(RunLifecycleState.CREATED, RunLifecycleState.READY)

    @classmethod
    def create(
        cls,
        scenario: ScenarioDefinition,
        run_config: Optional[RunConfig] = None,
        telemetry_config: Optional[TelemetryConfig] = None,
    ) -> "ScenarioRunner":
        """Factory method: validate scenario, assemble context, and create ScenarioRunner.

        Enforces CREATED -> VALIDATING -> READY lifecycle transitions.

        Args:
            scenario: Authoritative ScenarioDefinition instance.
            run_config: Optional execution configuration.
            telemetry_config: Optional telemetry configuration.

        Returns:
            Initialized ScenarioRunner in READY state.

        Raises:
            ScenarioValidationError: If scenario fails structural or semantic validation.
        """
        validate_scenario(scenario)
        context = ScenarioBuilder(scenario).build()
        return cls(context=context, run_config=run_config, telemetry_config=telemetry_config)

    @property
    def lifecycle_state(self) -> RunLifecycleState:
        """Current lifecycle state of the scenario execution."""
        return self._lifecycle_state

    @property
    def is_terminal(self) -> bool:
        """Whether the run is in a terminal lifecycle state."""
        return self._lifecycle_state in TERMINAL_LIFECYCLE_STATES

    @property
    def current_tick(self) -> int:
        """Current integer tick of the simulation engine."""
        return self.engine.current_tick

    @property
    def elapsed_time_s(self) -> float:
        """Current simulated elapsed time in seconds."""
        return self.engine.elapsed_time_s

    def _transition_to(self, new_state: RunLifecycleState) -> None:
        """Enforce valid lifecycle state transitions.

        Raises:
            RunStateTransitionError: If attempting an invalid transition or resuming a terminal run.
        """
        if self._lifecycle_state == new_state:
            return

        old_state = self._lifecycle_state

        if old_state in TERMINAL_LIFECYCLE_STATES:
            raise RunStateTransitionError(
                f"Cannot transition run '{self.run_id}' from terminal state "
                f"'{old_state.value}' to '{new_state.value}'.",
                current_state=old_state.value,
                target_state=new_state.value,
                run_id=self.run_id,
            )

        valid_transitions = {
            RunLifecycleState.CREATED: {
                RunLifecycleState.VALIDATING,
                RunLifecycleState.READY,
                RunLifecycleState.FAILED,
            },
            RunLifecycleState.VALIDATING: {
                RunLifecycleState.READY,
                RunLifecycleState.FAILED,
            },
            RunLifecycleState.READY: {
                RunLifecycleState.RUNNING,
                RunLifecycleState.CANCELLED,
                RunLifecycleState.FAILED,
            },
            RunLifecycleState.RUNNING: {
                RunLifecycleState.COMPLETED,
                RunLifecycleState.CANCELLED,
                RunLifecycleState.FAILED,
                RunLifecycleState.LIMIT_REACHED,
            },
        }

        allowed = valid_transitions.get(old_state, set())
        if new_state not in allowed:
            raise RunStateTransitionError(
                f"Invalid lifecycle transition for run '{self.run_id}': "
                f"'{old_state.value}' -> '{new_state.value}'.",
                current_state=old_state.value,
                target_state=new_state.value,
                run_id=self.run_id,
            )

        self._lifecycle_state = new_state
        self._record_lifecycle_change(old_state, new_state)

    def _record_lifecycle_change(
        self, old_state: RunLifecycleState, new_state: RunLifecycleState
    ) -> None:
        """Emit RUN_STATE_CHANGE telemetry record if collector is available."""
        if hasattr(self, "telemetry") and not self.telemetry.is_closed:
            self.telemetry.emit(
                record_type=TelemetryRecordType.RUN_STATE_CHANGE,
                name="run_state_change",
                tick_index=self.current_tick,
                simulation_time_s=self.elapsed_time_s,
                payload={
                    "previous_state": old_state.value,
                    "new_state": new_state.value,
                    "cancellation_reason": self._cancellation_reason,
                },
            )

    def cancel(self, reason: str = "User requested cancellation") -> bool:
        """Request cooperative cancellation of the scenario run between simulation ticks.

        Args:
            reason: Reason for cancellation.

        Returns:
            True if cancellation was accepted or already cancelled.

        Raises:
            RunStateTransitionError: If run is already in a non-cancellable terminal state.
        """
        if self._lifecycle_state == RunLifecycleState.CANCELLED:
            return True

        if self._lifecycle_state in (
            RunLifecycleState.COMPLETED,
            RunLifecycleState.FAILED,
            RunLifecycleState.LIMIT_REACHED,
        ):
            raise RunStateTransitionError(
                f"Cannot cancel run '{self.run_id}' in terminal state "
                f"'{self._lifecycle_state.value}'.",
                current_state=self._lifecycle_state.value,
                target_state=RunLifecycleState.CANCELLED.value,
                run_id=self.run_id,
            )

        self._cancellation_requested = True
        self._cancellation_reason = reason

        if self._lifecycle_state == RunLifecycleState.READY:
            self._transition_to(RunLifecycleState.CANCELLED)

        return True

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
            self._emit_tick_telemetry(tick_result)
            return tick_result
        except Exception as exc:
            raise ScenarioExecutionError(
                f"Scenario execution failed at tick {self.engine.current_tick + 1}: {exc}",
                scenario_id=self.scenario.metadata.id,
                tick=self.engine.current_tick + 1,
                cause=exc,
            ) from exc

    def _emit_tick_telemetry(self, tick_result: TickResult) -> None:
        """Record ordered observations for the completed tick."""
        if not self.telemetry.config.enabled or self.telemetry.is_closed:
            return

        tick = tick_result.tick
        sim_time = tick_result.elapsed_time_s

        # 1. World Snapshot (periodic)
        if tick % self.telemetry.config.snapshot_interval_ticks == 0:
            self.telemetry.emit(
                record_type=TelemetryRecordType.WORLD_SNAPSHOT,
                name="world_snapshot",
                tick_index=tick,
                simulation_time_s=sim_time,
                payload=self.world.get_snapshot().to_dict(),
            )

        # 2. Signals
        if tick_result.signal_states:
            self.telemetry.emit(
                record_type=TelemetryRecordType.SIGNAL_EVENT,
                name="signal_states",
                tick_index=tick,
                simulation_time_s=sim_time,
                payload={
                    sid: st.value if hasattr(st, "value") else str(st)
                    for sid, st in tick_result.signal_states.items()
                },
            )

        # 3. Vehicle States (sorted by vehicle_id for determinism)
        for vid in sorted(tick_result.step_results.keys()):
            s_res = tick_result.step_results[vid]
            self.telemetry.emit(
                record_type=TelemetryRecordType.VEHICLE_STATE,
                name="vehicle_motion",
                tick_index=tick,
                simulation_time_s=sim_time,
                payload=s_res.to_dict(),
                agent_id=vid,
            )

        # 4. Pedestrian States (sorted by pedestrian_id)
        if tick_result.pedestrian_step_results:
            for pid in sorted(tick_result.pedestrian_step_results.keys()):
                p_res = tick_result.pedestrian_step_results[pid]
                payload = p_res.to_dict() if hasattr(p_res, "to_dict") else p_res
                self.telemetry.emit(
                    record_type=TelemetryRecordType.PEDESTRIAN_STATE,
                    name="pedestrian_motion",
                    tick_index=tick,
                    simulation_time_s=sim_time,
                    payload=payload,
                    agent_id=pid,
                )

        # 5. Route changes
        if tick_result.routing_decisions:
            for r_dec in tick_result.routing_decisions:
                self.telemetry.emit(
                    record_type=TelemetryRecordType.ROUTE_CHANGE,
                    name="route_decision",
                    tick_index=tick,
                    simulation_time_s=sim_time,
                    payload=r_dec,
                    agent_id=r_dec.get("vehicle_id"),
                )

        # 6. Communication events
        if tick_result.communication_metrics:
            self.telemetry.emit(
                record_type=TelemetryRecordType.COMMUNICATION_EVENT,
                name="communication_metrics",
                tick_index=tick,
                simulation_time_s=sim_time,
                payload=dict(tick_result.communication_metrics),
            )

        # 7. Coordination events
        if tick_result.coordination_metrics:
            self.telemetry.emit(
                record_type=TelemetryRecordType.COORDINATION_EVENT,
                name="coordination_metrics",
                tick_index=tick,
                simulation_time_s=sim_time,
                payload=dict(tick_result.coordination_metrics),
            )

        # 8. Emergency events
        if tick_result.emergency_events:
            for ev in tick_result.emergency_events:
                self.telemetry.emit(
                    record_type=TelemetryRecordType.EMERGENCY_EVENT,
                    name="emergency_event",
                    tick_index=tick,
                    simulation_time_s=sim_time,
                    payload=ev,
                    agent_id=ev.get("vehicle_id"),
                )

        # 9. AI Decision records
        if tick_result.decision_records:
            for d_rec in tick_result.decision_records:
                self.telemetry.emit(
                    record_type=TelemetryRecordType.DECISION_EVENT,
                    name="decision_outcome",
                    tick_index=tick,
                    simulation_time_s=sim_time,
                    payload=d_rec,
                    agent_id=d_rec.get("vehicle_id"),
                )

        # 10. Safety & Collisions (CRITICAL)
        if tick_result.safety_events:
            for s_ev in tick_result.safety_events:
                is_coll = s_ev.get("event_type") == "collision"
                rec_type = (
                    TelemetryRecordType.COLLISION_EVENT
                    if is_coll
                    else TelemetryRecordType.SAFETY_EVENT
                )
                self.telemetry.emit(
                    record_type=rec_type,
                    name="safety_event",
                    tick_index=tick,
                    simulation_time_s=sim_time,
                    payload=s_ev,
                    agent_id=s_ev.get("vehicle_id_1"),
                )

        # 11. Metrics snapshot
        self.telemetry.emit(
            record_type=TelemetryRecordType.METRICS_SNAPSHOT,
            name="tick_metrics",
            tick_index=tick,
            simulation_time_s=sim_time,
            payload={
                "active_agents": len(tick_result.active_agent_ids),
                "arrived_agents": len(tick_result.arrived_agent_ids),
            },
        )

    def run(
        self,
        ticks: Optional[int] = None,
        target_accels_by_tick: Optional[list[dict[str, float]]] = None,
    ) -> ScenarioExecutionResult:
        """Execute simulation ticks according to configured limits, cancellation, and arrival.

        Args:
            ticks: Optional specific number of ticks to run in this invocation.
            target_accels_by_tick: Optional list of per-tick acceleration mappings.

        Returns:
            ScenarioExecutionResult summarizing execution results and agent states.

        Raises:
            RunStateTransitionError: If attempting to execute a run in a terminal state.
        """
        if self._lifecycle_state == RunLifecycleState.CANCELLED and self._last_result is None:
            return self._build_result(TerminationReason.CANCELLED, is_partial=True)

        if self._lifecycle_state in TERMINAL_LIFECYCLE_STATES:
            raise RunStateTransitionError(
                f"Cannot execute scenario in terminal state '{self._lifecycle_state.value}'.",
                current_state=self._lifecycle_state.value,
                target_state=RunLifecycleState.RUNNING.value,
                run_id=self.run_id,
            )

        if self.engine.status == EngineStatus.PAUSED:
            return self._build_result(TerminationReason.PAUSED)
        if self.engine.status == EngineStatus.STOPPED:
            return self._build_result(TerminationReason.STOPPED)
        if self.engine.status == EngineStatus.FAILED:
            self._transition_to(RunLifecycleState.FAILED)
            return self._build_result(
                TerminationReason.FAILED,
                error_message="Simulation engine is in FAILED state.",
            )

        if self._cancellation_requested:
            self._transition_to(RunLifecycleState.CANCELLED)
            return self._build_result(TerminationReason.CANCELLED, is_partial=True)

        self._transition_to(RunLifecycleState.RUNNING)

        start_tick = self.engine.current_tick
        max_configured_ticks = (
            self.run_config.max_ticks
            if self.run_config.max_ticks is not None
            else self.scenario.effective_max_ticks
        )
        max_duration_s = (
            self.run_config.max_duration_s
            if self.run_config.max_duration_s is not None
            else self.scenario.max_duration_s
        )

        # Check pre-run termination conditions
        agents = self.world.get_agents()
        if (
            self.run_config.stop_on_all_arrived
            and len(agents) > 0
            and all(a.is_arrived for a in agents)
        ):
            self._transition_to(RunLifecycleState.COMPLETED)
            return self._build_result(TerminationReason.ALL_ARRIVED)

        if max_configured_ticks is not None and self.engine.current_tick >= max_configured_ticks:
            self._transition_to(RunLifecycleState.LIMIT_REACHED)
            return self._build_result(TerminationReason.MAX_TICKS_REACHED)

        if max_duration_s is not None and self.engine.elapsed_time_s >= max_duration_s:
            self._transition_to(RunLifecycleState.LIMIT_REACHED)
            return self._build_result(TerminationReason.DURATION_LIMIT_REACHED)

        ticks_to_run = ticks
        accel_idx = 0

        while True:
            # 1. Check cooperative cancellation at tick boundary
            if self._cancellation_requested:
                self._transition_to(RunLifecycleState.CANCELLED)
                return self._build_result(TerminationReason.CANCELLED, is_partial=True)

            # 2. Check engine status
            if self.engine.status == EngineStatus.PAUSED:
                return self._build_result(TerminationReason.PAUSED)
            if self.engine.status == EngineStatus.STOPPED:
                return self._build_result(TerminationReason.STOPPED)

            # 3. Check duration limit
            if max_duration_s is not None and self.engine.elapsed_time_s >= max_duration_s:
                self._transition_to(RunLifecycleState.LIMIT_REACHED)
                return self._build_result(TerminationReason.DURATION_LIMIT_REACHED)

            # 4. Check tick limit
            if (
                max_configured_ticks is not None
                and self.engine.current_tick >= max_configured_ticks
            ):
                self._transition_to(RunLifecycleState.LIMIT_REACHED)
                return self._build_result(TerminationReason.MAX_TICKS_REACHED)

            # 5. Check target ticks for partial invocation
            if ticks_to_run is not None and (self.engine.current_tick - start_tick) >= ticks_to_run:
                return self._build_result(TerminationReason.TARGET_TICKS_COMPLETED, is_partial=True)

            # 6. Command acceleration step
            accels = None
            if target_accels_by_tick and accel_idx < len(target_accels_by_tick):
                accels = target_accels_by_tick[accel_idx]
                accel_idx += 1

            try:
                self.step(target_accels=accels)
            except Exception as exc:
                self._transition_to(RunLifecycleState.FAILED)
                if hasattr(self, "telemetry") and not self.telemetry.is_closed:
                    self.telemetry.emit(
                        record_type=TelemetryRecordType.ERROR,
                        name="step_failure",
                        tick_index=self.engine.current_tick,
                        simulation_time_s=self.engine.elapsed_time_s,
                        payload={"error": str(exc)},
                    )
                return self._build_result(
                    TerminationReason.FAILED,
                    error_message=str(exc),
                )

            # 7. Check post-step arrival condition
            agents = self.world.get_agents()
            if (
                self.run_config.stop_on_all_arrived
                and len(agents) > 0
                and all(a.is_arrived for a in agents)
            ):
                self._transition_to(RunLifecycleState.COMPLETED)
                return self._build_result(TerminationReason.ALL_ARRIVED)

    def run_to_completion(self) -> ScenarioExecutionResult:
        """Run the scenario to completion (either all vehicles arrive or limits reached)."""
        return self.run(ticks=None)

    def reset(self) -> None:
        """Reset scenario state, engine, and telemetry back to initial baseline.

        Raises:
            ScenarioResetError: If resetting the engine or world state fails.
        """
        try:
            self.engine.reset()
            self.tick_history.clear()
            self._initial_tick = self.engine.current_tick
            self.telemetry.clear()
            self._cancellation_requested = False
            self._cancellation_reason = None
            self._lifecycle_state = RunLifecycleState.READY
            self._record_lifecycle_change(RunLifecycleState.CREATED, RunLifecycleState.READY)
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to reset scenario '{self.scenario.metadata.id}': {exc}",
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

    def export_result(
        self,
        indent: Optional[int] = None,
        max_size_bytes: int = 10_000_000,
        max_telemetry_records: Optional[int] = None,
    ) -> str:
        """Export the last execution result as an RFC 8259 valid JSON string.

        Args:
            indent: Optional formatting indentation.
            max_size_bytes: Maximum allowed payload byte size.
            max_telemetry_records: Optional cap on telemetry records.

        Returns:
            JSON string representation.
        """
        if self._last_result is None:
            self._last_result = self._build_result(TerminationReason.STOPPED)
        return self._last_result.to_json(
            indent=indent,
            max_size_bytes=max_size_bytes,
            max_telemetry_records=max_telemetry_records,
        )

    def _build_result(
        self,
        reason: TerminationReason,
        error_message: Optional[str] = None,
        diagnostics: Optional[dict[str, Any]] = None,
        is_partial: bool = False,
    ) -> ScenarioExecutionResult:
        """Construct the immutable ScenarioExecutionResult with aggregated metrics and telemetry."""
        agents = self.world.get_agents()
        arrived = tuple(sorted([a.vehicle.id for a in agents if a.is_arrived]))
        active = tuple(sorted([a.vehicle.id for a in agents if not a.is_arrived]))

        diag = dict(diagnostics or {})
        diag["excluded_vehicle_ids"] = list(self.context.excluded_vehicle_ids)
        diag["engine_status"] = self.engine.status.value
        diag["signal_count"] = self.world.signal_count
        diag["run_id"] = self.run_id

        final_snapshot = self.world.get_snapshot()
        final_fingerprint = compute_world_state_fingerprint(final_snapshot)

        metadata = RunMetadata(
            run_id=self.run_id,
            scenario_id=self.scenario.metadata.id,
            scenario_name=self.scenario.metadata.name,
            scenario_version=self.scenario.metadata.version,
            scenario_fingerprint=self.scenario_fingerprint,
            initial_world_state_fingerprint=self.initial_world_state_fingerprint,
            final_world_state_fingerprint=final_fingerprint,
            commit_sha=self.commit_sha,
            start_simulation_time_s=self._initial_tick * self.engine.time_step_s,
            time_step_s=self.engine.time_step_s,
            seed=self.scenario.seed,
        )

        try:
            metrics_summary = MetricsAggregator.aggregate(
                tick_history=self.tick_history,
                world=self.world,
                total_vehicles=len(agents),
                arrived_vehicles=len(arrived),
                active_vehicles=len(active),
                terminal_state=self._lifecycle_state.value,
                termination_reason=(reason.value if hasattr(reason, "value") else str(reason)),
                elapsed_time_s=self.engine.elapsed_time_s,
                time_step_s=self.engine.time_step_s,
            ).to_dict()
        except Exception as exc:
            self._lifecycle_state = RunLifecycleState.FAILED
            reason = TerminationReason.FAILED
            error_message = f"Metrics aggregation and finalization failed: {exc}"
            metrics_summary = None

        if self.is_terminal and not self.telemetry.is_closed:
            self.telemetry.close()

        records_data = (
            tuple([r.to_dict() for r in self.telemetry.get_records()])
            if self.telemetry.record_count > 0
            else None
        )

        result = ScenarioExecutionResult(
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
            final_world_snapshot=final_snapshot,
            tick_results=tuple(self.tick_history) if self.tick_history else None,
            is_success=(reason not in (TerminationReason.FAILED, TerminationReason.CANCELLED)),
            error_message=error_message,
            diagnostics=diag,
            run_id=self.run_id,
            lifecycle_state=self._lifecycle_state,
            run_metadata=metadata,
            metrics_summary=metrics_summary,
            telemetry_drop_stats=self.telemetry.drop_stats.to_dict(),
            cancellation_reason=self._cancellation_reason,
            telemetry_records=records_data,
            is_partial=is_partial,
        )
        self._last_result = result
        return result
