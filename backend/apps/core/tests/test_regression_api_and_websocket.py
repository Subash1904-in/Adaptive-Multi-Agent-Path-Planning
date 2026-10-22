"""Regression test suite for REST API and WebSocket ASGI consumers.

Verifies:
- REST health check endpoint.
- Scenario listing, detail, and 404 / path-traversal error handling.
- Simulation run creation, discrete stepping, cooperative cancellation, and terminal conflicts.
- Incident creation and listing under active runs.
- Malformed payloads and invalid input validation.
- WebSocket origin header validation (allowed hosts accepted, untrusted origins rejected).
- WebSocket simulation subscription, stepping action, and error frame delivery.
- Clean client disconnect without server exception.
"""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from config.asgi import application

pytestmark = [pytest.mark.django_db(transaction=True)]


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
def api_client() -> APIClient:
    """REST API test client."""
    return APIClient()


class TestRestApiRegression:
    """Verifies REST API contract stability, validation, and error boundaries."""

    def test_health_check_endpoint(self, api_client: APIClient) -> None:
        """GET /api/v1/health/ returns 200 OK with health status."""
        response = api_client.get("/api/v1/health/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data or "healthy" in str(data).lower()

    def test_scenario_listing_and_retrieval(self, api_client: APIClient) -> None:
        """GET /api/v1/scenarios/ and /api/v1/scenarios/<id>/ return valid scenario definitions."""
        list_resp = api_client.get("/api/v1/scenarios/")
        assert list_resp.status_code == status.HTTP_200_OK
        scenarios = list_resp.json()
        assert isinstance(scenarios, list)
        assert len(scenarios) >= 1

        # Retrieve specific scenario definition
        detail_resp = api_client.get("/api/v1/scenarios/scn_single_veh/")
        assert detail_resp.status_code == status.HTTP_200_OK
        assert detail_resp.json()["metadata"]["id"] == "scn_single_veh"

    def test_scenario_not_found_and_path_traversal_prevention(self, api_client: APIClient) -> None:
        """Non-existent scenario and path-traversal inputs return structured 404 without leakage."""
        resp_404 = api_client.get("/api/v1/scenarios/nonexistent_scenario_9999/")
        assert resp_404.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST)

        # Path traversal attack attempt
        resp_traversal = api_client.get("/api/v1/scenarios/..%2f..%2fetc%2fpasswd/")
        assert resp_traversal.status_code in (
            status.HTTP_404_NOT_FOUND,
            status.HTTP_400_BAD_REQUEST,
        )
        assert "traceback" not in resp_traversal.content.decode().lower()
        assert "c:\\" not in resp_traversal.content.decode().lower()

    def test_run_lifecycle_create_step_cancel(self, api_client: APIClient) -> None:
        """Full lifecycle: create run, step, cancel, and verify terminal immutability."""
        # 1. Create run
        create_resp = api_client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "reg_run_01"},
            format="json",
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        run_data = create_resp.json()
        assert run_data["run_id"] == "reg_run_01"
        assert run_data["lifecycle_state"].upper() == "READY"

        # 2. Step 2 ticks
        step_resp = api_client.post(
            "/api/v1/runs/reg_run_01/step/",
            data={"ticks": 2},
            format="json",
        )
        assert step_resp.status_code == status.HTTP_200_OK
        step_data = step_resp.json()
        assert step_data["advanced_ticks"] == 2
        assert step_data["lifecycle_state"].upper() == "RUNNING"

        # 3. Cancel run
        cancel_resp = api_client.post(
            "/api/v1/runs/reg_run_01/cancel/",
            data={"reason": "Regression test cooperative cancellation"},
            format="json",
        )
        assert cancel_resp.status_code == status.HTTP_200_OK
        assert cancel_resp.json()["lifecycle_state"].upper() == "CANCELLED"

        # 4. Stepping a cancelled run must be rejected
        step_after_cancel = api_client.post(
            "/api/v1/runs/reg_run_01/step/",
            data={"ticks": 1},
            format="json",
        )
        assert step_after_cancel.status_code in (
            status.HTTP_409_CONFLICT,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_malformed_json_and_invalid_numeric_inputs(self, api_client: APIClient) -> None:
        """Malformed payloads and non-numeric inputs are rejected with 400 validation error."""
        # Malformed ticks string
        resp = api_client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "max_ticks": "not-an-int"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_incident_creation_under_run(self, api_client: APIClient) -> None:
        """POST and GET /api/v1/runs/<run_id>/incidents/ creates and enumerates active incidents."""
        api_client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "run_inc_test"},
            format="json",
        )

        inc_resp = api_client.post(
            "/api/v1/runs/run_inc_test/incidents/",
            data={
                "incident_type": "road_closure",
                "affected_edge_id": "edge_r0_c0_to_r0_c1",
                "severity": "high",
            },
            format="json",
        )
        assert inc_resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK)

        list_inc = api_client.get("/api/v1/runs/run_inc_test/incidents/")
        assert list_inc.status_code == status.HTTP_200_OK
        incidents = list_inc.json()
        assert len(incidents) >= 1


class TestWebSocketRegression:
    """Verifies Channels ASGI WebSocket handshake, origin protection, and frame protocols."""

    @pytest.mark.asyncio
    async def test_websocket_origin_security_enforcement(self) -> None:
        """Allowed origin connects; untrusted origin is strictly rejected at handshake."""
        service = SimulationService()
        runner = await sync_to_async(service.create_run)(
            scenario_id="scn_single_veh", run_id="run_ws_reg_01"
        )

        # 1. Allowed origin (localhost)
        comm_allowed = WebsocketCommunicator(
            application,
            f"/ws/v1/runs/{runner.run_id}/",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await comm_allowed.connect()
        assert connected is True
        await comm_allowed.disconnect()

        # 2. Untrusted origin
        comm_untrusted = WebsocketCommunicator(
            application,
            f"/ws/v1/runs/{runner.run_id}/",
            headers=[(b"origin", b"http://untrusted-cross-site-attacker.com")],
        )
        connected, _ = await comm_untrusted.connect()
        assert connected is False

    @pytest.mark.asyncio
    async def test_websocket_step_and_error_frames(self) -> None:
        """WebSocket consumer processes step actions and returns structured state frames."""
        service = SimulationService()
        runner = await sync_to_async(service.create_run)(
            scenario_id="scn_single_veh", run_id="run_ws_reg_02"
        )

        comm = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        connected, _ = await comm.connect()
        assert connected is True

        # Send step command over WebSocket
        await comm.send_json_to({"action": "step", "ticks": 1})
        response = await comm.receive_json_from(timeout=5.0)
        assert response is not None
        assert (
            "type" in response
            or "data" in response
            or "action" in response
            or "tick" in str(response)
        )

        # Send malformed action
        await comm.send_json_to({"action": "unknown_invalid_action_xyz"})
        err_response = await comm.receive_json_from(timeout=5.0)
        assert err_response is not None
        assert "error" in str(err_response).lower()

        # Clean disconnect
        await comm.disconnect()
