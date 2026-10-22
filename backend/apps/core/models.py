"""Django ORM models for simulation runs, benchmark history, and experiment metrics.

Provides persistent storage for simulation lifecycles, reproducible benchmark
configurations, individual trial outcomes, and structured experiment metrics.
"""

from __future__ import annotations

import math

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.benchmarking.models import BenchmarkStatus
from apps.core.scenarios.models import (
    TERMINAL_LIFECYCLE_STATES,
    RunLifecycleState,
)
from apps.core.telemetry.exceptions import RunStateTransitionError

# ==============================================================================
# Simulation Run Model
# ==============================================================================


class SimulationRun(models.Model):
    """Represents a single simulation execution run and its lifecycle state."""

    id = models.BigAutoField(primary_key=True)
    run_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique external string identifier for the simulation run.",
    )
    scenario_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Identifier of the scenario executed in this run.",
    )
    scenario_version = models.CharField(
        max_length=32,
        default="1.0.0",
        help_text="Version string of the scenario definition.",
    )
    status = models.CharField(
        max_length=32,
        db_index=True,
        choices=[(s.value, s.value) for s in RunLifecycleState],
        default=RunLifecycleState.CREATED.value,
        help_text="Current lifecycle state of the simulation run.",
    )
    start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when simulation execution began.",
    )
    completion_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when simulation execution completed or terminated.",
    )
    simulation_duration_s = models.FloatField(
        null=True,
        blank=True,
        help_text="Total elapsed simulation time in virtual seconds.",
    )
    completed_ticks = models.IntegerField(
        default=0,
        help_text="Number of discrete simulation ticks completed.",
    )
    configuration_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sanitized dictionary snapshot of the run configuration.",
    )
    configuration_fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default="",
        help_text="Deterministic SHA-256 fingerprint of the normalized configuration.",
    )
    seed = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Base pseudo-random seed used for the run.",
    )
    seed_policy = models.CharField(
        max_length=32,
        default="FIXED",
        help_text="Seed allocation policy (e.g. FIXED, RANDOM).",
    )
    routing_strategy = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Selected routing strategy identifier (e.g. astar, dijkstra, learned).",
    )
    git_commit_sha = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Active Git commit SHA when the run was initialized.",
    )
    schema_version = models.CharField(
        max_length=16,
        default="1.0.0",
        help_text="Schema version string for configuration compatibility.",
    )
    error_category = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Category code if the run encountered an unrecoverable failure.",
    )
    error_summary = models.TextField(
        null=True,
        blank=True,
        help_text="Bounded human-readable summary of the error if failed.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Wall-clock timestamp when the database record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Wall-clock timestamp when the database record was last updated.",
    )

    class Meta:
        db_table = "amapp_simulation_runs"
        ordering = ["-created_at", "-id"]
        verbose_name = "Simulation Run"
        verbose_name_plural = "Simulation Runs"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["scenario_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"SimulationRun({self.run_id}, status={self.status})"

    @property
    def is_terminal(self) -> bool:
        """Return True if the run is in a terminal lifecycle state."""
        return self.status in [s.value for s in TERMINAL_LIFECYCLE_STATES]

    def transition_to(
        self,
        new_state: RunLifecycleState | str,
        error_category: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Validate and apply a lifecycle state transition.

        Raises:
            RunStateTransitionError: If the transition is illegal or the run is already terminal.
        """
        target = new_state.value if isinstance(new_state, RunLifecycleState) else str(new_state)
        current = self.status

        # If already terminal, any state change is strictly prohibited
        if current in [s.value for s in TERMINAL_LIFECYCLE_STATES]:
            raise RunStateTransitionError(
                f"Cannot transition run '{self.run_id}' from terminal state "
                f"'{current}' to '{target}'.",
                run_id=self.run_id,
            )

        valid_transitions: dict[str, set[str]] = {
            RunLifecycleState.CREATED.value: {
                RunLifecycleState.VALIDATING.value,
                RunLifecycleState.READY.value,
                RunLifecycleState.FAILED.value,
                RunLifecycleState.CANCELLED.value,
            },
            RunLifecycleState.VALIDATING.value: {
                RunLifecycleState.READY.value,
                RunLifecycleState.FAILED.value,
                RunLifecycleState.CANCELLED.value,
            },
            RunLifecycleState.READY.value: {
                RunLifecycleState.RUNNING.value,
                RunLifecycleState.CANCELLED.value,
                RunLifecycleState.FAILED.value,
            },
            RunLifecycleState.RUNNING.value: {
                RunLifecycleState.COMPLETED.value,
                RunLifecycleState.LIMIT_REACHED.value,
                RunLifecycleState.CANCELLED.value,
                RunLifecycleState.FAILED.value,
            },
        }

        allowed = valid_transitions.get(current, set())
        if target not in allowed:
            raise RunStateTransitionError(
                f"Illegal state transition for run '{self.run_id}' from '{current}' to '{target}'.",
                run_id=self.run_id,
            )

        self.status = target
        if target == RunLifecycleState.RUNNING.value and not self.start_time:
            self.start_time = timezone.now()
        elif target in [s.value for s in TERMINAL_LIFECYCLE_STATES]:
            if not self.completion_time:
                self.completion_time = timezone.now()

        if error_category:
            self.error_category = error_category
        if error_summary:
            self.error_summary = error_summary[:2000]

        self.save(
            update_fields=[
                "status",
                "start_time",
                "completion_time",
                "error_category",
                "error_summary",
                "updated_at",
            ]
        )


# ==============================================================================
# Benchmark Configuration Model
# ==============================================================================


class BenchmarkConfiguration(models.Model):
    """Represents an immutable, reproducible benchmark experiment configuration."""

    id = models.BigAutoField(primary_key=True)
    configuration_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique identifier for the benchmark configuration.",
    )
    name = models.CharField(
        max_length=128,
        help_text="Descriptive title of the benchmark experiment.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Detailed description of the benchmark goals and parameters.",
    )
    scenario_ids = models.JSONField(
        default=list,
        help_text="List of standardized scenario IDs evaluated in this benchmark.",
    )
    algorithm_ids = models.JSONField(
        default=list,
        help_text="List of routing algorithm IDs compared in this benchmark.",
    )
    trial_count = models.IntegerField(
        default=1,
        help_text="Number of randomized trials evaluated per (scenario, algorithm) pair.",
    )
    base_seed = models.BigIntegerField(
        default=42,
        help_text="Base seed used to derive per-trial seeds.",
    )
    seed_policy = models.CharField(
        max_length=32,
        default="FIXED",
        help_text="Seed policy used (e.g. FIXED, RANDOM).",
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional benchmark parameters and overrides.",
    )
    configuration_fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default="",
        help_text="Deterministic SHA-256 fingerprint of this configuration.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the benchmark configuration was saved.",
    )

    class Meta:
        db_table = "amapp_benchmark_configurations"
        ordering = ["-created_at", "-id"]
        verbose_name = "Benchmark Configuration"
        verbose_name_plural = "Benchmark Configurations"

    def __str__(self) -> str:
        return f"BenchmarkConfiguration({self.configuration_id}, name={self.name})"

    def clean(self) -> None:
        """Validate configuration integrity constraints."""
        super().clean()
        if self.trial_count < 1:
            raise ValidationError({"trial_count": "Trial count must be at least 1."})
        if not isinstance(self.scenario_ids, list) or len(self.scenario_ids) == 0:
            raise ValidationError({"scenario_ids": "At least one scenario ID must be specified."})
        if not isinstance(self.algorithm_ids, list) or len(self.algorithm_ids) == 0:
            raise ValidationError({"algorithm_ids": "At least one algorithm ID must be specified."})


# ==============================================================================
# Benchmark Trial Model
# ==============================================================================


class BenchmarkTrial(models.Model):
    """Represents a single scenario-algorithm trial result in a benchmark run."""

    id = models.BigAutoField(primary_key=True)
    benchmark_run_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Identifier grouping all trials in a benchmark session.",
    )
    benchmark_config = models.ForeignKey(
        BenchmarkConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trials",
        help_text="Optional foreign key to the registered benchmark configuration.",
    )
    simulation_run = models.ForeignKey(
        SimulationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="benchmark_trials",
        help_text="Optional foreign key to the associated SimulationRun.",
    )
    scenario_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Scenario identifier evaluated in this trial.",
    )
    scenario_version = models.CharField(
        max_length=32,
        default="1.0.0",
        help_text="Version string of the evaluated scenario.",
    )
    algorithm_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Routing algorithm identifier evaluated in this trial.",
    )
    algorithm_version = models.CharField(
        max_length=32,
        default="1.0.0",
        help_text="Version string of the evaluated algorithm.",
    )
    trial_index = models.IntegerField(
        default=0,
        help_text="0-indexed trial sequence number for this (scenario, algorithm) pair.",
    )
    seed = models.BigIntegerField(
        help_text="Specific random seed used for this trial.",
    )
    status = models.CharField(
        max_length=32,
        db_index=True,
        choices=[(s.value, s.value) for s in BenchmarkStatus],
        help_text="Outcome status of the trial (success, infeasible, failed, timeout).",
    )
    route_feasible = models.BooleanField(
        default=True,
        help_text="True if a structurally connected route existed between endpoints.",
    )
    route_cost = models.FloatField(
        null=True,
        blank=True,
        help_text="Total calculated route cost, or None if infeasible/failed.",
    )
    route_length_m = models.FloatField(
        null=True,
        blank=True,
        help_text="Total physical route length in meters, or None if infeasible/failed.",
    )
    planning_duration_ms = models.FloatField(
        default=0.0,
        help_text="Wall-clock time spent computing path planning in milliseconds.",
    )
    simulation_duration_s = models.FloatField(
        default=0.0,
        help_text="Virtual elapsed simulation duration in seconds.",
    )
    simulation_ticks = models.IntegerField(
        default=0,
        help_text="Total discrete simulation ticks executed during the trial.",
    )
    travel_time_s = models.FloatField(
        null=True,
        blank=True,
        help_text="Total travel time until destination arrival, or None if incomplete/infeasible.",
    )
    completed_trips = models.IntegerField(
        default=0,
        help_text="Number of vehicles that successfully reached their destination.",
    )
    total_trips = models.IntegerField(
        default=0,
        help_text="Total number of vehicles participating in the trial.",
    )
    completion_rate_pct = models.FloatField(
        null=True,
        blank=True,
        help_text="Percentage of vehicles that arrived at destination.",
    )
    collision_count = models.IntegerField(
        default=0,
        help_text="Total number of physical collision events during the trial.",
    )
    near_miss_count = models.IntegerField(
        default=0,
        help_text="Total number of safety near-miss events during the trial.",
    )
    intersection_crossings = models.IntegerField(
        default=0,
        help_text="Total number of intersection transitions completed.",
    )
    reroutes_evaluated = models.IntegerField(
        default=0,
        help_text="Total number of dynamic reroute checks evaluated.",
    )
    reroutes_accepted = models.IntegerField(
        default=0,
        help_text="Total number of dynamic reroute actions accepted.",
    )
    messages_sent = models.IntegerField(
        default=0,
        help_text="Total V2V packets transmitted during the trial.",
    )
    messages_delivered = models.IntegerField(
        default=0,
        help_text="Total V2V packets successfully delivered to inboxes.",
    )
    pdr = models.FloatField(
        null=True,
        blank=True,
        help_text="V2V Packet Delivery Ratio [0.0, 1.0], or None if no packets transmitted.",
    )
    incident_count = models.IntegerField(
        default=0,
        help_text="Number of active incidents injected during the trial.",
    )
    fallback_count = models.IntegerField(
        default=0,
        help_text="Number of times learned policy triggered conventional fallback.",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="ISO 8601 timestamp when trial started.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="ISO 8601 timestamp when trial completed.",
    )
    failure_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Error message or reason if status is failed or infeasible.",
    )
    diagnostic_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bounded diagnostic metadata (e.g. fallback counters, execution mode).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the trial record was persisted.",
    )

    class Meta:
        db_table = "amapp_benchmark_trials"
        ordering = ["-created_at", "-id"]
        verbose_name = "Benchmark Trial"
        verbose_name_plural = "Benchmark Trials"
        constraints = [
            models.UniqueConstraint(
                fields=["benchmark_run_id", "scenario_id", "algorithm_id", "trial_index"],
                name="unique_benchmark_trial_identity",
            ),
        ]
        indexes = [
            models.Index(fields=["benchmark_run_id", "scenario_id"]),
            models.Index(fields=["algorithm_id", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"BenchmarkTrial({self.benchmark_run_id}, scenario={self.scenario_id}, "
            f"algorithm={self.algorithm_id}, trial={self.trial_index}, status={self.status})"
        )


# ==============================================================================
# Experiment Metric Model
# ==============================================================================


class ExperimentMetric(models.Model):
    """Represents a structured, typed numeric metric sample or summary."""

    METRIC_TYPE_CHOICES = [
        ("counter", "Counter"),
        ("gauge", "Gauge"),
        ("duration", "Duration"),
        ("ratio", "Ratio"),
        ("aggregate", "Aggregate Summary"),
    ]

    id = models.BigAutoField(primary_key=True)
    simulation_run = models.ForeignKey(
        SimulationRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="metrics",
        help_text="Optional foreign key to related SimulationRun.",
    )
    benchmark_trial = models.ForeignKey(
        BenchmarkTrial,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="metrics",
        help_text="Optional foreign key to related BenchmarkTrial.",
    )
    metric_name = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Canonical name of the metric (e.g. travel_time_mean_s, collision_count).",
    )
    metric_type = models.CharField(
        max_length=32,
        choices=METRIC_TYPE_CHOICES,
        default="gauge",
        help_text="Classification of the metric value.",
    )
    numeric_value = models.FloatField(
        help_text="Finite scalar value of the metric. NaN and Infinity are strictly rejected.",
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Physical unit of measurement (e.g. s, m, m/s, ms, count, ratio).",
    )
    sample_tick = models.IntegerField(
        null=True,
        blank=True,
        help_text="Simulation tick at which the sample was recorded, if applicable.",
    )
    sample_timestamp_s = models.FloatField(
        null=True,
        blank=True,
        help_text="Simulation time in seconds at which the sample was recorded.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bounded contextual metadata associated with the metric value.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the metric record was written.",
    )

    class Meta:
        db_table = "amapp_experiment_metrics"
        ordering = ["-created_at", "-id"]
        verbose_name = "Experiment Metric"
        verbose_name_plural = "Experiment Metrics"
        indexes = [
            models.Index(fields=["simulation_run", "metric_name"]),
            models.Index(fields=["benchmark_trial", "metric_name"]),
        ]

    def __str__(self) -> str:
        return f"ExperimentMetric({self.metric_name}={self.numeric_value} {self.unit})"

    def clean(self) -> None:
        """Validate numeric value finiteness."""
        super().clean()
        if not math.isfinite(self.numeric_value):
            raise ValidationError(
                {"numeric_value": "Metric numeric_value must be finite. NaN and Inf are rejected."}
            )
