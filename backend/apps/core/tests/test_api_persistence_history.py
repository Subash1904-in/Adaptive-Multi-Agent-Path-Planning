"""Integration tests for historical REST API endpoints.

Tests pagination, filtering, single-resource retrieval, error formatting, read-only
guarantees, and backward compatibility for simulation runs, benchmark configs, and trials.
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.scenarios.models import RunLifecycleState


@pytest.mark.django_db
class TestApiPersistenceHistory:
    """Verifies REST endpoints for historical runs, benchmark configurations,
    trials, and metrics.
    """


    @pytest.fixture
    def client(self) -> APIClient:
        return APIClient()

    def test_list_runs_pagination_and_filters(self, client: APIClient) -> None:
        """GET /api/v1/runs/ with pagination parameters returns bounded, ordered results."""
        # Seed test runs
        for i in range(25):
            SimulationRun.objects.create(
                run_id=f"run_hist_{i:02d}",
                scenario_id="scn_single_veh" if i % 2 == 0 else "scn_multi_veh",
                status=(
                    RunLifecycleState.COMPLETED.value if i < 20 else RunLifecycleState.FAILED.value
                ),
                completed_ticks=10 + i,
                configuration_fingerprint=f"fp_{i}",
            )

        # 1. Test pagination default limit
        resp = client.get("/api/v1/runs/?limit=10&offset=0")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "count" in data
        assert data["count"] == 25
        assert len(data["results"]) == 10
        assert "next" in data
        assert "disclaimer" in data["results"][0]

        # 2. Test status filter
        resp_failed = client.get("/api/v1/runs/?status=FAILED&limit=10")
        assert resp_failed.status_code == status.HTTP_200_OK
        data_failed = resp_failed.json()
        assert data_failed["count"] == 5
        assert all(r["status"] == "FAILED" for r in data_failed["results"])

        # 3. Test scenario_id filter
        resp_scn = client.get("/api/v1/runs/?scenario_id=scn_single_veh&limit=50")
        assert resp_scn.status_code == status.HTTP_200_OK
        data_scn = resp_scn.json()
        assert data_scn["count"] == 13
        assert all(r["scenario_id"] == "scn_single_veh" for r in data_scn["results"])

    def test_retrieve_run_detail_from_database(self, client: APIClient) -> None:
        """GET /api/v1/runs/{run_id}/ retrieves persisted historical run when not in memory."""
        SimulationRun.objects.create(
            run_id="run_persisted_archive_01",
            scenario_id="scn_single_veh",
            status=RunLifecycleState.COMPLETED.value,
            completed_ticks=42,
            simulation_duration_s=4.2,
            configuration_fingerprint="abc123def456",
        )

        resp = client.get("/api/v1/runs/run_persisted_archive_01/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["run_id"] == "run_persisted_archive_01"
        assert data["status"] == "COMPLETED"
        assert data["completed_ticks"] == 42
        assert data["simulation_duration_s"] == 4.2
        assert "disclaimer" in data

    def test_missing_run_returns_standard_404(self, client: APIClient) -> None:
        """Querying a non-existent run ID returns standard 404 with error details."""
        resp = client.get("/api/v1/runs/phantom_run_id_404/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "RUN_NOT_FOUND"

    def test_benchmark_configurations_list_and_detail(self, client: APIClient) -> None:
        """GET /api/v1/benchmarks/configurations/ returns paginated configs."""
        BenchmarkConfiguration.objects.create(
            configuration_id="cfg_hist_test_01",
            name="Urban Grid Benchmark",
            scenario_ids=["scn_grid_sparse"],
            algorithm_ids=["astar", "dijkstra"],
            trial_count=3,
            base_seed=42,
            configuration_fingerprint="fp_benchmark_123",
        )

        # List
        resp_list = client.get("/api/v1/benchmarks/configurations/")
        assert resp_list.status_code == status.HTTP_200_OK
        data_list = resp_list.json()
        assert data_list["count"] >= 1
        assert any(c["configuration_id"] == "cfg_hist_test_01" for c in data_list["results"])

        # Detail
        resp_det = client.get("/api/v1/benchmarks/configurations/cfg_hist_test_01/")
        assert resp_det.status_code == status.HTTP_200_OK
        data_det = resp_det.json()
        assert data_det["configuration_id"] == "cfg_hist_test_01"
        assert data_det["name"] == "Urban Grid Benchmark"

        # Missing configuration 404
        resp_404 = client.get("/api/v1/benchmarks/configurations/non_existent_cfg/")
        assert resp_404.status_code == status.HTTP_404_NOT_FOUND

    def test_benchmark_trials_list_and_detail(self, client: APIClient) -> None:
        """GET /api/v1/benchmarks/trials/ supports filtering by scenario, algorithm, and status."""
        config = BenchmarkConfiguration.objects.create(
            configuration_id="cfg_trial_test",
            name="Trial Test Suite",
            scenario_ids=["scn_1"],
            algorithm_ids=["astar", "learned"],
            trial_count=2,
            configuration_fingerprint="fp_trials_456",
        )

        t1 = BenchmarkTrial.objects.create(
            benchmark_run_id="bench_sess_99",
            benchmark_config=config,
            scenario_id="scn_1",
            algorithm_id="astar",
            trial_index=0,
            seed=101,
            status="success",
            travel_time_s=12.4,
            route_cost=10.0,
        )
        BenchmarkTrial.objects.create(
            benchmark_run_id="bench_sess_99",
            benchmark_config=config,
            scenario_id="scn_1",
            algorithm_id="learned",
            trial_index=0,
            seed=101,
            status="failed",
            travel_time_s=None,
            route_cost=None,
            failure_reason="Safety collision threshold exceeded",
        )

        # List all
        resp_list = client.get("/api/v1/benchmarks/trials/?benchmark_run_id=bench_sess_99")
        assert resp_list.status_code == status.HTTP_200_OK
        assert resp_list.json()["count"] == 2

        # Filter by algorithm
        resp_algo = client.get("/api/v1/benchmarks/trials/?algorithm_id=learned")
        assert resp_algo.status_code == status.HTTP_200_OK
        data_algo = resp_algo.json()
        assert data_algo["count"] == 1
        assert data_algo["results"][0]["algorithm_id"] == "learned"
        assert data_algo["results"][0]["travel_time_s"] is None

        # Detail
        resp_det = client.get(f"/api/v1/benchmarks/trials/{t1.id}/")
        assert resp_det.status_code == status.HTTP_200_OK
        assert resp_det.json()["id"] == t1.id
        assert resp_det.json()["travel_time_s"] == 12.4

        # Missing trial 404
        resp_miss = client.get("/api/v1/benchmarks/trials/999999/")
        assert resp_miss.status_code == status.HTTP_404_NOT_FOUND

    def test_run_metrics_historical_endpoint(self, client: APIClient) -> None:
        """GET /api/v1/runs/{run_id}/metrics/?persisted=true returns paginated ExperimentMetrics."""
        run = SimulationRun.objects.create(
            run_id="run_with_metrics_hist",
            scenario_id="scn_single_veh",
            status=RunLifecycleState.COMPLETED.value,
        )
        for i in range(5):
            ExperimentMetric.objects.create(
                simulation_run=run,
                metric_name=f"metric_{i}",
                metric_type="gauge",
                numeric_value=10.0 + i,
                unit="m/s",
            )

        resp = client.get("/api/v1/runs/run_with_metrics_hist/metrics/?persisted=true")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 5
        assert len(data["results"]) == 5
        assert data["results"][0]["numeric_value"] is not None

    def test_read_only_guarantee_on_historical_endpoints(self, client: APIClient) -> None:
        """POST, PUT, DELETE requests on benchmark history endpoints are rejected with 405."""
        resp_post_cfg = client.post("/api/v1/benchmarks/configurations/", data={})
        assert resp_post_cfg.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        resp_post_trial = client.post("/api/v1/benchmarks/trials/", data={})
        assert resp_post_trial.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
