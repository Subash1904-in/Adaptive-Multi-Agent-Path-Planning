"""Integration tests for Simulation Run Telemetry, Metrics, and Export REST API endpoints.

Tests querying bounded telemetry streams, computing aggregated cross-subsystem metrics,
retrieving final/intermediate execution results, and RFC 8259 compliant exports with size limits.
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_run_registry, default_scenario_registry


@pytest.fixture(autouse=True)
def clean_registries():
    """Reset and clean run and scenario registries between tests."""
    default_run_registry.clear()
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()
    yield
    default_run_registry.clear()
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()


@pytest.fixture
def client():
    """Django REST Framework test client."""
    return APIClient()


@pytest.fixture
def active_run_id(client):
    """Fixture that initializes a stepped simulation run."""
    run_id = "test_run_telemetry_01"
    client.post(
        "/api/v1/runs/",
        data={"scenario_id": "scn_single_veh", "run_id": run_id, "max_ticks": 40},
        format="json",
    )
    client.post(f"/api/v1/runs/{run_id}/step/", data={"ticks": 10}, format="json")
    return run_id


@pytest.mark.django_db
class TestRunTelemetryEndpoint:
    """Tests for GET /api/v1/runs/{run_id}/telemetry/."""

    def test_query_all_telemetry_records(self, client, active_run_id):
        """Querying without filters returns all buffered records and drop stats."""
        response = client.get(f"/api/v1/runs/{active_run_id}/telemetry/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == active_run_id
        assert data["query_returned_count"] > 0
        assert "records" in data
        assert "drop_stats" in data
        assert "disclaimer" in data

    def test_query_telemetry_filtered_by_tick_range(self, client, active_run_id):
        """Querying with tick_start and tick_end filters records."""
        response = client.get(
            f"/api/v1/runs/{active_run_id}/telemetry/",
            {"tick_start": 2, "tick_end": 5},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for rec in data["records"]:
            assert 2 <= rec["tick_index"] <= 5

    def test_query_telemetry_filtered_by_limit(self, client, active_run_id):
        """Querying with limit caps the returned record count."""
        response = client.get(
            f"/api/v1/runs/{active_run_id}/telemetry/",
            {"limit": 3},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["records"]) <= 3

    def test_query_telemetry_nonexistent_run_returns_404(self, client):
        """Querying telemetry for missing run ID returns 404."""
        response = client.get("/api/v1/runs/phantom_run/telemetry/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.django_db
class TestRunMetricsEndpoint:
    """Tests for GET /api/v1/runs/{run_id}/metrics/."""

    def test_get_metrics_for_active_run(self, client, active_run_id):
        """Active run computes intermediate aggregated metrics summary."""
        response = client.get(f"/api/v1/runs/{active_run_id}/metrics/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == active_run_id
        assert "metrics" in data
        metrics = data["metrics"]
        assert "simulation" in metrics
        assert "kinematics" in metrics
        assert "safety" in metrics
        sim = metrics["simulation"]
        assert "vehicles_registered" in sim
        assert "vehicles_arrived" in sim
        assert "vehicles_active" in sim
        assert "simulated_duration_s" in sim
        assert "time_step_s" in sim

    def test_get_metrics_nonexistent_run_returns_404(self, client):
        """Metrics query on missing run ID returns 404."""
        response = client.get("/api/v1/runs/no_such_run/metrics/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.django_db
class TestRunResultEndpoint:
    """Tests for GET /api/v1/runs/{run_id}/result/."""

    def test_get_result_for_stepped_run(self, client, active_run_id):
        """Intermediate or final result contains full execution result contract."""
        response = client.get(f"/api/v1/runs/{active_run_id}/result/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == active_run_id
        assert data["scenario_id"] == "scn_single_veh"
        assert "total_vehicles" in data
        assert "final_world_snapshot" in data
        assert "is_success" in data
        assert "disclaimer" in data

    def test_get_result_nonexistent_run_returns_404(self, client):
        """Result query on missing run ID returns 404."""
        response = client.get("/api/v1/runs/unknown_run/result/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.django_db
class TestRunExportEndpoint:
    """Tests for GET /api/v1/runs/{run_id}/export/."""

    def test_export_valid_json(self, client, active_run_id):
        """Export returns RFC 8259 valid JSON with correct Content-Type."""
        response = client.get(f"/api/v1/runs/{active_run_id}/export/")
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/json"
        parsed = json.loads(response.content.decode("utf-8"))
        assert "scenario_id" in parsed
        assert parsed["scenario_id"] == "scn_single_veh"
        assert "final_world_snapshot" in parsed

    def test_export_size_limit_exceeded_returns_413(self, client, active_run_id):
        """Configuring max_bytes lower than payload byte size returns HTTP 413."""
        response = client.get(
            f"/api/v1/runs/{active_run_id}/export/",
            {"max_bytes": 100},
        )
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "EXPORT_SIZE_LIMIT_EXCEEDED"
        assert "details" in data["error"]
        assert data["error"]["details"]["max_bytes"] == 100

    def test_export_nonexistent_run_returns_404(self, client):
        """Export query on missing run ID returns 404."""
        response = client.get("/api/v1/runs/ghost_run/export/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "RUN_NOT_FOUND"
