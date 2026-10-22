"""Reproducible JSON, CSV, and Markdown export utilities for benchmark runs."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from apps.core.benchmarking.exceptions import BenchmarkExportError
from apps.core.benchmarking.models import BenchmarkRunReport


class BenchmarkExporter:
    """Handles serialization of benchmark results to JSON, CSV, and Markdown.

    Includes path-traversal safety defense.
    """

    TRIAL_CSV_COLUMNS = [
        "benchmark_run_id",
        "scenario_id",
        "scenario_version",
        "algorithm_id",
        "algorithm_version",
        "seed",
        "trial_index",
        "status",
        "route_feasible",
        "route_cost",
        "route_length_m",
        "planning_duration_ms",
        "simulation_duration_s",
        "simulation_ticks",
        "travel_time_s",
        "completed_trips",
        "total_trips",
        "completion_rate_pct",
        "collision_count",
        "near_miss_count",
        "intersection_crossings",
        "reroutes_evaluated",
        "reroutes_accepted",
        "messages_sent",
        "messages_delivered",
        "pdr",
        "incident_count",
        "failure_reason",
        "started_at",
        "completed_at",
    ]

    SUMMARY_CSV_COLUMNS = [
        "scenario_id",
        "algorithm_id",
        "total_trials",
        "successful_trials",
        "failed_trials",
        "infeasible_trials",
        "route_success_rate_pct",
        "mean_route_cost",
        "median_route_cost",
        "std_route_cost",
        "min_route_cost",
        "max_route_cost",
        "mean_route_length_m",
        "median_route_length_m",
        "mean_planning_duration_ms",
        "median_planning_duration_ms",
        "mean_travel_time_s",
        "median_travel_time_s",
        "p90_travel_time_s",
        "p95_travel_time_s",
        "total_completed_trips",
        "total_trips",
        "overall_completion_rate_pct",
        "total_collisions",
        "total_near_misses",
        "total_intersection_crossings",
        "mean_pdr",
        "total_reroutes_accepted",
    ]

    @staticmethod
    def _validate_and_resolve_path(output_dir: Path | str, filename: str) -> Path:
        """Validate destination to prevent directory traversal attacks."""
        try:
            base = Path(output_dir).resolve()
            target = (base / filename).resolve()
            # Ensure target is within base directory
            target.relative_to(base)
            base.mkdir(parents=True, exist_ok=True)
            return target
        except (ValueError, RuntimeError) as exc:
            raise BenchmarkExportError(
                f"Path traversal detected or invalid output path '{filename}' "
                f"inside '{output_dir}': {exc}"
            ) from exc

    def export_json(
        self,
        report: BenchmarkRunReport,
        output_dir: Path | str,
        filename: str = "benchmark_results.json",
    ) -> Path:
        """Export benchmark run report as an RFC 8259 valid JSON file."""
        target_path = self._validate_and_resolve_path(output_dir, filename)
        try:
            data = report.to_dict()
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return target_path
        except Exception as exc:
            raise BenchmarkExportError(f"Failed to export JSON to '{target_path}': {exc}") from exc

    def export_trials_csv(
        self,
        report: BenchmarkRunReport,
        output_dir: Path | str,
        filename: str = "trials.csv",
    ) -> Path:
        """Export individual trial records as an analysis-friendly CSV file."""
        target_path = self._validate_and_resolve_path(output_dir, filename)
        try:
            with open(target_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.TRIAL_CSV_COLUMNS)
                writer.writeheader()
                for trial in report.trials:
                    td = trial.to_dict()
                    row = {
                        k: ("" if td.get(k) is None else str(td.get(k)))
                        for k in self.TRIAL_CSV_COLUMNS
                    }
                    writer.writerow(row)
            return target_path
        except Exception as exc:
            raise BenchmarkExportError(
                f"Failed to export trials CSV to '{target_path}': {exc}"
            ) from exc

    def export_summary_csv(
        self,
        report: BenchmarkRunReport,
        output_dir: Path | str,
        filename: str = "summary.csv",
    ) -> Path:
        """Export aggregated statistics per (scenario, algorithm) as a CSV file."""
        target_path = self._validate_and_resolve_path(output_dir, filename)
        try:
            with open(target_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.SUMMARY_CSV_COLUMNS)
                writer.writeheader()
                for agg in report.aggregates:
                    ad = agg.to_dict()
                    row = {
                        k: ("" if ad.get(k) is None else str(ad.get(k)))
                        for k in self.SUMMARY_CSV_COLUMNS
                    }
                    writer.writerow(row)
            return target_path
        except Exception as exc:
            raise BenchmarkExportError(
                f"Failed to export summary CSV to '{target_path}': {exc}"
            ) from exc

    def generate_report_markdown(self, report: BenchmarkRunReport) -> str:
        """Generate a structured Markdown benchmark report from authoritative execution records."""
        lines = [
            f"# AMAPP Routing Benchmark Report - {report.benchmark_run_id}",
            "",
            "## 1. Execution Provenance & Environment",
            f"- **Run ID:** `{report.benchmark_run_id}`",
            f"- **Created At:** {report.created_at}",
            f"- **Git Commit SHA:** `{report.commit_sha or 'untracked'}`",
            f"- **Base Seed:** `{report.base_seed}`",
            f"- **Trials per (Scenario, Algorithm) Pair:** `{report.trials_per_pair}`",
            f"- **Platform:** {report.environment_metadata.get('platform', 'unknown')}",
            f"- **Python Version:** "
            f"{report.environment_metadata.get('python_version', sys.version).split()[0]}",
            "",
            "## 2. Aggregated Comparison Matrix",
            "",
            "| Scenario | Algorithm | Trials (Succ/Fail/Inf) | Feasibility % | "
            "Mean Cost | Mean Length (m) | Mean Plan (ms) | Mean Travel (s) | Collisions | PDR |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for agg in report.aggregates:
            trials_str = (
                f"{agg.total_trials} "
                f"({agg.successful_trials}/{agg.failed_trials}/{agg.infeasible_trials})"
            )
            feas_str = f"{agg.route_success_rate_pct:.1f}%"
            cost_str = f"{agg.mean_route_cost:.2f}" if agg.mean_route_cost is not None else "N/A"
            len_str = (
                f"{agg.mean_route_length_m:.1f}" if agg.mean_route_length_m is not None else "N/A"
            )
            plan_str = f"{agg.mean_planning_duration_ms:.2f}"
            travel_str = (
                f"{agg.mean_travel_time_s:.2f}" if agg.mean_travel_time_s is not None else "N/A"
            )
            pdr_str = f"{agg.mean_pdr:.2%}" if agg.mean_pdr is not None else "N/A"

            lines.append(
                f"| `{agg.scenario_id}` | `{agg.algorithm_id}` | {trials_str} | {feas_str} | "
                f"{cost_str} | {len_str} | {plan_str} | {travel_str} | {agg.total_collisions} | "
                f"{pdr_str} |"
            )

        lines.extend(
            [
                "",
                "## 3. Failure & Infeasibility Analysis",
                "The benchmarking framework guarantees strict non-fabrication:",
                "- Infeasible routes (e.g. partition barriers) are explicitly marked `infeasible` "
                "and are never treated as successful zero-cost paths.",
                "- Incomplete or timed-out simulations do not register artificial travel times.",
                "- Sample counts for route cost, route length, and travel time exclude failed and "
                "infeasible runs.",
                "",
                "## 4. Methodological Notes & Limitations",
                "1. **Cost Comparability:** Dijkstra and A* compute optimal static routes over "
                "identical non-negative road graph edge costs.",
                "2. **Adaptive vs. Static:** Adaptive routing evaluates real-time edge congestion "
                "and dynamically updates routes during simulation ticks.",
                "3. **Planning Wall-Clock Time:** Planning duration measures real compute time on "
                "the test machine and naturally exhibits slight hardware-level variation.",
                "4. **Simulation Travel Time:** Simulation travel time reflects virtual elapsed "
                "seconds in the deterministic AMAPP kinematic simulation engine.",
                "",
            ]
        )

        return "\n".join(lines)

    def export_all(
        self,
        report: BenchmarkRunReport,
        output_dir: Path | str,
    ) -> dict[str, Path]:
        """Export JSON, CSVs, and Markdown summary report into the specified directory."""
        json_path = self.export_json(report, output_dir, "benchmark_results.json")
        trials_path = self.export_trials_csv(report, output_dir, "trials.csv")
        summary_path = self.export_summary_csv(report, output_dir, "summary.csv")

        # Export markdown report
        md_content = self.generate_report_markdown(report)
        md_path = self._validate_and_resolve_path(output_dir, "summary_report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return {
            "json": json_path,
            "trials_csv": trials_path,
            "summary_csv": summary_path,
            "report_md": md_path,
        }
