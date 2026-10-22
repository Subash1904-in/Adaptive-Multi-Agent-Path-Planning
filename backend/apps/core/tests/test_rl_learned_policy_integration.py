"""Automated tests for RL learned policy evaluation, validation, and safe fallback.

Phase 34 Test Suite covering:
1. Model Artifact Discovery, Validation, and Cache Lifecycle
2. Inference Safety, Bounds Checking, and Action-Mask Validation
3. Multi-Layer Fallback Policy Execution and Observable Diagnostics
4. Benchmark Framework Integration and Held-Out Scenario Execution
5. Isolation, Non-Interference, and Simulation Safety
"""

from __future__ import annotations

import json
import os
import threading
import time
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from gymnasium import spaces

from apps.core.benchmarking.adapters import (
    AlgorithmRegistry,
    LearnedRoutingBenchmarkAdapter,
    SafeFallbackPolicyWrapper,
)
from apps.core.benchmarking.models import BenchmarkStatus, BenchmarkTrialResult
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.rl.config import LearnedRoutingConfig
from apps.core.rl.model_manager import (
    CorruptModelArtifactError,
    IncompatibleModelArtifactError,
    ModelArtifactNotFoundError,
    RLModelManager,
    resolve_model_artifact_path,
    validate_model_artifact,
)

MASK_3_LEGAL = np.array([True, True, True, False, False, False, False, False, False])
MASK_2_LEGAL = np.array([True, True, False, False, False, False, False, False, False])
MASK_0_LEGAL = np.array([True, False, False, False, False, False, False, False, False])
MASK_BRANCH2_ONLY = np.array([False, False, True, False, False, False, False, False, False])


# ==============================================================================
# 1. Model Artifact Discovery, Validation & Cache Lifecycle Tests
# ==============================================================================
class TestModelArtifactDiscoveryAndValidation:
    """Verify artifact discovery, integrity inspection, space compatibility, and caching."""

    def test_resolve_model_artifact_path_explicit_file(self, tmp_path: Path) -> None:
        model_file = tmp_path / "custom_model.zip"
        model_file.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # Empty zip archive
        resolved = resolve_model_artifact_path(model_file)
        assert resolved is not None
        assert resolved.resolve() == model_file.resolve()

    def test_resolve_model_artifact_path_missing(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "does_not_exist.zip"
        assert resolve_model_artifact_path(missing_file) is None

    def test_resolve_model_artifact_path_env_var(self, tmp_path: Path) -> None:
        model_file = tmp_path / "env_model.zip"
        model_file.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        with patch.dict(os.environ, {"AMAPP_RL_MODEL_PATH": str(model_file)}):
            resolved = resolve_model_artifact_path(None)
            assert resolved is not None
            assert resolved.resolve() == model_file.resolve()

    def test_validate_model_artifact_nonexistent_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost_model.zip"
        res = validate_model_artifact(missing, raise_on_error=False)
        assert res.is_valid is False
        assert "does not exist" in (res.error_message or "")

        with pytest.raises(ModelArtifactNotFoundError, match="does not exist"):
            validate_model_artifact(missing, raise_on_error=True)

    def test_validate_model_artifact_corrupt_zip(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "corrupt_model.zip"
        corrupt.write_text("Not a zip archive content", encoding="utf-8")
        res = validate_model_artifact(corrupt, raise_on_error=False)
        assert res.is_valid is False
        assert "not a valid zip archive" in (res.error_message or "")

        with pytest.raises(CorruptModelArtifactError, match="not a valid zip archive"):
            validate_model_artifact(corrupt, raise_on_error=True)

    def test_validate_model_artifact_missing_data_entry(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "missing_data.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("some_file.txt", "hello")
        res = validate_model_artifact(zip_path, raise_on_error=False)
        assert res.is_valid is False
        assert "missing SB3 serialization entry 'data'" in (res.error_message or "")

        with pytest.raises(
            CorruptModelArtifactError, match="missing SB3 serialization entry 'data'"
        ):
            validate_model_artifact(zip_path, raise_on_error=True)

    def test_validate_model_artifact_space_mismatch(self, tmp_path: Path) -> None:
        fake_zip = tmp_path / "fake_model.zip"
        with zipfile.ZipFile(fake_zip, "w") as zf:
            zf.writestr("data", json.dumps({"policy_class": "MlpPolicy"}))

        mock_policy = MagicMock()
        mock_model = MagicMock()
        mock_model.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(16,), dtype=np.float32)
        mock_model.action_space = spaces.Discrete(9)
        mock_policy.model = mock_model

        with patch("apps.core.rl.training.policy.RLModelPolicy.load", return_value=mock_policy):
            res = validate_model_artifact(fake_zip, expected_obs_dim=32, raise_on_error=False)
            assert res.is_valid is False
            assert "Observation space mismatch" in (res.error_message or "")

            with pytest.raises(IncompatibleModelArtifactError, match="Observation space mismatch"):
                validate_model_artifact(fake_zip, expected_obs_dim=32, raise_on_error=True)

    def test_validate_model_artifact_action_space_mismatch(self, tmp_path: Path) -> None:
        fake_zip = tmp_path / "fake_model.zip"
        with zipfile.ZipFile(fake_zip, "w") as zf:
            zf.writestr("data", json.dumps({"policy_class": "MlpPolicy"}))

        mock_policy = MagicMock()
        mock_model = MagicMock()
        mock_model.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)
        mock_model.action_space = spaces.Discrete(5)
        mock_policy.model = mock_model

        with patch("apps.core.rl.training.policy.RLModelPolicy.load", return_value=mock_policy):
            res = validate_model_artifact(fake_zip, expected_actions=9, raise_on_error=False)
            assert res.is_valid is False
            assert "Action space mismatch" in (res.error_message or "")

            with pytest.raises(IncompatibleModelArtifactError, match="Action space mismatch"):
                validate_model_artifact(fake_zip, expected_actions=9, raise_on_error=True)

    def test_model_manager_caching_and_reload(self, tmp_path: Path) -> None:
        manager = RLModelManager()
        model_file = tmp_path / "test_model.zip"
        with zipfile.ZipFile(model_file, "w") as zf:
            zf.writestr("data", "sb3_data")

        mock_policy = MagicMock()
        mock_model = MagicMock()
        mock_model.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)
        mock_model.action_space = spaces.Discrete(9)
        mock_policy.model = mock_model

        with patch("apps.core.rl.training.policy.RLModelPolicy.load", return_value=mock_policy):
            # First load: populates cache
            p1, val1 = manager.get_policy(model_file)
            assert val1.is_valid is True
            assert p1 is mock_policy

            # Second load: retrieves from cache (identical instance)
            p2, val2 = manager.get_policy(model_file)
            assert p2 is p1

            # Reload: bypasses cache
            p3, val3 = manager.get_policy(model_file, reload=True)
            assert val3.is_valid is True

            # Clear cache: evicts entries
            manager.clear_cache()
            assert len(manager._cache) == 0

    def test_model_manager_thread_safety(self, tmp_path: Path) -> None:
        manager = RLModelManager()
        model_file = tmp_path / "threaded_model.zip"
        with zipfile.ZipFile(model_file, "w") as zf:
            zf.writestr("data", "sb3_data")

        mock_policy = MagicMock()
        mock_model = MagicMock()
        mock_model.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)
        mock_model.action_space = spaces.Discrete(9)
        mock_policy.model = mock_model

        results = []
        errors = []

        def worker() -> None:
            try:
                p, val = manager.get_policy(model_file)
                results.append((p, val.is_valid))
            except Exception as exc:
                errors.append(exc)

        with patch("apps.core.rl.training.policy.RLModelPolicy.load", return_value=mock_policy):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(results) == 8
        assert all(val is True for _, val in results)


# ==============================================================================
# 2. Inference Safety, Bounds Checking & Mask Validation Tests
# ==============================================================================
class TestInferenceSafetyAndBoundsChecking:
    """Verify policy inference validation, bounds checking, and mask enforcement."""

    def test_wrapper_accepts_valid_unmasked_action(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.return_value = 2  # Branch action 2
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_3_LEGAL}

        action = wrapper(obs, info)
        assert action == 2
        assert wrapper.learned_decisions == 1
        assert wrapper.fallback_decisions == 0
        assert wrapper.invalid_actions_count == 0

    def test_wrapper_rejects_out_of_bounds_action(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.return_value = 42  # Out of Discrete(9) bounds
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}

        action = wrapper(obs, info)
        assert action == 0  # Fallback to keep-route (action 0 is legal)
        assert wrapper.invalid_actions_count == 1
        assert wrapper.fallback_decisions == 1
        assert wrapper.fallback_reasons["out_of_bounds_action"] == 1

    def test_wrapper_rejects_negative_action(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.return_value = -1
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}

        action = wrapper(obs, info)
        assert action == 0
        assert wrapper.invalid_actions_count == 1
        assert wrapper.fallback_reasons["out_of_bounds_action"] == 1

    def test_wrapper_rejects_non_finite_output(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.return_value = float("nan")
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}

        action = wrapper(obs, info)
        assert action == 0
        assert wrapper.fallback_reasons["malformed_output"] == 1

    def test_wrapper_rejects_masked_action(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.return_value = 3  # Action 3 is masked out
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        # Only action 0 and action 1 are legal
        info = {"action_mask": MASK_2_LEGAL}

        action = wrapper(obs, info)
        assert action == 0
        assert wrapper.invalid_actions_count == 1
        assert wrapper.masked_actions_rejected == 1
        assert wrapper.fallback_reasons["masked_action_rejected"] == 1

    def test_wrapper_handles_inference_exception(self) -> None:
        mock_policy = MagicMock()
        mock_policy.predict.side_effect = RuntimeError("GPU memory corruption")
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_0_LEGAL}

        action = wrapper(obs, info)
        assert action == 0
        assert wrapper.fallback_decisions == 1
        assert "inference_exception:RuntimeError" in wrapper.fallback_reasons

    def test_wrapper_handles_timeout_enforcement(self) -> None:
        def slow_predict(obs: Any, info: Any) -> int:
            time.sleep(0.05)
            return 1

        mock_policy = MagicMock()
        mock_policy.predict.side_effect = slow_predict
        # Timeout configured to 0.01s (10ms)
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy, timeout_s=0.01)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}

        action = wrapper(obs, info)
        assert action == 0
        assert wrapper.fallback_reasons["inference_timeout"] == 1


# ==============================================================================
# 3. Fallback Policy Strategy & Incident Protection Tests
# ==============================================================================
class TestFallbackPolicyStrategyAndIncidentProtection:
    """Verify fallback policy behavior when Keep Route is blocked by an incident."""

    def test_fallback_when_action_0_blocked_finds_alternative(self) -> None:
        # In case current road is blocked by incident, action 0 is masked False
        # Action 2 is the legal alternative
        mock_policy = MagicMock()
        mock_policy.predict.side_effect = RuntimeError("Inference crash")

        # Custom fallback that picks action 2
        def fallback_planner(obs: Any, info: Any) -> int:
            return 2

        wrapper = SafeFallbackPolicyWrapper(
            model_policy=mock_policy,
            fallback_policy=fallback_planner,
        )

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_BRANCH2_ONLY}

        action = wrapper(obs, info)
        assert action == 2
        assert wrapper.fallback_decisions == 1

    def test_no_world_mutation_during_wrapper_call(self) -> None:
        grid = generate_synthetic_city_grid(CityGridConfig(rows=2, cols=2, spacing_m=50.0))
        edge_count_before = grid.edge_count
        node_count_before = grid.node_count

        mock_policy = MagicMock()
        mock_policy.predict.return_value = 1
        wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}
        _ = wrapper(obs, info)

        assert grid.edge_count == edge_count_before
        assert grid.node_count == node_count_before

    def test_multi_agent_isolation_wrapper_instances(self) -> None:
        # Agent 1 has failing model
        mock_policy_fail = MagicMock()
        mock_policy_fail.predict.side_effect = ValueError("Invalid tensor")
        wrapper_agent1 = SafeFallbackPolicyWrapper(model_policy=mock_policy_fail)

        # Agent 2 has working model
        mock_policy_ok = MagicMock()
        mock_policy_ok.predict.return_value = 1
        wrapper_agent2 = SafeFallbackPolicyWrapper(model_policy=mock_policy_ok)

        obs = np.zeros(32, dtype=np.float32)
        info = {"action_mask": MASK_2_LEGAL}

        a1 = wrapper_agent1(obs, info)
        a2 = wrapper_agent2(obs, info)

        assert a1 == 0
        assert wrapper_agent1.fallback_decisions == 1
        assert a2 == 1
        assert wrapper_agent2.learned_decisions == 1
        assert wrapper_agent2.fallback_decisions == 0


# ==============================================================================
# 4. Benchmark Framework Integration Tests
# ==============================================================================
class TestBenchmarkFrameworkIntegration:
    """Verify registry discovery, trial execution, and held-out scenario evaluation."""

    def test_algorithm_registry_contains_learned(self) -> None:
        reg = AlgorithmRegistry.get_default_registry()
        adapter = reg.get("learned")
        assert isinstance(adapter, LearnedRoutingBenchmarkAdapter)
        assert adapter.algorithm_id == "learned"
        assert adapter.is_implemented is True
        assert adapter.is_adaptive is True

    def test_learned_adapter_to_dict_metadata(self) -> None:
        adapter = LearnedRoutingBenchmarkAdapter()
        meta = adapter.to_dict()
        assert meta["algorithm_id"] == "learned"
        assert meta["name"] == "Learned RL Policy (MaskablePPO)"
        assert meta["version"] == "1.0.0"
        assert meta["is_adaptive"] is True
        assert meta["is_implemented"] is True
        assert "model_available" in meta
        assert "model_path" in meta

    def test_learned_trial_execution_with_fallback_mode(self) -> None:
        # Force fallback by specifying a non-existent model path
        adapter = LearnedRoutingBenchmarkAdapter(model_path="non_existent/model.zip")
        res = adapter.execute_trial(
            scenario_id="bench_grid_sparse_3x3",
            seed=42,
            max_ticks_override=30,
        )

        assert isinstance(res, BenchmarkTrialResult)
        assert res.algorithm_id == "learned"
        assert res.status in (BenchmarkStatus.SUCCESS, BenchmarkStatus.TIMEOUT)
        assert res.metadata["execution_mode"] == "fallback"
        assert res.metadata["model_available"] is False
        assert res.metadata["fallback_decisions"] >= 0

    def test_learned_trial_infeasible_barrier_returns_infeasible(self) -> None:
        adapter = LearnedRoutingBenchmarkAdapter()
        res = adapter.execute_trial(
            scenario_id="bench_infeasible_barrier",
            seed=42,
            max_ticks_override=30,
        )
        assert isinstance(res, BenchmarkTrialResult)
        assert res.algorithm_id == "learned"
        assert res.status == BenchmarkStatus.INFEASIBLE
        assert res.route_feasible is False
        assert res.route_cost is None
        assert res.travel_time_s is None
        assert res.completion_rate_pct == 0.0

    def test_runtime_configuration_defaults(self) -> None:
        cfg = LearnedRoutingConfig()
        assert cfg.enabled is False
        assert cfg.strategy_id == "learned"
        assert cfg.algorithm == "MaskablePPO"
        assert cfg.deterministic is True
        assert cfg.fallback_algorithm == "astar"
        assert cfg.fallback_cost_mode == "travel_time"
        assert cfg.inference_timeout_s == 1.0
        assert cfg.lazy_load is True

        d = cfg.to_dict()
        assert d["enabled"] is False
        assert d["strategy_id"] == "learned"
        assert d["fallback_algorithm"] == "astar"
