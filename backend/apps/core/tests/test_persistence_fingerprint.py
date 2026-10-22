"""Tests for deterministic configuration fingerprinting and reproducibility metadata.

Verifies SHA-256 canonicalization, key-order invariance, float precision normalization,
rejection of non-finite numbers, and protection against secret and absolute path leakage.
"""

from __future__ import annotations

import pytest

from apps.core.persistence.fingerprint import (
    canonical_json_dumps,
    canonicalize_for_fingerprint,
    compute_benchmark_config_fingerprint,
    compute_config_fingerprint,
    compute_run_config_fingerprint,
)


class TestPersistenceFingerprint:
    """Verifies reproducibility fingerprint algorithms and security constraints."""

    def test_key_ordering_invariance(self) -> None:
        """Configurations with identical keys in different insertion orders
        yield identical fingerprints.
        """
        dict_a = {
            "scenario_id": "scn_grid_sparse",
            "seed": 42,
            "routing_strategy": "learned",
            "parameters": {"max_ticks": 100, "time_step_s": 0.1},
        }
        dict_b = {
            "parameters": {"time_step_s": 0.1, "max_ticks": 100},
            "routing_strategy": "learned",
            "seed": 42,
            "scenario_id": "scn_grid_sparse",
        }

        fp_a = compute_config_fingerprint(dict_a)
        fp_b = compute_config_fingerprint(dict_b)

        assert fp_a == fp_b
        assert len(fp_a) == 64

    def test_float_precision_normalization(self) -> None:
        """Minor floating point precision differences beyond 6 decimals normalize identically."""
        data_a = {"time_step_s": 0.1000001}
        data_b = {"time_step_s": 0.1000004}
        # Both round to 0.1
        assert canonical_json_dumps(data_a) == canonical_json_dumps(data_b)
        assert compute_config_fingerprint(data_a) == compute_config_fingerprint(data_b)

    def test_changed_configuration_produces_distinct_fingerprints(self) -> None:
        """Any meaningful parameter alteration changes the deterministic fingerprint."""
        base_fp = compute_run_config_fingerprint(
            scenario_id="scn_single_veh",
            seed=42,
            routing_strategy="astar",
            parameters={"max_ticks": 50},
        )

        # Changed scenario ID
        fp_scenario = compute_run_config_fingerprint(
            scenario_id="scn_multi_veh",
            seed=42,
            routing_strategy="astar",
            parameters={"max_ticks": 50},
        )
        assert base_fp != fp_scenario

        # Changed seed
        fp_seed = compute_run_config_fingerprint(
            scenario_id="scn_single_veh",
            seed=43,
            routing_strategy="astar",
            parameters={"max_ticks": 50},
        )
        assert base_fp != fp_seed

        # Changed routing strategy
        fp_algo = compute_run_config_fingerprint(
            scenario_id="scn_single_veh",
            seed=42,
            routing_strategy="learned",
            parameters={"max_ticks": 50},
        )
        assert base_fp != fp_algo

        # Changed parameter
        fp_param = compute_run_config_fingerprint(
            scenario_id="scn_single_veh",
            seed=42,
            routing_strategy="astar",
            parameters={"max_ticks": 100},
        )
        assert base_fp != fp_param

    def test_benchmark_config_fingerprint_determinism(self) -> None:
        """Benchmark configuration fingerprints are deterministic across equivalent sets."""
        fp_1 = compute_benchmark_config_fingerprint(
            name="Matrix Benchmark",
            scenario_ids=["scn_2", "scn_1"],
            algorithm_ids=["dijkstra", "astar"],
            trial_count=5,
            base_seed=1234,
        )
        fp_2 = compute_benchmark_config_fingerprint(
            name="Matrix Benchmark",
            scenario_ids=["scn_1", "scn_2"],
            algorithm_ids=["astar", "dijkstra"],
            trial_count=5,
            base_seed=1234,
        )
        assert fp_1 == fp_2

    def test_rejection_of_non_finite_floats(self) -> None:
        """Non-finite floats (NaN, Inf) must be strictly rejected rather than hashed unstably."""
        with pytest.raises(ValueError, match="Non-finite numeric value"):
            canonicalize_for_fingerprint({"cost": float("nan")})

        with pytest.raises(ValueError, match="Non-finite numeric value"):
            canonicalize_for_fingerprint({"cost": float("inf")})

        with pytest.raises(ValueError, match="Non-finite numeric value"):
            canonicalize_for_fingerprint({"cost": float("-inf")})

    def test_rejection_of_sensitive_credential_keys(self) -> None:
        """Sensitive credential or secret keys must be rejected from configuration fingerprints."""
        with pytest.raises(ValueError, match="Sensitive credential key"):
            canonicalize_for_fingerprint({"api_key": "secret_abc123"})

        with pytest.raises(ValueError, match="Sensitive credential key"):
            canonicalize_for_fingerprint({"user_password": "my_secret_password"})

        with pytest.raises(ValueError, match="Sensitive credential key"):
            canonicalize_for_fingerprint({"auth_token": "token_xyz"})

    def test_rejection_of_absolute_filesystem_paths(self) -> None:
        """Absolute local filesystem paths must be rejected to prevent host path disclosure."""
        with pytest.raises(ValueError, match="Absolute local filesystem path"):
            canonicalize_for_fingerprint({"weights_path": "C:\\Users\\dev\\model.pt"})

        with pytest.raises(ValueError, match="Absolute local filesystem path"):
            canonicalize_for_fingerprint({"dataset_path": "/home/ubuntu/data/network.osm"})

        with pytest.raises(ValueError, match="Absolute local filesystem path"):
            canonicalize_for_fingerprint({"config_file": "/Users/developer/config.json"})

    def test_exclusion_of_operational_runtime_fields(self) -> None:
        """Volatile operational fields (timestamps, IDs) are excluded from fingerprints."""
        data_with_timestamps = {
            "scenario_id": "scn_test",
            "seed": 42,
            "wall_clock_time": "2026-10-22T10:00:00Z",
            "created_at": "2026-10-22T10:00:00Z",
            "elapsed_time_s": 12.34,
        }
        data_without = {
            "scenario_id": "scn_test",
            "seed": 42,
        }
        assert compute_config_fingerprint(data_with_timestamps) == compute_config_fingerprint(
            data_without
        )
