"""Real-time event broadcasting bridge between simulation services and Django Channels.

Translates telemetry observations and lifecycle events into WebSocket event envelopes
and dispatches them to per-run Channel layer groups using non-blocking, error-isolated execution.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.core.realtime.protocol import telemetry_record_to_websocket_event
from apps.core.telemetry.models import TelemetryRecord

if TYPE_CHECKING:
    from apps.core.scenarios.runner import ScenarioRunner

logger = logging.getLogger("amapp.realtime")


def _dispatch_to_group(channel_layer: Any, group_name: str, message: dict[str, Any]) -> None:
    """Dispatch a message to a channel group, adapting to sync or async execution contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        loop.create_task(channel_layer.group_send(group_name, message))
    else:
        async_to_sync(channel_layer.group_send)(group_name, message)


class SimulationEventBroadcaster:
    """Dispatches simulation telemetry observations and lifecycle events to Channel layer groups.

    Guarantees that channel layer delays, failures, or absent consumers never disrupt or block
    the authoritative simulation engine.
    """

    _instance: Optional["SimulationEventBroadcaster"] = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._attached_runners: set[str] = set()
        self._listener_refs: dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> "SimulationEventBroadcaster":
        """Retrieve the process-wide broadcaster singleton."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the broadcaster singleton for testing isolation."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.clear()
            cls._instance = None

    def attach_runner(self, runner: ScenarioRunner) -> None:
        """Register a listener on the runner's TelemetryCollector to broadcast observations.

        Args:
            runner: The active ScenarioRunner instance.
        """
        with self._lock:
            run_id = runner.run_id
            if run_id in self._attached_runners:
                return

            def on_record(record: TelemetryRecord) -> None:
                self.broadcast_record(record)

            if hasattr(runner, "telemetry") and not runner.telemetry.is_closed:
                runner.telemetry.add_listener(on_record)
                self._listener_refs[run_id] = on_record
                self._attached_runners.add(run_id)
                logger.debug("Attached WebSocket broadcaster to simulation run '%s'.", run_id)

    def detach_runner(self, runner: ScenarioRunner) -> None:
        """Unregister the broadcaster listener from a runner's TelemetryCollector."""
        with self._lock:
            run_id = runner.run_id
            if run_id in self._listener_refs:
                on_record = self._listener_refs.pop(run_id)
                if hasattr(runner, "telemetry") and not runner.telemetry.is_closed:
                    runner.telemetry.remove_listener(on_record)
            self._attached_runners.discard(run_id)
            logger.debug("Detached WebSocket broadcaster from simulation run '%s'.", run_id)

    def broadcast_record(self, record: TelemetryRecord) -> bool:
        """Translate and broadcast a single TelemetryRecord to the run's WebSocket channel group.

        Args:
            record: The TelemetryRecord to broadcast.

        Returns:
            True if broadcast was dispatched; False if channel layer unavailable or error caught.
        """
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return False

            envelope = telemetry_record_to_websocket_event(record)
            group_name = f"run_{record.run_id}"

            _dispatch_to_group(
                channel_layer,
                group_name,
                {
                    "type": "simulation.event",
                    "event": envelope,
                },
            )
            return True
        except Exception as exc:
            logger.warning(
                "Broadcasting telemetry record '%s' for run '%s' failed: %s",
                record.record_id,
                record.run_id,
                exc,
            )
            return False

    def broadcast_custom_event(self, run_id: str, event_envelope: dict[str, Any]) -> bool:
        """Broadcast an arbitrary validated event envelope to a run's channel group."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return False

            group_name = f"run_{run_id}"
            _dispatch_to_group(
                channel_layer,
                group_name,
                {
                    "type": "simulation.event",
                    "event": event_envelope,
                },
            )
            return True
        except Exception as exc:
            logger.warning(
                "Broadcasting custom event '%s' for run '%s' failed: %s",
                event_envelope.get("event_type"),
                run_id,
                exc,
            )
            return False

    def clear(self) -> None:
        """Detach all attached runners and reset broadcaster state."""
        with self._lock:
            self._attached_runners.clear()
            self._listener_refs.clear()
