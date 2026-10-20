"""Unit tests for pure vehicle motion integration and kinematics configuration."""

import math

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.kinematics.exceptions import (
    InvalidKinematicsConfigError,
    InvalidMotionInputError,
)
from apps.core.kinematics.models import KinematicsConfig, MotionStepResult
from apps.core.kinematics.motion import (
    compute_heading,
    integrate_motion,
    interpolate_position,
    validate_motion_inputs,
)


class TestKinematicsConfig:
    """Test validation and serialization of KinematicsConfig."""

    def test_default_config_valid(self) -> None:
        cfg = KinematicsConfig()
        assert cfg.max_speed_mps == 13.89
        assert cfg.max_acceleration_mps2 == 3.0
        assert cfg.max_deceleration_mps2 == 5.0
        assert cfg.min_speed_mps == 0.0
        assert cfg.enforce_road_speed_limits is True
        assert cfg.position_tolerance_m == 1e-4

    def test_custom_valid_config(self) -> None:
        cfg = KinematicsConfig(
            max_speed_mps=25.0,
            max_acceleration_mps2=4.0,
            max_deceleration_mps2=6.0,
            min_speed_mps=1.0,
            enforce_road_speed_limits=False,
            position_tolerance_m=0.01,
        )
        assert cfg.max_speed_mps == 25.0
        data = cfg.to_dict()
        assert data["max_speed_mps"] == 25.0
        assert data["enforce_road_speed_limits"] is False

    @pytest.mark.parametrize(
        "invalid_kwargs, expected_param",
        [
            ({"max_speed_mps": -5.0}, "max_speed_mps"),
            ({"max_speed_mps": 0.0}, "max_speed_mps"),
            ({"max_speed_mps": float("nan")}, "max_speed_mps"),
            ({"max_speed_mps": float("inf")}, "max_speed_mps"),
            ({"max_acceleration_mps2": -2.0}, "max_acceleration_mps2"),
            ({"max_acceleration_mps2": 0.0}, "max_acceleration_mps2"),
            ({"max_deceleration_mps2": -4.0}, "max_deceleration_mps2"),
            ({"max_deceleration_mps2": 0.0}, "max_deceleration_mps2"),
            ({"min_speed_mps": -1.0}, "min_speed_mps"),
            ({"max_speed_mps": 10.0, "min_speed_mps": 15.0}, "max_speed_mps"),
            ({"position_tolerance_m": 0.0}, "position_tolerance_m"),
            ({"position_tolerance_m": -0.01}, "position_tolerance_m"),
        ],
    )
    def test_invalid_config_raises(self, invalid_kwargs: dict, expected_param: str) -> None:
        with pytest.raises(InvalidKinematicsConfigError) as exc_info:
            KinematicsConfig(**invalid_kwargs)
        assert exc_info.value.param == expected_param


class TestMotionIntegration:
    """Test pure numerical motion integration across acceleration, braking, and saturation."""

    @pytest.fixture
    def default_config(self) -> KinematicsConfig:
        return KinematicsConfig(
            max_speed_mps=20.0,
            max_acceleration_mps2=2.0,
            max_deceleration_mps2=4.0,
        )

    def test_stationary_vehicle_remains_stationary(self, default_config: KinematicsConfig) -> None:
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=0.0,
            target_accel=0.0,
            dt=1.0,
            config=default_config,
        )
        assert new_speed == 0.0
        assert applied_accel == 0.0
        assert dist == 0.0

    def test_constant_speed_motion(self, default_config: KinematicsConfig) -> None:
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=10.0,
            target_accel=0.0,
            dt=2.5,
            config=default_config,
        )
        assert math.isclose(new_speed, 10.0)
        assert applied_accel == 0.0
        assert math.isclose(dist, 25.0)  # 10 m/s * 2.5 s = 25 m

    def test_forward_acceleration_within_limits(self, default_config: KinematicsConfig) -> None:
        # v0 = 5.0, a = 2.0, dt = 3.0 => v = 5 + 2*3 = 11.0, d = 5*3 + 0.5*2*9 = 15 + 9 = 24.0
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=5.0,
            target_accel=2.0,
            dt=3.0,
            config=default_config,
        )
        assert math.isclose(new_speed, 11.0)
        assert math.isclose(applied_accel, 2.0)
        assert math.isclose(dist, 24.0)

    def test_forward_acceleration_saturates_at_max_speed(
        self, default_config: KinematicsConfig
    ) -> None:
        # v0 = 18.0, max_speed = 20.0, a = 2.0, dt = 2.0
        # Time to reach 20 is (20 - 18) / 2 = 1.0 s.
        # d_accel = 18 * 1 + 0.5 * 2 * 1^2 = 19 m.
        # d_cruise = 20 * (2 - 1) = 20 m.
        # Total d = 39 m.
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=18.0,
            target_accel=2.0,
            dt=2.0,
            config=default_config,
        )
        assert math.isclose(new_speed, 20.0)
        assert math.isclose(applied_accel, 2.0)
        assert math.isclose(dist, 39.0)

    def test_braking_deceleration_within_step(self, default_config: KinematicsConfig) -> None:
        # v0 = 12.0, a = -3.0, dt = 2.0
        # v = 12 - 3*2 = 6.0 m/s.
        # d = 12*2 - 0.5*3*4 = 24 - 6 = 18.0 m.
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=12.0,
            target_accel=-3.0,
            dt=2.0,
            config=default_config,
        )
        assert math.isclose(new_speed, 6.0)
        assert math.isclose(applied_accel, -3.0)
        assert math.isclose(dist, 18.0)

    def test_braking_stops_mid_step_without_reversing(
        self, default_config: KinematicsConfig
    ) -> None:
        # v0 = 8.0, a = -4.0 (max decel), dt = 3.0
        # Time to stop = 8 / 4 = 2.0 s < 3.0 s.
        # d = 8^2 / (2 * 4) = 8.0 m.
        # Vehicle must not move backward during the remaining 1.0 s.
        new_speed, applied_accel, dist = integrate_motion(
            current_speed=8.0,
            target_accel=-4.0,
            dt=3.0,
            config=default_config,
        )
        assert new_speed == 0.0
        assert math.isclose(applied_accel, -4.0)
        assert math.isclose(dist, 8.0)

    def test_acceleration_clamped_to_max_limits(self, default_config: KinematicsConfig) -> None:
        # Commanded a = 10.0 (above max 2.0)
        new_speed, applied_accel, _ = integrate_motion(
            current_speed=0.0,
            target_accel=10.0,
            dt=1.0,
            config=default_config,
        )
        assert math.isclose(applied_accel, 2.0)
        assert math.isclose(new_speed, 2.0)

        # Commanded braking = -20.0 (below -max_deceleration -4.0)
        new_speed_brake, applied_brake, _ = integrate_motion(
            current_speed=10.0,
            target_accel=-20.0,
            dt=1.0,
            config=default_config,
        )
        assert math.isclose(applied_brake, -4.0)
        assert math.isclose(new_speed_brake, 6.0)

    def test_road_speed_limit_enforced_when_lower_than_vehicle_max(
        self, default_config: KinematicsConfig
    ) -> None:
        # Road speed limit is 10 m/s (vehicle max is 20 m/s)
        # v0 = 9.0, a = 2.0, dt = 2.0. Cap is 10.0 m/s.
        # Time to 10 m/s = (10 - 9) / 2 = 0.5 s.
        # d_accel = 9*0.5 + 0.5*2*0.25 = 4.5 + 0.25 = 4.75 m.
        # d_cruise = 10 * 1.5 = 15.0 m.
        # Total d = 19.75 m.
        new_speed, _, dist = integrate_motion(
            current_speed=9.0,
            target_accel=2.0,
            dt=2.0,
            config=default_config,
            speed_limit=10.0,
        )
        assert math.isclose(new_speed, 10.0)
        assert math.isclose(dist, 19.75)

    def test_distance_limit_stops_at_destination_boundary(
        self, default_config: KinematicsConfig
    ) -> None:
        # Distance limit is 10.0 m, but motion would produce 25.0 m
        new_speed, _, dist = integrate_motion(
            current_speed=10.0,
            target_accel=0.0,
            dt=2.5,
            config=default_config,
            distance_limit=10.0,
        )
        assert math.isclose(dist, 10.0)
        assert new_speed == 0.0  # Arrived vehicle stops at destination


class TestMotionInputValidation:
    """Test validation of numeric bounds, finite checks, and NaN/Inf rejection."""

    @pytest.mark.parametrize(
        "invalid_dt",
        [0.0, -1.0, float("nan"), float("inf"), float("-inf"), "invalid"],
    )
    def test_invalid_dt_raises(self, invalid_dt: float) -> None:
        with pytest.raises(InvalidMotionInputError):
            validate_motion_inputs(dt=invalid_dt)

    @pytest.mark.parametrize(
        "invalid_accel",
        [float("nan"), float("inf"), float("-inf"), "accel"],
    )
    def test_invalid_accel_raises(self, invalid_accel: float) -> None:
        with pytest.raises(InvalidMotionInputError):
            validate_motion_inputs(dt=1.0, target_accel=invalid_accel)

    @pytest.mark.parametrize(
        "invalid_speed",
        [-0.01, -10.0, float("nan"), float("inf"), "speed"],
    )
    def test_invalid_speed_raises(self, invalid_speed: float) -> None:
        with pytest.raises(InvalidMotionInputError):
            validate_motion_inputs(dt=1.0, current_speed=invalid_speed)


class TestGeometricCalculations:
    """Test 2D heading calculation and segment position interpolation."""

    def test_compute_heading_cardinal_directions(self) -> None:
        origin = Position2D(x=0.0, y=0.0)
        # East (positive X) => 0 rad
        assert math.isclose(compute_heading(origin, Position2D(x=10.0, y=0.0)), 0.0)
        # North (positive Y) => pi/2 rad (~1.5708)
        assert math.isclose(compute_heading(origin, Position2D(x=0.0, y=10.0)), math.pi / 2.0)
        # West (negative X) => pi rad (~3.1416)
        assert math.isclose(compute_heading(origin, Position2D(x=-10.0, y=0.0)), math.pi)
        # South (negative Y) => 3*pi/2 rad (~4.7124)
        assert math.isclose(
            compute_heading(origin, Position2D(x=0.0, y=-10.0)), 3.0 * math.pi / 2.0
        )

    def test_compute_heading_preserves_current_heading_when_collocated(self) -> None:
        pos = Position2D(x=5.0, y=5.0)
        assert math.isclose(compute_heading(pos, pos, current_heading=1.234), 1.234)

    def test_interpolate_position_endpoints_and_midpoint(self) -> None:
        p1 = Position2D(x=0.0, y=0.0)
        p2 = Position2D(x=100.0, y=50.0)

        # fraction = 0.0 => p1
        mid0 = interpolate_position(p1, p2, 0.0)
        assert math.isclose(mid0.x, 0.0) and math.isclose(mid0.y, 0.0)

        # fraction = 0.5 => midpoint (50.0, 25.0)
        mid50 = interpolate_position(p1, p2, 0.5)
        assert math.isclose(mid50.x, 50.0) and math.isclose(mid50.y, 25.0)

        # fraction = 1.0 => p2
        mid100 = interpolate_position(p1, p2, 1.0)
        assert math.isclose(mid100.x, 100.0) and math.isclose(mid100.y, 50.0)

        # fraction > 1.0 clamped to p2
        mid_over = interpolate_position(p1, p2, 1.5)
        assert math.isclose(mid_over.x, 100.0) and math.isclose(mid_over.y, 50.0)


class TestMotionStepResult:
    """Test MotionStepResult serialization and field reporting."""

    def test_step_result_to_dict(self) -> None:
        result = MotionStepResult(
            previous_position=Position2D(x=0.0, y=0.0),
            new_position=Position2D(x=10.0, y=0.0),
            previous_speed_mps=5.0,
            new_speed_mps=10.0,
            applied_acceleration_mps2=2.5,
            distance_traveled_m=10.0,
            remaining_route_distance_m=90.0,
            current_edge_id="edge_1",
            current_node_id="node_a",
            state=VehicleState.EN_ROUTE,
            arrived=False,
            heading_rad=0.0,
            dt_s=1.0,
        )
        d = result.to_dict()
        assert d["previous_position"] == {"x": 0.0, "y": 0.0}
        assert d["new_position"] == {"x": 10.0, "y": 0.0}
        assert d["previous_speed_mps"] == 5.0
        assert d["new_speed_mps"] == 10.0
        assert d["applied_acceleration_mps2"] == 2.5
        assert d["distance_traveled_m"] == 10.0
        assert d["remaining_route_distance_m"] == 90.0
        assert d["current_edge_id"] == "edge_1"
        assert d["current_node_id"] == "node_a"
        assert d["state"] == "en_route"
        assert d["arrived"] is False
        assert d["heading_rad"] == 0.0
        assert d["dt_s"] == 1.0
