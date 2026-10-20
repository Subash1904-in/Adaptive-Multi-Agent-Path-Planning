"""Pure kinematic motion integration and geometric calculations.

This module contains decoupled mathematical functions for:
- Bounded constant-acceleration kinematic integration.
- Planar heading and orientation calculation.
- 2D position interpolation along line segments.
- Strict input validation.

Zero external scientific dependencies; strictly pure Python.
"""

import math
from typing import Optional

from apps.core.domain.values import Position2D
from apps.core.kinematics.exceptions import InvalidMotionInputError
from apps.core.kinematics.models import KinematicsConfig


def validate_motion_inputs(
    dt: float,
    target_accel: Optional[float] = None,
    current_speed: Optional[float] = None,
) -> None:
    """Validate that simulation time step, acceleration, and speed are finite and physical.

    Raises:
        InvalidMotionInputError: If any parameter is non-numeric, non-finite,
                                 or violates physical bounds.
    """
    if not isinstance(dt, (int, float)) or not math.isfinite(dt):
        raise InvalidMotionInputError(
            f"Time step dt must be a finite numeric value, got {dt}.", field_name="dt"
        )
    if dt <= 0.0:
        raise InvalidMotionInputError(
            f"Time step dt must be strictly positive (> 0.0), got {dt}.", field_name="dt"
        )

    if target_accel is not None:
        if not isinstance(target_accel, (int, float)) or not math.isfinite(target_accel):
            raise InvalidMotionInputError(
                f"Acceleration command must be a finite numeric value, got {target_accel}.",
                field_name="target_accel",
            )

    if current_speed is not None:
        if not isinstance(current_speed, (int, float)) or not math.isfinite(current_speed):
            raise InvalidMotionInputError(
                f"Current speed must be a finite numeric value, got {current_speed}.",
                field_name="current_speed",
            )
        if current_speed < 0.0:
            raise InvalidMotionInputError(
                f"Current speed must be non-negative (>= 0.0), got {current_speed}.",
                field_name="current_speed",
            )


def compute_heading(
    from_pos: Position2D,
    to_pos: Position2D,
    current_heading: float = 0.0,
) -> float:
    """Compute the 2D directional heading angle in radians from from_pos to to_pos.

    Returns an angle normalized to [0.0, 2*pi).
    If distance between points is negligible (< 1e-7 m), preserves current_heading.
    """
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    dist = math.hypot(dx, dy)
    if dist < 1e-7:
        return float(current_heading % (2.0 * math.pi))
    return float(math.atan2(dy, dx) % (2.0 * math.pi))


def interpolate_position(
    start_pos: Position2D,
    end_pos: Position2D,
    fraction: float,
) -> Position2D:
    """Interpolate a 2D planar position along the straight line from start_pos to end_pos.

    Args:
        start_pos: Segment origin position.
        end_pos: Segment destination position.
        fraction: Normalized traversal fraction [0.0, 1.0]. Clamped to bounds.
    """
    clamped_fraction = max(0.0, min(1.0, float(fraction)))
    x = start_pos.x + clamped_fraction * (end_pos.x - start_pos.x)
    y = start_pos.y + clamped_fraction * (end_pos.y - start_pos.y)
    return Position2D(x=x, y=y)


def integrate_motion(
    current_speed: float,
    target_accel: float,
    dt: float,
    config: KinematicsConfig,
    speed_limit: Optional[float] = None,
    distance_limit: Optional[float] = None,
) -> tuple[float, float, float]:
    """Perform bounded constant-acceleration kinematic integration over time step dt.

    Equations of motion:
        v(t) = v_0 + a * t
        d(t) = v_0 * t + 0.5 * a * t^2

    Subject to physical constraints:
        - Deceleration limit: a >= -config.max_deceleration_mps2
        - Acceleration limit: a <= config.max_acceleration_mps2
        - Speed bounds: 0.0 <= v_next <= v_cap
        - Distance clamping: d <= distance_limit (if supplied)

    Args:
        current_speed: Longitudinal velocity at start of step (m/s).
        target_accel: Desired acceleration command (m/s^2).
        dt: Time step duration in seconds (> 0.0).
        config: Kinematics configuration and physical limits.
        speed_limit: Optional road edge speed limit (m/s).
        distance_limit: Optional remaining distance to target / endpoint (m).

    Returns:
        tuple of (new_speed_mps, applied_acceleration_mps2, distance_traveled_m)
    """
    validate_motion_inputs(dt, target_accel, current_speed)

    # Determine top speed cap for this step
    if speed_limit is not None and config.enforce_road_speed_limits and speed_limit > 0.0:
        v_cap = min(config.max_speed_mps, float(speed_limit))
    else:
        v_cap = config.max_speed_mps

    # Clamp commanded acceleration to vehicle physical limits
    a_applied = max(
        -config.max_deceleration_mps2,
        min(float(target_accel), config.max_acceleration_mps2),
    )

    v0 = float(current_speed)

    if abs(a_applied) < 1e-9:
        # Constant speed motion
        v_eff = min(v0, v_cap)
        d = v_eff * dt
        v_next = v_eff
    elif a_applied > 0.0:
        # Forward acceleration
        if v0 >= v_cap:
            v_next = v_cap
            d = v_cap * dt
        else:
            time_to_cap = (v_cap - v0) / a_applied
            if time_to_cap < dt:
                # Reached speed cap mid-step
                d_accel = v0 * time_to_cap + 0.5 * a_applied * (time_to_cap**2)
                d_cruise = v_cap * (dt - time_to_cap)
                d = d_accel + d_cruise
                v_next = v_cap
            else:
                # Accelerating throughout the entire step
                d = v0 * dt + 0.5 * a_applied * (dt**2)
                v_next = v0 + a_applied * dt
    else:
        # Braking / deceleration (a_applied < 0.0)
        if v0 <= 0.0:
            v_next = 0.0
            d = 0.0
        else:
            time_to_stop = v0 / abs(a_applied)
            if time_to_stop < dt:
                # Came to a complete stop mid-step; no reverse motion allowed
                d = 0.5 * v0 * time_to_stop
                v_next = 0.0
            else:
                # Decelerating throughout the step
                d = v0 * dt + 0.5 * a_applied * (dt**2)
                v_next = max(0.0, v0 + a_applied * dt)

    d = max(0.0, d)

    # Enforce remaining distance limit if provided (e.g., reaching final route destination)
    if distance_limit is not None:
        clamped_dist_limit = max(0.0, float(distance_limit))
        if d >= clamped_dist_limit:
            d = clamped_dist_limit
            v_next = 0.0  # Stop precisely at the destination boundary

    return v_next, a_applied, d
