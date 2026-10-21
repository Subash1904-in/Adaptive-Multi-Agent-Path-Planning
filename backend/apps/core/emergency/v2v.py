"""V2V message contracts, codecs, and local awareness ingestion for emergency priority."""

import json
from dataclasses import dataclass
from typing import Any, Optional

from apps.core.communication.exceptions import CommunicationValidationError
from apps.core.communication.models import V2VMessagePacket
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D
from apps.core.emergency.models import (
    EmergencyAwarenessRecord,
    EmergencyCorridor,
    EmergencyType,
    PriorityRequest,
    YieldActionType,
    YieldRequest,
)


@dataclass(frozen=True)
class EmergencyMessagePayload:
    """Base structured payload for emergency-related V2V message packets."""

    operation: str
    vehicle_id: str
    emergency_type: EmergencyType
    request_id: Optional[str] = None
    corridor_id: Optional[str] = None
    priority_level: int = 2
    destination_node_id: Optional[str] = None
    corridor_edges: tuple[str, ...] = ()
    corridor_nodes: tuple[str, ...] = ()
    target_vehicle_id: Optional[str] = None
    recommended_action: Optional[YieldActionType] = None
    target_speed_mps: float = 0.0
    target_decel_mps2: float = 0.0
    creation_time_s: float = 0.0
    expiry_time_s: float = 0.0
    details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize payload to a dictionary."""
        return {
            "operation": self.operation,
            "vehicle_id": self.vehicle_id,
            "emergency_type": self.emergency_type.value,
            "request_id": self.request_id,
            "corridor_id": self.corridor_id,
            "priority_level": self.priority_level,
            "destination_node_id": self.destination_node_id,
            "corridor_edges": list(self.corridor_edges),
            "corridor_nodes": list(self.corridor_nodes),
            "target_vehicle_id": self.target_vehicle_id,
            "recommended_action": (
                self.recommended_action.value if self.recommended_action else None
            ),
            "target_speed_mps": round(self.target_speed_mps, 4),
            "target_decel_mps2": round(self.target_decel_mps2, 4),
            "creation_time_s": round(self.creation_time_s, 4),
            "expiry_time_s": round(self.expiry_time_s, 4),
            "details": dict(self.details) if self.details is not None else None,
        }

    def to_json(self) -> str:
        """Serialize payload to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmergencyMessagePayload":
        """Reconstruct payload from dictionary."""
        op = data["operation"]
        vid = data["vehicle_id"]
        etype = EmergencyType(data["emergency_type"])
        act = (
            YieldActionType(data["recommended_action"]) if data.get("recommended_action") else None
        )
        return cls(
            operation=op,
            vehicle_id=vid,
            emergency_type=etype,
            request_id=data.get("request_id"),
            corridor_id=data.get("corridor_id"),
            priority_level=int(data.get("priority_level", 2)),
            destination_node_id=data.get("destination_node_id"),
            corridor_edges=tuple(data.get("corridor_edges", ())),
            corridor_nodes=tuple(data.get("corridor_nodes", ())),
            target_vehicle_id=data.get("target_vehicle_id"),
            recommended_action=act,
            target_speed_mps=float(data.get("target_speed_mps", 0.0)),
            target_decel_mps2=float(data.get("target_decel_mps2", 0.0)),
            creation_time_s=float(data.get("creation_time_s", 0.0)),
            expiry_time_s=float(data.get("expiry_time_s", 0.0)),
            details=data.get("details"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "EmergencyMessagePayload":
        """Parse payload from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as exc:
            raise CommunicationValidationError(
                f"Failed to parse emergency payload JSON: {exc}",
                field="payload",
            ) from exc


def build_emergency_packet(
    message_type: V2VMessageType,
    sender_id: str,
    payload: EmergencyMessagePayload,
    current_time_s: float,
    ttl_s: float,
    message_id: Optional[str] = None,
    sequence_number: int = 1,
    sender_position: Optional[Position2D] = None,
    sender_heading_rad: float = 0.0,
    sender_speed_mps: float = 0.0,
) -> V2VMessagePacket:
    """Construct an immutable, validated V2VMessagePacket for an emergency operation."""
    msg_id = message_id or f"msg_em_{sender_id}_{int(current_time_s * 1000):x}_{sequence_number}"
    return V2VMessagePacket(
        message_id=msg_id,
        sender_id=sender_id,
        sequence_number=sequence_number,
        timestamp_s=current_time_s,
        sender_position=sender_position or Position2D(x=0.0, y=0.0),
        sender_heading_rad=sender_heading_rad,
        sender_speed_mps=sender_speed_mps,
        message_type=message_type,
        payload=payload.to_dict(),
        expiry_timestamp_s=current_time_s + ttl_s,
    )


def create_emergency_activated_message(
    vehicle_id: str,
    emergency_type: EmergencyType,
    priority_level: int,
    current_time_s: float,
    ttl_s: float = 30.0,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct EMERGENCY_ACTIVATED announcement packet."""
    payload = EmergencyMessagePayload(
        operation="EMERGENCY_ACTIVATED",
        vehicle_id=vehicle_id,
        emergency_type=emergency_type,
        priority_level=priority_level,
        creation_time_s=current_time_s,
        expiry_time_s=current_time_s + ttl_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.EMERGENCY_ACTIVATED,
        sender_id=vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_priority_request_message(
    request: PriorityRequest,
    current_time_s: float,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct PRIORITY_REQUEST announcement packet."""
    payload = EmergencyMessagePayload(
        operation="PRIORITY_REQUEST",
        vehicle_id=request.vehicle_id,
        emergency_type=request.emergency_type,
        request_id=request.request_id,
        priority_level=request.priority_level,
        destination_node_id=request.destination_node_id,
        creation_time_s=current_time_s,
        expiry_time_s=request.expiry_time_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.PRIORITY_REQUEST,
        sender_id=request.vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=request.ttl_s,
        sequence_number=sequence_number,
    )


def create_corridor_proposed_message(
    corridor: EmergencyCorridor,
    emergency_type: EmergencyType,
    priority_level: int,
    current_time_s: float,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct CORRIDOR_PROPOSED announcement packet."""
    ttl_s = max(1.0, corridor.expiry_time_s - current_time_s)
    payload = EmergencyMessagePayload(
        operation="CORRIDOR_PROPOSED",
        vehicle_id=corridor.vehicle_id,
        emergency_type=emergency_type,
        request_id=corridor.request_id,
        corridor_id=corridor.corridor_id,
        priority_level=priority_level,
        corridor_edges=corridor.edge_ids,
        corridor_nodes=corridor.node_ids,
        creation_time_s=current_time_s,
        expiry_time_s=corridor.expiry_time_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.CORRIDOR_PROPOSED,
        sender_id=corridor.vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_yield_request_message(
    yield_req: YieldRequest,
    emergency_type: EmergencyType,
    priority_level: int,
    current_time_s: float,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct YIELD_REQUEST message packet directed to target vehicle."""
    ttl_s = max(1.0, yield_req.expiry_time_s - current_time_s)
    payload = EmergencyMessagePayload(
        operation="YIELD_REQUEST",
        vehicle_id=yield_req.emergency_vehicle_id,
        emergency_type=emergency_type,
        priority_level=priority_level,
        target_vehicle_id=yield_req.target_vehicle_id,
        recommended_action=yield_req.recommended_action,
        target_speed_mps=yield_req.target_speed_mps,
        target_decel_mps2=yield_req.target_decel_mps2,
        creation_time_s=current_time_s,
        expiry_time_s=yield_req.expiry_time_s,
        details={
            "yield_id": yield_req.yield_id,
            "edge_id": yield_req.edge_id,
            "node_id": yield_req.node_id,
        },
    )
    return build_emergency_packet(
        message_type=V2VMessageType.YIELD_REQUEST,
        sender_id=yield_req.emergency_vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_priority_cancelled_message(
    vehicle_id: str,
    emergency_type: EmergencyType,
    request_id: str,
    current_time_s: float,
    ttl_s: float = 15.0,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct PRIORITY_CANCELLED announcement packet."""
    payload = EmergencyMessagePayload(
        operation="PRIORITY_CANCELLED",
        vehicle_id=vehicle_id,
        emergency_type=emergency_type,
        request_id=request_id,
        creation_time_s=current_time_s,
        expiry_time_s=current_time_s + ttl_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.PRIORITY_CANCELLED,
        sender_id=vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_emergency_completed_message(
    vehicle_id: str,
    emergency_type: EmergencyType,
    request_id: str,
    current_time_s: float,
    ttl_s: float = 15.0,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct EMERGENCY_COMPLETED announcement packet."""
    payload = EmergencyMessagePayload(
        operation="EMERGENCY_COMPLETED",
        vehicle_id=vehicle_id,
        emergency_type=emergency_type,
        request_id=request_id,
        creation_time_s=current_time_s,
        expiry_time_s=current_time_s + ttl_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.EMERGENCY_COMPLETED,
        sender_id=vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_yield_acknowledged_message(
    vehicle_id: str,
    emergency_vehicle_id: str,
    yield_id: str,
    current_time_s: float,
    emergency_type: EmergencyType = EmergencyType.AMBULANCE,
    ttl_s: float = 15.0,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct YIELD_ACKNOWLEDGED response packet."""
    payload = EmergencyMessagePayload(
        operation="YIELD_ACKNOWLEDGED",
        vehicle_id=vehicle_id,
        emergency_type=emergency_type,
        target_vehicle_id=emergency_vehicle_id,
        creation_time_s=current_time_s,
        expiry_time_s=current_time_s + ttl_s,
        details={"yield_id": yield_id},
    )
    return build_emergency_packet(
        message_type=V2VMessageType.YIELD_ACKNOWLEDGED,
        sender_id=vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def create_corridor_updated_message(
    corridor: EmergencyCorridor,
    emergency_type: EmergencyType,
    priority_level: int,
    current_time_s: float,
    sequence_number: int = 1,
) -> V2VMessagePacket:
    """Construct CORRIDOR_UPDATED announcement packet."""
    ttl_s = max(1.0, corridor.expiry_time_s - current_time_s)
    payload = EmergencyMessagePayload(
        operation="CORRIDOR_UPDATED",
        vehicle_id=corridor.vehicle_id,
        emergency_type=emergency_type,
        request_id=corridor.request_id,
        corridor_id=corridor.corridor_id,
        priority_level=priority_level,
        corridor_edges=corridor.edge_ids,
        corridor_nodes=corridor.node_ids,
        creation_time_s=current_time_s,
        expiry_time_s=corridor.expiry_time_s,
    )
    return build_emergency_packet(
        message_type=V2VMessageType.CORRIDOR_UPDATED,
        sender_id=corridor.vehicle_id,
        payload=payload,
        current_time_s=current_time_s,
        ttl_s=ttl_s,
        sequence_number=sequence_number,
    )


def ingest_emergency_message_into_awareness(
    packet: V2VMessagePacket,
    awareness_store: dict[str, EmergencyAwarenessRecord],
    current_time_s: float,
) -> Optional[EmergencyAwarenessRecord]:
    """Process a received emergency V2V packet and update recipient's local awareness.

    Maintains strict local isolation: does not access global or sender state.
    """
    if packet.is_expired(current_time_s):
        return None

    try:
        if isinstance(packet.payload, dict):
            payload = EmergencyMessagePayload.from_dict(packet.payload)
        elif isinstance(packet.payload, str):
            payload = EmergencyMessagePayload.from_json(packet.payload)
        else:
            return None
    except Exception:
        return None

    em_id = payload.vehicle_id

    if payload.operation in ("PRIORITY_CANCELLED", "EMERGENCY_COMPLETED"):
        if em_id in awareness_store:
            record = awareness_store[em_id]
            record.is_active = False
            record.last_updated_s = current_time_s
            return record
        return None

    if em_id not in awareness_store:
        record = EmergencyAwarenessRecord(
            emergency_vehicle_id=em_id,
            emergency_type=payload.emergency_type,
            priority_level=payload.priority_level,
            last_updated_s=current_time_s,
            is_active=True,
        )
        awareness_store[em_id] = record
    else:
        record = awareness_store[em_id]

    record.last_updated_s = current_time_s
    record.is_active = True
    if payload.corridor_edges:
        record.corridor_edges = payload.corridor_edges
    if payload.corridor_nodes:
        record.corridor_nodes = payload.corridor_nodes
    if payload.operation == "YIELD_REQUEST" and payload.details:
        y_id = payload.details.get("yield_id")
        if y_id and y_id not in record.active_yield_requests:
            record.active_yield_requests = record.active_yield_requests + (y_id,)

    return record
