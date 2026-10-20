"""Vehicle kinematics and agent lifecycle subsystem for AMAPP.

Provides:
- Validated KinematicsConfig and MotionStepResult models.
- Pure mathematical motion integration and geometric utilities.
- Individual VehicleAgent coordinator for deterministic route following.
- Typed kinematics exceptions.
"""

from apps.core.kinematics.exceptions import (
    InvalidKinematicsConfigError,
    InvalidLifecycleTransitionError,
    InvalidMotionInputError,
    InvalidRouteError,
    KinematicsError,
)
from apps.core.kinematics.models import KinematicsConfig, MotionStepResult
from apps.core.kinematics.motion import (
    compute_heading,
    integrate_motion,
    interpolate_position,
    validate_motion_inputs,
)
from apps.core.kinematics.vehicle_agent import RouteSegment, VehicleAgent

__all__ = [
    "InvalidKinematicsConfigError",
    "InvalidLifecycleTransitionError",
    "InvalidMotionInputError",
    "InvalidRouteError",
    "KinematicsConfig",
    "KinematicsError",
    "MotionStepResult",
    "RouteSegment",
    "VehicleAgent",
    "compute_heading",
    "interpolate_position",
    "integrate_motion",
    "validate_motion_inputs",
]
