"""Data models, snapshots, and typed result contracts for simulation.

Provides immutable representations of vehicle states, world states, tick results,
and engine status enumerations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.kinematics.models import MotionStepResult


class EngineStatus(str, Enum):
    """Lifecycle and operational status of the simulation engine."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class VehicleSnapshot:
    """Immutable point-in-time state of an individual vehicle agent."""

    vehicle_id: str
    state: VehicleState
    position: Position2D
    heading_rad: float
    speed_mps: float
    current_edge_id: Optional[str]
    current_node_id: Optional[str]
    distance_along_segment_m: float
    remaining_route_distance_m: float
    route_id: Optional[str] = None
    target_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize vehicle snapshot to a plain JSON-compatible dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "state": self.state.value,
            "position": self.position.to_dict(),
            "heading_rad": round(self.heading_rad, 6),
            "speed_mps": round(self.speed_mps, 4),
            "current_edge_id": self.current_edge_id,
            "current_node_id": self.current_node_id,
            "distance_along_segment_m": round(self.distance_along_segment_m, 4),
            "remaining_route_distance_m": round(self.remaining_route_distance_m, 4),
            "route_id": self.route_id,
            "target_node_id": self.target_node_id,
        }


@dataclass(frozen=True)
class WorldSnapshot:
    """Immutable point-in-time snapshot of the overall simulation world."""

    tick: int
    elapsed_time_s: float
    time_step_s: float
    is_paused: bool
    agent_count: int
    vehicles: dict[str, VehicleSnapshot]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize world snapshot to a plain JSON-compatible dictionary."""
        return {
            "tick": self.tick,
            "elapsed_time_s": self.elapsed_time_s,
            "time_step_s": self.time_step_s,
            "is_paused": self.is_paused,
            "agent_count": self.agent_count,
            "vehicles": {vid: snap.to_dict() for vid, snap in self.vehicles.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TickResult:
    """Comprehensive typed result emitted after every completed simulation tick."""

    tick: int
    elapsed_time_s: float
    time_step_s: float
    agent_count: int
    step_results: dict[str, MotionStepResult]
    arrived_agent_ids: list[str]
    active_agent_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize tick result to a plain JSON-compatible dictionary."""
        return {
            "tick": self.tick,
            "elapsed_time_s": self.elapsed_time_s,
            "time_step_s": self.time_step_s,
            "agent_count": self.agent_count,
            "step_results": {vid: res.to_dict() for vid, res in self.step_results.items()},
            "arrived_agent_ids": list(self.arrived_agent_ids),
            "active_agent_ids": list(self.active_agent_ids),
        }
