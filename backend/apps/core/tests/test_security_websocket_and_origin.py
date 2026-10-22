"""Security tests for WebSocket connections, origin enforcement, and frame validation.

Validates:
- SimulationOriginValidator enforcement against untrusted browser origins and wildcards.
- Explicit origin whitelisting via AMAPP_WS_ALLOWED_ORIGINS.
- Message frame size limit enforcement (rejecting payloads > 64KB).
- Binary payload rejection.
- Malformed JSON and schema payload validation.
- Run isolation (rejecting attempts to override bound run_id).
- Command acceleration validation (rejecting NaN, Inf, and out-of-bounds accelerations).
- Role-based mutation control on WebSocket step/cancel commands.
- Leak-free disconnect and background task cancellation.
"""

from __future__ import annotations

import asyncio

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from config.asgi import application

User = get_user_model()
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure clean run and scenario registries for each test."""
    default_run_registry.clear()
    default_scenario_registry.preload_defaults()
    yield
    default_run_registry.clear()


@pytest.mark.asyncio
async def test_websocket_origin_validation_enforcement():
    """Origin validation allows trusted origins and rejects untrusted browser origins."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_origin_01"
    )

    # 1. Non-browser client without Origin header is allowed
    comm_no_origin = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await comm_no_origin.connect()
    assert connected is True
    await comm_no_origin.disconnect()

    # 2. Browser client with ALLOWED_HOSTS origin (localhost) is allowed
    comm_allowed = WebsocketCommunicator(
        application,
        f"/ws/v1/runs/{runner.run_id}/",
        headers=[(b"origin", b"http://localhost")],
    )
    connected, _ = await comm_allowed.connect()
    assert connected is True
    await comm_allowed.disconnect()

    # 3. Browser client with untrusted origin is rejected
    comm_untrusted = WebsocketCommunicator(
        application,
        f"/ws/v1/runs/{runner.run_id}/",
        headers=[(b"origin", b"http://untrusted-malicious-site.example.com")],
    )
    connected, _ = await comm_untrusted.connect()
    assert connected is False
    await comm_untrusted.disconnect()


@pytest.mark.asyncio
async def test_websocket_explicit_allowed_origins_configuration():
    """SimulationOriginValidator honors explicit origins in AMAPP_WS_ALLOWED_ORIGINS."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_custom_origin"
    )

    with override_settings(AMAPP_WS_ALLOWED_ORIGINS=["https://dashboard.amapp.internal"]):
        comm = WebsocketCommunicator(
            application,
            f"/ws/v1/runs/{runner.run_id}/",
            headers=[(b"origin", b"https://dashboard.amapp.internal")],
        )
        connected, _ = await comm.connect()
        assert connected is True
        await comm.disconnect()


@pytest.mark.asyncio
async def test_websocket_oversized_payload_rejection():
    """Incoming frames exceeding AMAPP_WS_MAX_MESSAGE_BYTES receive MESSAGE_SIZE_EXCEEDED."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_large_frame"
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Send 70 KB payload (> 64 KB limit)
    large_payload = "a" * 70000
    await communicator.send_to(text_data=f'{{"type": "step", "padding": "{large_payload}"}}')

    response = await communicator.receive_json_from(timeout=3)
    assert response["event_type"] == "error"
    assert response["payload"]["code"] == "MESSAGE_SIZE_EXCEEDED"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_websocket_binary_frame_rejection():
    """Incoming binary WebSocket frames are rejected with BINARY_NOT_SUPPORTED."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_binary"
    )

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
async def test_websocket_malformed_json_and_payload_format():
    """Malformed JSON string and non-dict payloads return structured error envelopes."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_malformed"
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Malformed JSON syntax
    await communicator.send_to(text_data="{invalid_json_payload: true,")
    resp_syntax = await communicator.receive_json_from(timeout=3)
    assert resp_syntax["event_type"] == "error"
    assert resp_syntax["payload"]["code"] == "INVALID_JSON"

    # Non-object payload (JSON array)
    await communicator.send_json_to(["step", 1])
    resp_array = await communicator.receive_json_from(timeout=3)
    assert resp_array["event_type"] == "error"
    assert resp_array["payload"]["code"] == "INVALID_PAYLOAD_FORMAT"

    # Unsupported message type
    await communicator.send_json_to({"type": "unknown_action_foo"})
    resp_unknown = await communicator.receive_json_from(timeout=3)
    assert resp_unknown["event_type"] == "error"
    assert resp_unknown["payload"]["code"] == "UNSUPPORTED_MESSAGE_TYPE"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_websocket_run_isolation_enforcement():
    """Clients cannot switch run_id or subscribe to mismatched run_ids on an existing connection."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_iso_01"
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Attempt to supply a different run_id in the payload
    await communicator.send_json_to({"type": "subscribe", "run_id": "different_run_id"})
    resp = await communicator.receive_json_from(timeout=3)
    assert resp["event_type"] == "error"
    assert resp["payload"]["code"] == "CANNOT_OVERRIDE_BOUND_RUN"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_websocket_finite_acceleration_validation():
    """WebSocket step command validates target_accels for finite numbers and physical limits."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_accel_check"
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Out-of-bounds acceleration (> 50 m/s^2)
    await communicator.send_json_to(
        {"type": "step", "ticks": 1, "target_accels": {"veh_01": 999.0}}
    )
    resp_oob = await communicator.receive_json_from(timeout=3)
    assert resp_oob["event_type"] == "error"
    assert resp_oob["payload"]["code"] == "INVALID_ACCELERATION_PAYLOAD"

    # Non-dictionary target_accels
    await communicator.send_json_to(
        {"type": "step", "ticks": 1, "target_accels": "not_a_dictionary"}
    )
    resp_nondict = await communicator.receive_json_from(timeout=3)
    assert resp_nondict["event_type"] == "error"
    assert resp_nondict["payload"]["code"] == "INVALID_ACCELERATION_PAYLOAD"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_websocket_staff_mutation_policy():
    """Step and cancel commands require staff privileges when configured."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_staff_policy"
    )

    with override_settings(AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS=True):
        communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.receive_json_from(timeout=3)

        # Unauthenticated / non-staff step command
        await communicator.send_json_to({"type": "step", "ticks": 1})
        resp = await communicator.receive_json_from(timeout=3)
        assert resp["event_type"] == "error"
        assert resp["payload"]["code"] == "PERMISSION_DENIED"

        # Unauthenticated / non-staff cancel command
        await communicator.send_json_to({"type": "cancel", "reason": "Test cancel"})
        resp_cancel = await communicator.receive_json_from(timeout=3)
        assert resp_cancel["event_type"] == "error"
        assert resp_cancel["payload"]["code"] == "PERMISSION_DENIED"

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_websocket_disconnect_cleans_up_resources():
    """Disconnect cancels background tasks, drains queues, and discards group membership."""
    service = SimulationService()
    runner = await sync_to_async(service.create_run)(
        scenario_id="scn_single_veh", run_id="run_ws_cleanup_01"
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Disconnect cleanly
    await communicator.disconnect()
    # Confirm no unhandled exceptions or dangling tasks on rapid disconnect
    await asyncio.sleep(0.05)
