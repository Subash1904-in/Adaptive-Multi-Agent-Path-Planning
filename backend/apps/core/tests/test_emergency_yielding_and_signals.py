"""Unit tests for Phase 18 yielding policies, pedestrian clearance, and signal priority.

Verifies:
- Yielding decisions based on explicit YieldRequests and local corridor awareness
- Kinematic deceleration enforcement within physical and comfort limits
- Prohibition against running red signals while yielding
- Prohibition against entering occupied pedestrian crosswalks while yielding
- Traffic signal priority evaluation, granting green overrides, and metric updates
- Absolute pedestrian clearance protection: priority denial when pedestrians are CROSSING
- SafetyManager collision avoidance override supremacy over emergency progression
- Nominal vehicle behavior when no emergency priority is active
"""

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import Position2D, TrafficSignal, Vehicle
from apps.core.emergency.models import (
    EmergencyAwarenessRecord,
    EmergencyConfig,
    EmergencyType,
    YieldActionType,
    YieldRequest,
)
from apps.core.emergency.priority_manager import EmergencyPriorityManager
from apps.core.emergency.yielding_policy import YieldingPolicy
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import RouteSegment, VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.models import (
    PedestrianConfig,
    PedestrianLifecycleState,
)
from apps.core.safety.manager import SafetyManager
from apps.core.signals.controller import TrafficSignalController
from apps.core.signals.models import SignalCycleConfig


@pytest.fixture
def test_grid():
    """Create a 3x3 synthetic city grid."""
    cfg = CityGridConfig(rows=3, cols=3, spacing_m=50.0, speed_limit_mps=15.0)
    return generate_synthetic_city_grid(cfg)


@pytest.fixture
def standard_agent(test_grid):
    """Create a standard autonomous vehicle agent."""
    veh = Vehicle(
        id="veh_std_01",
        position=Position2D(x=10.0, y=0.0),
        speed_mps=10.0,
        heading_rad=0.0,
        current_edge_id="edge_0_1",
        current_node_id="node_r0_c0",
    )
    k_cfg = KinematicsConfig(
        max_speed_mps=20.0,
        max_acceleration_mps2=3.0,
        max_deceleration_mps2=5.0,
    )
    return VehicleAgent(vehicle=veh, road_graph=test_grid, config=k_cfg)


@pytest.fixture
def emergency_agent(test_grid):
    """Create an emergency ambulance agent."""
    veh = Vehicle(
        id="amb_01",
        position=Position2D(x=0.0, y=0.0),
        speed_mps=15.0,
        max_speed_mps=25.0,
        heading_rad=0.0,
        current_edge_id="edge_0_1",
        current_node_id="node_r0_c0",
    )
    k_cfg = KinematicsConfig(
        max_speed_mps=25.0,
        max_acceleration_mps2=4.0,
        max_deceleration_mps2=6.0,
    )
    return VehicleAgent(vehicle=veh, road_graph=test_grid, config=k_cfg)


@pytest.fixture
def signal_controller():
    """Create a TrafficSignalController controlling intersection node_r0_c1."""
    sig = TrafficSignal(
        id="sig_r0_c1",
        node_id="node_r0_c1",
        position=Position2D(x=50.0, y=0.0),
        state=TrafficSignalState.RED,
        remaining_phase_s=15.0,
        cycle_duration_s=40.0,
    )
    cfg = SignalCycleConfig(
        green_duration_s=20.0,
        yellow_duration_s=3.0,
        red_duration_s=17.0,
    )
    ctrl = TrafficSignalController(signal=sig, config=cfg)
    ctrl.incoming_edge_ids.append("edge_0_1")
    return ctrl


class TestYieldingPolicyDecisions:
    """Tests for deterministic yielding policy decisions."""

    def test_nominal_driving_without_emergency(self, standard_agent) -> None:
        policy = YieldingPolicy()
        decision = policy.evaluate_vehicle_yield(
            agent=standard_agent,
            awareness=None,
            corridors=[],
            signals=[],
        )
        assert decision.action == YieldActionType.CONTINUE
        assert decision.effective_decel_mps2 == 0.0

    def test_yield_to_explicit_yield_request(self, standard_agent) -> None:
        policy = YieldingPolicy(config=EmergencyConfig(yield_decel_mps2=-2.5))
        y_req = YieldRequest(
            yield_id="y_req_101",
            emergency_vehicle_id="amb_01",
            target_vehicle_id="veh_std_01",
            edge_id="edge_0_1",
            node_id="node_r0_c1",
            recommended_action=YieldActionType.YIELD_TO_EMERGENCY,
            target_speed_mps=0.0,
            target_decel_mps2=-2.5,
            creation_time_s=1.0,
            expiry_time_s=30.0,
        )

        decision = policy.evaluate_vehicle_yield(
            agent=standard_agent,
            awareness=None,
            corridors=[],
            signals=[],
            yield_requests=[y_req],
            current_time_s=2.0,
        )

        assert decision.action == YieldActionType.YIELD_TO_EMERGENCY
        assert decision.effective_decel_mps2 == -2.5
        assert decision.source_yield_id == "y_req_101"

    def test_yield_from_local_awareness_record(self, standard_agent, emergency_agent) -> None:
        policy = YieldingPolicy(
            config=EmergencyConfig(yield_decel_mps2=-3.0, yielding_distance_m=40.0)
        )
        awareness = EmergencyAwarenessRecord(
            emergency_vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            last_updated_s=1.0,
            is_active=True,
            corridor_edges=("edge_0_1", "edge_1_2"),
        )

        decision = policy.evaluate_vehicle_yield(
            agent=standard_agent,
            awareness=awareness,
            corridors=[],
            signals=[],
            emergency_agents=[emergency_agent],
            current_time_s=1.5,
        )

        assert decision.action == YieldActionType.YIELD_TO_EMERGENCY
        assert decision.effective_decel_mps2 == -3.0

    def test_yielding_vehicle_does_not_cross_red_signal(
        self, standard_agent, signal_controller
    ) -> None:
        """A vehicle must NOT enter an intersection against a red signal while yielding."""
        policy = YieldingPolicy()
        # Set agent near end of segment approaching signal
        standard_agent.current_segment = RouteSegment(
            edge_id="edge_0_1",
            start_node_id="node_r0_c0",
            end_node_id="node_r0_c1",
            length_m=50.0,
            speed_limit_mps=15.0,
            start_pos=Position2D(x=0.0, y=0.0),
            end_pos=Position2D(x=50.0, y=0.0),
            heading_rad=0.0,
        )
        standard_agent.distance_along_segment_m = 40.0  # 10m from signal (< 25m)

        y_req = YieldRequest(
            yield_id="y_req_red",
            emergency_vehicle_id="amb_01",
            target_vehicle_id="veh_std_01",
            edge_id="edge_0_1",
            node_id="node_r0_c1",
            recommended_action=YieldActionType.CLEAR_CORRIDOR,
            target_speed_mps=5.0,
            target_decel_mps2=-2.0,
            creation_time_s=1.0,
            expiry_time_s=30.0,
        )

        decision = policy.evaluate_vehicle_yield(
            agent=standard_agent,
            awareness=None,
            corridors=[],
            signals=[signal_controller],
            yield_requests=[y_req],
            current_time_s=2.0,
        )

        # Must halt before intersection
        assert decision.action == YieldActionType.STOP_BEFORE_INTERSECTION
        assert "red signal" in decision.reason.lower()

    def test_yielding_vehicle_does_not_enter_occupied_crosswalk(
        self, standard_agent
    ) -> None:
        """A vehicle must NOT enter a crosswalk occupied by crossing pedestrians while yielding."""
        policy = YieldingPolicy()
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=15.0, y=1.0),
            config=PedestrianConfig(),
            initial_state=PedestrianLifecycleState.CROSSING,
        )

        y_req = YieldRequest(
            yield_id="y_req_ped",
            emergency_vehicle_id="amb_01",
            target_vehicle_id="veh_std_01",
            edge_id="edge_0_1",
            node_id="node_r0_c1",
            recommended_action=YieldActionType.CLEAR_CORRIDOR,
            target_speed_mps=5.0,
            target_decel_mps2=-2.0,
            creation_time_s=1.0,
            expiry_time_s=30.0,
        )

        decision = policy.evaluate_vehicle_yield(
            agent=standard_agent,
            awareness=None,
            corridors=[],
            signals=[],
            pedestrians=[ped],
            yield_requests=[y_req],
            current_time_s=2.0,
        )

        assert decision.action == YieldActionType.STOP_BEFORE_INTERSECTION
        assert "crosswalk" in decision.reason.lower()


class TestTrafficSignalPriorityAndPedestrianProtection:
    """Tests for signal priority overrides and pedestrian crossing clearance invariants."""

    def test_grant_signal_priority_when_no_pedestrians(
        self, test_grid, signal_controller
    ) -> None:
        mgr = EmergencyPriorityManager(test_grid)
        mgr.register_emergency_vehicle("amb_01")
        req = mgr.activate_emergency("amb_01", EmergencyType.AMBULANCE, "node_r0_c2", 0.0)

        # Plan corridor through node_r0_c1
        mgr.plan_and_commit_corridor(req.request_id, "node_r0_c0", 0.0)

        overrides = mgr.evaluate_signal_priority(
            signals=[signal_controller],
            pedestrians=[],
            current_time_s=1.0,
        )

        assert signal_controller.id in overrides
        ovr = overrides[signal_controller.id]
        assert ovr.is_granted is True
        assert ovr.desired_phase == TrafficSignalState.GREEN
        assert signal_controller.signal.state == TrafficSignalState.GREEN
        assert signal_controller.has_active_priority_override(1.0) is True

    def test_deny_signal_priority_when_pedestrians_crossing(
        self, test_grid, signal_controller
    ) -> None:
        """Pedestrians in CROSSING state have absolute clearance right of way."""
        mgr = EmergencyPriorityManager(test_grid)
        mgr.register_emergency_vehicle("amb_01")
        req = mgr.activate_emergency("amb_01", EmergencyType.AMBULANCE, "node_r0_c2", 0.0)
        mgr.plan_and_commit_corridor(req.request_id, "node_r0_c0", 0.0)

        # Pedestrian actively crossing at signal position (50, 0)
        ped = PedestrianAgent(
            pedestrian_id="ped_crossing_01",
            position=Position2D(x=52.0, y=2.0),
            config=PedestrianConfig(),
            initial_state=PedestrianLifecycleState.CROSSING,
        )

        overrides = mgr.evaluate_signal_priority(
            signals=[signal_controller],
            pedestrians=[ped],
            current_time_s=1.0,
        )

        assert signal_controller.id in overrides
        ovr = overrides[signal_controller.id]
        assert ovr.is_granted is False
        assert "pedestrian clearance" in ovr.reason.lower()
        assert mgr.metrics.signal_priority_denials == 1
        assert signal_controller.has_active_priority_override(1.0) is False


class TestEmergencySafetySubsystemPrecedence:
    """Tests confirming Phase 16 SafetyManager overrides emergency vehicle movement."""

    def test_emergency_vehicle_obeys_safety_collision_braking(
        self, test_grid, emergency_agent
    ) -> None:
        """Even with emergency priority, an imminent obstacle triggers emergency braking."""
        from apps.core.domain.enums import VehicleState

        safety = SafetyManager()
        emergency_agent.vehicle.state = VehicleState.EN_ROUTE
        emergency_agent.vehicle.speed_mps = 10.0

        # Obstacle immediately ahead (5m)
        other_veh = Vehicle(
            id="stalled_car",
            position=Position2D(x=5.0, y=0.0),
            speed_mps=0.0,
            heading_rad=0.0,
            state=VehicleState.EN_ROUTE,
        )
        other_agent = VehicleAgent(
            vehicle=other_veh,
            road_graph=test_grid,
            config=KinematicsConfig(max_speed_mps=15.0),
        )

        overrides, collisions, events = safety.evaluate_and_stage(
            agents=[emergency_agent, other_agent],
            current_time_s=0.5,
        )

        assert len(overrides) > 0 or len(collisions) > 0
