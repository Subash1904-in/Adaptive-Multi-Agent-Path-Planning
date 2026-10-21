"""Data models, snapshots, and typed result contracts for simulation.

Provides immutable representations of vehicle states, world states, tick results,
and engine status enumerations.
"""

from dataclasses import dataclass, field
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
    signals: dict[str, Any] = field(default_factory=dict)
    communication: Optional[dict[str, Any]] = None
    coordination: Optional[dict[str, Any]] = None
    routing: Optional[dict[str, Any]] = None
    safety: Optional[dict[str, Any]] = None
    pedestrians: dict[str, Any] = field(default_factory=dict)
    crosswalks: dict[str, Any] = field(default_factory=dict)
    pedestrian_metrics: Optional[dict[str, Any]] = None
    emergency: dict[str, Any] = field(default_factory=dict)
    corridors: dict[str, Any] = field(default_factory=dict)
    emergency_metrics: Optional[dict[str, Any]] = None
    decision_metrics: Optional[dict[str, Any]] = None
    decision_records: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize world snapshot to a plain JSON-compatible dictionary."""
        comm_dict = (
            self.communication.to_dict()
            if hasattr(self.communication, "to_dict")
            else self.communication
        )
        coord_dict = (
            self.coordination.to_dict()
            if hasattr(self.coordination, "to_dict")
            else self.coordination
        )
        routing_dict = self.routing.to_dict() if hasattr(self.routing, "to_dict") else self.routing
        safety_dict = self.safety.to_dict() if hasattr(self.safety, "to_dict") else self.safety
        return {
            "tick": self.tick,
            "elapsed_time_s": self.elapsed_time_s,
            "time_step_s": self.time_step_s,
            "is_paused": self.is_paused,
            "agent_count": self.agent_count,
            "vehicles": {vid: snap.to_dict() for vid, snap in self.vehicles.items()},
            "signals": {
                sid: snap.to_dict() if hasattr(snap, "to_dict") else snap
                for sid, snap in self.signals.items()
            },
            "communication": comm_dict,
            "coordination": coord_dict,
            "routing": routing_dict,
            "safety": safety_dict,
            "pedestrians": {
                pid: snap.to_dict() if hasattr(snap, "to_dict") else snap
                for pid, snap in self.pedestrians.items()
            },
            "crosswalks": {
                cwid: cw.to_dict() if hasattr(cw, "to_dict") else cw
                for cwid, cw in self.crosswalks.items()
            },
            "pedestrian_metrics": (
                dict(self.pedestrian_metrics) if self.pedestrian_metrics else None
            ),
            "emergency": dict(self.emergency),
            "corridors": dict(self.corridors),
            "emergency_metrics": (dict(self.emergency_metrics) if self.emergency_metrics else None),
            "decision_metrics": (dict(self.decision_metrics) if self.decision_metrics else None),
            "decision_records": (list(self.decision_records) if self.decision_records else None),
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
    signal_states: dict[str, Any] = field(default_factory=dict)
    communication_metrics: Optional[dict[str, int]] = None
    coordination_metrics: Optional[dict[str, int]] = None
    routing_metrics: Optional[dict[str, Any]] = None
    routing_decisions: Optional[list[dict[str, Any]]] = None
    safety_metrics: Optional[dict[str, Any]] = None
    safety_events: Optional[list[dict[str, Any]]] = None
    pedestrian_step_results: dict[str, Any] = field(default_factory=dict)
    pedestrian_metrics: Optional[dict[str, Any]] = None
    emergency_metrics: Optional[dict[str, Any]] = None
    emergency_events: Optional[list[dict[str, Any]]] = None
    corridors: Optional[dict[str, Any]] = None
    yield_decisions: Optional[dict[str, Any]] = None
    decision_metrics: Optional[dict[str, Any]] = None
    decision_records: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize tick result to a plain JSON-compatible dictionary."""
        return {
            "tick": self.tick,
            "elapsed_time_s": self.elapsed_time_s,
            "time_step_s": self.time_step_s,
            "agent_count": self.agent_count,
            "step_results": {vid: res.to_dict() for vid, res in self.step_results.items()},
            "signal_states": {
                sid: st.value if hasattr(st, "value") else str(st)
                for sid, st in self.signal_states.items()
            },
            "communication_metrics": (
                dict(self.communication_metrics) if self.communication_metrics else None
            ),
            "coordination_metrics": (
                dict(self.coordination_metrics) if self.coordination_metrics else None
            ),
            "routing_metrics": (dict(self.routing_metrics) if self.routing_metrics else None),
            "routing_decisions": (list(self.routing_decisions) if self.routing_decisions else None),
            "safety_metrics": (dict(self.safety_metrics) if self.safety_metrics else None),
            "safety_events": (list(self.safety_events) if self.safety_events else None),
            "pedestrian_step_results": {
                pid: res.to_dict() if hasattr(res, "to_dict") else res
                for pid, res in self.pedestrian_step_results.items()
            },
            "pedestrian_metrics": (
                dict(self.pedestrian_metrics) if self.pedestrian_metrics else None
            ),
            "emergency_metrics": (dict(self.emergency_metrics) if self.emergency_metrics else None),
            "emergency_events": (list(self.emergency_events) if self.emergency_events else None),
            "corridors": (dict(self.corridors) if self.corridors else None),
            "yield_decisions": (dict(self.yield_decisions) if self.yield_decisions else None),
            "decision_metrics": (dict(self.decision_metrics) if self.decision_metrics else None),
            "decision_records": (list(self.decision_records) if self.decision_records else None),
            "arrived_agent_ids": list(self.arrived_agent_ids),
            "active_agent_ids": list(self.active_agent_ids),
        }
