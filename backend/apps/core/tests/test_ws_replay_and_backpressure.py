"""Tests for bounded telemetry replay, gap notifications, and backpressure."""

import asyncio

import pytest
from channels.testing import WebsocketCommunicator

from apps.core.api.services import (
    SimulationService,
    default_run_registry,
    default_scenario_registry,
)
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
async def test_bounded_replay_by_last_sequence():
    """Subscribing with last_sequence streams events after sequence in ascending order."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_replay_seq_01")

    # Step 5 ticks to accumulate telemetry records
    service.step_run(runner.run_id, ticks=5)
    records = runner.telemetry.get_records()
    assert len(records) >= 5

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    connected, _ = await communicator.connect()
    assert connected is True

    # Initial run.status on connect
    init_msg = await communicator.receive_json_from(timeout=3)
    assert init_msg["event_type"] == "run.status"

    # Request replay with cursor sequence 2
    cursor = 2
    await communicator.send_json_to(
        {"type": "subscribe", "last_sequence": cursor, "max_replay_records": 50}
    )

    # Read events
    replayed_sequences = []
    for _ in range(len(records) + 2):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        if msg["event_type"] != "run.status":
            seq = msg["sequence"]
            assert seq > cursor
            replayed_sequences.append(seq)

    assert len(replayed_sequences) > 0
    # Sequences must be strictly ascending
    assert replayed_sequences == sorted(replayed_sequences)

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_replay_expired_history_emits_gap_notification():
    """Requesting a cursor older than the retained telemetry emits a telemetry.gap notification."""
    service = SimulationService()
    # Create runner with bounded telemetry buffer of 5 records
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_gap_01")

    # Step 5 ticks
    service.step_run(runner.run_id, ticks=5)
    assert len(runner.telemetry.get_records()) >= 5

    # Simulate eviction of the oldest 3 records
    evicted_seq = runner.telemetry.get_records()[2].sequence_number
    runner.telemetry._records = runner.telemetry._records[3:]
    oldest_available_seq = runner.telemetry.get_records()[0].sequence_number
    assert oldest_available_seq > evicted_seq

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    try:
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.receive_json_from(timeout=3)  # init run.status

        # Request cursor 1 (which was evicted)
        await communicator.send_json_to({"type": "subscribe", "last_sequence": 1})

        gap_msg = await communicator.receive_json_from(timeout=2)
        assert gap_msg["event_type"] == "telemetry.gap"
        assert gap_msg["payload"]["reason"] == "expired_history"
        assert gap_msg["payload"]["requested_sequence"] == 1
        assert gap_msg["payload"]["oldest_available_sequence"] == oldest_available_seq
    finally:
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_replay_max_limit_enforced():
    """Client cannot request more replay records than max_replay_records."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_limit_01")

    # Step 10 ticks
    service.step_run(runner.run_id, ticks=10)
    records = runner.telemetry.get_records()
    assert len(records) >= 10

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)  # init run.status

    # Request max 3 records
    await communicator.send_json_to(
        {"type": "subscribe", "last_sequence": 0, "max_replay_records": 3}
    )

    replayed_count = 0
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        if msg["event_type"] != "run.status":
            replayed_count += 1

    assert replayed_count == 3

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_replay_by_tick_index():
    """Subscribing with replay_from_tick streams records with tick_index >= requested tick."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_tick_replay_01")

    service.step_run(runner.run_id, ticks=5)

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)  # init status

    await communicator.send_json_to({"type": "subscribe", "replay_from_tick": 3})

    replayed_ticks = []
    for _ in range(10):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        if msg["event_type"] != "run.status":
            replayed_ticks.append(msg["tick"])

    assert len(replayed_ticks) > 0
    assert all(t >= 3 for t in replayed_ticks)

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_backpressure_bounded_queue_drops_noncritical_and_emits_gap():
    """When outbound queue capacity is exceeded, events drop and a gap is reported."""
    from apps.core.realtime.consumer import SimulationRunConsumer

    consumer = SimulationRunConsumer()
    consumer.run_id = "run_overflow_01"
    consumer.max_queue_size = 3
    consumer.outbound_queue = asyncio.Queue(maxsize=3)

    # Fill queue to maximum capacity of 3
    for i in range(3):
        consumer.outbound_queue.put_nowait(
            {
                "event_type": "vehicle.updated",
                "sequence": i + 1,
                "run_id": "run_overflow_01",
            }
        )

    assert consumer.outbound_queue.full()

    # Enqueue a 4th non-critical event when full
    overflow_event = {
        "event_type": "vehicle.updated",
        "sequence": 4,
        "run_id": "run_overflow_01",
    }
    await consumer._enqueue_event(overflow_event)

    # Verify dropped counter and bounds
    assert consumer.dropped_events_count == 1
    assert consumer.dropped_start_seq == 4
    assert consumer.dropped_end_seq == 4
    assert consumer.outbound_queue.qsize() == 3

    # Now verify _outbound_sender prepends telemetry.gap upon draining
    sent_messages = []

    async def mock_send(msg):
        sent_messages.append(msg)

    consumer.send_json = mock_send

    sender_task = asyncio.create_task(consumer._outbound_sender())
    # Allow sender task to drain queue
    await asyncio.sleep(0.05)
    sender_task.cancel()
    try:
        await sender_task
    except asyncio.CancelledError:
        pass

    assert len(sent_messages) >= 4
    # First message transmitted after drops must be telemetry.gap
    gap_msg = sent_messages[0]
    assert gap_msg["event_type"] == "telemetry.gap"
    assert gap_msg["payload"]["reason"] == "buffer_overflow"
    assert gap_msg["payload"]["dropped_count"] == 1
    assert consumer.dropped_events_count == 0


@pytest.mark.asyncio
async def test_critical_events_never_silently_dropped_on_backpressure():
    """Critical events evict noncritical events and are delivered despite pressure."""
    from apps.core.realtime.consumer import SimulationRunConsumer

    consumer = SimulationRunConsumer()
    consumer.run_id = "run_crit_evict_01"
    consumer.max_queue_size = 3
    consumer.outbound_queue = asyncio.Queue(maxsize=3)

    # Fill queue with 3 non-critical vehicle updates
    for i in range(3):
        consumer.outbound_queue.put_nowait(
            {
                "event_type": "vehicle.updated",
                "sequence": i + 1,
                "run_id": "run_crit_evict_01",
            }
        )

    assert consumer.outbound_queue.full()

    # Enqueue a critical collision event
    crit_event = {
        "event_type": "collision.detected",
        "sequence": 4,
        "run_id": "run_crit_evict_01",
        "payload": {"vehicle_id_1": "veh_01"},
    }
    await consumer._enqueue_event(crit_event)

    # Non-critical item was evicted to make room for critical event
    assert consumer.dropped_events_count == 1
    assert consumer.outbound_queue.qsize() == 3

    # Verify critical event is now inside outbound queue
    items = []
    while not consumer.outbound_queue.empty():
        items.append(consumer.outbound_queue.get_nowait())

    collision_items = [it for it in items if it.get("event_type") == "collision.detected"]
    assert len(collision_items) == 1
    assert collision_items[0]["sequence"] == 4


@pytest.mark.asyncio
async def test_duplicate_subscribe_does_not_duplicate_delivery():
    """Sending multiple subscribe messages does not duplicate delivered events."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_dup_sub_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)  # init status

    # Subscribe twice
    await communicator.send_json_to({"type": "subscribe"})
    msg1 = await communicator.receive_json_from(timeout=2)
    assert msg1["event_type"] == "run.status"

    await communicator.send_json_to({"type": "subscribe"})
    msg2 = await communicator.receive_json_from(timeout=2)
    assert msg2["event_type"] == "run.status"

    # Step 1 tick
    service.step_run(runner.run_id, ticks=1)

    events = []
    for _ in range(8):
        if await communicator.receive_nothing(timeout=0.1):
            break
        msg = await communicator.receive_json_from(timeout=2)
        events.append(msg)

    # Count vehicle.updated events
    veh_events = [e for e in events if e["event_type"] == "vehicle.updated"]
    # Exactly 1 vehicle in scn_single_veh, so exactly 1 vehicle.updated event
    assert len(veh_events) == 1

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_heartbeat_ping_pong():
    """Client ping or heartbeat receives a server.heartbeat response."""
    service = SimulationService()
    runner = service.create_run(scenario_id="scn_single_veh", run_id="run_ping_01")

    communicator = WebsocketCommunicator(application, f"/ws/v1/runs/{runner.run_id}/")
    await communicator.connect()
    await communicator.receive_json_from(timeout=3)  # init status

    # Send ping
    await communicator.send_json_to({"type": "ping"})
    pong_msg = await communicator.receive_json_from(timeout=2)
    assert pong_msg["event_type"] == "server.heartbeat"
    assert pong_msg["payload"]["pong"] is True
    assert pong_msg["payload"]["client_ping"] is True

    # Send heartbeat
    await communicator.send_json_to({"type": "heartbeat"})
    pong_msg2 = await communicator.receive_json_from(timeout=2)
    assert pong_msg2["event_type"] == "server.heartbeat"
    assert pong_msg2["payload"]["pong"] is True

    await communicator.disconnect()
