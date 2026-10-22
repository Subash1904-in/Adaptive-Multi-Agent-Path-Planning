"""Django management command for reproducible routing benchmarking."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.benchmarking.adapters import AlgorithmRegistry
from apps.core.benchmarking.exceptions import (
    BenchmarkError,
)
from apps.core.benchmarking.export import BenchmarkExporter
from apps.core.benchmarking.runner import BenchmarkRunner
from apps.core.benchmarking.scenarios import BenchmarkScenarioRegistry


class Command(BaseCommand):
    """Run reproducible routing benchmarks across algorithms and scenarios."""

    help = (
        "Execute reproducible AMAPP routing benchmarks, export JSON/CSV results, "
        "and print summaries."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--algorithms",
            "-a",
            type=str,
            default="",
            help="Comma-separated algorithm IDs (e.g., 'dijkstra,astar,static,adaptive').",
        )
        parser.add_argument(
            "--scenarios",
            "-s",
            type=str,
            default="",
            help=(
                "Comma-separated scenario IDs "
                "(e.g., 'bench_grid_sparse_3x3,bench_incident_closure')."
            ),
        )
        parser.add_argument(
            "--trials",
            "-t",
            type=int,
            default=1,
            help="Number of trials per (scenario, algorithm) pair. Default: 1.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Base integer random seed for reproducibility. Default: 42.",
        )
        parser.add_argument(
            "--export-dir",
            "-o",
            type=str,
            default="",
            help="Output directory path for exported JSON, CSV, and Markdown files.",
        )
        parser.add_argument(
            "--smoke",
            action="store_true",
            help=(
                "Execute a minimal, fast 1-trial benchmark comparing dijkstra and astar "
                "on bench_grid_sparse_3x3."
            ),
        )
        parser.add_argument(
            "--max-ticks",
            type=int,
            default=None,
            help="Optional override for simulation ticks limit per trial.",
        )
        parser.add_argument(
            "--list-algorithms",
            action="store_true",
            help="Print list of available routing algorithm adapters and exit.",
        )
        parser.add_argument(
            "--list-scenarios",
            action="store_true",
            help="Print list of standardized benchmark scenarios and exit.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        algo_reg = AlgorithmRegistry.get_default_registry()
        scen_reg = BenchmarkScenarioRegistry.get_default_registry()

        # Handle --list-algorithms
        if options["list_algorithms"]:
            self.stdout.write(self.style.SUCCESS("Available Routing Benchmark Algorithms:"))
            for item in algo_reg.list_algorithms():
                impl_str = (
                    "IMPLEMENTED" if item["is_implemented"] else "NOT IMPLEMENTED (Phase 32+)"
                )
                adapt_str = "Adaptive" if item["is_adaptive"] else "Static"
                self.stdout.write(
                    f"  - {item['algorithm_id']:<10} [{impl_str}] ({adapt_str}) - "
                    f"{item['name']}: {item['description']}"
                )
            return

        # Handle --list-scenarios
        if options["list_scenarios"]:
            self.stdout.write(self.style.SUCCESS("Standardized Benchmark Scenarios:"))
            for item in scen_reg.list_scenarios():
                tags_str = ", ".join(item["tags"])
                self.stdout.write(
                    f"  - {item['scenario_id']:<26} (v{item['version']}) [{tags_str}] - "
                    f"{item['name']}: {item['description']}"
                )
            return

        # Handle --smoke preset
        if options["smoke"]:
            algorithms = ["dijkstra", "astar"]
            scenarios = ["bench_grid_sparse_3x3"]
            trials = 1
            seed = options["seed"]
            self.stdout.write(
                self.style.NOTICE(
                    "Running smoke benchmark (dijkstra, astar on bench_grid_sparse_3x3)..."
                )
            )
        else:
            raw_algos = options["algorithms"].strip()
            raw_scens = options["scenarios"].strip()

            if not raw_algos:
                algorithms = ["dijkstra", "astar", "static", "adaptive"]
            else:
                algorithms = [a.strip() for a in raw_algos.split(",") if a.strip()]

            if not raw_scens:
                scenarios = ["bench_grid_sparse_3x3", "bench_incident_closure"]
            else:
                scenarios = [s.strip() for s in raw_scens.split(",") if s.strip()]

            trials = options["trials"]
            seed = options["seed"]

        if trials < 1:
            raise CommandError(f"Trials must be >= 1, got {trials}.")

        # Execute benchmark suite
        runner = BenchmarkRunner(
            algorithm_registry=algo_reg,
            scenario_registry=scen_reg,
        )

        try:
            report = runner.run_suite(
                algorithms=algorithms,
                scenarios=scenarios,
                trials_per_pair=trials,
                base_seed=seed,
                max_ticks_override=options["max_ticks"],
            )
        except BenchmarkError as exc:
            raise CommandError(f"Benchmark execution failed: {exc}") from exc

        # Output results summary table to stdout
        exporter = BenchmarkExporter()
        report_md = exporter.generate_report_markdown(report)
        self.stdout.write("\n" + report_md + "\n")

        # Export files if export_dir specified
        export_dir = options["export_dir"].strip()
        if export_dir:
            try:
                paths = exporter.export_all(report, output_dir=export_dir)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully exported benchmark artifacts to: {export_dir}"
                    )
                )
                for key, p in paths.items():
                    self.stdout.write(f"  - {key}: {p}")
            except Exception as exc:
                raise CommandError(f"Export failed: {exc}") from exc
