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
from apps.core.graph.generator import CityGridConfig
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
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

