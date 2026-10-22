"""Reward computation engine for AMAPP RL environments.

Calculates transparent, objective-driven rewards and penalties directly from authoritative
simulation measurements without future leakage or double-counting.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.core.rl.config import RewardConfig


@dataclass(frozen=True)
class RewardBreakdown:
    """Detailed breakdown of individual reward components for transparency and diagnostics."""

    progress_reward: float
    step_penalty: float
    arrival_reward: float
    collision_penalty: float
    near_miss_penalty: float
    invalid_action_penalty: float
    truncation_penalty: float
    reroute_penalty: float
    total_reward: float

    def to_dict(self) -> dict[str, float]:
        return {
            "progress_reward": self.progress_reward,
            "step_penalty": self.step_penalty,
            "arrival_reward": self.arrival_reward,
            "collision_penalty": self.collision_penalty,
            "near_miss_penalty": self.near_miss_penalty,
            "invalid_action_penalty": self.invalid_action_penalty,
            "truncation_penalty": self.truncation_penalty,
            "reroute_penalty": self.reroute_penalty,
            "total_reward": self.total_reward,
        }


class RewardCalculator:
    """Calculates step rewards from physical motion, safety events, and goal progress."""

    def __init__(self, config: RewardConfig) -> None:
        self.config = config

    def calculate_reward(
        self,
        prev_distance_m: float,
        curr_distance_m: float,
        is_arrived: bool,
        arrival_already_rewarded: bool,
        new_collisions: int = 0,
        new_near_misses: int = 0,
        is_invalid_action: bool = False,
        is_truncated: bool = False,
        is_rerouted: bool = False,
        diag_span_m: float = 200.0,
    ) -> RewardBreakdown:
        """Compute the step reward and breakdown.

        Args:
            prev_distance_m: Previous distance to destination in meters.
            curr_distance_m: Current distance to destination in meters.
            is_arrived: Whether vehicle is currently at destination.
            arrival_already_rewarded: Whether arrival bonus was already credited in this episode.
            new_collisions: Number of collision events experienced during this step.
            new_near_misses: Number of near-miss events experienced during this step.
            is_invalid_action: Whether the action chosen by agent was rejected as invalid.
            is_truncated: Whether the step resulted in episode truncation.
            is_rerouted: Whether a new route was successfully executed.
            diag_span_m: Diagonal network scale for normalizing progress distance.
        """
        # 1. Progress reward: positive when vehicle moves closer, negative when moving away
        scale = max(diag_span_m, 10.0)
        dist_delta_m = prev_distance_m - curr_distance_m
        progress_reward = self.config.progress_weight * (dist_delta_m / scale)

        # 2. Step penalty: constant cost per step to encourage prompt completion
        step_penalty = -abs(self.config.step_penalty)

        # 3. Arrival bonus: credited exactly once upon successful completion
        arrival_reward = 0.0
        if is_arrived and not arrival_already_rewarded:
            arrival_reward = abs(self.config.arrival_reward)

        # 4. Safety penalties
        collision_penalty = -abs(self.config.collision_penalty) * max(0, new_collisions)
        near_miss_penalty = -abs(self.config.near_miss_penalty) * max(0, new_near_misses)

        # 5. Invalid action penalty
        invalid_action_penalty = (
            -abs(self.config.invalid_action_penalty) if is_invalid_action else 0.0
        )

        # 6. Truncation penalty
        truncation_penalty = -abs(self.config.truncation_penalty) if is_truncated else 0.0

        # 7. Reroute cost
        reroute_penalty = -abs(self.config.reroute_cost) if is_rerouted else 0.0

        total_reward = (
            progress_reward
            + step_penalty
            + arrival_reward
            + collision_penalty
            + near_miss_penalty
            + invalid_action_penalty
            + truncation_penalty
            + reroute_penalty
        )

        return RewardBreakdown(
            progress_reward=float(progress_reward),
            step_penalty=float(step_penalty),
            arrival_reward=float(arrival_reward),
            collision_penalty=float(collision_penalty),
            near_miss_penalty=float(near_miss_penalty),
            invalid_action_penalty=float(invalid_action_penalty),
            truncation_penalty=float(truncation_penalty),
            reroute_penalty=float(reroute_penalty),
            total_reward=float(total_reward),
        )
