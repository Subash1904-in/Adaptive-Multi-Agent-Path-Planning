"""Automated tests for RL baseline training, model persistence, and evaluation (Phase 33)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import gymnasium as gym
import numpy as np
import pytest
import torch
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.benchmarking.adapters import LearnedRoutingBenchmarkAdapter
from apps.core.rl.env import AMAPPSingleAgentEnv
from apps.core.rl.exceptions import RLEnvironmentError
from apps.core.rl.training.config import (
    RLAlgorithm,
    RLTrainingConfig,
    create_smoke_training_config,
)
from apps.core.rl.training.evaluator import (
    EvaluationReport,
    RLBaselineEvaluator,
)
from apps.core.rl.training.policy import RLModelPolicy
from apps.core.rl.training.trainer import (
    RLBaselineTrainer,
    TrainingResult,
)


# ==============================================================================
# 1. Dependency & Configuration Tests
# ==============================================================================
class TestRLTrainingDependenciesAndConfig:
    """Verify library imports and Pydantic configuration validation."""

    def test_training_dependencies_import(self) -> None:
        import sb3_contrib
        import stable_baselines3

        assert stable_baselines3.__version__ is not None
        assert sb3_contrib.__version__ is not None
        assert torch.__version__ is not None
        assert gym.__version__ is not None
        assert np.__version__ is not None

    def test_training_config_defaults(self) -> None:
        cfg = RLTrainingConfig()
        assert cfg.algorithm == RLAlgorithm.MASKABLE_PPO
        assert cfg.scenario_id == "bench_grid_sparse_3x3"
        assert cfg.train_seed == 42
        assert cfg.device == "cpu"
        assert cfg.batch_size <= cfg.n_steps
        assert cfg.train_seed not in cfg.eval_seeds

    def test_training_config_validation_timesteps(self) -> None:
        with pytest.raises(ValueError, match="total_timesteps must be positive"):
            RLTrainingConfig(total_timesteps=0)

    def test_training_config_validation_batch_size(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed n_steps"):
            RLTrainingConfig(batch_size=256, n_steps=64)

    def test_training_config_validation_gamma(self) -> None:
        with pytest.raises(ValueError, match="gamma must be in"):
            RLTrainingConfig(gamma=1.5)

    def test_training_config_validation_learning_rate(self) -> None:
        with pytest.raises(ValueError, match="learning_rate must be positive"):
            RLTrainingConfig(learning_rate=-0.001)

    def test_training_config_held_out_seed_isolation(self) -> None:
        with pytest.raises(ValueError, match="must not contain train_seed"):
            RLTrainingConfig(train_seed=42, eval_seeds=[42, 101])

    def test_smoke_config_factory(self, tmp_path: Path) -> None:
        smoke = create_smoke_training_config(
            run_name="smoke_test",
            output_dir=str(tmp_path),
            seed=99,
        )
        assert smoke.total_timesteps == 64
        assert smoke.train_seed == 99
        assert smoke.eval_seeds == [199]
        assert smoke.device == "cpu"
        assert Path(smoke.output_dir) == tmp_path


# ==============================================================================
# 2. Training Pipeline & Model Persistence Tests
# ==============================================================================
class TestRLTrainingPipeline:
    """Verify training loop, checkpointing, and model reload functionality."""

    def test_smoke_training_run_creates_valid_artifacts(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="unit_smoke_run",
            output_dir=str(tmp_path),
            seed=42,
        )
        trainer = RLBaselineTrainer(cfg)
        result = trainer.train()

        assert isinstance(result, TrainingResult)
        assert result.total_timesteps == 64
        assert result.elapsed_time_s > 0.0

        model_file = Path(result.model_path)
        metadata_file = Path(result.metadata_path)
        assert model_file.is_file(), f"Model file missing: {model_file}"
        assert metadata_file.is_file(), f"Metadata file missing: {metadata_file}"

        with open(metadata_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["run_name"] == "unit_smoke_run"
        assert meta["train_seed"] == 42
        assert "environment_info" in meta
        assert meta["environment_info"]["torch_version"] == torch.__version__

    def test_checkpoints_saved_when_frequency_configured(self, tmp_path: Path) -> None:
        cfg = RLTrainingConfig(
            run_name="checkpoint_test_run",
            output_dir=str(tmp_path),
            total_timesteps=128,
            n_steps=64,
            batch_size=32,
            checkpoint_freq=64,
            train_seed=42,
            eval_seeds=[101],
        )
        trainer = RLBaselineTrainer(cfg)
        result = trainer.train()

        assert len(result.checkpoints) >= 1
        for ckpt in result.checkpoints:
            assert Path(ckpt).is_file()

    def test_model_reload_and_inference(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="reload_test_run",
            output_dir=str(tmp_path),
            seed=42,
        )
        trainer = RLBaselineTrainer(cfg)
        result = trainer.train()

        policy = RLModelPolicy.load(
            model_path=result.model_path,
            algorithm=cfg.algorithm,
            device="cpu",
        )

        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=101)
        action = policy(obs, info)

        assert isinstance(action, int)
        assert env.action_space.contains(action)
        assert info["action_mask"][action] is True or info["action_mask"][action] == 1

    def test_model_deterministic_inference(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="determ_infer_run",
            output_dir=str(tmp_path),
            seed=42,
        )
        trainer = RLBaselineTrainer(cfg)
        result = trainer.train()

        policy = RLModelPolicy.load(result.model_path, algorithm=cfg.algorithm)
        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=102)

        a1 = policy.predict(obs, info)
        a2 = policy.predict(obs, info)
        assert a1 == a2

    def test_missing_model_file_raises_error(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "non_existent.zip"
        with pytest.raises(FileNotFoundError, match="Model artifact not found"):
            RLModelPolicy.load(missing_path)

    def test_trainer_handles_error_and_cleans_up(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="error_test_run",
            output_dir=str(tmp_path),
        )
        trainer = RLBaselineTrainer(cfg)
        with patch(
            "sb3_contrib.MaskablePPO.learn",
            side_effect=RuntimeError("Simulated Learn Crash"),
        ):
            with pytest.raises(RLEnvironmentError, match="Training failed during model.learn"):
                trainer.train()


# ==============================================================================
# 3. Held-Out Evaluation & Baseline Comparison Tests
# ==============================================================================
class TestRLBaselineEvaluator:
    """Verify evaluation across held-out seeds, baseline comparisons, and report generation."""

    def test_evaluator_held_out_evaluation(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="eval_test_run",
            output_dir=str(tmp_path),
            seed=42,
        )
        trainer = RLBaselineTrainer(cfg)
        train_res = trainer.train()

        evaluator = RLBaselineEvaluator(cfg)
        report = evaluator.evaluate(
            trained_policy=train_res.model_path,
            eval_seeds=[101, 102],
            eval_scenarios=["bench_grid_sparse_3x3"],
            save_report=True,
        )

        assert isinstance(report, EvaluationReport)
        assert report.train_seed == 42
        assert report.eval_seeds == [101, 102]
        assert len(report.summaries) == 3  # learned, greedy, random

        # Verify artifacts persisted
        report_json = Path(cfg.output_dir) / cfg.run_name / "evaluation_report.json"
        report_md = Path(cfg.output_dir) / cfg.run_name / "evaluation_summary.md"
        assert report_json.is_file()
        assert report_md.is_file()

        with open(report_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["run_name"] == "eval_test_run"
        assert len(data["summaries"]) == 3

    def test_evaluation_summary_metrics_validity(self, tmp_path: Path) -> None:
        cfg = create_smoke_training_config(
            run_name="metrics_val_run",
            output_dir=str(tmp_path),
            seed=42,
        )
        trainer = RLBaselineTrainer(cfg)
        train_res = trainer.train()

        evaluator = RLBaselineEvaluator(cfg)
        report = evaluator.evaluate(
            trained_policy=train_res.model_path,
            eval_seeds=[103],
            eval_scenarios=["bench_grid_sparse_3x3"],
            save_report=False,
        )

        for s in report.summaries:
            assert s.total_trials == 1
            assert 0.0 <= s.completion_rate_pct <= 100.0
            assert s.total_collisions >= 0
            assert s.mean_planning_duration_ms >= 0.0
            if s.completion_rate_pct > 0.0:
                assert s.mean_travel_time_s is not None
                assert s.mean_travel_time_s > 0.0


# ==============================================================================
# 4. Management Command Tests
# ==============================================================================
class TestRLManagementCommand:
    """Verify train_rl_baseline CLI execution modes."""

    def test_management_command_smoke(self, tmp_path: Path) -> None:
        call_command(
            "train_rl_baseline",
            smoke=True,
            output_dir=str(tmp_path),
            seed=42,
        )
        smoke_dir = tmp_path / "smoke_training_run"
        assert (smoke_dir / "final_model.zip").is_file()
        assert (smoke_dir / "training_metadata.json").is_file()
        assert (smoke_dir / "evaluation_report.json").is_file()

    def test_management_command_eval_only_missing_path(self) -> None:
        with pytest.raises(CommandError, match="--model-path is required"):
            call_command("train_rl_baseline", eval_only=True)

    def test_management_command_eval_only_success(self, tmp_path: Path) -> None:
        # First train a smoke model
        call_command(
            "train_rl_baseline",
            smoke=True,
            output_dir=str(tmp_path),
            seed=42,
        )
        model_path = tmp_path / "smoke_training_run" / "final_model.zip"

        # Now evaluate the model with --eval-only
        call_command(
            "train_rl_baseline",
            eval_only=True,
            model_path=str(model_path),
            eval_seeds="105",
            eval_scenarios="bench_grid_sparse_3x3",
            output_dir=str(tmp_path),
            run_name="eval_test_only",
        )
        eval_report = tmp_path / "eval_test_only" / "evaluation_report.json"
        assert eval_report.is_file()


# ==============================================================================
# 5. Production Isolation & Regression Tests
# ==============================================================================
class TestProductionIsolationAndRegressions:
    """Ensure baseline routing interfaces and production boundaries remain uncompromised."""

    def test_learned_routing_adapter_is_implemented(self) -> None:
        adapter = LearnedRoutingBenchmarkAdapter()
        assert adapter.algorithm_id == "learned"
        assert adapter.is_implemented is True

    def test_gymnasium_env_checker_preserved(self) -> None:
        from gymnasium.utils.env_checker import check_env

        env = AMAPPSingleAgentEnv()
        check_env(env)

    def test_phase31_benchmark_smoke_command_preserved(self) -> None:
        # Run benchmark smoke command verifying Phase 31 compatibility
        call_command("run_benchmark", smoke=True)
