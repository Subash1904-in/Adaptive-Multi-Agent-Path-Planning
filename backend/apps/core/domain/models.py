"""Typed domain models for the AMAPP simulation platform.

This module defines the 10 core domain entities:
1. RoadNode
2. RoadEdge
3. Route
4. Vehicle
5. Pedestrian
6. TrafficSignal
7. Obstacle
8. Incident
9. V2VMessage
10. SimulationConfig

All models are pure Python dataclasses decoupled from Django's ORM.
Validation occurs on construction via `__post_init__`, raising `DomainValidationError`.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Optional

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
from apps.core.domain.exceptions import DomainValidationError
from apps.core.domain.values import Dimensions2D, GeoCoordinate, Position2D


def _validate_id(identifier: str, field_name: str) -> str:
    """Validate that an identifier is a non-empty string."""
    if not isinstance(identifier, str):
        raise DomainValidationError(
            f"Identifier must be a string, got {type(identifier).__name__}.",
            field=field_name,
        )
    cleaned = identifier.strip()
    if not cleaned:
        raise DomainValidationError("Identifier cannot be empty or whitespace.", field=field_name)
    return cleaned


def _validate_non_negative(value: float, field_name: str) -> float:
    """Validate that a numeric value is finite and >= 0.0."""
    if not isinstance(value, (int, float)):
        raise DomainValidationError(
            f"Value must be numeric, got {type(value).__name__}.",
            field=field_name,
        )
    if not math.isfinite(value):
        raise DomainValidationError("Value must be a finite number.", field=field_name)
    if value < 0.0:
        raise DomainValidationError(
            f"Value must be non-negative (>= 0.0), got {value}.",
            field=field_name,
        )
    return float(value)


def _validate_positive(value: float, field_name: str) -> float:
    """Validate that a numeric value is finite and > 0.0."""
    if not isinstance(value, (int, float)):
        raise DomainValidationError(
            f"Value must be numeric, got {type(value).__name__}.",
            field=field_name,
        )
    if not math.isfinite(value):
        raise DomainValidationError("Value must be a finite number.", field=field_name)
    if value <= 0.0:
        raise DomainValidationError(
            f"Value must be strictly positive (> 0.0), got {value}.",
            field=field_name,
        )
    return float(value)


# -----------------------------------------------------------------------------
# 1. RoadNode
# -----------------------------------------------------------------------------
@dataclass
class RoadNode:
    """A spatial intersection or topological endpoint in the road network.

    Attributes:
        id: Unique node identifier.
        position: Planar 2D position in meters.
        geo_coordinate: Optional WGS84 geographic coordinate for OSM mapping.
        attributes: Extensible metadata dictionary (e.g., osm_id, is_intersection).
    """

    id: str
    position: Position2D
    geo_coordinate: Optional[GeoCoordinate] = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "RoadNode position must be an instance of Position2D.", field="position"
            )
        if self.geo_coordinate is not None and not isinstance(self.geo_coordinate, GeoCoordinate):
            raise DomainValidationError(
                "geo_coordinate must be an instance of GeoCoordinate or None.",
                field="geo_coordinate",
            )
        if not isinstance(self.attributes, dict):
            raise DomainValidationError("attributes must be a dictionary.", field="attributes")


# -----------------------------------------------------------------------------
# 2. RoadEdge
# -----------------------------------------------------------------------------
@dataclass
class RoadEdge:
    """A directed roadway segment connecting two RoadNodes.

    Attributes:
        id: Unique edge identifier.
        start_node_id: Identifier of the source RoadNode.
        end_node_id: Identifier of the destination RoadNode.
        length_m: Road segment length in meters (> 0.0).
        speed_limit_mps: Maximum legal speed limit in meters per second (> 0.0).
        lanes: Number of travel lanes (>= 1).
        name: Optional roadway or street name.
        attributes: Extensible metadata dictionary (e.g., highway_type, one_way).
    """

    id: str
    start_node_id: str
    end_node_id: str
    length_m: float
    speed_limit_mps: float
    lanes: int = 1
    name: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        self.start_node_id = _validate_id(self.start_node_id, "start_node_id")
        self.end_node_id = _validate_id(self.end_node_id, "end_node_id")
        if self.start_node_id == self.end_node_id:
            raise DomainValidationError(
                f"RoadEdge cannot connect a node to itself: '{self.start_node_id}'.",
                field="end_node_id",
            )
        self.length_m = _validate_positive(self.length_m, "length_m")
        self.speed_limit_mps = _validate_positive(self.speed_limit_mps, "speed_limit_mps")
        if not isinstance(self.lanes, int) or self.lanes < 1:
            raise DomainValidationError(
                f"Lanes must be an integer >= 1, got {self.lanes}.", field="lanes"
            )
        if self.name is not None and not isinstance(self.name, str):
            raise DomainValidationError("RoadEdge name must be a string or None.", field="name")
        if not isinstance(self.attributes, dict):
            raise DomainValidationError("attributes must be a dictionary.", field="attributes")


# -----------------------------------------------------------------------------
# 3. Route
# -----------------------------------------------------------------------------
@dataclass
class Route:
    """An ordered navigation path traversing the road network graph.

    Attributes:
        id: Unique route identifier.
        node_ids: Ordered sequence of at least 2 road node identifiers.
        edge_ids: Optional sequence of corresponding road edge identifiers.
        total_distance_m: Optional cached total route distance in meters (>= 0.0).
        estimated_duration_s: Optional estimated travel duration in seconds (>= 0.0).
    """

    id: str
    node_ids: list[str]
    edge_ids: list[str] = field(default_factory=list)
    total_distance_m: Optional[float] = None
    estimated_duration_s: Optional[float] = None

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.node_ids, list):
            raise DomainValidationError(
                "Route node_ids must be a list of string node IDs.", field="node_ids"
            )
        if len(self.node_ids) < 2:
            raise DomainValidationError(
                f"Route must contain at least 2 nodes, got {len(self.node_ids)}.",
                field="node_ids",
            )
        self.node_ids = [_validate_id(nid, "node_ids") for nid in self.node_ids]

        if not isinstance(self.edge_ids, list):
            raise DomainValidationError(
                "Route edge_ids must be a list of string edge IDs.", field="edge_ids"
            )
        self.edge_ids = [_validate_id(eid, "edge_ids") for eid in self.edge_ids]

        if self.total_distance_m is not None:
            self.total_distance_m = _validate_non_negative(
                self.total_distance_m, "total_distance_m"
            )
        if self.estimated_duration_s is not None:
            self.estimated_duration_s = _validate_non_negative(
                self.estimated_duration_s, "estimated_duration_s"
            )


# -----------------------------------------------------------------------------
# 4. Vehicle
# -----------------------------------------------------------------------------
@dataclass
class Vehicle:
    """An autonomous or emergency vehicle agent within the simulation.

    Attributes:
        id: Unique vehicle identifier.
        position: Authoritative 2D planar position in meters.
        speed_mps: Current longitudinal speed in meters per second (>= 0.0).
        max_speed_mps: Maximum vehicle speed capability in m/s (> 0.0).
        heading_rad: Orientation heading angle in radians [0.0, 2*pi).
        state: Current operational lifecycle state.
        vehicle_type: Vehicle classification (STANDARD or EMERGENCY).
        dimensions: Vehicle physical length and width footprint in meters.
        current_node_id: Optional reference to nearest or current node.
        current_edge_id: Optional reference to road edge currently occupied.
        route_id: Optional reference to active navigation Route.
        target_node_id: Optional final destination node identifier.
    """

    id: str
    position: Position2D
    speed_mps: float = 0.0
    max_speed_mps: float = 13.89  # ~50 km/h default
    heading_rad: float = 0.0
    state: VehicleState = VehicleState.IDLE
    vehicle_type: VehicleType = VehicleType.STANDARD
    dimensions: Dimensions2D = field(
        default_factory=lambda: Dimensions2D(length_m=4.5, width_m=2.0)
    )
    current_node_id: Optional[str] = None
    current_edge_id: Optional[str] = None
    route_id: Optional[str] = None
    target_node_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "Vehicle position must be an instance of Position2D.", field="position"
            )
        self.max_speed_mps = _validate_positive(self.max_speed_mps, "max_speed_mps")
        self.speed_mps = _validate_non_negative(self.speed_mps, "speed_mps")
        if self.speed_mps > self.max_speed_mps + 1e-6:
            raise DomainValidationError(
                f"Vehicle speed ({self.speed_mps:.2f} m/s) cannot exceed "
                f"max speed ({self.max_speed_mps:.2f} m/s).",
                field="speed_mps",
            )
        if not isinstance(self.heading_rad, (int, float)) or not math.isfinite(self.heading_rad):
            raise DomainValidationError(
                "Vehicle heading_rad must be a finite number.", field="heading_rad"
            )
        # Normalize heading to [0.0, 2*pi)
        self.heading_rad = float(self.heading_rad % (2.0 * math.pi))

        if not isinstance(self.state, VehicleState):
            raise DomainValidationError(f"Invalid vehicle state: {self.state}.", field="state")
        if not isinstance(self.vehicle_type, VehicleType):
            raise DomainValidationError(
                f"Invalid vehicle type: {self.vehicle_type}.", field="vehicle_type"
            )
        if not isinstance(self.dimensions, Dimensions2D):
            raise DomainValidationError(
                "Vehicle dimensions must be an instance of Dimensions2D.", field="dimensions"
            )

        if self.current_node_id is not None:
            self.current_node_id = _validate_id(self.current_node_id, "current_node_id")
        if self.current_edge_id is not None:
            self.current_edge_id = _validate_id(self.current_edge_id, "current_edge_id")
        if self.route_id is not None:
            self.route_id = _validate_id(self.route_id, "route_id")
        if self.target_node_id is not None:
            self.target_node_id = _validate_id(self.target_node_id, "target_node_id")


# -----------------------------------------------------------------------------
# 5. Pedestrian
# -----------------------------------------------------------------------------
@dataclass
class Pedestrian:
    """A pedestrian agent navigating crosswalks or road shoulders.

    Attributes:
        id: Unique pedestrian identifier.
        position: Authoritative 2D position in meters.
        state: Current pedestrian crossing state.
        speed_mps: Current walking speed in meters per second (>= 0.0).
        max_speed_mps: Maximum walking speed capability in m/s (> 0.0).
        crossing_node_id: Optional crosswalk / intersection node reference.
        target_position: Optional target destination position in meters.
    """

    id: str
    position: Position2D
    state: PedestrianState = PedestrianState.WAITING
    speed_mps: float = 0.0
    max_speed_mps: float = 1.4  # ~5 km/h average walking speed
    crossing_node_id: Optional[str] = None
    target_position: Optional[Position2D] = None

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "Pedestrian position must be an instance of Position2D.", field="position"
            )
        if not isinstance(self.state, PedestrianState):
            raise DomainValidationError(f"Invalid pedestrian state: {self.state}.", field="state")
        self.max_speed_mps = _validate_positive(self.max_speed_mps, "max_speed_mps")
        self.speed_mps = _validate_non_negative(self.speed_mps, "speed_mps")
        if self.speed_mps > self.max_speed_mps + 1e-6:
            raise DomainValidationError(
                f"Pedestrian speed ({self.speed_mps} m/s) cannot exceed "
                f"max speed ({self.max_speed_mps} m/s).",
                field="speed_mps",
            )
        if self.crossing_node_id is not None:
            self.crossing_node_id = _validate_id(self.crossing_node_id, "crossing_node_id")
        if self.target_position is not None and not isinstance(self.target_position, Position2D):
            raise DomainValidationError(
                "target_position must be an instance of Position2D or None.",
                field="target_position",
            )


# -----------------------------------------------------------------------------
# 6. TrafficSignal
# -----------------------------------------------------------------------------
@dataclass
class TrafficSignal:
    """A traffic signal governing an intersection node.

    Attributes:
        id: Unique traffic signal identifier.
        node_id: Controlled intersection RoadNode identifier.
        state: Current signal phase (RED, YELLOW, GREEN).
        position: Optional spatial position in meters.
        cycle_duration_s: Full signal cycle period in seconds (> 0.0).
        remaining_phase_s: Time remaining in current phase in seconds (>= 0.0).
    """

    id: str
    node_id: str
    state: TrafficSignalState = TrafficSignalState.RED
    position: Optional[Position2D] = None
    cycle_duration_s: float = 60.0
    remaining_phase_s: float = 30.0

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        self.node_id = _validate_id(self.node_id, "node_id")
        if not isinstance(self.state, TrafficSignalState):
            raise DomainValidationError(
                f"Invalid traffic signal state: {self.state}.", field="state"
            )
        if self.position is not None and not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "position must be an instance of Position2D or None.", field="position"
            )
        self.cycle_duration_s = _validate_positive(self.cycle_duration_s, "cycle_duration_s")
        self.remaining_phase_s = _validate_non_negative(
            self.remaining_phase_s, "remaining_phase_s"
        )
        if self.remaining_phase_s > self.cycle_duration_s + 1e-6:
            raise DomainValidationError(
                f"remaining_phase_s ({self.remaining_phase_s}) cannot exceed "
                f"cycle_duration_s ({self.cycle_duration_s}).",
                field="remaining_phase_s",
            )


# -----------------------------------------------------------------------------
# 7. Obstacle
# -----------------------------------------------------------------------------
@dataclass
class Obstacle:
    """A physical stationary obstacle obstructing a roadway.

    Attributes:
        id: Unique obstacle identifier.
        position: Planar position in meters.
        obstacle_type: Classification of obstacle (CONSTRUCTION, DEBRIS, etc.).
        dimensions: Physical bounding footprint (length and width in meters).
        edge_id: Optional RoadEdge identifier where obstacle is positioned.
        description: Optional human-readable description.
    """

    id: str
    position: Position2D
    obstacle_type: ObstacleType = ObstacleType.STATIC_BARRIER
    dimensions: Dimensions2D = field(
        default_factory=lambda: Dimensions2D(length_m=1.0, width_m=1.0)
    )
    edge_id: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "Obstacle position must be an instance of Position2D.", field="position"
            )
        if not isinstance(self.obstacle_type, ObstacleType):
            raise DomainValidationError(
                f"Invalid obstacle type: {self.obstacle_type}.", field="obstacle_type"
            )
        if not isinstance(self.dimensions, Dimensions2D):
            raise DomainValidationError(
                "Obstacle dimensions must be an instance of Dimensions2D.", field="dimensions"
            )
        if self.edge_id is not None:
            self.edge_id = _validate_id(self.edge_id, "edge_id")
        if self.description is not None and not isinstance(self.description, str):
            raise DomainValidationError(
                "description must be a string or None.", field="description"
            )


# -----------------------------------------------------------------------------
# 8. Incident
# -----------------------------------------------------------------------------
@dataclass
class Incident:
    """A dynamic roadway incident (accident, road closure, hazard, congestion).

    Attributes:
        id: Unique incident identifier.
        position: Spatial coordinate of incident in meters.
        incident_type: Category of incident (ACCIDENT, ROAD_CLOSURE, etc.).
        severity: Impact severity level (LOW, MEDIUM, HIGH, CRITICAL).
        status: Operational resolution status (ACTIVE, RESOLVED).
        affected_edge_id: Optional RoadEdge identifier impeded by incident.
        affected_node_id: Optional RoadNode identifier impeded by incident.
        reported_timestamp_s: Simulation time when incident was reported (>= 0.0).
        description: Optional human-readable explanation.
    """

    id: str
    position: Position2D
    incident_type: IncidentType = IncidentType.ACCIDENT
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.ACTIVE
    affected_edge_id: Optional[str] = None
    affected_node_id: Optional[str] = None
    reported_timestamp_s: float = 0.0
    description: Optional[str] = None

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        if not isinstance(self.position, Position2D):
            raise DomainValidationError(
                "Incident position must be an instance of Position2D.", field="position"
            )
        if not isinstance(self.incident_type, IncidentType):
            raise DomainValidationError(
                f"Invalid incident type: {self.incident_type}.", field="incident_type"
            )
        if not isinstance(self.severity, IncidentSeverity):
            raise DomainValidationError(
                f"Invalid incident severity: {self.severity}.", field="severity"
            )
        if not isinstance(self.status, IncidentStatus):
            raise DomainValidationError(
                f"Invalid incident status: {self.status}.", field="status"
            )
        if self.affected_edge_id is not None:
            self.affected_edge_id = _validate_id(self.affected_edge_id, "affected_edge_id")
        if self.affected_node_id is not None:
            self.affected_node_id = _validate_id(self.affected_node_id, "affected_node_id")
        self.reported_timestamp_s = _validate_non_negative(
            self.reported_timestamp_s, "reported_timestamp_s"
        )
        if self.description is not None and not isinstance(self.description, str):
            raise DomainValidationError(
                "description must be a string or None.", field="description"
            )


# -----------------------------------------------------------------------------
# 9. V2VMessage
# -----------------------------------------------------------------------------
@dataclass
class V2VMessage:
    """A peer-to-peer or broadcast Vehicle-to-Vehicle communication packet.

    Attributes:
        id: Unique message packet identifier.
        sender_id: Identifier of the transmitting vehicle agent.
        recipient_id: Identifier of target recipient, or None for spatial broadcast.
        message_type: Semantic purpose of message (HAZARD_WARNING, etc.).
        timestamp_s: Simulation dispatch timestamp in seconds (>= 0.0).
        expiry_timestamp_s: Optional expiration timestamp in seconds (>= timestamp_s).
        sender_position: Optional spatial location of sender at dispatch time.
        payload: Structured telemetry, hazard, or coordination dictionary.
    """

    id: str
    sender_id: str
    message_type: V2VMessageType
    timestamp_s: float
    recipient_id: Optional[str] = None
    expiry_timestamp_s: Optional[float] = None
    sender_position: Optional[Position2D] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _validate_id(self.id, "id")
        self.sender_id = _validate_id(self.sender_id, "sender_id")
        if self.recipient_id is not None:
            self.recipient_id = _validate_id(self.recipient_id, "recipient_id")
        if not isinstance(self.message_type, V2VMessageType):
            raise DomainValidationError(
                f"Invalid V2V message type: {self.message_type}.", field="message_type"
            )
        self.timestamp_s = _validate_non_negative(self.timestamp_s, "timestamp_s")
        if self.expiry_timestamp_s is not None:
            self.expiry_timestamp_s = _validate_non_negative(
                self.expiry_timestamp_s, "expiry_timestamp_s"
            )
            if self.expiry_timestamp_s < self.timestamp_s:
                raise DomainValidationError(
                    f"expiry_timestamp_s ({self.expiry_timestamp_s}) cannot be earlier than "
                    f"timestamp_s ({self.timestamp_s}).",
                    field="expiry_timestamp_s",
                )
        if self.sender_position is not None and not isinstance(self.sender_position, Position2D):
            raise DomainValidationError(
                "sender_position must be an instance of Position2D or None.",
                field="sender_position",
            )
        if not isinstance(self.payload, dict):
            raise DomainValidationError("payload must be a dictionary.", field="payload")


# -----------------------------------------------------------------------------
# 10. SimulationConfig
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class SimulationConfig:
    """Validated configuration parameters for a simulation run.

    Attributes:
        time_step_s: Discrete simulation clock step size in seconds (0.01 <= dt <= 2.0).
        random_seed: Deterministic pseudorandom seed.
        communication_radius_m: V2V direct broadcast radius in meters (> 0.0).
        max_simulation_time_s: Simulation timeout horizon in seconds (> 0.0).
        max_vehicles: Maximum concurrent vehicle capacity (> 0).
        enable_v2v: Flag enabling or disabling V2V peer-to-peer communication.
        grid_width_m: Synthetic city grid boundary width in meters (> 0.0).
        grid_height_m: Synthetic city grid boundary height in meters (> 0.0).
    """

    time_step_s: float = 0.1
    random_seed: int = 42
    communication_radius_m: float = 150.0
    max_simulation_time_s: float = 3600.0
    max_vehicles: int = 100
    enable_v2v: bool = True
    grid_width_m: float = 1000.0
    grid_height_m: float = 1000.0

    def __post_init__(self) -> None:
        if not isinstance(self.time_step_s, (int, float)) or not math.isfinite(self.time_step_s):
            raise DomainValidationError(
                "time_step_s must be a finite numeric value.", field="time_step_s"
            )
        if not (0.001 <= self.time_step_s <= 2.0):
            raise DomainValidationError(
                f"time_step_s must be in range [0.001, 2.0] seconds, got {self.time_step_s}.",
                field="time_step_s",
            )
        object.__setattr__(self, "time_step_s", float(self.time_step_s))

        if not isinstance(self.random_seed, int):
            raise DomainValidationError("random_seed must be an integer.", field="random_seed")

        object.__setattr__(
            self,
            "communication_radius_m",
            _validate_positive(self.communication_radius_m, "communication_radius_m"),
        )
        object.__setattr__(
            self,
            "max_simulation_time_s",
            _validate_positive(self.max_simulation_time_s, "max_simulation_time_s"),
        )

        if not isinstance(self.max_vehicles, int) or self.max_vehicles < 1:
            raise DomainValidationError(
                f"max_vehicles must be an integer >= 1, got {self.max_vehicles}.",
                field="max_vehicles",
            )

        if not isinstance(self.enable_v2v, bool):
            raise DomainValidationError("enable_v2v must be a boolean.", field="enable_v2v")

        object.__setattr__(
            self,
            "grid_width_m",
            _validate_positive(self.grid_width_m, "grid_width_m"),
        )
        object.__setattr__(
            self,
            "grid_height_m",
            _validate_positive(self.grid_height_m, "grid_height_m"),
        )
