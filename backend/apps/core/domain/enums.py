"""Domain enumerations for the AMAPP simulation platform.

All enums inherit from `str, Enum` for reliable string-based serialization
and JSON interoperability.
"""

from enum import Enum


class VehicleState(str, Enum):
    """Operational lifecycle state of an autonomous vehicle agent."""

    IDLE = "idle"
    EN_ROUTE = "en_route"
    WAITING_AT_SIGNAL = "waiting_at_signal"
    STOPPED = "stopped"
    BLOCKED = "blocked"
    REROUTING = "rerouting"
    ARRIVED = "arrived"


class VehicleType(str, Enum):
    """Classification of vehicle agent."""

    STANDARD = "standard"
    EMERGENCY = "emergency"


class TrafficSignalState(str, Enum):
    """State of an intersection traffic signal phase."""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class IncidentType(str, Enum):
    """Category of roadway incident or disruption."""

    ACCIDENT = "accident"
    ROAD_CLOSURE = "road_closure"
    CONGESTION = "congestion"
    HAZARD = "hazard"
    OBSTACLE = "obstacle"
    SIGNAL_OVERRIDE = "signal_override"


class IncidentSeverity(str, Enum):
    """Impact severity level of a roadway incident."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Operational resolution status of an incident."""

    ACTIVE = "active"
    RESOLVED = "resolved"


class ObstacleType(str, Enum):
    """Physical obstacle classification impeding roadway movement."""

    CONSTRUCTION = "construction"
    DEBRIS = "debris"
    STALLED_VEHICLE = "stalled_vehicle"
    STATIC_BARRIER = "static_barrier"


class V2VMessageType(str, Enum):
    """Semantic type of peer-to-peer V2V broadcast message."""

    HAZARD_WARNING = "hazard_warning"
    CONGESTION_ALERT = "congestion_alert"
    EMERGENCY_CORRIDOR = "emergency_corridor"
    ROUTE_ADVISORY = "route_advisory"
    HEARTBEAT = "heartbeat"
    # Phase 18 Emergency Vehicle Priority & Corridor operations
    EMERGENCY_ACTIVATED = "emergency_activated"
    PRIORITY_REQUEST = "priority_request"
    CORRIDOR_PROPOSED = "corridor_proposed"
    YIELD_REQUEST = "yield_request"
    YIELD_ACKNOWLEDGED = "yield_acknowledged"
    CORRIDOR_UPDATED = "corridor_updated"
    PRIORITY_CANCELLED = "priority_cancelled"
    EMERGENCY_COMPLETED = "emergency_completed"


class PedestrianState(str, Enum):
    """Physical state of a pedestrian agent relative to crosswalks."""

    WAITING = "waiting"
    CROSSING = "crossing"
    SAFE = "safe"
