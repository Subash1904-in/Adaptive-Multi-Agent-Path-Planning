"""Deterministic collision, safe separation, and Time-To-Collision (TTC) detection.

Evaluates multi-vehicle conflicts from a consistent snapshot of vehicle states,
providing canonical pairwise ordering, relative closing speed analysis,
safe separation distance computation, and hierarchical risk classification.
"""

import math
from typing import Optional, Sequence

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import Vehicle
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.exceptions import GeometryValidationError
from apps.core.safety.geometry import (
    OrientedBoundingBox2D,
    check_obb_overlap_sat,
    compute_obb_separation_distance,
)
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    VehiclePairCollision,
)


def compute_closing_speed(
    pos_a: tuple[float, float],
    vel_a: tuple[float, float],
    pos_b: tuple[float, float],
    vel_b: tuple[float, float],
) -> float:
    """Compute the relative closing speed between two entities in meters per second.

    Closing speed represents the instantaneous rate of decrease of the distance
    between entity centers: v_closing = -d(Distance)/dt.

    Positive v_closing (> 0) means the entities are closing in on each other.
    Zero or negative v_closing (<= 0) means they are stationary or moving apart.

    Args:
        pos_a: (x, y) coordinates of entity A in meters.
        vel_a: (vx, vy) velocity vector of entity A in m/s.
        pos_b: (x, y) coordinates of entity B in meters.
        vel_b: (vx, vy) velocity vector of entity B in m/s.

    Returns:
        Closing speed in m/s (positive when closing, negative when receding).
    """
    dx = pos_b[0] - pos_a[0]
    dy = pos_b[1] - pos_a[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return 0.0

    # Relative velocity vector Delta_v = v_b - v_a
    dvx = vel_b[0] - vel_a[0]
    dvy = vel_b[1] - vel_a[1]

    # Rate of distance change d(dist)/dt = (Delta_p . Delta_v) / dist
    rate_of_dist_change = (dx * dvx + dy * dvy) / dist
    return -rate_of_dist_change


def compute_safe_separation_distance(
    speed_a_mps: float,
    speed_b_mps: float,
    closing_speed_mps: float,
    config: SafetyConfig,
) -> float:
    """Calculate the required safe separation distance d_safe in meters.

    Formula:
        d_safe = d_0 + v_rel^+ * T_r + max(d_brake_a, d_brake_b)
    where:
        d_0 = config.min_separation_m
        v_rel^+ = max(0.0, closing_speed_mps)
        T_r = config.reaction_time_s
        d_brake = v^2 / (2 * config.braking_accel_reference_mps2)

    Args:
        speed_a_mps: Longitudinal speed of vehicle A in m/s.
        speed_b_mps: Longitudinal speed of vehicle B in m/s.
        closing_speed_mps: Relative closing speed in m/s.
        config: Safety configuration parameters.

    Returns:
        Minimum safe separation distance in meters (> 0.0).
    """
    d0 = config.min_separation_m
    v_rel_plus = max(0.0, closing_speed_mps)
    tr = config.reaction_time_s
    a_brake = config.braking_accel_reference_mps2

    d_brake_a = (speed_a_mps * speed_a_mps) / (2.0 * a_brake) if speed_a_mps > 0 else 0.0
    d_brake_b = (speed_b_mps * speed_b_mps) / (2.0 * a_brake) if speed_b_mps > 0 else 0.0

    return d0 + v_rel_plus * tr + max(d_brake_a, d_brake_b)


def estimate_time_to_collision(
    separation_distance_m: float,
    closing_speed_mps: float,
    is_overlap: bool,
) -> Optional[float]:
    """Estimate Time-To-Collision (TTC) in simulation seconds.

    Semantics:
        - If vehicles already geometrically overlap: returns 0.0 seconds.
        - If closing speed <= 1e-4 m/s (stationary, moving apart, or non-closing):
          returns None (no collision course predicted).
        - If closing: returns separation_distance_m / closing_speed_mps.

    Args:
        separation_distance_m: Minimum boundary-to-boundary distance in meters.
        closing_speed_mps: Relative closing speed in m/s.
        is_overlap: Whether vehicle bounding boxes currently overlap.

    Returns:
        Estimated TTC in seconds, or None if vehicles are not closing.
    """
    if is_overlap:
        return 0.0
    if closing_speed_mps <= 1e-4:
        return None
    eff_dist = max(0.0, separation_distance_m)
    return eff_dist / closing_speed_mps


def classify_collision_risk(
    is_overlap: bool,
    separation_distance_m: float,
    ttc_s: Optional[float],
    safe_separation_m: float,
    config: SafetyConfig,
) -> CollisionRiskLevel:
    """Classify the safety risk level for a vehicle pair based on geometric and kinematic metrics.

    Priority hierarchy:
        1. COLLISION: Geometric bounding box overlap is true.
        2. IMMINENT: TTC <= config.ttc_imminent_s OR separation < 0.5 * config.min_separation_m.
        3. HIGH_RISK: TTC <= config.ttc_high_risk_s OR separation < config.min_separation_m.
        4. CAUTION: TTC <= config.ttc_caution_s OR separation < safe_separation_m.
        5. SAFE: Separation is safe and no imminent/high/caution TTC violations.

    Args:
        is_overlap: True if bounding envelopes intersect.
        separation_distance_m: Measured boundary-to-boundary separation in meters.
        ttc_s: Estimated time-to-collision in seconds (None if non-closing).
        safe_separation_m: Configured safe separation distance in meters.
        config: Authoritative safety configuration.

    Returns:
        CollisionRiskLevel category.
    """
    if is_overlap:
        return CollisionRiskLevel.COLLISION

    # Check IMMINENT condition
    if (ttc_s is not None and ttc_s <= config.ttc_imminent_s) or (
        separation_distance_m < 0.5 * config.min_separation_m
    ):
        return CollisionRiskLevel.IMMINENT

    # Check HIGH_RISK condition
    if (ttc_s is not None and ttc_s <= config.ttc_high_risk_s) or (
        separation_distance_m < config.min_separation_m
    ):
        return CollisionRiskLevel.HIGH_RISK

    # Check CAUTION condition
    if (ttc_s is not None and ttc_s <= config.ttc_caution_s) or (
        separation_distance_m < safe_separation_m
    ):
        return CollisionRiskLevel.CAUTION

    return CollisionRiskLevel.SAFE


class CollisionDetector:
    """Pairwise collision and conflict detector operating across all active simulation vehicles."""

    def __init__(self, config: Optional[SafetyConfig] = None) -> None:
        """Initialize the collision detector with an optional SafetyConfig."""
        self.config: SafetyConfig = config or SafetyConfig()

    def evaluate_pair(
        self,
        vehicle_a: Vehicle,
        vehicle_b: Vehicle,
    ) -> VehiclePairCollision:
        """Deterministically evaluate geometric overlap, safe separation, and risk for two vehicles.

        Args:
            vehicle_a: First vehicle entity.
            vehicle_b: Second vehicle entity.

        Returns:
            VehiclePairCollision containing detailed metrics and recommended actions.

        Raises:
            GeometryValidationError: If vehicles are identical or possess invalid geometry.
        """
        if vehicle_a.id == vehicle_b.id:
            raise GeometryValidationError(
                f"Cannot evaluate collision for vehicle '{vehicle_a.id}' with itself.",
                vehicle_id=vehicle_a.id,
            )

        box_a = OrientedBoundingBox2D.from_vehicle(vehicle_a)
        box_b = OrientedBoundingBox2D.from_vehicle(vehicle_b)

        # 1. Geometric overlap and minimum distance
        is_overlap = check_obb_overlap_sat(
            box_a, box_b, touching_is_overlap=self.config.touching_is_overlap
        )
        separation_dist_m = compute_obb_separation_distance(
            box_a, box_b, touching_is_overlap=self.config.touching_is_overlap
        )

        # 2. Kinematics and closing speed
        pos_a = (vehicle_a.position.x, vehicle_a.position.y)
        pos_b = (vehicle_b.position.x, vehicle_b.position.y)
        vel_a = (
            vehicle_a.speed_mps * math.cos(vehicle_a.heading_rad),
            vehicle_a.speed_mps * math.sin(vehicle_a.heading_rad),
        )
        vel_b = (
            vehicle_b.speed_mps * math.cos(vehicle_b.heading_rad),
            vehicle_b.speed_mps * math.sin(vehicle_b.heading_rad),
        )

        closing_spd = compute_closing_speed(pos_a, vel_a, pos_b, vel_b)
        safe_sep_m = compute_safe_separation_distance(
            speed_a_mps=vehicle_a.speed_mps,
            speed_b_mps=vehicle_b.speed_mps,
            closing_speed_mps=closing_spd,
            config=self.config,
        )
        sep_violated = separation_dist_m < safe_sep_m

        # 3. TTC and Risk Classification
        ttc_s = estimate_time_to_collision(separation_dist_m, closing_spd, is_overlap)
        risk = classify_collision_risk(
            is_overlap=is_overlap,
            separation_distance_m=separation_dist_m,
            ttc_s=ttc_s,
            safe_separation_m=safe_sep_m,
            config=self.config,
        )

        # 4. Preliminary recommended actions per vehicle based on directional contribution
        action_a, decel_a, action_b, decel_b = self._compute_pair_actions(
            vehicle_a, vehicle_b, risk, is_overlap
        )

        return VehiclePairCollision(
            vehicle_a_id=vehicle_a.id,
            vehicle_b_id=vehicle_b.id,
            distance_m=separation_dist_m,
            ttc_s=ttc_s,
            closing_speed_mps=closing_spd,
            risk_level=risk,
            is_overlap=is_overlap,
            safe_separation_m=safe_sep_m,
            separation_violated=sep_violated,
            recommended_action_a=action_a,
            recommended_action_b=action_b,
            action_a_decel=decel_a,
            action_b_decel=decel_b,
        )

    def _compute_pair_actions(
        self,
        vehicle_a: Vehicle,
        vehicle_b: Vehicle,
        risk: CollisionRiskLevel,
        is_overlap: bool,
    ) -> tuple[SafetyActionType, float, SafetyActionType, float]:
        """Determine preliminary braking action recommendations for each vehicle in the pair."""
        if risk == CollisionRiskLevel.SAFE:
            return (SafetyActionType.NONE, 0.0, SafetyActionType.NONE, 0.0)

        # Base deceleration magnitude for the risk tier
        if risk in (CollisionRiskLevel.COLLISION, CollisionRiskLevel.IMMINENT):
            action = SafetyActionType.EMERGENCY_BRAKE
            decel = self.config.emergency_decel_mps2
        elif risk == CollisionRiskLevel.HIGH_RISK:
            action = SafetyActionType.STRONG_BRAKE
            decel = self.config.strong_decel_mps2
        else:  # CAUTION
            action = SafetyActionType.GENTLE_BRAKE
            decel = self.config.gentle_decel_mps2

        if is_overlap:
            # Overlap requires immediate emergency braking from both
            return (action, decel, action, decel)

        # Directional closing analysis: check if vehicle is traveling towards the other
        dx_ab = vehicle_b.position.x - vehicle_a.position.x
        dy_ab = vehicle_b.position.y - vehicle_a.position.y
        dist_ab = math.hypot(dx_ab, dy_ab)

        if dist_ab < 1e-6:
            return (action, decel, action, decel)

        u_ab_x = dx_ab / dist_ab
        u_ab_y = dy_ab / dist_ab

        # Velocity projection towards the other vehicle
        v_a_towards_b = (
            math.cos(vehicle_a.heading_rad) * u_ab_x + math.sin(vehicle_a.heading_rad) * u_ab_y
        ) * vehicle_a.speed_mps
        v_b_towards_a = (
            math.cos(vehicle_b.heading_rad) * (-u_ab_x)
            + math.sin(vehicle_b.heading_rad) * (-u_ab_y)
        ) * vehicle_b.speed_mps

        # If a vehicle is receding away from the other, it should not brake for this conflict
        # unless risk is IMMINENT or COLLISION
        receding_threshold = 1e-3

        action_a = (
            action
            if (v_a_towards_b > receding_threshold or risk == CollisionRiskLevel.IMMINENT)
            else SafetyActionType.NONE
        )
        decel_a = decel if action_a != SafetyActionType.NONE else 0.0

        action_b = (
            action
            if (v_b_towards_a > receding_threshold or risk == CollisionRiskLevel.IMMINENT)
            else SafetyActionType.NONE
        )
        decel_b = decel if action_b != SafetyActionType.NONE else 0.0

        # If both were classified as receding due to cross-angle calculation but closing speed > 0,
        # assign braking to whichever is moving faster
        if (
            action_a == SafetyActionType.NONE
            and action_b == SafetyActionType.NONE
            and risk != CollisionRiskLevel.SAFE
        ):
            if vehicle_a.speed_mps >= vehicle_b.speed_mps:
                action_a, decel_a = action, decel
            else:
                action_b, decel_b = action, decel

        return (action_a, decel_a, action_b, decel_b)

    def detect_all_conflicts(
        self,
        agents: Sequence[VehicleAgent],
    ) -> list[VehiclePairCollision]:
        """Detect conflicts across all active vehicles in deterministic canonical order.

        Rules:
        - Only active vehicles (state in (EN_ROUTE, BLOCKED, STOPPED)) are evaluated.
        - Arrived vehicles (ARRIVED) and unassigned/idle vehicles (IDLE) are excluded.
        - Canonical pair ordering: (min(v1.id, v2.id), max(v1.id, v2.id)).
        - Stable enumeration ensures order-independent deterministic outcomes.

        Args:
            agents: Sequence of VehicleAgent instances in current world state.

        Returns:
            List of VehiclePairCollision results for all evaluated pairs.
        """
        # Filter active agents
        active_agents = [
            ag
            for ag in agents
            if ag.state in (VehicleState.EN_ROUTE, VehicleState.BLOCKED, VehicleState.STOPPED)
        ]
        # Sort deterministically by vehicle id
        sorted_agents = sorted(active_agents, key=lambda ag: ag.vehicle.id)

        conflicts: list[VehiclePairCollision] = []
        n = len(sorted_agents)

        for i in range(n):
            for j in range(i + 1, n):
                ag_a = sorted_agents[i]
                ag_b = sorted_agents[j]
                pair_result = self.evaluate_pair(ag_a.vehicle, ag_b.vehicle)
                conflicts.append(pair_result)

        return conflicts
