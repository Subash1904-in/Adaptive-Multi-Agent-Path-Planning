"""Unit and integration tests for AMAPP persistence models, constraints, and migrations.

Validates SimulationRun, BenchmarkConfiguration, BenchmarkTrial, and ExperimentMetric
fields, status choices, foreign keys, lifecycle transition validation, unique constraints,
cascade deletions, and rejection of non-finite floats.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError

from apps.core.benchmarking.models import BenchmarkStatus
from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.scenarios.models import RunLifecycleState
from apps.core.telemetry.exceptions import RunStateTransitionError


@pytest.mark.django_db
class TestPersistenceModelsAndMigrations:
    """Verifies schema integrity, constraints, and model lifecycle behavior."""

    def test_makemigrations_check_dry_run(self) -> None:
        """Confirm makemigrations --check --dry-run detects no unapplied model changes."""
        call_command("makemigrations", "--check", "--dry-run")

    def test_simulation_run_crud_and_lifecycle_transitions(self) -> None:
        """Verify SimulationRun model field defaults, status choices, and lifecycle transitions."""
        run = SimulationRun.objects.create(
            run_id="run_test_persist_01",
            scenario_id="scn_single_veh",
            scenario_version="1.0.0",
            seed=42,
            routing_strategy="dijkstra",
            configuration_snapshot={"time_step_s": 0.1, "max_ticks": 100},
            configuration_fingerprint="a" * 64,
        )
        assert run.status == RunLifecycleState.CREATED.value
        assert run.is_terminal is False
        assert run.completed_ticks == 0
        assert str(run) == "SimulationRun(run_test_persist_01, status=CREATED)"

        # Valid transition: CREATED -> VALIDATING -> READY -> RUNNING -> COMPLETED
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

        # Illegal transition from terminal state raises RunStateTransitionError
        with pytest.raises(RunStateTransitionError) as exc_info:
            run.transition_to(RunLifecycleState.RUNNING)
        assert "Cannot transition run" in str(exc_info.value)

    def test_simulation_run_illegal_state_transitions(self) -> None:
        """Verify illegal intermediate state transitions are rejected."""
        run = SimulationRun.objects.create(
            run_id="run_illegal_trans_01",
            scenario_id="scn_single_veh",
            status=RunLifecycleState.CREATED.value,
        )
        # Cannot jump directly from CREATED to COMPLETED
        with pytest.raises(RunStateTransitionError):
            run.transition_to(RunLifecycleState.COMPLETED)

    def test_benchmark_configuration_integrity_and_validation(self) -> None:
        """Verify BenchmarkConfiguration constraints and validation."""
        config = BenchmarkConfiguration(
            configuration_id="cfg_test_valid_01",
            name="Standard Grid Suite",
            description="Reproducible test benchmark",
            scenario_ids=["scn_grid_sparse", "scn_grid_dense"],
            algorithm_ids=["astar", "dijkstra"],
            trial_count=3,
            base_seed=100,
            seed_policy="FIXED",
            configuration_fingerprint="b" * 64,
        )
        config.clean()
        config.save()

        retrieved = BenchmarkConfiguration.objects.get(configuration_id="cfg_test_valid_01")
        assert retrieved.name == "Standard Grid Suite"
        assert len(retrieved.scenario_ids) == 2
        assert len(retrieved.algorithm_ids) == 2

        # Invalid trial_count (< 1) must raise ValidationError
        invalid_config = BenchmarkConfiguration(
            configuration_id="cfg_invalid_01",
            name="Invalid Suite",
            scenario_ids=["scn_1"],
            algorithm_ids=["astar"],
            trial_count=0,
        )
        with pytest.raises(ValidationError) as exc_info:
            invalid_config.clean()
        assert "trial_count" in exc_info.value.message_dict

    def test_benchmark_trial_uniqueness_constraint(self) -> None:
        """Verify unique constraint on trial identity fields."""
        config = BenchmarkConfiguration.objects.create(
            configuration_id="cfg_unique_check",
            name="Unique Check",
            scenario_ids=["scn_1"],
            algorithm_ids=["astar"],
            trial_count=1,
            configuration_fingerprint="c" * 64,
        )

        BenchmarkTrial.objects.create(
            benchmark_run_id="bench_session_01",
            benchmark_config=config,
            scenario_id="scn_1",
            algorithm_id="astar",
            trial_index=0,
            seed=42,
            status=BenchmarkStatus.SUCCESS.value,
            route_feasible=True,
            route_cost=12.5,
            route_length_m=125.0,
            travel_time_s=15.2,
        )

        # Duplicate trial identity must raise IntegrityError
        with pytest.raises(IntegrityError):
            BenchmarkTrial.objects.create(
                benchmark_run_id="bench_session_01",
                benchmark_config=config,
                scenario_id="scn_1",
                algorithm_id="astar",
                trial_index=0,
                seed=42,
                status=BenchmarkStatus.SUCCESS.value,
            )

    def test_benchmark_trial_infeasible_and_null_metrics(self) -> None:
        """Verify that infeasible trials preserve null metrics without converting to zeros."""
        trial = BenchmarkTrial.objects.create(
            benchmark_run_id="bench_infeasible_test",
            scenario_id="scn_partitioned",
            algorithm_id="astar",
            trial_index=0,
            seed=999,
            status=BenchmarkStatus.INFEASIBLE.value,
            route_feasible=False,
            route_cost=None,
            route_length_m=None,
            travel_time_s=None,
            pdr=None,
            failure_reason="Destination unreachable partition",
        )
        assert trial.route_feasible is False
        assert trial.route_cost is None
        assert trial.route_length_m is None
        assert trial.travel_time_s is None
        assert trial.pdr is None

    def test_experiment_metric_finite_validation_and_nan_rejection(self) -> None:
        """Verify ExperimentMetric accepts finite floats and rejects NaN and Infinities."""
        run = SimulationRun.objects.create(
            run_id="run_metrics_check_01",
            scenario_id="scn_single_veh",
            status=RunLifecycleState.COMPLETED.value,
        )

        # Valid finite metric
        m_valid = ExperimentMetric(
            simulation_run=run,
            metric_name="travel_time_mean_s",
            metric_type="duration",
            numeric_value=14.25,
            unit="s",
        )
        m_valid.clean()
        m_valid.save()
        assert m_valid.id is not None

        # NaN must be rejected by clean()
        m_nan = ExperimentMetric(
            simulation_run=run,
            metric_name="invalid_nan",
            numeric_value=float("nan"),
        )
        with pytest.raises(ValidationError) as exc_nan:
            m_nan.clean()
        assert "numeric_value" in exc_nan.value.message_dict

        # Infinity must be rejected by clean()
        m_inf = ExperimentMetric(
            simulation_run=run,
            metric_name="invalid_inf",
            numeric_value=float("inf"),
        )
        with pytest.raises(ValidationError) as exc_inf:
            m_inf.clean()
        assert "numeric_value" in exc_inf.value.message_dict

    def test_cascade_and_set_null_deletion_behavior(self) -> None:
        """Verify on_delete foreign key semantics for runs, configurations, and metrics."""
        config = BenchmarkConfiguration.objects.create(
            configuration_id="cfg_delete_test",
            name="Delete Suite",
            scenario_ids=["scn_1"],
            algorithm_ids=["astar"],
            trial_count=1,
            configuration_fingerprint="d" * 64,
        )
        run = SimulationRun.objects.create(
            run_id="run_delete_test_01",
            scenario_id="scn_1",
        )
        trial = BenchmarkTrial.objects.create(
            benchmark_run_id="bench_del_test",
            benchmark_config=config,
            simulation_run=run,
            scenario_id="scn_1",
            algorithm_id="astar",
            trial_index=0,
            seed=1,
            status=BenchmarkStatus.SUCCESS.value,
        )
        metric = ExperimentMetric.objects.create(
            simulation_run=run,
            benchmark_trial=trial,
            metric_name="test_counter",
            numeric_value=42.0,
        )

        # Deleting BenchmarkConfiguration should SET_NULL on BenchmarkTrial
        config.delete()
        trial.refresh_from_db()
        assert trial.benchmark_config is None

        # Deleting SimulationRun should CASCADE delete its ExperimentMetric
        run.delete()
        assert not ExperimentMetric.objects.filter(id=metric.id).exists()
