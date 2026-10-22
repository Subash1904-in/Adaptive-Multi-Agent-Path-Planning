"""Data models and result contracts for scenario orchestration.

Defines immutable scenario configurations, road network source specifications,
vehicle deployment parameters, and structured execution summary results.
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from apps.core.communication.models import CommunicationConfig
from apps.core.coordination.models import CoordinationConfig
from apps.core.decision.config import DecisionConfig
from apps.core.domain.enums import VehicleType
from apps.core.emergency.models import EmergencyConfig, EmergencyType
from apps.core.graph.generator import CityGridConfig
from apps.core.graph.osm_models import OSMImportConfig
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
from apps.core.safety.models import SafetyConfig
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.models import TickResult, WorldSnapshot
from apps.core.telemetry.exceptions import (
    ExportSizeLimitExceededError,
    InvalidExecutionLimitsError,
)
from apps.core.telemetry.models import TelemetryConfig, sanitize_for_json


class RunLifecycleState(str, Enum):
    """Explicit lifecycle states for a scenario execution run."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    LIMIT_REACHED = "LIMIT_REACHED"


TERMINAL_LIFECYCLE_STATES = frozenset(
    {
        RunLifecycleState.COMPLETED,
        RunLifecycleState.CANCELLED,
        RunLifecycleState.FAILED,
        RunLifecycleState.LIMIT_REACHED,
    }
)


class TerminationReason(str, Enum):
    """Reason for scenario run termination."""

    MAX_TICKS_REACHED = "max_ticks_reached"
    DURATION_LIMIT_REACHED = "duration_limit_reached"
    ALL_ARRIVED = "all_arrived"
    TARGET_TICKS_COMPLETED = "target_ticks_completed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class RoadNetworkSourceType(str, Enum):
    """Source type for road network creation."""

    SYNTHETIC_GRID = "synthetic_grid"
    SUPPLIED_GRAPH = "supplied_graph"
    OSM_IMPORT = "osm_import"


@dataclass(frozen=True)
class ScenarioMetadata:
    """Descriptive identification and version metadata for a simulation scenario."""

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }


@dataclass(frozen=True)
class VehicleScenarioDefinition:
    """Deployment specification for an autonomous vehicle agent in a scenario."""

    vehicle_id: str
    start_node_id: str
    destination_node_id: str
    algorithm: Union[str, RoutingAlgorithm] = RoutingAlgorithm.ASTAR
    cost_mode: Union[str, CostMode] = CostMode.TRAVEL_TIME
    closed_edge_ids: tuple[str, ...] = field(default_factory=tuple)
    kinematics: Optional[KinematicsConfig] = None
    initial_speed_mps: float = 0.0
    vehicle_type: VehicleType = VehicleType.STANDARD
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize vehicle definition to a JSON-compatible dictionary."""
        algo = (
            self.algorithm.value
            if isinstance(self.algorithm, RoutingAlgorithm)
            else str(self.algorithm)
        )
        cost = self.cost_mode.value if isinstance(self.cost_mode, CostMode) else str(self.cost_mode)
        v_type = (
            self.vehicle_type.value
            if hasattr(self.vehicle_type, "value")
            else str(self.vehicle_type)
        )
        return {
            "vehicle_id": self.vehicle_id,
            "start_node_id": self.start_node_id,
            "destination_node_id": self.destination_node_id,
            "algorithm": algo,
            "cost_mode": cost,
            "closed_edge_ids": list(self.closed_edge_ids),
            "kinematics": self.kinematics.to_dict() if self.kinematics else None,
            "initial_speed_mps": round(self.initial_speed_mps, 4),
            "vehicle_type": v_type,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TrafficSignalScenarioDefinition:
    """Explicit traffic signal configuration for an intersection in a scenario."""

    signal_id: str
    node_id: str
    config: SignalCycleConfig = field(default_factory=SignalCycleConfig)
    incoming_edge_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize signal definition to a JSON-compatible dictionary."""
        return {
            "signal_id": self.signal_id,
            "node_id": self.node_id,
            "config": self.config.to_dict(),
            "incoming_edge_ids": list(self.incoming_edge_ids),
        }


@dataclass(frozen=True)
class RoadNetworkDefinition:
    """Specification of the road network topology for a scenario."""

    source_type: RoadNetworkSourceType = RoadNetworkSourceType.SYNTHETIC_GRID
    grid_config: Optional[CityGridConfig] = None
    supplied_graph: Optional[RoadGraph] = None
    osm_config: Optional[OSMImportConfig] = None
    allow_osm_fallback: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize road network definition to a JSON-compatible dictionary."""
        return {
            "source_type": self.source_type.value,
            "grid_config": self.grid_config.__dict__ if self.grid_config else None,
            "supplied_graph_name": self.supplied_graph.name if self.supplied_graph else None,
            "osm_config": self.osm_config.to_dict() if self.osm_config else None,
            "allow_osm_fallback": self.allow_osm_fallback,
        }


@dataclass(frozen=True)
class CrosswalkScenarioDefinition:
    """Specification of a crosswalk in a scenario."""

    crosswalk_id: str
    entry_point: tuple[float, float]
    exit_point: tuple[float, float]
    width_m: float = 3.0
    associated_intersection_id: Optional[str] = None
    associated_road_segment_ids: tuple[str, ...] = field(default_factory=tuple)
    signal_controller_id: Optional[str] = None
    walk_signal_phase: Optional[str] = None
    clearance_signal_phase: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize crosswalk definition to dictionary."""
        return {
            "crosswalk_id": self.crosswalk_id,
            "entry_point": list(self.entry_point),
            "exit_point": list(self.exit_point),
            "width_m": self.width_m,
            "associated_intersection_id": self.associated_intersection_id,
            "associated_road_segment_ids": list(self.associated_road_segment_ids),
            "signal_controller_id": self.signal_controller_id,
            "walk_signal_phase": self.walk_signal_phase,
            "clearance_signal_phase": self.clearance_signal_phase,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PedestrianScenarioDefinition:
    """Deployment specification for a pedestrian agent in a scenario."""

    pedestrian_id: str
    initial_position: tuple[float, float]
    destination_point: tuple[float, float]
    crosswalk_id: Optional[str] = None
    initial_heading_rad: float = 0.0
    initial_speed_mps: float = 0.0
    walking_speed_mps: float = 1.4
    max_speed_mps: float = 2.0
    length_m: float = 0.6
    width_m: float = 0.6
    arrival_tolerance_m: float = 0.5
    waiting_distance_m: float = 1.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize pedestrian definition to dictionary."""
        return {
            "pedestrian_id": self.pedestrian_id,
            "initial_position": list(self.initial_position),
            "destination_point": list(self.destination_point),
            "crosswalk_id": self.crosswalk_id,
            "initial_heading_rad": round(self.initial_heading_rad, 4),
            "initial_speed_mps": round(self.initial_speed_mps, 4),
            "walking_speed_mps": round(self.walking_speed_mps, 4),
            "max_speed_mps": round(self.max_speed_mps, 4),
            "length_m": round(self.length_m, 4),
            "width_m": round(self.width_m, 4),
            "arrival_tolerance_m": round(self.arrival_tolerance_m, 4),
            "waiting_distance_m": round(self.waiting_distance_m, 4),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EmergencyVehicleScenarioDefinition:
    """Deployment specification for an emergency vehicle in a scenario."""

    vehicle_id: str
    emergency_type: EmergencyType = EmergencyType.AMBULANCE
    start_node_id: str = ""
    destination_node_id: str = ""
    priority_level: Optional[int] = None
    activate_at_time_s: float = 0.0
    ttl_s: float = 60.0
    auto_activate: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize emergency vehicle definition to dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "emergency_type": (
                self.emergency_type.value
                if hasattr(self.emergency_type, "value")
                else str(self.emergency_type)
            ),
            "start_node_id": self.start_node_id,
            "destination_node_id": self.destination_node_id,
            "priority_level": self.priority_level,
            "activate_at_time_s": round(self.activate_at_time_s, 4),
            "ttl_s": round(self.ttl_s, 4),
            "auto_activate": self.auto_activate,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ScenarioDefinition:
    """Authoritative declaration of a complete simulation scenario."""

    metadata: ScenarioMetadata
    road_network: RoadNetworkDefinition
    vehicles: tuple[VehicleScenarioDefinition, ...]
    signals: tuple[TrafficSignalScenarioDefinition, ...] = field(default_factory=tuple)
    pedestrians: tuple[PedestrianScenarioDefinition, ...] = field(default_factory=tuple)
    crosswalks: tuple[CrosswalkScenarioDefinition, ...] = field(default_factory=tuple)
    emergency_vehicles: tuple[EmergencyVehicleScenarioDefinition, ...] = field(
        default_factory=tuple
    )
    time_step_s: float = 0.1
    max_ticks: Optional[int] = None
    max_duration_s: Optional[float] = None
    stop_on_all_arrived: bool = True
    seed: Optional[int] = None
    allow_unreachable_vehicles: bool = False
    simulation_metadata: dict[str, Any] = field(default_factory=dict)
    v2v_config: Optional[CommunicationConfig] = None
    coordination_config: Optional[CoordinationConfig] = None
    adaptive_routing_config: Optional[AdaptiveRoutingConfig] = None
    safety_config: Optional[SafetyConfig] = None
    emergency_config: Optional[EmergencyConfig] = None
    decision_config: Optional[DecisionConfig] = None

    @property
    def effective_max_ticks(self) -> Optional[int]:
        """Derive authoritative maximum tick count from max_ticks and max_duration_s."""
        if self.max_ticks is not None and self.max_duration_s is not None:
            duration_ticks = max(1, math.ceil(self.max_duration_s / self.time_step_s))
            return min(self.max_ticks, duration_ticks)
        if self.max_ticks is not None:
            return self.max_ticks
        if self.max_duration_s is not None:
            return max(1, math.ceil(self.max_duration_s / self.time_step_s))
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize scenario definition to a plain JSON-compatible dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "road_network": self.road_network.to_dict(),
            "vehicles": [v.to_dict() for v in self.vehicles],
            "signals": [s.to_dict() for s in self.signals],
            "pedestrians": [p.to_dict() for p in self.pedestrians],
            "crosswalks": [c.to_dict() for c in self.crosswalks],
            "emergency_vehicles": [ev.to_dict() for ev in self.emergency_vehicles],
            "time_step_s": round(self.time_step_s, 6),
            "max_ticks": self.max_ticks,
            "max_duration_s": (
                round(self.max_duration_s, 4) if self.max_duration_s is not None else None
            ),
            "effective_max_ticks": self.effective_max_ticks,
            "stop_on_all_arrived": self.stop_on_all_arrived,
            "seed": self.seed,
            "allow_unreachable_vehicles": self.allow_unreachable_vehicles,
            "v2v_config": self.v2v_config.to_dict() if self.v2v_config else None,
            "coordination_config": (
                self.coordination_config.to_dict() if self.coordination_config else None
            ),
            "adaptive_routing_config": (
                self.adaptive_routing_config.to_dict() if self.adaptive_routing_config else None
            ),
            "safety_config": (self.safety_config.to_dict() if self.safety_config else None),
            "emergency_config": (
                self.emergency_config.to_dict() if self.emergency_config else None
            ),
            "decision_config": (self.decision_config.to_dict() if self.decision_config else None),
            "simulation_metadata": dict(self.simulation_metadata),
        }


@dataclass(frozen=True)
class RunConfig:
    """Configuration parameters governing scenario run execution limits and telemetry."""

    run_id: Optional[str] = None
    max_ticks: Optional[int] = None
    max_duration_s: Optional[float] = None
    stop_on_all_arrived: bool = True
    time_step_s: Optional[float] = None
    seed: Optional[int] = None
    telemetry_config: Optional[TelemetryConfig] = None
    max_export_bytes: int = 10_000_000

    def __post_init__(self) -> None:
        """Validate execution limits constraints."""
        if self.max_ticks is not None and self.max_ticks <= 0:
            raise InvalidExecutionLimitsError("max_ticks must be positive.", field="max_ticks")
        if self.max_duration_s is not None and self.max_duration_s <= 0.0:
            raise InvalidExecutionLimitsError(
                "max_duration_s must be positive.", field="max_duration_s"
            )
        if self.time_step_s is not None and self.time_step_s <= 0.0:
            raise InvalidExecutionLimitsError("time_step_s must be positive.", field="time_step_s")
        if self.max_export_bytes <= 0:
            raise InvalidExecutionLimitsError(
                "max_export_bytes must be positive.", field="max_export_bytes"
            )

    def to_dict(self) -> dict[str, Any]:
        """Return serializable dictionary snapshot of run configuration parameters."""
        return {
            "run_id": self.run_id,
            "max_ticks": self.max_ticks,
            "max_duration_s": self.max_duration_s,
            "stop_on_all_arrived": self.stop_on_all_arrived,
            "time_step_s": self.time_step_s,
            "seed": self.seed,
            "max_export_bytes": self.max_export_bytes,
        }



@dataclass(frozen=True)
class RunMetadata:
    """Reproducibility and provenance metadata for an executed simulation run."""

    run_id: str
    scenario_id: str
    scenario_name: str
    scenario_version: str
    scenario_fingerprint: str
    initial_world_state_fingerprint: str
    final_world_state_fingerprint: Optional[str] = None
    commit_sha: Optional[str] = None
    start_simulation_time_s: float = 0.0
    time_step_s: float = 0.1
    seed: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize run metadata to a JSON-compatible dictionary."""
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "scenario_fingerprint": self.scenario_fingerprint,
            "initial_world_state_fingerprint": self.initial_world_state_fingerprint,
            "final_world_state_fingerprint": self.final_world_state_fingerprint,
            "commit_sha": self.commit_sha,
            "start_simulation_time_s": round(self.start_simulation_time_s, 6),
            "time_step_s": round(self.time_step_s, 6),
            "seed": self.seed,
        }


@dataclass(frozen=True)
class ScenarioExecutionResult:
    """Structured result emitted upon scenario run completion or termination."""

    scenario_id: str
    scenario_name: str
    scenario_version: str
    termination_reason: TerminationReason
    initial_tick: int
    final_tick: int
    completed_ticks: int
    elapsed_time_s: float
    time_step_s: float
    total_vehicles: int
    arrived_count: int
    arrived_vehicle_ids: tuple[str, ...]
    active_count: int
    active_vehicle_ids: tuple[str, ...]
    final_world_snapshot: WorldSnapshot
    tick_results: Optional[tuple[TickResult, ...]] = None
    is_success: bool = True
    error_message: Optional[str] = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    lifecycle_state: RunLifecycleState = RunLifecycleState.COMPLETED
    run_metadata: Optional[RunMetadata] = None
    metrics_summary: Optional[dict[str, Any]] = None
    telemetry_drop_stats: Optional[dict[str, Any]] = None
    cancellation_reason: Optional[str] = None
    telemetry_records: Optional[tuple[dict[str, Any], ...]] = None
    is_partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution result to a JSON-compatible dictionary.

        Excludes non-deterministic wall-clock timestamps from output comparisons.
        """
        base = {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "termination_reason": (
                self.termination_reason.value
                if hasattr(self.termination_reason, "value")
                else str(self.termination_reason)
            ),
            "initial_tick": self.initial_tick,
            "final_tick": self.final_tick,
            "completed_ticks": self.completed_ticks,
            "elapsed_time_s": round(self.elapsed_time_s, 4),
            "time_step_s": round(self.time_step_s, 6),
            "total_vehicles": self.total_vehicles,
            "arrived_count": self.arrived_count,
            "arrived_vehicle_ids": list(self.arrived_vehicle_ids),
            "active_count": self.active_count,
            "active_vehicle_ids": list(self.active_vehicle_ids),
            "final_world_snapshot": self.final_world_snapshot.to_dict(),
            "is_success": self.is_success,
            "error_message": self.error_message,
            "diagnostics": dict(self.diagnostics),
            "run_id": self.run_id,
            "lifecycle_state": (
                self.lifecycle_state.value
                if hasattr(self.lifecycle_state, "value")
                else str(self.lifecycle_state)
            ),
            "run_metadata": self.run_metadata.to_dict() if self.run_metadata else None,
            "metrics_summary": self.metrics_summary,
            "telemetry_drop_stats": self.telemetry_drop_stats,
            "cancellation_reason": self.cancellation_reason,
            "is_partial": self.is_partial,
        }
        if self.telemetry_records is not None:
            base["telemetry_records"] = list(self.telemetry_records)
        return base

    def to_json(
        self,
        indent: Optional[int] = None,
        max_size_bytes: int = 10_000_000,
        max_telemetry_records: Optional[int] = None,
    ) -> str:
        """Serialize execution result to an RFC 8259 valid JSON string with size guardrails.

        Args:
            indent: Optional indentation for pretty-printing.
            max_size_bytes: Maximum allowed payload byte size before raising
                ExportSizeLimitExceededError.
            max_telemetry_records: Optional cap on telemetry records included in export.

        Returns:
            Valid JSON string representation.

        Raises:
            ExportSizeLimitExceededError: If serialized bytes exceed max_size_bytes.
        """
        d = self.to_dict()
        if (
            max_telemetry_records is not None
            and "telemetry_records" in d
            and d["telemetry_records"]
        ):
            d["telemetry_records"] = d["telemetry_records"][:max_telemetry_records]
        sanitized = sanitize_for_json(d)
        serialized = json.dumps(sanitized, indent=indent, sort_keys=True, allow_nan=False)
        encoded_bytes = len(serialized.encode("utf-8"))
        if encoded_bytes > max_size_bytes:
            raise ExportSizeLimitExceededError(
                f"Export payload size ({encoded_bytes} bytes) exceeds limit "
                f"({max_size_bytes} bytes).",
                size_bytes=encoded_bytes,
                max_bytes=max_size_bytes,
                run_id=self.run_id,
            )
        return serialized
