"""Comprehensive automated test suite for the AMAPP Reproducible Routing Benchmarking Framework."""

from __future__ import annotations

import csv
import json
import math
import tempfile
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.benchmarking.adapters import (
    AdaptiveRoutingBenchmarkAdapter,
    AlgorithmRegistry,
    AStarBenchmarkAdapter,
    DijkstraBenchmarkAdapter,
    LearnedRoutingBenchmarkAdapter,
    StaticRoutingBenchmarkAdapter,
)
from apps.core.benchmarking.exceptions import (
    BenchmarkExecutionError,
    BenchmarkExportError,
    UnsupportedAlgorithmError,
    UnsupportedScenarioError,
)
from apps.core.benchmarking.export import BenchmarkExporter
from apps.core.benchmarking.models import (
    BenchmarkStatus,
    SeedPolicy,
)
from apps.core.benchmarking.runner import (
    BenchmarkRunner,
    _compute_mean,
    _compute_median,
    _compute_percentile,
    _compute_std,
)
from apps.core.benchmarking.scenarios import (
    BenchmarkScenarioRegistry,
)
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.routing.models import CostMode


# ==============================================================================
# 1. Algorithm Adapter & Registry Tests
# ==============================================================================
class TestAlgorithmRegistryAndAdapters:
    """Tests for algorithm adapters, registry lookup, and contract adherence."""

    def test_default_registry_preloaded_algorithms(self) -> None:
        registry = AlgorithmRegistry.get_default_registry()
        algos = registry.list_algorithms()
        algo_ids = {a["algorithm_id"] for a in algos}

        assert "dijkstra" in algo_ids
        assert "astar" in algo_ids
        assert "static" in algo_ids
        assert "adaptive" in algo_ids
        assert "learned" in algo_ids

    def test_get_implemented_algorithms(self) -> None:
        registry = AlgorithmRegistry.get_default_registry()
        dijkstra = registry.get("dijkstra")
        assert isinstance(dijkstra, DijkstraBenchmarkAdapter)
        assert dijkstra.is_implemented is True
        assert dijkstra.is_adaptive is False

        astar = registry.get("astar")
        assert isinstance(astar, AStarBenchmarkAdapter)
        assert astar.is_implemented is True
        assert astar.is_adaptive is False

        static_a = registry.get("static")
        assert isinstance(static_a, StaticRoutingBenchmarkAdapter)
        assert static_a.is_implemented is True

        adaptive_a = registry.get("adaptive")
        assert isinstance(adaptive_a, AdaptiveRoutingBenchmarkAdapter)
        assert adaptive_a.is_implemented is True
        assert adaptive_a.is_adaptive is True

    def test_unsupported_algorithm_raises_explicit_error(self) -> None:
        registry = AlgorithmRegistry.get_default_registry()
        with pytest.raises(UnsupportedAlgorithmError) as exc_info:
            registry.get("non_existent_algo")

        err = exc_info.value
        assert err.algorithm_id == "non_existent_algo"
        assert "dijkstra" in err.available_algorithms

    def test_learned_algorithm_raises_clear_error_when_accessed_or_executed(self) -> None:
        registry = AlgorithmRegistry.get_default_registry()
        with pytest.raises(UnsupportedAlgorithmError) as exc_info:
            registry.get("learned")

        err = exc_info.value
        assert "learned" in err.algorithm_id
        assert "Phases 32-34" in str(err)

        # Directly testing adapter instance methods
        learned_adapter = LearnedRoutingBenchmarkAdapter()
        assert learned_adapter.is_implemented is False
        assert learned_adapter.is_adaptive is True

        grid = generate_synthetic_city_grid(CityGridConfig(rows=2, cols=2))
        with pytest.raises(UnsupportedAlgorithmError):
            learned_adapter.plan_initial_route(grid, "node_r0_c0", "node_r1_c1")

    def test_dijkstra_and_astar_route_cost_parity_on_grid(self) -> None:
        """Dijkstra and A* must compute identical optimal objective costs on identical graphs."""
        grid = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=50.0, speed_limit_mps=10.0)
        )
        dijkstra = DijkstraBenchmarkAdapter()
        astar = AStarBenchmarkAdapter()

        res_dijkstra, dur_d = dijkstra.plan_initial_route(
            grid, "node_r0_c0", "node_r2_c2", CostMode.TRAVEL_TIME
        )
        res_astar, dur_a = astar.plan_initial_route(
            grid, "node_r0_c0", "node_r2_c2", CostMode.TRAVEL_TIME
        )

        assert res_dijkstra is not None and res_dijkstra.success
        assert res_astar is not None and res_astar.success
        assert math.isclose(res_dijkstra.objective_cost, res_astar.objective_cost, rel_tol=1e-5)
        assert math.isclose(res_dijkstra.total_distance_m, res_astar.total_distance_m, rel_tol=1e-5)
        assert dur_d >= 0.0
        assert dur_a >= 0.0

    def test_plan_initial_route_infeasible_returns_none(self) -> None:
        grid = generate_synthetic_city_grid(CityGridConfig(rows=2, cols=2, spacing_m=50.0))
        astar = AStarBenchmarkAdapter()
        # Block both incoming edges to node_r1_c1
        closed = {"edge_r0_c1_to_r1_c1", "edge_r1_c0_to_r1_c1"}
        res, dur = astar.plan_initial_route(
            grid, "node_r0_c0", "node_r1_c1", closed_edge_ids=closed
        )
        assert res is None
        assert dur >= 0.0


# ==============================================================================
# 2. Scenario Registry & Seed Determinism Tests
# ==============================================================================
class TestScenarioRegistryAndSeeds:
    """Tests for standardized scenarios, seed isolation, and reproducibility."""

    def test_scenario_registry_contains_all_standard_scenarios(self) -> None:
        registry = BenchmarkScenarioRegistry.get_default_registry()
        scenarios = registry.list_scenarios()
        scen_ids = [s["scenario_id"] for s in scenarios]

        expected_ids = [
            "bench_grid_sparse_3x3",
            "bench_urban_medium_4x4",
            "bench_dense_corridor_5x5",
            "bench_incident_closure",
            "bench_incident_congestion",
            "bench_infeasible_barrier",
            "bench_emergency_corridor",
            "bench_v2v_degradation",
        ]
        for sid in expected_ids:
            assert sid in scen_ids

    def test_unsupported_scenario_raises_explicit_error(self) -> None:
        registry = BenchmarkScenarioRegistry.get_default_registry()
        with pytest.raises(UnsupportedScenarioError) as exc_info:
            registry.get("invalid_scenario_id")

        err = exc_info.value
        assert err.scenario_id == "invalid_scenario_id"
        assert "bench_grid_sparse_3x3" in err.available_scenarios

    def test_seed_policy_deterministic_derivation(self) -> None:
        policy = SeedPolicy(base_seed=100)
        s0 = policy.derive_seed(0)
        s1 = policy.derive_seed(1)
        s2 = policy.derive_seed(2)

        assert s0 == 100
        assert s1 == 1100
        assert s2 == 2100
        # Repeat derivation yields exact equality
        assert policy.derive_seed(1) == 1100

        with pytest.raises(ValueError):
            policy.derive_seed(-1)

    def test_scenario_factory_produces_isolated_instances(self) -> None:
        registry = BenchmarkScenarioRegistry.get_default_registry()
        sdef = registry.get("bench_grid_sparse_3x3")

        scen_a = sdef.create_scenario(seed=42)
        scen_b = sdef.create_scenario(seed=42)

        assert scen_a is not scen_b
        assert scen_a.metadata.id == scen_b.metadata.id
        assert scen_a.seed == scen_b.seed


# ==============================================================================
# 3. Statistical Aggregator Function Tests
# ==============================================================================
class TestStatisticalCalculations:
    """Unit tests for standalone statistical calculation helpers."""

    def test_mean_calculation(self) -> None:
        assert _compute_mean([]) is None
        assert _compute_mean([10.0]) == 10.0
        assert _compute_mean([10.0, 20.0, 30.0]) == 20.0

    def test_median_calculation(self) -> None:
        assert _compute_median([]) is None
        assert _compute_median([42.0]) == 42.0
        assert _compute_median([10.0, 30.0, 20.0]) == 20.0
        assert _compute_median([10.0, 20.0, 30.0, 40.0]) == 25.0

    def test_std_calculation(self) -> None:
        assert _compute_std([]) is None
        assert _compute_std([5.0]) == 0.0
        # [10, 20]: mean=15, diffs=[-5, 5], sum_sq=50, var=50/1=50, std=sqrt(50)
        assert math.isclose(_compute_std([10.0, 20.0]), math.sqrt(50.0), rel_tol=1e-5)

    def test_percentile_calculation(self) -> None:
        assert _compute_percentile([], 90.0) is None
        assert _compute_percentile([100.0], 90.0) == 100.0
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        # p50 should be median 30.0
        assert _compute_percentile(vals, 50.0) == 30.0
        # p100 should be max 50.0
        assert _compute_percentile(vals, 100.0) == 50.0
        # p0 should be min 10.0
        assert _compute_percentile(vals, 0.0) == 10.0


# ==============================================================================
# 4. Benchmark Runner Execution & Failure Handling Tests
# ==============================================================================
class TestBenchmarkRunnerExecution:
    """End-to-end tests for trial orchestration, aggregates, and failure isolation."""

    def test_single_trial_execution_success(self) -> None:
        runner = BenchmarkRunner()
        trial = runner.run_trial(
            scenario_id="bench_grid_sparse_3x3",
            algorithm_id="dijkstra",
            trial_index=0,
            seed=42,
            benchmark_run_id="test_run_01",
        )

        assert trial.benchmark_run_id == "test_run_01"
        assert trial.status == BenchmarkStatus.SUCCESS
        assert trial.route_feasible is True
        assert trial.route_cost == 20.0
        assert trial.route_length_m == 200.0
        assert trial.planning_duration_ms > 0.0
        assert trial.simulation_ticks > 0
        assert trial.completed_trips == 1
        assert trial.total_trips == 1
        assert trial.travel_time_s is not None
        assert trial.failure_reason is None

    def test_infeasible_barrier_scenario_handling(self) -> None:
        """Infeasible barrier scenario must be classified as INFEASIBLE with None cost."""
        runner = BenchmarkRunner()
        trial = runner.run_trial(
            scenario_id="bench_infeasible_barrier",
            algorithm_id="astar",
            trial_index=0,
            seed=42,
            benchmark_run_id="test_infeasible_run",
        )

        assert trial.status == BenchmarkStatus.INFEASIBLE
        assert trial.route_feasible is False
        assert trial.route_cost is None
        assert trial.route_length_m is None
        assert trial.travel_time_s is None
        assert trial.completed_trips == 0
        assert trial.failure_reason is not None
        assert (
            "No feasible route" in trial.failure_reason
            or "No traversable path" in trial.failure_reason
        )

    def test_run_suite_matrix_and_aggregates(self) -> None:
        runner = BenchmarkRunner()
        report = runner.run_suite(
            algorithms=["dijkstra", "astar"],
            scenarios=["bench_grid_sparse_3x3"],
            trials_per_pair=2,
            base_seed=42,
            run_id="suite_test_run",
        )

        assert report.benchmark_run_id == "suite_test_run"
        assert len(report.trials) == 4  # 2 algorithms * 1 scenario * 2 trials
        assert len(report.aggregates) == 2  # (dijkstra, grid) and (astar, grid)

        for agg in report.aggregates:
            assert agg.total_trials == 2
            assert agg.successful_trials == 2
            assert agg.failed_trials == 0
            assert agg.infeasible_trials == 0
            assert agg.route_success_rate_pct == 100.0
            assert agg.mean_route_cost == 20.0
            assert agg.mean_route_length_m == 200.0
            assert agg.mean_travel_time_s is not None
            assert agg.total_completed_trips == 2

    def test_run_suite_validation_errors(self) -> None:
        runner = BenchmarkRunner()
        with pytest.raises(BenchmarkExecutionError, match="Algorithms list cannot be empty"):
            runner.run_suite(algorithms=[], scenarios=["bench_grid_sparse_3x3"])

        with pytest.raises(BenchmarkExecutionError, match="Scenarios list cannot be empty"):
            runner.run_suite(algorithms=["dijkstra"], scenarios=[])

        with pytest.raises(BenchmarkExecutionError, match="trials_per_pair must be >= 1"):
            runner.run_suite(
                algorithms=["dijkstra"], scenarios=["bench_grid_sparse_3x3"], trials_per_pair=0
            )

    def test_failure_isolation_does_not_corrupt_subsequent_trials(self) -> None:
        """A failed/infeasible scenario must not contaminate subsequent successful scenarios."""
        runner = BenchmarkRunner()
        report = runner.run_suite(
            algorithms=["astar"],
            scenarios=["bench_infeasible_barrier", "bench_grid_sparse_3x3"],
            trials_per_pair=1,
            base_seed=42,
        )

        assert len(report.trials) == 2
        infeasible_t = report.trials[0]
        success_t = report.trials[1]

        assert infeasible_t.scenario_id == "bench_infeasible_barrier"
        assert infeasible_t.status == BenchmarkStatus.INFEASIBLE

        assert success_t.scenario_id == "bench_grid_sparse_3x3"
        assert success_t.status == BenchmarkStatus.SUCCESS
        assert success_t.route_cost == 20.0

        # Aggregates verify strict metric separation
        agg_infeasible = report.aggregates[0]
        agg_success = report.aggregates[1]

        assert agg_infeasible.mean_route_cost is None
        assert agg_infeasible.infeasible_trials == 1
        assert agg_infeasible.successful_trials == 0

        assert agg_success.mean_route_cost == 20.0
        assert agg_success.successful_trials == 1
        assert agg_success.infeasible_trials == 0


# ==============================================================================
# 5. Export Tests (JSON, CSV, Markdown, Path-Traversal Defense)
# ==============================================================================
class TestBenchmarkExporter:
    """Tests for serializing benchmark results with schema stability and safety."""

    def test_json_and_csv_export_round_trip(self) -> None:
        runner = BenchmarkRunner()
        report = runner.run_suite(
            algorithms=["dijkstra"],
            scenarios=["bench_grid_sparse_3x3"],
            trials_per_pair=1,
            base_seed=42,
        )

        exporter = BenchmarkExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_files = exporter.export_all(report, output_dir=tmpdir)

            # 1. Verify JSON
            json_path = out_files["json"]
            assert json_path.exists()
            with open(json_path, encoding="utf-8") as f:
                json_data = json.load(f)

            assert json_data["schema_version"] == "1.0.0"
            assert json_data["benchmark_run_id"] == report.benchmark_run_id
            assert len(json_data["trials"]) == 1
            assert len(json_data["aggregates"]) == 1

            # 2. Verify Trials CSV
            trials_path = out_files["trials_csv"]
            assert trials_path.exists()
            with open(trials_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 1
                assert rows[0]["algorithm_id"] == "dijkstra"
                assert rows[0]["scenario_id"] == "bench_grid_sparse_3x3"
                assert rows[0]["status"] == "success"
                assert float(rows[0]["route_cost"]) == 20.0

            # 3. Verify Summary CSV
            summary_path = out_files["summary_csv"]
            assert summary_path.exists()
            with open(summary_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 1
                assert rows[0]["algorithm_id"] == "dijkstra"
                assert rows[0]["total_trials"] == "1"
                assert float(rows[0]["mean_route_cost"]) == 20.0

            # 4. Verify Markdown Report
            md_path = out_files["report_md"]
            assert md_path.exists()
            md_text = md_path.read_text(encoding="utf-8")
            assert report.benchmark_run_id in md_text
            assert "bench_grid_sparse_3x3" in md_text
            assert "dijkstra" in md_text

    def test_path_traversal_rejection(self) -> None:
        runner = BenchmarkRunner()
        report = runner.run_suite(
            algorithms=["dijkstra"],
            scenarios=["bench_grid_sparse_3x3"],
            trials_per_pair=1,
            base_seed=42,
        )
        exporter = BenchmarkExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(BenchmarkExportError, match="Path traversal detected"):
                exporter.export_json(report, output_dir=tmpdir, filename="../../malicious.json")


# ==============================================================================
# 6. Django Management Command Tests
# ==============================================================================
class TestBenchmarkManagementCommand:
    """Tests for the `python manage.py run_benchmark` CLI workflow."""

    def test_list_algorithms_command(self) -> None:
        out = StringIO()
        call_command("run_benchmark", "--list-algorithms", stdout=out)
        output = out.getvalue()
        assert "Available Routing Benchmark Algorithms:" in output
        assert "dijkstra" in output
        assert "astar" in output
        assert "static" in output
        assert "adaptive" in output
        assert "learned" in output

    def test_list_scenarios_command(self) -> None:
        out = StringIO()
        call_command("run_benchmark", "--list-scenarios", stdout=out)
        output = out.getvalue()
        assert "Standardized Benchmark Scenarios:" in output
        assert "bench_grid_sparse_3x3" in output
        assert "bench_incident_closure" in output
        assert "bench_infeasible_barrier" in output

    def test_smoke_benchmark_command(self) -> None:
        out = StringIO()
        call_command("run_benchmark", "--smoke", stdout=out)
        output = out.getvalue()
        assert "Running smoke benchmark" in output
        assert "bench_grid_sparse_3x3" in output
        assert "dijkstra" in output
        assert "astar" in output
        assert "1 (1/0/0)" in output

    def test_smoke_benchmark_with_export_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = StringIO()
            call_command("run_benchmark", "--smoke", f"--export-dir={tmpdir}", stdout=out)
            output = out.getvalue()
            assert "Successfully exported benchmark artifacts" in output

            # Ensure files exist in tmpdir
            assert (Path(tmpdir) / "benchmark_results.json").exists()
            assert (Path(tmpdir) / "trials.csv").exists()
            assert (Path(tmpdir) / "summary.csv").exists()
            assert (Path(tmpdir) / "summary_report.md").exists()

    def test_invalid_trials_count_raises_command_error(self) -> None:
        with pytest.raises(CommandError, match="Trials must be >= 1"):
            call_command("run_benchmark", "--trials=0")
