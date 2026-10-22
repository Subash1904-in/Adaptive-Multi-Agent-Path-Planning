"""Tests for simulation run lifecycle persistence and failure handling.

Verifies end-to-end lifecycle recording, non-blocking failure tolerance, duplicate
finalization safety, and backward compatibility with persistence-disabled in-memory runs.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from apps.core.api.services import SimulationService
from apps.core.benchmarking.runner import BenchmarkRunner
from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.persistence.service import SimulationPersistenceService
from apps.core.scenarios.models import RunLifecycleState


@pytest.mark.django_db
class TestPersistenceLifecycleAndFailures:
    """Verifies lifecycle recording, failure containment, and in-memory fallback."""

    def test_successful_simulation_lifecycle_persisted(self) -> None:
        """Simulation run created, stepped to completion, and persisted with final summary."""
        service = SimulationService()
        runner = service.create_run(
            scenario_id="scn_single_veh",
            run_id="run_lifecycle_success_01",
            max_ticks=500,
        )
        assert runner.run_id == "run_lifecycle_success_01"


        db_run = SimulationRun.objects.get(run_id="run_lifecycle_success_01")
        assert db_run.status == RunLifecycleState.READY.value
        assert db_run.scenario_id == "scn_single_veh"
        assert len(db_run.configuration_fingerprint) == 64

        # Step to completion
        service.step_run(run_id="run_lifecycle_success_01", run_to_completion=True)

        db_run.refresh_from_db()
        assert db_run.status == RunLifecycleState.COMPLETED.value
        assert db_run.completed_ticks > 0
        assert db_run.simulation_duration_s is not None
        assert db_run.completion_time is not None
        assert db_run.is_terminal is True

    def test_cancelled_simulation_lifecycle_persisted(self) -> None:
        """Simulation run cancellation properly records CANCELLED terminal state."""
        service = SimulationService()
        service.create_run(
            scenario_id="scn_single_veh",
            run_id="run_lifecycle_cancel_01",
            max_ticks=50,
        )

        service.step_run(run_id="run_lifecycle_cancel_01", ticks=2)
        service.cancel_run(run_id="run_lifecycle_cancel_01", reason="Operator aborted execution")

        db_run = SimulationRun.objects.get(run_id="run_lifecycle_cancel_01")
        assert db_run.status == RunLifecycleState.CANCELLED.value
        assert db_run.error_category == "USER_CANCELLED"
        assert "Operator aborted execution" in (db_run.error_summary or "")
        assert db_run.is_terminal is True

    def test_duplicate_finalization_is_safe_and_idempotent(self) -> None:
        """Calling finalization on an already-terminal run does not corrupt status or timestamps."""
        persist_svc = SimulationPersistenceService()
        persist_svc.record_run_created(
            run_id="run_double_finalize",
            scenario_id="scn_single_veh",
        )
        # First finalization
        res1 = persist_svc.record_run_completed(
            run_id="run_double_finalize",
            completed_ticks=10,
            simulation_duration_s=1.0,
        )
        assert res1.success is True

        db_run = SimulationRun.objects.get(run_id="run_double_finalize")
        first_completion = db_run.completion_time

        # Second finalization call
        res2 = persist_svc.record_run_completed(
            run_id="run_double_finalize",
            completed_ticks=15,
            simulation_duration_s=1.5,
        )
        assert res2.success is True

        db_run.refresh_from_db()
        # Original status, completed_ticks, and completion_time preserved
        assert db_run.status == RunLifecycleState.COMPLETED.value
        assert db_run.completed_ticks == 10
        assert db_run.completion_time == first_completion

    def test_persistence_failure_does_not_crash_simulation_step(self) -> None:
        """A database error during finalization is logged and does not crash the simulation step."""
        service = SimulationService()
        service.create_run(
            scenario_id="scn_single_veh",
            run_id="run_db_error_tolerated",
            max_ticks=10,
        )

        # Simulate database failure during persistence
        with patch.object(
            SimulationPersistenceService,
            "record_run_completed",
            side_effect=RuntimeError("Simulated database locked error"),
        ):
            # Simulation step must still succeed without propagating DB exception
            result = service.step_run(run_id="run_db_error_tolerated", run_to_completion=True)
            assert result["run_id"] == "run_db_error_tolerated"
            assert result["is_terminal"] is True

    def test_persistence_disabled_mode(self) -> None:
        """When persistence is disabled, runs execute normally in-memory without DB rows."""
        service = SimulationService()
        disabled_persist = SimulationPersistenceService(enabled=False)

        with patch("apps.core.persistence.service.default_persistence_service", disabled_persist):
            runner = service.create_run(
                scenario_id="scn_single_veh",
                run_id="run_in_memory_only",
                max_ticks=5,
            )
            assert runner.run_id == "run_in_memory_only"

            result = service.step_run(run_id="run_in_memory_only", ticks=2)
            assert result["current_tick"] == 2

            # No DB row should have been created
            assert not SimulationRun.objects.filter(run_id="run_in_memory_only").exists()

    def test_benchmark_suite_persistence_and_metrics(self) -> None:
        """Executing a benchmark suite persists BenchmarkConfiguration, Trials, and Metrics."""
        runner = BenchmarkRunner()
        report = runner.run_suite(
            algorithms=["astar", "dijkstra"],
            scenarios=["bench_grid_sparse_3x3"],
            trials_per_pair=1,
            base_seed=42,
            max_ticks_override=10,
        )

        # Verify BenchmarkConfiguration was persisted
        assert BenchmarkConfiguration.objects.filter(
            configuration_fingerprint__isnull=False
        ).exists()

        # Verify BenchmarkTrials were persisted
        trials = BenchmarkTrial.objects.filter(benchmark_run_id=report.benchmark_run_id)
        assert trials.count() == 2

        # Verify summary ExperimentMetrics were recorded
        metrics = ExperimentMetric.objects.filter(benchmark_trial__in=trials)
        assert metrics.count() > 0
        for m in metrics:
            assert math.isfinite(m.numeric_value)

    def test_no_per_tick_database_writes(self) -> None:
        """Stepping intermediate ticks in RUNNING state does not issue DB queries per tick."""
        service = SimulationService()
        service.create_run(
            scenario_id="scn_single_veh",
            run_id="run_no_per_tick_db",
            max_ticks=50,
        )

        with patch.object(SimulationPersistenceService, "record_run_started") as mock_started:
            # First step transitions to RUNNING: 1 start notification
            service.step_run(run_id="run_no_per_tick_db", ticks=1)
            assert mock_started.call_count == 1

            # Subsequent steps while RUNNING do not call persistence start again
            service.step_run(run_id="run_no_per_tick_db", ticks=5)
            assert mock_started.call_count == 1
