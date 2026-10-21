"""Data models and serialization contracts for simulation telemetry streams.

Defines typed telemetry records, categories, schema versioning, retention configurations,
and drop counter statistics with non-finite numeric sanitization for valid JSON export.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from apps.core.telemetry.exceptions import (
    TelemetryValidationError,
    UnsupportedSchemaError,
)

TELEMETRY_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})


class TelemetryRecordType(str, Enum):
    """Categorical classification of telemetry observations."""

    RUN_STATE_CHANGE = "RUN_STATE_CHANGE"
    WORLD_SNAPSHOT = "WORLD_SNAPSHOT"
    VEHICLE_STATE = "VEHICLE_STATE"
    PEDESTRIAN_STATE = "PEDESTRIAN_STATE"
    ROUTE_CHANGE = "ROUTE_CHANGE"
    COMMUNICATION_EVENT = "COMMUNICATION_EVENT"
    COORDINATION_EVENT = "COORDINATION_EVENT"
    SAFETY_EVENT = "SAFETY_EVENT"
    COLLISION_EVENT = "COLLISION_EVENT"
    SIGNAL_EVENT = "SIGNAL_EVENT"
    EMERGENCY_EVENT = "EMERGENCY_EVENT"
    DECISION_EVENT = "DECISION_EVENT"
    METRICS_SNAPSHOT = "METRICS_SNAPSHOT"
    ERROR = "ERROR"


CRITICAL_RECORD_TYPES = frozenset(
    {
        TelemetryRecordType.SAFETY_EVENT,
        TelemetryRecordType.COLLISION_EVENT,
        TelemetryRecordType.ERROR,
        TelemetryRecordType.RUN_STATE_CHANGE,
    }
)


def sanitize_for_json(data: Any) -> Any:
    """Recursively sanitize data structures for RFC 8259 valid JSON serialization.

    Converts non-finite floating-point numbers (nan, inf, -inf) into deterministic string
    representations, maps Enums to values, and transforms nested mappings/iterables.
    """
    if isinstance(data, float):
        if math.isnan(data):
            return "NaN"
        if math.isinf(data):
            return "Infinity" if data > 0 else "-Infinity"
        return round(data, 6)
    if isinstance(data, (int, str, bool)) or data is None:
        return data
    if isinstance(data, Enum):
        return data.value
    if hasattr(data, "to_dict") and callable(data.to_dict):
        return sanitize_for_json(data.to_dict())
    if isinstance(data, dict):
        return {str(k): sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set, frozenset)):
        return [sanitize_for_json(item) for item in data]
    return str(data)


@dataclass(frozen=True)
class TelemetryRecord:
    """Immutable, typed observation emitted by the simulation engine or subsystems."""

    record_id: str
    run_id: str
    tick_index: int
    simulation_time_s: float
    record_type: TelemetryRecordType
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[str] = None
    correlation_id: Optional[str] = None
    schema_version: str = TELEMETRY_SCHEMA_VERSION
    sequence_number: int = 0

    def __post_init__(self) -> None:
        """Validate record structure and invariant constraints."""
        if not self.record_id:
            raise TelemetryValidationError(
                "record_id must be a non-empty string.", field="record_id"
            )
        if not self.run_id:
            raise TelemetryValidationError("run_id must be a non-empty string.", field="run_id")
        if self.tick_index < 0:
            raise TelemetryValidationError("tick_index must be non-negative.", field="tick_index")
        if self.simulation_time_s < 0.0:
            raise TelemetryValidationError(
                "simulation_time_s must be non-negative.", field="simulation_time_s"
            )
        if not self.name:
            raise TelemetryValidationError("name must be a non-empty string.", field="name")
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError(
                f"Unsupported telemetry schema version: '{self.schema_version}'. "
                f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
                schema_version=self.schema_version,
                run_id=self.run_id,
            )

    @property
    def is_critical(self) -> bool:
        """Indicates whether this record is of a critical type that must not be silently dropped."""
        return self.record_type in CRITICAL_RECORD_TYPES

    def to_dict(self) -> dict[str, Any]:
        """Serialize telemetry record to a JSON-compatible dictionary."""
        return {
            "record_id": self.record_id,
            "run_id": self.run_id,
            "tick_index": self.tick_index,
            "simulation_time_s": round(self.simulation_time_s, 6),
            "record_type": (
                self.record_type.value
                if isinstance(self.record_type, TelemetryRecordType)
                else str(self.record_type)
            ),
            "name": self.name,
            "payload": sanitize_for_json(self.payload),
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "schema_version": self.schema_version,
            "sequence_number": self.sequence_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TelemetryRecord":
        """Reconstruct a validated TelemetryRecord from serialized dictionary."""
        schema_ver = data.get("schema_version", TELEMETRY_SCHEMA_VERSION)
        if schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError(
                f"Unsupported telemetry schema version: '{schema_ver}'. "
                f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
                schema_version=schema_ver,
                run_id=data.get("run_id"),
            )
        raw_type = data.get("record_type")
        try:
            rec_type = TelemetryRecordType(raw_type)
        except ValueError as exc:
            raise TelemetryValidationError(
                f"Invalid record_type: '{raw_type}'.", field="record_type"
            ) from exc

        return cls(
            record_id=str(data.get("record_id", "")),
            run_id=str(data.get("run_id", "")),
            tick_index=int(data.get("tick_index", 0)),
            simulation_time_s=float(data.get("simulation_time_s", 0.0)),
            record_type=rec_type,
            name=str(data.get("name", "")),
            payload=dict(data.get("payload", {})),
            agent_id=data.get("agent_id"),
            correlation_id=data.get("correlation_id"),
            schema_version=schema_ver,
            sequence_number=int(data.get("sequence_number", 0)),
        )


@dataclass(frozen=True)
class TelemetryConfig:
    """Configuration governing in-process telemetry collection, snapshotting, and retention."""

    enabled: bool = True
    max_records: int = 5000
    snapshot_interval_ticks: int = 1
    enabled_categories: Optional[frozenset[TelemetryRecordType]] = None
    strict_retention: bool = False
    schema_version: str = TELEMETRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate telemetry configuration parameters."""
        if self.max_records <= 0:
            raise TelemetryValidationError("max_records must be positive.", field="max_records")
        if self.snapshot_interval_ticks <= 0:
            raise TelemetryValidationError(
                "snapshot_interval_ticks must be positive.", field="snapshot_interval_ticks"
            )
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError(
                f"Unsupported telemetry schema version: '{self.schema_version}'.",
                schema_version=self.schema_version,
            )

    def is_category_enabled(self, category: Union[TelemetryRecordType, str]) -> bool:
        """Determine if a record category should be collected."""
        if not self.enabled:
            return False
        cat = (
            category if isinstance(category, TelemetryRecordType) else TelemetryRecordType(category)
        )
        if cat in CRITICAL_RECORD_TYPES:
            return True
        if self.enabled_categories is None:
            return True
        return cat in self.enabled_categories

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        categories = (
            [c.value for c in sorted(self.enabled_categories, key=lambda x: x.value)]
            if self.enabled_categories is not None
            else None
        )
        return {
            "enabled": self.enabled,
            "max_records": self.max_records,
            "snapshot_interval_ticks": self.snapshot_interval_ticks,
            "enabled_categories": categories,
            "strict_retention": self.strict_retention,
            "schema_version": self.schema_version,
        }


@dataclass
class TelemetryDropStats:
    """Tracks counts of dropped telemetry records caused by buffer capacity limits."""

    total_dropped: int = 0
    dropped_by_category: dict[str, int] = field(default_factory=dict)

    def record_drop(self, category: str, count: int = 1) -> None:
        """Increment drop count for a specific category."""
        self.total_dropped += count
        self.dropped_by_category[category] = self.dropped_by_category.get(category, 0) + count

    def to_dict(self) -> dict[str, Any]:
        """Serialize drop statistics to a dictionary."""
        return {
            "total_dropped": self.total_dropped,
            "dropped_by_category": dict(self.dropped_by_category),
        }
