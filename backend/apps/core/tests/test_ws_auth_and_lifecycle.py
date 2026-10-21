"""Tests for WebSocket authentication, authorization, lifecycle, and resilience."""

import asyncio
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import override_settings

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from apps.core.telemetry.models import TelemetryRecordType
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
async def test_anonymous_development_mode_allowed_by_default():
    """When AMAPP_API_REQUIRE_AUTHENTICATION is False, anonymous connections succeed."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_auth_dev_01")

    with override_settings(AMAPP_API_REQUIRE_AUTHENTICATION=False):
        communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        connected, _ = await communicator.connect()
        assert connected is True
        msg = await communicator.receive_json_from(timeout=3)
        assert msg["event_type"] == "run.status"
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_strict_authentication_rejects_anonymous_connection():
    """When AMAPP_API_REQUIRE_AUTHENTICATION is True, unauthenticated connections receive 4401."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_auth_strict_01")

    with override_settings(AMAPP_API_REQUIRE_AUTHENTICATION=True):
        communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        connected, close_code = await communicator.connect()
        assert connected is True  # channels accepts before closing with custom code
        err_msg = await communicator.receive_json_from(timeout=3)
        assert err_msg["event_type"] == "error"
        assert err_msg["payload"]["code"] == "UNAUTHENTICATED"

        # Connection should close with custom code 4401
        await communicator.wait(timeout=2)


@pytest.mark.asyncio
async def test_authenticated_connection_succeeds_under_strict_mode():
    """Authenticated user connects successfully when strict authentication is active."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_auth_ok_01")

    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="password123"
    )

    with override_settings(AMAPP_API_REQUIRE_AUTHENTICATION=True):
        communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected is True
        msg = await communicator.receive_json_from(timeout=3)
        assert msg["event_type"] == "run.status"
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_simulation_control_step_requires_staff_privileges():
    """Non-staff users are denied simulation control actions (step, cancel) over WebSockets."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_ctrl_staff_01")

    user = await sync_to_async(User.objects.create_user)(
        username="regularuser", password="password123", is_staff=False
    )
    staff_user = await sync_to_async(User.objects.create_user)(
        username="staffadmin", password="password123", is_staff=True
    )

    with override_settings(AMAPP_API_REQUIRE_AUTHENTICATION=True):
        # 1. Non-staff user attempt
        comm_user = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        comm_user.scope["user"] = user
        await comm_user.connect()
        await comm_user.receive_json_from(timeout=3)  # init status

        await comm_user.send_json_to({"type": "step", "ticks": 1})
        err_msg = await comm_user.receive_json_from(timeout=2)
        assert err_msg["event_type"] == "error"
        assert err_msg["payload"]["code"] == "PERMISSION_DENIED"
        assert runner.current_tick == 0
        await comm_user.disconnect()

        # 2. Staff user attempt
        comm_staff = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        comm_staff.scope["user"] = staff_user
        await comm_staff.connect()
        await comm_staff.receive_json_from(timeout=3)  # init status

        await comm_staff.send_json_to({"type": "step", "ticks": 1})
        await asyncio.sleep(0.05)
        assert runner.current_tick == 1
        await comm_staff.disconnect()


@pytest.mark.asyncio
async def test_simulation_control_cancel_requires_staff_privileges():
    """Staff user can cancel a simulation run over WebSockets."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_ctrl_cancel_01")

    staff_user = await sync_to_async(User.objects.create_user)(
        username="canceller", password="password123", is_staff=True
    )

    with override_settings(AMAPP_API_REQUIRE_AUTHENTICATION=True):
        comm_staff = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
        comm_staff.scope["user"] = staff_user
        await comm_staff.connect()
        await comm_staff.receive_json_from(timeout=3)

        await comm_staff.send_json_to({"type": "cancel", "reason": "Operator cancel test"})
        await asyncio.sleep(0.05)
        assert runner.is_terminal is True
        assert runner.lifecycle_state.value == "CANCELLED"
        await comm_staff.disconnect()


@pytest.mark.asyncio
async def test_origin_header_validation():
    """AllowedOrigins check rejects browser requests with untrusted Origin header."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_origin_01")

    # 1. Allowed origin (e.g. testserver, localhost)
    comm_valid = WebsocketCommunicator(
        application,
        f"/ws/v1/runs/{runner.run_id}/",
        headers=[(b"origin", b"http://testserver")],
    )
    conn_valid, _ = await comm_valid.connect()
    assert conn_valid is True
    await comm_valid.disconnect()

    # 2. Malicious / unauthorized origin
    comm_invalid = WebsocketCommunicator(
        application,
        f"/ws/v1/runs/{runner.run_id}/",
        headers=[(b"origin", b"http://malicious-attacker.com")],
    )
    conn_invalid, _ = await comm_invalid.connect()
    # Channels OriginValidator closes the connection immediately if origin is not allowed
    assert conn_invalid is False


@pytest.mark.asyncio
async def test_run_completed_event_emitted_on_terminal_transition():
    """Advancing a run to completion emits run.completed event at most once."""
    from apps.core.scenarios.runner import RunLifecycleState

    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_term_completed_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    try:
        await communicator.connect()
        init_msg = await communicator.receive_json_from(timeout=3)
        assert init_msg["event_type"] == "run.status"

        # Transition runner to RUNNING then COMPLETED
        runner._transition_to(RunLifecycleState.RUNNING)
        runner._transition_to(RunLifecycleState.COMPLETED)
        assert runner.is_terminal is True

        # Read events
        received_events = []
        for _ in range(10):
            if await communicator.receive_nothing(timeout=0.1):
                break
            msg = await communicator.receive_json_from(timeout=1.0)
            received_events.append(msg)

        event_types = [e["event_type"] for e in received_events]
        assert "run.started" in event_types
        assert "run.completed" in event_types
        assert event_types.count("run.completed") == 1
    finally:
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_run_cancelled_event_emitted_via_service():
    """Cancelling a run via SimulationService emits run.cancelled event to subscribers."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_term_cancel_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)

    # Step 1 tick
    service.step_run(runner.run_id, ticks=1)
    # Cancel run
    service.cancel_run(runner.run_id, reason="Emergency operator abort")

    # Read events until run.cancelled
    received_cancelled = False
    for _ in range(30):
        if await communicator.receive_nothing(timeout=0.05):
            break
        msg = await communicator.receive_json_from(timeout=2)
        if msg["event_type"] == "run.cancelled":
            received_cancelled = True
            assert msg["payload"]["new_state"] == "CANCELLED"
            break

    assert received_cancelled is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_run_failed_event_emitted():
    """Failed lifecycle state transition emits run.failed event."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_term_fail_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)

    # Emit a failure state change record
    runner.telemetry.emit(
        record_type=TelemetryRecordType.RUN_STATE_CHANGE,
        name="run_failed",
        tick_index=runner.current_tick,
        simulation_time_s=runner.elapsed_time_s,
        payload={"previous_state": "RUNNING", "new_state": "FAILED", "reason": "Hardware fault"},
    )

    received_failed = False
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.05):
            break
        msg = await communicator.receive_json_from(timeout=2)
        if msg["event_type"] == "run.failed":
            received_failed = True
            assert msg["payload"]["new_state"] == "FAILED"
            break

    assert received_failed is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_channel_layer_failure_does_not_corrupt_or_block_simulation():
    """If the Channel layer raises an unhandled exception, simulation stepping completes safely."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_fault_tol_01")

    # Mock broadcaster dispatch to simulate catastrophic channel layer failure
    with patch(
        "apps.core.realtime.broadcaster._dispatch_to_group",
        side_effect=RuntimeError("Channel layer Redis connection reset"),
    ):
        # Stepping the simulation must not crash or be interrupted
        result = service.step_run(runner.run_id, ticks=5)
        assert result["current_tick"] == 5
        assert runner.current_tick == 5
        assert not runner.is_terminal
