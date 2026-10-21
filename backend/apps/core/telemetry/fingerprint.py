"""Deterministic hashing and reproducibility fingerprinting for AMAPP simulations.

Provides stable SHA-256 fingerprints for scenario definitions and world states,
excluding non-deterministic operational timestamps, object memory addresses, and
dictionary iteration orderings. Also securely discovers the active Git commit SHA.
"""

import hashlib
import json
import os
import subprocess
from typing import Any, Optional

from apps.core.telemetry.models import sanitize_for_json


def canonical_json_dumps(data: Any) -> str:
    """Serialize data into a deterministic, sorted, whitespace-minimized canonical JSON string."""
    sanitized = sanitize_for_json(data)
    return json.dumps(sanitized, sort_keys=True, separators=(",", ":"), allow_nan=False)


def compute_sha256_digest(data: Any) -> str:
    """Compute the SHA-256 hexadecimal digest of canonical serialized data."""
    canonical_repr = canonical_json_dumps(data)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def compute_scenario_fingerprint(scenario_definition: Any) -> str:
    """Generate a stable, deterministic SHA-256 fingerprint for a ScenarioDefinition.

    Args:
        scenario_definition: ScenarioDefinition instance or dictionary representation.

    Returns:
        64-character lowercase SHA-256 hexadecimal digest.
    """
    if hasattr(scenario_definition, "to_dict"):
        raw_dict = scenario_definition.to_dict()
    elif isinstance(scenario_definition, dict):
        raw_dict = dict(scenario_definition)
    else:
        raw_dict = {"repr": str(scenario_definition)}

    # Remove non-deterministic operational runtime metadata if any
    cleaned_dict = dict(raw_dict)
    if "simulation_metadata" in cleaned_dict and isinstance(
        cleaned_dict["simulation_metadata"], dict
    ):
        meta = dict(cleaned_dict["simulation_metadata"])
        meta.pop("wall_clock_time", None)
        meta.pop("timestamp", None)
        cleaned_dict["simulation_metadata"] = meta

    return compute_sha256_digest(cleaned_dict)


def compute_world_state_fingerprint(world_snapshot: Any) -> str:
    """Generate a stable, deterministic SHA-256 fingerprint for a WorldSnapshot.

    Args:
        world_snapshot: WorldSnapshot instance or dictionary representation.

    Returns:
        64-character lowercase SHA-256 hexadecimal digest.
    """
    if hasattr(world_snapshot, "to_dict"):
        raw_dict = world_snapshot.to_dict()
    elif isinstance(world_snapshot, dict):
        raw_dict = dict(world_snapshot)
    else:
        raw_dict = {"repr": str(world_snapshot)}

    cleaned = dict(raw_dict)
    # Exclude operational metadata that may contain wall-clock timestamps
    if "metadata" in cleaned and isinstance(cleaned["metadata"], dict):
        meta = dict(cleaned["metadata"])
        meta.pop("wall_clock_time", None)
        meta.pop("timestamp", None)
        cleaned["metadata"] = meta

    return compute_sha256_digest(cleaned)


def get_git_commit_sha() -> Optional[str]:
    """Discover the active Git commit SHA without inventing or fabricating a fallback value.

    Returns:
        40-character hexadecimal SHA string if discoverable, otherwise None.
    """
    # 1. Check standard CI environment variables
    for env_var in ("GIT_COMMIT_SHA", "GITHUB_SHA", "COMMIT_SHA"):
        val = os.environ.get(env_var)
        if val and len(val.strip()) in (7, 40):
            return val.strip()

    # 2. Query git repository directly if git command is available
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        sha = result.stdout.strip()
        if len(sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in sha):
            return sha.lower()
    except Exception:
        pass

    return None
