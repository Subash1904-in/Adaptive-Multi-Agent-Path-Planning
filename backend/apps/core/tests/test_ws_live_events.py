"""Tests for real-time simulation event streaming, scope isolation, and domain event types."""

import pytest
from channels.testing import WebsocketCommunicator

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
from apps.core.scenarios.examples import (
    create_ambulance_corridor_scenario,
    create_pedestrian_crossing_permitted_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
)
from apps.core.telemetry.models import TelemetryConfig, TelemetryRecordType
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
async def test_vehicle_update_and_metrics_delivered_on_step():
    """Stepping a simulation run broadcasts vehicle.updated and metrics.snapshot events."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_live_veh_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Read initial run.status
    init_msg = await communicator.receive_json_from(timeout=3)
    assert init_msg["event_type"] == "run.status"

    # Step run by 1 tick via service
    service.step_run(runner.run_id, ticks=1)

    # Collect emitted events for the tick
    received_types = []
    for _ in range(8):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        received_types.append(msg["event_type"])
        assert msg["run_id"] == "run_live_veh_01"
        assert msg["tick"] in (0, 1)

    assert "vehicle.updated" in received_types
    assert "metrics.snapshot" in received_types

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_world_snapshot_event_delivered():
    """Snapshot interval tick triggers world.snapshot event delivery."""
    service = SimulationService()
    # Telemetry with snapshot interval = 1 tick
    t_cfg = TelemetryConfig(snapshot_interval_ticks=1)
    runner = service.create_run(
        scenario_id="scn_single_veh",
        run_id="run_live_snap_01",
        telemetry_config=t_cfg,
    )

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    service.step_run(runner.run_id, ticks=1)

    received_types = []
    for _ in range(6):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        received_types.append(msg["event_type"])
        if msg["event_type"] == "world.snapshot":
            assert "vehicles" in msg["payload"]

    assert "world.snapshot" in received_types

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_pedestrian_event_delivered():
    """Pedestrian scenario broadcasts pedestrian.updated events upon stepping."""
    service = SimulationService()
    scn = create_pedestrian_crossing_permitted_scenario()
    runner = service.create_run(scenario=scn, run_id="run_live_ped_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    service.step_run(runner.run_id, ticks=1)

    received_types = []
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        received_types.append(msg["event_type"])

    assert "pedestrian.updated" in received_types

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_signal_event_delivered():
    """Signalized scenario broadcasts signal.updated events upon stepping."""
    service = SimulationService()
    scn = create_signalized_scenario()
    runner = service.create_run(scenario=scn, run_id="run_live_sig_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    service.step_run(runner.run_id, ticks=1)

    received_types = []
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        received_types.append(msg["event_type"])

    assert "signal.updated" in received_types

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_emergency_event_delivered():
    """Emergency ambulance corridor scenario broadcasts emergency.updated events."""
    service = SimulationService()
    scn = create_ambulance_corridor_scenario()
    runner = service.create_run(scenario=scn, run_id="run_live_emg_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    service.step_run(runner.run_id, ticks=1)

    received_types = []
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        received_types.append(msg["event_type"])

    assert any(t in ("emergency.updated", "corridor.updated") for t in received_types)

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_safety_and_collision_event_delivered():
    """Safety and collision observations emitted by telemetry are translated and broadcast."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_live_safe_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from(timeout=3)

    # Emit a safety event directly to runner's telemetry
    runner.telemetry.emit(
        record_type=TelemetryRecordType.SAFETY_EVENT,
        name="safety_event",
        tick_index=1,
        simulation_time_s=0.1,
        payload={"event_type": "headway_warning", "risk_level": "CAUTION"},
    )

    msg = await communicator.receive_json_from(timeout=2)
    assert msg["event_type"] == "safety.event"
    assert msg["payload"]["risk_level"] == "CAUTION"

    # Emit a collision event
    runner.telemetry.emit(
        record_type=TelemetryRecordType.COLLISION_EVENT,
        name="collision_detected",
        tick_index=2,
        simulation_time_s=0.2,
        payload={"event_type": "collision", "vehicle_id_1": "veh_01"},
    )

    msg2 = await communicator.receive_json_from(timeout=2)
    assert msg2["event_type"] == "collision.detected"
    assert msg2["payload"]["event_type"] == "collision"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_events_scoped_to_correct_run_no_cross_leakage():
    """Subscribers to run A never receive events emitted by run B."""
    service = SimulationService()
    runner_a = service.create_run(scenario_id="scn_single_veh", run_id="run_iso_alpha")
    runner_b = service.create_run(scenario_id="scn_single_veh", run_id="run_iso_beta")

    comm_a = WebsocketCommunicator(application, f"/ws/v1/runs/{runner_a.run_id}/")
    conn_a, _ = await comm_a.connect()
    assert conn_a is True
    await comm_a.receive_json_from(timeout=3)

    comm_b = WebsocketCommunicator(application, f"/ws/v1/runs/{runner_b.run_id}/")
    conn_b, _ = await comm_b.connect()
    assert conn_b is True
    await comm_b.receive_json_from(timeout=3)

    # Step ONLY run_iso_alpha
    service.step_run(runner_a.run_id, ticks=1)

    # comm_a receives events with run_id == 'run_iso_alpha'
    msg_a = await comm_a.receive_json_from(timeout=2)
    assert msg_a["run_id"] == "run_iso_alpha"

    # comm_b receives NOTHING
    assert await comm_b.receive_nothing(timeout=0.2) is True

    await comm_a.disconnect()
    await comm_b.disconnect()


@pytest.mark.asyncio
async def test_broadcasting_does_not_mutate_world_state():
    """Broadcasting events does not alter simulation world state or agent positions."""
    service = SimulationService()
    scn1 = create_single_vehicle_scenario()
    scn2 = create_single_vehicle_scenario()

    # Run 1: with WebSocket connected
    runner1 = service.create_run(scenario=scn1, run_id="run_det_ws_01")
    comm = WebsocketCommunicator(application, f"/ws/v1/runs/{runner1.run_id}/")
    await comm.connect()
    await comm.receive_json_from(timeout=3)

    # Run 2: without WebSocket connected
    runner2 = service.create_run(scenario=scn2, run_id="run_det_now_02")

    # Step both 5 ticks
    service.step_run(runner1.run_id, ticks=5)
    service.step_run(runner2.run_id, ticks=5)

    snap1 = runner1.world.get_snapshot()
    snap2 = runner2.world.get_snapshot()

    v1 = snap1.vehicles["veh_01"]
    v2 = snap2.vehicles["veh_01"]

    assert v1.position.x == v2.position.x
    assert v1.position.y == v2.position.y
    assert v1.distance_along_segment_m == v2.distance_along_segment_m
    assert runner1.current_tick == runner2.current_tick

    await comm.disconnect()


@pytest.mark.asyncio
async def test_client_disconnect_does_not_stop_or_corrupt_simulation():
    """Disconnecting a client mid-run leaves the runner healthy and advanceable to completion."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_disconn_01")

    comm = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await comm.connect()
    await comm.receive_json_from(timeout=3)

    # Step 2 ticks
    service.step_run(runner.run_id, ticks=2)
    assert runner.current_tick == 2

    # Disconnect client
    await comm.disconnect()

    # Step 3 more ticks on runner
    service.step_run(runner.run_id, ticks=3)
    assert runner.current_tick == 5
    assert not runner.is_terminal
