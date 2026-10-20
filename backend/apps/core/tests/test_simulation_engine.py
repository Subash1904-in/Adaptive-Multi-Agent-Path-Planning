"""Unit tests for SimulationEngine coordinator.

Verifies deterministic tick sequencing, identical dt distribution, pause/resume/single-step
semantics, atomic rollback on stepping failure, and reset recovery.
"""

from unittest.mock import patch

import pytest

from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import RoadEdge, RoadNode, Route, SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import EngineStateError, TickExecutionError
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


def create_linear_graph(edge_length_m: float = 200.0) -> RoadGraph:
    """Create a 3-node linear graph: node_a -> node_b -> node_c."""
    graph = RoadGraph()
    n_a = RoadNode(id="node_a", position=Position2D(x=0.0, y=0.0))
    n_b = RoadNode(id="node_b", position=Position2D(x=edge_length_m, y=0.0))
    n_c = RoadNode(id="node_c", position=Position2D(x=edge_length_m * 2, y=0.0))
    graph.add_node(n_a)
    graph.add_node(n_b)
    graph.add_node(n_c)

    e1 = RoadEdge(
        id="edge_ab",
        start_node_id="node_a",
        end_node_id="node_b",
        length_m=edge_length_m,
        speed_limit_mps=20.0,
    )
    e2 = RoadEdge(
        id="edge_bc",
        start_node_id="node_b",
        end_node_id="node_c",
        length_m=edge_length_m,
        speed_limit_mps=20.0,
    )
    graph.add_edge(e1)
    graph.add_edge(e2)
    return graph


def create_agent(
    vehicle_id: str,
    graph: RoadGraph,
    initial_speed_mps: float = 0.0,
    route_nodes: tuple[str, str, str] = ("node_a", "node_b", "node_c"),
) -> VehicleAgent:
    """Create an en-route VehicleAgent starting at node_a."""
    vehicle = Vehicle(
        id=vehicle_id,
        vehicle_type=VehicleType.STANDARD,
        state=VehicleState.IDLE,
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=initial_speed_mps,
    )
    route = Route(id=f"route_{vehicle_id}", node_ids=list(route_nodes))
    agent = VehicleAgent(vehicle=vehicle, road_graph=graph, route=route)
    agent.start()
    return agent


class TestSimulationEngineBasics:
    """Test engine initialization, property delegation, and type checks."""

    def test_initialization(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph, config=SimulationConfig(time_step_s=0.1))
        engine = SimulationEngine(world=world)

        assert engine.world is world
        assert engine.status == EngineStatus.INITIALIZED
        assert engine.time_step_s == 0.1
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0
        assert engine.is_paused is False
        assert engine.last_tick_result is None

    def test_invalid_world_raises(self) -> None:
        with pytest.raises(TypeError, match="Expected WorldState instance"):
            SimulationEngine(world="not_a_world")  # type: ignore


class TestSimulationEngineStepping:
    """Test stepping single and multiple agents across discrete simulation ticks."""

    def test_step_single_vehicle(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        world.add_agent(agent)
        engine = SimulationEngine(world=world)

        tick_res = engine.step(target_accels={"v1": 2.0})

        assert tick_res.tick == 1
        assert tick_res.time_step_s == 0.1
        assert tick_res.elapsed_time_s == 0.1
        assert tick_res.agent_count == 1
        assert "v1" in tick_res.step_results
        assert engine.current_tick == 1
        assert engine.status == EngineStatus.RUNNING

        step_res = tick_res.step_results["v1"]
        assert step_res.distance_traveled_m > 0.0
        assert agent.vehicle.position.x > 0.0

    def test_step_multiple_vehicles_receive_identical_dt(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph, config=SimulationConfig(time_step_s=0.2))
        a1 = create_agent("v1", graph)
        a2 = create_agent("v2", graph)
        world.add_agent(a1)
        world.add_agent(a2)
        engine = SimulationEngine(world=world)

        tick_res = engine.step(target_accels={"v1": 1.0, "v2": 2.0})

        assert tick_res.time_step_s == 0.2
        assert tick_res.step_results["v1"].dt_s == 0.2
        assert tick_res.step_results["v2"].dt_s == 0.2
        assert tick_res.step_results["v1"].applied_acceleration_mps2 == 1.0
        assert tick_res.step_results["v2"].applied_acceleration_mps2 == 2.0

    def test_run_multiple_ticks(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        world.add_agent(agent)
        engine = SimulationEngine(world=world)

        results = engine.run(ticks=5)
        assert len(results) == 5
        assert results[-1].tick == 5
        assert engine.current_tick == 5
        assert engine.elapsed_time_s == 0.5

    def test_run_invalid_tick_count_raises(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        engine = SimulationEngine(world=world)

        with pytest.raises(ValueError, match="positive integer"):
            engine.run(ticks=0)
        with pytest.raises(ValueError, match="positive integer"):
            engine.run(ticks=-3)


class TestSimulationEngineLifecycleAndPause:
    """Test pause, resume, single-step, stop, and reset semantics."""

    def test_pause_and_resume(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        engine = SimulationEngine(world=world)

        engine.pause()
        assert engine.is_paused is True
        assert engine.status == EngineStatus.PAUSED

        engine.resume()
        assert engine.is_paused is False
        assert engine.status == EngineStatus.RUNNING

    def test_single_step_while_paused(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        world.add_agent(agent)
        engine = SimulationEngine(world=world)

        engine.pause()
        assert engine.is_paused is True

        # Single step advances 1 tick but engine remains paused
        tick_res = engine.step(target_accels={"v1": 1.0})
        assert tick_res.tick == 1
        assert engine.current_tick == 1
        assert engine.is_paused is True

    def test_run_while_paused_raises_state_error(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        engine = SimulationEngine(world=world)
        engine.pause()

        with pytest.raises(EngineStateError, match="Cannot run multiple ticks"):
            engine.run(ticks=3)

    def test_stop_prevents_stepping(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        engine = SimulationEngine(world=world)
        engine.stop()

        assert engine.status == EngineStatus.STOPPED
        with pytest.raises(EngineStateError, match="Cannot step an engine in STOPPED state"):
            engine.step()

    def test_reset_restores_motion_and_arrivals(self) -> None:
        graph = create_linear_graph(edge_length_m=10.0)
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        world.add_agent(agent)
        engine = SimulationEngine(world=world)

        # Drive until arrival
        for _ in range(50):
            engine.step(target_accels={"v1": 5.0})
            if agent.is_arrived:
                break

        assert agent.is_arrived is True
        assert engine.current_tick > 0

        # Reset engine
        engine.reset()
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0
        assert engine.status == EngineStatus.INITIALIZED
        assert agent.vehicle.position.x == 0.0
        assert agent.is_en_route is True  # baseline was captured when en_route


class TestSimulationEngineAtomicRollback:
    """Test atomic rollback guarantees when an agent fails mid-tick."""

    def test_atomic_rollback_on_agent_stepping_failure(self) -> None:
        graph = create_linear_graph()
        world = WorldState(road_graph=graph)
        a1 = create_agent("v1", graph)
        a2 = create_agent("v2", graph)
        world.add_agent(a1)
        world.add_agent(a2)
        engine = SimulationEngine(world=world)

        # Step tick 1 successfully
        engine.step(target_accels={"v1": 1.0, "v2": 1.0})
        assert engine.current_tick == 1
        pos_v1_before = a1.vehicle.position
        pos_v2_before = a2.vehicle.position

        # Now simulate a failure on vehicle 2 during tick 2
        def failing_step(dt: float, target_accel: float | None = None):
            raise RuntimeError("Simulated vehicle sensor hardware failure")

        with patch.object(a2, "step", side_effect=failing_step):
            with pytest.raises(TickExecutionError) as exc_info:
                engine.step()
            assert "Simulated vehicle sensor hardware failure" in str(exc_info.value)

        # Atomic rollback verification:
        # 1. Clock did NOT advance
        assert engine.current_tick == 1
        assert engine.elapsed_time_s == 0.1
        # 2. Engine status is FAILED
        assert engine.status == EngineStatus.FAILED
        # 3. Agent 1 (which was stepped before Agent 2 in deterministic order) was rolled back!
        assert a1.vehicle.position.x == pos_v1_before.x
        assert a2.vehicle.position.x == pos_v2_before.x

        # Stepping while FAILED raises EngineStateError
        with pytest.raises(EngineStateError, match="FAILED"):
            engine.step()

        # Calling reset() recovers from FAILED state
        engine.reset()
        assert engine.status == EngineStatus.INITIALIZED
        assert engine.current_tick == 0
