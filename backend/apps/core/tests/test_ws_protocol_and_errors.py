"""Tests for WebSocket message protocol, validation, and structured error handling."""

import json

import pytest
from channels.testing import WebsocketCommunicator

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from apps.core.realtime.protocol import WEBSOCKET_SCHEMA_VERSION
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
async def test_valid_subscription_delivers_run_status():
    """Sending subscribe action returns run.status with current runner state."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_sub_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Initial status
    await communicator.receive_json_from(timeout=3)

    # Explicit subscribe message
    await communicator.send_json_to({"type": "subscribe"})
    response = await communicator.receive_json_from(timeout=3)
    assert response["event_type"] == "run.status"
    assert response["run_id"] == "run_proto_sub_01"
    assert response["payload"]["lifecycle_state"] == "READY"
    assert response["payload"]["total_vehicles"] == 1

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_valid_unsubscribe_stops_event_delivery():
    """Sending unsubscribe stops live event delivery to the client."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_unsub_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Initial status
    await communicator.receive_json_from(timeout=3)

    # Unsubscribe
    await communicator.send_json_to({"type": "unsubscribe"})
    unsub_resp = await communicator.receive_json_from(timeout=3)
    assert unsub_resp["event_type"] == "run.status"
    assert unsub_resp["payload"]["status"] == "unsubscribed"

    # Step the run via service
    service.step_run(runner.run_id, ticks=1)

    # Verify no simulation event was received
    assert await communicator.receive_nothing(timeout=0.2) is True

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_malformed_json_returns_error_envelope():
    """Sending unparseable JSON returns structured INVALID_JSON error envelope."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_json_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Discard initial status
    await communicator.receive_json_from(timeout=3)

    # Send raw invalid JSON text frame
    await communicator.send_to(text_data="{invalid_json_payload: true, missing_closing_bracket")
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "INVALID_JSON"
    assert "Malformed JSON" in response["payload"]["message"]

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_unsupported_message_type_returns_error():
    """Sending unknown message type returns UNSUPPORTED_MESSAGE_TYPE error envelope."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_unknown_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    await communicator.send_json_to({"type": "fly_to_mars", "altitude": 100000})
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "UNSUPPORTED_MESSAGE_TYPE"
    assert "fly_to_mars" in response["payload"]["message"]

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_invalid_payload_format_returns_error():
    """Sending JSON array or primitive instead of object returns INVALID_PAYLOAD_FORMAT."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_arr_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    await communicator.send_to(text_data=json.dumps(["item1", "item2"]))
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "INVALID_PAYLOAD_FORMAT"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_binary_frame_returns_error():
    """Sending binary WebSocket frame returns BINARY_NOT_SUPPORTED error envelope."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_bin_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    await communicator.send_to(bytes_data=b"\x00\x01\x02\x03\x04")
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "BINARY_NOT_SUPPORTED"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_oversized_message_returns_error():
    """Sending message exceeding max_message_bytes returns MESSAGE_SIZE_EXCEEDED."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_big_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    # Generate oversized payload > 65,536 bytes
    oversized = {"type": "subscribe", "padding": "A" * 70000}
    await communicator.send_to(text_data=json.dumps(oversized))
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "MESSAGE_SIZE_EXCEEDED"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_client_cannot_override_bound_run_id():
    """Supplying a different run_id in the message payload is strictly rejected."""
    service = SimulationService()
    runner1 = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_orig_01")
    service.create_run(scenario_id="scn_single_veh", run_id="run_proto_target_02")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner1.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    # Attempt to hijack or override to run_proto_target_02
    await communicator.send_json_to({"type": "subscribe", "run_id": "run_proto_target_02"})
    response = await communicator.receive_json_from(timeout=3)

    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "CANNOT_OVERRIDE_BOUND_RUN"
    assert "run_proto_orig_01" in response["payload"]["message"]

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_event_envelope_schema_version_and_structure():
    """All outbound messages follow the documented 8-field envelope schema."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_schema_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    response = await communicator.receive_json_from(timeout=3)
    # Required envelope keys
    expected_keys = {
        "schema_version",
        "message_id",
        "event_type",
        "run_id",
        "tick",
        "simulation_time_s",
        "sequence",
        "payload",
    }
    assert expected_keys.issubset(response.keys())
    assert response["schema_version"] == WEBSOCKET_SCHEMA_VERSION
    assert response["run_id"] == "run_proto_schema_01"
    assert isinstance(response["payload"], dict)

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_no_traceback_in_error_payloads():
    """Protocol error payloads do not expose Python tracebacks or internal file paths."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_proto_safe_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.receive_json_from(timeout=3)

    # Malformed JSON
    await communicator.send_to(text_data="{bad_json")
    response = await communicator.receive_json_from(timeout=3)
    res_str = json.dumps(response)

    assert "Traceback" not in res_str
    assert "apps/core" not in res_str
    assert "SimulationRunConsumer" not in res_str

    await communicator.disconnect()
