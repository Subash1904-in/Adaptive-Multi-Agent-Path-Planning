"""Persistence service for AMAPP simulation runs and benchmark history.

Coordinates lifecycle state persistence, benchmark trials, and bounded experiment
metrics via Django ORM with atomic transactions, non-blocking error handling,
and support for disabling persistence in lightweight in-memory environments.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Mapping

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.persistence.fingerprint import (
    canonicalize_for_fingerprint,
    compute_benchmark_config_fingerprint,
    compute_run_config_fingerprint,
)
from apps.core.scenarios.models import RunLifecycleState
from apps.core.telemetry.fingerprint import get_git_commit_sha

logger = logging.getLogger("apps.core.persistence")


@dataclass(frozen=True)
class PersistenceResult:
    """Outcome status of a persistence operation."""

    success: bool
    record_id: str | None = None
    error: str | None = None


def _safe_finite_float(val: Any) -> float | None:
    """Coerce value to a finite float, returning None if non-numeric, NaN, or infinite."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isfinite(f):
            return f
    except (ValueError, TypeError):
        pass
    return None


class SimulationPersistenceService:
    """Manages transactional database persistence for simulation runs and benchmarks."""

    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = getattr(settings, "AMAPP_PERSISTENCE_ENABLED", True)

    def is_enabled(self) -> bool:
        """Return True if persistence is active and database writes are permitted."""
        return self.enabled

    # --------------------------------------------------------------------------
    # Simulation Run Lifecycle Persistence
    # --------------------------------------------------------------------------

    def record_run_created(
        self,
        run_id: str,
        scenario_id: str,
        scenario_version: str = "1.0.0",
        seed: int | None = None,
        seed_policy: str = "FIXED",
        routing_strategy: str = "",
        configuration_snapshot: dict[str, Any] | None = None,
        git_commit_sha: str | None = None,
        schema_version: str = "1.0.0",
        initial_status: RunLifecycleState = RunLifecycleState.READY,
    ) -> PersistenceResult:
        """Create and persist an initial SimulationRun record."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=run_id)

        try:
            sha = git_commit_sha or get_git_commit_sha()
            sanitized_snapshot = (
                canonicalize_for_fingerprint(configuration_snapshot)
                if configuration_snapshot
                else {}
            )

            fingerprint = compute_run_config_fingerprint(
                scenario_id=scenario_id,
                scenario_version=scenario_version,
                seed=seed,
                seed_policy=seed_policy,
                routing_strategy=routing_strategy,
                parameters=sanitized_snapshot.get("parameters"),
                schema_version=schema_version,
            )

            with transaction.atomic():
                run = SimulationRun.objects.create(
                    run_id=run_id,
                    scenario_id=scenario_id,
                    scenario_version=scenario_version,
                    status=initial_status.value,
                    seed=seed,
                    seed_policy=seed_policy,
                    routing_strategy=routing_strategy,
                    configuration_snapshot=sanitized_snapshot,
                    configuration_fingerprint=fingerprint,
                    git_commit_sha=sha,
                    schema_version=schema_version,
                )
            return PersistenceResult(success=True, record_id=run.run_id)
        except Exception as exc:
            logger.error("Failed to persist SimulationRun '%s' creation: %s", run_id, exc)
            return PersistenceResult(success=False, record_id=run_id, error=str(exc))

    def record_run_started(self, run_id: str) -> PersistenceResult:
        """Transition an existing SimulationRun to RUNNING state."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=run_id)

        try:
            with transaction.atomic():
                run = SimulationRun.objects.filter(run_id=run_id).first()
                if not run:
                    logger.warning("SimulationRun '%s' not found for start transition.", run_id)
                    return PersistenceResult(
                        success=False, record_id=run_id, error="Run record not found"
                    )

                if run.is_terminal:
                    return PersistenceResult(
                        success=False,
                        record_id=run_id,
                        error=f"Cannot start run already in terminal state '{run.status}'.",
                    )

                run.transition_to(RunLifecycleState.RUNNING)
            return PersistenceResult(success=True, record_id=run_id)
        except Exception as exc:
            logger.error("Failed to transition SimulationRun '%s' to RUNNING: %s", run_id, exc)
            return PersistenceResult(success=False, record_id=run_id, error=str(exc))

    def record_run_completed(
        self,
        run_id: str,
        completed_ticks: int,
        simulation_duration_s: float,
        summary_metrics: Mapping[str, Any] | None = None,
        target_state: RunLifecycleState = RunLifecycleState.COMPLETED,
    ) -> PersistenceResult:
        """Finalize and persist successful completion of a simulation run."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=run_id)

        try:
            with transaction.atomic():
                run = SimulationRun.objects.filter(run_id=run_id).first()
                if not run:
                    logger.warning("SimulationRun '%s' not found for completion.", run_id)
                    return PersistenceResult(
                        success=False, record_id=run_id, error="Run record not found"
                    )

                if run.is_terminal:
                    logger.warning(
                        "SimulationRun '%s' already in terminal state '%s'. Skipping completion.",
                        run_id,
                        run.status,
                    )
                    return PersistenceResult(success=True, record_id=run_id)

                run.completed_ticks = completed_ticks
                safe_duration = _safe_finite_float(simulation_duration_s) or 0.0
                run.simulation_duration_s = round(safe_duration, 6)
                run.completion_time = timezone.now()
                run.status = target_state.value
                run.save(
                    update_fields=[
                        "completed_ticks",
                        "simulation_duration_s",
                        "completion_time",
                        "status",
                        "updated_at",
                    ]
                )

                if summary_metrics:
                    self._persist_metrics_internal(
                        simulation_run=run,
                        metrics_dict=summary_metrics,
                        sample_tick=completed_ticks,
                        sample_timestamp_s=simulation_duration_s,
                    )

            return PersistenceResult(success=True, record_id=run_id)
        except Exception as exc:
            logger.error("Failed to record completion for SimulationRun '%s': %s", run_id, exc)
            return PersistenceResult(success=False, record_id=run_id, error=str(exc))

    def record_run_failed(
        self,
        run_id: str,
        completed_ticks: int = 0,
        simulation_duration_s: float = 0.0,
        error_category: str | None = None,
        error_summary: str | None = None,
    ) -> PersistenceResult:
        """Persist unrecoverable failure of a simulation run."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=run_id)

        try:
            with transaction.atomic():
                run = SimulationRun.objects.filter(run_id=run_id).first()
                if not run:
                    logger.warning("SimulationRun '%s' not found for failure recording.", run_id)
                    return PersistenceResult(
                        success=False, record_id=run_id, error="Run record not found"
                    )

                if run.is_terminal:
                    return PersistenceResult(success=True, record_id=run_id)

                run.completed_ticks = completed_ticks
                safe_duration = _safe_finite_float(simulation_duration_s) or 0.0
                run.simulation_duration_s = round(safe_duration, 6)
                run.completion_time = timezone.now()
                run.error_category = error_category or "EXECUTION_ERROR"
                run.error_summary = (error_summary or "Simulation failed during execution")[:2000]
                run.status = RunLifecycleState.FAILED.value
                run.save(
                    update_fields=[
                        "completed_ticks",
                        "simulation_duration_s",
                        "completion_time",
                        "error_category",
                        "error_summary",
                        "status",
                        "updated_at",
                    ]
                )
            return PersistenceResult(success=True, record_id=run_id)
        except Exception as exc:
            logger.error("Failed to record failure for SimulationRun '%s': %s", run_id, exc)
            return PersistenceResult(success=False, record_id=run_id, error=str(exc))

    def record_run_cancelled(
        self,
        run_id: str,
        completed_ticks: int = 0,
        simulation_duration_s: float = 0.0,
        reason: str | None = None,
    ) -> PersistenceResult:
        """Persist cooperative cancellation of a simulation run."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=run_id)

        try:
            with transaction.atomic():
                run = SimulationRun.objects.filter(run_id=run_id).first()
                if not run:
                    logger.warning("SimulationRun '%s' not found for cancellation.", run_id)
                    return PersistenceResult(
                        success=False, record_id=run_id, error="Run record not found"
                    )

                if run.is_terminal:
                    return PersistenceResult(success=True, record_id=run_id)

                run.completed_ticks = completed_ticks
                safe_duration = _safe_finite_float(simulation_duration_s) or 0.0
                run.simulation_duration_s = round(safe_duration, 6)
                run.completion_time = timezone.now()
                run.error_category = "USER_CANCELLED"
                run.error_summary = (reason or "User requested cancellation")[:2000]
                run.status = RunLifecycleState.CANCELLED.value
                run.save(
                    update_fields=[
                        "completed_ticks",
                        "simulation_duration_s",
                        "completion_time",
                        "error_category",
                        "error_summary",
                        "status",
                        "updated_at",
                    ]
                )
            return PersistenceResult(success=True, record_id=run_id)
        except Exception as exc:
            logger.error("Failed to record cancellation for SimulationRun '%s': %s", run_id, exc)
            return PersistenceResult(success=False, record_id=run_id, error=str(exc))

    # --------------------------------------------------------------------------
    # Benchmark Suite and Trial Persistence
    # --------------------------------------------------------------------------

    def record_benchmark_suite(
        self,
        benchmark_run_id: str,
        name: str,
        scenario_ids: list[str],
        algorithm_ids: list[str],
        trial_count: int,
        base_seed: int,
        trial_results: list[Any],
        seed_policy: str = "FIXED",
        parameters: dict[str, Any] | None = None,
        description: str = "",
    ) -> PersistenceResult:
        """Persist an immutable BenchmarkConfiguration and its constituent BenchmarkTrials."""
        if not self.enabled:
            return PersistenceResult(success=True, record_id=benchmark_run_id)

        try:
            fingerprint = compute_benchmark_config_fingerprint(
                name=name,
                scenario_ids=scenario_ids,
                algorithm_ids=algorithm_ids,
                trial_count=trial_count,
                base_seed=base_seed,
                seed_policy=seed_policy,
                parameters=parameters,
            )

            with transaction.atomic():
                config, _ = BenchmarkConfiguration.objects.get_or_create(
                    configuration_fingerprint=fingerprint,
                    defaults={
                        "configuration_id": f"cfg_{fingerprint[:16]}",
                        "name": name,
                        "description": description,
                        "scenario_ids": scenario_ids,
                        "algorithm_ids": algorithm_ids,
                        "trial_count": trial_count,
                        "base_seed": base_seed,
                        "seed_policy": seed_policy,
                        "parameters": parameters or {},
                    },
                )

                trials_to_create: list[BenchmarkTrial] = []
                metrics_to_create: list[ExperimentMetric] = []

                for trial in trial_results:
                    # Extract trial attributes safely from trial domain dataclass or dict
                    t_dict = trial.to_dict() if hasattr(trial, "to_dict") else dict(trial)

                    status_val = t_dict.get("status", "failed")
                    if hasattr(status_val, "value"):
                        status_val = status_val.value

                    bt = BenchmarkTrial(
                        benchmark_run_id=benchmark_run_id,
                        benchmark_config=config,
                        scenario_id=str(t_dict.get("scenario_id", "")),
                        scenario_version=str(t_dict.get("scenario_version", "1.0.0")),
                        algorithm_id=str(t_dict.get("algorithm_id", "")),
                        algorithm_version=str(t_dict.get("algorithm_version", "1.0.0")),
                        trial_index=int(t_dict.get("trial_index", 0)),
                        seed=int(t_dict.get("seed", 0)),
                        status=str(status_val),
                        route_feasible=bool(t_dict.get("route_feasible", True)),
                        route_cost=_safe_finite_float(t_dict.get("route_cost")),
                        route_length_m=_safe_finite_float(t_dict.get("route_length_m")),
                        planning_duration_ms=(
                            _safe_finite_float(t_dict.get("planning_duration_ms")) or 0.0
                        ),
                        simulation_duration_s=(
                            _safe_finite_float(t_dict.get("simulation_duration_s")) or 0.0
                        ),
                        simulation_ticks=int(t_dict.get("simulation_ticks", 0)),
                        travel_time_s=_safe_finite_float(t_dict.get("travel_time_s")),
                        completed_trips=int(t_dict.get("completed_trips", 0)),
                        total_trips=int(t_dict.get("total_trips", 0)),
                        completion_rate_pct=_safe_finite_float(t_dict.get("completion_rate_pct")),
                        collision_count=int(t_dict.get("collision_count", 0)),
                        near_miss_count=int(t_dict.get("near_miss_count", 0)),
                        intersection_crossings=int(t_dict.get("intersection_crossings", 0)),
                        reroutes_evaluated=int(t_dict.get("reroutes_evaluated", 0)),
                        reroutes_accepted=int(t_dict.get("reroutes_accepted", 0)),
                        messages_sent=int(t_dict.get("messages_sent", 0)),
                        messages_delivered=int(t_dict.get("messages_delivered", 0)),
                        pdr=_safe_finite_float(t_dict.get("pdr")),
                        incident_count=int(t_dict.get("incident_count", 0)),
                        fallback_count=int(t_dict.get("fallback_count", 0)),
                        started_at=t_dict.get("started_at"),
                        completed_at=t_dict.get("completed_at"),
                        failure_reason=t_dict.get("failure_reason"),
                        diagnostic_summary=t_dict.get("diagnostic_summary", {}),
                    )
                    trials_to_create.append(bt)

                # Save trials in transaction to ensure primary keys exist for metrics
                created_trials: list[BenchmarkTrial] = []
                for bt in trials_to_create:
                    bt.save()
                    created_trials.append(bt)

                # Persist summary metrics for created trials
                for trial_inst in created_trials:
                    if trial_inst.travel_time_s is not None:
                        metrics_to_create.append(
                            ExperimentMetric(
                                benchmark_trial=trial_inst,
                                metric_name="travel_time_s",
                                metric_type="duration",
                                numeric_value=trial_inst.travel_time_s,
                                unit="s",
                            )
                        )
                    if trial_inst.route_length_m is not None:
                        metrics_to_create.append(
                            ExperimentMetric(
                                benchmark_trial=trial_inst,
                                metric_name="route_length_m",
                                metric_type="gauge",
                                numeric_value=trial_inst.route_length_m,
                                unit="m",
                            )
                        )
                    if trial_inst.route_cost is not None:
                        metrics_to_create.append(
                            ExperimentMetric(
                                benchmark_trial=trial_inst,
                                metric_name="route_cost",
                                metric_type="gauge",
                                numeric_value=trial_inst.route_cost,
                                unit="cost",
                            )
                        )

                if metrics_to_create:
                    ExperimentMetric.objects.bulk_create(metrics_to_create, ignore_conflicts=True)


            return PersistenceResult(success=True, record_id=benchmark_run_id)
        except Exception as exc:
            logger.error("Failed to persist benchmark suite '%s': %s", benchmark_run_id, exc)
            return PersistenceResult(success=False, record_id=benchmark_run_id, error=str(exc))

    # --------------------------------------------------------------------------
    # Experiment Metrics Persistence
    # --------------------------------------------------------------------------

    def record_metrics(
        self,
        simulation_run_id: str | None = None,
        benchmark_trial_id: int | None = None,
        metrics_dict: Mapping[str, Any] | None = None,
        sample_tick: int | None = None,
        sample_timestamp_s: float | None = None,
    ) -> PersistenceResult:
        """Persist structured numeric metrics associated with a run or trial."""
        if not self.enabled or not metrics_dict:
            return PersistenceResult(success=True)

        try:
            with transaction.atomic():
                sim_run = (
                    SimulationRun.objects.filter(run_id=simulation_run_id).first()
                    if simulation_run_id
                    else None
                )
                bt = (
                    BenchmarkTrial.objects.filter(id=benchmark_trial_id).first()
                    if benchmark_trial_id
                    else None
                )
                self._persist_metrics_internal(
                    simulation_run=sim_run,
                    benchmark_trial=bt,
                    metrics_dict=metrics_dict,
                    sample_tick=sample_tick,
                    sample_timestamp_s=sample_timestamp_s,
                )
            return PersistenceResult(success=True)
        except Exception as exc:
            logger.error("Failed to record experiment metrics: %s", exc)
            return PersistenceResult(success=False, error=str(exc))

    def _persist_metrics_internal(
        self,
        simulation_run: SimulationRun | None = None,
        benchmark_trial: BenchmarkTrial | None = None,
        metrics_dict: Mapping[str, Any] | None = None,
        sample_tick: int | None = None,
        sample_timestamp_s: float | None = None,
    ) -> None:
        """Helper to validate and bulk create ExperimentMetric records."""
        if not metrics_dict:
            return

        to_create: list[ExperimentMetric] = []
        for name, value in metrics_dict.items():
            if value is None:
                continue

            # Convert boolean or numeric values
            num_val: float | None = None
            if isinstance(value, (int, float)):
                if math.isfinite(value):
                    num_val = float(value)
            elif isinstance(value, dict) and "value" in value:
                v = value["value"]
                if isinstance(v, (int, float)) and math.isfinite(v):
                    num_val = float(v)

            if num_val is None:
                continue

            m_type = "gauge"
            unit = ""
            if isinstance(value, dict):
                m_type = str(value.get("type", "gauge"))
                unit = str(value.get("unit", ""))

            to_create.append(
                ExperimentMetric(
                    simulation_run=simulation_run,
                    benchmark_trial=benchmark_trial,
                    metric_name=str(name),
                    metric_type=m_type,
                    numeric_value=num_val,
                    unit=unit,
                    sample_tick=sample_tick,
                    sample_timestamp_s=sample_timestamp_s,
                )
            )

        if to_create:
            ExperimentMetric.objects.bulk_create(to_create, ignore_conflicts=True)


# Default singleton instance
default_persistence_service = SimulationPersistenceService()
