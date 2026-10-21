"""Unit and integration tests for deterministic hashing, reproducibility metadata, and JSON export.

Verifies:
- Bit-identical execution reproducibility for equivalent scenario inputs
- Stable scenario fingerprints invariant to dictionary ordering and non-deterministic metadata
- World state fingerprint reproducibility
- Git commit SHA discovery (returns real SHA or None, never invented)
- Valid RFC 8259 JSON serialization of completed, cancelled, and failed runs
- Non-finite numeric handling (-inf, inf, nan) in exported results
- Payload byte size limit enforcement raising ExportSizeLimitExceededError
- Invariance: Export does not mutate simulation or runner state
"""

import json

import pytest

from apps.core.scenarios.examples import (
    create_multi_vehicle_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.models import (
    TerminationReason,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.telemetry.exceptions import ExportSizeLimitExceededError
from apps.core.telemetry.fingerprint import (
    compute_scenario_fingerprint,
    get_git_commit_sha,
)


class TestScenarioFingerprintingAndReproducibility:
    """Tests deterministic scenario and world-state fingerprinting."""

    def test_identical_scenarios_have_identical_fingerprints(self):
        """Two independently created scenario definitions have bit-identical fingerprints."""
        scn1 = create_multi_vehicle_scenario(seed=42)
        scn2 = create_multi_vehicle_scenario(seed=42)

        fp1 = compute_scenario_fingerprint(scn1)
        fp2 = compute_scenario_fingerprint(scn2)

        assert fp1 == fp2
        assert len(fp1) == 64
        assert all(c in "0123456789abcdef" for c in fp1)

    def test_scenario_fingerprint_changes_on_semantic_difference(self):
        """Changing vehicle configuration or time step alters the scenario fingerprint."""
        scn1 = create_single_vehicle_scenario(time_step_s=0.1)
        scn2 = create_single_vehicle_scenario(time_step_s=0.2)

        fp1 = compute_scenario_fingerprint(scn1)
        fp2 = compute_scenario_fingerprint(scn2)

        assert fp1 != fp2

    def test_operational_timestamps_do_not_affect_fingerprint(self):
        """Simulation metadata with wall-clock timestamps is stripped from hashing."""
        scn = create_single_vehicle_scenario()
        fp_baseline = compute_scenario_fingerprint(scn)

        # Mutate dictionary copy with wall_clock_time
        d = scn.to_dict()
        d["simulation_metadata"]["wall_clock_time"] = "2026-10-21T12:00:00Z"
        d["simulation_metadata"]["timestamp"] = 1792400000.0

        fp_with_timestamps = compute_scenario_fingerprint(d)
        assert fp_with_timestamps == fp_baseline

    def test_world_state_fingerprint_determinism(self):
        """Identical simulation executions generate identical final world state fingerprints."""
        scn1 = create_single_vehicle_scenario(max_ticks=5, seed=100)
        scn2 = create_single_vehicle_scenario(max_ticks=5, seed=100)

        runner1 = ScenarioRunner.create(scn1)
        runner2 = ScenarioRunner.create(scn2)

        res1 = runner1.run_to_completion()
        res2 = runner2.run_to_completion()

        assert res1.run_metadata is not None
        assert res2.run_metadata is not None
        assert (
            res1.run_metadata.initial_world_state_fingerprint
            == res2.run_metadata.initial_world_state_fingerprint
        )
        assert (
            res1.run_metadata.final_world_state_fingerprint
            == res2.run_metadata.final_world_state_fingerprint
        )

    def test_git_commit_sha_discovery(self):
        """Commit SHA is discoverable: 40-char hex string or None (never invented)."""
        sha = get_git_commit_sha()
        if sha is not None:
            assert len(sha) == 40
            assert all(c in "0123456789abcdefABCDEF" for c in sha)


class TestResultExportAndJSONSerialization:
    """Tests RFC 8259 JSON result export, size guardrails, and non-finite numbers."""

    def test_completed_run_json_export(self):
        """Completed run serializes to valid, parseable JSON with all required fields."""
        scenario = create_single_vehicle_scenario(max_ticks=4)
        runner = ScenarioRunner.create(scenario)
        runner.run_to_completion()

        json_str = runner.export_result(indent=2)
        parsed = json.loads(json_str)

        assert parsed["scenario_id"] == scenario.metadata.id
        assert parsed["termination_reason"] in ("max_ticks_reached", "all_arrived")
        assert parsed["is_success"] is True
        assert "run_metadata" in parsed
        assert "metrics_summary" in parsed
        assert "telemetry_records" in parsed
        assert len(parsed["telemetry_records"]) > 0

    def test_cancelled_run_json_export(self):
        """Cancelled run export reflects is_partial=True and records cancellation reason."""
        scenario = create_single_vehicle_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scenario)
        runner.run(ticks=2)
        runner.cancel(reason="Benchmarking aborted")
        result = runner.run()

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["lifecycle_state"] == "CANCELLED"
        assert parsed["termination_reason"] == "cancelled"
        assert parsed["is_partial"] is True
        assert parsed["cancellation_reason"] == "Benchmarking aborted"

    def test_failed_run_json_export(self, monkeypatch):
        """Failed run export preserves error message and is_success=False without raising."""
        scenario = create_single_vehicle_scenario(max_ticks=5)
        runner = ScenarioRunner.create(scenario)

        def blow_up(*args, **kwargs):
            raise ValueError("Injected step failure for export test")

        monkeypatch.setattr(runner.engine, "step", blow_up)
        result = runner.run()

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["lifecycle_state"] == "FAILED"
        assert parsed["termination_reason"] == "failed"
        assert parsed["is_success"] is False
        assert "Injected step failure" in parsed["error_message"]

    def test_non_finite_float_handling_in_json_export(self):
        """Diagnostics containing -inf or nan serialize cleanly into valid JSON."""
        scenario = create_single_vehicle_scenario(max_ticks=2)
        runner = ScenarioRunner.create(scenario)
        result = runner.run_to_completion()

        # Inject non-finite floats into diagnostics
        dirty_diag = dict(result.diagnostics)
        dirty_diag["hard_constraint_score"] = float("-inf")
        dirty_diag["unconstrained_cost"] = float("inf")
        dirty_diag["undefined_ratio"] = float("nan")

        # Create updated result copy
        modified_result = ScenarioRunner._build_result(
            runner,
            reason=TerminationReason.ALL_ARRIVED,
            diagnostics=dirty_diag,
        )

        # Must not raise ValueError: Out of range float values are not JSON compliant
        json_str = modified_result.to_json()
        parsed = json.loads(json_str)
        assert parsed["diagnostics"]["hard_constraint_score"] == "-Infinity"
        assert parsed["diagnostics"]["unconstrained_cost"] == "Infinity"
        assert parsed["diagnostics"]["undefined_ratio"] == "NaN"

    def test_export_size_limit_exceeded_raises_error(self):
        """When payload exceeds max_size_bytes, ExportSizeLimitExceededError is raised."""
        scenario = create_single_vehicle_scenario(max_ticks=5)
        runner = ScenarioRunner.create(scenario)
        result = runner.run_to_completion()

        # Enforce an unrealistically small limit of 100 bytes
        with pytest.raises(ExportSizeLimitExceededError) as exc_info:
            result.to_json(max_size_bytes=100)

        assert exc_info.value.max_bytes == 100
        assert exc_info.value.size_bytes is not None
        assert exc_info.value.size_bytes > 100

    def test_export_does_not_mutate_world_or_runner_state(self):
        """Exporting a result does not alter engine, world snapshot, or tick history."""
        scenario = create_single_vehicle_scenario(max_ticks=3)
        runner = ScenarioRunner.create(scenario)
        res = runner.run_to_completion()

        tick_before = runner.engine.current_tick
        history_len_before = len(runner.tick_history)
        snap_before = runner.world.get_snapshot().to_dict()

        _ = runner.export_result()
        _ = res.to_json()

        assert runner.engine.current_tick == tick_before
        assert len(runner.tick_history) == history_len_before
        assert runner.world.get_snapshot().to_dict() == snap_before
