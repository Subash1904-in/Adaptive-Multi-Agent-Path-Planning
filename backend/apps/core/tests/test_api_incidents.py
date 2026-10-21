"""Integration tests for AMAPP REST API incident injection endpoints.

Verifies:
- GET /api/v1/runs/<run_id>/incidents/ (empty list, filtered by active/resolved)
- POST /api/v1/runs/<run_id>/incidents/ (valid creation, 201 Created)
- Validation errors return RFC 7807 JSON error responses (400 Bad Request)
- Non-existent run returns 404 Run Not Found
- Terminal run mutations return 409 Conflict
- GET /api/v1/runs/<run_id>/incidents/<incident_id>/ returns incident record
- DELETE /api/v1/runs/<run_id>/incidents/<incident_id>/ removes incident and restores baseline
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_simulation_service
from apps.core.scenarios.examples import create_single_vehicle_scenario
from apps.core.scenarios.runner import ScenarioRunner


@pytest.fixture(autouse=True)
def clean_services() -> None:
    """Clear registries before and after each test."""
    default_simulation_service.run_registry.clear()
    default_simulation_service.scenario_registry.clear()
    yield
    default_simulation_service.run_registry.clear()
    default_simulation_service.scenario_registry.clear()


@pytest.fixture
def active_run() -> ScenarioRunner:
    """Create and register a valid ScenarioRunner in READY state."""
    scenario = create_single_vehicle_scenario()
    default_simulation_service.scenario_registry.register(scenario)
    run_id = "test_run_incident_api"
    runner = ScenarioRunner.create(scenario)
    runner.run_id = run_id
    default_simulation_service.run_registry.register(runner)
    return runner


def test_list_incidents_empty(active_run: ScenarioRunner) -> None:
    """GET /runs/<run_id>/incidents/ returns an empty list initially."""
    client = APIClient()
    url = f"/api/v1/runs/{active_run.run_id}/incidents/"
    resp = client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["run_id"] == active_run.run_id
    assert data["total_count"] == 0
    assert data["active_count"] == 0
    assert data["incidents"] == []


def test_create_road_closure_incident(active_run: ScenarioRunner) -> None:
    """POST /runs/<run_id>/incidents/ creates road closure incident and returns 201."""
    client = APIClient()
    url = f"/api/v1/runs/{active_run.run_id}/incidents/"

    edges = active_run.world.road_graph.edge_ids()
    assert len(edges) > 0
    target_edge = edges[0]

    payload = {
        "incident_type": "road_closure",
        "affected_edge_id": target_edge,
        "severity": "high",
        "description": "Downed tree blocking lane",
        "duration_s": 30.0,
    }

    resp = client.post(url, data=payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["incident_type"] == "road_closure"
    assert data["affected_edge_id"] == target_edge
    assert data["status"] == "active"
    assert data["severity"] == "high"
    assert data["duration_s"] == 30.0
    assert "id" in data

    incident_id = data["id"]

    # Verify listing now has 1 incident
    list_resp = client.get(url)
    assert list_resp.status_code == status.HTTP_200_OK
    assert list_resp.json()["total_count"] == 1
    assert list_resp.json()["active_count"] == 1

    # Verify detail retrieval
    detail_url = f"/api/v1/runs/{active_run.run_id}/incidents/{incident_id}/"
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.json()["id"] == incident_id

    # Verify removal
    del_resp = client.delete(detail_url)
    assert del_resp.status_code == status.HTTP_200_OK
    assert del_resp.json()["status"] == "resolved"

    # Verify listing shows 0 active and 1 resolved
    active_resp = client.get(f"{url}?status=active")
    assert active_resp.json()["total_count"] == 0
    resolved_resp = client.get(f"{url}?status=resolved")
    assert resolved_resp.json()["total_count"] == 1


def test_create_congestion_incident(active_run: ScenarioRunner) -> None:
    """POST /runs/<run_id>/incidents/ creates congestion incident."""
    client = APIClient()
    url = f"/api/v1/runs/{active_run.run_id}/incidents/"
    edges = active_run.world.road_graph.edge_ids()
    target_edge = edges[0]

    payload = {
        "incident_type": "congestion",
        "affected_edge_id": target_edge,
        "severity": "medium",
        "congestion_factor": 2.5,
    }

    resp = client.post(url, data=payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["incident_type"] == "congestion"
    assert data["congestion_factor"] == 2.5


def test_incident_validation_error_responses(active_run: ScenarioRunner) -> None:
    """Invalid requests return 400 Bad Request with RFC 7807 problem details."""
    client = APIClient()
    url = f"/api/v1/runs/{active_run.run_id}/incidents/"

    # 1. Invalid target edge
    resp = client.post(
        url,
        data={"incident_type": "road_closure", "affected_edge_id": "non_existent_edge"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    err = resp.json()["error"]
    assert err["code"] == "INVALID_INCIDENT_TARGET"

    # 2. Invalid incident type
    resp = client.post(
        url,
        data={"incident_type": "earthquake_fissure", "affected_edge_id": "edge_1"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Missing target edge for road closure
    resp = client.post(
        url,
        data={"incident_type": "road_closure"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_incident_run_not_found() -> None:
    """Requesting an unknown run returns 404 NOT_FOUND."""
    client = APIClient()
    url = "/api/v1/runs/non_existent_run/incidents/"

    resp = client.get(url)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_terminal_run_rejects_incident_mutations(active_run: ScenarioRunner) -> None:
    """Terminal runs reject incident creation and deletion with 409 Conflict."""
    client = APIClient()
    # Cancel the run to make it terminal
    active_run.cancel(reason="Test termination")

    edges = active_run.world.road_graph.edge_ids()
    target_edge = edges[0]

    # Attempt POST
    post_url = f"/api/v1/runs/{active_run.run_id}/incidents/"
    resp = client.post(
        post_url,
        data={"incident_type": "road_closure", "affected_edge_id": target_edge},
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["error"]["code"] == "TERMINAL_RUN_CONFLICT"
