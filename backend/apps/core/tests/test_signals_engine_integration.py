"""Integration tests for SimulationEngine and traffic signal orchestration.

Verifies clock-synchronized signal progression, TickResult signal_states reporting,
pause/single-step semantics, atomic rollback on failure, and engine query delegation.
"""

from unittest.mock import MagicMock

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
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.signals.models import SignalCycleConfig, SignalQueryResult
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


class TestSimulationEngineSignalProgression:
    """Tests for discrete stepping and traffic signal synchronization."""

    @pytest.fixture
    def single_intersection_engine(self) -> SimulationEngine:
        """Create an engine with one signalized intersection and one vehicle."""
        graph = RoadGraph(name="test_city")
        n1 = RoadNode(id="node_1", position=Position2D(x=0.0, y=0.0))
        n2 = RoadNode(id="node_2", position=Position2D(x=100.0, y=0.0))
        n3 = RoadNode(id="node_3", position=Position2D(x=200.0, y=0.0))
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n3)

        e1 = RoadEdge(
            id="edge_1_2",
            start_node_id="node_1",
            end_node_id="node_2",
            length_m=100.0,
            speed_limit_mps=15.0,
        )
        e2 = RoadEdge(
            id="edge_2_3",
            start_node_id="node_2",
            end_node_id="node_3",
            length_m=100.0,
            speed_limit_mps=15.0,
        )
        graph.add_edge(e1)
        graph.add_edge(e2)

        # Signal at node_2: RED 2.0s, GREEN 2.0s, YELLOW 1.0s (total 5.0s cycle)
        sig = TrafficSignal(
            id="sig_int",
            node_id="node_2",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=0.0),
        )
        cfg = SignalCycleConfig(
            red_duration_s=2.0,
            green_duration_s=2.0,
            yellow_duration_s=1.0,
            initial_phase=TrafficSignalState.RED,
        )

        cfg_sim = SimulationConfig(time_step_s=1.0)
        world = WorldState(road_graph=graph, config=cfg_sim)
        world.add_traffic_signal(sig, config=cfg)

        # Add a vehicle agent
        v = Vehicle(id="veh_01", position=Position2D(x=0.0, y=0.0), speed_mps=0.0)
        route = Route(
            id="route_1",
            node_ids=["node_1", "node_2", "node_3"],
            edge_ids=["edge_1_2", "edge_2_3"],
        )
        agent = VehicleAgent(vehicle=v, road_graph=graph, route=route)
        agent.start()
        world.add_agent(agent)

        return SimulationEngine(world=world)

    def test_single_tick_signal_synchronization(
        self, single_intersection_engine: SimulationEngine
    ) -> None:
        """Test that single step advances signal and populates TickResult.signal_states."""
        engine = single_intersection_engine
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        # At t=0, signal is RED, 2.0s remaining
        sig_ctrl = engine.world.get_signal("sig_int")
        assert sig_ctrl.state == TrafficSignalState.RED
        assert sig_ctrl.remaining_phase_s == pytest.approx(2.0)

        # Step 1: dt = 1.0s -> t = 1.0s (still RED, 1.0s remaining)
        res1 = engine.step()
        assert res1.tick == 1
        assert res1.elapsed_time_s == pytest.approx(1.0)
        assert res1.signal_states == {"sig_int": TrafficSignalState.RED}
        assert sig_ctrl.state == TrafficSignalState.RED
        assert sig_ctrl.remaining_phase_s == pytest.approx(1.0)

        # Step 2: dt = 1.0s -> t = 2.0s (transitions to GREEN, 2.0s remaining)
        res2 = engine.step()
        assert res2.tick == 2
        assert res2.elapsed_time_s == pytest.approx(2.0)
        assert res2.signal_states == {"sig_int": TrafficSignalState.GREEN}
        assert sig_ctrl.state == TrafficSignalState.GREEN
        assert sig_ctrl.remaining_phase_s == pytest.approx(2.0)

    def test_full_cycle_progression_across_ticks(
        self, single_intersection_engine: SimulationEngine
    ) -> None:
        """Test full cyclic progression: RED (2s) -> GREEN (2s) -> YELLOW (1s) -> RED (2s)."""
        engine = single_intersection_engine

        # Tick 1 (t=1.0): RED
        r1 = engine.step()
        assert r1.signal_states["sig_int"] == TrafficSignalState.RED

        # Tick 2 (t=2.0): GREEN
        r2 = engine.step()
        assert r2.signal_states["sig_int"] == TrafficSignalState.GREEN

        # Tick 3 (t=3.0): GREEN
        r3 = engine.step()
        assert r3.signal_states["sig_int"] == TrafficSignalState.GREEN

        # Tick 4 (t=4.0): YELLOW
        r4 = engine.step()
        assert r4.signal_states["sig_int"] == TrafficSignalState.YELLOW

        # Tick 5 (t=5.0): RED (cycle rollover)
        r5 = engine.step()
        assert r5.signal_states["sig_int"] == TrafficSignalState.RED

    def test_engine_signal_query_delegation(
        self, single_intersection_engine: SimulationEngine
    ) -> None:
        """Test engine.query_signal and engine.query_signal_for_edge APIs."""
        engine = single_intersection_engine
        engine.run(ticks=2)  # Advance to t=2.0s (GREEN)

        q = engine.query_signal("sig_int")
        assert isinstance(q, SignalQueryResult)
        assert q.state == TrafficSignalState.GREEN
        assert q.time_to_green_s == 0.0
        assert q.time_to_red_s == pytest.approx(3.0)  # 2.0s rem green + 1.0s yellow

        # Query via edge
        q_edge = engine.query_signal_for_edge("edge_1_2")
        assert q_edge is not None
        assert q_edge.signal_id == "sig_int"
        assert q_edge.state == TrafficSignalState.GREEN

        # Query edge without signal
        assert engine.query_signal_for_edge("edge_2_3") is None

    def test_pause_and_single_step_signal_behavior(
        self, single_intersection_engine: SimulationEngine
    ) -> None:
        """Test signal behavior under pause and single-stepping."""
        engine = single_intersection_engine
        engine.pause()
        assert engine.is_paused is True

        # While paused, calling step() executes a single forced step
        res = engine.step()
        assert res.tick == 1
        assert res.elapsed_time_s == pytest.approx(1.0)
        assert res.signal_states["sig_int"] == TrafficSignalState.RED
        assert engine.is_paused is True

        # Resume and step normally
        engine.resume()
        assert engine.is_paused is False
        res2 = engine.step()
        assert res2.tick == 2
        assert res2.signal_states["sig_int"] == TrafficSignalState.GREEN

    def test_engine_reset_restores_signal_states(
        self, single_intersection_engine: SimulationEngine
    ) -> None:
        """Test that engine.reset() restores signals to t=0 baseline."""
        engine = single_intersection_engine
        engine.run(ticks=3)  # t=3.0 (GREEN)
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.GREEN

        engine.reset()
        assert engine.status == EngineStatus.INITIALIZED
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.RED
        assert engine.world.get_signal("sig_int").remaining_phase_s == pytest.approx(2.0)


class TestSimulationEngineAtomicRollback:
    """Tests for atomic rollback of signals and vehicles on stepping failures."""

    def test_atomic_rollback_preserves_signal_states_on_agent_failure(self) -> None:
        """Verify that when an agent step fails, both vehicles AND signals roll back atomically."""
        graph = RoadGraph(name="test_city")
        n1 = RoadNode(id="node_1", position=Position2D(x=0.0, y=0.0))
        n2 = RoadNode(id="node_2", position=Position2D(x=100.0, y=0.0))
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(
            RoadEdge(
                id="edge_1_2",
                start_node_id="node_1",
                end_node_id="node_2",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )

        sig = TrafficSignal(
            id="sig_int",
            node_id="node_2",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=0.0),
        )
        cfg = SignalCycleConfig(
            red_duration_s=10.0,
            green_duration_s=10.0,
            yellow_duration_s=2.0,
        )
        world = WorldState(road_graph=graph, config=SimulationConfig(time_step_s=1.0))
        world.add_traffic_signal(sig, config=cfg)

        # Agent 1: normal
        v1 = Vehicle(id="veh_01", position=Position2D(x=0.0, y=0.0), speed_mps=5.0)
        route = Route(id="r1", node_ids=["node_1", "node_2"], edge_ids=["edge_1_2"])
        agent1 = VehicleAgent(vehicle=v1, road_graph=graph, route=route)
        agent1.start()
        world.add_agent(agent1)

        # Agent 2: will fail on step
        v2 = Vehicle(id="veh_02", position=Position2D(x=10.0, y=0.0), speed_mps=5.0)
        agent2 = VehicleAgent(vehicle=v2, road_graph=graph, route=route)
        agent2.start()
        world.add_agent(agent2)

        engine = SimulationEngine(world=world)

        # Run 5 normal ticks (t=5.0s, RED, 5.0s remaining)
        engine.run(ticks=5)
        assert engine.current_tick == 5
        assert engine.elapsed_time_s == 5.0
        sig_ctrl = world.get_signal("sig_int")
        assert sig_ctrl.state == TrafficSignalState.RED
        assert sig_ctrl.remaining_phase_s == pytest.approx(5.0)
        v1_pos_before = Position2D(x=agent1.vehicle.position.x, y=agent1.vehicle.position.y)

        # Now mock agent2.step to fail
        agent2.step = MagicMock(side_effect=RuntimeError("Simulated kinematic step failure"))

        with pytest.raises(TickExecutionError, match="Simulated kinematic step failure"):
            engine.step()

        # Verify atomic rollback guarantees:
        # 1. Engine status is FAILED
        assert engine.status == EngineStatus.FAILED
        # 2. Clock was not advanced (remains at tick 5, 5.0s)
        assert engine.current_tick == 5
        assert engine.elapsed_time_s == 5.0
        # 3. Agent 1 was rolled back to pre-tick position
        assert agent1.vehicle.position.x == pytest.approx(v1_pos_before.x)
        assert agent1.vehicle.position.y == pytest.approx(v1_pos_before.y)
        # 4. Signal state was rolled back to pre-tick phase and remaining time
        assert sig_ctrl.state == TrafficSignalState.RED
        assert sig_ctrl.remaining_phase_s == pytest.approx(5.0)


class TestSyntheticCityMultiAgentSignals:
    """End-to-end tests for synthetic city with multiple signals and agents."""

    def test_multi_agent_synthetic_city_signal_progression(self) -> None:
        """Run 100 ticks in a 4x4 synthetic city and verify deterministic signal progression."""
        city = generate_synthetic_city_grid(
            config=CityGridConfig(rows=4, cols=4, spacing_m=100.0, signal_cycle_s=40.0)
        )
        world = WorldState(road_graph=city, config=SimulationConfig(time_step_s=0.5))
        assert world.signal_count == 4

        # Add 2 vehicles
        v1 = Vehicle(id="veh_01", position=Position2D(x=0.0, y=100.0), speed_mps=10.0)
        r1 = Route(
            id="r1",
            node_ids=["node_r1_c0", "node_r1_c1", "node_r1_c2", "node_r1_c3"],
            edge_ids=["edge_r1_c0_to_r1_c1", "edge_r1_c1_to_r1_c2", "edge_r1_c2_to_r1_c3"],
        )
        agent1 = VehicleAgent(vehicle=v1, road_graph=city, route=r1)
        agent1.start()
        world.add_agent(agent1)

        engine = SimulationEngine(world=world)
        results = engine.run(ticks=100)

        assert len(results) == 100
        assert engine.current_tick == 100
        assert engine.elapsed_time_s == pytest.approx(50.0)

        # Check all 4 signals are present in tick result
        last_res = results[-1]
        assert len(last_res.signal_states) == 4
        for sig_id in world.signal_ids:
            assert sig_id in last_res.signal_states
            # Verify state is valid TrafficSignalState
            assert isinstance(last_res.signal_states[sig_id], TrafficSignalState)

        # Snapshot consistency
        snap = engine.get_snapshot()
        assert len(snap.signals) == 4
        for sid, s_snap in snap.signals.items():
            assert s_snap.signal_id == sid
            assert s_snap.remaining_phase_s > 0.0
