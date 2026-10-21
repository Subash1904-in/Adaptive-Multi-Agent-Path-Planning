"""Integration tests for Pedestrians within SimulationEngine and WorldState.

Verifies:
- Clock-synchronized stepping of vehicles, pedestrians, and signals using authoritative engine.
- Atomic rollback of pedestrians, vehicles, signals, and metrics upon injected step failure.
- Deterministic replay reproducibility across repeated scenario runs.
- WorldState and SimulationEngine reset restoring baseline pedestrian configurations and states.
- Pedestrian metric tracking (active count, waiting count, started/completed crossings).
"""

import math
from unittest.mock import patch

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import (
    RoadEdge,
    RoadNode,
    Route,
    SimulationConfig,
    TrafficSignal,
    Vehicle,
)
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.crosswalk import Crosswalk
from apps.core.pedestrians.models import PedestrianLifecycleState
from apps.core.safety.models import SafetyConfig
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


def _build_test_world() -> tuple[WorldState, Crosswalk, PedestrianAgent, VehicleAgent]:
    """Helper to build a complete world with graph, signal, crosswalk, vehicle, and pedestrian."""
    graph = RoadGraph(name="engine_test_grid")
    n1 = RoadNode(id="n1", position=Position2D(x=0.0, y=0.0))
    n2 = RoadNode(id="n2", position=Position2D(x=100.0, y=0.0))
    n3 = RoadNode(id="n3", position=Position2D(x=200.0, y=0.0))
    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)

    e1 = RoadEdge(
        id="e1", start_node_id="n1", end_node_id="n2", length_m=100.0, speed_limit_mps=15.0
    )
    e2 = RoadEdge(
        id="e2", start_node_id="n2", end_node_id="n3", length_m=100.0, speed_limit_mps=15.0
    )
    graph.add_edge(e1)
    graph.add_edge(e2)

    sig = TrafficSignal(
        id="sig_1", node_id="n2", state=TrafficSignalState.RED, position=Position2D(x=100.0, y=0.0)
    )
    sig_cfg = SignalCycleConfig(
        red_duration_s=4.0,
        green_duration_s=4.0,
        yellow_duration_s=2.0,
        initial_phase=TrafficSignalState.RED,
    )

    sim_cfg = SimulationConfig(time_step_s=1.0)
    safety_cfg = SafetyConfig(enabled=True, min_separation_m=2.0)
    world = WorldState(road_graph=graph, config=sim_cfg, safety_config=safety_cfg)
    world.add_traffic_signal(sig, config=sig_cfg)

    cw = Crosswalk(
        id="cw_1",
        node_id="n2",
        road_edge_ids=("e1",),
        entry_point=Position2D(x=90.0, y=-5.0),
        exit_point=Position2D(x=90.0, y=5.0),
        width_m=4.0,
        signal_id="sig_1",
    )
    world.add_crosswalk(cw)

    ped = PedestrianAgent(
        pedestrian_id="ped_1",
        position=Position2D(x=90.0, y=-5.0),
        destination=Position2D(x=90.0, y=5.0),
        current_crosswalk_id="cw_1",
        desired_speed_mps=1.5,
        state=PedestrianLifecycleState.CROSSING,
    )
    world.add_pedestrian(ped)

    v = Vehicle(id="veh_1", position=Position2D(x=0.0, y=0.0), speed_mps=10.0, max_speed_mps=20.0)
    route = Route(id="r1", node_ids=["n1", "n2", "n3"], edge_ids=["e1", "e2"])
    agent = VehicleAgent(vehicle=v, road_graph=graph, route=route)
    agent.start()
    world.add_agent(agent)

    return world, cw, ped, agent


class TestPedestrianEngineIntegration:
    """Verifies SimulationEngine execution lifecycle and guarantees for pedestrians."""

    def test_pedestrian_single_clock_synchronization(self) -> None:
        """Pedestrians, vehicles, and signals advance in unison under the authoritative clock."""
        world, cw, ped, agent = _build_test_world()
        engine = SimulationEngine(world=world)

        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        res1 = engine.step()
        assert res1.tick == 1
        assert res1.elapsed_time_s == 1.0
        assert "ped_1" in res1.pedestrian_step_results
        assert res1.pedestrian_step_results["ped_1"].pedestrian_id == "ped_1"
        assert res1.pedestrian_metrics is not None
        assert res1.pedestrian_metrics["active_pedestrians"] == 1

        # Pedestrian advanced along y-axis
        assert ped.position.y > -5.0
        # Clock matches elapsed time
        assert math.isclose(engine.elapsed_time_s, 1.0)

    def test_atomic_rollback_on_pedestrian_step_failure(self) -> None:
        """Failure during pedestrian stepping rolls back vehicles, pedestrians, and metrics."""
        world, cw, ped, agent = _build_test_world()
        engine = SimulationEngine(world=world)

        initial_ped_pos = Position2D(x=ped.position.x, y=ped.position.y)
        initial_ped_state = ped.state
        initial_veh_pos = Position2D(x=agent.vehicle.position.x, y=agent.vehicle.position.y)
        initial_metrics = world.pedestrian_metrics.capture_state()

        def fail_ped_step(*args, **kwargs):
            raise RuntimeError("Injected pedestrian stepping exception")

        with patch.object(ped, "step", side_effect=fail_ped_step):
            with pytest.raises(TickExecutionError, match="Tick 1 failed during agent execution"):
                engine.step()

        # Engine must transition to FAILED status
        assert engine.status == EngineStatus.FAILED

        # Clock must remain at tick 0 and elapsed 0.0s
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        # Pedestrian state must be restored to pre-tick values
        assert ped.position == initial_ped_pos
        assert ped.state == initial_ped_state

        # Vehicle state must be restored to pre-tick values
        assert agent.vehicle.position == initial_veh_pos

        # Pedestrian metrics must be reverted completely
        assert world.pedestrian_metrics.capture_state() == initial_metrics

    def test_atomic_rollback_on_vehicle_failure_restores_pedestrian(self) -> None:
        """Failure during vehicle stepping cleanly rolls back pedestrian state."""
        world, cw, ped, agent = _build_test_world()
        engine = SimulationEngine(world=world)

        initial_ped_pos = Position2D(x=ped.position.x, y=ped.position.y)
        initial_ped_state = ped.state

        def fail_veh_step(*args, **kwargs):
            raise RuntimeError("Injected vehicle stepping exception")

        with patch.object(agent, "step", side_effect=fail_veh_step):
            with pytest.raises(TickExecutionError, match="Tick 1 failed during agent execution"):
                engine.step()

        assert engine.status == EngineStatus.FAILED
        assert ped.position == initial_ped_pos
        assert ped.state == initial_ped_state

    def test_scenario_reset_restores_baseline_pedestrians(self) -> None:
        """Engine reset restores all pedestrians to initial baseline positions and states."""
        world, cw, ped, agent = _build_test_world()
        engine = SimulationEngine(world=world)

        # Run 3 ticks
        engine.step()
        engine.step()
        engine.step()

        assert engine.current_tick == 3
        assert ped.position.y > -5.0

        # Reset engine
        engine.reset()

        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        ped_reset = world.get_pedestrian("ped_1")
        assert math.isclose(ped_reset.position.x, 90.0)
        assert math.isclose(ped_reset.position.y, -5.0)
        assert ped_reset.state == PedestrianLifecycleState.CROSSING
        assert ped_reset.waiting_time_s == 0.0
        assert ped_reset.total_distance_m == 0.0

    def test_deterministic_replay_produces_identical_results(self) -> None:
        """Running the same scenario twice from baseline produces identical step results."""

        def run_simulation(ticks: int = 5) -> list[tuple[float, float, str]]:
            world, cw, ped, agent = _build_test_world()
            engine = SimulationEngine(world=world)
            trajectory = []
            for _ in range(ticks):
                engine.step()
                p = world.get_pedestrian("ped_1")
                trajectory.append((round(p.position.x, 5), round(p.position.y, 5), p.state.value))
            return trajectory

        run1 = run_simulation(5)
        run2 = run_simulation(5)
        assert run1 == run2

    def test_pedestrian_metrics_tracking(self) -> None:
        """PedestrianMetrics accurately counts active, waiting, and completed crossings."""
        world, cw, ped, agent = _build_test_world()
        # Set pedestrian very close to exit curb (4.0m with speed 1.5m/s -> arrives in 1 tick)
        ped.pedestrian.position = Position2D(x=90.0, y=4.5)
        ped.state = PedestrianLifecycleState.CROSSING

        engine = SimulationEngine(world=world)
        engine.step()

        # Pedestrian should have arrived at destination (y=5.0)
        assert ped.state == PedestrianLifecycleState.ARRIVED
        metrics = world.pedestrian_metrics.to_dict()
        assert metrics["crossings_completed"] == 1
        assert metrics["active_pedestrians"] == 0
