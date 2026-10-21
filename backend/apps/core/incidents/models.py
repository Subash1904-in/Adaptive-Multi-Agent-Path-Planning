"""Data models and snapshot contracts for the traffic incident management subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from apps.core.domain.enums import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    ObstacleType,
    TrafficSignalState,
)
from apps.core.domain.values import Position2D


@dataclass
class IncidentRecord:
    """Authoritative representation of an active or resolved roadway incident."""

    id: str
    incident_type: IncidentType
    position: Position2D
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.ACTIVE
    affected_edge_id: Optional[str] = None
    affected_node_id: Optional[str] = None
    reported_timestamp_s: float = 0.0
    duration_s: Optional[float] = None
    description: Optional[str] = None
    congestion_factor: Optional[float] = None
    target_signal_phase: Optional[TrafficSignalState] = None
    obstacle_type: Optional[ObstacleType] = None
    resolved_timestamp_s: Optional[float] = None
    created_tick: int = 0
    resolved_tick: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, current_time_s: float) -> bool:
        """Evaluate if this incident has reached its configured duration."""
        if self.duration_s is None or self.duration_s <= 0.0:
            return False
        expiry_time = self.reported_timestamp_s + self.duration_s
        return (current_time_s - expiry_time) >= -1e-7

    @property
    def remaining_duration_s(self) -> Optional[float]:
        """Compute remaining duration relative to reported time."""
        if self.duration_s is None:
            return None
        return self.duration_s

    def calculate_remaining_s(self, current_time_s: float) -> Optional[float]:
        """Compute seconds remaining before expiration."""
        if self.duration_s is None:
            return None
        expiry_time = self.reported_timestamp_s + self.duration_s
        return max(0.0, expiry_time - current_time_s)

    def to_dict(self) -> dict[str, Any]:
        """Convert incident record to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "incident_type": self.incident_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "affected_edge_id": self.affected_edge_id,
            "affected_node_id": self.affected_node_id,
            "position": self.position.to_dict(),
            "reported_timestamp_s": round(self.reported_timestamp_s, 4),
            "duration_s": round(self.duration_s, 4) if self.duration_s is not None else None,
            "description": self.description,
            "congestion_factor": (
                round(self.congestion_factor, 4) if self.congestion_factor is not None else None
            ),
            "target_signal_phase": (
                self.target_signal_phase.value if self.target_signal_phase is not None else None
            ),
            "obstacle_type": self.obstacle_type.value if self.obstacle_type is not None else None,
            "resolved_timestamp_s": (
                round(self.resolved_timestamp_s, 4)
                if self.resolved_timestamp_s is not None
                else None
            ),
            "created_tick": self.created_tick,
            "resolved_tick": self.resolved_tick,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class IncidentSubsystemSnapshot:
    """Immutable point-in-time snapshot of the overall incident management subsystem."""

    active_incidents: list[dict[str, Any]]
    resolved_incidents: list[dict[str, Any]]
    closed_edge_ids: list[str]
    congestion_modifiers: dict[str, float]
    active_signal_overrides: dict[str, str]
    total_created: int
    total_resolved: int
    total_active: int

    def to_dict(self) -> dict[str, Any]:
        """Convert subsystem snapshot to a JSON-compatible dictionary."""
        return {
            "active_incidents": list(self.active_incidents),
            "resolved_incidents": list(self.resolved_incidents),
            "closed_edge_ids": sorted(self.closed_edge_ids),
            "congestion_modifiers": dict(self.congestion_modifiers),
            "active_signal_overrides": dict(self.active_signal_overrides),
            "total_created": self.total_created,
            "total_resolved": self.total_resolved,
            "total_active": self.total_active,
        }
