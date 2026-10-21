"""Integration tests for Simulation Run Lifecycle and Stepping REST API endpoints.

Tests run initialization, listing, point-in-time status queries, discrete stepping,
multi-tick advancement, completion runs, cooperative cancellation, and lifecycle conflicts.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_run_registry, default_scenario_registry
from apps.core.scenarios.examples import create_single_vehicle_scenario


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


@pytest.mark.django_db
class TestRunCreationEndpoints:
    """Tests for POST /api/v1/runs/ and GET /api/v1/runs/."""

    def test_list_runs_initially_empty(self, client):
        """Listing runs when none are registered returns an empty list."""
        response = client.get("/api/v1/runs/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_create_run_from_scenario_id_success(self, client):
        """Creating a run referencing an existing scenario ID returns 201 in READY state."""
        payload = {
            "scenario_id": "scn_single_veh",
            "run_id": "test_run_single_01",
            "max_ticks": 50,
        }
        response = client.post("/api/v1/runs/", data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["run_id"] == "test_run_single_01"
        assert data["scenario_id"] == "scn_single_veh"
        assert data["lifecycle_state"] == "READY"
        assert data["current_tick"] == 0
        assert data["elapsed_time_s"] == 0.0
        assert data["is_terminal"] is False
        assert data["total_vehicles"] == 1
        assert "disclaimer" in data

        # Check listing now includes the created run
        list_resp = client.get("/api/v1/runs/")
        assert list_resp.status_code == status.HTTP_200_OK
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["run_id"] == "test_run_single_01"

    def test_create_run_with_auto_generated_id(self, client):
        """Omitting explicit run_id auto-generates a unique run ID."""
        payload = {"scenario_id": "scn_single_veh"}
        response = client.post("/api/v1/runs/", data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["run_id"].startswith("run_scn_single_veh_")
        assert default_run_registry.exists(data["run_id"])

    def test_create_run_duplicate_id_returns_409(self, client):
        """Attempting to create two runs with the same run_id returns 409 Conflict."""
        payload = {"scenario_id": "scn_single_veh", "run_id": "duplicate_run_id"}
        resp1 = client.post("/api/v1/runs/", data=payload, format="json")
        assert resp1.status_code == status.HTTP_201_CREATED

        resp2 = client.post("/api/v1/runs/", data=payload, format="json")
        assert resp2.status_code == status.HTTP_409_CONFLICT
        data = resp2.json()
        assert data["error"]["code"] == "DUPLICATE_RUN_ID"

    def test_create_run_nonexistent_scenario_returns_404(self, client):
        """Referencing a missing scenario_id returns 404 Not Found."""
        payload = {"scenario_id": "missing_scn_id_404"}
        response = client.post("/api/v1/runs/", data=payload, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "SCENARIO_NOT_FOUND"

    def test_create_run_missing_both_id_and_inline_scenario_returns_400(self, client):
        """Missing both scenario_id and inline scenario returns 400 Bad Request."""
        payload = {"run_id": "orphaned_run"}
        response = client.post("/api/v1/runs/", data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_run_with_inline_scenario_success(self, client):
        """Creating a run with an inline scenario definition returns 201 Created."""
        scenario = create_single_vehicle_scenario()
        scn_dict = scenario.to_dict()
        scn_dict["metadata"]["id"] = "inline_scn_run_test"

        payload = {
            "scenario": scn_dict,
            "run_id": "inline_run_01",
        }
        response = client.post("/api/v1/runs/", data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["run_id"] == "inline_run_01"
        assert data["scenario_id"] == "inline_scn_run_test"


@pytest.mark.django_db
class TestRunSteppingAndLifecycleEndpoints:
    """Tests for run stepping, cancellation, and lifecycle state transitions."""

    def test_get_run_detail_returns_status(self, client):
        """GET /api/v1/runs/{run_id}/ returns current run state."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_detail_test"},
            format="json",
        )
        response = client.get("/api/v1/runs/run_detail_test/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == "run_detail_test"
        assert data["lifecycle_state"] == "READY"
        assert data["current_tick"] == 0

    def test_get_nonexistent_run_detail_returns_404(self, client):
        """Querying nonexistent run ID returns 404 Not Found."""
        response = client.get("/api/v1/runs/ghost_run_404/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["code"] == "RUN_NOT_FOUND"

    def test_step_single_tick(self, client):
        """Stepping default advances simulation by exactly 1 tick."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_step_single"},
            format="json",
        )
        response = client.post("/api/v1/runs/run_step_single/step/", data={}, format="json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == "run_step_single"
        assert data["current_tick"] == 1
        assert data["elapsed_time_s"] == pytest.approx(0.1, abs=1e-4)
        assert data["lifecycle_state"] == "RUNNING"
        assert "tick_result" in data

    def test_step_multi_ticks(self, client):
        """Stepping with ticks=5 advances simulation by 5 ticks."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_step_multi"},
            format="json",
        )
        response = client.post(
            "/api/v1/runs/run_step_multi/step/",
            data={"ticks": 5},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["current_tick"] == 5
        assert data["advanced_ticks"] == 5
        assert data["elapsed_time_s"] == pytest.approx(0.5, abs=1e-4)
        assert "last_tick_result" in data

    def test_run_to_completion(self, client):
        """POST step with run_to_completion=True executes until arrival or termination."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_complete_test", "max_ticks": 80},
            format="json",
        )
        response = client.post(
            "/api/v1/runs/run_complete_test/step/",
            data={"run_to_completion": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_terminal"] is True
        assert data["lifecycle_state"] in ("COMPLETED", "LIMIT_REACHED")
        assert data["current_tick"] > 0

    def test_step_terminal_run_returns_409(self, client):
        """Attempting to step a completed or terminated run returns 409 Conflict."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_term_conflict", "max_ticks": 50},
            format="json",
        )
        # Run to completion
        client.post(
            "/api/v1/runs/run_term_conflict/step/",
            data={"run_to_completion": True},
            format="json",
        )

        # Attempt further step
        response = client.post(
            "/api/v1/runs/run_term_conflict/step/",
            data={"ticks": 1},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["error"]["code"] == "LIFECYCLE_CONFLICT"

    def test_cooperative_cancellation_success(self, client):
        """Cooperative cancellation transitions active run to CANCELLED state."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_cancel_test"},
            format="json",
        )
        client.post("/api/v1/runs/run_cancel_test/step/", data={"ticks": 2}, format="json")

        cancel_resp = client.post(
            "/api/v1/runs/run_cancel_test/cancel/",
            data={"reason": "Operator requested stop"},
            format="json",
        )
        assert cancel_resp.status_code == status.HTTP_200_OK
        data = cancel_resp.json()
        assert data["lifecycle_state"] == "CANCELLED"
        assert data["is_terminal"] is True
        assert data["cancellation_reason"] == "Operator requested stop"

    def test_cancel_already_completed_run_returns_409(self, client):
        """Attempting to cancel a completed run returns 409 Conflict."""
        client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_cancel_term", "max_ticks": 40},
            format="json",
        )
        # Complete run
        client.post(
            "/api/v1/runs/run_cancel_term/step/",
            data={"run_to_completion": True},
            format="json",
        )

        # Cancel should fail with 409
        response = client.post(
            "/api/v1/runs/run_cancel_term/cancel/",
            data={"reason": "Late cancel"},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["error"]["code"] == "LIFECYCLE_CONFLICT"
