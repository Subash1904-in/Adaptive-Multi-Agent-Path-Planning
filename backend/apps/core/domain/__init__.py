"""AMAPP Core Domain Package.

Exposes typed domain entities, immutable value types, enumerations,
validation exceptions, and serialization contracts for the simulation platform.
"""

from apps.core.domain.enums import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    ObstacleType,
    PedestrianState,
    TrafficSignalState,
    V2VMessageType,
    VehicleState,
    VehicleType,
)
from apps.core.domain.exceptions import (
    DomainException,
    DomainValidationError,
    SerializationError,
)
from apps.core.domain.models import (
    Incident,
    Obstacle,
    Pedestrian,
    RoadEdge,
    RoadNode,
    Route,
    SimulationConfig,
    TrafficSignal,
    V2VMessage,
    Vehicle,
)
from apps.core.domain.serialization import (
    from_dict,
    from_json,
    to_dict,
    to_json,
)
from apps.core.domain.values import (
    Dimensions2D,
    GeoCoordinate,
    Position2D,
)

__all__ = [
    # Exceptions
    "DomainException",
    "DomainValidationError",
    "SerializationError",
    # Enums
    "VehicleState",
    "VehicleType",
    "TrafficSignalState",
    "IncidentType",
    "IncidentSeverity",
    "IncidentStatus",
    "ObstacleType",
    "V2VMessageType",
    "PedestrianState",
    # Value Types
    "Position2D",
    "GeoCoordinate",
    "Dimensions2D",
    # Domain Models
    "RoadNode",
    "RoadEdge",
    "Route",
    "Vehicle",
    "Pedestrian",
    "TrafficSignal",
    "Obstacle",
    "Incident",
    "V2VMessage",
    "SimulationConfig",
    # Serialization
    "to_dict",
    "to_json",
    "from_dict",
    "from_json",
]
