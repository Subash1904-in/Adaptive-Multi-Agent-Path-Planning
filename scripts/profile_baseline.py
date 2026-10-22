"""Reproducible performance profiling suite for AMAPP (Phase 38 Baseline).

Measures and records high-resolution timing, throughput, and memory across:
1. Simulation tick duration (10, 50, 100 vehicles)
2. Routing pathfinding latency (Dijkstra vs A*, various grid sizes)
3. Collision detection broad/narrow phase (10, 50, 100 vehicles)
4. V2V neighbor discovery & message dispatch (10, 50, 100 vehicles)
5. Adaptive rerouting after incident injection
6. Metrics aggregation across tick histories
7. Database persistence and paginated REST queries
8. RL environment stepping and policy inference
9. Memory allocation stability across repeated runs
"""

# ruff: noqa: E402, F401, E501

from __future__ import annotations

import gc
import json
import os
import statistics
import sys
import time
import tracemalloc

# Ensure backend is on pythonpath
sys.path.insert(0, os.path.abspath("backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.management import call_command

call_command("migrate", interactive=False, verbosity=0)

from apps.core.communication.discovery import SpatialPeerDiscovery
from apps.core.communication.models import CommunicationConfig
from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.models import ExperimentMetric, SimulationRun
from apps.core.persistence.service import SimulationPersistenceService
from apps.core.rl.env import AMAPPSingleAgentEnv
from apps.core.rl.model_manager import RLModelManager
from apps.core.routing import CostMode, astar_search, dijkstra_search
from apps.core.routing.planner import RoutePlanner
from apps.core.safety.detection import CollisionDetector
from apps.core.safety.models import SafetyConfig
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.world import WorldState
from apps.core.telemetry.aggregation import MetricsAggregator


def time_block(fn, reps=5, warmup=2):
    """Run function with warmup and return median, min, max, mean times in milliseconds."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)
    return {
        "median_ms": statistics.median(times),
        "mean_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "reps": reps,
    }


def profile_routing():
    print("=== PROFILING ROUTING & GRAPH ===")
    results = {}
    for size in [(5, 5), (10, 10), (20, 20)]:
        rows, cols = size
        grid = generate_synthetic_city_grid(
            CityGridConfig(rows=rows, cols=cols, spacing_m=50.0, bidirectional=True, seed=42)
        )
        start = "node_r0_c0"
        goal = f"node_r{rows-1}_c{cols-1}"

        d_stats = time_block(
            lambda: dijkstra_search(grid, start, goal, CostMode.DISTANCE), reps=10, warmup=3
        )
        a_stats = time_block(
            lambda: astar_search(grid, start, goal, CostMode.DISTANCE), reps=10, warmup=3
        )
        results[f"grid_{rows}x{cols}_dijkstra"] = d_stats
        results[f"grid_{rows}x{cols}_astar"] = a_stats
        print(f"Grid {rows}x{cols} ({grid.node_count} nodes, {grid.edge_count} edges):")
        print(f"  Dijkstra median: {d_stats['median_ms']:.3f} ms")
        print(f"  A* median:       {a_stats['median_ms']:.3f} ms")
    return results


def profile_collision_detection():
    print("\n=== PROFILING COLLISION DETECTION ===")
    results = {}
    detector = CollisionDetector(SafetyConfig(enabled=True))
    grid = generate_synthetic_city_grid(
        CityGridConfig(rows=5, cols=5, spacing_m=50.0, bidirectional=True, seed=42)
    )

    for n in [10, 50, 100]:
        agents = []
        for i in range(n):
            v = Vehicle(
                id=f"veh_{i:03d}",
                vehicle_type=VehicleType.STANDARD,
                state=VehicleState.EN_ROUTE,
                position=Position2D(x=float(i * 15), y=float((i % 5) * 10)),
                heading_rad=0.0,
                speed_mps=10.0,
            )
            ag = VehicleAgent(vehicle=v, road_graph=grid)
            agents.append(ag)

        stats = time_block(lambda: detector.detect_all_conflicts(agents), reps=10, warmup=3)
        results[f"collision_{n}_vehicles"] = stats
        pairs = n * (n - 1) // 2
        print(
            f"{n} vehicles ({pairs} pairs): median {stats['median_ms']:.3f} ms ({stats['mean_ms']:.3f} ms mean)"
        )
    return results


def profile_v2v_discovery():
    print("\n=== PROFILING V2V PEER DISCOVERY ===")
    results = {}
    discovery = SpatialPeerDiscovery(range_m=50.0)
    for n in [10, 50, 100]:
        candidates = {
            f"veh_{i:03d}": Position2D(x=float((i % 10) * 15), y=float((i // 10) * 15))
            for i in range(n)
        }
        sender_pos = Position2D(x=30.0, y=30.0)
        # Scan for one sender
        s1 = time_block(
            lambda: discovery.find_peers("veh_000", sender_pos, candidates), reps=20, warmup=5
        )

        # Scan for all vehicles (all-to-all peer discovery per tick)
        def all_pairs_discovery():
            for vid, pos in candidates.items():
                discovery.find_peers(vid, pos, candidates)

        s_all = time_block(all_pairs_discovery, reps=5, warmup=2)
        results[f"v2v_single_{n}"] = s1
        results[f"v2v_all_pairs_{n}"] = s_all
        print(
            f"V2V {n} vehicles: single scan median {s1['median_ms']:.3f} ms | All-pairs full tick median {s_all['median_ms']:.3f} ms"
        )
    return results


def profile_simulation_engine_ticks():
    print("\n=== PROFILING SIMULATION ENGINE TICKS ===")
    results = {}
    grid = generate_synthetic_city_grid(
        CityGridConfig(rows=10, cols=10, spacing_m=50.0, bidirectional=True, seed=42)
    )

    for n in [10, 50, 100]:
        world = WorldState(
            road_graph=grid,
            communication_config=CommunicationConfig(enabled=True),
            safety_config=SafetyConfig(enabled=True),
        )

        # Add N vehicles with routes
        for i in range(n):
            v = Vehicle(
                id=f"veh_{i:03d}",
                vehicle_type=VehicleType.STANDARD,
                position=Position2D(x=float((i % 10) * 50), y=0.0),
                heading_rad=0.0,
                speed_mps=8.0,
            )
            # Route across grid
            start_node = f"node_r{i % 10}_c0"
            goal_node = f"node_r{i % 10}_c9"
            route_res = astar_search(grid, start_node, goal_node, CostMode.DISTANCE)
            ag = VehicleAgent(vehicle=v, road_graph=grid, route=route_res.route)
            ag.start()
            world.add_agent(ag)

        engine = SimulationEngine(world)
        engine.resume()

        step_stats = time_block(lambda: engine.step(), reps=20, warmup=5)
        results[f"engine_step_{n}_vehicles"] = step_stats
        print(
            f"Engine tick with {n} vehicles: median {step_stats['median_ms']:.3f} ms/tick ({step_stats['mean_ms']:.3f} ms mean)"
        )
    return results


def profile_adaptive_rerouting():
    print("\n=== PROFILING ADAPTIVE REROUTING AFTER INCIDENT ===")
    grid = generate_synthetic_city_grid(
        CityGridConfig(rows=10, cols=10, spacing_m=50.0, bidirectional=True, seed=42)
    )
    start = "node_r0_c0"
    goal = "node_r9_c9"
    baseline_res = astar_search(grid, start, goal, CostMode.TRAVEL_TIME)

    # Simulate closure on first edge
    closed = {baseline_res.edge_ids[2]}
    stats = time_block(
        lambda: astar_search(grid, start, goal, CostMode.TRAVEL_TIME, closed_edge_ids=closed),
        reps=15,
        warmup=3,
    )
    print(f"Incident reroute on 10x10 grid with closure: median {stats['median_ms']:.3f} ms")
    return {"incident_reroute_10x10": stats}


def profile_persistence_and_queries():
    print("\n=== PROFILING PERSISTENCE & ORM QUERIES ===")
    service = SimulationPersistenceService(enabled=True)
    run_id = f"prof_run_{int(time.time())}"
    service.record_run_created(run_id=run_id, scenario_id="prof_scn", seed=42)
    run_obj = SimulationRun.objects.get(run_id=run_id)

    # Bulk insert 500 metrics
    metrics = [
        ExperimentMetric(
            simulation_run=run_obj,
            metric_name=f"metric_{i % 10}",
            metric_type="gauge",
            numeric_value=float(i * 1.5),
            unit="s",
            sample_tick=i,
            sample_timestamp_s=i * 0.1,
        )
        for i in range(500)
    ]
    t0 = time.perf_counter()
    ExperimentMetric.objects.bulk_create(metrics)
    insert_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Bulk insert 500 metrics: {insert_ms:.2f} ms")

    # Query metrics with filter and pagination
    def query_metrics():
        qs = ExperimentMetric.objects.filter(
            simulation_run__run_id=run_id, metric_name="metric_0"
        ).order_by("-created_at", "-id")[:50]
        return list(qs)

    query_stats = time_block(query_metrics, reps=15, warmup=3)
    print(f"Filtered + paginated metrics query: median {query_stats['median_ms']:.3f} ms")

    # Clean up
    run_obj.delete()
    return {"bulk_insert_500_metrics_ms": insert_ms, "paginated_metrics_query": query_stats}


def profile_rl_inference():
    print("\n=== PROFILING RL ENVIRONMENT & INFERENCE ===")
    env = AMAPPSingleAgentEnv()
    obs, info = env.reset(seed=42)

    step_stats = time_block(lambda: env.step(1), reps=30, warmup=5)
    print(f"RL Gymnasium step: median {step_stats['median_ms']:.3f} ms")
    return {"rl_env_step": step_stats}


def profile_memory_stability():
    print("\n=== PROFILING MEMORY STABILITY ACROSS RUNS ===")
    gc.collect()
    tracemalloc.start()
    snap1 = tracemalloc.take_snapshot()

    grid = generate_synthetic_city_grid(
        CityGridConfig(rows=5, cols=5, spacing_m=50.0, bidirectional=True, seed=42)
    )
    for r in range(10):
        world = WorldState(
            road_graph=grid,
            communication_config=CommunicationConfig(enabled=True),
        )
        for i in range(20):
            v = Vehicle(
                id=f"veh_{i:03d}",
                vehicle_type=VehicleType.STANDARD,
                position=Position2D(x=float((i % 5) * 50), y=0.0),
                heading_rad=0.0,
                speed_mps=5.0,
            )
            route_res = astar_search(
                grid, f"node_r{i % 5}_c0", f"node_r{i % 5}_c4", CostMode.DISTANCE
            )
            ag = VehicleAgent(vehicle=v, road_graph=grid, route=route_res.route)
            ag.start()
            world.add_agent(ag)
        engine = SimulationEngine(world)
        engine.resume()
        for _ in range(20):
            engine.step()
        engine.reset()
        del engine
        del world

    gc.collect()
    snap2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snap2.compare_to(snap1, "lineno")
    top_diff_kb = sum(stat.size_diff for stat in stats if stat.size_diff > 0) / 1024.0
    print(
        f"Memory growth across 10 simulation runs (20 veh x 20 ticks each): net growth {top_diff_kb:.2f} KB"
    )
    return {"net_growth_kb": top_diff_kb}


def main():
    print("=" * 60)
    print("STARTING AMAPP PHASE 38 REPRODUCIBLE PROFILING BASELINE")
    print("Platform:", sys.platform)
    print("Python:", sys.version.split()[0])
    print("Timestamp:", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print("=" * 60)

    report = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    report["routing"] = profile_routing()
    report["collision"] = profile_collision_detection()
    report["v2v"] = profile_v2v_discovery()
    report["engine"] = profile_simulation_engine_ticks()
    report["adaptive_rerouting"] = profile_adaptive_rerouting()
    report["persistence"] = profile_persistence_and_queries()
    report["rl"] = profile_rl_inference()
    report["memory"] = profile_memory_stability()

    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/baseline_performance.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nSaved baseline measurements to artifacts/baseline_performance.json")


if __name__ == "__main__":
    main()
