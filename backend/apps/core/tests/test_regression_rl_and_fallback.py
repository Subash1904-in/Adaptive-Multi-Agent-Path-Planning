"""Regression test suite for RL environment compliance, observation invariants, and safe fallback.

Verifies:
1. Gymnasium environment API compliance via standard check_env.
2. Observation and action space declarations, dimensions, dtypes, and bounds.
3. Observation finite-value guarantees (no NaN or Inf values).
4. Action mask validation and illegal action rejection.
5. Safe fallback to conventional routing upon missing or corrupt model artifacts.
6. SafeFallbackPolicyWrapper decision accounting, metric tracking, and graceful degradation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from apps.core.benchmarking.adapters import (
    SafeFallbackPolicyWrapper,
)
from apps.core.rl import (
    AMAPPSingleAgentEnv,
    SingleAgentRLConfig,
)
from apps.core.rl.exceptions import (
    InvalidActionError,
)
from apps.core.rl.model_manager import (
    CorruptModelArtifactError,
    ModelArtifactNotFoundError,
    validate_model_artifact,
)


class TestRLEnvironmentAndFallbackRegression:
    """Comprehensive regression tests for RL environment compliance and fallback safety."""

    def test_gymnasium_single_agent_environment_compliance(self) -> None:
        """AMAPPSingleAgentEnv complies with the standard Gymnasium specification."""
        env = AMAPPSingleAgentEnv()
        # check_env raises exception if Gymnasium contract is violated
        check_env(env)
        env.close()

    def test_observation_and_action_spaces_bounds(self) -> None:
        """Observation space is bounded [-1.0, 1.0] and action space matches discrete branching."""
        config = SingleAgentRLConfig(max_outgoing_actions=6, observation_dim=32)
        env = AMAPPSingleAgentEnv(config=config)

        obs_space = env.observation_space
        assert obs_space.shape == (32,)
        assert obs_space.dtype == np.float32
        assert np.all(obs_space.low == -1.0)
        assert np.all(obs_space.high == 1.0)

        # Action space: 1 (keep route) + 6 branching candidates = Discrete(7)
        assert env.action_space.n == 7
        env.close()

    def test_reset_and_step_produce_finite_observations_and_masks(self) -> None:
        """reset and step produce finite numeric observations and valid action masks."""
        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=42)

        # Observation checks
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (32,)
        assert np.all(np.isfinite(obs)), "Observation contains non-finite numbers (NaN/Inf)"
        assert np.all(obs >= -1.0) and np.all(obs <= 1.0)

        # Action mask checks
        assert "action_mask" in info
        mask = info["action_mask"]
        assert isinstance(mask, np.ndarray)
        assert mask.dtype == bool
        assert mask.shape == (env.action_space.n,)
        assert mask[0] is True or mask[0] == 1  # Action 0 (keep route) is always available

        # Step with keep route action (action 0)
        next_obs, reward, terminated, truncated, step_info = env.step(0)
        assert isinstance(next_obs, np.ndarray)
        assert np.all(np.isfinite(next_obs))
        assert isinstance(reward, (float, np.floating))
        assert np.isfinite(reward)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert "action_mask" in step_info
        env.close()

    def test_illegal_masked_action_rejected_with_invalid_action_error(self) -> None:
        """Actions outside bounds raise InvalidActionError; masked actions are penalized."""
        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=42)

        # 1. Out of bounds action strictly raises InvalidActionError
        with pytest.raises(InvalidActionError):
            env.step(999)

        # 2. In-bounds but masked action is safely handled without engine crash
        mask = info["action_mask"]
        illegal_indices = np.where(~mask)[0]
        if len(illegal_indices) > 0:
            illegal_action = int(illegal_indices[0])
            next_obs, reward, term, trunc, step_info = env.step(illegal_action)
            assert np.all(np.isfinite(next_obs))
            assert reward < 0.0 or step_info.get("is_invalid_action", False)
        env.close()

    def test_missing_and_corrupt_artifact_resolution(self, tmp_path: Path) -> None:
        """Model resolution and validation safely identify missing or corrupt archives."""
        # Non-existent file raises ModelArtifactNotFoundError when raise_on_error=True
        non_existent = tmp_path / "absent_model.zip"
        with pytest.raises(ModelArtifactNotFoundError):
            validate_model_artifact(non_existent, raise_on_error=True)

        # Corrupt / non-zip file raises CorruptModelArtifactError when raise_on_error=True
        corrupt_file = tmp_path / "corrupt_model.zip"
        corrupt_file.write_bytes(b"NOT_A_VALID_ZIP_HEADER_DATA")
        with pytest.raises(CorruptModelArtifactError):
            validate_model_artifact(corrupt_file, raise_on_error=True)

    def test_safe_fallback_policy_wrapper_accounting_and_fallback(self) -> None:
        """SafeFallbackPolicyWrapper intercepts invalid outputs and accounts fallback metrics."""
        mock_policy = MagicMock()
        mock_policy.predict.return_value = 999  # Out of bounds
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        mask = np.zeros(9, dtype=bool)
        mask[0] = True
        mask[1] = True

        # Action out of bounds -> fallback to legal keep-route action (0)
        action = wrapper(obs, {"action_mask": mask})
        assert action == 0
        assert wrapper.fallback_decisions == 1
        assert wrapper.invalid_actions_count == 1
        assert wrapper.fallback_reasons["out_of_bounds_action"] == 1

        # NaN output from model -> fallback
        mock_policy.predict.return_value = float("nan")
        action_nan = wrapper(obs, {"action_mask": mask})
        assert action_nan == 0
        assert wrapper.fallback_decisions == 2

        # Valid prediction -> direct acceptance
        mock_policy.predict.return_value = 1
        action_valid = wrapper(obs, {"action_mask": mask})
        assert action_valid == 1
        assert wrapper.learned_decisions == 1
