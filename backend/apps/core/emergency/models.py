"""Data models, contracts, and lifecycle specifications for emergency priority."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from apps.core.domain.enums import TrafficSignalState
from apps.core.emergency.exceptions import (
    InvalidEmergencyStateError,
    InvalidEmergencyTypeError,
)


class EmergencyType(str, Enum):
    """Categorization of emergency response vehicles."""

    AMBULANCE = "ambulance"
    FIRE_ENGINE = "fire_engine"
    POLICE = "police"


class EmergencyLifecycleState(str, Enum):
    """Lifecycle states of an emergency vehicle agent."""

    INACTIVE = "inactive"
    REQUESTING_PRIORITY = "requesting_priority"
    PRIORITY_ACTIVE = "priority_active"
    YIELDING_OR_CORRIDOR_PENDING = "yielding_or_corridor_pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PriorityRequestStatus(str, Enum):
    """Operational status of a priority request."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    ACTIVE = "active"
    EXPIRED = "expired"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class YieldActionType(str, Enum):
    """Action requested of or executed by a yielding non-emergency vehicle."""

    CONTINUE = "continue"
    REDUCE_SPEED = "reduce_speed"
    STOP_BEFORE_INTERSECTION = "stop_before_intersection"
    YIELD_TO_EMERGENCY = "yield_to_emergency"
    CLEAR_CORRIDOR = "clear_corridor"
    RESUME_NORMAL = "resume_normal"


class ReservationConflictPolicy(str, Enum):
    """Policy for resolving competing corridor or intersection reservations."""

    STRICT_PRIORITY = "strict_priority"
    FIRST_COME_FIRST_SERVED = "first_come_first_served"


# Valid state transitions for emergency vehicle lifecycle
_LEGAL_TRANSITIONS: dict[EmergencyLifecycleState, set[EmergencyLifecycleState]] = {
    EmergencyLifecycleState.INACTIVE: {
        EmergencyLifecycleState.REQUESTING_PRIORITY,
        EmergencyLifecycleState.PRIORITY_ACTIVE,
    },
    EmergencyLifecycleState.REQUESTING_PRIORITY: {
        EmergencyLifecycleState.PRIORITY_ACTIVE,
        EmergencyLifecycleState.YIELDING_OR_CORRIDOR_PENDING,
        EmergencyLifecycleState.CANCELLED,
    },
    EmergencyLifecycleState.PRIORITY_ACTIVE: {
        EmergencyLifecycleState.YIELDING_OR_CORRIDOR_PENDING,
        EmergencyLifecycleState.COMPLETED,
        EmergencyLifecycleState.CANCELLED,
    },
    EmergencyLifecycleState.YIELDING_OR_CORRIDOR_PENDING: {
        EmergencyLifecycleState.PRIORITY_ACTIVE,
        EmergencyLifecycleState.COMPLETED,
        EmergencyLifecycleState.CANCELLED,
    },
    EmergencyLifecycleState.COMPLETED: {
        EmergencyLifecycleState.INACTIVE,  # Re-arming after mission
    },
    EmergencyLifecycleState.CANCELLED: {
        EmergencyLifecycleState.INACTIVE,  # Re-arming after cancellation
    },
}


def validate_emergency_transition(
    from_state: EmergencyLifecycleState, to_state: EmergencyLifecycleState
) -> None:
    """Validate that transition from from_state to to_state is legal.

    Raises:
        InvalidEmergencyStateError: If transition is not permitted.
    """
    if from_state == to_state:
        return
    allowed = _LEGAL_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise InvalidEmergencyStateError(
            f"Illegal emergency state transition from '{from_state.value}' to '{to_state.value}'.",
            from_state=from_state.value,
            to_state=to_state.value,
        )


def default_priority_level_for_type(emergency_type: EmergencyType) -> int:
    """Derive standard priority ranking by vehicle type (lower number = higher priority).

    Default ordering: FIRE_ENGINE (1) > AMBULANCE (2) > POLICE (3).
    """
    if emergency_type == EmergencyType.FIRE_ENGINE:
        return 1
    if emergency_type == EmergencyType.AMBULANCE:
        return 2
    if emergency_type == EmergencyType.POLICE:
        return 3
    raise InvalidEmergencyTypeError(
        f"Unknown emergency type '{emergency_type}'.", emergency_type=str(emergency_type)
    )


@dataclass(frozen=True)
class EmergencyConfig:
    """Configuration parameters for the emergency priority subsystem."""

    enabled: bool = True
    default_request_ttl_s: float = 60.0
    default_corridor_ttl_s: float = 45.0
    corridor_lookahead_edges: int = 5
    yielding_distance_m: float = 50.0
    yield_decel_mps2: float = 3.5
    conflict_policy: ReservationConflictPolicy = ReservationConflictPolicy.STRICT_PRIORITY
    signal_priority_enabled: bool = True
    signal_hold_green_duration_s: float = 10.0
    log_events: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        return {
            "enabled": self.enabled,
            "default_request_ttl_s": self.default_request_ttl_s,
            "default_corridor_ttl_s": self.default_corridor_ttl_s,
            "corridor_lookahead_edges": self.corridor_lookahead_edges,
            "yielding_distance_m": self.yielding_distance_m,
            "yield_decel_mps2": self.yield_decel_mps2,
            "conflict_policy": self.conflict_policy.value,
            "signal_priority_enabled": self.signal_priority_enabled,
            "signal_hold_green_duration_s": self.signal_hold_green_duration_s,
            "log_events": self.log_events,
        }


@dataclass
class PriorityRequest:
    """Authoritative declaration of an emergency priority request."""

    request_id: str
    vehicle_id: str
    emergency_type: EmergencyType
    priority_level: int
    destination_node_id: str
    creation_time_s: float
    ttl_s: float
    status: PriorityRequestStatus = PriorityRequestStatus.PENDING
    corridor_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def expiry_time_s(self) -> float:
        """Absolute simulation time at which request expires."""
        return self.creation_time_s + self.ttl_s

    def is_expired(self, current_time_s: float) -> bool:
        """Check whether request has timed out in simulation time."""
        return current_time_s >= self.expiry_time_s

    @property
    def sort_key(self) -> tuple[int, float, str]:
        """Deterministic tie-breaking priority tuple.

        Format: (priority_level, creation_time_s, vehicle_id).
        """
        return (self.priority_level, round(self.creation_time_s, 6), self.vehicle_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize priority request to dictionary."""
        return {
            "request_id": self.request_id,
            "vehicle_id": self.vehicle_id,
            "emergency_type": self.emergency_type.value,
            "priority_level": self.priority_level,
            "destination_node_id": self.destination_node_id,
            "creation_time_s": round(self.creation_time_s, 4),
            "expiry_time_s": round(self.expiry_time_s, 4),
            "ttl_s": round(self.ttl_s, 4),
            "status": self.status.value,
            "corridor_id": self.corridor_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CorridorReservation:
    """Temporary reservation of a specific edge or intersection node for an emergency corridor."""

    reservation_id: str
    corridor_id: str
    request_id: str
    vehicle_id: str
    priority_level: int
    edge_id: Optional[str] = None
    node_id: Optional[str] = None
    start_time_s: float = 0.0
    expiry_time_s: float = 0.0

    def is_expired(self, current_time_s: float) -> bool:
        """Check whether reservation has expired."""
        return current_time_s >= self.expiry_time_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize reservation to dictionary."""
        return {
            "reservation_id": self.reservation_id,
            "corridor_id": self.corridor_id,
            "request_id": self.request_id,
            "vehicle_id": self.vehicle_id,
            "priority_level": self.priority_level,
            "edge_id": self.edge_id,
            "node_id": self.node_id,
            "start_time_s": round(self.start_time_s, 4),
            "expiry_time_s": round(self.expiry_time_s, 4),
        }


@dataclass
class EmergencyCorridor:
    """Prioritized route corridor along directed road edges and intersection nodes."""

    corridor_id: str
    request_id: str
    vehicle_id: str
    edge_ids: tuple[str, ...]
    node_ids: tuple[str, ...]
    creation_time_s: float
    expiry_time_s: float
    version: int = 1
    is_active: bool = True
    is_released: bool = False

    def is_expired(self, current_time_s: float) -> bool:
        """Check whether corridor has timed out."""
        return current_time_s >= self.expiry_time_s

    def contains_edge(self, edge_id: str) -> bool:
        """Check whether corridor includes edge."""
        return edge_id in self.edge_ids

    def contains_node(self, node_id: str) -> bool:
        """Check whether corridor includes intersection node."""
        return node_id in self.node_ids

    def to_dict(self) -> dict[str, Any]:
        """Serialize corridor to dictionary."""
        return {
            "corridor_id": self.corridor_id,
            "request_id": self.request_id,
            "vehicle_id": self.vehicle_id,
            "edge_ids": list(self.edge_ids),
            "node_ids": list(self.node_ids),
            "creation_time_s": round(self.creation_time_s, 4),
            "expiry_time_s": round(self.expiry_time_s, 4),
            "version": self.version,
            "is_active": self.is_active,
            "is_released": self.is_released,
        }


@dataclass(frozen=True)
class YieldRequest:
    """Action request issued to a non-emergency vehicle to safely yield corridor space."""

    yield_id: str
    emergency_vehicle_id: str
    target_vehicle_id: str
    edge_id: Optional[str]
    node_id: Optional[str]
    recommended_action: YieldActionType
    target_speed_mps: float
    target_decel_mps2: float
    creation_time_s: float
    expiry_time_s: float

    def is_expired(self, current_time_s: float) -> bool:
        """Check whether yield request has timed out."""
        return current_time_s >= self.expiry_time_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize yield request to dictionary."""
        return {
            "yield_id": self.yield_id,
            "emergency_vehicle_id": self.emergency_vehicle_id,
            "target_vehicle_id": self.target_vehicle_id,
            "edge_id": self.edge_id,
            "node_id": self.node_id,
            "recommended_action": self.recommended_action.value,
            "target_speed_mps": round(self.target_speed_mps, 4),
            "target_decel_mps2": round(self.target_decel_mps2, 4),
            "creation_time_s": round(self.creation_time_s, 4),
            "expiry_time_s": round(self.expiry_time_s, 4),
        }


@dataclass(frozen=True)
class YieldDecision:
    """Deterministic yielding decision for a non-emergency vehicle."""

    vehicle_id: str
    action: YieldActionType
    effective_decel_mps2: float
    reason: str
    source_yield_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize yielding decision to dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "action": self.action.value,
            "effective_decel_mps2": round(self.effective_decel_mps2, 4),
            "reason": self.reason,
            "source_yield_id": self.source_yield_id,
        }


@dataclass
class SignalPriorityOverride:
    """Temporary green-extension or phase priority override applied to a TrafficSignal."""

    request_id: str
    signal_id: str
    node_id: str
    emergency_vehicle_id: str
    desired_phase: TrafficSignalState
    held_until_s: float
    is_granted: bool
    reason: str = ""

    def is_expired(self, current_time_s: float) -> bool:
        """Check if signal override has elapsed."""
        return current_time_s >= self.held_until_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize signal priority override to dictionary."""
        return {
            "request_id": self.request_id,
            "signal_id": self.signal_id,
            "node_id": self.node_id,
            "emergency_vehicle_id": self.emergency_vehicle_id,
            "desired_phase": self.desired_phase.value,
            "held_until_s": round(self.held_until_s, 4),
            "is_granted": self.is_granted,
            "reason": self.reason,
        }


@dataclass
class EmergencyAwarenessRecord:
    """Local, decentralized record maintained by a vehicle about observed emergency operations."""

    emergency_vehicle_id: str
    emergency_type: EmergencyType
    priority_level: int
    corridor_edges: tuple[str, ...] = field(default_factory=tuple)
    corridor_nodes: tuple[str, ...] = field(default_factory=tuple)
    active_yield_requests: tuple[str, ...] = field(default_factory=tuple)
    last_updated_s: float = 0.0
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize awareness record to dictionary."""
        return {
            "emergency_vehicle_id": self.emergency_vehicle_id,
            "emergency_type": self.emergency_type.value,
            "priority_level": self.priority_level,
            "corridor_edges": list(self.corridor_edges),
            "corridor_nodes": list(self.corridor_nodes),
            "active_yield_requests": list(self.active_yield_requests),
            "last_updated_s": round(self.last_updated_s, 4),
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class EmergencyEvent:
    """Immutable structured audit log of an emergency event."""

    event_id: str
    sim_time_s: float
    event_type: str
    vehicle_id: str
    emergency_type: Optional[EmergencyType] = None
    request_id: Optional[str] = None
    corridor_id: Optional[str] = None
    target_vehicle_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event record to dictionary."""
        return {
            "event_id": self.event_id,
            "sim_time_s": round(self.sim_time_s, 4),
            "event_type": self.event_type,
            "vehicle_id": self.vehicle_id,
            "emergency_type": self.emergency_type.value if self.emergency_type else None,
            "request_id": self.request_id,
            "corridor_id": self.corridor_id,
            "target_vehicle_id": self.target_vehicle_id,
            "details": dict(self.details),
        }
