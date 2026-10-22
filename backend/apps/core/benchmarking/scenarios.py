"""Standardized benchmark scenarios and scenario registry for AMAPP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.core.benchmarking.exceptions import UnsupportedScenarioError
from apps.core.communication.models import CommunicationConfig
from apps.core.emergency.models import EmergencyConfig, EmergencyType
from apps.core.graph.generator import CityGridConfig
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import CostMode, RoutingAlgorithm
from apps.core.safety.models import SafetyConfig
from apps.core.scenarios.models import (
    EmergencyVehicleScenarioDefinition,
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.signals.models import SignalCycleConfig


@dataclass(frozen=True)
class BenchmarkScenarioDefinition:
    """Descriptor and factory wrapper for a standardized benchmark scenario."""

    scenario_id: str
    name: str
    version: str
    description: str
    tags: tuple[str, ...]
    factory_fn: Callable[[int], ScenarioDefinition]

    def create_scenario(self, seed: int = 42) -> ScenarioDefinition:
        """Instantiate an isolated ScenarioDefinition with the provided seed."""
        return self.factory_fn(seed)

    def to_dict(self) -> dict[str, Any]:
        """Convert descriptor to a JSON-serializable dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tags": list(self.tags),
        }


# ==============================================================================
# Scenario 1: Sparse Synthetic 3x3 Grid (Baseline)
# ==============================================================================
def _create_bench_grid_sparse_3x3(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_01",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_acceleration_mps2=3.0),
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_grid_sparse_3x3",
            name="Sparse Synthetic 3x3 Grid",
            description="Single vehicle diagonal traversal on a 3x3 grid.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v1,),
        time_step_s=0.1,
        max_ticks=250,
        stop_on_all_arrived=True,
        seed=seed,
    )


# ==============================================================================
# Scenario 2: Medium-Density Urban 4x4 Grid
# ==============================================================================
def _create_bench_urban_medium_4x4(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    v_north = VehicleScenarioDefinition(
        vehicle_id="veh_north",
        start_node_id="node_r0_c0",
        destination_node_id="node_r3_c0",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    v_south = VehicleScenarioDefinition(
        vehicle_id="veh_south",
        start_node_id="node_r3_c3",
        destination_node_id="node_r0_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    v_east = VehicleScenarioDefinition(
        vehicle_id="veh_east",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    v_west = VehicleScenarioDefinition(
        vehicle_id="veh_west",
        start_node_id="node_r2_c3",
        destination_node_id="node_r2_c0",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_urban_medium_4x4",
            name="Medium-Density Urban 4x4 Grid",
            description="Four vehicles traversing crossing paths on a 4x4 grid.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v_north, v_south, v_east, v_west),
        time_step_s=0.1,
        max_ticks=300,
        stop_on_all_arrived=True,
        seed=seed,
        safety_config=SafetyConfig(enabled=True),
    )


# ==============================================================================
# Scenario 3: Dense Multi-Vehicle 5x5 Urban Corridor
# ==============================================================================
def _create_bench_dense_corridor_5x5(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=5,
        cols=5,
        spacing_m=45.0,
        speed_limit_mps=11.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    vehicles = []
    # 8 vehicles with varied origins and destinations
    coords = [
        ("v0", "node_r0_c0", "node_r4_c4"),
        ("v1", "node_r4_c0", "node_r0_c4"),
        ("v2", "node_r0_c4", "node_r4_c0"),
        ("v3", "node_r4_c4", "node_r0_c0"),
        ("v4", "node_r2_c0", "node_r2_c4"),
        ("v5", "node_r2_c4", "node_r2_c0"),
        ("v6", "node_r0_c2", "node_r4_c2"),
        ("v7", "node_r4_c2", "node_r0_c2"),
    ]
    for vid, s, d in coords:
        vehicles.append(
            VehicleScenarioDefinition(
                vehicle_id=vid,
                start_node_id=s,
                destination_node_id=d,
                algorithm=RoutingAlgorithm.ASTAR,
                cost_mode=CostMode.TRAVEL_TIME,
                initial_speed_mps=0.0,
            )
        )

    sig_cfg = SignalCycleConfig(green_duration_s=10.0, yellow_duration_s=2.0, red_duration_s=10.0)
    sig = TrafficSignalScenarioDefinition(
        signal_id="sig_center_5x5", node_id="node_r2_c2", config=sig_cfg
    )

    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_dense_corridor_5x5",
            name="Dense Multi-Vehicle 5x5 Urban Corridor",
            description="Eight vehicles crossing an active signalized 5x5 network.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=tuple(vehicles),
        signals=(sig,),
        time_step_s=0.1,
        max_ticks=350,
        stop_on_all_arrived=True,
        seed=seed,
        safety_config=SafetyConfig(enabled=True),
    )


# ==============================================================================
# Scenario 4: Incident Detour: Closed Roadway Segment
# ==============================================================================
def _create_bench_incident_closure(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    # Direct horizontal path on Row 0 is blocked at first segment
    v_detour = VehicleScenarioDefinition(
        vehicle_id="veh_detour",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        closed_edge_ids=("edge_r0_c0_to_r0_c1",),
        initial_speed_mps=0.0,
    )
    v_cross = VehicleScenarioDefinition(
        vehicle_id="veh_cross",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_incident_closure",
            name="Incident Detour: Closed Roadway Segment",
            description="Vehicle navigating around a closed edge on the primary corridor.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v_detour, v_cross),
        time_step_s=0.1,
        max_ticks=280,
        stop_on_all_arrived=True,
        seed=seed,
    )


# ==============================================================================
# Scenario 5: Dynamic Congestion Corridor
# ==============================================================================
def _create_bench_incident_congestion(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_c1",
        start_node_id="node_r0_c1",
        destination_node_id="node_r3_c1",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_c2",
        start_node_id="node_r0_c2",
        destination_node_id="node_r3_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_incident_congestion",
            name="Dynamic Congestion Corridor",
            description="Vehicles traversing parallel corridors under congestion simulation.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v1, v2),
        time_step_s=0.1,
        max_ticks=300,
        stop_on_all_arrived=True,
        seed=seed,
    )


# ==============================================================================
# Scenario 6: Infeasible Destination Partition
# ==============================================================================
def _create_bench_infeasible_barrier(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    # Block both incoming edges to node_r2_c2
    v_infeasible = VehicleScenarioDefinition(
        vehicle_id="veh_blocked",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        closed_edge_ids=("edge_r1_c2_to_r2_c2", "edge_r2_c1_to_r2_c2"),
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_infeasible_barrier",
            name="Infeasible Destination Partition",
            description="Destination node is completely partitioned with no valid path.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v_infeasible,),
        time_step_s=0.1,
        max_ticks=50,
        stop_on_all_arrived=True,
        allow_unreachable_vehicles=True,
        seed=seed,
    )


# ==============================================================================
# Scenario 7: Emergency Vehicle Priority Navigation
# ==============================================================================
def _create_bench_emergency_corridor(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    v_civilian = VehicleScenarioDefinition(
        vehicle_id="veh_civ_01",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    v_ambulance = EmergencyVehicleScenarioDefinition(
        vehicle_id="amb_01",
        start_node_id="node_r0_c1",
        destination_node_id="node_r3_c1",
        emergency_type=EmergencyType.AMBULANCE,
        priority_level=1,
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_emergency_corridor",
            name="Emergency Vehicle Priority Navigation",
            description="Ambulance traversing along emergency corridor with civilian traffic.",
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v_civilian,),
        emergency_vehicles=(v_ambulance,),
        time_step_s=0.1,
        max_ticks=300,
        stop_on_all_arrived=True,
        seed=seed,
        emergency_config=EmergencyConfig(enabled=True),
        safety_config=SafetyConfig(enabled=True),
    )


# ==============================================================================
# Scenario 8: Degraded V2V Communication Network
# ==============================================================================
def _create_bench_v2v_degradation(seed: int) -> ScenarioDefinition:
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_v2v_1",
        start_node_id="node_r0_c0",
        destination_node_id="node_r3_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_v2v_2",
        start_node_id="node_r0_c1",
        destination_node_id="node_r3_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    v3 = VehicleScenarioDefinition(
        vehicle_id="veh_v2v_3",
        start_node_id="node_r1_c0",
        destination_node_id="node_r2_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="bench_v2v_degradation",
            name="Degraded V2V Communication Network",
            description=(
                "Three vehicles communicating with spatial range constraints and packet loss."
            ),
            version="1.0.0",
        ),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=grid_cfg,
        ),
        vehicles=(v1, v2, v3),
        time_step_s=0.1,
        max_ticks=300,
        stop_on_all_arrived=True,
        seed=seed,
        v2v_config=CommunicationConfig(
            enabled=True,
            communication_range_m=40.0,
            packet_loss_probability=0.15,
            broadcast_interval_ticks=5,
        ),
    )


# ==============================================================================
# Scenario Registry
# ==============================================================================
class BenchmarkScenarioRegistry:
    """Registry maintaining standardized benchmark scenarios."""

    def __init__(self) -> None:
        self._scenarios: dict[str, BenchmarkScenarioDefinition] = {}

    def register(self, definition: BenchmarkScenarioDefinition) -> None:
        """Register a benchmark scenario descriptor."""
        self._scenarios[definition.scenario_id.lower()] = definition

    def get(self, scenario_id: str) -> BenchmarkScenarioDefinition:
        """Retrieve a benchmark scenario by ID or raise UnsupportedScenarioError."""
        key = scenario_id.strip().lower()
        if key not in self._scenarios:
            raise UnsupportedScenarioError(
                scenario_id=scenario_id,
                available_scenarios=sorted(self._scenarios.keys()),
            )
        return self._scenarios[key]

    def list_scenarios(self) -> list[dict[str, Any]]:
        """Return descriptors for all registered benchmark scenarios."""
        return [sc.to_dict() for sc in self._scenarios.values()]

    @classmethod
    def get_default_registry(cls) -> "BenchmarkScenarioRegistry":
        """Instantiate a registry preloaded with all 8 standard AMAPP benchmark scenarios."""
        reg = cls()
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_grid_sparse_3x3",
                name="Sparse Synthetic 3x3 Grid",
                version="1.0.0",
                description="Single vehicle diagonal traversal on a 3x3 grid.",
                tags=("synthetic", "sparse", "baseline"),
                factory_fn=_create_bench_grid_sparse_3x3,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_urban_medium_4x4",
                name="Medium-Density Urban 4x4 Grid",
                version="1.0.0",
                description="Four vehicles traversing crossing paths on a 4x4 grid.",
                tags=("synthetic", "medium_density", "multi_vehicle"),
                factory_fn=_create_bench_urban_medium_4x4,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_dense_corridor_5x5",
                name="Dense Multi-Vehicle 5x5 Urban Corridor",
                version="1.0.0",
                description="Eight vehicles crossing an active signalized 5x5 network.",
                tags=("synthetic", "dense", "signals"),
                factory_fn=_create_bench_dense_corridor_5x5,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_incident_closure",
                name="Incident Detour: Closed Roadway Segment",
                version="1.0.0",
                description="Vehicle navigating around a closed edge on the primary corridor.",
                tags=("incident", "closure", "detour"),
                factory_fn=_create_bench_incident_closure,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_incident_congestion",
                name="Dynamic Congestion Corridor",
                version="1.0.0",
                description="Vehicles traversing parallel corridors under congestion simulation.",
                tags=("incident", "congestion", "rerouting"),
                factory_fn=_create_bench_incident_congestion,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_infeasible_barrier",
                name="Infeasible Destination Partition",
                version="1.0.0",
                description="Destination node is completely partitioned with no valid path.",
                tags=("failure", "infeasible", "safety"),
                factory_fn=_create_bench_infeasible_barrier,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_emergency_corridor",
                name="Emergency Vehicle Priority Navigation",
                version="1.0.0",
                description="Ambulance traversing along emergency corridor with civilian traffic.",
                tags=("emergency", "priority", "yielding"),
                factory_fn=_create_bench_emergency_corridor,
            )
        )
        reg.register(
            BenchmarkScenarioDefinition(
                scenario_id="bench_v2v_degradation",
                name="Degraded V2V Communication Network",
                version="1.0.0",
                description=(
                    "Three vehicles communicating with spatial range constraints and packet loss."
                ),
                tags=("v2v", "communication", "degradation"),
                factory_fn=_create_bench_v2v_degradation,
            )
        )
        return reg
