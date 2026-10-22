"""Benchmark execution engine orchestrating standardized scenarios and statistics."""

from __future__ import annotations

import math
import platform
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from apps.core.benchmarking.adapters import AlgorithmRegistry
from apps.core.benchmarking.exceptions import (
    BenchmarkExecutionError,
)
from apps.core.benchmarking.models import (
    BenchmarkAggregateResult,
    BenchmarkRunReport,
    BenchmarkStatus,
    BenchmarkTrialResult,
    SeedPolicy,
)
from apps.core.benchmarking.scenarios import BenchmarkScenarioRegistry
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.exceptions import UnreachableDestinationError
from apps.core.scenarios.models import RunConfig, TerminationReason
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.telemetry.fingerprint import get_git_commit_sha


def _compute_mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _compute_median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _compute_std(values: Sequence[float]) -> Optional[float]:
    if not values or len(values) < 2:
        return 0.0 if values else None
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _compute_percentile(values: Sequence[float], percentile: float) -> Optional[float]:
    """Calculate percentile using linear interpolation between closest ranks."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    floor_k = math.floor(k)
    ceil_k = math.ceil(k)
    if floor_k == ceil_k:
        return sorted_vals[int(k)]
    d0 = sorted_vals[floor_k] * (ceil_k - k)
    d1 = sorted_vals[ceil_k] * (k - floor_k)
    return d0 + d1


class BenchmarkRunner:
    """Orchestrates reproducible scenario-algorithm benchmarks, metric gathering, and statistics."""

    def __init__(
        self,
        algorithm_registry: Optional[AlgorithmRegistry] = None,
        scenario_registry: Optional[BenchmarkScenarioRegistry] = None,
        seed_policy: Optional[SeedPolicy] = None,
    ) -> None:
        self.algorithms = algorithm_registry or AlgorithmRegistry.get_default_registry()
        self.scenarios = scenario_registry or BenchmarkScenarioRegistry.get_default_registry()
        self.seed_policy = seed_policy or SeedPolicy()

    def run_trial(
        self,
        scenario_id: str,
        algorithm_id: str,
        trial_index: int,
        seed: int,
        benchmark_run_id: str,
        max_ticks_override: Optional[int] = None,
    ) -> BenchmarkTrialResult:
        """Execute a single scenario-algorithm benchmark trial with strict isolation."""
        scenario_def = self.scenarios.get(scenario_id)
        adapter = self.algorithms.get(algorithm_id)

        # Delegate to specialized trial executor if implemented
        # (e.g. LearnedRoutingBenchmarkAdapter)
        if hasattr(adapter, "execute_trial"):
            return adapter.execute_trial(
                scenario_id=scenario_id,
                trial_index=trial_index,
                seed=seed,
                benchmark_run_id=benchmark_run_id,
                max_ticks_override=max_ticks_override,
            )

        started_at = datetime.now(timezone.utc).isoformat()

        # 1. Instantiate isolated scenario definition with explicit seed
        base_scenario = scenario_def.create_scenario(seed=seed)
        configured_scenario = adapter.configure_scenario(base_scenario)

        # 2. Evaluate initial routing plan for the primary vehicle
        route_feasible = False
        route_cost: Optional[float] = None
        route_length_m: Optional[float] = None
        planning_duration_ms: float = 0.0

        road_graph = ScenarioBuilder(configured_scenario)._resolve_road_graph()
        if configured_scenario.vehicles:
            primary_vehicle = configured_scenario.vehicles[0]
            routing_res, planning_duration_ms = adapter.plan_initial_route(
                road_graph=road_graph,
                start_node_id=primary_vehicle.start_node_id,
                destination_node_id=primary_vehicle.destination_node_id,
                cost_mode=primary_vehicle.cost_mode,
                closed_edge_ids=set(primary_vehicle.closed_edge_ids),
            )
            if routing_res is not None and routing_res.success:
                route_feasible = True
                route_cost = routing_res.objective_cost
                route_length_m = routing_res.total_distance_m
            else:
                route_feasible = False
        else:
            route_feasible = True

        # 3. If route is not feasible and unreachable vehicles disallowed, record infeasible trial
        if not route_feasible and not configured_scenario.allow_unreachable_vehicles:
            completed_at = datetime.now(timezone.utc).isoformat()
            return BenchmarkTrialResult(
                benchmark_run_id=benchmark_run_id,
                scenario_id=scenario_id,
                scenario_version=scenario_def.version,
                algorithm_id=adapter.algorithm_id,
                algorithm_version=adapter.version,
                seed=seed,
                trial_index=trial_index,
                status=BenchmarkStatus.INFEASIBLE,
                route_feasible=False,
                route_cost=None,
                route_length_m=None,
                planning_duration_ms=planning_duration_ms,
                simulation_duration_s=0.0,
                simulation_ticks=0,
                travel_time_s=None,
                completed_trips=0,
                total_trips=len(configured_scenario.vehicles),
                completion_rate_pct=0.0,
                collision_count=0,
                near_miss_count=0,
                intersection_crossings=0,
                reroutes_evaluated=0,
                reroutes_accepted=0,
                messages_sent=0,
                messages_delivered=0,
                pdr=None,
                incident_count=0,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason="No feasible route exists from origin to destination.",
                metadata={"is_adaptive": adapter.is_adaptive},
            )

        # 4. Execute simulation run under ScenarioRunner
        run_config = None
        if max_ticks_override is not None:
            run_config = RunConfig(
                max_ticks=max_ticks_override,
                stop_on_all_arrived=configured_scenario.stop_on_all_arrived,
                seed=seed,
            )

        try:
            runner = ScenarioRunner.create(scenario=configured_scenario, run_config=run_config)
            exec_result = runner.run_to_completion()
        except UnreachableDestinationError as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            return BenchmarkTrialResult(
                benchmark_run_id=benchmark_run_id,
                scenario_id=scenario_id,
                scenario_version=scenario_def.version,
                algorithm_id=adapter.algorithm_id,
                algorithm_version=adapter.version,
                seed=seed,
                trial_index=trial_index,
                status=BenchmarkStatus.INFEASIBLE,
                route_feasible=False,
                route_cost=None,
                route_length_m=None,
                planning_duration_ms=planning_duration_ms,
                simulation_duration_s=0.0,
                simulation_ticks=0,
                travel_time_s=None,
                completed_trips=0,
                total_trips=len(configured_scenario.vehicles),
                completion_rate_pct=0.0,
                collision_count=0,
                near_miss_count=0,
                intersection_crossings=0,
                reroutes_evaluated=0,
                reroutes_accepted=0,
                messages_sent=0,
                messages_delivered=0,
                pdr=None,
                incident_count=0,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason=f"Unreachable destination partition: {exc}",
                metadata={"is_adaptive": adapter.is_adaptive},
            )
        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            return BenchmarkTrialResult(
                benchmark_run_id=benchmark_run_id,
                scenario_id=scenario_id,
                scenario_version=scenario_def.version,
                algorithm_id=adapter.algorithm_id,
                algorithm_version=adapter.version,
                seed=seed,
                trial_index=trial_index,
                status=BenchmarkStatus.FAILED,
                route_feasible=route_feasible,
                route_cost=route_cost,
                route_length_m=route_length_m,
                planning_duration_ms=planning_duration_ms,
                simulation_duration_s=0.0,
                simulation_ticks=0,
                travel_time_s=None,
                completed_trips=0,
                total_trips=len(configured_scenario.vehicles),
                completion_rate_pct=0.0,
                collision_count=0,
                near_miss_count=0,
                intersection_crossings=0,
                reroutes_evaluated=0,
                reroutes_accepted=0,
                messages_sent=0,
                messages_delivered=0,
                pdr=None,
                incident_count=0,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason=f"Scenario execution exception: {exc}",
                metadata={"is_adaptive": adapter.is_adaptive},
            )

        completed_at = datetime.now(timezone.utc).isoformat()
        metrics = exec_result.metrics_summary or {}

        # Extract authoritative subsystem metrics
        rout_m = metrics.get("routing", {})
        comm_m = metrics.get("communication", {})
        coord_m = metrics.get("coordination", {})
        safe_m = metrics.get("safety", {})
        inc_m = metrics.get("incidents", {})

        completed_trips = exec_result.arrived_count
        total_trips = exec_result.total_vehicles
        completion_rate = (completed_trips / total_trips * 100.0) if total_trips > 0 else 100.0

        collision_count = safe_m.get("actual_collisions", 0)
        near_miss_count = safe_m.get("near_misses", 0)
        intersection_crossings = coord_m.get("conflicts_resolved", 0) + coord_m.get(
            "yield_actions", 0
        )
        reroutes_eval = rout_m.get("reroutes_evaluated", 0)
        reroutes_acc = rout_m.get("reroutes_accepted", 0)
        msgs_sent = comm_m.get("messages_sent", 0)
        msgs_delivered = comm_m.get("messages_delivered", 0)
        pdr = comm_m.get("packet_delivery_ratio")

        # Determine travel time (only meaningful when at least one trip completed)
        travel_time_s: Optional[float] = None
        if completed_trips > 0:
            travel_time_s = exec_result.elapsed_time_s

        # Determine status
        if not route_feasible:
            status = BenchmarkStatus.INFEASIBLE
            failure_reason = "No traversable path from origin to destination."
        elif (
            exec_result.termination_reason == TerminationReason.MAX_TICKS_REACHED
            and completed_trips == 0
            and total_trips > 0
        ):
            status = BenchmarkStatus.TIMEOUT
            failure_reason = (
                f"Max ticks limit reached ({exec_result.completed_ticks}) "
                "before any vehicle arrived."
            )
        elif (
            not exec_result.is_success or exec_result.termination_reason == TerminationReason.FAILED
        ):
            status = BenchmarkStatus.FAILED
            failure_reason = exec_result.error_message or "Simulation failed."
        else:
            status = BenchmarkStatus.SUCCESS
            failure_reason = None

        return BenchmarkTrialResult(
            benchmark_run_id=benchmark_run_id,
            scenario_id=scenario_id,
            scenario_version=scenario_def.version,
            algorithm_id=adapter.algorithm_id,
            algorithm_version=adapter.version,
            seed=seed,
            trial_index=trial_index,
            status=status,
            route_feasible=route_feasible,
            route_cost=route_cost,
            route_length_m=route_length_m,
            planning_duration_ms=planning_duration_ms,
            simulation_duration_s=exec_result.elapsed_time_s,
            simulation_ticks=exec_result.completed_ticks,
            travel_time_s=travel_time_s,
            completed_trips=completed_trips,
            total_trips=total_trips,
            completion_rate_pct=completion_rate,
            collision_count=collision_count,
            near_miss_count=near_miss_count,
            intersection_crossings=intersection_crossings,
            reroutes_evaluated=reroutes_eval,
            reroutes_accepted=reroutes_acc,
            messages_sent=msgs_sent,
            messages_delivered=msgs_delivered,
            pdr=pdr,
            incident_count=inc_m.get("total_incidents_registered", 0),
            started_at=started_at,
            completed_at=completed_at,
            failure_reason=failure_reason,
            metadata={
                "is_adaptive": adapter.is_adaptive,
                "termination_reason": (
                    exec_result.termination_reason.value
                    if hasattr(exec_result.termination_reason, "value")
                    else str(exec_result.termination_reason)
                ),
            },
        )

    def compute_aggregates(
        self,
        scenario_id: str,
        algorithm_id: str,
        trials: Sequence[BenchmarkTrialResult],
    ) -> BenchmarkAggregateResult:
        """Compute statistical summary for a pair without conflating failures."""
        pair_trials = [
            t for t in trials if t.scenario_id == scenario_id and t.algorithm_id == algorithm_id
        ]
        total_trials = len(pair_trials)
        if total_trials == 0:
            raise BenchmarkExecutionError(
                f"Cannot compute aggregates: no trials found for ({scenario_id}, {algorithm_id})."
            )

        successful_trials = sum(1 for t in pair_trials if t.status == BenchmarkStatus.SUCCESS)
        failed_trials = sum(
            1 for t in pair_trials if t.status in (BenchmarkStatus.FAILED, BenchmarkStatus.TIMEOUT)
        )
        infeasible_trials = sum(1 for t in pair_trials if t.status == BenchmarkStatus.INFEASIBLE)
        route_success_count = sum(1 for t in pair_trials if t.route_feasible)
        route_success_rate = (route_success_count / total_trials) * 100.0

        # Strict isolation: failed and infeasible trials are NEVER treated as zero-cost routes
        valid_cost_samples = [
            t.route_cost
            for t in pair_trials
            if t.route_cost is not None and t.status == BenchmarkStatus.SUCCESS
        ]
        valid_length_samples = [
            t.route_length_m
            for t in pair_trials
            if t.route_length_m is not None and t.status == BenchmarkStatus.SUCCESS
        ]
        planning_duration_samples = [t.planning_duration_ms for t in pair_trials]
        valid_travel_time_samples = [
            t.travel_time_s
            for t in pair_trials
            if t.travel_time_s is not None and t.status == BenchmarkStatus.SUCCESS
        ]
        valid_pdr_samples = [t.pdr for t in pair_trials if t.pdr is not None]

        # Route cost statistics
        mean_cost = _compute_mean(valid_cost_samples)
        median_cost = _compute_median(valid_cost_samples)
        std_cost = _compute_std(valid_cost_samples)
        min_cost = min(valid_cost_samples) if valid_cost_samples else None
        max_cost = max(valid_cost_samples) if valid_cost_samples else None

        # Route length statistics
        mean_len = _compute_mean(valid_length_samples)
        median_len = _compute_median(valid_length_samples)

        # Planning duration statistics
        mean_plan_ms = _compute_mean(planning_duration_samples) or 0.0
        median_plan_ms = _compute_median(planning_duration_samples) or 0.0

        # Travel time statistics
        mean_travel = _compute_mean(valid_travel_time_samples)
        median_travel = _compute_median(valid_travel_time_samples)
        p90_travel = _compute_percentile(valid_travel_time_samples, 90.0)
        p95_travel = _compute_percentile(valid_travel_time_samples, 95.0)

        # Aggregate cumulative event counts across all trials
        tot_completed_trips = sum(t.completed_trips for t in pair_trials)
        tot_trips = sum(t.total_trips for t in pair_trials)
        overall_comp_rate = (tot_completed_trips / tot_trips * 100.0) if tot_trips > 0 else 100.0

        tot_collisions = sum(t.collision_count for t in pair_trials)
        tot_near_misses = sum(t.near_miss_count for t in pair_trials)
        tot_crossings = sum(t.intersection_crossings for t in pair_trials)
        tot_reroutes = sum(t.reroutes_accepted for t in pair_trials)
        mean_pdr = _compute_mean(valid_pdr_samples)

        sample_counts = {
            "total_trials": total_trials,
            "route_cost": len(valid_cost_samples),
            "route_length_m": len(valid_length_samples),
            "planning_duration_ms": len(planning_duration_samples),
            "travel_time_s": len(valid_travel_time_samples),
            "pdr": len(valid_pdr_samples),
        }

        return BenchmarkAggregateResult(
            scenario_id=scenario_id,
            algorithm_id=algorithm_id,
            total_trials=total_trials,
            successful_trials=successful_trials,
            failed_trials=failed_trials,
            infeasible_trials=infeasible_trials,
            route_success_rate_pct=route_success_rate,
            mean_route_cost=mean_cost,
            median_route_cost=median_cost,
            std_route_cost=std_cost,
            min_route_cost=min_cost,
            max_route_cost=max_cost,
            mean_route_length_m=mean_len,
            median_route_length_m=median_len,
            mean_planning_duration_ms=mean_plan_ms,
            median_planning_duration_ms=median_plan_ms,
            mean_travel_time_s=mean_travel,
            median_travel_time_s=median_travel,
            p90_travel_time_s=p90_travel,
            p95_travel_time_s=p95_travel,
            total_completed_trips=tot_completed_trips,
            total_trips=tot_trips,
            overall_completion_rate_pct=overall_comp_rate,
            total_collisions=tot_collisions,
            total_near_misses=tot_near_misses,
            total_intersection_crossings=tot_crossings,
            mean_pdr=mean_pdr,
            total_reroutes_accepted=tot_reroutes,
            sample_counts=sample_counts,
        )

    def run_suite(
        self,
        algorithms: Sequence[str],
        scenarios: Sequence[str],
        trials_per_pair: int = 1,
        base_seed: int = 42,
        max_ticks_override: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> BenchmarkRunReport:
        """Execute a full matrix benchmark suite and return an authoritative report."""
        if not algorithms:
            raise BenchmarkExecutionError("Algorithms list cannot be empty.")
        if not scenarios:
            raise BenchmarkExecutionError("Scenarios list cannot be empty.")
        if trials_per_pair < 1:
            raise BenchmarkExecutionError(f"trials_per_pair must be >= 1, got {trials_per_pair}.")

        # Pre-validate algorithms and scenarios before starting executions
        validated_algorithms: list[str] = []
        for aid in algorithms:
            adapter = self.algorithms.get(aid)
            validated_algorithms.append(adapter.algorithm_id)

        validated_scenarios: list[str] = []
        for sid in scenarios:
            sdef = self.scenarios.get(sid)
            validated_scenarios.append(sdef.scenario_id)

        seed_policy = SeedPolicy(base_seed=base_seed)
        benchmark_run_id = run_id or f"bench_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()

        all_trials: list[BenchmarkTrialResult] = []

        # Iterate deterministically through scenarios, algorithms, and trials
        for sid in validated_scenarios:
            for aid in validated_algorithms:
                for trial_idx in range(trials_per_pair):
                    trial_seed = seed_policy.derive_seed(trial_idx)
                    trial_result = self.run_trial(
                        scenario_id=sid,
                        algorithm_id=aid,
                        trial_index=trial_idx,
                        seed=trial_seed,
                        benchmark_run_id=benchmark_run_id,
                        max_ticks_override=max_ticks_override,
                    )
                    all_trials.append(trial_result)

        # Compute aggregates per (scenario, algorithm)
        aggregates: list[BenchmarkAggregateResult] = []
        for sid in validated_scenarios:
            for aid in validated_algorithms:
                agg = self.compute_aggregates(
                    scenario_id=sid,
                    algorithm_id=aid,
                    trials=all_trials,
                )
                aggregates.append(agg)

        # Record environment metadata for auditability
        env_metadata = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "os": sys.platform,
        }

        # Persist benchmark suite if persistence is enabled
        try:
            from apps.core.persistence.service import default_persistence_service

            default_persistence_service.record_benchmark_suite(
                benchmark_run_id=benchmark_run_id,
                name=f"Benchmark Suite {benchmark_run_id}",
                scenario_ids=validated_scenarios,
                algorithm_ids=validated_algorithms,
                trial_count=trials_per_pair,
                base_seed=base_seed,
                trial_results=all_trials,
                parameters={"max_ticks_override": max_ticks_override},
            )
        except Exception:
            # Safe non-blocking fallback
            pass

        return BenchmarkRunReport(
            benchmark_run_id=benchmark_run_id,
            created_at=created_at,
            commit_sha=get_git_commit_sha(),
            base_seed=base_seed,
            trials_per_pair=trials_per_pair,
            scenarios_evaluated=validated_scenarios,
            algorithms_evaluated=validated_algorithms,
            trials=all_trials,
            aggregates=aggregates,
            environment_metadata=env_metadata,
        )
