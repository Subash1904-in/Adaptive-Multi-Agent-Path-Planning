"""Safety package for collision detection, safe separation, and collision avoidance."""

from apps.core.safety.detection import (
    CollisionDetector,
    classify_collision_risk,
    compute_closing_speed,
    compute_safe_separation_distance,
    estimate_time_to_collision,
)
from apps.core.safety.exceptions import (
    ControlApplicationError,
    GeometryValidationError,
    InvalidSafetyConfigError,
    SafetyError,
)
from apps.core.safety.geometry import (
    OrientedBoundingBox2D,
    check_obb_overlap_sat,
    compute_obb_separation_distance,
    point_to_segment_distance,
)
from apps.core.safety.manager import SafetyManager
from apps.core.safety.metrics import SafetyMetrics
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    SafetyEvent,
    SafetyEventType,
    VehicleControlOverride,
    VehiclePairCollision,
)
from apps.core.safety.policy import SafetyPolicy

__all__ = [
    "CollisionDetector",
    "CollisionRiskLevel",
    "ControlApplicationError",
    "GeometryValidationError",
    "InvalidSafetyConfigError",
    "OrientedBoundingBox2D",
    "SafetyActionType",
    "SafetyConfig",
    "SafetyError",
    "SafetyEvent",
    "SafetyEventType",
    "SafetyManager",
    "SafetyMetrics",
    "SafetyPolicy",
    "VehicleControlOverride",
    "VehiclePairCollision",
    "check_obb_overlap_sat",
    "classify_collision_risk",
    "compute_closing_speed",
    "compute_obb_separation_distance",
    "compute_safe_separation_distance",
    "estimate_time_to_collision",
    "point_to_segment_distance",
]
