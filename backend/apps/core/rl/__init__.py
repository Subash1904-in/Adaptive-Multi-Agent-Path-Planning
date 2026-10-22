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
    LearnedRoutingConfig,
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
from apps.core.rl.model_manager import (
    CorruptModelArtifactError,
    IncompatibleModelArtifactError,
    ModelArtifactError,
    ModelArtifactNotFoundError,
    ModelValidationResult,
    RLModelManager,
    resolve_model_artifact_path,
    validate_model_artifact,
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
    "LearnedRoutingConfig",
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
    "RLModelManager",
    "resolve_model_artifact_path",
    "validate_model_artifact",
    "ModelValidationResult",
    "ModelArtifactError",
    "ModelArtifactNotFoundError",
    "CorruptModelArtifactError",
    "IncompatibleModelArtifactError",
]
