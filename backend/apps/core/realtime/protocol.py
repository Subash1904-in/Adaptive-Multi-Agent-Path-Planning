"""WebSocket communication protocol contracts, schema versioning, and message envelopes.

Defines validated message types, schema version constants, server-to-client event models,
client-to-server action types, and serialization converters for AMAPP simulation streaming.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Union

from apps.core.telemetry.models import TelemetryRecord, TelemetryRecordType, sanitize_for_json

if TYPE_CHECKING:
    from apps.core.scenarios.runner import ScenarioRunner

WEBSOCKET_SCHEMA_VERSION = "1.0.0"
SUPPORTED_WS_SCHEMA_VERSIONS = frozenset({"1.0.0"})

EDUCATIONAL_DISCLAIMER: str = (
    "AMAPP is an educational simulation framework and is not intended for "
    "real-world autonomous vehicle safety-critical control."
)


class SimulationEventType(str, Enum):
    """Categorical types of server-to-client simulation observations and events."""

    RUN_STATUS = "run.status"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    WORLD_SNAPSHOT = "world.snapshot"
    VEHICLE_UPDATED = "vehicle.updated"
    PEDESTRIAN_UPDATED = "pedestrian.updated"
    ROUTE_CHANGED = "route.changed"
    SIGNAL_UPDATED = "signal.updated"
    COMMUNICATION_EVENT = "communication.event"
    COORDINATION_EVENT = "coordination.event"
    SAFETY_EVENT = "safety.event"
    COLLISION_DETECTED = "collision.detected"
    EMERGENCY_UPDATED = "emergency.updated"
    CORRIDOR_UPDATED = "corridor.updated"
    DECISION_UPDATED = "decision.updated"
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_REMOVED = "incident.removed"
    METRICS_SNAPSHOT = "metrics.snapshot"
    TELEMETRY_GAP = "telemetry.gap"
    SERVER_HEARTBEAT = "server.heartbeat"
    ERROR = "error"


class ClientMessageType(str, Enum):
    """Valid actions a WebSocket client may dispatch to the simulation server."""

    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    HEARTBEAT = "heartbeat"
    PING = "ping"
    STEP = "step"
    CANCEL = "cancel"


# Critical events that must NOT be discarded under queue backpressure if evictable non-critical
# events are present in outbound client queues.
CRITICAL_WS_EVENT_TYPES = frozenset(
    {
        SimulationEventType.RUN_COMPLETED.value,
        SimulationEventType.RUN_CANCELLED.value,
        SimulationEventType.RUN_FAILED.value,
        SimulationEventType.SAFETY_EVENT.value,
        SimulationEventType.COLLISION_DETECTED.value,
        SimulationEventType.INCIDENT_CREATED.value,
        SimulationEventType.INCIDENT_REMOVED.value,
        SimulationEventType.ERROR.value,
    }
)


def build_event_envelope(
    event_type: Union[SimulationEventType, str],
    run_id: str,
    tick: int = 0,
    simulation_time_s: float = 0.0,
    sequence: int = 0,
    payload: Optional[dict[str, Any]] = None,
    schema_version: str = WEBSOCKET_SCHEMA_VERSION,
    message_id: Optional[str] = None,
) -> dict[str, Any]:
    """Construct a RFC 8259-compliant server-to-client WebSocket message envelope.

    Args:
        event_type: The categorical event type string or SimulationEventType.
        run_id: Unique simulation run identifier.
        tick: Simulation clock tick index.
        simulation_time_s: Simulation clock elapsed seconds.
        sequence: Monotonically increasing sequence number.
        payload: Event-specific data dictionary.
        schema_version: Version of the event wire schema.
        message_id: Optional unique message UUID string.

    Returns:
        Structured message envelope dictionary.
    """
    ev_type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
    return {
        "schema_version": schema_version,
        "message_id": message_id or str(uuid.uuid4()),
        "event_type": ev_type_str,
        "run_id": str(run_id),
        "tick": int(tick),
        "simulation_time_s": round(float(simulation_time_s), 4),
        "sequence": int(sequence),
        "payload": sanitize_for_json(payload or {}),
    }


def build_error_envelope(
    code: str,
    message: str,
    run_id: str,
    tick: int = 0,
    simulation_time_s: float = 0.0,
    sequence: int = 0,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Construct a standardized protocol or domain error envelope."""
    return build_event_envelope(
        event_type=SimulationEventType.ERROR,
        run_id=run_id,
        tick=tick,
        simulation_time_s=simulation_time_s,
        sequence=sequence,
        payload={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


def build_run_status_payload(runner: ScenarioRunner) -> dict[str, Any]:
    """Build a comprehensive point-in-time status payload for a simulation runner."""
    agents = runner.world.get_agents()
    arrived_cnt = sum(1 for a in agents if a.is_arrived)
    pedestrians = runner.world.get_pedestrians()
    return {
        "run_id": runner.run_id,
        "lifecycle_state": runner.lifecycle_state.value,
        "current_tick": runner.current_tick,
        "elapsed_time_s": round(runner.elapsed_time_s, 4),
        "is_terminal": runner.is_terminal,
        "total_vehicles": len(agents),
        "arrived_count": arrived_cnt,
        "active_count": len(agents) - arrived_cnt,
        "pedestrian_count": len(pedestrians),
        "disclaimer": EDUCATIONAL_DISCLAIMER,
    }


def telemetry_record_to_websocket_event(record: TelemetryRecord) -> dict[str, Any]:
    """Map an immutable TelemetryRecord to a standardized WebSocket event envelope."""
    payload = dict(record.payload) if isinstance(record.payload, dict) else {"data": record.payload}

    # Map TelemetryRecordType to SimulationEventType
    if record.record_type == TelemetryRecordType.RUN_STATE_CHANGE:
        new_state = payload.get("new_state", "")
        prev_state = payload.get("previous_state", "")
        if new_state == "RUNNING" and prev_state in ("READY", "CREATED"):
            ev_type = SimulationEventType.RUN_STARTED
        elif new_state == "COMPLETED":
            ev_type = SimulationEventType.RUN_COMPLETED
        elif new_state == "CANCELLED":
            ev_type = SimulationEventType.RUN_CANCELLED
        elif new_state in ("FAILED", "LIMIT_REACHED"):
            ev_type = (
                SimulationEventType.RUN_FAILED
                if new_state == "FAILED"
                else SimulationEventType.RUN_STATUS
            )
        else:
            ev_type = SimulationEventType.RUN_STATUS
    elif record.record_type == TelemetryRecordType.WORLD_SNAPSHOT:
        ev_type = SimulationEventType.WORLD_SNAPSHOT
    elif record.record_type == TelemetryRecordType.VEHICLE_STATE:
        ev_type = SimulationEventType.VEHICLE_UPDATED
    elif record.record_type == TelemetryRecordType.PEDESTRIAN_STATE:
        ev_type = SimulationEventType.PEDESTRIAN_UPDATED
    elif record.record_type == TelemetryRecordType.ROUTE_CHANGE:
        ev_type = SimulationEventType.ROUTE_CHANGED
    elif record.record_type == TelemetryRecordType.SIGNAL_EVENT:
        ev_type = SimulationEventType.SIGNAL_UPDATED
    elif record.record_type == TelemetryRecordType.COMMUNICATION_EVENT:
        ev_type = SimulationEventType.COMMUNICATION_EVENT
    elif record.record_type == TelemetryRecordType.COORDINATION_EVENT:
        ev_type = SimulationEventType.COORDINATION_EVENT
    elif record.record_type == TelemetryRecordType.SAFETY_EVENT:
        ev_type = SimulationEventType.SAFETY_EVENT
    elif record.record_type == TelemetryRecordType.COLLISION_EVENT:
        ev_type = SimulationEventType.COLLISION_DETECTED
    elif record.record_type == TelemetryRecordType.EMERGENCY_EVENT:
        if payload.get("event_type") == "corridor" or "corridor" in record.name:
            ev_type = SimulationEventType.CORRIDOR_UPDATED
        else:
            ev_type = SimulationEventType.EMERGENCY_UPDATED
    elif record.record_type == TelemetryRecordType.DECISION_EVENT:
        ev_type = SimulationEventType.DECISION_UPDATED
    elif record.record_type == TelemetryRecordType.METRICS_SNAPSHOT:
        ev_type = SimulationEventType.METRICS_SNAPSHOT
    elif record.record_type == TelemetryRecordType.ERROR:
        ev_type = SimulationEventType.ERROR
    else:
        ev_type = SimulationEventType.RUN_STATUS

    # Attach agent_id or correlation_id if present
    if record.agent_id and "agent_id" not in payload:
        payload["agent_id"] = record.agent_id
    if record.correlation_id and "correlation_id" not in payload:
        payload["correlation_id"] = record.correlation_id

    return build_event_envelope(
        event_type=ev_type,
        run_id=record.run_id,
        tick=record.tick_index,
        simulation_time_s=record.simulation_time_s,
        sequence=record.sequence_number,
        payload=payload,
        schema_version=record.schema_version,
    )
