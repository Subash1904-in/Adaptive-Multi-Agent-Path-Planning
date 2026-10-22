"""Configuration models and hyperparameters for RL baseline training."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RLAlgorithm(str, Enum):
    """Supported reinforcement learning baseline algorithms."""

    MASKABLE_PPO = "MaskablePPO"
    PPO = "PPO"


class RLTrainingConfig(BaseModel):
    """Hyperparameters and execution configuration for RL baseline training."""

    run_name: str = Field(
        default="baseline_maskable_ppo",
        description="Unique identifier for the training run and artifact subfolder.",
    )
    algorithm: RLAlgorithm = Field(
        default=RLAlgorithm.MASKABLE_PPO,
        description="Algorithm choice: MaskablePPO (with action masking) or standard PPO.",
    )
    policy_type: str = Field(
        default="MlpPolicy",
        description="Neural network policy architecture (e.g. MlpPolicy).",
    )
    scenario_id: str = Field(
        default="bench_grid_sparse_3x3",
        description="Standardized scenario ID from BenchmarkScenarioRegistry used for training.",
    )
    train_seed: int = Field(
        default=42,
        description="Deterministic base random seed for environment and policy initialization.",
    )
    eval_seeds: list[int] = Field(
        default_factory=lambda: [101, 102, 103, 104, 105],
        description="Distinct held-out random seeds used for post-training evaluation.",
    )
    eval_scenarios: list[str] = Field(
        default_factory=lambda: ["bench_grid_sparse_3x3", "bench_incident_closure"],
        description="Scenarios evaluated post-training to verify generalization.",
    )
    total_timesteps: int = Field(
        default=2048,
        description="Total environment transition timesteps for the training run.",
    )
    learning_rate: float = Field(
        default=3e-4,
        description="Adam optimizer learning rate.",
    )
    gamma: float = Field(
        default=0.99,
        description="Discount factor for future rewards.",
    )
    n_steps: int = Field(
        default=128,
        description="Number of environment steps per rollout buffer before policy update.",
    )
    batch_size: int = Field(
        default=64,
        description="Minibatch size for PPO gradient updates.",
    )
    n_epochs: int = Field(
        default=4,
        description="Number of optimization epochs per rollout buffer.",
    )
    clip_range: float = Field(
        default=0.2,
        description="PPO policy surrogate clipping parameter epsilon.",
    )
    ent_coef: float = Field(
        default=0.01,
        description="Entropy loss bonus coefficient to promote exploration.",
    )
    vf_coef: float = Field(
        default=0.5,
        description="Value function loss coefficient in the combined objective.",
    )
    max_grad_norm: float = Field(
        default=0.5,
        description="Maximum gradient norm for gradient clipping.",
    )
    decision_interval_ticks: int = Field(
        default=5,
        description="Authoritative simulation ticks advanced per RL decision step (0.5s).",
    )
    max_steps: int = Field(
        default=200,
        description="Maximum RL decision steps before episode truncation.",
    )
    checkpoint_freq: int = Field(
        default=1024,
        description="Timestep interval for saving intermediate model checkpoints (0 to disable).",
    )
    output_dir: str = Field(
        default="artifacts/rl_models",
        description="Root artifact directory for saving model checkpoints and reports.",
    )
    device: str = Field(
        default="cpu",
        description="PyTorch compute device ('cpu' strictly guaranteed in CI).",
    )
    verbose: int = Field(
        default=0,
        description="Verbosity level for Stable-Baselines3 logger (0=silent, 1=info).",
    )

    @field_validator("total_timesteps")
    @classmethod
    def validate_timesteps(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"total_timesteps must be positive, got {v}")
        return v

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"batch_size must be positive, got {v}")
        return v

    @field_validator("gamma")
    @classmethod
    def validate_gamma(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError(f"gamma must be in (0.0, 1.0], got {v}")
        return v

    @field_validator("learning_rate")
    @classmethod
    def validate_lr(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"learning_rate must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def validate_batch_and_steps(self) -> "RLTrainingConfig":
        if self.batch_size > self.n_steps:
            raise ValueError(
                f"batch_size ({self.batch_size}) cannot exceed n_steps ({self.n_steps})"
            )
        if self.train_seed in self.eval_seeds:
            raise ValueError(
                f"Evaluation seeds {self.eval_seeds} must not contain "
                f"train_seed ({self.train_seed}) to ensure held-out validation integrity."
            )
        return self

    def get_run_output_dir(self) -> Path:
        """Resolve path to this run's artifact directory."""
        return Path(self.output_dir) / self.run_name

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to serialized dictionary."""
        return self.model_dump()


def create_smoke_training_config(
    run_name: str = "smoke_training_run",
    output_dir: str = "artifacts/rl_models",
    algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
    seed: int = 42,
) -> RLTrainingConfig:
    """Create a bounded, minimal training configuration suitable for fast CI verification."""
    return RLTrainingConfig(
        run_name=run_name,
        algorithm=algorithm,
        scenario_id="bench_grid_sparse_3x3",
        train_seed=seed,
        eval_seeds=[seed + 100],
        eval_scenarios=["bench_grid_sparse_3x3"],
        total_timesteps=64,
        n_steps=64,
        batch_size=32,
        n_epochs=1,
        decision_interval_ticks=5,
        max_steps=50,
        checkpoint_freq=0,
        output_dir=output_dir,
        device="cpu",
        verbose=0,
    )
