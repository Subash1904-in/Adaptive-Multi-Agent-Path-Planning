"""Domain models and value types for the AMAPP benchmarking subsystem."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class BenchmarkStatus(str, Enum):
    """Execution status for an individual benchmark trial."""

    SUCCESS = "success"
    INFEASIBLE = "infeasible"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class SeedPolicy:
    """Deterministic seed allocation policy for repeatable benchmark trials."""

    base_seed: int = 42

    def derive_seed(self, trial_index: int) -> int:
        """Derive a deterministic integer seed for a given trial index."""
        if trial_index < 0:
            raise ValueError(f"trial_index must be non-negative, got {trial_index}.")
        # Use prime multiplier to ensure well-spaced seeds within 31-bit integer bounds
        return (self.base_seed + trial_index * 1000) % 2147483647


@dataclass
class BenchmarkTrialResult:
    """Authoritative result record for a single scenario-algorithm benchmark trial."""

    benchmark_run_id: str
    scenario_id: str
    scenario_version: str
    algorithm_id: str
    algorithm_version: str
    seed: int
    trial_index: int
    status: BenchmarkStatus
    route_feasible: bool
    route_cost: Optional[float]
    route_length_m: Optional[float]
    planning_duration_ms: float
    simulation_duration_s: float
    simulation_ticks: int
    travel_time_s: Optional[float]
    completed_trips: int
    total_trips: int
    completion_rate_pct: Optional[float]
    collision_count: int
    near_miss_count: int
    intersection_crossings: int
    reroutes_evaluated: int
    reroutes_accepted: int
    messages_sent: int
    messages_delivered: int
    pdr: Optional[float]
    incident_count: int
    started_at: str
    completed_at: str
    failure_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert trial result to a JSON-serializable dictionary."""
        return {
            "benchmark_run_id": self.benchmark_run_id,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "algorithm_id": self.algorithm_id,
            "algorithm_version": self.algorithm_version,
            "seed": self.seed,
            "trial_index": self.trial_index,
            "status": self.status.value
            if isinstance(self.status, BenchmarkStatus)
            else str(self.status),
            "route_feasible": self.route_feasible,
            "route_cost": round(self.route_cost, 4)
            if self.route_cost is not None and math.isfinite(self.route_cost)
            else None,
            "route_length_m": round(self.route_length_m, 2)
            if self.route_length_m is not None
            else None,
            "planning_duration_ms": round(self.planning_duration_ms, 3),
            "simulation_duration_s": round(self.simulation_duration_s, 2),
            "simulation_ticks": self.simulation_ticks,
            "travel_time_s": round(self.travel_time_s, 2)
            if self.travel_time_s is not None
            else None,
            "completed_trips": self.completed_trips,
            "total_trips": self.total_trips,
            "completion_rate_pct": round(self.completion_rate_pct, 2)
            if self.completion_rate_pct is not None
            else None,
            "collision_count": self.collision_count,
            "near_miss_count": self.near_miss_count,
            "intersection_crossings": self.intersection_crossings,
            "reroutes_evaluated": self.reroutes_evaluated,
            "reroutes_accepted": self.reroutes_accepted,
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "pdr": round(self.pdr, 4) if self.pdr is not None else None,
            "incident_count": self.incident_count,
            "failure_reason": self.failure_reason,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class BenchmarkAggregateResult:
    """Statistical summary aggregating multiple trials for a specific (scenario, algorithm) pair."""

    scenario_id: str
    algorithm_id: str
    total_trials: int
    successful_trials: int
    failed_trials: int
    infeasible_trials: int
    route_success_rate_pct: float
    mean_route_cost: Optional[float]
    median_route_cost: Optional[float]
    std_route_cost: Optional[float]
    min_route_cost: Optional[float]
    max_route_cost: Optional[float]
    mean_route_length_m: Optional[float]
    median_route_length_m: Optional[float]
    mean_planning_duration_ms: float
    median_planning_duration_ms: float
    mean_travel_time_s: Optional[float]
    median_travel_time_s: Optional[float]
    p90_travel_time_s: Optional[float]
    p95_travel_time_s: Optional[float]
    total_completed_trips: int
    total_trips: int
    overall_completion_rate_pct: Optional[float]
    total_collisions: int
    total_near_misses: int
    total_intersection_crossings: int
    mean_pdr: Optional[float]
    total_reroutes_accepted: int
    sample_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert aggregate result to a JSON-serializable dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "algorithm_id": self.algorithm_id,
            "total_trials": self.total_trials,
            "successful_trials": self.successful_trials,
            "failed_trials": self.failed_trials,
            "infeasible_trials": self.infeasible_trials,
            "route_success_rate_pct": round(self.route_success_rate_pct, 2),
            "mean_route_cost": round(self.mean_route_cost, 4)
            if self.mean_route_cost is not None
            else None,
            "median_route_cost": round(self.median_route_cost, 4)
            if self.median_route_cost is not None
            else None,
            "std_route_cost": round(self.std_route_cost, 4)
            if self.std_route_cost is not None
            else None,
            "min_route_cost": round(self.min_route_cost, 4)
            if self.min_route_cost is not None
            else None,
            "max_route_cost": round(self.max_route_cost, 4)
            if self.max_route_cost is not None
            else None,
            "mean_route_length_m": round(self.mean_route_length_m, 2)
            if self.mean_route_length_m is not None
            else None,
            "median_route_length_m": round(self.median_route_length_m, 2)
            if self.median_route_length_m is not None
            else None,
            "mean_planning_duration_ms": round(self.mean_planning_duration_ms, 3),
            "median_planning_duration_ms": round(self.median_planning_duration_ms, 3),
            "mean_travel_time_s": round(self.mean_travel_time_s, 2)
            if self.mean_travel_time_s is not None
            else None,
            "median_travel_time_s": round(self.median_travel_time_s, 2)
            if self.median_travel_time_s is not None
            else None,
            "p90_travel_time_s": round(self.p90_travel_time_s, 2)
            if self.p90_travel_time_s is not None
            else None,
            "p95_travel_time_s": round(self.p95_travel_time_s, 2)
            if self.p95_travel_time_s is not None
            else None,
            "total_completed_trips": self.total_completed_trips,
            "total_trips": self.total_trips,
            "overall_completion_rate_pct": round(self.overall_completion_rate_pct, 2)
            if self.overall_completion_rate_pct is not None
            else None,
            "total_collisions": self.total_collisions,
            "total_near_misses": self.total_near_misses,
            "total_intersection_crossings": self.total_intersection_crossings,
            "mean_pdr": round(self.mean_pdr, 4) if self.mean_pdr is not None else None,
            "total_reroutes_accepted": self.total_reroutes_accepted,
            "sample_counts": dict(self.sample_counts),
        }


@dataclass
class BenchmarkRunReport:
    """Comprehensive execution report for a completed benchmark session."""

    benchmark_run_id: str
    created_at: str
    commit_sha: Optional[str]
    base_seed: int
    trials_per_pair: int
    scenarios_evaluated: list[str]
    algorithms_evaluated: list[str]
    trials: list[BenchmarkTrialResult] = field(default_factory=list)
    aggregates: list[BenchmarkAggregateResult] = field(default_factory=list)
    environment_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to a JSON-serializable dictionary."""
        return {
            "schema_version": "1.0.0",
            "benchmark_run_id": self.benchmark_run_id,
            "created_at": self.created_at,
            "commit_sha": self.commit_sha,
            "base_seed": self.base_seed,
            "trials_per_pair": self.trials_per_pair,
            "scenarios_evaluated": list(self.scenarios_evaluated),
            "algorithms_evaluated": list(self.algorithms_evaluated),
            "trials": [t.to_dict() for t in self.trials],
            "aggregates": [a.to_dict() for a in self.aggregates],
            "environment_metadata": dict(self.environment_metadata),
        }
