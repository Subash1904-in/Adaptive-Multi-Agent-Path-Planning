"""Integration tests for Scenario Management REST API endpoints.

Tests scenario listing, detail queries, registration, payload validation,
duplicate conflicts, and schema validation error responses.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_scenario_registry
from apps.core.scenarios.examples import create_single_vehicle_scenario


@pytest.fixture(autouse=True)
def reset_registries():
    """Reset and preload the default scenario registry for each test."""
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()
    yield
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()


@pytest.fixture
def client():
    """Django REST Framework test client."""
    return APIClient()


@pytest.mark.django_db
class TestScenarioListEndpoint:
    """Tests for GET /api/v1/scenarios/."""

    def test_list_scenarios_returns_preloaded_defaults(self, client):
        """Preloaded scenarios should be returned with summary fields."""
        response = client.get("/api/v1/scenarios/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5

        scenario_ids = [s["id"] for s in data]
        assert "scn_single_veh" in scenario_ids
        assert "scn_multi_veh" in scenario_ids
        assert "scn_signalized" in scenario_ids

        # Check summary schema fields
        first = data[0]
        assert "id" in first
        assert "name" in first
        assert "vehicle_count" in first
        assert "road_network_source" in first
        assert "time_step_s" in first


@pytest.mark.django_db
class TestScenarioDetailEndpoint:
    """Tests for GET /api/v1/scenarios/{scenario_id}/."""

    def test_get_existing_scenario_returns_full_definition(self, client):
        """Existing scenario definition is returned with 200 OK."""
        response = client.get("/api/v1/scenarios/scn_single_veh/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["metadata"]["id"] == "scn_single_veh"
        assert len(data["vehicles"]) == 1
        assert "road_network" in data
        assert "disclaimer" in data
        assert "educational simulation" in data["disclaimer"].lower()

    def test_get_nonexistent_scenario_returns_404(self, client):
        """Querying nonexistent scenario returns 404 with standard error envelope."""
        response = client.get("/api/v1/scenarios/nonexistent_scenario_xyz/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "SCENARIO_NOT_FOUND"
        assert "nonexistent_scenario_xyz" in data["error"]["message"]


@pytest.mark.django_db
class TestScenarioCreateEndpoint:
    """Tests for POST /api/v1/scenarios/."""

    def test_create_valid_scenario_success(self, client):
        """Registering a new valid scenario returns 201 Created."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        payload["metadata"]["id"] = "scn_custom_test_01"
        payload["metadata"]["name"] = "Custom Test Scenario"

        response = client.post("/api/v1/scenarios/", data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["metadata"]["id"] == "scn_custom_test_01"
        assert data["metadata"]["name"] == "Custom Test Scenario"
        assert default_scenario_registry.exists("scn_custom_test_01")

    def test_create_duplicate_scenario_id_returns_409(self, client):
        """Attempting to register with an existing ID returns 409 Conflict."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        # scn_single_veh already exists in default preloaded registry
        payload["metadata"]["id"] = "scn_single_veh"

        response = client.post("/api/v1/scenarios/", data=payload, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["error"]["code"] == "DUPLICATE_SCENARIO_ID"
        assert "scn_single_veh" in data["error"]["message"]

    def test_create_scenario_missing_metadata_id_returns_400(self, client):
        """Omitting required metadata ID returns 400 Bad Request."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        payload["metadata"]["id"] = ""

        response = client.post("/api/v1/scenarios/", data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_scenario_invalid_time_step_returns_400(self, client):
        """Negative time step fails validation and returns 400 Bad Request."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        payload["metadata"]["id"] = "scn_invalid_dt"
        payload["time_step_s"] = -0.5

        response = client.post("/api/v1/scenarios/", data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
class TestScenarioValidateEndpoint:
    """Tests for POST /api/v1/scenarios/validate/."""

    def test_validate_valid_scenario_returns_200(self, client):
        """Valid scenario payload returns 200 OK without registering."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        payload["metadata"]["id"] = "scn_validate_only_99"

        response = client.post("/api/v1/scenarios/validate/", data=payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True
        assert data["scenario_id"] == "scn_validate_only_99"
        # Must not be registered in registry
        assert not default_scenario_registry.exists("scn_validate_only_99")

    def test_validate_invalid_scenario_returns_400(self, client):
        """Invalid scenario payload returns 400 Bad Request with details."""
        scenario = create_single_vehicle_scenario()
        payload = scenario.to_dict()
        payload["metadata"]["id"] = "scn_invalid_validate"
        payload["time_step_s"] = 0.0  # Invalid non-positive time step

        response = client.post("/api/v1/scenarios/validate/", data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_register_and_query_rich_pedestrian_and_emergency_scenario(self, client):
        """Rich scenario with pedestrians and emergencies deserializes and registers cleanly."""
        from apps.core.scenarios.examples import (
            create_ambulance_corridor_scenario,
            create_pedestrian_crossing_permitted_scenario,
            create_signalized_scenario,
        )

        for factory, custom_id in [
            (create_signalized_scenario, "scn_rich_signalized_01"),
            (create_pedestrian_crossing_permitted_scenario, "scn_rich_pedestrian_01"),
            (create_ambulance_corridor_scenario, "scn_rich_ambulance_01"),
        ]:
            scn = factory()
            payload = scn.to_dict()
            payload["metadata"]["id"] = custom_id

            resp = client.post("/api/v1/scenarios/", data=payload, format="json")
            assert resp.status_code == status.HTTP_201_CREATED
            assert resp.json()["metadata"]["id"] == custom_id

            # Verify GET detail endpoint
            get_resp = client.get(f"/api/v1/scenarios/{custom_id}/")
            assert get_resp.status_code == status.HTTP_200_OK
            assert get_resp.json()["metadata"]["id"] == custom_id
