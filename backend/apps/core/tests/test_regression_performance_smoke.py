"""Performance smoke tests with environment-tolerant thresholds.

Verifies computational complexity and latency upper bounds on noisy CI workers:
1. Dijkstra and A* pathfinding computation bounds (< 0.5s).
2. Multi-agent simulation step computation bounds (< 0.5s).
3. Cross-subsystem metrics and analytics aggregation bounds (< 0.5s).
4. Scenario validation and builder assembly bounds (< 0.5s).
"""

from __future__ import annotations

import time

from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.routing import CostMode, astar_search, dijkstra_search
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_multi_vehicle_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import validate_scenario
from apps.core.telemetry.aggregation import MetricsAggregator


class TestPerformanceSmokeRegression:
    """Non-brittle performance smoke tests ensuring zero computational regressions."""

    def test_routing_pathfinding_performance_bounds(self) -> None:
        """Dijkstra and A* pathfinding on a 5x5 grid graph complete well within 500ms."""
        config = CityGridConfig(rows=5, cols=5, spacing_m=50.0, bidirectional=True, seed=42)
        grid = generate_synthetic_city_grid(config)

        start_node = "node_r0_c0"
        goal_node = "node_r4_c4"

        # Dijkstra benchmark
        t0 = time.perf_counter()
        d_res = dijkstra_search(grid, start_node, goal_node, CostMode.DISTANCE)
        d_duration = time.perf_counter() - t0
        assert d_res.success is True
        assert d_duration < 0.5, f"Dijkstra search exceeded smoke budget: {d_duration:.4f}s"

        # A* benchmark
        t1 = time.perf_counter()
        a_res = astar_search(grid, start_node, goal_node, CostMode.DISTANCE)
        a_duration = time.perf_counter() - t1
        assert a_res.success is True
        assert a_duration < 0.5, f"A* search exceeded smoke budget: {a_duration:.4f}s"

    def test_multi_agent_step_performance_bounds(self) -> None:
        """A single simulation step with multiple active vehicles executes within 500ms."""
        scenario = create_multi_vehicle_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scenario)

        t0 = time.perf_counter()
        runner.step()
        step_duration = time.perf_counter() - t0

        assert runner.current_tick == 1
        assert step_duration < 0.5, f"Simulation step exceeded smoke budget: {step_duration:.4f}s"

    def test_metrics_aggregation_performance_bounds(self) -> None:
        """Metrics aggregation across a multi-tick run completes within 500ms."""
        scenario = create_single_vehicle_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scenario)
        runner.run(ticks=10)

        t0 = time.perf_counter()
        agents = runner.world.get_agents()
        arrived = [a for a in agents if a.is_arrived]
        active = [a for a in agents if not a.is_arrived]
        MetricsAggregator.aggregate(
            tick_history=runner.tick_history,
            world=runner.world,
            total_vehicles=len(agents),
            arrived_vehicles=len(arrived),
            active_vehicles=len(active),
            terminal_state="RUNNING",
            termination_reason="STOPPED",
            elapsed_time_s=runner.engine.elapsed_time_s,
            time_step_s=runner.engine.time_step_s,
        )
        agg_duration = time.perf_counter() - t0

        assert len(runner.tick_history) == 10
        assert agg_duration < 0.5, f"Metrics aggregation exceeded smoke budget: {agg_duration:.4f}s"

    def test_scenario_validation_and_build_performance_bounds(self) -> None:
        """Validating and assembling a multi-vehicle scenario executes within 500ms."""
        scenario = create_multi_vehicle_scenario()

        t0 = time.perf_counter()
        validate_scenario(scenario)
        builder = ScenarioBuilder(scenario)
        context = builder.build()
        total_duration = time.perf_counter() - t0

        assert context.world is not None
        assert total_duration < 0.5, f"Scenario build exceeded smoke budget: {total_duration:.4f}s"
