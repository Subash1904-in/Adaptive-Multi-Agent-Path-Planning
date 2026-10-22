"""Model artifact discovery, validation, caching, and lifecycle management for RL policies."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from gymnasium import spaces

from apps.core.rl.exceptions import RLEnvironmentError
from apps.core.rl.training.config import RLAlgorithm
from apps.core.rl.training.policy import RLModelPolicy

logger = logging.getLogger(__name__)


class ModelArtifactError(RLEnvironmentError):
    """Base exception for RL model artifact discovery, validation, or loading failures."""

    def __init__(
        self,
        message: str,
        model_path: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.model_path = model_path


class ModelArtifactNotFoundError(ModelArtifactError):
    """Raised when the specified or discovered model artifact file does not exist."""

    pass


class CorruptModelArtifactError(ModelArtifactError):
    """Raised when the model artifact file is damaged, unreadable, or not a valid zip archive."""

    pass


class IncompatibleModelArtifactError(ModelArtifactError):
    """Raised when model observation space, action space, or algorithm mismatches requirements."""

    pass


@dataclass(frozen=True)
class ModelValidationResult:
    """Immutable audit report summarizing model validation and compatibility inspection."""

    is_valid: bool
    model_path: str
    algorithm: Optional[str] = None
    observation_shape: Optional[tuple[int, ...]] = None
    action_space_size: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to JSON-serializable dictionary."""
        return {
            "is_valid": self.is_valid,
            "model_path": self.model_path,
            "algorithm": self.algorithm,
            "observation_shape": list(self.observation_shape) if self.observation_shape else None,
            "action_space_size": self.action_space_size,
            "metadata": dict(self.metadata),
            "error_message": self.error_message,
        }


def _get_project_root() -> Path:
    """Resolve the repository root directory regardless of current working directory."""
    # backend/apps/core/rl/model_manager.py -> parents[4] is repo root
    current_file = Path(__file__).resolve()
    # Path parents: 0=rl, 1=core, 2=apps, 3=backend, 4=repo root
    if len(current_file.parents) >= 5:
        return current_file.parents[4]
    return Path.cwd()


def is_safe_contained_path(path: Union[str, Path]) -> bool:
    """Verify path is contained within approved project, working, or temp directories."""
    try:
        resolved = Path(path).resolve()
        approved_roots = [
            _get_project_root().resolve(),
            Path.cwd().resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]
        return any(resolved.is_relative_to(root) for root in approved_roots)
    except (ValueError, AttributeError, OSError):
        return False


def resolve_model_artifact_path(
    configured_path: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Discover and resolve model artifact file without developer-specific hardcoding.

    Search hierarchy:
    1. Explicit `configured_path` argument.
    2. Environment variable `AMAPP_RL_MODEL_PATH`.
    3. Default artifact candidates relative to cwd and project root:
       - `artifacts/rl_models/maskableppo_bench_grid_sparse_3x3_s42/final_model.zip`
       - `artifacts/rl_models/smoke_training_run/final_model.zip`

    Returns:
        Resolved absolute Path if readable file is found in project bounds, else None.
    """
    candidates: list[Path] = []
    root = _get_project_root()
    cwd = Path.cwd().resolve()

    # 1. Explicit configured path takes strict priority
    if configured_path is not None:
        p = Path(configured_path)
        if not p.is_absolute():
            candidates = [cwd / p, root / p]
        else:
            candidates = [p]
        for cand in candidates:
            try:
                cand_resolved = cand.resolve()
                if not is_safe_contained_path(cand_resolved):
                    logger.warning("Rejecting unsafe path outside approved root: %s", cand)
                    continue
                if cand_resolved.is_file() and os.access(cand_resolved, os.R_OK):
                    return cand_resolved
            except (OSError, PermissionError):
                continue
        return None

    # 2. Environment variable
    env_path = os.environ.get("AMAPP_RL_MODEL_PATH")
    if env_path:
        p = Path(env_path.strip())
        if not p.is_absolute():
            candidates = [cwd / p, root / p]
        else:
            candidates = [p]
        for cand in candidates:
            try:
                cand_resolved = cand.resolve()
                if not is_safe_contained_path(cand_resolved):
                    logger.warning("Rejecting unsafe path outside approved root: %s", cand)
                    continue
                if cand_resolved.is_file() and os.access(cand_resolved, os.R_OK):
                    return cand_resolved
            except (OSError, PermissionError):
                continue
        return None

    # 3. Standard default relative paths
    default_rels = [
        Path("artifacts/rl_models/maskableppo_bench_grid_sparse_3x3_s42/final_model.zip"),
        Path("artifacts/rl_models/smoke_training_run/final_model.zip"),
    ]
    candidates = []
    for rel in default_rels:
        candidates.append(cwd / rel)
        candidates.append(root / rel)

    for cand in candidates:
        try:
            cand_resolved = cand.resolve()
            if not is_safe_contained_path(cand_resolved):
                continue
            if cand_resolved.is_file() and os.access(cand_resolved, os.R_OK):
                return cand_resolved
        except (OSError, PermissionError):
            continue

    return None


def validate_model_artifact(
    model_path: Union[str, Path],
    expected_obs_dim: int = 32,
    expected_actions: int = 9,
    algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
    raise_on_error: bool = False,
) -> ModelValidationResult:
    """Validate model artifact existence, format, spaces, and compatibility.

    Args:
        model_path: Path to the .zip model artifact.
        expected_obs_dim: Required continuous observation dimension (default: 32).
        expected_actions: Required discrete action space size (default: 9).
        algorithm: Expected RL algorithm enum.
        raise_on_error: Whether to raise structured exception instead of returning invalid result.

    Returns:
        ModelValidationResult describing validation status and extracted metadata.

    Raises:
        ModelArtifactNotFoundError: If file does not exist.
        CorruptModelArtifactError: If file is not a valid zip archive or is damaged.
        IncompatibleModelArtifactError: If spaces or algorithm mismatch.
    """
    path = Path(model_path).resolve()
    path_str = str(path)

    # 0. Path traversal and approved root containment check
    if not is_safe_contained_path(path):
        msg = f"Model artifact path is outside approved project directory: '{path_str}'"
        if raise_on_error:
            raise ModelArtifactError(msg, model_path=path_str)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            error_message=msg,
        )

    # 1. Existence and readability check
    if not path.is_file():
        msg = f"Model artifact file does not exist: '{path_str}'"
        if raise_on_error:
            raise ModelArtifactNotFoundError(msg, model_path=path_str)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            error_message=msg,
        )

    # 2. Zip archive format and integrity check
    if not zipfile.is_zipfile(path):
        msg = f"Model artifact is not a valid zip archive: '{path_str}'"
        if raise_on_error:
            raise CorruptModelArtifactError(msg, model_path=path_str)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            error_message=msg,
        )

    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                msg = f"Corrupt entry detected in model zip archive '{path_str}': {bad_file}"
                if raise_on_error:
                    raise CorruptModelArtifactError(msg, model_path=path_str)
                return ModelValidationResult(
                    is_valid=False,
                    model_path=path_str,
                    error_message=msg,
                )
            namelist = zf.namelist()
            for entry_name in namelist:
                if (
                    ".." in entry_name
                    or entry_name.startswith(("/", "\\"))
                    or (len(entry_name) > 1 and entry_name[1] == ":")
                ):
                    msg = (
                        f"Zip slip / unsafe path traversal detected in model archive '{path_str}': "
                        f"{entry_name}"
                    )
                    if raise_on_error:
                        raise CorruptModelArtifactError(msg, model_path=path_str)
                    return ModelValidationResult(
                        is_valid=False,
                        model_path=path_str,
                        error_message=msg,
                    )
            if "data" not in namelist:
                msg = f"Model artifact missing SB3 serialization entry 'data': '{path_str}'"
                if raise_on_error:
                    raise CorruptModelArtifactError(msg, model_path=path_str)
                return ModelValidationResult(
                    is_valid=False,
                    model_path=path_str,
                    error_message=msg,
                )
    except Exception as exc:
        msg = f"Failed to inspect zip archive '{path_str}': {exc}"
        if raise_on_error:
            raise CorruptModelArtifactError(msg, model_path=path_str, cause=exc)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            error_message=msg,
        )

    # 3. Provenance and training metadata check if present
    metadata: dict[str, Any] = {}
    meta_path = path.parent / "training_metadata.json"
    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as exc:
            logger.warning(f"Could not read metadata at '{meta_path}': {exc}")

    # 4. Model loading and observation/action space verification
    try:
        policy = RLModelPolicy.load(
            model_path=path,
            algorithm=algorithm,
            device="cpu",
            deterministic=True,
        )
        loaded_model = policy.model
    except Exception as exc:
        msg = f"Failed to load model policy with algorithm '{algorithm.value}': {exc}"
        if raise_on_error:
            raise IncompatibleModelArtifactError(msg, model_path=path_str, cause=exc)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            metadata=metadata,
            error_message=msg,
        )

    # Validate observation space
    obs_space = getattr(loaded_model, "observation_space", None)
    if not isinstance(obs_space, spaces.Box) or obs_space.shape != (expected_obs_dim,):
        msg = (
            f"Observation space mismatch for '{path_str}': expected Box({expected_obs_dim},), "
            f"got {obs_space}"
        )
        if raise_on_error:
            raise IncompatibleModelArtifactError(msg, model_path=path_str)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            algorithm=algorithm.value,
            observation_shape=obs_space.shape if obs_space else None,
            metadata=metadata,
            error_message=msg,
        )

    # Validate action space
    act_space = getattr(loaded_model, "action_space", None)
    if not isinstance(act_space, spaces.Discrete) or act_space.n != expected_actions:
        msg = (
            f"Action space mismatch for '{path_str}': expected Discrete({expected_actions}), "
            f"got {act_space}"
        )
        if raise_on_error:
            raise IncompatibleModelArtifactError(msg, model_path=path_str)
        return ModelValidationResult(
            is_valid=False,
            model_path=path_str,
            algorithm=algorithm.value,
            observation_shape=obs_space.shape,
            action_space_size=act_space.n if act_space else None,
            metadata=metadata,
            error_message=msg,
        )

    return ModelValidationResult(
        is_valid=True,
        model_path=path_str,
        algorithm=algorithm.value,
        observation_shape=obs_space.shape,
        action_space_size=act_space.n,
        metadata=metadata,
        error_message=None,
    )


class RLModelManager:
    """Thread-safe cached manager orchestrating RL model discovery, validation, and lifecycle.

    Prevents repetitive deserialization of heavy neural network models across vehicle decisions
    while providing thread safety and deterministic reload mechanics.
    """

    _instance: Optional["RLModelManager"] = None
    _global_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._cache: dict[str, tuple[RLModelPolicy, ModelValidationResult]] = {}
        self._lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "RLModelManager":
        """Retrieve the process-level singleton instance."""
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def clear_cache(self) -> None:
        """Evict all cached models and force subsequent calls to reload."""
        with self._lock:
            self._cache.clear()

    def is_model_available(
        self,
        model_path: Optional[Union[str, Path]] = None,
        algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
    ) -> bool:
        """Check whether a verified model artifact exists without throwing exceptions."""
        resolved = resolve_model_artifact_path(model_path)
        if resolved is None:
            return False
        with self._lock:
            key = f"{str(resolved)}:{algorithm.value}"
            if key in self._cache and self._cache[key][1].is_valid:
                return True
        val = validate_model_artifact(resolved, algorithm=algorithm, raise_on_error=False)
        return val.is_valid

    def get_policy(
        self,
        model_path: Optional[Union[str, Path]] = None,
        algorithm: RLAlgorithm = RLAlgorithm.MASKABLE_PPO,
        deterministic: bool = True,
        reload: bool = False,
        raise_on_error: bool = False,
    ) -> tuple[Optional[RLModelPolicy], ModelValidationResult]:
        """Retrieve cached model policy or load and validate a newly discovered artifact.

        Args:
            model_path: Optional explicit path. If omitted, uses discovery resolution.
            algorithm: Algorithm enum (default: MaskablePPO).
            deterministic: Deterministic inference flag.
            reload: If True, bypass cache and reload from disk.
            raise_on_error: If True, raise structured ModelArtifactError on validation failure.

        Returns:
            Tuple of (RLModelPolicy or None, ModelValidationResult).
        """
        resolved = resolve_model_artifact_path(model_path)
        if resolved is None:
            msg = f"No model artifact could be found for path: '{model_path}'"
            if raise_on_error:
                err_path = str(model_path) if model_path else None
                raise ModelArtifactNotFoundError(msg, model_path=err_path)
            return None, ModelValidationResult(
                is_valid=False,
                model_path=str(model_path) if model_path else "unresolved",
                error_message=msg,
            )

        cache_key = f"{str(resolved)}:{algorithm.value}:{deterministic}"

        with self._lock:
            if not reload and cache_key in self._cache:
                policy, val_result = self._cache[cache_key]
                if val_result.is_valid:
                    return policy, val_result

        # Validate artifact
        val_result = validate_model_artifact(
            model_path=resolved,
            algorithm=algorithm,
            raise_on_error=raise_on_error,
        )

        if not val_result.is_valid:
            return None, val_result

        # Load policy
        try:
            policy = RLModelPolicy.load(
                model_path=resolved,
                algorithm=algorithm,
                device="cpu",
                deterministic=deterministic,
            )
        except Exception as exc:
            msg = f"Exception loading verified model policy: {exc}"
            if raise_on_error:
                raise CorruptModelArtifactError(msg, model_path=str(resolved), cause=exc)
            fail_val = ModelValidationResult(
                is_valid=False,
                model_path=str(resolved),
                algorithm=algorithm.value,
                metadata=val_result.metadata,
                error_message=msg,
            )
            return None, fail_val

        with self._lock:
            self._cache[cache_key] = (policy, val_result)

        return policy, val_result
