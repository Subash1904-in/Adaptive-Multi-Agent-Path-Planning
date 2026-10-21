"""Unit tests for safety policy, simultaneous conflict resolution, and metrics."""

import math

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import RoadEdge, RoadNode, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.manager import SafetyManager
from apps.core.safety.metrics import SafetyMetrics
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    VehicleControlOverride,
    VehiclePairCollision,
)
from apps.core.safety.policy import SafetyPolicy


def _make_agent(
    vid: str,
    x: float,
    y: float,
    heading_rad: float = 0.0,
    speed_mps: float = 10.0,
    max_decel_mps2: float = 6.0,
) -> VehicleAgent:
    graph = RoadGraph(f"net_{vid}")
    graph.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
    graph.add_node(RoadNode(id="n1", position=Position2D(x=200.0, y=0.0)))
    graph.add_edge(
        RoadEdge(
            id="e0",
            start_node_id="n0",
            end_node_id="n1",
            length_m=200.0,
            speed_limit_mps=20.0,
        )
    )

    veh = Vehicle(
        id=vid,
        position=Position2D(x=x, y=y),
        speed_mps=speed_mps,
        max_speed_mps=25.0,
        heading_rad=heading_rad,
        state=VehicleState.EN_ROUTE,
    )
    kin_cfg = KinematicsConfig(max_deceleration_mps2=max_decel_mps2)
    return VehicleAgent(veh, graph, config=kin_cfg)


class TestSafetyPolicyDecisions:
    """Tests for mapping detected risks to deceleration commands."""

    def test_safe_separation_produces_no_overrides(self):
        config = SafetyConfig()
        policy = SafetyPolicy(config)
        ag1 = _make_agent("v1", 0.0, 0.0)
        ag2 = _make_agent("v2", 50.0, 0.0)

        pair = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v2",
            distance_m=45.5,
            ttc_s=None,
            closing_speed_mps=0.0,
            risk_level=CollisionRiskLevel.SAFE,
            is_overlap=False,
            safe_separation_m=15.0,
            separation_violated=False,
            recommended_action_a=SafetyActionType.NONE,
            recommended_action_b=SafetyActionType.NONE,
            action_a_decel=0.0,
            action_b_decel=0.0,
        )

        overrides = policy.resolve_conflicts([ag1, ag2], [pair])
        assert overrides == {}

    def test_gentle_deceleration_for_caution(self):
        config = SafetyConfig(gentle_decel_mps2=2.0)
        policy = SafetyPolicy(config)
        ag1 = _make_agent("v1", 0.0, 0.0)
        ag2 = _make_agent("v2", 20.0, 0.0)

        pair = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v2",
            distance_m=15.5,
            ttc_s=4.0,
            closing_speed_mps=4.0,
            risk_level=CollisionRiskLevel.CAUTION,
            is_overlap=False,
            safe_separation_m=20.0,
            separation_violated=True,
            recommended_action_a=SafetyActionType.GENTLE_BRAKE,
            recommended_action_b=SafetyActionType.NONE,
            action_a_decel=2.0,
            action_b_decel=0.0,
        )

        overrides = policy.resolve_conflicts([ag1, ag2], [pair])
        assert "v1" in overrides
        assert "v2" not in overrides
        assert overrides["v1"].action_type == SafetyActionType.GENTLE_BRAKE
        assert math.isclose(overrides["v1"].target_acceleration_mps2, -2.0)

    def test_clamping_to_vehicle_max_deceleration(self):
        # Vehicle max deceleration capability is 5.0 m/s^2, but emergency braking demands 7.0 m/s^2
        config = SafetyConfig(emergency_decel_mps2=7.0)
        policy = SafetyPolicy(config)
        ag1 = _make_agent("v1", 0.0, 0.0, max_decel_mps2=5.0)
        ag2 = _make_agent("v2", 10.0, 0.0, max_decel_mps2=5.0)

        pair = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v2",
            distance_m=5.5,
            ttc_s=0.8,
            closing_speed_mps=7.0,
            risk_level=CollisionRiskLevel.IMMINENT,
            is_overlap=False,
            safe_separation_m=25.0,
            separation_violated=True,
            recommended_action_a=SafetyActionType.EMERGENCY_BRAKE,
            recommended_action_b=SafetyActionType.NONE,
            action_a_decel=7.0,
            action_b_decel=0.0,
        )

        overrides = policy.resolve_conflicts([ag1, ag2], [pair])
        assert overrides["v1"].action_type == SafetyActionType.EMERGENCY_BRAKE
        # Clamped to vehicle's physical limit -5.0 m/s^2
        assert math.isclose(overrides["v1"].target_acceleration_mps2, -5.0)


class TestSimultaneousConflictResolution:
    """Tests for resolving multiple concurrent conflicts deterministically."""

    def test_conservative_strongest_braking_wins(self):
        config = SafetyConfig(
            gentle_decel_mps2=2.0,
            strong_decel_mps2=4.5,
            emergency_decel_mps2=7.0,
        )
        policy = SafetyPolicy(config)

        # Vehicle V1 faces V2 (CAUTION, gentle decel 2.0) and V3 (IMMINENT, emergency decel 7.0)
        ag1 = _make_agent("v1", 10.0, 10.0, max_decel_mps2=8.0)
        ag2 = _make_agent("v2", 30.0, 10.0)
        ag3 = _make_agent("v3", 10.0, 15.0)

        pair_1_2 = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v2",
            distance_m=15.0,
            ttc_s=4.5,
            closing_speed_mps=3.0,
            risk_level=CollisionRiskLevel.CAUTION,
            is_overlap=False,
            safe_separation_m=20.0,
            separation_violated=True,
            recommended_action_a=SafetyActionType.GENTLE_BRAKE,
            recommended_action_b=SafetyActionType.NONE,
            action_a_decel=2.0,
            action_b_decel=0.0,
        )

        pair_1_3 = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v3",
            distance_m=4.0,
            ttc_s=0.9,
            closing_speed_mps=6.0,
            risk_level=CollisionRiskLevel.IMMINENT,
            is_overlap=False,
            safe_separation_m=22.0,
            separation_violated=True,
            recommended_action_a=SafetyActionType.EMERGENCY_BRAKE,
            recommended_action_b=SafetyActionType.EMERGENCY_BRAKE,
            action_a_decel=7.0,
            action_b_decel=7.0,
        )

        # Pass in order (1_2 then 1_3)
        overrides_order1 = policy.resolve_conflicts([ag1, ag2, ag3], [pair_1_2, pair_1_3])
        # Pass in reverse order (1_3 then 1_2)
        overrides_order2 = policy.resolve_conflicts([ag1, ag2, ag3], [pair_1_3, pair_1_2])

        assert overrides_order1["v1"].action_type == SafetyActionType.EMERGENCY_BRAKE
        assert math.isclose(overrides_order1["v1"].target_acceleration_mps2, -7.0)
        assert set(overrides_order1["v1"].triggering_pair_ids) == {"v2", "v3"}

        # Independence of input ordering
        assert overrides_order1["v1"].action_type == overrides_order2["v1"].action_type
        assert (
            overrides_order1["v1"].target_acceleration_mps2
            == overrides_order2["v1"].target_acceleration_mps2
        )


class TestSafetyMetricsAndRollback:
    """Tests for SafetyMetrics counters and atomic rollback serialization."""

    def test_metrics_recording_and_snapshot_restore(self):
        metrics = SafetyMetrics()
        metrics.record_pair_observation(
            separation_m=2.5,
            ttc_s=1.2,
            is_overlap=False,
            is_near_miss=True,
            is_separation_violated=True,
            is_ttc_violated=True,
            is_potential_collision=True,
        )
        metrics.record_override_action("emergency_brake")

        assert metrics.pair_checks == 1
        assert metrics.near_misses == 1
        assert metrics.emergency_brakes == 1
        assert metrics.min_separation_observed == 2.5
        assert metrics.min_ttc_observed == 1.2

        snapshot = metrics.capture_state()

        # Mutate further
        metrics.record_pair_observation(
            separation_m=0.0,
            ttc_s=0.0,
            is_overlap=True,
            is_near_miss=False,
            is_separation_violated=True,
            is_ttc_violated=True,
            is_potential_collision=False,
        )
        assert metrics.actual_collisions == 1
        assert metrics.pair_checks == 2

        # Rollback
        metrics.restore_state(snapshot)
        assert metrics.pair_checks == 1
        assert metrics.actual_collisions == 0
        assert metrics.near_misses == 1
        assert metrics.emergency_brakes == 1
        assert metrics.min_separation_observed == 2.5
        assert metrics.min_ttc_observed == 1.2


class TestSafetyModelsAndConfigs:
    """Tests for SafetyConfig validation invariants, serialization, and exceptions."""

    def test_config_non_numeric_and_non_finite_rejection(self):
        from apps.core.safety.exceptions import (
            InvalidSafetyConfigError,
        )

        with pytest.raises(InvalidSafetyConfigError, match="must be numeric"):
            SafetyConfig(min_separation_m="invalid")

        with pytest.raises(InvalidSafetyConfigError, match="must be finite"):
            SafetyConfig(reaction_time_s=float("nan"))

    def test_config_bound_invariants(self):
        from apps.core.safety.exceptions import InvalidSafetyConfigError

        with pytest.raises(
            InvalidSafetyConfigError, match="min_separation_m must be strictly positive"
        ):
            SafetyConfig(min_separation_m=0.0)

        with pytest.raises(InvalidSafetyConfigError, match="reaction_time_s must be non-negative"):
            SafetyConfig(reaction_time_s=-0.1)

        with pytest.raises(InvalidSafetyConfigError, match="must be strictly positive"):
            SafetyConfig(braking_accel_reference_mps2=0.0)

        with pytest.raises(InvalidSafetyConfigError, match="Deceleration bounds must satisfy"):
            SafetyConfig(gentle_decel_mps2=5.0, strong_decel_mps2=3.0)

        with pytest.raises(
            InvalidSafetyConfigError, match="ttc_imminent_s must be strictly positive"
        ):
            SafetyConfig(ttc_imminent_s=0.0)

        with pytest.raises(InvalidSafetyConfigError, match="TTC thresholds must strictly satisfy"):
            SafetyConfig(ttc_imminent_s=2.0, ttc_high_risk_s=1.5, ttc_caution_s=3.0)

        with pytest.raises(
            InvalidSafetyConfigError, match="near_miss_distance_m must be non-negative"
        ):
            SafetyConfig(near_miss_distance_m=-1.0)

    def test_config_serialization(self):
        cfg = SafetyConfig()
        d = cfg.to_dict()
        assert d["enabled"] is True
        assert d["min_separation_m"] == 3.0
        assert d["touching_is_overlap"] is True

    def test_model_to_dict_and_exceptions(self):
        from apps.core.safety.exceptions import ControlApplicationError
        from apps.core.safety.models import SafetyEvent, SafetyEventType

        override = VehicleControlOverride(
            vehicle_id="v1",
            action_type=SafetyActionType.STRONG_BRAKE,
            target_acceleration_mps2=-4.5,
            reason="test reason",
            risk_level=CollisionRiskLevel.HIGH_RISK,
        )
        assert override.to_dict()["action_type"] == "strong_brake"

        pair = VehiclePairCollision(
            vehicle_a_id="v1",
            vehicle_b_id="v2",
            distance_m=10.0,
            ttc_s=2.0,
            closing_speed_mps=5.0,
            risk_level=CollisionRiskLevel.HIGH_RISK,
            is_overlap=False,
            safe_separation_m=15.0,
            separation_violated=True,
            recommended_action_a=SafetyActionType.STRONG_BRAKE,
            recommended_action_b=SafetyActionType.NONE,
            action_a_decel=4.5,
            action_b_decel=0.0,
        )
        assert pair.to_dict()["risk_level"] == "high_risk"

        evt = SafetyEvent(
            event_id="e1",
            sim_time_s=1.5,
            vehicle_ids=("v1", "v2"),
            event_type=SafetyEventType.NEAR_MISS,
            risk_category=CollisionRiskLevel.IMMINENT,
            measured_separation_m=2.0,
            estimated_ttc_s=1.0,
            action_taken_a=SafetyActionType.EMERGENCY_BRAKE,
            action_taken_b=SafetyActionType.EMERGENCY_BRAKE,
            is_overlap=False,
        )
        assert evt.to_dict()["event_type"] == "near_miss"

        err = ControlApplicationError("Failed override", vehicle_id="v1", target_accel=-5.0)
        assert err.vehicle_id == "v1"

        mgr = SafetyManager(config=SafetyConfig(enabled=False))
        assert mgr.evaluate_and_stage([], 0.0) == ({}, [], [])
