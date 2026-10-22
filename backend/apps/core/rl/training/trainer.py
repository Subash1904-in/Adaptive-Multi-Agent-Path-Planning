"""Reinforcement Learning baseline training pipeline for AMAPP."""

from __future__ import annotations

import json
import platform
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3.common.callbacks import BaseCallback

from apps.core.rl.config import SingleAgentRLConfig
from apps.core.rl.env import AMAPPSingleAgentEnv
from apps.core.rl.exceptions import RLEnvironmentError
from apps.core.rl.training.config import RLAlgorithm, RLTrainingConfig


@dataclass
class TrainingResult:
    """Encapsulates outcomes and metrics from a completed RL training run."""

    run_name: str
    algorithm: str
    scenario_id: str
    train_seed: int
    total_timesteps: int
    elapsed_time_s: float
    model_path: str
    metadata_path: str
    final_loss: Optional[float] = None
    final_policy_loss: Optional[float] = None
    final_value_loss: Optional[float] = None
    final_entropy_loss: Optional[float] = None
    checkpoints: list[str] = field(default_factory=list)
    training_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert result dataclass to dictionary."""
        return asdict(self)


class MetricsAndCheckpointCallback(BaseCallback):
    """Custom callback tracking loss diagnostics and checkpointing during training."""

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        checkpoint_freq: int = 0,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_freq = checkpoint_freq
        self.checkpoints: list[str] = []
        self.metrics_history: dict[str, list[float]] = {}
        self._last_checkpoint_step = 0

    def _on_step(self) -> bool:
        if self.checkpoint_freq > 0 and self.checkpoint_dir:
            steps_since = self.num_timesteps - self._last_checkpoint_step
            if steps_since >= self.checkpoint_freq:
                ckpt_path = self.checkpoint_dir / f"checkpoint_{self.num_timesteps}.zip"
                self.model.save(str(ckpt_path))
                self.checkpoints.append(str(ckpt_path))
                self._last_checkpoint_step = self.num_timesteps
        return True

    def _on_rollout_end(self) -> None:
        """Capture logger metrics after rollout update."""
        if hasattr(self.logger, "name_to_value"):
            for name, val in self.logger.name_to_value.items():
                if name not in self.metrics_history:
                    self.metrics_history[name] = []
                self.metrics_history[name].append(float(val))

    def get_latest_metric(self, name: str) -> Optional[float]:
        """Retrieve most recent value for a named training metric."""
        history = self.metrics_history.get(name)
        if history:
            return history[-1]
        return None


class RLBaselineTrainer:
    """Executes reproducible baseline training runs for AMAPP routing."""

    def __init__(self, config: Optional[RLTrainingConfig] = None) -> None:
        self.config = config or RLTrainingConfig()

    def train(self) -> TrainingResult:
        """Execute the full training pipeline, persisting model and metadata artifacts.

        Returns:
            TrainingResult capturing model artifacts and recorded metrics.
        """
        run_dir = self.config.get_run_output_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        checkpoints_dir = run_dir / "checkpoints"
        if self.config.checkpoint_freq > 0:
            checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # 1. Deterministic Seeding across all active libraries
        seed = self.config.train_seed
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        # 2. Instantiate and validate AMAPPSingleAgentEnv
        env_config = SingleAgentRLConfig(
            scenario_id=self.config.scenario_id,
            decision_interval_ticks=self.config.decision_interval_ticks,
            max_steps=self.config.max_steps,
        )
        env = AMAPPSingleAgentEnv(config=env_config)

        # 3. Instantiate chosen algorithm
        algorithm_choice = self.config.algorithm
        model: Any = None

        if algorithm_choice == RLAlgorithm.MASKABLE_PPO:
            from sb3_contrib import MaskablePPO

            model = MaskablePPO(
                policy=self.config.policy_type,
                env=env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                batch_size=self.config.batch_size,
                n_epochs=self.config.n_epochs,
                gamma=self.config.gamma,
                clip_range=self.config.clip_range,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                seed=seed,
                device=self.config.device,
                verbose=self.config.verbose,
            )
        elif algorithm_choice == RLAlgorithm.PPO:
            from stable_baselines3 import PPO

            model = PPO(
                policy=self.config.policy_type,
                env=env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                batch_size=self.config.batch_size,
                n_epochs=self.config.n_epochs,
                gamma=self.config.gamma,
                clip_range=self.config.clip_range,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                seed=seed,
                device=self.config.device,
                verbose=self.config.verbose,
            )
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm_choice}")

        # 4. Setup callback and execute optimization
        callback = MetricsAndCheckpointCallback(
            checkpoint_dir=checkpoints_dir if self.config.checkpoint_freq > 0 else None,
            checkpoint_freq=self.config.checkpoint_freq,
            verbose=self.config.verbose,
        )

        t_start = time.perf_counter()
        try:
            model.learn(
                total_timesteps=self.config.total_timesteps,
                callback=callback,
                reset_num_timesteps=True,
            )
        except Exception as exc:
            env.close()
            raise RLEnvironmentError(
                f"Training failed during model.learn: {exc}",
                cause=exc,
            ) from exc
        finally:
            env.close()

        elapsed_time_s = time.perf_counter() - t_start

        # 5. Persist final model artifact
        final_model_path = run_dir / "final_model.zip"
        model.save(str(final_model_path))

        # 6. Extract recorded training loss diagnostics
        final_loss = callback.get_latest_metric("train/loss")
        final_policy_loss = callback.get_latest_metric("train/policy_gradient_loss")
        final_value_loss = callback.get_latest_metric("train/value_loss")
        final_entropy_loss = callback.get_latest_metric("train/entropy_loss")

        # 7. Write comprehensive metadata manifest
        import stable_baselines3

        sb3_version = stable_baselines3.__version__
        metadata = {
            "run_name": self.config.run_name,
            "algorithm": self.config.algorithm.value,
            "scenario_id": self.config.scenario_id,
            "train_seed": self.config.train_seed,
            "total_timesteps": self.config.total_timesteps,
            "elapsed_time_s": elapsed_time_s,
            "hyperparameters": self.config.to_dict(),
            "diagnostics": {
                "final_loss": final_loss,
                "final_policy_loss": final_policy_loss,
                "final_value_loss": final_value_loss,
                "final_entropy_loss": final_entropy_loss,
            },
            "metrics_history": callback.metrics_history,
            "checkpoints": callback.checkpoints,
            "final_model_path": str(final_model_path.resolve()),
            "environment_info": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "numpy_version": np.__version__,
                "torch_version": torch.__version__,
                "gymnasium_version": gym.__version__,
                "stable_baselines3_version": sb3_version,
            },
        }

        metadata_path = run_dir / "training_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return TrainingResult(
            run_name=self.config.run_name,
            algorithm=self.config.algorithm.value,
            scenario_id=self.config.scenario_id,
            train_seed=self.config.train_seed,
            total_timesteps=self.config.total_timesteps,
            elapsed_time_s=elapsed_time_s,
            model_path=str(final_model_path.resolve()),
            metadata_path=str(metadata_path.resolve()),
            final_loss=final_loss,
            final_policy_loss=final_policy_loss,
            final_value_loss=final_value_loss,
            final_entropy_loss=final_entropy_loss,
            checkpoints=callback.checkpoints,
            training_metrics=callback.metrics_history,
        )
