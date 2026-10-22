"""Inference policy wrapper for trained Reinforcement Learning models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from apps.core.rl.exceptions import RLEnvironmentError
from apps.core.rl.training.config import RLAlgorithm


class RLModelPolicy:
    """Policy wrapper for inference using trained Stable-Baselines3 or sb3-contrib models.

    Conforms to the callable protocol `(obs: np.ndarray, info: dict) -> int`
    compatible with `evaluate_rl_environment_episode`.
    """

    def __init__(
        self,
        model: Any,
        algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
        deterministic: bool = True,
        model_path: Optional[str] = None,
    ) -> None:
        self.model = model
        self.algorithm = algorithm
        self.deterministic = deterministic
        self.model_path = model_path

    def __call__(self, obs: np.ndarray, info: dict) -> int:
        """Select action using the trained model policy."""
        return self.predict(obs, info)

    def predict(self, obs: np.ndarray, info: Optional[dict] = None) -> int:
        """Predict the next discrete action given observation and optional info mask.

        Args:
            obs: 32-dim continuous observation vector.
            info: Step info dictionary optionally containing 'action_mask'.

        Returns:
            Integer action index in range [0, K].
        """
        action_mask: Optional[np.ndarray] = None
        if info and "action_mask" in info:
            action_mask = np.asarray(info["action_mask"], dtype=bool)

        try:
            if self.algorithm == RLAlgorithm.MASKABLE_PPO:
                action, _ = self.model.predict(
                    obs,
                    action_masks=action_mask,
                    deterministic=self.deterministic,
                )
            else:
                action, _ = self.model.predict(
                    obs,
                    deterministic=self.deterministic,
                )

            # Convert numpy scalar or 0-d array to standard python int
            if isinstance(action, np.ndarray):
                return int(action.item())
            return int(action)
        except Exception as exc:
            raise RLEnvironmentError(
                f"RLModelPolicy failed during inference: {exc}",
                cause=exc,
            ) from exc

    @classmethod
    def load(
        cls,
        model_path: Union[str, Path],
        algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
        device: str = "cpu",
        deterministic: bool = True,
    ) -> "RLModelPolicy":
        """Load a persisted model artifact from disk and wrap it in an inference policy.

        Args:
            model_path: Path to the .zip model artifact.
            algorithm: Algorithm used to train the model.
            device: Compute device ('cpu').
            deterministic: Whether to use deterministic action selection.

        Returns:
            RLModelPolicy instance.
        """
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"Model artifact not found at: {path.resolve()}")

        if algorithm == RLAlgorithm.MASKABLE_PPO:
            from sb3_contrib import MaskablePPO

            model = MaskablePPO.load(str(path), device=device)
        elif algorithm == RLAlgorithm.PPO:
            from stable_baselines3 import PPO

            model = PPO.load(str(path), device=device)
        else:
            raise ValueError(f"Unsupported algorithm for policy loading: {algorithm}")

        return cls(
            model=model,
            algorithm=algorithm,
            deterministic=deterministic,
            model_path=str(path.resolve()),
        )
