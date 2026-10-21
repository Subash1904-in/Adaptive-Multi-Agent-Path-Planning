"""Standard programmatic scenario definitions for AMAPP testing and demonstration.

Provides compact, offline, and deterministic scenario templates illustrating:
- Single-vehicle synthetic grid navigation
- Multi-vehicle simultaneous routing
- Signalized intersection traversal
- Unreachable path failure handling
- Tick-limited execution termination
"""

from apps.core.communication.models import CommunicationConfig
from apps.core.coordination.models import CoordinationConfig
from apps.core.domain.enums import VehicleType
from apps.core.emergency.models import EmergencyConfig, EmergencyType, ReservationConflictPolicy
from apps.core.graph.generator import CityGridConfig
from apps.core.kinematics.models import KinematicsConfig
from apps.core.pedestrians.models import PedestrianLifecycleState
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
from apps.core.safety.models import SafetyConfig
from apps.core.scenarios.models import (
    CrosswalkScenarioDefinition,
    EmergencyVehicleScenarioDefinition,
    PedestrianScenarioDefinition,
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


def create_congestion_sharing_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating peer-to-peer V2V congestion report sharing."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_leader",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.DISTANCE,
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_follower",
        start_node_id="node_r0_c1",
        destination_node_id="node_r2_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.DISTANCE,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_congestion_sharing",
            name="V2V Congestion Knowledge Sharing",
            description="Two vehicles in range sharing decentralized edge congestion observations.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(enabled=True, range_m=120.0),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_road_closure_sharing_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating decentralized road-closure and reopening reporting."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_observer",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c2",
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_approaching",
        start_node_id="node_r0_c1",
        destination_node_id="node_r2_c1",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_closure_sharing",
            name="V2V Road Closure Information Exchange",
            description="Vehicles exchange road closure reports without altering graph topology.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(enabled=True, range_m=150.0),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_hazard_dissemination_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating multi-hop roadway hazard dissemination."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=4,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_A", start_node_id="node_r0_c0", destination_node_id="node_r0_c3"
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_B", start_node_id="node_r0_c1", destination_node_id="node_r0_c3"
    )
    v3 = VehicleScenarioDefinition(
        vehicle_id="veh_C", start_node_id="node_r0_c2", destination_node_id="node_r0_c3"
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_hazard_dissemination",
            name="V2V Multi-Hop Hazard Alert Dissemination",
            description="Hazard alert propagated across multiple hops to alert distant vehicles.",
        ),
        road_network=rn,
        vehicles=(v1, v2, v3),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(enabled=True, range_m=100.0),
        coordination_config=CoordinationConfig(enabled=True, max_forwarding_hops=3),
        seed=seed,
    )


def create_latency_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    latency_s: float = 0.2,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating deterministic communication latency and delayed delivery."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_sender",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_receiver",
        start_node_id="node_r0_c1",
        destination_node_id="node_r2_c1",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_latency",
            name="V2V Latency and Delayed Delivery",
            description="Scenario demonstrating multi-tick packet transit queues under latency.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(
            enabled=True,
            range_m=150.0,
            min_latency_s=latency_s,
            max_latency_s=latency_s,
            latency_seed=seed,
        ),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_packet_loss_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    loss_rate: float = 0.3,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating deterministic packet loss and drop metrics."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_A", start_node_id="node_r0_c0", destination_node_id="node_r0_c2"
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_B", start_node_id="node_r0_c1", destination_node_id="node_r2_c1"
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_packet_loss",
            name="V2V Deterministic Packet Loss",
            description="Scenario demonstrating deterministic packet loss with seeded PRNG.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(
            enabled=True,
            range_m=150.0,
            packet_loss_rate=loss_rate,
            packet_loss_seed=seed,
        ),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_burst_loss_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating two-state Markov Gilbert-Elliott burst loss."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_1", start_node_id="node_r0_c0", destination_node_id="node_r0_c2"
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_2", start_node_id="node_r0_c1", destination_node_id="node_r2_c1"
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_burst_loss",
            name="V2V Burst Loss Channel Model",
            description="Scenario demonstrating Markov good/bad channel transitions.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(
            enabled=True,
            range_m=150.0,
            burst_loss_enabled=True,
            burst_loss_p_gb=0.1,
            burst_loss_p_bg=0.5,
            burst_loss_seed=seed,
        ),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_degraded_network_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario combining latency, probabilistic loss, and distance loss."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_alpha", start_node_id="node_r0_c0", destination_node_id="node_r0_c2"
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_beta", start_node_id="node_r0_c1", destination_node_id="node_r2_c1"
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_degraded_network",
            name="V2V Degraded Network Simulation",
            description="Combined latency, packet loss, and distance-dependent attenuation.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(
            enabled=True,
            range_m=150.0,
            min_latency_s=0.1,
            max_latency_s=0.3,
            latency_seed=seed,
            packet_loss_rate=0.15,
            packet_loss_seed=seed,
            distance_loss_enabled=True,
            distance_loss_exponent=2.0,
        ),
        coordination_config=CoordinationConfig(enabled=True),
        seed=seed,
    )


def create_adaptive_reroute_closure_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating rerouting around a reported road closure."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_reroute",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_closure",
            name="Adaptive Reroute Around Closure",
            description="Vehicle dynamically adapts route when a road closure belief is accepted.",
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            min_benefit_absolute=0.1,
            min_benefit_relative=0.01,
            cooldown_ticks=5,
        ),
        seed=seed,
    )


def create_adaptive_reroute_congestion_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating rerouting around a heavily congested corridor."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_congested",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_congestion",
            name="Adaptive Reroute for Congestion Avoidance",
            description=(
                "Vehicle reroutes to an alternative corridor due to local congestion beliefs."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            min_benefit_absolute=1.0,
            min_benefit_relative=0.05,
            cooldown_ticks=5,
        ),
        seed=seed,
    )


def create_adaptive_reroute_hazard_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating rerouting away from a reported hazard."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_hazard",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_hazard",
            name="Adaptive Reroute for Hazard Avoidance",
            description=(
                "Vehicle avoids an edge with an active hazard penalty exceeding threshold."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            min_benefit_absolute=1.0,
            default_hazard_penalty=50.0,
            cooldown_ticks=5,
        ),
        seed=seed,
    )


def create_adaptive_reroute_insufficient_benefit_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario where cost improvement does not meet benefit threshold."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_stable",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_insufficient_benefit",
            name="Adaptive Reroute Insufficient Benefit Suppression",
            description="Minor delay does not trigger route flapping due to benefit hysteresis.",
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            min_benefit_absolute=100.0,
            min_benefit_relative=0.5,
            cooldown_ticks=5,
        ),
        seed=seed,
    )


def create_adaptive_reroute_cooldown_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario demonstrating cooldown suppression following an accepted reroute."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_cooldown",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_cooldown",
            name="Adaptive Reroute Cooldown Suppression",
            description=(
                "Vehicle suppresses subsequent route recalculation during active cooldown period."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            cooldown_s=2.0,
            cooldown_ticks=20,
        ),
        seed=seed,
    )


def create_adaptive_reroute_stale_report_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario demonstrating expired/stale beliefs do not penalize routes."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_stale",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_stale",
            name="Adaptive Reroute Stale Belief Ignored",
            description=(
                "Expired closure or congestion beliefs are pruned and do not restrict edges."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
        ),
        seed=seed,
    )


def create_adaptive_reroute_no_alternative_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario where an isolated destination yields NO_ALTERNATIVE_ROUTE."""
    grid_cfg = CityGridConfig(
        rows=2,
        cols=2,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        bidirectional=False,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_blocked",
        start_node_id="node_r0_c0",
        destination_node_id="node_r1_c1",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_no_alternative",
            name="Adaptive Reroute No Alternative Path",
            description=(
                "Destination is unreachable under current closures yielding no-route outcome."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
        ),
        seed=seed,
    )


def create_adaptive_reroute_current_edge_continuation_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario verifying safe continuation of current edge on downstream closure."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_traversing",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_continuation",
            name="Adaptive Reroute Current Edge Continuation",
            description=(
                "Vehicle finishes active edge and splices candidate route from edge endpoint."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            current_edge_policy="finish_edge",
        ),
        seed=seed,
    )


def create_adaptive_reroute_delayed_network_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where network latency delays closure information until after it expires."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_source",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_target",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c2",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_adaptive_delayed_network",
            name="Adaptive Reroute Delayed Network Propagation",
            description="Closure message is delayed by channel latency exceeding belief TTL.",
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        v2v_config=CommunicationConfig(
            enabled=True,
            range_m=150.0,
            min_latency_s=0.5,
            max_latency_s=1.0,
            latency_seed=seed,
        ),
        coordination_config=CoordinationConfig(enabled=True),
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
        ),
        seed=seed,
    )


# -----------------------------------------------------------------------------
# Phase 16 — Collision Detection, Safe Separation, and Avoidance Scenarios
# -----------------------------------------------------------------------------


def create_head_on_collision_avoidance_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario with two vehicles moving toward each other on a bidirectional corridor.

    Both vehicles detect the closing conflict and apply braking to prevent collision.
    """
    grid_cfg = CityGridConfig(
        rows=2,
        cols=4,
        spacing_m=40.0,
        speed_limit_mps=10.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_eastbound",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c3",
        initial_speed_mps=6.0,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_deceleration_mps2=5.0),
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_westbound",
        start_node_id="node_r0_c3",
        destination_node_id="node_r0_c0",
        initial_speed_mps=6.0,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_deceleration_mps2=5.0),
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_safety_head_on",
            name="Head-On Collision Avoidance",
            description=(
                "Two vehicles approaching each other along a straight corridor apply braking."
            ),
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=4.0,
            reaction_time_s=0.3,
            ttc_imminent_s=1.5,
            ttc_high_risk_s=3.0,
            ttc_caution_s=5.0,
        ),
        seed=seed,
    )


def create_rear_end_following_safety_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario where a fast vehicle approaches a slower leading vehicle on the same route.

    The following vehicle detects the closing speed, safe separation violation, and applies braking.
    """
    grid_cfg = CityGridConfig(
        rows=2,
        cols=5,
        spacing_m=40.0,
        speed_limit_mps=15.0,
        bidirectional=False,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Slow leader starting at c1
    v_leader = VehicleScenarioDefinition(
        vehicle_id="veh_leader",
        start_node_id="node_r0_c1",
        destination_node_id="node_r0_c4",
        initial_speed_mps=3.0,
        kinematics=KinematicsConfig(max_speed_mps=4.0),
    )
    # Fast follower starting at c0
    v_follower = VehicleScenarioDefinition(
        vehicle_id="veh_follower",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c4",
        initial_speed_mps=12.0,
        kinematics=KinematicsConfig(max_speed_mps=15.0, max_deceleration_mps2=6.0),
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_safety_rear_end",
            name="Rear-End Headway Protection",
            description=(
                "Follower vehicle closes in on slower leader and brakes to avoid collision."
            ),
        ),
        road_network=rn,
        vehicles=(v_leader, v_follower),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=5.0,
            reaction_time_s=0.5,
        ),
        seed=seed,
    )


def create_intersection_conflict_safety_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario with two vehicles approaching a shared intersection perpendicularly."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Vehicle moving East through (1, 1): from (1, 0) to (1, 2)
    v_east = VehicleScenarioDefinition(
        vehicle_id="veh_crossing_east",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c2",
        initial_speed_mps=7.0,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_deceleration_mps2=5.0),
    )
    # Vehicle moving North through (1, 1): from (0, 1) to (2, 1)
    v_north = VehicleScenarioDefinition(
        vehicle_id="veh_crossing_north",
        start_node_id="node_r0_c1",
        destination_node_id="node_r2_c1",
        initial_speed_mps=7.0,
        kinematics=KinematicsConfig(max_speed_mps=10.0, max_deceleration_mps2=5.0),
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_safety_intersection",
            name="Intersection Crossing Conflict",
            description="Perpendicular crossing paths at intersection resolved via braking.",
        ),
        road_network=rn,
        vehicles=(v_east, v_north),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=4.0,
            ttc_imminent_s=1.5,
            ttc_high_risk_s=3.0,
        ),
        seed=seed,
    )


def create_unavoidable_collision_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario where vehicles close at extreme speed with limited braking,
    causing collision.
    """
    grid_cfg = CityGridConfig(
        rows=2,
        cols=3,
        spacing_m=15.0,
        speed_limit_mps=25.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Closing at 40 m/s relative speed with only 1.0 m/s^2 deceleration capability and 15m distance
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_fast_a",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        initial_speed_mps=20.0,
        kinematics=KinematicsConfig(max_speed_mps=25.0, max_deceleration_mps2=1.0),
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="veh_fast_b",
        start_node_id="node_r0_c1",
        destination_node_id="node_r0_c0",
        initial_speed_mps=20.0,
        kinematics=KinematicsConfig(max_speed_mps=25.0, max_deceleration_mps2=1.0),
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_safety_unavoidable_collision",
            name="Unavoidable Physical Collision",
            description=(
                "High relative velocity and low braking capability result in physical collision."
            ),
        ),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=3.0,
            gentle_decel_mps2=0.5,
            strong_decel_mps2=0.8,
            emergency_decel_mps2=1.0,
        ),
        seed=seed,
    )


def create_pedestrian_waiting_at_red_signal_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where a pedestrian approaches a crosswalk and waits for a WALK indication.

    The traffic signal for the conflicting vehicle approach is GREEN (so pedestrian indication is
    DONT_WALK). The pedestrian stops at the waiting area and remains in WAITING_TO_CROSS state.
    """
    grid_cfg = CityGridConfig(
        rows=2,
        cols=2,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    sig_def = TrafficSignalScenarioDefinition(
        signal_id="sig_node_r0_c1",
        node_id="node_r0_c1",
        config=SignalCycleConfig(green_duration_s=20.0, yellow_duration_s=3.0, red_duration_s=20.0),
        incoming_edge_ids=("edge_r0_c0_to_r0_c1",),
    )
    cw_def = CrosswalkScenarioDefinition(
        crosswalk_id="cw_1",
        entry_point=(48.0, -3.0),
        exit_point=(48.0, 3.0),
        width_m=4.0,
        associated_intersection_id="node_r0_c1",
        associated_road_segment_ids=("edge_r0_c0_to_r0_c1",),
        signal_controller_id="sig_node_r0_c1",
    )
    ped_def = PedestrianScenarioDefinition(
        pedestrian_id="ped_01",
        initial_position=(48.0, -5.0),
        destination_point=(48.0, 5.0),
        crosswalk_id="cw_1",
        walking_speed_mps=1.4,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_ped_waiting_red",
            name="Pedestrian Waiting at Red Signal",
            description="Pedestrian stops at crosswalk and waits for WALK indication.",
        ),
        road_network=rn,
        vehicles=(),
        signals=(sig_def,),
        crosswalks=(cw_def,),
        pedestrians=(ped_def,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_pedestrian_crossing_permitted_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where a pedestrian crosses a crosswalk under a WALK indication."""
    grid_cfg = CityGridConfig(
        rows=2,
        cols=2,
        spacing_m=50.0,
        speed_limit_mps=10.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Unsignalized crosswalk or signal granting WALK
    cw_def = CrosswalkScenarioDefinition(
        crosswalk_id="cw_walk",
        entry_point=(48.0, -2.0),
        exit_point=(48.0, 2.0),
        width_m=4.0,
        associated_intersection_id="node_r0_c1",
        associated_road_segment_ids=("edge_r0_c0_to_r0_c1",),
    )
    ped_def = PedestrianScenarioDefinition(
        pedestrian_id="ped_walker",
        initial_position=(48.0, -2.0),
        destination_point=(48.0, 3.0),
        crosswalk_id="cw_walk",
        walking_speed_mps=1.4,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_ped_crossing_walk",
            name="Pedestrian Crossing with Permission",
            description="Pedestrian crosses a crosswalk under a WALK indication and arrives.",
        ),
        road_network=rn,
        vehicles=(),
        crosswalks=(cw_def,),
        pedestrians=(ped_def,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_vehicle_braking_for_pedestrian_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where an approaching vehicle brakes to avoid a crossing pedestrian."""
    grid_cfg = CityGridConfig(
        rows=2,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    # Vehicle approaching along edge from node_r0_c0 (0, 0) to node_r0_c1 (50, 0)
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_approaching",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        initial_speed_mps=10.0,
        kinematics=KinematicsConfig(max_speed_mps=12.0, max_deceleration_mps2=5.0),
    )
    cw_def = CrosswalkScenarioDefinition(
        crosswalk_id="cw_yield",
        entry_point=(35.0, -3.0),
        exit_point=(35.0, 3.0),
        width_m=4.0,
        associated_road_segment_ids=("edge_r0_c0_to_r0_c1",),
    )
    ped_def = PedestrianScenarioDefinition(
        pedestrian_id="ped_crossing",
        initial_position=(35.0, -1.0),
        destination_point=(35.0, 4.0),
        crosswalk_id="cw_yield",
        walking_speed_mps=1.2,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_veh_braking_for_ped",
            name="Vehicle Braking for Pedestrian",
            description=(
                "Vehicle detects crossing pedestrian and engages collision avoidance braking."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        crosswalks=(cw_def,),
        pedestrians=(ped_def,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=3.0,
            gentle_decel_mps2=2.0,
            strong_decel_mps2=4.0,
            emergency_decel_mps2=6.0,
        ),
        seed=seed,
    )


def create_unavoidable_vehicle_pedestrian_collision_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 50,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where excessive vehicle speed results in an unavoidable collision
    with a pedestrian.
    """
    grid_cfg = CityGridConfig(
        rows=2,
        cols=2,
        spacing_m=50.0,
        speed_limit_mps=25.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="veh_fast",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c1",
        initial_speed_mps=20.0,
        kinematics=KinematicsConfig(max_speed_mps=25.0, max_deceleration_mps2=1.0),
    )
    cw_def = CrosswalkScenarioDefinition(
        crosswalk_id="cw_hazard",
        entry_point=(10.0, -2.0),
        exit_point=(10.0, 2.0),
        width_m=4.0,
        associated_road_segment_ids=("edge_r0_c0_to_r0_c1",),
    )
    ped_def = PedestrianScenarioDefinition(
        pedestrian_id="ped_in_path",
        initial_position=(10.0, 0.0),
        destination_point=(10.0, 3.0),
        crosswalk_id="cw_hazard",
        walking_speed_mps=0.5,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_unavoidable_ped_collision",
            name="Unavoidable Vehicle-Pedestrian Collision",
            description=(
                "Vehicle unable to stop in time, causing geometric overlap and COLLISION event."
            ),
        ),
        road_network=rn,
        vehicles=(v1,),
        crosswalks=(cw_def,),
        pedestrians=(ped_def,),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        safety_config=SafetyConfig(
            enabled=True,
            min_separation_m=3.0,
            gentle_decel_mps2=0.5,
            strong_decel_mps2=0.8,
            emergency_decel_mps2=1.0,
        ),
        seed=seed,
    )


def create_ambulance_corridor_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario with an ambulance requesting priority and generating a dynamic corridor."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=60.0,
        speed_limit_mps=15.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    amb_veh = VehicleScenarioDefinition(
        vehicle_id="amb_01",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=5.0,
        kinematics=KinematicsConfig(max_speed_mps=20.0, max_acceleration_mps2=4.0),
    )
    ev_def = EmergencyVehicleScenarioDefinition(
        vehicle_id="amb_01",
        emergency_type=EmergencyType.AMBULANCE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        priority_level=3,
        auto_activate=True,
        ttl_s=60.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_ambulance_corridor",
            name="Ambulance Priority Corridor",
            description=(
                "Ambulance activating emergency mode and establishing an "
                "authoritative priority corridor."
            ),
        ),
        road_network=rn,
        vehicles=(amb_veh,),
        emergency_vehicles=(ev_def,),
        emergency_config=EmergencyConfig(
            enabled=True,
            signal_priority_enabled=True,
        ),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_fire_engine_multi_intersection_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 150,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario with a fire engine traversing multiple signalized intersections."""
    grid_cfg = CityGridConfig(
        rows=4,
        cols=4,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    fe_veh = VehicleScenarioDefinition(
        vehicle_id="fire_01",
        start_node_id="node_r0_c0",
        destination_node_id="node_r3_c3",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
        kinematics=KinematicsConfig(max_speed_mps=15.0, max_acceleration_mps2=3.0),
    )
    sig1 = TrafficSignalScenarioDefinition(
        signal_id="sig_r1_c1",
        node_id="node_r1_c1",
        config=SignalCycleConfig(green_duration_s=20.0, yellow_duration_s=4.0, red_duration_s=20.0),
    )
    sig2 = TrafficSignalScenarioDefinition(
        signal_id="sig_r2_c2",
        node_id="node_r2_c2",
        config=SignalCycleConfig(green_duration_s=20.0, yellow_duration_s=4.0, red_duration_s=20.0),
    )
    ev_def = EmergencyVehicleScenarioDefinition(
        vehicle_id="fire_01",
        emergency_type=EmergencyType.FIRE_ENGINE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r3_c3",
        priority_level=2,
        auto_activate=True,
        ttl_s=120.0,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_fire_engine_multi_signal",
            name="Fire Engine Multi-Intersection Priority",
            description=(
                "Fire engine traversing multiple signalized intersections "
                "requesting signal priority."
            ),
        ),
        road_network=rn,
        vehicles=(fe_veh,),
        signals=(sig1, sig2),
        emergency_vehicles=(ev_def,),
        emergency_config=EmergencyConfig(
            enabled=True,
            signal_priority_enabled=True,
            signal_hold_green_duration_s=15.0,
        ),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_police_activation_cancellation_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 80,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario with a police vehicle activating and cancelling priority."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=50.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    pol_veh = VehicleScenarioDefinition(
        vehicle_id="pol_01",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        cost_mode=CostMode.TRAVEL_TIME,
        initial_speed_mps=0.0,
    )
    ev_def = EmergencyVehicleScenarioDefinition(
        vehicle_id="pol_01",
        emergency_type=EmergencyType.POLICE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        priority_level=1,
        auto_activate=False,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_police_activation_cancellation",
            name="Police Vehicle Activation and Cancellation",
            description="Police vehicle manual emergency priority activation and cancellation.",
        ),
        road_network=rn,
        vehicles=(pol_veh,),
        emergency_vehicles=(ev_def,),
        emergency_config=EmergencyConfig(enabled=True),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_competing_emergency_priority_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where an ambulance and police vehicle compete for corridor space."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=60.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v_amb = VehicleScenarioDefinition(
        vehicle_id="amb_high",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        initial_speed_mps=0.0,
    )
    v_pol = VehicleScenarioDefinition(
        vehicle_id="pol_low",
        start_node_id="node_r1_c0",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        initial_speed_mps=0.0,
    )
    ev_amb = EmergencyVehicleScenarioDefinition(
        vehicle_id="amb_high",
        emergency_type=EmergencyType.AMBULANCE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        priority_level=1,
        auto_activate=True,
    )
    ev_pol = EmergencyVehicleScenarioDefinition(
        vehicle_id="pol_low",
        emergency_type=EmergencyType.POLICE,
        start_node_id="node_r1_c0",
        destination_node_id="node_r0_c2",
        priority_level=3,
        auto_activate=True,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_competing_emergency",
            name="Competing Emergency Priority",
            description=(
                "Higher-priority ambulance resolves intersection conflict "
                "over lower-priority police vehicle."
            ),
        ),
        road_network=rn,
        vehicles=(v_amb, v_pol),
        emergency_vehicles=(ev_amb, ev_pol),
        emergency_config=EmergencyConfig(
            enabled=True,
            conflict_policy=ReservationConflictPolicy.STRICT_PRIORITY,
        ),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_vehicle_yielding_to_emergency_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 100,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create a scenario where a standard vehicle receives a yield request and decelerates."""
    grid_cfg = CityGridConfig(
        rows=3,
        cols=3,
        spacing_m=80.0,
        speed_limit_mps=15.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v_lead = VehicleScenarioDefinition(
        vehicle_id="veh_standard",
        start_node_id="node_r0_c1",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        initial_speed_mps=8.0,
        kinematics=KinematicsConfig(max_speed_mps=12.0, max_deceleration_mps2=4.0),
    )
    v_amb = VehicleScenarioDefinition(
        vehicle_id="amb_chase",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        algorithm=RoutingAlgorithm.ASTAR,
        initial_speed_mps=10.0,
        kinematics=KinematicsConfig(max_speed_mps=20.0, max_acceleration_mps2=4.0),
    )
    ev_amb = EmergencyVehicleScenarioDefinition(
        vehicle_id="amb_chase",
        emergency_type=EmergencyType.AMBULANCE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c2",
        priority_level=3,
        auto_activate=True,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_vehicle_yielding",
            name="Vehicle Yielding to Emergency Corridor",
            description="Standard vehicle yields and safely decelerates upon corridor awareness.",
        ),
        road_network=rn,
        vehicles=(v_lead, v_amb),
        emergency_vehicles=(ev_amb,),
        v2v_config=CommunicationConfig(enabled=True, range_m=200.0),
        emergency_config=EmergencyConfig(
            enabled=True,
            yielding_distance_m=100.0,
            yield_decel_mps2=3.0,
        ),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )


def create_pedestrian_crosswalk_signal_priority_denial_scenario(
    time_step_s: float = 0.1,
    max_ticks: int = 80,
    seed: int = 42,
) -> ScenarioDefinition:
    """Create scenario where emergency signal priority is denied due to crossing pedestrians."""
    grid_cfg = CityGridConfig(
        rows=2,
        cols=2,
        spacing_m=60.0,
        speed_limit_mps=12.0,
        bidirectional=True,
        seed=seed,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    amb_veh = VehicleScenarioDefinition(
        vehicle_id="amb_ped_test",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c1",
        algorithm=RoutingAlgorithm.ASTAR,
        initial_speed_mps=5.0,
    )
    sig_def = TrafficSignalScenarioDefinition(
        signal_id="sig_r0_c1",
        node_id="node_r0_c1",
        config=SignalCycleConfig(green_duration_s=20.0, yellow_duration_s=4.0, red_duration_s=20.0),
    )
    cw_def = CrosswalkScenarioDefinition(
        crosswalk_id="cw_sig_denial",
        entry_point=(58.0, -3.0),
        exit_point=(58.0, 3.0),
        width_m=4.0,
        associated_intersection_id="node_r0_c1",
    )
    ped_def = PedestrianScenarioDefinition(
        pedestrian_id="ped_crossing",
        initial_position=(58.0, -1.0),
        destination_point=(58.0, 3.0),
        crosswalk_id="cw_sig_denial",
        walking_speed_mps=1.0,
        metadata={"initial_state": PedestrianLifecycleState.CROSSING},
    )
    ev_def = EmergencyVehicleScenarioDefinition(
        vehicle_id="amb_ped_test",
        emergency_type=EmergencyType.AMBULANCE,
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c1",
        priority_level=3,
        auto_activate=True,
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(
            id="scn_pedestrian_priority_denial",
            name="Pedestrian Clearance Priority Denial",
            description=(
                "Signal priority is denied while pedestrian is in CROSSING "
                "state at intersection crosswalk."
            ),
        ),
        road_network=rn,
        vehicles=(amb_veh,),
        signals=(sig_def,),
        crosswalks=(cw_def,),
        pedestrians=(ped_def,),
        emergency_vehicles=(ev_def,),
        emergency_config=EmergencyConfig(
            enabled=True,
            signal_priority_enabled=True,
        ),
        time_step_s=time_step_s,
        max_ticks=max_ticks,
        seed=seed,
    )



