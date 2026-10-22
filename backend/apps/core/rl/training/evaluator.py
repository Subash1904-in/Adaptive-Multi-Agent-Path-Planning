"""Evaluation and baseline comparison suite for trained RL models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

import numpy as np

from apps.core.benchmarking.models import BenchmarkStatus, BenchmarkTrialResult
from apps.core.rl.adapter import (
    GreedyProgressTestPolicy,
    RandomTestPolicy,
    evaluate_rl_environment_episode,
)
from apps.core.rl.training.config import RLTrainingConfig
from apps.core.rl.training.policy import RLModelPolicy


@dataclass
class PolicyScenarioSummary:
    """Aggregated evaluation metrics for a policy on a specific scenario across seeds."""

    policy_id: str
    scenario_id: str
    total_trials: int
    completed_trials: int
    completion_rate_pct: float
    mean_travel_time_s: Optional[float]
    median_travel_time_s: Optional[float]
    mean_route_length_m: Optional[float]
    mean_planning_duration_ms: float
    total_collisions: int
    total_near_misses: int
    trials: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report capturing held-out test results and baseline comparisons."""

    run_name: str
    algorithm: str
    trained_model_path: str
    evaluated_at: str
    train_seed: int
    eval_seeds: list[int]
    eval_scenarios: list[str]
    summaries: list[PolicyScenarioSummary] = field(default_factory=list)
    reproducibility_manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "algorithm": self.algorithm,
            "trained_model_path": self.trained_model_path,
            "evaluated_at": self.evaluated_at,
            "train_seed": self.train_seed,
            "eval_seeds": self.eval_seeds,
            "eval_scenarios": self.eval_scenarios,
            "summaries": [s.to_dict() for s in self.summaries],
            "reproducibility_manifest": self.reproducibility_manifest,
        }

    def to_markdown(self) -> str:
        """Render evaluation report as a clean Markdown summary table."""
        lines = [
            f"# Evaluation Report: {self.run_name}",
            f"- **Algorithm:** `{self.algorithm}`",
            f"- **Trained Model:** `{self.trained_model_path}`",
            f"- **Evaluated At:** {self.evaluated_at}",
            f"- **Train Seed:** `{self.train_seed}` | **Eval Seeds:** `{self.eval_seeds}`",
            "",
            "## Aggregate Policy Performance Comparison",
            "",
            "| Scenario | Policy / Baseline | Trials | Success % | Mean Time (s) | "
            "Median Time (s) | Collisions | Latency (ms) |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for s in self.summaries:
            mean_time_str = (
                f"{s.mean_travel_time_s:.2f}" if s.mean_travel_time_s is not None else "N/A"
            )
            median_time_str = (
                f"{s.median_travel_time_s:.2f}" if s.median_travel_time_s is not None else "N/A"
            )
            lines.append(
                f"| `{s.scenario_id}` | `{s.policy_id}` | {s.total_trials} | "
                f"{s.completion_rate_pct:.1f}% | {mean_time_str} | {median_time_str} | "
                f"{s.total_collisions} | {s.mean_planning_duration_ms:.2f} |"
            )
        lines.append("")
        return "\n".join(lines)


class RLBaselineEvaluator:
    """Evaluates trained RL models against baseline policies across held-out seeds."""

    def __init__(self, config: Optional[RLTrainingConfig] = None) -> None:
        self.config = config or RLTrainingConfig()

    def evaluate(
        self,
        trained_policy: Union[RLModelPolicy, str],
        eval_seeds: Optional[list[int]] = None,
        eval_scenarios: Optional[list[str]] = None,
        save_report: bool = True,
    ) -> EvaluationReport:
        """Run held-out evaluation across multiple seeds and benchmark scenarios.

        Args:
            trained_policy: RLModelPolicy instance or string path to saved .zip model.
            eval_seeds: Optional override for evaluation seeds.
            eval_scenarios: Optional override for scenario IDs.
            save_report: Whether to persist JSON and Markdown reports.

        Returns:
            EvaluationReport instance containing per-trial and aggregate results.
        """
        # Resolve policy
        if isinstance(trained_policy, str):
            policy_inst = RLModelPolicy.load(
                model_path=trained_policy,
                algorithm=self.config.algorithm,
                device=self.config.device,
            )
        else:
            policy_inst = trained_policy

        seeds = eval_seeds or self.config.eval_seeds
        scenarios = eval_scenarios or self.config.eval_scenarios

        summaries: list[PolicyScenarioSummary] = []
        now_str = datetime.now(timezone.utc).isoformat()

        # Policies to compare:
        # 1. Trained RL Model Policy
        # 2. Greedy Progress Heuristic Baseline
        # 3. Random Legal-Action Baseline
        policy_suite = [
            ("learned_rl_baseline", policy_inst),
            ("greedy_progress_baseline", GreedyProgressTestPolicy()),
            ("random_action_baseline", lambda seed: RandomTestPolicy(seed=seed)),
        ]

        for scenario_id in scenarios:
            for pol_id, pol_factory in policy_suite:
                trial_results: list[BenchmarkTrialResult] = []
                travel_times: list[float] = []
                route_lengths: list[float] = []
                planning_latencies: list[float] = []
                collisions = 0
                near_misses = 0
                completed_count = 0

                for idx, seed in enumerate(seeds):
                    if callable(pol_factory) and pol_id == "random_action_baseline":
                        active_pol = pol_factory(seed)
                    else:
                        active_pol = pol_factory

                    res = evaluate_rl_environment_episode(
                        scenario_id=scenario_id,
                        policy=active_pol,
                        seed=seed,
                        max_steps=self.config.max_steps,
                        decision_interval_ticks=self.config.decision_interval_ticks,
                        benchmark_run_id=f"eval_{self.config.run_name}_{pol_id}",
                        trial_index=idx,
                    )
                    trial_results.append(res)
                    planning_latencies.append(res.planning_duration_ms)
                    collisions += res.collision_count
                    near_misses += res.near_miss_count

                    if res.status == BenchmarkStatus.SUCCESS and res.travel_time_s is not None:
                        completed_count += 1
                        travel_times.append(res.travel_time_s)
                        if res.route_length_m is not None:
                            route_lengths.append(res.route_length_m)

                total_trials = len(seeds)
                completion_rate = (
                    (completed_count / total_trials * 100.0) if total_trials > 0 else 0.0
                )
                mean_tt = float(np.mean(travel_times)) if travel_times else None
                median_tt = float(np.median(travel_times)) if travel_times else None
                mean_dist = float(np.mean(route_lengths)) if route_lengths else None
                mean_lat = float(np.mean(planning_latencies)) if planning_latencies else 0.0

                summary = PolicyScenarioSummary(
                    policy_id=pol_id,
                    scenario_id=scenario_id,
                    total_trials=total_trials,
                    completed_trials=completed_count,
                    completion_rate_pct=completion_rate,
                    mean_travel_time_s=mean_tt,
                    median_travel_time_s=median_tt,
                    mean_route_length_m=mean_dist,
                    mean_planning_duration_ms=mean_lat,
                    total_collisions=collisions,
                    total_near_misses=near_misses,
                    trials=[t.to_dict() for t in trial_results],
                )
                summaries.append(summary)

        # Build final report
        model_path_str = policy_inst.model_path or "in_memory_model"
        report = EvaluationReport(
            run_name=self.config.run_name,
            algorithm=self.config.algorithm.value,
            trained_model_path=model_path_str,
            evaluated_at=now_str,
            train_seed=self.config.train_seed,
            eval_seeds=seeds,
            eval_scenarios=scenarios,
            summaries=summaries,
            reproducibility_manifest={
                "training_config": self.config.to_dict(),
                "eval_seeds": seeds,
                "eval_scenarios": scenarios,
            },
        )

        if save_report:
            out_dir = self.config.get_run_output_dir()
            out_dir.mkdir(parents=True, exist_ok=True)
            json_path = out_dir / "evaluation_report.json"
            md_path = out_dir / "evaluation_summary.md"

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report.to_markdown())

        return report
