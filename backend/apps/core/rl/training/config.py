"""Configuration models and hyperparameters for RL baseline training."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RLAlgorithm(str, Enum):
    """Supported reinforcement learning baseline algorithms."""

    MASKABLE_PPO = "MaskablePPO"
    PPO = "PPO"


@dataclass
class RLTrainingConfig:
    """Hyperparameters and execution configuration for RL baseline training."""

    run_name: str = "baseline_maskable_ppo"
    algorithm: RLAlgorithm | str = RLAlgorithm.MASKABLE_PPO
    policy_type: str = "MlpPolicy"
    scenario_id: str = "bench_grid_sparse_3x3"
    train_seed: int = 42
    eval_seeds: list[int] = field(default_factory=lambda: [101, 102, 103, 104, 105])
    eval_scenarios: list[str] = field(
        default_factory=lambda: ["bench_grid_sparse_3x3", "bench_incident_closure"]
    )
    total_timesteps: int = 2048
    learning_rate: float = 3e-4
    gamma: float = 0.99
    n_steps: int = 128
    batch_size: int = 64
    n_epochs: int = 4
    clip_range: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    decision_interval_ticks: int = 5
    max_steps: int = 200
    checkpoint_freq: int = 1024
    output_dir: str = "artifacts/rl_models"
    device: str = "cpu"
    verbose: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.algorithm, str):
            norm = self.algorithm.strip().lower()
            if norm in ("maskableppo", "maskable_ppo"):
                self.algorithm = RLAlgorithm.MASKABLE_PPO
            elif norm == "ppo":
                self.algorithm = RLAlgorithm.PPO

        if self.total_timesteps <= 0:
            raise ValueError(f"total_timesteps must be positive, got {self.total_timesteps}")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")
        if not (0.0 < self.gamma <= 1.0):
            raise ValueError(f"gamma must be in (0.0, 1.0], got {self.gamma}")
        if self.learning_rate <= 0.0:
            raise ValueError(f"learning_rate must be positive, got {self.learning_rate}")
        if self.batch_size > self.n_steps:
            raise ValueError(
                f"batch_size ({self.batch_size}) cannot exceed n_steps ({self.n_steps})"
            )
        if self.train_seed in self.eval_seeds:
            raise ValueError(
                f"Evaluation seeds {self.eval_seeds} must not contain "
                f"train_seed ({self.train_seed}) to ensure held-out validation integrity."
            )

    def get_run_output_dir(self) -> Path:
        """Resolve path to this run's artifact directory."""
        return Path(self.output_dir) / self.run_name

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to serialized dictionary."""
        d = asdict(self)
        if isinstance(self.algorithm, RLAlgorithm):
            d["algorithm"] = self.algorithm.value
        return d


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
