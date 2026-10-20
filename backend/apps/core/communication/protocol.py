"""Message factory, validation, and serialization routines for V2V protocol."""

from typing import TYPE_CHECKING, Any, Optional, Union

from apps.core.communication.exceptions import (
    CommunicationValidationError,
    MessageSerializationError,
)
from apps.core.communication.models import V2VMessagePacket, VehicleStatusPayload
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D

if TYPE_CHECKING:
    from apps.core.domain.models import Vehicle
    from apps.core.kinematics.vehicle_agent import VehicleAgent
    from apps.core.simulation.models import VehicleSnapshot


def create_status_message(
    vehicle: Union["Vehicle", "VehicleAgent", "VehicleSnapshot"],
    sequence_number: int,
    timestamp_s: float,
    ttl_s: Optional[float] = 1.0,
    message_id: Optional[str] = None,
    custom_payload: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    protocol_version: str = "1.0.0",
) -> V2VMessagePacket:
    """Construct an immutable V2V status message packet from a vehicle instance or snapshot.

    Analogous in role to a Cooperative Awareness Message (CAM) or Basic Safety Message (BSM).

    Args:
        vehicle: Source vehicle entity, VehicleAgent, or VehicleSnapshot.
        sequence_number: Monotonically increasing sequence number for this sender.
        timestamp_s: Authoritative simulation time in seconds.
        ttl_s: Optional time-to-live in seconds before the message expires.
        message_id: Optional explicit message identifier; defaults to deterministic string.
        custom_payload: Optional application-specific metadata dictionary.
        correlation_id: Optional correlation identifier.
        protocol_version: Version string for the communication schema.

    Returns:
        An immutable, validated V2VMessagePacket instance.
    """
    if hasattr(vehicle, "vehicle") and hasattr(vehicle.vehicle, "position"):
        v_entity = vehicle.vehicle
        sender_id = v_entity.id
        pos = Position2D(x=v_entity.position.x, y=v_entity.position.y)
        heading = float(v_entity.heading_rad)
        speed = float(v_entity.speed_mps)
        edge_id = v_entity.current_edge_id
        target_node = v_entity.target_node_id
        route_id = v_entity.route_id
        rem_dist = float(vehicle.remaining_route_distance_m)
        accel = 0.0  # Instantaneous acceleration
    elif hasattr(vehicle, "vehicle_id") and hasattr(vehicle, "position"):
        sender_id = vehicle.vehicle_id
        pos = Position2D(x=vehicle.position.x, y=vehicle.position.y)
        heading = float(vehicle.heading_rad)
        speed = float(vehicle.speed_mps)
        edge_id = getattr(vehicle, "current_edge_id", None)
        target_node = getattr(vehicle, "target_node_id", None)
        route_id = getattr(vehicle, "route_id", None)
        rem_dist = getattr(vehicle, "remaining_route_distance_m", None)
        accel = None
    elif hasattr(vehicle, "id") and hasattr(vehicle, "position"):
        sender_id = vehicle.id
        pos = Position2D(x=vehicle.position.x, y=vehicle.position.y)
        heading = float(vehicle.heading_rad)
        speed = float(vehicle.speed_mps)
        edge_id = getattr(vehicle, "current_edge_id", None)
        target_node = getattr(vehicle, "target_node_id", None)
        route_id = getattr(vehicle, "route_id", None)
        rem_dist = None
        accel = None
    else:
        raise CommunicationValidationError(
            f"Unsupported vehicle type for status message: {type(vehicle).__name__}.",
            field="vehicle",
        )

    # Derive deterministic message identifier if not explicitly provided
    if not message_id:
        # Use microsecond-equivalent integer for deterministic, stable ID
        time_part = int(round(timestamp_s * 1000.0))
        message_id = f"v2v_{sender_id}_{sequence_number}_{time_part}"

    # Calculate expiry timestamp
    expiry_s = (timestamp_s + ttl_s) if ttl_s is not None else None

    # Assemble typed payload
    status_payload = VehicleStatusPayload(
        current_edge_id=edge_id,
        target_node_id=target_node,
        route_id=route_id,
        remaining_distance_m=rem_dist,
        acceleration_mps2=accel,
        custom_data=dict(custom_payload or {}),
    )

    return V2VMessagePacket(
        protocol_version=protocol_version,
        message_id=message_id,
        sender_id=sender_id,
        sequence_number=sequence_number,
        timestamp_s=timestamp_s,
        sender_position=pos,
        sender_heading_rad=heading,
        sender_speed_mps=speed,
        message_type=V2VMessageType.HEARTBEAT,
        recipient_id=None,  # Broadcast
        expiry_timestamp_s=expiry_s,
        payload=status_payload.to_dict(),
        correlation_id=correlation_id,
    )


def serialize_message(message: V2VMessagePacket) -> str:
    """Serialize a V2VMessagePacket to a deterministic JSON string.

    Args:
        message: The V2VMessagePacket instance.

    Returns:
        JSON-encoded string with sorted keys.

    Raises:
        MessageSerializationError: If serialization fails.
    """
    if not isinstance(message, V2VMessagePacket):
        raise MessageSerializationError(
            f"Expected V2VMessagePacket instance, got {type(message).__name__}."
        )
    try:
        return message.to_json()
    except Exception as exc:
        raise MessageSerializationError(
            f"Failed to serialize message '{message.message_id}': {exc}"
        ) from exc


def deserialize_message(raw_json: str) -> V2VMessagePacket:
    """Deserialize a JSON string into an immutable V2VMessagePacket.

    Args:
        raw_json: JSON-encoded string.

    Returns:
        Parsed and validated V2VMessagePacket instance.

    Raises:
        MessageSerializationError: If parsing or validation fails.
    """
    if not isinstance(raw_json, str):
        raise MessageSerializationError("raw_json must be a string.")
    try:
        return V2VMessagePacket.from_json(raw_json)
    except CommunicationValidationError as exc:
        raise MessageSerializationError(f"Validation failed during deserialization: {exc}") from exc
    except Exception as exc:
        raise MessageSerializationError(f"Unexpected error deserializing message: {exc}") from exc
