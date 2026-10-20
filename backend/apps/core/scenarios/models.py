"""Data models and result contracts for scenario orchestration.

Defines immutable scenario configurations, road network source specifications,
vehicle deployment parameters, and structured execution summary results.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from apps.core.communication.models import CommunicationConfig
from apps.core.coordination.models import CoordinationConfig
from apps.core.domain.enums import VehicleType
from apps.core.graph.generator import CityGridConfig
from apps.core.graph.osm_models import OSMImportConfig
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.models import TickResult, WorldSnapshot


class TerminationReason(str, Enum):
    """Reason for scenario run termination."""

    MAX_TICKS_REACHED = "max_ticks_reached"
    ALL_ARRIVED = "all_arrived"
    TARGET_TICKS_COMPLETED = "target_ticks_completed"
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
class ScenarioDefinition:
    """Authoritative declaration of a complete simulation scenario."""

    metadata: ScenarioMetadata
    road_network: RoadNetworkDefinition
    vehicles: tuple[VehicleScenarioDefinition, ...]
    signals: tuple[TrafficSignalScenarioDefinition, ...] = field(default_factory=tuple)
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
                self.adaptive_routing_config.to_dict()
                if self.adaptive_routing_config
                else None
            ),
            "simulation_metadata": dict(self.simulation_metadata),
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution result to a JSON-compatible dictionary.

        Excludes wall-clock timestamps from deterministic output comparisons.
        """
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "termination_reason": self.termination_reason.value,
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
        }
