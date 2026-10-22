"""Configuration dataclasses for Single-Agent and Multi-Agent RL environments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class RewardConfig:
    """Configurable reward objective weights for AMAPP RL environments.

    Every component corresponds directly to authoritative simulation measurements.
    """

    progress_weight: float = 1.0
    arrival_reward: float = 100.0
    step_penalty: float = 0.05
    collision_penalty: float = 50.0
    near_miss_penalty: float = 10.0
    invalid_action_penalty: float = 2.0
    truncation_penalty: float = 10.0
    reroute_cost: float = 0.1

    def to_dict(self) -> dict[str, float]:
        return {
            "progress_weight": self.progress_weight,
            "arrival_reward": self.arrival_reward,
            "step_penalty": self.step_penalty,
            "collision_penalty": self.collision_penalty,
            "near_miss_penalty": self.near_miss_penalty,
            "invalid_action_penalty": self.invalid_action_penalty,
            "truncation_penalty": self.truncation_penalty,
            "reroute_cost": self.reroute_cost,
        }


@dataclass(frozen=True)
class SingleAgentRLConfig:
    """Configuration for single-agent Gymnasium environment."""

    scenario_id: str = "bench_grid_sparse_3x3"
    agent_id: Optional[str] = None
    decision_interval_ticks: int = 5
    max_steps: int = 200
    max_outgoing_actions: int = 8
    observation_dim: int = 32
    normalize_observations: bool = True
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    scenario_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision_interval_ticks <= 0:
            raise ValueError(
                f"decision_interval_ticks must be >= 1, got {self.decision_interval_ticks}"
            )
        if self.max_steps <= 0:
            raise ValueError(f"max_steps must be >= 1, got {self.max_steps}")
        if self.max_outgoing_actions <= 0:
            raise ValueError(f"max_outgoing_actions must be >= 1, got {self.max_outgoing_actions}")
        if self.observation_dim <= 0:
            raise ValueError(f"observation_dim must be >= 1, got {self.observation_dim}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "agent_id": self.agent_id,
            "decision_interval_ticks": self.decision_interval_ticks,
            "max_steps": self.max_steps,
            "max_outgoing_actions": self.max_outgoing_actions,
            "observation_dim": self.observation_dim,
            "normalize_observations": self.normalize_observations,
            "reward_config": self.reward_config.to_dict(),
            "scenario_options": dict(self.scenario_options),
        }


@dataclass(frozen=True)
class MultiAgentRLConfig:
    """Configuration for multi-agent Gymnasium environment."""

    scenario_id: str = "bench_urban_medium_4x4"
    agent_ids: Optional[list[str]] = None
    decision_interval_ticks: int = 5
    max_steps: int = 200
    max_outgoing_actions: int = 8
    observation_dim: int = 32
    normalize_observations: bool = True
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    scenario_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision_interval_ticks <= 0:
            raise ValueError(
                f"decision_interval_ticks must be >= 1, got {self.decision_interval_ticks}"
            )
        if self.max_steps <= 0:
            raise ValueError(f"max_steps must be >= 1, got {self.max_steps}")
        if self.max_outgoing_actions <= 0:
            raise ValueError(f"max_outgoing_actions must be >= 1, got {self.max_outgoing_actions}")
        if self.observation_dim <= 0:
            raise ValueError(f"observation_dim must be >= 1, got {self.observation_dim}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "agent_ids": list(self.agent_ids) if self.agent_ids else None,
            "decision_interval_ticks": self.decision_interval_ticks,
            "max_steps": self.max_steps,
            "max_outgoing_actions": self.max_outgoing_actions,
            "observation_dim": self.observation_dim,
            "normalize_observations": self.normalize_observations,
            "reward_config": self.reward_config.to_dict(),
            "scenario_options": dict(self.scenario_options),
        }


@dataclass(frozen=True)
class LearnedRoutingConfig:
    """Runtime configuration for optional learned RL routing strategy
    with safe conventional fallback.

    Ensures learned routing is strictly opt-in, preserving conventional Dijkstra, A*,
    static, and adaptive algorithms by default.
    """

    enabled: bool = False
    strategy_id: str = "learned"
    model_path: Optional[str] = None
    algorithm: str = "MaskablePPO"
    deterministic: bool = True
    fallback_algorithm: str = "astar"
    fallback_cost_mode: str = "travel_time"
    inference_timeout_s: Optional[float] = 1.0
    lazy_load: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert runtime configuration to JSON-serializable dictionary."""
        return {
            "enabled": self.enabled,
            "strategy_id": self.strategy_id,
            "model_path": self.model_path,
            "algorithm": self.algorithm,
            "deterministic": self.deterministic,
            "fallback_algorithm": self.fallback_algorithm,
            "fallback_cost_mode": self.fallback_cost_mode,
            "inference_timeout_s": self.inference_timeout_s,
            "lazy_load": self.lazy_load,
        }
