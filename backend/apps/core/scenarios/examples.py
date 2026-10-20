"""Standard programmatic scenario definitions for AMAPP testing and demonstration.

Provides compact, offline, and deterministic scenario templates illustrating:
- Single-vehicle synthetic grid navigation
- Multi-vehicle simultaneous routing
- Signalized intersection traversal
- Unreachable path failure handling
- Tick-limited execution termination
"""

from apps.core.domain.enums import VehicleType
from apps.core.graph.generator import CityGridConfig
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import CostMode, RoutingAlgorithm
from apps.core.scenarios.models import (
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.signals.models import SignalCycleConfig


def create_single_vehicle_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 200,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a small deterministic synthetic grid scenario with a single vehicle."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_01",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.DISTANCE,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_acceleration_mps2=3.0),
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_single_veh",
            name="Single Vehicle Straight Run",
            description="Single vehicle navigating from (0,0) to (0,2) on a 3x3 grid.",
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        stop_on_all_arrived=True,
        seed=seed,
    )


def create_multi_vehicle_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 150,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a synthetic grid scenario with multiple vehicles using distinct routes."""
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_north",
        start_node_id="node_r0_c0",
        destination_node_id="node_r3_c0",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_east",
        start_node_id="node_r0_c1",
        destination_node_id="node_r0_c3",
        algorithm=RoutingAlgorithm.DIJKSTRA,
        cost_mode=CostMode.DISTANCE,
        initial_speed_mps=0.0,
    )
    v3 = VehicleScenarioDefinition(
        vehicle_id="veh_diagonal",
        start_node_id="node_r1_c0",
        destination_node_id="node_r2_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_multi_veh",
            name="Multi-Vehicle Grid Deployment",
            description="Three vehicles traversing a 4x4 grid along distinct routes.",
        ),
        road_network=rn,
        vehicles=(v1, v2, v3),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        stop_on_all_arrived=True,
        seed=seed,
    )


def create_signalized_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario with an explicitly configured traffic signal at a central intersection."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=60.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        signalized_intersections=None,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    sig_cfg = SignalCycleConfig(
        green_duration_s=10.0,
        yellow_duration_s=2.0,
        red_duration_s=10.0,
    )
    sig = TrafficSignalScenarioDefinition(
        signal_id="sig_center",
        node_id="node_r1_c1",
        config=sig_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_crossing_h",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        vehicle_type=VehicleType.STANDARD,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_signalized",
            name="Signalized Center Intersection",
            description="Vehicle traversing an intersection governed by a traffic signal.",
        ),
        road_network=rn,
        vehicles=(v1,),
        signals=(sig,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        stop_on_all_arrived=True,
        seed=seed,
    )


def create_unreachable_vehicle_scenario(
    allow_unreachable: bool = False,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario containing a vehicle with an impossible route."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Block both edges from node_r0_c0 to isolate it
    v_unreachable = VehicleScenarioDefinition(
        vehicle_id="veh_trapped",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        closed_edge_ids=("edge_r0_c0_to_r0_c1", "edge_r0_c0_to_r1_c0"),
    )
    v_reachable = VehicleScenarioDefinition(
        vehicle_id="veh_valid",
        start_node_id="node_r1_c1",
        destination_node_id="node_r1_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_unreachable",
            name="Unreachable Destination Scenario",
            description="Vehicle whose path is completely blocked by closed edges.",
        ),
        road_network=rn,
        vehicles=(v_unreachable, v_reachable),
        time_step_s=0.1,
        max_ticks=50,
        allow_unreachable_vehicles=allow_unreachable,
        seed=seed,
    )


def create_tick_limited_scenario(
    max_ticks: int = 5,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario with a short tick limit that terminates before arrival."""
    grid_cfg = CityGridConfig(
        rows=5,
        cols=5,
        spacing_m=100.0,
        speed_limit_mps=10.0,
        lanes=1,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_long_distance",
        start_node_id="node_r0_c0",
        destination_node_id="node_r4_c4",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.DISTANCE,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_tick_limited",
            name="Tick-Limited Incomplete Run",
            description="Scenario configured with a small tick limit that terminates early.",
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=0.1,
        max_ticks=max_ticks,
        stop_on_all_arrived=True,
        seed=seed,
    )
