"""Tests for database failure tolerance, transaction rollback, and persistence containment.

Validates:
- Database failure containment: SimulationPersistenceService catches database exceptions and returns
  PersistenceResult(success=False) without breaking active simulation execution.
- In-memory execution: When AMAPP_PERSISTENCE_ENABLED is False, persistence operations return
  PersistenceResult(success=True) without accessing the database.
- Idempotent finalization: Duplicate completion or failure transitions on terminal runs
  do not error.
- Non-finite float filtering: NaN, +Inf, -Inf metrics and duration values are safely coerced
  or filtered.
- Atomic transaction containment: Partial failures during benchmark suite persistence rollback
  cleanly.
"""

from __future__ import annotations

from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase

from apps.core.models import BenchmarkConfiguration, BenchmarkTrial, ExperimentMetric, SimulationRun
from apps.core.persistence.service import (
    SimulationPersistenceService,
    _safe_finite_float,
)
from apps.core.scenarios.models import RunLifecycleState


class PersistenceFailureContainmentTestCase(TestCase):
    """Verifies non-blocking failure tolerance and data integrity in persistence operations."""

    def setUp(self) -> None:
        self.service = SimulationPersistenceService(enabled=True)

    def test_safe_finite_float_helper(self) -> None:
        """_safe_finite_float coerces valid finite floats and converts NaN/Inf to None."""
        assert _safe_finite_float(42.5) == 42.5
        assert _safe_finite_float("12.34") == 12.34
        assert _safe_finite_float(0) == 0.0
        assert _safe_finite_float(float("nan")) is None
        assert _safe_finite_float(float("inf")) is None
        assert _safe_finite_float(float("-inf")) is None
        assert _safe_finite_float("not_a_number") is None
        assert _safe_finite_float(None) is None

    def test_database_operational_error_containment_on_create(self) -> None:
        """Database errors during run creation return failure result without throwing."""
        with patch.object(
            SimulationRun.objects, "create", side_effect=OperationalError("Disk full")
        ):
            result = self.service.record_run_created(
                run_id="run_fail_contain_01",
                scenario_id="scn_single_veh",
            )
            assert result.success is False
            assert "Disk full" in (result.error or "")

    def test_database_operational_error_containment_on_complete(self) -> None:
        """Database errors during run completion return failure result without throwing."""
        self.service.record_run_created(
            run_id="run_fail_contain_02",
            scenario_id="scn_single_veh",
        )
        with patch.object(SimulationRun, "save", side_effect=OperationalError("Connection lost")):
            result = self.service.record_run_completed(
                run_id="run_fail_contain_02",
                completed_ticks=10,
                simulation_duration_s=1.0,
            )
            assert result.success is False
            assert "Connection lost" in (result.error or "")

    def test_in_memory_mode_skips_database_access(self) -> None:
        """When disabled, persistence service returns success without database interaction."""
        in_memory_service = SimulationPersistenceService(enabled=False)
        assert in_memory_service.is_enabled() is False

        with patch.object(SimulationRun.objects, "create") as mock_create:
            result = in_memory_service.record_run_created(
                run_id="run_in_memory",
                scenario_id="scn_single_veh",
            )
            assert result.success is True
            assert result.record_id == "run_in_memory"
            mock_create.assert_not_called()

    def test_duplicate_finalization_is_idempotent(self) -> None:
        """Attempting to finalize an already-terminal run is idempotent and safe."""
        run_id = "run_idempotent_01"
        self.service.record_run_created(run_id=run_id, scenario_id="scn_single_veh")
        self.service.record_run_started(run_id=run_id)

        # First completion
        res1 = self.service.record_run_completed(
            run_id=run_id,
            completed_ticks=50,
            simulation_duration_s=5.0,
        )
        assert res1.success is True

        # Duplicate completion
        res2 = self.service.record_run_completed(
            run_id=run_id,
            completed_ticks=60,
            simulation_duration_s=6.0,
        )
        assert res2.success is True

        # Status remains COMPLETED with original ticks
        run = SimulationRun.objects.get(run_id=run_id)
        assert run.status == RunLifecycleState.COMPLETED.value
        assert run.completed_ticks == 50

    def test_non_finite_metric_coercion_and_filtering(self) -> None:
        """Non-finite metric values (NaN, Inf) are filtered out, preventing DB corruption."""
        run_id = "run_finite_metrics_01"
        self.service.record_run_created(run_id=run_id, scenario_id="scn_single_veh")

        # Record metrics with mixed finite and non-finite values
        metrics = {
            "valid_gauge": 42.0,
            "nan_metric": float("nan"),
            "inf_metric": float("inf"),
            "negative_inf_metric": float("-inf"),
            "valid_counter": 10,
        }
        res = self.service.record_metrics(
            simulation_run_id=run_id,
            metrics_dict=metrics,
            sample_tick=5,
            sample_timestamp_s=0.5,
        )
        assert res.success is True

        # Verify only finite metrics were created in database
        saved_names = set(
            ExperimentMetric.objects.filter(simulation_run__run_id=run_id).values_list(
                "metric_name", flat=True
            )
        )
        assert "valid_gauge" in saved_names
        assert "valid_counter" in saved_names
        assert "nan_metric" not in saved_names
        assert "inf_metric" not in saved_names
        assert "negative_inf_metric" not in saved_names

    def test_benchmark_suite_transaction_containment_on_error(self) -> None:
        """If benchmark persistence fails mid-operation, the transaction rolls back cleanly."""
        trial_data = [
            {
                "scenario_id": "scn_single_veh",
                "algorithm_id": "astar",
                "trial_index": 0,
                "seed": 42,
                "status": "COMPLETED",
                "route_cost": float("nan"),  # Non-finite float coerced safely
                "planning_duration_ms": 15.0,
                "simulation_duration_s": 2.5,
            }
        ]

        # Simulate exception during trial saving
        with patch.object(BenchmarkTrial, "save", side_effect=OperationalError("Disk failure")):
            res = self.service.record_benchmark_suite(
                benchmark_run_id="bench_fail_run_01",
                name="Failure Containment Config",
                scenario_ids=["scn_single_veh"],
                algorithm_ids=["astar"],
                trial_count=1,
                base_seed=42,
                trial_results=trial_data,
            )
            assert res.success is False
            assert "Disk failure" in (res.error or "")

        # Verify no orphan BenchmarkConfiguration was committed
        assert not BenchmarkConfiguration.objects.filter(name="Failure Containment Config").exists()
