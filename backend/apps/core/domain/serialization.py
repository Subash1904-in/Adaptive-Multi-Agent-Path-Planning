"""Serialization contracts and codecs for AMAPP domain entities.

Provides JSON-compatible dictionary conversion (to_dict) and type-safe
reconstruction (from_dict) for all domain entities and value objects.
No external serialization dependencies required.
"""

import json
from enum import Enum
from typing import Any, Type, TypeVar

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
from apps.core.domain.exceptions import DomainValidationError, SerializationError
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
from apps.core.domain.values import Dimensions2D, GeoCoordinate, Position2D

T = TypeVar("T")


def to_dict(obj: Any) -> Any:
    """Recursively convert a domain model, value object, or collection to a JSON-compatible dict."""
    if obj is None:
        return None
    if isinstance(obj, (int, float, str, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (Position2D, GeoCoordinate, Dimensions2D)):
        return obj.to_dict()
    if isinstance(
        obj,
        (
            RoadNode,
            RoadEdge,
            Route,
            Vehicle,
            Pedestrian,
            TrafficSignal,
            Obstacle,
            Incident,
            V2VMessage,
            SimulationConfig,
        ),
    ):
        result = {}
        for k, v in obj.__dict__.items():
            result[k] = to_dict(v)
        return result
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    raise SerializationError(f"Unsupported object type for serialization: {type(obj).__name__}")


def to_json(obj: Any, **kwargs: Any) -> str:
    """Serialize a domain model or value object to a JSON formatted string."""
    return json.dumps(to_dict(obj), **kwargs)


def _parse_enum(enum_cls: Type[Enum], value: Any, field_name: str) -> Any:
    """Safely parse an enum instance or string value."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            valid_vals = [e.value for e in enum_cls]
            raise SerializationError(
                f"Invalid value '{value}' for {enum_cls.__name__}. Valid values: {valid_vals}.",
                field=field_name,
            ) from None
    raise SerializationError(
        f"Expected string or {enum_cls.__name__} for field '{field_name}', "
        f"got {type(value).__name__}.",
        field=field_name,
    )


def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
    """Deserialize a dictionary into a typed domain entity or value object."""
    if not isinstance(data, dict):
        raise SerializationError(
            f"Expected a dictionary for {cls.__name__}, got {type(data).__name__}."
        )

    try:
        if cls is Position2D:
            return Position2D.from_dict(data)  # type: ignore[return-value]

        if cls is GeoCoordinate:
            return GeoCoordinate.from_dict(data)  # type: ignore[return-value]

        if cls is Dimensions2D:
            return Dimensions2D.from_dict(data)  # type: ignore[return-value]

        if cls is RoadNode:
            pos_data = data.get("position")
            if pos_data is None:
                raise SerializationError("Missing required field 'position'.", field="position")
            pos = from_dict(Position2D, pos_data)

            geo_data = data.get("geo_coordinate")
            geo = from_dict(GeoCoordinate, geo_data) if geo_data is not None else None

            return RoadNode(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                position=pos,
                geo_coordinate=geo,
                attributes=data.get("attributes", {}),
            )

        if cls is RoadEdge:
            return RoadEdge(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                start_node_id=data.get("start_node_id"),  # type: ignore[arg-type]
                end_node_id=data.get("end_node_id"),  # type: ignore[arg-type]
                length_m=data.get("length_m"),  # type: ignore[arg-type]
                speed_limit_mps=data.get("speed_limit_mps"),  # type: ignore[arg-type]
                lanes=data.get("lanes", 1),
                name=data.get("name"),
                attributes=data.get("attributes", {}),
            )

        if cls is Route:
            return Route(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                node_ids=data.get("node_ids"),  # type: ignore[arg-type]
                edge_ids=data.get("edge_ids", []),
                total_distance_m=data.get("total_distance_m"),
                estimated_duration_s=data.get("estimated_duration_s"),
            )

        if cls is Vehicle:
            pos_data = data.get("position")
            if pos_data is None:
                raise SerializationError("Missing required field 'position'.", field="position")
            pos = from_dict(Position2D, pos_data)

            dim_data = data.get("dimensions")
            dim = (
                from_dict(Dimensions2D, dim_data)
                if dim_data is not None
                else Dimensions2D(4.5, 2.0)
            )

            state_val = data.get("state", VehicleState.IDLE.value)
            state = _parse_enum(VehicleState, state_val, "state")

            type_val = data.get("vehicle_type", VehicleType.STANDARD.value)
            vehicle_type = _parse_enum(VehicleType, type_val, "vehicle_type")

            return Vehicle(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                position=pos,
                speed_mps=data.get("speed_mps", 0.0),
                max_speed_mps=data.get("max_speed_mps", 13.89),
                heading_rad=data.get("heading_rad", 0.0),
                state=state,
                vehicle_type=vehicle_type,
                dimensions=dim,
                current_node_id=data.get("current_node_id"),
                current_edge_id=data.get("current_edge_id"),
                route_id=data.get("route_id"),
                target_node_id=data.get("target_node_id"),
            )

        if cls is Pedestrian:
            pos_data = data.get("position")
            if pos_data is None:
                raise SerializationError("Missing required field 'position'.", field="position")
            pos = from_dict(Position2D, pos_data)

            state_val = data.get("state", PedestrianState.WAITING.value)
            state = _parse_enum(PedestrianState, state_val, "state")

            target_data = data.get("target_position")
            target_pos = from_dict(Position2D, target_data) if target_data is not None else None

            return Pedestrian(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                position=pos,
                state=state,
                speed_mps=data.get("speed_mps", 0.0),
                max_speed_mps=data.get("max_speed_mps", 1.4),
                crossing_node_id=data.get("crossing_node_id"),
                target_position=target_pos,
            )

        if cls is TrafficSignal:
            state_val = data.get("state", TrafficSignalState.RED.value)
            state = _parse_enum(TrafficSignalState, state_val, "state")

            pos_data = data.get("position")
            pos = from_dict(Position2D, pos_data) if pos_data is not None else None

            return TrafficSignal(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                node_id=data.get("node_id"),  # type: ignore[arg-type]
                state=state,
                position=pos,
                cycle_duration_s=data.get("cycle_duration_s", 60.0),
                remaining_phase_s=data.get("remaining_phase_s", 30.0),
            )

        if cls is Obstacle:
            pos_data = data.get("position")
            if pos_data is None:
                raise SerializationError("Missing required field 'position'.", field="position")
            pos = from_dict(Position2D, pos_data)

            dim_data = data.get("dimensions")
            dim = (
                from_dict(Dimensions2D, dim_data)
                if dim_data is not None
                else Dimensions2D(1.0, 1.0)
            )

            type_val = data.get("obstacle_type", ObstacleType.STATIC_BARRIER.value)
            obs_type = _parse_enum(ObstacleType, type_val, "obstacle_type")

            return Obstacle(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                position=pos,
                obstacle_type=obs_type,
                dimensions=dim,
                edge_id=data.get("edge_id"),
                description=data.get("description"),
            )

        if cls is Incident:
            pos_data = data.get("position")
            if pos_data is None:
                raise SerializationError("Missing required field 'position'.", field="position")
            pos = from_dict(Position2D, pos_data)

            inc_type = _parse_enum(
                IncidentType,
                data.get("incident_type", IncidentType.ACCIDENT.value),
                "incident_type",
            )
            sev = _parse_enum(
                IncidentSeverity,
                data.get("severity", IncidentSeverity.MEDIUM.value),
                "severity",
            )
            stat = _parse_enum(
                IncidentStatus,
                data.get("status", IncidentStatus.ACTIVE.value),
                "status",
            )

            sig_phase = None
            if data.get("target_signal_phase") is not None:
                sig_phase = _parse_enum(
                    TrafficSignalState,
                    data.get("target_signal_phase"),
                    "target_signal_phase",
                )

            obs_type = None
            if data.get("obstacle_type") is not None:
                obs_type = _parse_enum(
                    ObstacleType,
                    data.get("obstacle_type"),
                    "obstacle_type",
                )

            return Incident(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                position=pos,
                incident_type=inc_type,
                severity=sev,
                status=stat,
                affected_edge_id=data.get("affected_edge_id"),
                affected_node_id=data.get("affected_node_id"),
                reported_timestamp_s=data.get("reported_timestamp_s", 0.0),
                description=data.get("description"),
                duration_s=data.get("duration_s"),
                target_signal_phase=sig_phase,
                congestion_factor=data.get("congestion_factor"),
                obstacle_type=obs_type,
                metadata=data.get("metadata", {}),
            )

        if cls is V2VMessage:
            msg_type = _parse_enum(V2VMessageType, data.get("message_type"), "message_type")

            pos_data = data.get("sender_position")
            sender_pos = from_dict(Position2D, pos_data) if pos_data is not None else None

            return V2VMessage(  # type: ignore[return-value]
                id=data.get("id"),  # type: ignore[arg-type]
                sender_id=data.get("sender_id"),  # type: ignore[arg-type]
                recipient_id=data.get("recipient_id"),
                message_type=msg_type,
                timestamp_s=data.get("timestamp_s"),  # type: ignore[arg-type]
                expiry_timestamp_s=data.get("expiry_timestamp_s"),
                sender_position=sender_pos,
                payload=data.get("payload", {}),
            )

        if cls is SimulationConfig:
            return SimulationConfig(  # type: ignore[return-value]
                time_step_s=data.get("time_step_s", 0.1),
                random_seed=data.get("random_seed", 42),
                communication_radius_m=data.get("communication_radius_m", 150.0),
                max_simulation_time_s=data.get("max_simulation_time_s", 3600.0),
                max_vehicles=data.get("max_vehicles", 100),
                enable_v2v=data.get("enable_v2v", True),
                grid_width_m=data.get("grid_width_m", 1000.0),
                grid_height_m=data.get("grid_height_m", 1000.0),
            )

    except DomainValidationError as e:
        raise SerializationError(
            f"Validation failed during deserialization of {cls.__name__}: {e.message}",
            field=e.field,
        ) from e
    except (TypeError, KeyError) as e:
        raise SerializationError(f"Malformed data for {cls.__name__}: {e}") from e

    raise SerializationError(f"Unsupported class for deserialization: {cls.__name__}")


def from_json(cls: Type[T], json_str: str) -> T:
    """Deserialize a JSON string into a typed domain entity or value object."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise SerializationError(f"Malformed JSON string: {e}") from e
    return from_dict(cls, data)
