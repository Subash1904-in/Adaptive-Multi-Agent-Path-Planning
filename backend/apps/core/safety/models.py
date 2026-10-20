"""Data models, enums, configurations, and event contracts for the safety subsystem."""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from apps.core.safety.exceptions import InvalidSafetyConfigError


class CollisionRiskLevel(str, Enum):
    """Safety risk classification categories for vehicle-to-vehicle interactions.

    Ordered strictly from lowest to highest threat:
    SAFE < CAUTION < HIGH_RISK < IMMINENT < COLLISION
    """

    SAFE = "safe"
    CAUTION = "caution"
    HIGH_RISK = "high_risk"
    IMMINENT = "imminent"
    COLLISION = "collision"


class SafetyActionType(str, Enum):
    """Categorical control action selected by the collision avoidance safety policy."""

    NONE = "none"
    GENTLE_BRAKE = "gentle_brake"
    STRONG_BRAKE = "strong_brake"
    EMERGENCY_BRAKE = "emergency_brake"


class SafetyEventType(str, Enum):
    """Classification of recorded discrete safety events."""

    COLLISION = "collision"
    NEAR_MISS = "near_miss"


@dataclass(frozen=True)
class SafetyConfig:
    """Configuration parameters governing collision detection, TTC, and avoidance policy.

    Attributes:
        enabled: Master toggle for safety detection and control overrides.
        min_separation_m: Baseline geometric clearance buffer d_0 in meters (> 0.0).
        reaction_time_s: Modeled perception and actuation lag T_r in seconds (>= 0.0).
        braking_accel_reference_mps2: Reference deceleration magnitude a_brake in m/s^2 (> 0.0)
            used in safe stopping distance formula d_brake = v^2 / (2 * a_brake).
        gentle_decel_mps2: Deceleration magnitude for CAUTION risk in m/s^2 (> 0.0).
        strong_decel_mps2: Deceleration magnitude for HIGH_RISK in m/s^2 (> 0.0).
        emergency_decel_mps2: Deceleration magnitude for IMMINENT / COLLISION in m/s^2 (> 0.0).
        ttc_imminent_s: Time-to-collision threshold for IMMINENT risk in seconds (> 0.0).
        ttc_high_risk_s: Time-to-collision threshold for HIGH_RISK in seconds (> 0.0).
        ttc_caution_s: Time-to-collision threshold for CAUTION risk in seconds (> 0.0).
        near_miss_distance_m: Maximum separation distance to trigger near-miss logging in meters.
        touching_is_overlap: Whether boundary touching is treated as geometric collision overlap.
        log_events: Whether to buffer structured SafetyEvent objects.
    """

    enabled: bool = True
    min_separation_m: float = 3.0
    reaction_time_s: float = 0.5
    braking_accel_reference_mps2: float = 4.0
    gentle_decel_mps2: float = 2.0
    strong_decel_mps2: float = 4.5
    emergency_decel_mps2: float = 7.0
    ttc_imminent_s: float = 1.5
    ttc_high_risk_s: float = 3.0
    ttc_caution_s: float = 5.0
    near_miss_distance_m: float = 4.0
    touching_is_overlap: bool = True
    log_events: bool = True

    def __post_init__(self) -> None:
        """Validate numeric bounds and monotonic ordering invariants."""
        numeric_fields = [
            ("min_separation_m", self.min_separation_m),
            ("reaction_time_s", self.reaction_time_s),
            ("braking_accel_reference_mps2", self.braking_accel_reference_mps2),
            ("gentle_decel_mps2", self.gentle_decel_mps2),
            ("strong_decel_mps2", self.strong_decel_mps2),
            ("emergency_decel_mps2", self.emergency_decel_mps2),
            ("ttc_imminent_s", self.ttc_imminent_s),
            ("ttc_high_risk_s", self.ttc_high_risk_s),
            ("ttc_caution_s", self.ttc_caution_s),
            ("near_miss_distance_m", self.near_miss_distance_m),
        ]
        for name, val in numeric_fields:
            if not isinstance(val, (int, float)):
                raise InvalidSafetyConfigError(
                    f"Parameter '{name}' must be numeric, got {type(val).__name__}.",
                    param_name=name,
                    param_value=val,
                )
            if not math.isfinite(val):
                raise InvalidSafetyConfigError(
                    f"Parameter '{name}' must be finite, got {val}.",
                    param_name=name,
                    param_value=val,
                )

        if self.min_separation_m <= 0.0:
            raise InvalidSafetyConfigError(
                f"min_separation_m must be strictly positive, got {self.min_separation_m}.",
                param_name="min_separation_m",
                param_value=self.min_separation_m,
            )
        if self.reaction_time_s < 0.0:
            raise InvalidSafetyConfigError(
                f"reaction_time_s must be non-negative, got {self.reaction_time_s}.",
                param_name="reaction_time_s",
                param_value=self.reaction_time_s,
            )
        for decel_name, decel_val in [
            ("braking_accel_reference_mps2", self.braking_accel_reference_mps2),
            ("gentle_decel_mps2", self.gentle_decel_mps2),
            ("strong_decel_mps2", self.strong_decel_mps2),
            ("emergency_decel_mps2", self.emergency_decel_mps2),
        ]:
            if decel_val <= 0.0:
                raise InvalidSafetyConfigError(
                    f"{decel_name} must be strictly positive, got {decel_val}.",
                    param_name=decel_name,
                    param_value=decel_val,
                )

        if not (self.gentle_decel_mps2 <= self.strong_decel_mps2 <= self.emergency_decel_mps2):
            raise InvalidSafetyConfigError(
                "Deceleration bounds must satisfy gentle <= strong <= emergency. Got "
                f"gentle={self.gentle_decel_mps2}, strong={self.strong_decel_mps2}, "
                f"emergency={self.emergency_decel_mps2}.",
                param_name="gentle_decel_mps2",
                param_value=(
                    self.gentle_decel_mps2,
                    self.strong_decel_mps2,
                    self.emergency_decel_mps2,
                ),
            )

        if self.ttc_imminent_s <= 0.0:
            raise InvalidSafetyConfigError(
                f"ttc_imminent_s must be strictly positive, got {self.ttc_imminent_s}.",
                param_name="ttc_imminent_s",
                param_value=self.ttc_imminent_s,
            )
        if not (self.ttc_imminent_s < self.ttc_high_risk_s < self.ttc_caution_s):
            raise InvalidSafetyConfigError(
                "TTC thresholds must strictly satisfy 0 < imminent < high_risk < caution. Got "
                f"imminent={self.ttc_imminent_s}, high_risk={self.ttc_high_risk_s}, "
                f"caution={self.ttc_caution_s}.",
                param_name="ttc_imminent_s",
                param_value=(self.ttc_imminent_s, self.ttc_high_risk_s, self.ttc_caution_s),
            )

        if self.near_miss_distance_m < 0.0:
            raise InvalidSafetyConfigError(
                f"near_miss_distance_m must be non-negative, got {self.near_miss_distance_m}.",
                param_name="near_miss_distance_m",
                param_value=self.near_miss_distance_m,
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration parameters to a plain JSON-compatible dictionary."""
        return {
            "enabled": self.enabled,
            "min_separation_m": self.min_separation_m,
            "reaction_time_s": self.reaction_time_s,
            "braking_accel_reference_mps2": self.braking_accel_reference_mps2,
            "gentle_decel_mps2": self.gentle_decel_mps2,
            "strong_decel_mps2": self.strong_decel_mps2,
            "emergency_decel_mps2": self.emergency_decel_mps2,
            "ttc_imminent_s": self.ttc_imminent_s,
            "ttc_high_risk_s": self.ttc_high_risk_s,
            "ttc_caution_s": self.ttc_caution_s,
            "near_miss_distance_m": self.near_miss_distance_m,
            "touching_is_overlap": self.touching_is_overlap,
            "log_events": self.log_events,
        }


@dataclass(frozen=True)
class VehicleControlOverride:
    """Authoritative commanded kinematic override computed by the safety policy."""

    vehicle_id: str
    action_type: SafetyActionType
    target_acceleration_mps2: float
    reason: str
    risk_level: CollisionRiskLevel
    triggering_pair_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize control override to dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "action_type": self.action_type.value,
            "target_acceleration_mps2": self.target_acceleration_mps2,
            "reason": self.reason,
            "risk_level": self.risk_level.value,
            "triggering_pair_ids": list(self.triggering_pair_ids),
        }


@dataclass(frozen=True)
class VehiclePairCollision:
    """Deterministic evaluation outcome between a canonical pair of vehicles."""

    vehicle_a_id: str
    vehicle_b_id: str
    distance_m: float
    ttc_s: Optional[float]
    closing_speed_mps: float
    risk_level: CollisionRiskLevel
    is_overlap: bool
    safe_separation_m: float
    separation_violated: bool
    recommended_action_a: SafetyActionType
    recommended_action_b: SafetyActionType
    action_a_decel: float
    action_b_decel: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize pair evaluation to dictionary."""
        return {
            "vehicle_a_id": self.vehicle_a_id,
            "vehicle_b_id": self.vehicle_b_id,
            "distance_m": round(self.distance_m, 4),
            "ttc_s": round(self.ttc_s, 4) if self.ttc_s is not None else None,
            "closing_speed_mps": round(self.closing_speed_mps, 4),
            "risk_level": self.risk_level.value,
            "is_overlap": self.is_overlap,
            "safe_separation_m": round(self.safe_separation_m, 4),
            "separation_violated": self.separation_violated,
            "recommended_action_a": self.recommended_action_a.value,
            "recommended_action_b": self.recommended_action_b.value,
            "action_a_decel": round(self.action_a_decel, 4),
            "action_b_decel": round(self.action_b_decel, 4),
        }


@dataclass(frozen=True)
class SafetyEvent:
    """Immutable structured record of a collision or near-miss incident."""

    event_id: str
    sim_time_s: float
    vehicle_ids: tuple[str, str]
    event_type: SafetyEventType
    risk_category: CollisionRiskLevel
    measured_separation_m: float
    estimated_ttc_s: Optional[float]
    action_taken_a: SafetyActionType
    action_taken_b: SafetyActionType
    is_overlap: bool
    edge_context: Optional[str] = None
    scenario_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize safety event to a plain JSON-compatible dictionary."""
        return {
            "event_id": self.event_id,
            "sim_time_s": round(self.sim_time_s, 4),
            "vehicle_ids": list(self.vehicle_ids),
            "event_type": self.event_type.value,
            "risk_category": self.risk_category.value,
            "measured_separation_m": round(self.measured_separation_m, 4),
            "estimated_ttc_s": (
                round(self.estimated_ttc_s, 4) if self.estimated_ttc_s is not None else None
            ),
            "action_taken_a": self.action_taken_a.value,
            "action_taken_b": self.action_taken_b.value,
            "is_overlap": self.is_overlap,
            "edge_context": self.edge_context,
            "scenario_id": self.scenario_id,
        }
