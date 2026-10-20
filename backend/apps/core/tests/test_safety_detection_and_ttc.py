"""Unit tests for safety detection, closing speed, safe separation, and TTC estimation."""

import math

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.detection import (
    CollisionDetector,
    classify_collision_risk,
    compute_closing_speed,
    compute_safe_separation_distance,
    estimate_time_to_collision,
)
from apps.core.safety.exceptions import GeometryValidationError
from apps.core.safety.models import CollisionRiskLevel, SafetyActionType, SafetyConfig


class TestClosingSpeedAndSeparationFormula:
    """Tests for closing speed and safe separation distance calculations."""

    def test_head_on_approaching_closing_speed(self):
        # Veh A at x=0 moving East (+10 m/s). Veh B at x=100 moving West (-10 m/s).
        pos_a = (0.0, 0.0)
        vel_a = (10.0, 0.0)
        pos_b = (100.0, 0.0)
        vel_b = (-10.0, 0.0)
        v_closing = compute_closing_speed(pos_a, vel_a, pos_b, vel_b)
        assert math.isclose(v_closing, 20.0, abs_tol=1e-5)

    def test_receding_vehicles_negative_closing_speed(self):
        # Veh A at x=0 moving West (-10 m/s). Veh B at x=100 moving East (+10 m/s).
        pos_a = (0.0, 0.0)
        vel_a = (-10.0, 0.0)
        pos_b = (100.0, 0.0)
        vel_b = (10.0, 0.0)
        v_closing = compute_closing_speed(pos_a, vel_a, pos_b, vel_b)
        assert math.isclose(v_closing, -20.0, abs_tol=1e-5)

    def test_parallel_same_speed_zero_closing_speed(self):
        # Both moving North at 15 m/s, side by side
        pos_a = (0.0, 0.0)
        vel_a = (0.0, 15.0)
        pos_b = (10.0, 0.0)
        vel_b = (0.0, 15.0)
        v_closing = compute_closing_speed(pos_a, vel_a, pos_b, vel_b)
        assert math.isclose(v_closing, 0.0, abs_tol=1e-5)

    def test_stationary_obstacle_closing_speed(self):
        # Veh A moving East at 12 m/s toward stationary Veh B
        pos_a = (0.0, 0.0)
        vel_a = (12.0, 0.0)
        pos_b = (60.0, 0.0)
        vel_b = (0.0, 0.0)
        v_closing = compute_closing_speed(pos_a, vel_a, pos_b, vel_b)
        assert math.isclose(v_closing, 12.0, abs_tol=1e-5)

    def test_safe_separation_distance_computation(self):
        config = SafetyConfig(
            min_separation_m=3.0,
            reaction_time_s=0.5,
            braking_accel_reference_mps2=4.0,
        )
        # v_a = 10 m/s, v_b = 0 m/s, closing = 10 m/s
        # d_safe = 3.0 + 10 * 0.5 + max(10^2 / 8, 0) = 3.0 + 5.0 + 12.5 = 20.5 m
        d_safe = compute_safe_separation_distance(10.0, 0.0, 10.0, config)
        assert math.isclose(d_safe, 20.5, abs_tol=1e-5)

    def test_safe_separation_non_closing(self):
        config = SafetyConfig(
            min_separation_m=3.0,
            reaction_time_s=0.5,
            braking_accel_reference_mps2=4.0,
        )
        # Non-closing (closing speed <= 0): v_rel_plus is clamped to 0.0
        # d_safe = 3.0 + 0.0 + max(100/8, 100/8) = 3.0 + 12.5 = 15.5 m
        d_safe = compute_safe_separation_distance(10.0, 10.0, -5.0, config)
        assert math.isclose(d_safe, 15.5, abs_tol=1e-5)


class TestTTCEstimationAndRiskClassification:
    """Tests for TTC estimation and tiered risk classification."""

    def test_ttc_for_closing_vehicles(self):
        # 30m distance, 15 m/s closing -> TTC = 2.0s
        ttc = estimate_time_to_collision(30.0, 15.0, is_overlap=False)
        assert ttc is not None
        assert math.isclose(ttc, 2.0, abs_tol=1e-5)

    def test_ttc_for_non_closing_returns_none(self):
        assert estimate_time_to_collision(30.0, 0.0, is_overlap=False) is None
        assert estimate_time_to_collision(30.0, -5.0, is_overlap=False) is None

    def test_ttc_for_overlapping_returns_zero(self):
        assert estimate_time_to_collision(0.0, 10.0, is_overlap=True) == 0.0

    def test_risk_classification_hierarchy(self):
        config = SafetyConfig(
            min_separation_m=3.0,
            ttc_imminent_s=1.5,
            ttc_high_risk_s=3.0,
            ttc_caution_s=5.0,
        )

        # 1. COLLISION: overlap True
        assert classify_collision_risk(True, 0.0, 0.0, 10.0, config) == CollisionRiskLevel.COLLISION

        # 2. IMMINENT: TTC <= 1.5s
        assert classify_collision_risk(False, 5.0, 1.2, 10.0, config) == CollisionRiskLevel.IMMINENT
        # or separation < 0.5 * min_separation (1.5m)
        assert classify_collision_risk(False, 1.0, 2.0, 10.0, config) == CollisionRiskLevel.IMMINENT

        # 3. HIGH_RISK: TTC <= 3.0s
        assert (
            classify_collision_risk(False, 5.0, 2.5, 10.0, config)
            == CollisionRiskLevel.HIGH_RISK
        )
        # or separation < 3.0m
        assert (
            classify_collision_risk(False, 2.5, 4.0, 10.0, config)
            == CollisionRiskLevel.HIGH_RISK
        )

        # 4. CAUTION: TTC <= 5.0s
        assert classify_collision_risk(False, 5.0, 4.5, 10.0, config) == CollisionRiskLevel.CAUTION
        # or separation < safe_separation (10.0m)
        assert classify_collision_risk(False, 7.0, None, 10.0, config) == CollisionRiskLevel.CAUTION

        # 5. SAFE: separation >= safe_separation and no TTC violation
        assert classify_collision_risk(False, 15.0, None, 10.0, config) == CollisionRiskLevel.SAFE
        assert classify_collision_risk(False, 15.0, 8.0, 10.0, config) == CollisionRiskLevel.SAFE


class TestCollisionDetector:
    """Tests for multi-vehicle Pairwise CollisionDetector."""

    def test_rejects_self_pairing(self):
        detector = CollisionDetector()
        veh = Vehicle(id="v1", position=Position2D(x=0.0, y=0.0))
        with pytest.raises(
            GeometryValidationError,
            match="Cannot evaluate collision for vehicle 'v1' with itself",
        ):
            detector.evaluate_pair(veh, veh)

    def test_rear_end_approach_evaluation(self):
        detector = CollisionDetector()
        # V1 at x=0 moving East at 10 m/s. V2 at x=20 moving East at 2 m/s.
        v1 = Vehicle(
            id="v1", position=Position2D(x=0.0, y=0.0), speed_mps=10.0,
            max_speed_mps=20.0, heading_rad=0.0,
        )
        v2 = Vehicle(
            id="v2", position=Position2D(x=20.0, y=0.0), speed_mps=2.0,
            max_speed_mps=20.0, heading_rad=0.0,
        )

        pair_res = detector.evaluate_pair(v1, v2)
        assert pair_res.vehicle_a_id == "v1"
        assert pair_res.vehicle_b_id == "v2"
        assert math.isclose(pair_res.closing_speed_mps, 8.0, abs_tol=1e-5)
        # Length of each vehicle is 4.5m. Distance between centers is 20m.
        # Boundary distance = 20 - 4.5 = 15.5m.
        assert math.isclose(pair_res.distance_m, 15.5, abs_tol=1e-5)
        # TTC = 15.5 / 8.0 = 1.9375s (HIGH_RISK because <= 3.0s and > 1.5s)
        assert pair_res.risk_level == CollisionRiskLevel.HIGH_RISK
        # V1 is closing in, so V1 receives STRONG_BRAKE
        assert pair_res.recommended_action_a == SafetyActionType.STRONG_BRAKE
        # V2 is opening gap (moving away at 2 m/s), so V2 does not brake
        assert pair_res.recommended_action_b == SafetyActionType.NONE

    def test_deterministic_pair_enumeration_ordering(self):
        from apps.core.domain.models import RoadEdge, RoadNode

        graph = RoadGraph("test_net")
        graph.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=0.0)))
        graph.add_edge(
            RoadEdge(
                id="e0", start_node_id="n0", end_node_id="n1",
                length_m=100.0, speed_limit_mps=13.89,
            )
        )

        detector = CollisionDetector()

        v_c = Vehicle(id="veh_c", position=Position2D(x=10.0, y=0.0), state=VehicleState.EN_ROUTE)
        v_a = Vehicle(id="veh_a", position=Position2D(x=20.0, y=0.0), state=VehicleState.EN_ROUTE)
        v_b = Vehicle(id="veh_b", position=Position2D(x=30.0, y=0.0), state=VehicleState.EN_ROUTE)
        v_arrived = Vehicle(
            id="veh_z", position=Position2D(x=90.0, y=0.0), state=VehicleState.ARRIVED
        )

        ag_c = VehicleAgent(v_c, graph)
        ag_a = VehicleAgent(v_a, graph)
        ag_b = VehicleAgent(v_b, graph)
        ag_arr = VehicleAgent(v_arrived, graph)

        # Pass in arbitrary unsorted order: [ag_c, ag_arr, ag_b, ag_a]
        conflicts = detector.detect_all_conflicts([ag_c, ag_arr, ag_b, ag_a])

        # veh_z arrived should be excluded!
        # Active are veh_a, veh_b, veh_c -> pairs: (veh_a, veh_b), (veh_a, veh_c), (veh_b, veh_c)
        assert len(conflicts) == 3
        pairs = [(c.vehicle_a_id, c.vehicle_b_id) for c in conflicts]
        assert pairs == [
            ("veh_a", "veh_b"),
            ("veh_a", "veh_c"),
            ("veh_b", "veh_c"),
        ]
