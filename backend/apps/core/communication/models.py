"""Data models, message contracts, and configuration for V2V communication."""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from apps.core.communication.exceptions import CommunicationValidationError
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D


class DeliveryPolicy(str, Enum):
    """Message delivery timing semantics relative to simulation clock ticks."""

    NEXT_TICK = "next_tick"
    SAME_TICK = "same_tick"


class DropReason(str, Enum):
    """Categorized diagnostic reason for a dropped or rejected message delivery."""

    OUT_OF_RANGE = "out_of_range"
    PACKET_LOSS = "packet_loss"
    RECEIVER_UNAVAILABLE = "receiver_unavailable"
    SENDER_UNAVAILABLE = "sender_unavailable"
    EXPIRED = "expired"
    DUPLICATE = "duplicate"
    INVALID_MESSAGE = "invalid_message"


class NeighborStatus(str, Enum):
    """Lifecycle freshness status of a known communication neighbor."""

    ACTIVE = "active"
    STALE = "stale"


class StaleNeighborPolicy(str, Enum):
    """Policy governing handling and removal of neighbors exceeding heartbeat timeout."""

    MARK_STALE = "mark_stale"
    REMOVE_IMMEDIATELY = "remove_immediately"
    STALE_THEN_REMOVE = "stale_then_remove"


@dataclass(frozen=True)
class VehicleStatusPayload:
    """Standardized vehicle telemetry payload inspired by CAM and BSM protocols."""

    current_edge_id: Optional[str] = None
    target_node_id: Optional[str] = None
    route_id: Optional[str] = None
    remaining_distance_m: Optional[float] = None
    acceleration_mps2: Optional[float] = None
    custom_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert payload to a JSON-compatible dictionary."""
        return {
            "current_edge_id": self.current_edge_id,
            "target_node_id": self.target_node_id,
            "route_id": self.route_id,
            "remaining_distance_m": (
                round(self.remaining_distance_m, 4)
                if self.remaining_distance_m is not None
                else None
            ),
            "acceleration_mps2": (
                round(self.acceleration_mps2, 4) if self.acceleration_mps2 is not None else None
            ),
            "custom_data": dict(self.custom_data),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VehicleStatusPayload":
        """Construct payload from a dictionary."""
        if not isinstance(data, dict):
            raise CommunicationValidationError(
                "Payload data must be a dictionary.", field="payload"
            )
        return cls(
            current_edge_id=data.get("current_edge_id"),
            target_node_id=data.get("target_node_id"),
            route_id=data.get("route_id"),
            remaining_distance_m=data.get("remaining_distance_m"),
            acceleration_mps2=data.get("acceleration_mps2"),
            custom_data=dict(data.get("custom_data", {})),
        )


@dataclass(frozen=True)
class V2VMessagePacket:
    """Immutable, typed Vehicle-to-Vehicle communication packet.

    Attributes:
        message_id: Unique identifier for this message packet.
        sender_id: Identifier of the transmitting vehicle agent.
        sequence_number: Monotonically increasing sequence number per sender.
        timestamp_s: Authoritative simulation timestamp in seconds (>= 0.0).
        sender_position: Spatial planar coordinates of sender at transmission.
        sender_heading_rad: Heading orientation of sender in radians.
        sender_speed_mps: Instantaneous forward speed in meters/second (>= 0.0).
        message_type: Semantic category (e.g. HEARTBEAT for status broadcasts).
        protocol_version: Protocol schema version (e.g. '1.0.0').
        recipient_id: Optional unicast recipient ID; None indicates spatial broadcast.
        expiry_timestamp_s: Optional simulation timestamp when message becomes invalid.
        payload: Structured telemetry dictionary or serialized VehicleStatusPayload.
        correlation_id: Optional identifier for tracing response or causality chains.
    """

    message_id: str
    sender_id: str
    sequence_number: int
    timestamp_s: float
    sender_position: Position2D
    sender_heading_rad: float
    sender_speed_mps: float
    message_type: V2VMessageType = V2VMessageType.HEARTBEAT
    protocol_version: str = "1.0.0"
    recipient_id: Optional[str] = None
    expiry_timestamp_s: Optional[float] = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.protocol_version, str) or not self.protocol_version.strip():
            raise CommunicationValidationError(
                "protocol_version must be a non-empty string.", field="protocol_version"
            )
        if not isinstance(self.message_id, str) or not self.message_id.strip():
            raise CommunicationValidationError(
                "message_id must be a non-empty string.", field="message_id"
            )
        if not isinstance(self.sender_id, str) or not self.sender_id.strip():
            raise CommunicationValidationError(
                "sender_id must be a non-empty string.", field="sender_id"
            )
        if (
            not isinstance(self.sequence_number, int)
            or isinstance(self.sequence_number, bool)
            or self.sequence_number < 0
        ):
            raise CommunicationValidationError(
                f"sequence_number must be a non-negative integer, got {self.sequence_number}.",
                field="sequence_number",
            )
        if (
            not isinstance(self.timestamp_s, (int, float))
            or not math.isfinite(self.timestamp_s)
            or self.timestamp_s < 0.0
        ):
            raise CommunicationValidationError(
                f"timestamp_s must be a finite non-negative number, got {self.timestamp_s}.",
                field="timestamp_s",
            )
        if not isinstance(self.sender_position, Position2D):
            pos_type = type(self.sender_position).__name__
            raise CommunicationValidationError(
                f"sender_position must be an instance of Position2D, got {pos_type}.",
                field="sender_position",
            )
        if not isinstance(self.sender_heading_rad, (int, float)) or not math.isfinite(
            self.sender_heading_rad
        ):
            raise CommunicationValidationError(
                f"sender_heading_rad must be a finite number, got {self.sender_heading_rad}.",
                field="sender_heading_rad",
            )
        if (
            not isinstance(self.sender_speed_mps, (int, float))
            or not math.isfinite(self.sender_speed_mps)
            or self.sender_speed_mps < 0.0
        ):
            msg = (
                f"sender_speed_mps must be a finite non-negative number, got "
                f"{self.sender_speed_mps}."
            )
            raise CommunicationValidationError(msg, field="sender_speed_mps")
        if not isinstance(self.message_type, V2VMessageType):
            raise CommunicationValidationError(
                f"Invalid message_type: {self.message_type}.", field="message_type"
            )
        if self.recipient_id is not None:
            if not isinstance(self.recipient_id, str) or not self.recipient_id.strip():
                raise CommunicationValidationError(
                    "recipient_id must be a non-empty string when provided.",
                    field="recipient_id",
                )
        if self.expiry_timestamp_s is not None:
            if (
                not isinstance(self.expiry_timestamp_s, (int, float))
                or not math.isfinite(self.expiry_timestamp_s)
                or self.expiry_timestamp_s < self.timestamp_s
            ):
                raise CommunicationValidationError(
                    f"expiry_timestamp_s ({self.expiry_timestamp_s}) cannot be less than "
                    f"timestamp_s ({self.timestamp_s}) or non-finite.",
                    field="expiry_timestamp_s",
                )
        if not isinstance(self.payload, dict):
            raise CommunicationValidationError("payload must be a dictionary.", field="payload")
        if self.correlation_id is not None:
            if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
                raise CommunicationValidationError(
                    "correlation_id must be a non-empty string when provided.",
                    field="correlation_id",
                )

        # Enforce exact normalized float values on immutable instance
        object.__setattr__(self, "timestamp_s", float(self.timestamp_s))
        object.__setattr__(self, "sender_heading_rad", float(self.sender_heading_rad))
        object.__setattr__(self, "sender_speed_mps", float(self.sender_speed_mps))
        if self.expiry_timestamp_s is not None:
            object.__setattr__(self, "expiry_timestamp_s", float(self.expiry_timestamp_s))

    def is_expired(self, current_time_s: float) -> bool:
        """Evaluate if the message has passed its expiration simulation timestamp."""
        if self.expiry_timestamp_s is None:
            return False
        return current_time_s >= self.expiry_timestamp_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize message to a deterministic, JSON-compatible dictionary."""
        return {
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sequence_number": self.sequence_number,
            "timestamp_s": round(self.timestamp_s, 6),
            "sender_position": self.sender_position.to_dict(),
            "sender_heading_rad": round(self.sender_heading_rad, 6),
            "sender_speed_mps": round(self.sender_speed_mps, 4),
            "message_type": self.message_type.value,
            "recipient_id": self.recipient_id,
            "expiry_timestamp_s": (
                round(self.expiry_timestamp_s, 6) if self.expiry_timestamp_s is not None else None
            ),
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "V2VMessagePacket":
        """Deserialize message packet from dictionary with strict field validation."""
        if not isinstance(data, dict):
            raise CommunicationValidationError(
                "Message data must be a dictionary.", field="message"
            )

        required_keys = {
            "message_id",
            "sender_id",
            "sequence_number",
            "timestamp_s",
            "sender_position",
            "sender_heading_rad",
            "sender_speed_mps",
        }
        missing = required_keys - set(data.keys())
        if missing:
            raise CommunicationValidationError(
                f"Missing required message fields: {sorted(missing)}.",
                field=sorted(missing)[0],
            )

        # Parse position
        pos_raw = data["sender_position"]
        if not isinstance(pos_raw, dict) or "x" not in pos_raw or "y" not in pos_raw:
            raise CommunicationValidationError(
                "sender_position must be a dict with 'x' and 'y'.",
                field="sender_position",
            )
        pos = Position2D(x=pos_raw["x"], y=pos_raw["y"])

        # Parse message_type
        mtype_val = data.get("message_type", V2VMessageType.HEARTBEAT.value)
        try:
            mtype = V2VMessageType(mtype_val)
        except ValueError as exc:
            raise CommunicationValidationError(
                f"Unknown message_type '{mtype_val}'.", field="message_type"
            ) from exc

        return cls(
            message_id=str(data["message_id"]),
            sender_id=str(data["sender_id"]),
            sequence_number=data["sequence_number"],
            timestamp_s=data["timestamp_s"],
            sender_position=pos,
            sender_heading_rad=data["sender_heading_rad"],
            sender_speed_mps=data["sender_speed_mps"],
            message_type=mtype,
            protocol_version=data.get("protocol_version", "1.0.0"),
            recipient_id=data.get("recipient_id"),
            expiry_timestamp_s=data.get("expiry_timestamp_s"),
            payload=dict(data.get("payload", {})),
            correlation_id=data.get("correlation_id"),
        )

    def to_json(self) -> str:
        """Convert message packet to a deterministic JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> "V2VMessagePacket":
        """Parse message packet from a JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise CommunicationValidationError(
                f"Invalid JSON string: {exc}.", field="json"
            ) from exc
        return cls.from_dict(data)


@dataclass(frozen=True)
class CommunicationConfig:
    """Immutable configuration defining V2V communication and failure parameters.

    Attributes:
        enabled: Master switch for V2V communication in simulation.
        range_m: Maximum communication radius in planar meters (> 0.0, default: 50.0).
        broadcast_interval_s: Scheduled period between periodic status broadcasts (> 0.0).
        message_ttl_s: Optional duration in seconds before transmitted message expires.
        delivery_policy: Timing policy for message delivery (NEXT_TICK default).
        max_peers: Optional cap on the number of eligible peers discovered per query.
        packet_loss_rate: Deterministic packet drop probability in [0.0, 1.0].
        packet_loss_seed: Optional integer seed for reproducible packet loss behavior.
        protocol_version: Enforced V2V protocol version string.
        neighbor_tracking_enabled: Toggle dynamic neighbor table maintenance (default: True).
        neighbor_update_interval_s: Discrete period between table updates (> 0.0, default: 0.1).
        heartbeat_timeout_s: Seconds before a neighbor becomes stale (> 0.0, default: 0.5).
        stale_grace_period_s: Optional grace period before stale neighbor removal (default: 1.0).
        stale_policy: Policy for handling timed-out neighbors (STALE_THEN_REMOVE default).
    """

    enabled: bool = True
    range_m: float = 50.0
    broadcast_interval_s: float = 0.1
    message_ttl_s: Optional[float] = 1.0
    delivery_policy: DeliveryPolicy = DeliveryPolicy.NEXT_TICK
    max_peers: Optional[int] = None
    packet_loss_rate: float = 0.0
    packet_loss_seed: Optional[int] = None
    protocol_version: str = "1.0.0"
    neighbor_tracking_enabled: bool = True
    neighbor_update_interval_s: float = 0.1
    heartbeat_timeout_s: float = 0.5
    stale_grace_period_s: Optional[float] = 1.0
    stale_policy: StaleNeighborPolicy = StaleNeighborPolicy.STALE_THEN_REMOVE

    def __post_init__(self) -> None:
        if (
            not isinstance(self.range_m, (int, float))
            or not math.isfinite(self.range_m)
            or self.range_m <= 0.0
        ):
            raise CommunicationValidationError(
                f"range_m must be a finite positive number, got {self.range_m}.",
                field="range_m",
            )
        if (
            not isinstance(self.broadcast_interval_s, (int, float))
            or not math.isfinite(self.broadcast_interval_s)
            or self.broadcast_interval_s <= 0.0
        ):
            msg = (
                f"broadcast_interval_s must be a finite positive number, got "
                f"{self.broadcast_interval_s}."
            )
            raise CommunicationValidationError(msg, field="broadcast_interval_s")
        if (
            not isinstance(self.packet_loss_rate, (int, float))
            or not math.isfinite(self.packet_loss_rate)
            or not (0.0 <= self.packet_loss_rate <= 1.0)
        ):
            raise CommunicationValidationError(
                f"packet_loss_rate must be between 0.0 and 1.0, got {self.packet_loss_rate}.",
                field="packet_loss_rate",
            )
        if self.message_ttl_s is not None:
            if (
                not isinstance(self.message_ttl_s, (int, float))
                or not math.isfinite(self.message_ttl_s)
                or self.message_ttl_s <= 0.0
            ):
                msg = (
                    f"message_ttl_s must be a finite positive number when provided, got "
                    f"{self.message_ttl_s}."
                )
                raise CommunicationValidationError(msg, field="message_ttl_s")
        if self.max_peers is not None:
            if (
                not isinstance(self.max_peers, int)
                or isinstance(self.max_peers, bool)
                or self.max_peers <= 0
            ):
                raise CommunicationValidationError(
                    f"max_peers must be a positive integer, got {self.max_peers}.",
                    field="max_peers",
                )
        if not isinstance(self.delivery_policy, DeliveryPolicy):
            raise CommunicationValidationError(
                f"Invalid delivery_policy: {self.delivery_policy}.",
                field="delivery_policy",
            )
        if (
            not isinstance(self.neighbor_update_interval_s, (int, float))
            or not math.isfinite(self.neighbor_update_interval_s)
            or self.neighbor_update_interval_s <= 0.0
        ):
            msg = (
                f"neighbor_update_interval_s must be a finite positive number, got "
                f"{self.neighbor_update_interval_s}."
            )
            raise CommunicationValidationError(msg, field="neighbor_update_interval_s")
        if (
            not isinstance(self.heartbeat_timeout_s, (int, float))
            or not math.isfinite(self.heartbeat_timeout_s)
            or self.heartbeat_timeout_s <= 0.0
        ):
            msg = (
                f"heartbeat_timeout_s must be a finite positive number, got "
                f"{self.heartbeat_timeout_s}."
            )
            raise CommunicationValidationError(msg, field="heartbeat_timeout_s")
        if self.stale_grace_period_s is not None:
            if (
                not isinstance(self.stale_grace_period_s, (int, float))
                or not math.isfinite(self.stale_grace_period_s)
                or self.stale_grace_period_s < 0.0
            ):
                msg = (
                    f"stale_grace_period_s must be a finite non-negative number when provided, "
                    f"got {self.stale_grace_period_s}."
                )
                raise CommunicationValidationError(msg, field="stale_grace_period_s")
        if not isinstance(self.stale_policy, StaleNeighborPolicy):
            raise CommunicationValidationError(
                f"Invalid stale_policy: {self.stale_policy}.",
                field="stale_policy",
            )

        object.__setattr__(self, "range_m", float(self.range_m))
        object.__setattr__(self, "broadcast_interval_s", float(self.broadcast_interval_s))
        object.__setattr__(self, "packet_loss_rate", float(self.packet_loss_rate))
        if self.message_ttl_s is not None:
            object.__setattr__(self, "message_ttl_s", float(self.message_ttl_s))
        object.__setattr__(
            self, "neighbor_update_interval_s", float(self.neighbor_update_interval_s)
        )
        object.__setattr__(self, "heartbeat_timeout_s", float(self.heartbeat_timeout_s))
        if self.stale_grace_period_s is not None:
            object.__setattr__(self, "stale_grace_period_s", float(self.stale_grace_period_s))

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to JSON-serializable dictionary."""
        return {
            "enabled": self.enabled,
            "range_m": self.range_m,
            "broadcast_interval_s": self.broadcast_interval_s,
            "message_ttl_s": self.message_ttl_s,
            "delivery_policy": self.delivery_policy.value,
            "max_peers": self.max_peers,
            "packet_loss_rate": self.packet_loss_rate,
            "packet_loss_seed": self.packet_loss_seed,
            "protocol_version": self.protocol_version,
            "neighbor_tracking_enabled": self.neighbor_tracking_enabled,
            "neighbor_update_interval_s": self.neighbor_update_interval_s,
            "heartbeat_timeout_s": self.heartbeat_timeout_s,
            "stale_grace_period_s": self.stale_grace_period_s,
            "stale_policy": self.stale_policy.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommunicationConfig":
        """Construct configuration from dictionary."""
        if not isinstance(data, dict):
            raise CommunicationValidationError(
                "CommunicationConfig data must be a dictionary.", field="config"
            )
        policy_raw = data.get("delivery_policy", DeliveryPolicy.NEXT_TICK.value)
        try:
            policy = DeliveryPolicy(policy_raw)
        except ValueError as exc:
            raise CommunicationValidationError(
                f"Unknown delivery_policy '{policy_raw}'.", field="delivery_policy"
            ) from exc

        stale_policy_raw = data.get("stale_policy", StaleNeighborPolicy.STALE_THEN_REMOVE.value)
        try:
            stale_policy = StaleNeighborPolicy(stale_policy_raw)
        except ValueError as exc:
            raise CommunicationValidationError(
                f"Unknown stale_policy '{stale_policy_raw}'.", field="stale_policy"
            ) from exc

        return cls(
            enabled=bool(data.get("enabled", True)),
            range_m=data.get("range_m", 50.0),
            broadcast_interval_s=data.get("broadcast_interval_s", 0.1),
            message_ttl_s=data.get("message_ttl_s", 1.0),
            delivery_policy=policy,
            max_peers=data.get("max_peers"),
            packet_loss_rate=data.get("packet_loss_rate", 0.0),
            packet_loss_seed=data.get("packet_loss_seed"),
            protocol_version=data.get("protocol_version", "1.0.0"),
            neighbor_tracking_enabled=bool(data.get("neighbor_tracking_enabled", True)),
            neighbor_update_interval_s=data.get("neighbor_update_interval_s", 0.1),
            heartbeat_timeout_s=data.get("heartbeat_timeout_s", 0.5),
            stale_grace_period_s=data.get("stale_grace_period_s", 1.0),
            stale_policy=stale_policy,
        )


@dataclass(frozen=True)
class CommunicationSnapshot:
    """Immutable point-in-time snapshot of communication subsystem state."""

    enabled: bool
    range_m: float
    delivery_policy: str
    total_broadcasts: int
    total_delivered: int
    total_dropped: int
    pending_inbox_counts: dict[str, int]
    sequence_counters: dict[str, int]
    neighbor_tables: Optional[dict[str, Any]] = None
    neighbor_metrics: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to JSON-compatible dictionary."""
        d: dict[str, Any] = {
            "enabled": self.enabled,
            "range_m": self.range_m,
            "delivery_policy": self.delivery_policy,
            "total_broadcasts": self.total_broadcasts,
            "total_delivered": self.total_delivered,
            "total_dropped": self.total_dropped,
            "pending_inbox_counts": dict(self.pending_inbox_counts),
            "sequence_counters": dict(self.sequence_counters),
        }
        if self.neighbor_tables is not None:
            d["neighbor_tables"] = dict(self.neighbor_tables)
        if self.neighbor_metrics is not None:
            d["neighbor_metrics"] = dict(self.neighbor_metrics)
        return d
