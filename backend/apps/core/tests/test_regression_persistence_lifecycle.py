"""Regression test suite for simulation persistence and benchmark lifecycle integrity.

Verifies:
1. Migration consistency and schema integrity (no pending unapplied model changes).
2. SimulationRun lifecycle transitions, field defaults, and terminal immutability.
3. BenchmarkConfiguration and BenchmarkTrial relational constraints, cascade behavior, and status.
4. Atomic rollback and failure containment on partial or failed writes.
5. ExperimentMetric validation (rejection of non-finite floats, deterministic ordering).
6. In-memory execution resilience without database persistence side effects.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.core.benchmarking.models import BenchmarkStatus
from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.scenarios.examples import create_single_vehicle_scenario
from apps.core.scenarios.models import RunLifecycleState
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.telemetry.exceptions import RunStateTransitionError


@pytest.mark.django_db
class TestPersistenceLifecycleRegression:
    """Comprehensive regression tests for data persistence and benchmark lifecycle."""

    def test_schema_migration_consistency_and_clean_state(self) -> None:
        """makemigrations --check --dry-run confirms no unmigrated schema drift exists."""
        call_command("makemigrations", "--check", "--dry-run")

    def test_simulation_run_lifecycle_and_transition_invariants(self) -> None:
        """SimulationRun transitions adhere to state machine invariants and terminal locking."""
        run = SimulationRun.objects.create(
            run_id="reg_persist_run_01",
            scenario_id="scn_single_veh",
            seed=42,
            routing_strategy="astar",
            configuration_snapshot={"time_step_s": 0.1, "max_ticks": 50},
            configuration_fingerprint="f" * 64,
        )
        assert run.status == RunLifecycleState.CREATED.value
        assert run.is_terminal is False
        assert run.completed_ticks == 0

        # Normal progression: CREATED -> VALIDATING -> READY -> RUNNING -> COMPLETED
        run.transition_to(RunLifecycleState.VALIDATING)
        assert run.status == RunLifecycleState.VALIDATING.value

        run.transition_to(RunLifecycleState.READY)
        assert run.status == RunLifecycleState.READY.value

        run.transition_to(RunLifecycleState.RUNNING)
        assert run.status == RunLifecycleState.RUNNING.value
        assert run.start_time is not None

        run.transition_to(RunLifecycleState.COMPLETED)
        assert run.status == RunLifecycleState.COMPLETED.value
        assert run.completion_time is not None
        assert run.is_terminal is True

        # Terminal state must reject any further transitions
        with pytest.raises(RunStateTransitionError) as exc_info:
            run.transition_to(RunLifecycleState.RUNNING)
        assert "Cannot transition run" in str(exc_info.value)

    def test_benchmark_trial_persistence_and_configuration_foreign_key(self) -> None:
        """BenchmarkConfiguration links to BenchmarkTrial via related query."""
        config = BenchmarkConfiguration.objects.create(
            configuration_id="reg_bench_cfg_01",
            name="Regression Suite A",
            description="Automated benchmark configuration",
            scenario_ids=["scn_single_veh"],
            algorithm_ids=["astar", "dijkstra"],
            trial_count=2,
            base_seed=123,
            seed_policy="FIXED",
            configuration_fingerprint="c" * 64,
        )

        trial1 = BenchmarkTrial.objects.create(
            benchmark_run_id="bench_run_01",
            benchmark_config=config,
            scenario_id="scn_single_veh",
            algorithm_id="astar",
            trial_index=0,
            seed=123,
            status=BenchmarkStatus.SUCCESS.value,
        )
        BenchmarkTrial.objects.create(
            benchmark_run_id="bench_run_01",
            benchmark_config=config,
            scenario_id="scn_single_veh",
            algorithm_id="dijkstra",
            trial_index=1,
            seed=123,
            status=BenchmarkStatus.FAILED.value,
        )

        # Related manager access
        assert config.trials.count() == 2
        trial_algos = {t.algorithm_id for t in config.trials.all()}
        assert trial_algos == {"astar", "dijkstra"}

        # Status transition
        trial1.execution_time_s = 0.45
        trial1.save()
        trial1.refresh_from_db()
        assert trial1.status == BenchmarkStatus.SUCCESS.value

        # SET_NULL behavior on config deletion
        config.delete()
        trial1.refresh_from_db()
        assert trial1.benchmark_config is None

    def test_atomic_rollback_on_partial_failure(self) -> None:
        """Atomic transaction rolls back partial database mutations if a nested write fails."""
        initial_run_count = SimulationRun.objects.count()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                # 1. Create a valid run
                SimulationRun.objects.create(
                    run_id="atomic_run_valid",
                    scenario_id="scn_single_veh",
                )
                # 2. Trigger an integrity violation by inserting duplicate primary key
                SimulationRun.objects.create(
                    run_id="atomic_run_valid",
                    scenario_id="scn_single_veh",
                )

        # Ensure atomic rollback occurred and the first run was NOT committed
        assert SimulationRun.objects.count() == initial_run_count
        assert not SimulationRun.objects.filter(run_id="atomic_run_valid").exists()

    def test_experiment_metric_bounds_and_deterministic_ordering(self) -> None:
        """ExperimentMetric enforces finite numbers and deterministic ordering."""
        run = SimulationRun.objects.create(
            run_id="metric_run_01",
            scenario_id="scn_single_veh",
        )

        # Valid metrics
        ExperimentMetric.objects.create(
            simulation_run=run,
            metric_name="completion_rate",
            metric_type="ratio",
            numeric_value=1.0,
            unit="ratio",
        )
        ExperimentMetric.objects.create(
            simulation_run=run,
            metric_name="average_speed_mps",
            metric_type="gauge",
            numeric_value=12.5,
            unit="m/s",
        )

        # Non-finite values (NaN / Infinity) must fail clean() validation
        bad_metric = ExperimentMetric(
            simulation_run=run,
            metric_name="infinite_metric",
            numeric_value=float("inf"),
        )
        with pytest.raises(ValidationError):
            bad_metric.clean()

        bad_metric_nan = ExperimentMetric(
            simulation_run=run,
            metric_name="nan_metric",
            numeric_value=float("nan"),
        )
        with pytest.raises(ValidationError):
            bad_metric_nan.clean()

        # Deterministic retrieval
        metrics = list(ExperimentMetric.objects.filter(simulation_run=run).order_by("metric_name"))
        assert len(metrics) == 2
        assert metrics[0].metric_name == "average_speed_mps"
        assert metrics[1].metric_name == "completion_rate"

    def test_in_memory_simulation_without_db_side_effects(self) -> None:
        """Standalone ScenarioRunner runs in-memory without requiring database interaction."""
        from apps.core.scenarios.builder import ScenarioBuilder
        from apps.core.scenarios.models import RunConfig

        scenario = create_single_vehicle_scenario()
        context = ScenarioBuilder(scenario).build()
        runner = ScenarioRunner(context=context, run_config=RunConfig(max_ticks=5))

        runner.run(ticks=5)
        assert runner.current_tick == 5
        assert runner.world is not None
        assert len(runner.tick_history) == 5
        # No simulation run was implicitly persisted to the DB
        assert not SimulationRun.objects.filter(run_id=runner.run_id).exists()
