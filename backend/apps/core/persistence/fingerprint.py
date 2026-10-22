"""Deterministic hashing and reproducibility fingerprinting for AMAPP persistence.

Provides deterministic SHA-256 configuration fingerprints for SimulationRun
and BenchmarkConfiguration models, canonicalizing JSON structures, rejecting
non-finite floats and sensitive credentials, and excluding volatile operational
runtime fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from enum import Enum
from typing import Any, Mapping

# Keys that indicate operational/volatile runtime data to exclude from fingerprints
EXCLUDED_OPERATIONAL_KEYS = frozenset(
    {
        "wall_clock_time",
        "timestamp",
        "start_time",
        "completion_time",
        "created_at",
        "updated_at",
        "elapsed_time_s",
        "run_id",
        "benchmark_run_id",
        "id",
        "pk",
    }
)

# Pattern for identifying sensitive secrets or credential keys to reject
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:^|_)(password|secret|token|api_?key|auth|credential|private_key)(?:$|_)",
    re.IGNORECASE,
)

# Pattern identifying absolute local filesystem paths (e.g. C:\Users\... or /home/... or /Users/...)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"^(?:[a-zA-Z]:[\\/]|/(?:home|Users|tmp|var|etc)[\\/])",
    re.IGNORECASE,
)


def is_sensitive_key(key: str) -> bool:
    """Return True if key name matches secret/credential patterns."""
    return bool(SENSITIVE_KEY_PATTERN.search(key))


def is_absolute_filesystem_path(value: str) -> bool:
    """Return True if string represents an absolute local filesystem path."""
    return bool(ABSOLUTE_PATH_PATTERN.match(value))


def canonicalize_for_fingerprint(data: Any, key_name: str | None = None) -> Any:
    """Recursively normalize and validate configuration data for deterministic fingerprinting.

    Args:
        data: Primitive, mapping, sequence, or dataclass/object to canonicalize.
        key_name: Key or attribute name associated with data (for secret detection).

    Returns:
        Canonical JSON-compatible data structure with sorted keys and normalized scalars.

    Raises:
        ValueError: If non-finite numbers (NaN, Inf), sensitive credentials, or local
            filesystem paths are detected in the configuration.
    """
    if key_name and is_sensitive_key(key_name):
        raise ValueError(
            f"Sensitive credential field '{key_name}' is not allowed in configuration fingerprint."
        )

    if isinstance(data, float):
        if not math.isfinite(data):
            raise ValueError(
                f"Non-finite numeric value '{data}' is not allowed in configuration fingerprint."
            )
        # Normalize floating point precision
        return round(data, 6)

    if isinstance(data, (int, bool)) or data is None:
        return data

    if isinstance(data, str):
        if is_absolute_filesystem_path(data):
            raise ValueError(
                f"Absolute local filesystem path '{data}' is not allowed in fingerprint."
            )
        return data

    if isinstance(data, Enum):
        return data.value

    if hasattr(data, "to_dict") and callable(data.to_dict):
        return canonicalize_for_fingerprint(data.to_dict(), key_name=key_name)

    if isinstance(data, Mapping):
        cleaned: dict[str, Any] = {}
        # Sort keys deterministically
        for k in sorted(str(k) for k in data.keys()):
            if k in EXCLUDED_OPERATIONAL_KEYS:
                continue
            if is_sensitive_key(k):
                raise ValueError(
                    f"Sensitive credential key '{k}' cannot be included in fingerprint."
                )
            cleaned[k] = canonicalize_for_fingerprint(data[k], key_name=k)
        return cleaned

    if isinstance(data, (set, frozenset)):
        # Normalize sets to sorted lists
        items = [canonicalize_for_fingerprint(item) for item in data]
        return sorted(items, key=lambda x: str(x))

    if isinstance(data, (list, tuple)):
        return [canonicalize_for_fingerprint(item) for item in data]

    # For unknown objects, convert to string representation or raise
    val_str = str(data)
    if is_absolute_filesystem_path(val_str):
        raise ValueError(
            f"Absolute local filesystem path in '{val_str}' cannot be included in configuration."
        )
    return val_str


def canonical_json_dumps(data: Any) -> str:
    """Serialize canonicalized configuration data to a deterministic, compact JSON string.

    Args:
        data: Arbitrary configuration data.

    Returns:
        Deterministic compact UTF-8 JSON string.
    """
    canonical_data = canonicalize_for_fingerprint(data)
    return json.dumps(canonical_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_config_fingerprint(data: Any) -> str:
    """Compute the deterministic SHA-256 hex digest for an arbitrary configuration structure."""
    canonical_str = canonical_json_dumps(data)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_run_config_fingerprint(
    scenario_id: str,
    scenario_version: str = "1.0.0",
    seed: int | None = None,
    seed_policy: str = "FIXED",
    routing_strategy: str = "",
    parameters: dict[str, Any] | None = None,
    schema_version: str = "1.0.0",
) -> str:
    """Compute deterministic SHA-256 fingerprint for a simulation run configuration.

    Normalizes scenario ID, version, random seed, routing strategy, and custom parameters.
    """
    payload: dict[str, Any] = {
        "scenario_id": str(scenario_id),
        "scenario_version": str(scenario_version),
        "seed": seed,
        "seed_policy": str(seed_policy),
        "routing_strategy": str(routing_strategy),
        "schema_version": str(schema_version),
        "parameters": parameters or {},
    }
    return compute_config_fingerprint(payload)


def compute_benchmark_config_fingerprint(
    name: str,
    scenario_ids: list[str],
    algorithm_ids: list[str],
    trial_count: int,
    base_seed: int,
    seed_policy: str = "FIXED",
    parameters: dict[str, Any] | None = None,
) -> str:
    """Compute deterministic SHA-256 fingerprint for a benchmark configuration."""
    payload: dict[str, Any] = {
        "name": str(name),
        "scenario_ids": sorted(scenario_ids),
        "algorithm_ids": sorted(algorithm_ids),
        "trial_count": int(trial_count),
        "base_seed": int(base_seed),
        "seed_policy": str(seed_policy),
        "parameters": parameters or {},
    }
    return compute_config_fingerprint(payload)
