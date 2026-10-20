"""Tests verifying bit-identical determinism and replay repeatability across scenarios."""

from apps.core.scenarios import (
    ScenarioBuilder,
    ScenarioRunner,
    create_multi_vehicle_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
)


def test_independent_identical_runs_produce_identical_results():
    """Verify two separately constructed scenarios produce identical results."""
    scn1 = create_multi_vehicle_scenario(seed=123)
    scn2 = create_multi_vehicle_scenario(seed=123)

    ctx1 = ScenarioBuilder(scn1).build()
    ctx2 = ScenarioBuilder(scn2).build()

    # Compare initial snapshots
    assert ctx1.initial_snapshot.to_dict() == ctx2.initial_snapshot.to_dict()

    # Compare planned routes for all vehicles
    for vid in ctx1.world.agent_ids:
        r1 = ctx1.world.get_agent(vid).route
        r2 = ctx2.world.get_agent(vid).route
        assert r1 is not None and r2 is not None
        assert r1.node_ids == r2.node_ids
        assert r1.edge_ids == r2.edge_ids

    runner1 = ScenarioRunner(ctx1)
    runner2 = ScenarioRunner(ctx2)

    res1 = runner1.run_to_completion()
    res2 = runner2.run_to_completion()

    # Compare final snapshots and serialization dictionaries
    dict1 = res1.to_dict()
    dict2 = res2.to_dict()

    assert dict1 == dict2
    assert res1.completed_ticks == res2.completed_ticks
    assert res1.elapsed_time_s == res2.elapsed_time_s
    assert res1.arrived_vehicle_ids == res2.arrived_vehicle_ids


def test_reset_and_replay_is_bit_identical():
    """Verify that resetting a runner and re-executing produces bit-identical results."""
    scenario = create_signalized_scenario(seed=999)
    ctx = ScenarioBuilder(scenario).build()
    runner = ScenarioRunner(ctx)

    # First execution
    res1 = runner.run_to_completion()
    dict1 = res1.to_dict()

    # Reset
    runner.reset()

    # Second execution
    res2 = runner.run_to_completion()
    dict2 = res2.to_dict()

    assert dict1 == dict2
    assert res1.final_world_snapshot.to_dict() == res2.final_world_snapshot.to_dict()


def test_intermediate_tick_results_are_identical():
    """Verify that tick-by-tick intermediate step results match exactly across runs."""
    scn1 = create_single_vehicle_scenario(seed=42)
    scn2 = create_single_vehicle_scenario(seed=42)

    runner1 = ScenarioRunner(ScenarioBuilder(scn1).build())
    runner2 = ScenarioRunner(ScenarioBuilder(scn2).build())

    for _ in range(15):
        t1 = runner1.step()
        t2 = runner2.step()

        assert t1.tick == t2.tick
        assert t1.elapsed_time_s == t2.elapsed_time_s
        assert t1.signal_states == t2.signal_states

        step1 = t1.step_results["veh_01"]
        step2 = t2.step_results["veh_01"]

        assert step1.distance_traveled_m == step2.distance_traveled_m
        assert step1.new_speed_mps == step2.new_speed_mps
        assert step1.heading_rad == step2.heading_rad
        assert step1.new_position.x == step2.new_position.x
        assert step1.new_position.y == step2.new_position.y
        assert step1.arrived == step2.arrived
