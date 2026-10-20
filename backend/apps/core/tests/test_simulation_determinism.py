"""Determinism and reproducibility tests for the simulation core subsystem.

Verifies bit-identical execution across independent runs, registration order independence,
reset replayability, and complex multi-agent progression on synthetic city grids.
"""

from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.planner import CostMode, find_route
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.world import WorldState


def setup_multi_agent_world(
    order: tuple[str, ...],
    grid_rows: int = 4,
    grid_cols: int = 4,
) -> tuple[WorldState, SimulationEngine]:
    """Helper building a 4x4 synthetic city grid with multiple vehicles in given order."""
    grid_cfg = CityGridConfig(rows=grid_rows, cols=grid_cols, spacing_m=100.0)
    graph = generate_synthetic_city_grid(grid_cfg)

    sim_cfg = SimulationConfig(time_step_s=0.1)
    world = WorldState(road_graph=graph, config=sim_cfg)

    # Route definitions
    # V1: node_r0_c0 -> node_r0_c3 -> node_r3_c3
    r1 = find_route(graph, "node_r0_c0", "node_r3_c3", cost_mode=CostMode.DISTANCE).route
    assert r1 is not None
    # V2: node_r3_c0 -> node_r0_c3
    r2 = find_route(graph, "node_r3_c0", "node_r0_c3", cost_mode=CostMode.DISTANCE).route
    assert r2 is not None
    # V3: node_r2_c2 -> node_r1_c1
    r3 = find_route(graph, "node_r2_c2", "node_r1_c1", cost_mode=CostMode.DISTANCE).route
    assert r3 is not None

    agent_map = {
        "v1": VehicleAgent(
            vehicle=Vehicle(
                id="v1",
                vehicle_type=VehicleType.STANDARD,
                state=VehicleState.IDLE,
                position=Position2D(x=0.0, y=0.0),
                heading_rad=0.0,
                speed_mps=0.0,
            ),
            road_graph=graph,
            route=r1,
        ),
        "v2": VehicleAgent(
            vehicle=Vehicle(
                id="v2",
                vehicle_type=VehicleType.STANDARD,
                state=VehicleState.IDLE,
                position=Position2D(x=0.0, y=0.0),
                heading_rad=0.0,
                speed_mps=0.0,
            ),
            road_graph=graph,
            route=r2,
        ),
        "v3": VehicleAgent(
            vehicle=Vehicle(
                id="v3",
                vehicle_type=VehicleType.STANDARD,
                state=VehicleState.IDLE,
                position=Position2D(x=0.0, y=0.0),
                heading_rad=0.0,
                speed_mps=0.0,
            ),
            road_graph=graph,
            route=r3,
        ),
    }

    # Start all agents
    for a in agent_map.values():
        a.start()

    # Add agents to world in caller-specified order
    for vid in order:
        world.add_agent(agent_map[vid])

    engine = SimulationEngine(world=world)
    return world, engine


class TestSimulationDeterminism:
    """Test deterministic reproducibility across simulation executions."""

    def test_identical_runs_produce_bit_identical_snapshots(self) -> None:
        # Run 1
        _, engine1 = setup_multi_agent_world(order=("v1", "v2", "v3"))
        results1 = engine1.run(ticks=30)
        snap1 = engine1.get_snapshot()

        # Run 2 (completely separate memory instances)
        _, engine2 = setup_multi_agent_world(order=("v1", "v2", "v3"))
        results2 = engine2.run(ticks=30)
        snap2 = engine2.get_snapshot()

        assert len(results1) == len(results2) == 30
        for r1, r2 in zip(results1, results2):
            assert r1.tick == r2.tick
            assert r1.elapsed_time_s == r2.elapsed_time_s
            assert r1.arrived_agent_ids == r2.arrived_agent_ids
            assert r1.active_agent_ids == r2.active_agent_ids
            for vid in ("v1", "v2", "v3"):
                sr1 = r1.step_results[vid]
                sr2 = r2.step_results[vid]
                assert sr1.new_position.x == sr2.new_position.x
                assert sr1.new_position.y == sr2.new_position.y
                assert sr1.new_speed_mps == sr2.new_speed_mps
                assert sr1.heading_rad == sr2.heading_rad
                assert sr1.distance_traveled_m == sr2.distance_traveled_m
                assert sr1.remaining_route_distance_m == sr2.remaining_route_distance_m

        assert snap1.to_dict() == snap2.to_dict()

    def test_agent_registration_order_independence(self) -> None:
        # World A: v1, v2, v3
        _, engine_a = setup_multi_agent_world(order=("v1", "v2", "v3"))
        results_a = engine_a.run(ticks=25)
        snap_a = engine_a.get_snapshot()

        # World B: v3, v1, v2 (reverse/shuffled registration order)
        _, engine_b = setup_multi_agent_world(order=("v3", "v1", "v2"))
        results_b = engine_b.run(ticks=25)
        snap_b = engine_b.get_snapshot()

        assert snap_a.to_dict() == snap_b.to_dict()
        for r_a, r_b in zip(results_a, results_b):
            assert r_a.to_dict() == r_b.to_dict()

    def test_reset_and_replay_reproducibility(self) -> None:
        # Run 20 ticks, record snapshot, reset, run 20 ticks again -> identical snapshot!
        _, engine = setup_multi_agent_world(order=("v1", "v2", "v3"))

        # Pass 1
        engine.run(ticks=20)
        snap_pass1 = engine.get_snapshot()

        # Reset
        engine.reset()
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        # Pass 2
        engine.run(ticks=20)
        snap_pass2 = engine.get_snapshot()

        assert snap_pass1.to_dict() == snap_pass2.to_dict()
