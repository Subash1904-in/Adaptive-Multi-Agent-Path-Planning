"""Deterministic collision avoidance and multi-conflict resolution policy.

Translates detected risks and separation violations into bounded deceleration overrides,
deterministically resolving simultaneous conflicts by choosing the most conservative
braking action without altering road topology or vehicle route progress.
"""

from typing import Sequence

from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    VehicleControlOverride,
    VehiclePairCollision,
)

RISK_RANK: dict[CollisionRiskLevel, int] = {
    CollisionRiskLevel.SAFE: 0,
    CollisionRiskLevel.CAUTION: 1,
    CollisionRiskLevel.HIGH_RISK: 2,
    CollisionRiskLevel.IMMINENT: 3,
    CollisionRiskLevel.COLLISION: 4,
}

ACTION_RANK: dict[SafetyActionType, int] = {
    SafetyActionType.NONE: 0,
    SafetyActionType.GENTLE_BRAKE: 1,
    SafetyActionType.STRONG_BRAKE: 2,
    SafetyActionType.EMERGENCY_BRAKE: 3,
}


class SafetyPolicy:
    """Authoritative collision avoidance policy engine."""

    def __init__(self, config: SafetyConfig) -> None:
        """Initialize the safety policy engine with a validated SafetyConfig."""
        self.config: SafetyConfig = config

    def resolve_conflicts(
        self,
        agents: Sequence[VehicleAgent],
        pair_collisions: Sequence[VehiclePairCollision],
    ) -> dict[str, VehicleControlOverride]:
        """Deterministically resolve pairwise conflicts into per-vehicle control overrides.

        Policy rules:
        - Vehicles with only SAFE interactions receive no override (normal control continues).
        - For vehicles involved in multiple simultaneous conflicts:
          Select the most conservative (highest deceleration magnitude) braking action.
        - Commanded deceleration is clamped to the vehicle's physical max_deceleration_mps2.
        - Negative speeds are prevented by the kinematics motion integration layer.
        - Stable ordering ensures outcomes are 100% deterministic regardless of iteration order.

        Args:
            agents: Sequence of active VehicleAgent instances.
            pair_collisions: List of evaluated VehiclePairCollision outcomes.

        Returns:
            Dictionary mapping vehicle_id to VehicleControlOverride for affected vehicles.
        """
        # Map vehicle_id -> list of (action_type, decel_magnitude, risk_level, other_vehicle_id)
        candidate_actions: dict[
            str, list[tuple[SafetyActionType, float, CollisionRiskLevel, str]]
        ] = {ag.vehicle.id: [] for ag in agents}

        for pair in pair_collisions:
            if pair.risk_level == CollisionRiskLevel.SAFE:
                continue

            # Process Vehicle A
            if pair.recommended_action_a != SafetyActionType.NONE:
                if pair.vehicle_a_id in candidate_actions:
                    candidate_actions[pair.vehicle_a_id].append(
                        (
                            pair.recommended_action_a,
                            pair.action_a_decel,
                            pair.risk_level,
                            pair.vehicle_b_id,
                        )
                    )

            # Process Vehicle B
            if pair.recommended_action_b != SafetyActionType.NONE:
                if pair.vehicle_b_id in candidate_actions:
                    candidate_actions[pair.vehicle_b_id].append(
                        (
                            pair.recommended_action_b,
                            pair.action_b_decel,
                            pair.risk_level,
                            pair.vehicle_a_id,
                        )
                    )

        overrides: dict[str, VehicleControlOverride] = {}
        agent_map = {ag.vehicle.id: ag for ag in agents}

        # Sort vehicle IDs for stable deterministic iteration
        for vid in sorted(candidate_actions.keys()):
            actions = candidate_actions[vid]
            if not actions:
                continue

            # Sort actions deterministically: highest action rank first, highest decel first
            # in case of tie, highest risk rank first, then sorted other_vehicle_id
            actions_sorted = sorted(
                actions,
                key=lambda item: (
                    ACTION_RANK[item[0]],
                    item[1],
                    RISK_RANK[item[2]],
                ),
                reverse=True,
            )

            winning_action, winning_decel, winning_risk, _ = actions_sorted[0]
            triggering_ids = tuple(sorted(set(item[3] for item in actions)))

            # Clamp commanded deceleration against vehicle kinematics physical limit
            agent = agent_map[vid]
            max_phys_decel = agent.config.max_deceleration_mps2
            effective_decel = min(winning_decel, max_phys_decel)
            target_accel = -effective_decel

            reason = (
                f"Safety override: {winning_action.value} due to {winning_risk.value} risk "
                f"with vehicle(s) {list(triggering_ids)}"
            )

            overrides[vid] = VehicleControlOverride(
                vehicle_id=vid,
                action_type=winning_action,
                target_acceleration_mps2=target_accel,
                reason=reason,
                risk_level=winning_risk,
                triggering_pair_ids=triggering_ids,
            )

        return overrides
