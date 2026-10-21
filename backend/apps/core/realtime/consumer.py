"""WebSocket consumer for real-time AMAPP simulation observations and stream control.

Implements asynchronous, bounded, per-run WebSocket subscriptions with authentication,
authorization, event prioritization, drop tracking, gap detection, and heartbeats.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.core.api.services import SimulationService, default_run_registry
from apps.core.realtime.protocol import (
    CRITICAL_WS_EVENT_TYPES,
    ClientMessageType,
    SimulationEventType,
    build_error_envelope,
    build_event_envelope,
    build_run_status_payload,
    telemetry_record_to_websocket_event,
)

logger = logging.getLogger("amapp.realtime")

RUN_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


class SimulationRunConsumer(AsyncJsonWebsocketConsumer):
    """Asynchronous WebSocket consumer managing live simulation streams for a specific run."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.run_id: str = ""
        self.group_name: str = ""
        self.is_subscribed: bool = False
        self.outbound_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sender_task: Optional[asyncio.Task[None]] = None
        self.heartbeat_task: Optional[asyncio.Task[None]] = None
        self.dropped_events_count: int = 0
        self.dropped_start_seq: Optional[int] = None
        self.dropped_end_seq: Optional[int] = None

        # Configuration bounds
        self.max_queue_size: int = getattr(settings, "AMAPP_WS_MAX_QUEUE_SIZE", 128)
        self.max_message_bytes: int = getattr(settings, "AMAPP_WS_MAX_MESSAGE_BYTES", 65536)
        self.max_replay_records: int = getattr(settings, "AMAPP_WS_MAX_REPLAY_RECORDS", 500)
        self.heartbeat_interval_s: float = getattr(settings, "AMAPP_WS_HEARTBEAT_INTERVAL_S", 30.0)

    async def connect(self) -> None:
        """Handle incoming WebSocket connection handshake, auth, and run validation."""
        self.run_id = self.scope.get("url_route", {}).get("kwargs", {}).get("run_id", "")

        # 1. Validate run_id structure
        if not self.run_id or not RUN_ID_REGEX.match(self.run_id):
            await self.accept()
            err = build_error_envelope(
                code="INVALID_RUN_ID",
                message=f"Invalid or missing run identifier: '{self.run_id}'.",
                run_id=self.run_id or "unknown",
            )
            await self.send_json(err)
            await self.close(code=4400)
            return

        # 2. Authentication check
        require_auth = getattr(settings, "AMAPP_API_REQUIRE_AUTHENTICATION", False)
        user = self.scope.get("user")
        if require_auth and (user is None or not user.is_authenticated):
            await self.accept()
            err = build_error_envelope(
                code="UNAUTHENTICATED",
                message="Authentication credentials were not provided or are invalid.",
                run_id=self.run_id,
            )
            await self.send_json(err)
            await self.close(code=4401)
            return

        # 3. Validate simulation run existence
        run_exists = await sync_to_async(default_run_registry.exists)(self.run_id)
        if not run_exists:
            await self.accept()
            err = build_error_envelope(
                code="RUN_NOT_FOUND",
                message=f"Simulation run '{self.run_id}' not found.",
                run_id=self.run_id,
            )
            await self.send_json(err)
            await self.close(code=4404)
            return

        # 4. Accept connection and establish group subscription
        await self.accept()
        self.group_name = f"run_{self.run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        self.is_subscribed = True
        self.outbound_queue = asyncio.Queue(maxsize=self.max_queue_size)

        # 5. Start background worker tasks
        self.sender_task = asyncio.create_task(self._outbound_sender())
        if self.heartbeat_interval_s > 0:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 6. Deliver initial point-in-time run status
        runner = await sync_to_async(default_run_registry.get)(self.run_id)
        status_payload = build_run_status_payload(runner)
        initial_status = build_event_envelope(
            event_type=SimulationEventType.RUN_STATUS,
            run_id=self.run_id,
            tick=runner.current_tick,
            simulation_time_s=runner.elapsed_time_s,
            sequence=0,
            payload=status_payload,
        )
        await self.outbound_queue.put(initial_status)
        logger.debug("WebSocket client connected to simulation run '%s'.", self.run_id)

    async def disconnect(self, close_code: int) -> None:
        """Release group membership, cancel background tasks, and clean up connection."""
        self.is_subscribed = False

        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.sender_task and not self.sender_task.done():
            self.sender_task.cancel()
            try:
                await self.sender_task
            except asyncio.CancelledError:
                pass

        if self.group_name and self.channel_layer:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

        # Drain outbound queue
        while not self.outbound_queue.empty():
            try:
                self.outbound_queue.get_nowait()
                self.outbound_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        logger.debug(
            "WebSocket client disconnected from run '%s' with code %s.",
            self.run_id,
            close_code,
        )

    async def receive(
        self,
        text_data: Optional[str] = None,
        bytes_data: Optional[bytes] = None,
    ) -> None:
        """Validate raw incoming frame size and content format before decoding."""
        if bytes_data is not None:
            err = build_error_envelope(
                code="BINARY_NOT_SUPPORTED",
                message="Binary WebSocket frames are not supported; use JSON text frames.",
                run_id=self.run_id,
            )
            await self._enqueue_event(err)
            return

        if text_data is None:
            return

        # Check payload size limit
        if len(text_data.encode("utf-8")) > self.max_message_bytes:
            err = build_error_envelope(
                code="MESSAGE_SIZE_EXCEEDED",
                message=f"Message size exceeds maximum allowed of {self.max_message_bytes} bytes.",
                run_id=self.run_id,
            )
            await self._enqueue_event(err)
            return

        # Parse JSON
        try:
            content = json.loads(text_data)
        except json.JSONDecodeError as exc:
            err = build_error_envelope(
                code="INVALID_JSON",
                message=f"Malformed JSON payload: {exc.msg}.",
                run_id=self.run_id,
            )
            await self._enqueue_event(err)
            return

        await self.receive_json(content)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        """Process validated client JSON messages."""
        if not isinstance(content, dict):
            err = build_error_envelope(
                code="INVALID_PAYLOAD_FORMAT",
                message="WebSocket message must be a JSON object.",
                run_id=self.run_id,
            )
            await self._enqueue_event(err)
            return

        # Verify client is not attempting to switch run_id on an existing connection
        supplied_run_id = content.get("run_id")
        if supplied_run_id and supplied_run_id != self.run_id:
            err = build_error_envelope(
                code="CANNOT_OVERRIDE_BOUND_RUN",
                message=(
                    f"Supplied run_id '{supplied_run_id}' does not match "
                    f"connection bound run_id '{self.run_id}'."
                ),
                run_id=self.run_id,
            )
            await self._enqueue_event(err)
            return

        msg_type = content.get("type")

        # 1. Subscribe
        if msg_type == ClientMessageType.SUBSCRIBE.value:
            if not self.is_subscribed:
                await self.channel_layer.group_add(self.group_name, self.channel_name)
                self.is_subscribed = True

            # Handle bounded replay if requested
            if "last_sequence" in content or "replay_from_tick" in content:
                await self._handle_replay(content)

            runner = await sync_to_async(default_run_registry.get)(self.run_id)
            status_envelope = build_event_envelope(
                event_type=SimulationEventType.RUN_STATUS,
                run_id=self.run_id,
                tick=runner.current_tick,
                simulation_time_s=runner.elapsed_time_s,
                sequence=0,
                payload=build_run_status_payload(runner),
            )
            await self._enqueue_event(status_envelope)

        # 2. Unsubscribe
        elif msg_type == ClientMessageType.UNSUBSCRIBE.value:
            if self.is_subscribed:
                self.is_subscribed = False
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            unsub_envelope = build_event_envelope(
                event_type=SimulationEventType.RUN_STATUS,
                run_id=self.run_id,
                sequence=0,
                payload={"status": "unsubscribed", "run_id": self.run_id},
            )
            await self._enqueue_event(unsub_envelope)

        # 3. Heartbeat / Ping
        elif msg_type in (ClientMessageType.HEARTBEAT.value, ClientMessageType.PING.value):
            pong_envelope = build_event_envelope(
                event_type=SimulationEventType.SERVER_HEARTBEAT,
                run_id=self.run_id,
                sequence=0,
                payload={"pong": True, "timestamp": time.time(), "client_ping": True},
            )
            await self._enqueue_event(pong_envelope)

        # 4. Step (Simulation Control Extension)
        elif msg_type == ClientMessageType.STEP.value:
            require_auth = getattr(settings, "AMAPP_API_REQUIRE_AUTHENTICATION", False)
            user = self.scope.get("user")
            if require_auth and not (user and user.is_staff):
                err = build_error_envelope(
                    code="PERMISSION_DENIED",
                    message="Simulation control actions require staff privileges.",
                    run_id=self.run_id,
                )
                await self._enqueue_event(err)
                return

            ticks = content.get("ticks", 1)
            try:
                ticks_int = int(ticks)
                if ticks_int < 1 or ticks_int > 1000:
                    raise ValueError
            except (ValueError, TypeError):
                err = build_error_envelope(
                    code="INVALID_STEP_TICKS",
                    message="Parameter 'ticks' must be an integer between 1 and 1000.",
                    run_id=self.run_id,
                )
                await self._enqueue_event(err)
                return

            service = SimulationService()
            try:
                await sync_to_async(service.step_run)(self.run_id, ticks=ticks_int)
            except Exception as exc:
                err = build_error_envelope(
                    code="STEP_FAILED",
                    message=f"Simulation step failed: {exc}",
                    run_id=self.run_id,
                )
                await self._enqueue_event(err)

        # 5. Cancel (Simulation Control Extension)
        elif msg_type == ClientMessageType.CANCEL.value:
            require_auth = getattr(settings, "AMAPP_API_REQUIRE_AUTHENTICATION", False)
            user = self.scope.get("user")
            if require_auth and not (user and user.is_staff):
                err = build_error_envelope(
                    code="PERMISSION_DENIED",
                    message="Simulation control actions require staff privileges.",
                    run_id=self.run_id,
                )
                await self._enqueue_event(err)
                return

            reason = str(content.get("reason", "User requested cancellation via WebSocket"))
            service = SimulationService()
            try:
                await sync_to_async(service.cancel_run)(self.run_id, reason=reason)
            except Exception as exc:
                err = build_error_envelope(
                    code="CANCEL_FAILED",
                    message=f"Simulation cancel failed: {exc}",
                    run_id=self.run_id,
                )
                await self._enqueue_event(err)

        # 6. Unknown message type
        else:
            err = build_error_envelope(
                code="UNSUPPORTED_MESSAGE_TYPE",
                message=f"Message type '{msg_type}' is not recognized or supported.",
                run_id=self.run_id,
            )
            await self._enqueue_event(err)

    async def simulation_event(self, event: dict[str, Any]) -> None:
        """Handler for Channel layer group messages dispatched by broadcaster."""
        if not self.is_subscribed:
            return

        envelope = event.get("event")
        if not envelope or not isinstance(envelope, dict):
            return

        # Enforce run isolation: never emit another run's event to this connection
        if envelope.get("run_id") != self.run_id:
            return

        await self._enqueue_event(envelope)

    async def _enqueue_event(self, envelope: dict[str, Any]) -> None:
        """Enqueue an outbound event envelope adhering to bounded queue and drop policies."""
        is_critical = envelope.get("event_type") in CRITICAL_WS_EVENT_TYPES

        if not self.outbound_queue.full():
            self.outbound_queue.put_nowait(envelope)
            return

        # Queue capacity exhausted: apply backpressure policy
        if is_critical:
            # Make room for critical event by evicting an existing non-critical event if possible
            temp_items: list[dict[str, Any]] = []
            evicted: bool = False
            while not self.outbound_queue.empty():
                item = self.outbound_queue.get_nowait()
                if not evicted and item.get("event_type") not in CRITICAL_WS_EVENT_TYPES:
                    evicted = True
                    self.dropped_events_count += 1
                    seq = item.get("sequence", 0)
                    if self.dropped_start_seq is None:
                        self.dropped_start_seq = seq
                    self.dropped_end_seq = seq
                else:
                    temp_items.append(item)

            for item in temp_items:
                self.outbound_queue.put_nowait(item)

            if not self.outbound_queue.full():
                self.outbound_queue.put_nowait(envelope)
            else:
                logger.error(
                    "WebSocket outbound queue completely saturated with critical events "
                    "for run '%s'. Critical event cannot be queued.",
                    self.run_id,
                )
        else:
            # Drop incoming non-critical event and track sequence gap
            self.dropped_events_count += 1
            seq = envelope.get("sequence", 0)
            if self.dropped_start_seq is None:
                self.dropped_start_seq = seq
            self.dropped_end_seq = seq

    async def _outbound_sender(self) -> None:
        """Worker task consuming from outbound queue and transmitting frames to client."""
        try:
            while True:
                envelope = await self.outbound_queue.get()

                # If events were dropped, prepend a telemetry.gap notification
                if self.dropped_events_count > 0:
                    gap_envelope = build_event_envelope(
                        event_type=SimulationEventType.TELEMETRY_GAP,
                        run_id=self.run_id,
                        sequence=self.dropped_end_seq or 0,
                        payload={
                            "reason": "buffer_overflow",
                            "dropped_count": self.dropped_events_count,
                            "gap_start_sequence": self.dropped_start_seq,
                            "gap_end_sequence": self.dropped_end_seq,
                        },
                    )
                    await self.send_json(gap_envelope)
                    self.dropped_events_count = 0
                    self.dropped_start_seq = None
                    self.dropped_end_seq = None

                await self.send_json(envelope)
                self.outbound_queue.task_done()
        except asyncio.CancelledError:
            pass

    async def _heartbeat_loop(self) -> None:
        """Periodic server heartbeat task maintaining connection liveness."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval_s)
                heartbeat_envelope = build_event_envelope(
                    event_type=SimulationEventType.SERVER_HEARTBEAT,
                    run_id=self.run_id,
                    sequence=0,
                    payload={"status": "alive", "timestamp": time.time()},
                )
                await self._enqueue_event(heartbeat_envelope)
        except asyncio.CancelledError:
            pass

    async def _handle_replay(self, content: dict[str, Any]) -> None:
        """Extract and transmit bounded historical telemetry records for reconnect/replay."""
        runner = await sync_to_async(default_run_registry.get)(self.run_id)
        if not hasattr(runner, "telemetry") or runner.telemetry.record_count == 0:
            return

        records = runner.telemetry.get_records()
        if not records:
            return

        last_sequence = content.get("last_sequence")
        replay_from_tick = content.get("replay_from_tick")
        max_requested = content.get("max_replay_records", self.max_replay_records)
        try:
            max_limit = min(int(max_requested), self.max_replay_records)
        except (ValueError, TypeError):
            max_limit = self.max_replay_records

        replay_slice: list[Any] = []

        if last_sequence is not None:
            try:
                last_seq_int = int(last_sequence)
                oldest_seq = records[0].sequence_number
                if last_seq_int < oldest_seq:
                    # History was evicted: notify client of sequence gap
                    gap_envelope = build_event_envelope(
                        event_type=SimulationEventType.TELEMETRY_GAP,
                        run_id=self.run_id,
                        sequence=records[0].sequence_number,
                        payload={
                            "reason": "expired_history",
                            "requested_sequence": last_seq_int,
                            "oldest_available_sequence": oldest_seq,
                            "gap_start_sequence": last_seq_int + 1,
                            "gap_end_sequence": oldest_seq - 1,
                        },
                    )
                    await self._enqueue_event(gap_envelope)
                replay_slice = [r for r in records if r.sequence_number > last_seq_int]
            except (ValueError, TypeError):
                replay_slice = list(records)
        elif replay_from_tick is not None:
            try:
                tick_int = int(replay_from_tick)
                replay_slice = [r for r in records if r.tick_index >= tick_int]
            except (ValueError, TypeError):
                replay_slice = list(records)
        else:
            replay_slice = list(records)

        # Enforce maximum bounded replay limit
        bounded_records = replay_slice[:max_limit]
        for record in bounded_records:
            envelope = telemetry_record_to_websocket_event(record)
            await self._enqueue_event(envelope)
