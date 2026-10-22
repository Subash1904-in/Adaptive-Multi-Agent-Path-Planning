"""Performance smoke tests with environment-tolerant thresholds.

Verifies computational complexity and latency upper bounds on noisy CI workers:
1. Dijkstra and A* pathfinding computation bounds (< 0.5s).
2. Multi-agent simulation step computation bounds (< 0.5s).
3. Cross-subsystem metrics and analytics aggregation bounds (< 0.5s).
4. Scenario validation and builder assembly bounds (< 0.5s).
"""

from __future__ import annotations

import gc
import time
import tracemalloc

from apps.core.communication.discovery import SpatialPeerDiscovery
from apps.core.communication.models import CommunicationConfig
from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing import CostMode, astar_search, dijkstra_search
from apps.core.safety.detection import CollisionDetector
from apps.core.safety.models import SafetyConfig
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_multi_vehicle_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import validate_scenario
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.world import WorldState
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

    def test_phase38_scaling_collision_detection_bounds(self) -> None:
        """Pairwise collision detection for 50 active vehicles (1,225 pairs) runs within 250ms."""
        detector = CollisionDetector(SafetyConfig(enabled=True))
        cfg = CityGridConfig(rows=5, cols=5, spacing_m=50.0, bidirectional=True, seed=42)
        grid = generate_synthetic_city_grid(cfg)

        agents = []
        for i in range(50):
            v = Vehicle(
                id=f"smoke_veh_{i:03d}",
                vehicle_type=VehicleType.STANDARD,
                state=VehicleState.EN_ROUTE,
                position=Position2D(x=float((i % 10) * 15), y=float((i // 10) * 15)),
                heading_rad=0.0,
                speed_mps=10.0,
            )
            ag = VehicleAgent(vehicle=v, road_graph=grid)
            agents.append(ag)

        t0 = time.perf_counter()
        conflicts = detector.detect_all_conflicts(agents)
        duration_s = time.perf_counter() - t0

        assert len(conflicts) == 50 * 49 // 2  # exactly 1,225 pairs evaluated
        assert duration_s < 0.25, f"Collision detection took {duration_s:.4f}s (budget: 0.25s)"

    def test_phase38_scaling_multi_agent_step_bounds(self) -> None:
        """A full authoritative engine step with 50 active vehicles executes within 250ms."""
        cfg = CityGridConfig(rows=10, cols=10, spacing_m=50.0, bidirectional=True, seed=42)
        grid = generate_synthetic_city_grid(cfg)
        world = WorldState(
            road_graph=grid,
            communication_config=CommunicationConfig(enabled=True),
            safety_config=SafetyConfig(enabled=True),
        )

        for i in range(50):
            v = Vehicle(
                id=f"step_veh_{i:03d}",
                vehicle_type=VehicleType.STANDARD,
                position=Position2D(x=float((i % 10) * 50), y=0.0),
                heading_rad=0.0,
                speed_mps=8.0,
            )
            route_res = astar_search(
                grid, f"node_r{i % 10}_c0", f"node_r{i % 10}_c9", CostMode.DISTANCE
            )
            ag = VehicleAgent(vehicle=v, road_graph=grid, route=route_res.route)
            ag.start()
            world.add_agent(ag)

        engine = SimulationEngine(world)
        engine.resume()

        t0 = time.perf_counter()
        result = engine.step()
        duration_s = time.perf_counter() - t0

        assert result.tick == 1
        assert duration_s < 0.25, f"50-vehicle engine step took {duration_s:.4f}s (budget: 0.25s)"

    def test_phase38_incident_adaptive_rerouting_bounds(self) -> None:
        """Adaptive rerouting on a 10x10 grid with closure executes within 50ms."""
        cfg = CityGridConfig(rows=10, cols=10, spacing_m=50.0, bidirectional=True, seed=42)
        grid = generate_synthetic_city_grid(cfg)
        start = "node_r0_c0"
        goal = "node_r9_c9"
        base_res = astar_search(grid, start, goal, CostMode.TRAVEL_TIME)
        closed = {base_res.edge_ids[1]}

        t0 = time.perf_counter()
        rerouted = astar_search(grid, start, goal, CostMode.TRAVEL_TIME, closed_edge_ids=closed)
        duration_s = time.perf_counter() - t0

        assert rerouted.success is True
        assert base_res.edge_ids[1] not in rerouted.edge_ids
        assert duration_s < 0.05, f"Incident rerouting took {duration_s:.4f}s (budget: 0.05s)"

    def test_phase38_spatial_peer_discovery_scaling_bounds(self) -> None:
        """Spatial V2V discovery for 50 vehicles completes within 50ms."""
        discovery = SpatialPeerDiscovery(range_m=50.0)
        candidates = {
            f"veh_{i:03d}": Position2D(x=float((i % 10) * 15), y=float((i // 10) * 15))
            for i in range(50)
        }

        t0 = time.perf_counter()
        for vid, pos in candidates.items():
            discovery.find_peers(vid, pos, candidates)
        duration_s = time.perf_counter() - t0

        assert duration_s < 0.05, f"All-pairs V2V discovery took {duration_s:.4f}s (budget: 0.05s)"

    def test_phase38_repeated_simulation_lifecycle_memory_stability(self) -> None:
        """Repeated simulation creation, stepping, and teardown does not leak memory."""
        gc.collect()
        tracemalloc.start()
        snap1 = tracemalloc.take_snapshot()

        cfg = CityGridConfig(rows=5, cols=5, spacing_m=50.0, bidirectional=True, seed=42)
        grid = generate_synthetic_city_grid(cfg)
        for _ in range(5):
            world = WorldState(
                road_graph=grid,
                communication_config=CommunicationConfig(enabled=True),
            )
            for i in range(15):
                v = Vehicle(
                    id=f"mem_veh_{i:03d}",
                    vehicle_type=VehicleType.STANDARD,
                    position=Position2D(x=float((i % 5) * 50), y=0.0),
                    heading_rad=0.0,
                    speed_mps=5.0,
                )
                r_res = astar_search(
                    grid, f"node_r{i % 5}_c0", f"node_r{i % 5}_c4", CostMode.DISTANCE
                )
                ag = VehicleAgent(vehicle=v, road_graph=grid, route=r_res.route)
                ag.start()
                world.add_agent(ag)
            eng = SimulationEngine(world)
            eng.resume()
            for _ in range(10):
                eng.step()
            eng.reset()
            del eng
            del world

        gc.collect()
        snap2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap2.compare_to(snap1, "lineno")
        net_diff_kb = sum(s.size_diff for s in stats if s.size_diff > 0) / 1024.0
        assert net_diff_kb < 1024.0, f"Memory growth exceeded limit: {net_diff_kb:.2f} KB"
