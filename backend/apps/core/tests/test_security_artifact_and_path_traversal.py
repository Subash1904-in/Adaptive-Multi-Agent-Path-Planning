"""Tests for model artifact path traversal prevention, Zip Slip mitigation, and fallback safety.

Validates:
- is_safe_contained_path rejects external paths and project root traversal.
- resolve_model_artifact_path rejects path traversal attempts.
- validate_model_artifact detects and rejects Zip Slip directory traversal entries.
- Corrupt or non-zip artifact handling returns structured invalid results or raises
  CorruptModelArtifactError.
- SafeFallbackPolicyWrapper safely falls back to conventional routing on corrupt or
  failing policies.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from apps.core.benchmarking.adapters import SafeFallbackPolicyWrapper
from apps.core.rl.model_manager import (
    CorruptModelArtifactError,
    ModelArtifactError,
    _get_project_root,
    is_safe_contained_path,
    resolve_model_artifact_path,
    validate_model_artifact,
)


def test_is_safe_contained_path():
    """Verify is_safe_contained_path strictly permits only paths within project or cwd."""
    root = _get_project_root()
    cwd = Path.cwd().resolve()

    # Allowed paths
    assert is_safe_contained_path(root / "artifacts" / "test.zip") is True
    assert is_safe_contained_path(cwd / "test_file.zip") is True

    # Traversal escaping project root
    traversal_path = root / ".." / ".." / ".." / "escaped.zip"
    assert is_safe_contained_path(traversal_path) is False

    # External system files
    assert is_safe_contained_path(Path("C:/Windows/System32/cmd.exe")) is False
    assert is_safe_contained_path(Path("/etc/passwd")) is False


def test_resolve_model_artifact_path_rejects_traversal(monkeypatch):
    """resolve_model_artifact_path rejects paths outside approved project root."""
    # Explicit traversal path
    bad_configured = "../../../../../etc/passwd"
    resolved = resolve_model_artifact_path(bad_configured)
    assert resolved is None

    # Traversal via environment variable
    monkeypatch.setenv("AMAPP_RL_MODEL_PATH", "../../../../../Windows/System32/calc.exe")
    resolved_env = resolve_model_artifact_path()
    assert resolved_env is None


def test_validate_model_artifact_detects_zip_slip():
    """Archives with Zip Slip path traversal entries (.. or /) are rejected."""
    root = _get_project_root()
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", dir=artifacts_dir, delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        # Create a malicious zip with Zip Slip traversal entry
        with zipfile.ZipFile(tmp_path, "w") as zf:
            zf.writestr("../../evil_script.sh", b"echo pwned")
            zf.writestr("data", b"sb3_serialized_data")

        # 1. With raise_on_error=False
        result = validate_model_artifact(tmp_path, raise_on_error=False)
        assert result.is_valid is False
        assert result.error_message is not None
        assert "Zip slip" in result.error_message or "traversal" in result.error_message

        # 2. With raise_on_error=True
        with pytest.raises(CorruptModelArtifactError) as exc_info:
            validate_model_artifact(tmp_path, raise_on_error=True)
        assert "Zip slip" in str(exc_info.value) or "traversal" in str(exc_info.value)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_validate_model_artifact_rejects_corrupt_and_non_zip_files():
    """Corrupt or non-zip files are rejected with CorruptModelArtifactError."""
    root = _get_project_root()
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", dir=artifacts_dir, delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
        tmp_file.write(b"not a valid zip file content at all")

    try:
        result = validate_model_artifact(tmp_path, raise_on_error=False)
        assert result.is_valid is False
        assert "not a valid zip archive" in (result.error_message or "")

        with pytest.raises(CorruptModelArtifactError):
            validate_model_artifact(tmp_path, raise_on_error=True)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_validate_model_artifact_rejects_unapproved_path():
    """validate_model_artifact rejects paths located outside approved directories."""
    external_path = (
        Path("C:/Windows/System32/drivers/etc/hosts") if os.name == "nt" else Path("/etc/hosts")
    )
    result = validate_model_artifact(external_path, raise_on_error=False)
    assert result.is_valid is False
    assert "outside approved project directory" in (result.error_message or "")

    with pytest.raises(ModelArtifactError):
        validate_model_artifact(external_path, raise_on_error=True)


def test_safe_fallback_policy_wrapper_handles_corrupt_model():
    """SafeFallbackPolicyWrapper safely falls back to action 0 when model prediction crashes."""
    mock_policy = MagicMock()
    mock_policy.predict.side_effect = RuntimeError("Corrupted weights or memory access violation")
    wrapper = SafeFallbackPolicyWrapper(model_policy=mock_policy)

    obs = np.zeros(32, dtype=np.float32)
    info = {"action_mask": np.array([1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.int8)}

    action = wrapper(obs, info)
    assert action == 0
    assert wrapper.fallback_decisions == 1
    assert "inference_exception:RuntimeError" in wrapper.fallback_reasons
