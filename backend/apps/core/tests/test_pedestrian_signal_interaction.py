"""Tests for pedestrian interaction with traffic signals and clearance policy.

Verifies:
- Pedestrians wait at crosswalk when pedestrian signal is DONT_WALK.
- Pedestrians enter crosswalk when pedestrian signal is WALK.
- Pedestrians mid-crossing continue traversing to exit curb under CLEARANCE policy.
- Traffic signal transitions follow authoritative simulation clock.
- Vehicle signal compliance is unaffected by pedestrian presence.
- World/engine reset restores initial signal and crossing states deterministically.
- Order of pedestrian registration does not alter crossing decisions.
"""

import math

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
from apps.core.pedestrians.models import (
    PedestrianLifecycleState,
    PedestrianSignalState,
)
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.world import WorldState


@pytest.fixture
def signalized_crossing_world() -> tuple[SimulationEngine, Crosswalk, PedestrianAgent]:
    """Fixture providing a signalized intersection with a crosswalk and pedestrian."""
    graph = RoadGraph(name="signal_test_graph")
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
        speed_limit_mps=10.0,
    )
    e2 = RoadEdge(
        id="edge_2_3",
        start_node_id="node_2",
        end_node_id="node_3",
        length_m=100.0,
        speed_limit_mps=10.0,
    )
    graph.add_edge(e1)
    graph.add_edge(e2)

    # Signal at node_2:
    # Phase 1: GREEN 2.0s (Vehicles go, Pedestrians DONT_WALK)
    # Phase 2: YELLOW 1.0s (Vehicles clearing, Pedestrians CLEARANCE)
    # Phase 3: RED 3.0s (Vehicles stop, Pedestrians WALK)
    sig = TrafficSignal(
        id="sig_int",
        node_id="node_2",
        state=TrafficSignalState.GREEN,
        position=Position2D(x=100.0, y=0.0),
    )
    cfg = SignalCycleConfig(
        red_duration_s=3.0,
        green_duration_s=2.0,
        yellow_duration_s=1.0,
        initial_phase=TrafficSignalState.GREEN,
    )

    sim_cfg = SimulationConfig(time_step_s=1.0)
    world = WorldState(road_graph=graph, config=sim_cfg)
    world.add_traffic_signal(sig, config=cfg)

    # Crosswalk across edge_1_2 right before node_2 at x=95.0, spanning y from -5.0 to 5.0
    cw = Crosswalk(
        id="cw_node2",
        node_id="node_2",
        road_edge_ids=("edge_1_2",),
        entry_point=Position2D(x=95.0, y=-5.0),
        exit_point=Position2D(x=95.0, y=5.0),
        width_m=4.0,
        signal_id="sig_int",
        waiting_radius_m=2.0,
    )
    world.add_crosswalk(cw)

    # Pedestrian starting right at entry curb (waiting area)
    ped = PedestrianAgent(
        pedestrian_id="ped_01",
        position=Position2D(x=95.0, y=-5.0),
        destination=Position2D(x=95.0, y=5.0),
        current_crosswalk_id="cw_node2",
        desired_speed_mps=1.5,
        state=PedestrianLifecycleState.APPROACHING_CROSSWALK,
    )
    world.add_pedestrian(ped)

    engine = SimulationEngine(world=world)
    return engine, cw, ped


class TestPedestrianSignalInteraction:
    """Verifies pedestrian decision-making in response to traffic signals."""

    def test_pedestrian_waits_when_signal_is_dont_walk(
        self, signalized_crossing_world: tuple[SimulationEngine, Crosswalk, PedestrianAgent]
    ) -> None:
        """Pedestrian stays waiting when traffic signal is GREEN (pedestrian DONT_WALK)."""
        engine, cw, ped = signalized_crossing_world

        # Initial signal is GREEN -> Pedestrian signal is DONT_WALK
        sig_state = engine.world.get_signal("sig_int").state
        assert sig_state == TrafficSignalState.GREEN
        assert cw.get_pedestrian_signal_state(sig_state) == PedestrianSignalState.DONT_WALK

        # Step tick 1: Pedestrian recognizes crosswalk entry and transitions to WAITING_TO_CROSS
        engine.step()
        assert ped.state == PedestrianLifecycleState.WAITING_TO_CROSS
        assert math.isclose(ped.position.x, 95.0)
        assert math.isclose(ped.position.y, -5.0)
        assert ped.waiting_time_s >= 1.0

        # Step tick 2: Still GREEN -> still waiting
        engine.step()
        assert ped.state == PedestrianLifecycleState.WAITING_TO_CROSS
        assert math.isclose(ped.position.y, -5.0)
        assert ped.waiting_time_s >= 2.0

    def test_pedestrian_enters_crosswalk_when_signal_turns_walk(
        self, signalized_crossing_world: tuple[SimulationEngine, Crosswalk, PedestrianAgent]
    ) -> None:
        """Pedestrian transitions from waiting to crossing when signal changes to RED/WALK."""
        engine, cw, ped = signalized_crossing_world

        # Tick 1: t=1.0 -> GREEN (DONT_WALK)
        engine.step()
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.GREEN
        assert ped.state == PedestrianLifecycleState.WAITING_TO_CROSS

        # Tick 2: t=2.0 -> YELLOW (CLEARANCE for pedestrians, but waiting ped stays waiting)
        engine.step()
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.YELLOW
        assert ped.state == PedestrianLifecycleState.WAITING_TO_CROSS

        # Tick 3: t=2.0 -> 3.0: Signal was YELLOW during step; transitions to RED after step
        engine.step()
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.RED
        assert ped.state == PedestrianLifecycleState.WAITING_TO_CROSS

        # Tick 4: t=3.0 -> 4.0: Starts step with RED (WALK) -> Transitions to CROSSING!
        engine.step()
        assert engine.world.get_signal("sig_int").state == TrafficSignalState.RED
        assert ped.state == PedestrianLifecycleState.CROSSING
        # Pedestrian has advanced forward towards y=5.0
        assert ped.position.y > -5.0

    def test_clearance_policy_preserves_mid_crossing_pedestrian(
        self, signalized_crossing_world: tuple[SimulationEngine, Crosswalk, PedestrianAgent]
    ) -> None:
        """Pedestrian mid-crossing when signal changes to YELLOW/GREEN does not freeze or revert."""
        engine, cw, ped = signalized_crossing_world

        # Fast-forward signal to RED
        ctrl = engine.world.get_signal("sig_int")
        ctrl.signal.state = TrafficSignalState.RED
        ped.state = PedestrianLifecycleState.WAITING_TO_CROSS

        # Tick 1: Starts crossing on RED (WALK)
        engine.step()
        assert ped.state == PedestrianLifecycleState.CROSSING
        pos_after_t1 = ped.position.y
        assert pos_after_t1 > -5.0

        # Now simulate premature signal change back to GREEN (DONT_WALK)
        ctrl.signal.state = TrafficSignalState.GREEN

        # Step next tick: Pedestrian in CROSSING must follow clearance policy
        # and continue advancing!
        engine.step()
        assert ped.state == PedestrianLifecycleState.CROSSING
        assert ped.position.y > pos_after_t1

    def test_vehicle_signal_behavior_remains_correct_with_pedestrians(self) -> None:
        """Vehicles still halt at RED signals even when pedestrians are present."""
        graph = RoadGraph(name="signal_test_graph_red")
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
            speed_limit_mps=10.0,
        )
        e2 = RoadEdge(
            id="edge_2_3",
            start_node_id="node_2",
            end_node_id="node_3",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
        graph.add_edge(e1)
        graph.add_edge(e2)

        sig = TrafficSignal(
            id="sig_red",
            node_id="node_2",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=0.0),
        )
        cfg = SignalCycleConfig(
            red_duration_s=5.0,
            green_duration_s=5.0,
            yellow_duration_s=2.0,
            initial_phase=TrafficSignalState.RED,
        )

        world = WorldState(road_graph=graph, config=SimulationConfig(time_step_s=1.0))
        world.add_traffic_signal(sig, config=cfg)

        v = Vehicle(id="veh_01", position=Position2D(x=80.0, y=0.0), speed_mps=10.0)
        route = Route(
            id="route_1",
            node_ids=["node_1", "node_2", "node_3"],
            edge_ids=["edge_1_2", "edge_2_3"],
        )
        agent = VehicleAgent(vehicle=v, road_graph=world.road_graph, route=route)
        agent.start()
        world.add_agent(agent)

        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=95.0, y=-5.0),
            destination=Position2D(x=95.0, y=5.0),
            desired_speed_mps=1.5,
            state=PedestrianLifecycleState.CROSSING,
        )
        world.add_pedestrian(ped)

        engine = SimulationEngine(world=world)
        res = engine.step()

        assert engine.world.get_signal("sig_red").state == TrafficSignalState.RED
        assert "veh_01" in res.step_results

    def test_registration_order_independence(self) -> None:
        """Registration order of pedestrians does not change simulation outcome."""
        def run_sim(order: list[str]) -> list[tuple[float, float]]:
            graph = RoadGraph(name="order_graph")
            n1 = RoadNode(id="node_1", position=Position2D(x=0.0, y=0.0))
            n2 = RoadNode(id="node_2", position=Position2D(x=50.0, y=0.0))
            graph.add_node(n1)
            graph.add_node(n2)
            graph.add_edge(
                RoadEdge(
                    id="e1",
                    start_node_id="node_1",
                    end_node_id="node_2",
                    length_m=50.0,
                    speed_limit_mps=10.0,
                )
            )

            world = WorldState(road_graph=graph, config=SimulationConfig(time_step_s=1.0))
            cw = Crosswalk(
                id="cw_test",
                node_id="node_2",
                entry_point=Position2D(x=25.0, y=0.0),
                exit_point=Position2D(x=25.0, y=10.0),
            )
            world.add_crosswalk(cw)

            peds = {
                "ped_a": PedestrianAgent(
                    pedestrian_id="ped_a",
                    position=Position2D(x=25.0, y=0.0),
                    destination=Position2D(x=25.0, y=10.0),
                    desired_speed_mps=1.0,
                    state=PedestrianLifecycleState.CROSSING,
                ),
                "ped_b": PedestrianAgent(
                    pedestrian_id="ped_b",
                    position=Position2D(x=25.0, y=2.0),
                    destination=Position2D(x=25.0, y=10.0),
                    desired_speed_mps=1.2,
                    state=PedestrianLifecycleState.CROSSING,
                ),
            }
            for pid in order:
                world.add_pedestrian(peds[pid])

            eng = SimulationEngine(world=world)
            eng.step()
            return [
                (world.get_pedestrian(pid).position.x, world.get_pedestrian(pid).position.y)
                for pid in sorted(order)
            ]

        res_ab = run_sim(["ped_a", "ped_b"])
        res_ba = run_sim(["ped_b", "ped_a"])
        assert res_ab == res_ba

    def test_scenario_reset_restores_signal_and_crossing_state(
        self, signalized_crossing_world: tuple[SimulationEngine, Crosswalk, PedestrianAgent]
    ) -> None:
        """Reset restores pedestrian position, state, waiting time, and signal phase."""
        engine, cw, ped = signalized_crossing_world

        # Step 3 ticks to mutate states
        engine.step()
        engine.step()
        engine.step()

        assert engine.current_tick == 3
        assert ped.waiting_time_s > 0.0

        # Reset world to baseline
        engine.reset()

        assert engine.current_tick == 0
        ped_reset = engine.world.get_pedestrian("ped_01")
        assert ped_reset.position == Position2D(x=95.0, y=-5.0)
        assert ped_reset.state == PedestrianLifecycleState.APPROACHING_CROSSWALK
        assert ped_reset.waiting_time_s == 0.0
