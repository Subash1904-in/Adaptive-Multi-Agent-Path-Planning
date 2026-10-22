"""Reinforcement Learning (RL) environment package for AMAPP.

Provides deterministic, Gymnasium-compatible single-agent and multi-agent simulation
environments for autonomous vehicle path planning and routing decisions.
"""

from apps.core.rl.adapter import (
    GreedyProgressTestPolicy,
    RandomTestPolicy,
    evaluate_rl_environment_episode,
)
from apps.core.rl.config import (
    MultiAgentRLConfig,
    RewardConfig,
    SingleAgentRLConfig,
)
from apps.core.rl.env import AMAPPSingleAgentEnv
from apps.core.rl.exceptions import (
    ActionMaskError,
    AgentNotFoundError,
    InvalidActionError,
    ObservationError,
    RLEnvironmentError,
    ScenarioResetError,
)
from apps.core.rl.features import (
    OBSERVATION_FEATURE_NAMES,
    extract_agent_observation,
)
from apps.core.rl.multi_agent import AMAPPMultiAgentEnv
from apps.core.rl.rewards import (
    RewardBreakdown,
    RewardCalculator,
)

__all__ = [
    "AMAPPSingleAgentEnv",
    "AMAPPMultiAgentEnv",
    "SingleAgentRLConfig",
    "MultiAgentRLConfig",
    "RewardConfig",
    "RewardBreakdown",
    "RewardCalculator",
    "OBSERVATION_FEATURE_NAMES",
    "extract_agent_observation",
    "GreedyProgressTestPolicy",
    "RandomTestPolicy",
    "evaluate_rl_environment_episode",
    "RLEnvironmentError",
    "InvalidActionError",
    "ObservationError",
    "ScenarioResetError",
    "ActionMaskError",
    "AgentNotFoundError",
]
