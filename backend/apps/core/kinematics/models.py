"""Kinematics configuration and motion step result models.

Pure Python dataclasses for configuring physical vehicle limits and
reporting deterministic motion integration results.
"""

import math
from dataclasses import dataclass
from typing import Any, Optional

from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.kinematics.exceptions import InvalidKinematicsConfigError


@dataclass
class KinematicsConfig:
    """Validated configuration for vehicle motion and physical limits.

    Attributes:
        max_speed_mps: Maximum speed capability in m/s (> 0.0). Default ~50 km/h (13.89 m/s).
        max_acceleration_mps2: Maximum forward acceleration in m/s^2 (> 0.0).
        max_deceleration_mps2: Maximum braking deceleration in m/s^2 (> 0.0, positive magnitude).
        min_speed_mps: Minimum allowable speed in m/s (>= 0.0, defaults to 0.0).
        enforce_road_speed_limits: If True, caps top speed to min(max_speed_mps, edge speed limit).
        position_tolerance_m: Floating-point tolerance in meters for node arrival checks.
    """

    max_speed_mps: float = 13.89
    max_acceleration_mps2: float = 3.0
    max_deceleration_mps2: float = 5.0
    min_speed_mps: float = 0.0
    enforce_road_speed_limits: bool = True
    position_tolerance_m: float = 1e-4

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """Validate physical constraints and finite bounds."""
        for name, val in [
            ("max_speed_mps", self.max_speed_mps),
            ("max_acceleration_mps2", self.max_acceleration_mps2),
            ("max_deceleration_mps2", self.max_deceleration_mps2),
            ("min_speed_mps", self.min_speed_mps),
            ("position_tolerance_m", self.position_tolerance_m),
        ]:
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise InvalidKinematicsConfigError(
                    f"Parameter '{name}' must be a finite numeric value, got {val}.",
                    param=name,
                )

        if self.max_speed_mps <= 0.0:
            raise InvalidKinematicsConfigError(
                f"max_speed_mps must be strictly positive (> 0.0), got {self.max_speed_mps}.",
                param="max_speed_mps",
            )
        if self.max_acceleration_mps2 <= 0.0:
            raise InvalidKinematicsConfigError(
                f"max_acceleration_mps2 must be strictly positive (> 0.0), "
                f"got {self.max_acceleration_mps2}.",
                param="max_acceleration_mps2",
            )
        if self.max_deceleration_mps2 <= 0.0:
            raise InvalidKinematicsConfigError(
                f"max_deceleration_mps2 must be strictly positive (> 0.0), "
                f"got {self.max_deceleration_mps2}.",
                param="max_deceleration_mps2",
            )
        if self.min_speed_mps < 0.0:
            raise InvalidKinematicsConfigError(
                f"min_speed_mps must be non-negative (>= 0.0), got {self.min_speed_mps}.",
                param="min_speed_mps",
            )
        if self.max_speed_mps <= self.min_speed_mps:
            raise InvalidKinematicsConfigError(
                f"max_speed_mps ({self.max_speed_mps}) must be greater than "
                f"min_speed_mps ({self.min_speed_mps}).",
                param="max_speed_mps",
            )
        if self.position_tolerance_m <= 0.0:
            raise InvalidKinematicsConfigError(
                f"position_tolerance_m must be strictly positive (> 0.0), "
                f"got {self.position_tolerance_m}.",
                param="position_tolerance_m",
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration parameters to dictionary."""
        return {
            "max_speed_mps": self.max_speed_mps,
            "max_acceleration_mps2": self.max_acceleration_mps2,
            "max_deceleration_mps2": self.max_deceleration_mps2,
            "min_speed_mps": self.min_speed_mps,
            "enforce_road_speed_limits": self.enforce_road_speed_limits,
            "position_tolerance_m": self.position_tolerance_m,
        }


@dataclass(frozen=True)
class MotionStepResult:
    """Immutable result contract summarizing an individual vehicle simulation time step.

    Attributes:
        previous_position: Position at the beginning of the step.
        new_position: Updated position at the end of the step.
        previous_speed_mps: Speed at the beginning of the step in m/s.
        new_speed_mps: Updated speed at the end of the step in m/s.
        applied_acceleration_mps2: Constrained acceleration applied during the step in m/s^2.
        distance_traveled_m: Physical distance traversed during the step in meters.
        remaining_route_distance_m: Distance remaining to the destination in meters.
        current_edge_id: Active directed road edge identifier currently occupied, if any.
        current_node_id: Nearest or current road node identifier occupied, if any.
        state: Operational lifecycle state at the end of the step.
        arrived: True if the vehicle reached its final destination during or before this step.
        heading_rad: Vehicle orientation heading in radians [0.0, 2*pi).
        dt_s: Simulation time step duration in seconds.
    """

    previous_position: Position2D
    new_position: Position2D
    previous_speed_mps: float
    new_speed_mps: float
    applied_acceleration_mps2: float
    distance_traveled_m: float
    remaining_route_distance_m: float
    current_edge_id: Optional[str]
    current_node_id: Optional[str]
    state: VehicleState
    arrived: bool
    heading_rad: float
    dt_s: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize step diagnostics to a JSON-compatible dictionary."""
        return {
            "previous_position": self.previous_position.to_dict(),
            "new_position": self.new_position.to_dict(),
            "previous_speed_mps": round(self.previous_speed_mps, 4),
            "new_speed_mps": round(self.new_speed_mps, 4),
            "applied_acceleration_mps2": round(self.applied_acceleration_mps2, 4),
            "distance_traveled_m": round(self.distance_traveled_m, 4),
            "remaining_route_distance_m": round(self.remaining_route_distance_m, 4),
            "current_edge_id": self.current_edge_id,
            "current_node_id": self.current_node_id,
            "state": self.state.value,
            "arrived": self.arrived,
            "heading_rad": round(self.heading_rad, 4),
            "dt_s": round(self.dt_s, 4),
        }
