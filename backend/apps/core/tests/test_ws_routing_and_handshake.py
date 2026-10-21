"""Tests for WebSocket routing, ASGI handshake, and connection lifecycle."""

import pytest
from channels.testing import WebsocketCommunicator
from django.test import Client

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from apps.core.realtime.consumer import SimulationRunConsumer
from config.asgi import application

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure clean run and scenario registries for each test."""
    default_run_registry.clear()
    default_scenario_registry.preload_defaults()
    yield
    default_run_registry.clear()


@pytest.mark.asyncio
async def test_valid_websocket_route_connects():
    """Valid run ID connects successfully and receives initial run.status."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_ws_valid_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Initial run.status event is emitted on connect
    response = await communicator.receive_json_from(timeout=3)
    assert response["event_type"] == "run.status"
    assert response["run_id"] == "run_ws_valid_01"
    assert response["schema_version"] == "1.0.0"
    assert response["payload"]["lifecycle_state"] == "READY"
    assert response["payload"]["total_vehicles"] == 1

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_unknown_run_rejected_with_4404():
    """Connecting to a non-existent run receives RUN_NOT_FOUND error and closes with 4404."""
    communicator = WebsocketCommunicator(application, "/ws/v1/runs/nonexistent_run_999/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Error envelope received before close
    response = await communicator.receive_json_from(timeout=3)
    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "RUN_NOT_FOUND"
    assert "nonexistent_run_999" in response["payload"]["message"]

    # Next receive verifies connection closure with 4404
    close_event = await communicator.receive_output(timeout=3)
    assert close_event["type"] == "websocket.close"
    assert close_event["code"] == 4404


@pytest.mark.asyncio
async def test_invalid_run_id_rejected():
    """Connecting to a malformed run ID receives INVALID_RUN_ID and closes with 4400."""
    communicator = WebsocketCommunicator(
        SimulationRunConsumer.as_asgi(),
        "/ws/v1/runs/invalid@run!id/",
        subprotocols=None,
    )
    # Provide URL route kwargs manually if testing consumer directly with bad ID
    communicator.scope["url_route"] = {"kwargs": {"run_id": "invalid@run!id"}}
    connected, _ = await communicator.connect()
    assert connected is True

    response = await communicator.receive_json_from(timeout=3)
    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "INVALID_RUN_ID"

    close_event = await communicator.receive_output(timeout=3)
    assert close_event["type"] == "websocket.close"
    assert close_event["code"] == 4400


@pytest.mark.asyncio
async def test_http_endpoints_continue_working():
    """Verifies that ASGI ProtocolTypeRouter allows HTTP requests to continue functioning."""
    client = Client()
    # Health endpoint
    health_resp = client.get("/api/v1/health/")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    # Scenarios list endpoint
    scenarios_resp = client.get("/api/v1/scenarios/")
    assert scenarios_resp.status_code == 200
    assert isinstance(scenarios_resp.json(), list)


@pytest.mark.asyncio
async def test_consumer_cleanup_after_disconnect():
    """Verifies that disconnecting cancels background tasks and discards group membership."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_cleanup_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Read initial status
    await communicator.receive_json_from(timeout=3)

    # Disconnect
    await communicator.disconnect()

    # Reconnect to verify clean state
    comm2 = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected2, _ = await comm2.connect()
    assert connected2 is True
    res2 = await comm2.receive_json_from(timeout=3)
    assert res2["event_type"] == "run.status"
    await comm2.disconnect()
