"""Integration tests for safety subsystem, simulation engine, rollback, and scenario execution."""

import math
from unittest.mock import patch

import pytest

from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.models import (
    SafetyConfig,
)
from apps.core.scenarios.examples import (
    create_head_on_collision_avoidance_scenario,
    create_intersection_conflict_safety_scenario,
    create_rear_end_following_safety_scenario,
    create_unavoidable_collision_scenario,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.world import WorldState


def _build_test_corridor(length_m: float = 200.0) -> tuple[RoadGraph, Route, Route]:
    """Build a 2-node bidirectional corridor with forward and reverse routes."""
    graph = RoadGraph("corridor")
    n0 = RoadNode(id="node_0", position=Position2D(x=0.0, y=0.0))
    n1 = RoadNode(id="node_1", position=Position2D(x=length_m, y=0.0))
    graph.add_node(n0)
    graph.add_node(n1)

    e_fwd = RoadEdge(
        id="e_fwd",
        start_node_id="node_0",
        end_node_id="node_1",
        length_m=length_m,
        speed_limit_mps=20.0,
    )
    e_rev = RoadEdge(
        id="e_rev",
        start_node_id="node_1",
        end_node_id="node_0",
        length_m=length_m,
        speed_limit_mps=20.0,
    )
    graph.add_edge(e_fwd)
    graph.add_edge(e_rev)

    route_fwd = Route(id="r_fwd", node_ids=["node_0", "node_1"], edge_ids=["e_fwd"])
    route_rev = Route(id="r_rev", node_ids=["node_1", "node_0"], edge_ids=["e_rev"])
    return graph, route_fwd, route_rev


class TestSafetyEngineSteppingIntegration:
    """Tests for safety detection and override application within SimulationEngine.step()."""

    def test_safety_override_applied_over_normal_acceleration(self):
        # 12m corridor: vehicle at x=0 (length 4.5, front at 2.25) and
        # vehicle at x=12 (rear at 9.75).
        # distance = 12 - 4.5 = 7.5m, closing at 20 m/s -> TTC = 7.5 / 20 = 0.375s (IMMINENT)
        graph, r_fwd, r_rev = _build_test_corridor(length_m=12.0)
        safety_cfg = SafetyConfig(
            enabled=True,
            min_separation_m=5.0,
            near_miss_distance_m=10.0,
            reaction_time_s=0.5,
            gentle_decel_mps2=2.0,
            strong_decel_mps2=4.5,
            emergency_decel_mps2=7.0,
        )
        world = WorldState(road_graph=graph, safety_config=safety_cfg)

        v1 = Vehicle(
            id="v1",
            position=Position2D(x=0.0, y=0.0),
            speed_mps=10.0,
            max_speed_mps=20.0,
            heading_rad=0.0,
        )
        v2 = Vehicle(
            id="v2",
            position=Position2D(x=12.0, y=0.0),
            speed_mps=10.0,
            max_speed_mps=20.0,
            heading_rad=math.pi,
        )

        ag1 = VehicleAgent(
            v1,
            graph,
            route=r_fwd,
            config=KinematicsConfig(max_speed_mps=20.0, max_deceleration_mps2=8.0),
        )
        ag2 = VehicleAgent(
            v2,
            graph,
            route=r_rev,
            config=KinematicsConfig(max_speed_mps=20.0, max_deceleration_mps2=8.0),
        )
        ag1.start()
        ag2.start()

        world.add_agent(ag1)
        world.add_agent(ag2)
        engine = SimulationEngine(world=world)

        # Target accels try to accelerate +2.0 m/s^2, but safety override demands emergency braking
        res = engine.step(target_accels={"v1": 2.0, "v2": 2.0})

        assert res.step_results["v1"].applied_acceleration_mps2 < 0.0
        assert res.step_results["v2"].applied_acceleration_mps2 < 0.0
        assert res.safety_metrics is not None
        assert res.safety_metrics["control_overrides"] == 2
        assert res.safety_metrics["pair_checks"] == 1
        assert res.safety_events is not None
        assert len(res.safety_events) >= 1

    def test_safe_separated_vehicles_continue_normal_accel(self):
        # Two parallel independent corridors 50m apart laterally
        graph = RoadGraph("parallel_corridors")
        graph.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=0.0, y=50.0)))
        graph.add_node(RoadNode(id="n3", position=Position2D(x=100.0, y=50.0)))
        e1 = RoadEdge(
            id="e1",
            start_node_id="n0",
            end_node_id="n1",
            length_m=100.0,
            speed_limit_mps=20.0,
        )
        e2 = RoadEdge(
            id="e2",
            start_node_id="n2",
            end_node_id="n3",
            length_m=100.0,
            speed_limit_mps=20.0,
        )
        graph.add_edge(e1)
        graph.add_edge(e2)

        r1 = Route(id="r1", node_ids=["n0", "n1"], edge_ids=["e1"])
        r2 = Route(id="r2", node_ids=["n2", "n3"], edge_ids=["e2"])

        safety_cfg = SafetyConfig(enabled=True, min_separation_m=5.0)
        world = WorldState(road_graph=graph, safety_config=safety_cfg)

        v1 = Vehicle(
            id="v1",
            position=Position2D(x=0.0, y=0.0),
            speed_mps=5.0,
            max_speed_mps=20.0,
            heading_rad=0.0,
        )
        v2 = Vehicle(
            id="v2",
            position=Position2D(x=0.0, y=50.0),
            speed_mps=5.0,
            max_speed_mps=20.0,
            heading_rad=0.0,
        )

        ag1 = VehicleAgent(v1, graph, route=r1, config=KinematicsConfig(max_speed_mps=20.0))
        ag2 = VehicleAgent(v2, graph, route=r2, config=KinematicsConfig(max_speed_mps=20.0))
        ag1.start()
        ag2.start()

        world.add_agent(ag1)
        world.add_agent(ag2)
        engine = SimulationEngine(world=world)

        res = engine.step(target_accels={"v1": 2.5, "v2": 1.5})
        assert math.isclose(res.step_results["v1"].applied_acceleration_mps2, 2.5, abs_tol=1e-5)
        assert math.isclose(res.step_results["v2"].applied_acceleration_mps2, 1.5, abs_tol=1e-5)
        assert res.safety_metrics["control_overrides"] == 0


class TestSafetyEngineAtomicRollback:
    """Tests verifying atomic rollback of vehicle, world, and safety state upon stepping failure."""

    def test_stepping_failure_rolls_back_safety_metrics_and_events(self):
        graph, r_fwd, r_rev = _build_test_corridor(length_m=100.0)
        safety_cfg = SafetyConfig(enabled=True, min_separation_m=5.0)
        world = WorldState(road_graph=graph, safety_config=safety_cfg)

        v1 = Vehicle(
            id="v1",
            position=Position2D(x=10.0, y=0.0),
            speed_mps=10.0,
            max_speed_mps=20.0,
            heading_rad=0.0,
        )
        v2 = Vehicle(
            id="v2",
            position=Position2D(x=20.0, y=0.0),
            speed_mps=10.0,
            max_speed_mps=20.0,
            heading_rad=math.pi,
        )

        ag1 = VehicleAgent(v1, graph, route=r_fwd)
        ag2 = VehicleAgent(v2, graph, route=r_rev)
        ag1.start()
        ag2.start()

        world.add_agent(ag1)
        world.add_agent(ag2)
        engine = SimulationEngine(world=world)

        initial_events_count = len(world.safety_manager.events)
        initial_metrics = world.safety_manager.metrics.capture_state()
        initial_pos_v1 = Position2D(x=v1.position.x, y=v1.position.y)
        initial_speed_v1 = v1.speed_mps

        # Inject failure during ag2.step()
        def fail_step(*args, **kwargs):
            raise RuntimeError("Injected kinematics integration failure")

        with patch.object(ag2, "step", side_effect=fail_step):
            with pytest.raises(TickExecutionError, match="Tick 1 failed during agent execution"):
                engine.step()

        # Engine must transition to FAILED
        assert engine.status.value == "failed"

        # Safety metrics and events must be completely restored without committing partial counts
        assert len(world.safety_manager.events) == initial_events_count
        assert world.safety_manager.metrics.capture_state() == initial_metrics

        # Vehicle states must be restored to original pre-tick values
        assert v1.position == initial_pos_v1
        assert v1.speed_mps == initial_speed_v1

        # Reset engine and verify clean retry
        engine.reset()
        assert engine.status.value == "initialized"
        assert engine.current_tick == 0
        assert world.safety_manager.metrics.pair_checks == 0


class TestSafetyDeterministicScenarios:
    """End-to-end execution of Phase 16 deterministic safety scenario templates."""

    def test_head_on_collision_avoidance_scenario_execution(self):
        from apps.core.scenarios.builder import ScenarioBuilder

        scenario = create_head_on_collision_avoidance_scenario(time_step_s=0.1, max_ticks=80)
        runner = ScenarioRunner(ScenarioBuilder(scenario).build())
        summary = runner.run()

        assert summary.completed_ticks > 0
        assert summary.tick_results is not None
        last_tick = summary.tick_results[-1]
        assert last_tick.safety_metrics is not None
        # Braking must have been applied
        assert last_tick.safety_metrics["control_overrides"] > 0
        # No actual geometric collision occurred!
        assert last_tick.safety_metrics["actual_collisions"] == 0
        assert last_tick.safety_metrics["min_separation_observed"] is not None
        assert last_tick.safety_metrics["min_separation_observed"] > 0.0

    def test_rear_end_headway_protection_scenario_execution(self):
        from apps.core.scenarios.builder import ScenarioBuilder

        scenario = create_rear_end_following_safety_scenario(time_step_s=0.1, max_ticks=80)
        runner = ScenarioRunner(ScenarioBuilder(scenario).build())
        summary = runner.run()

        last_tick = summary.tick_results[-1]
        assert last_tick.safety_metrics is not None
        assert last_tick.safety_metrics["control_overrides"] > 0
        assert last_tick.safety_metrics["actual_collisions"] == 0

    def test_intersection_conflict_safety_scenario_execution(self):
        from apps.core.scenarios.builder import ScenarioBuilder

        scenario = create_intersection_conflict_safety_scenario(time_step_s=0.1, max_ticks=80)
        runner = ScenarioRunner(ScenarioBuilder(scenario).build())
        summary = runner.run()

        last_tick = summary.tick_results[-1]
        assert last_tick.safety_metrics is not None
        assert last_tick.safety_metrics["pair_checks"] > 0
        assert last_tick.safety_metrics["actual_collisions"] == 0

    def test_unavoidable_collision_scenario_execution(self):
        from apps.core.scenarios.builder import ScenarioBuilder

        scenario = create_unavoidable_collision_scenario(time_step_s=0.1, max_ticks=30)
        runner = ScenarioRunner(ScenarioBuilder(scenario).build())
        summary = runner.run()

        last_tick = summary.tick_results[-1]
        assert last_tick.safety_metrics is not None
        # Physical limits caused actual collision
        assert last_tick.safety_metrics["actual_collisions"] >= 1
        assert last_tick.safety_metrics["unresolved_conflicts"] >= 1

    def test_deterministic_replay_reproducibility(self):
        from apps.core.scenarios.builder import ScenarioBuilder

        scenario = create_head_on_collision_avoidance_scenario(
            time_step_s=0.1, max_ticks=40, seed=123
        )
        runner1 = ScenarioRunner(ScenarioBuilder(scenario).build())
        res1 = runner1.run()

        runner2 = ScenarioRunner(ScenarioBuilder(scenario).build())
        res2 = runner2.run()

        assert res1.completed_ticks == res2.completed_ticks
        last1 = res1.tick_results[-1]
        last2 = res2.tick_results[-1]

        assert last1.safety_metrics == last2.safety_metrics
        for vid in last1.step_results:
            p1 = last1.step_results[vid].new_position
            p2 = last2.step_results[vid].new_position
            assert math.isclose(p1.x, p2.x, abs_tol=1e-6)
            assert math.isclose(p1.y, p2.y, abs_tol=1e-6)
