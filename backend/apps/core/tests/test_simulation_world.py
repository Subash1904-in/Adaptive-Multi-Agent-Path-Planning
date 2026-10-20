"""Unit tests for WorldState container.

Verifies agent registration, graph compatibility checks, deterministic iteration ordering,
baseline capture, reset semantics, and point-in-time snapshot serialization.
"""

import pytest

from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import RoadEdge, RoadNode, Route, SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.exceptions import (
    AgentNotFoundError,
    DuplicateAgentIdError,
    IncompatibleAgentGraphError,
)
from apps.core.simulation.world import WorldState


def create_test_graph() -> RoadGraph:
    """Helper creating a simple 3-node linear graph A -> B -> C."""
    graph = RoadGraph()
    n_a = RoadNode(id="node_a", position=Position2D(x=0.0, y=0.0))
    n_b = RoadNode(id="node_b", position=Position2D(x=100.0, y=0.0))
    n_c = RoadNode(id="node_c", position=Position2D(x=200.0, y=0.0))
    graph.add_node(n_a)
    graph.add_node(n_b)
    graph.add_node(n_c)

    e1 = RoadEdge(
        id="edge_ab",
        start_node_id="node_a",
        end_node_id="node_b",
        length_m=100.0,
        speed_limit_mps=15.0,
    )
    e2 = RoadEdge(
        id="edge_bc",
        start_node_id="node_b",
        end_node_id="node_c",
        length_m=100.0,
        speed_limit_mps=15.0,
    )
    graph.add_edge(e1)
    graph.add_edge(e2)
    return graph


def create_agent(
    vehicle_id: str,
    graph: RoadGraph,
    route_nodes: tuple[str, str, str] = ("node_a", "node_b", "node_c"),
) -> VehicleAgent:
    """Helper creating an en-route VehicleAgent with assigned route."""
    vehicle = Vehicle(
        id=vehicle_id,
        vehicle_type=VehicleType.STANDARD,
        state=VehicleState.IDLE,
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=0.0,
    )
    route = Route(id=f"route_{vehicle_id}", node_ids=list(route_nodes))
    agent = VehicleAgent(vehicle=vehicle, road_graph=graph, route=route)
    return agent


class TestWorldStateInitialization:
    """Test WorldState instantiation, configuration, and default properties."""

    def test_default_initialization(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)

        assert world.road_graph is graph
        assert world.agent_count == 0
        assert world.agent_ids == []
        assert world.clock.time_step_s == 0.1
        assert world.clock.tick_count == 0
        assert world.metadata == {}

    def test_custom_initialization(self) -> None:
        graph = create_test_graph()
        config = SimulationConfig(time_step_s=0.05, max_vehicles=50)
        clock = SimulationClock(time_step_s=0.05, initial_tick=5)
        metadata = {"scenario_id": "test_urban"}

        world = WorldState(
            road_graph=graph,
            config=config,
            clock=clock,
            metadata=metadata,
        )

        assert world.config.max_vehicles == 50
        assert world.clock.tick_count == 5
        assert world.clock.time_step_s == 0.05
        assert world.metadata["scenario_id"] == "test_urban"

    def test_invalid_road_graph_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Expected RoadGraph instance"):
            WorldState(road_graph="not_a_graph")  # type: ignore


class TestWorldStateAgentManagement:
    """Test adding, retrieving, removing, and validating vehicle agents."""

    def test_add_and_retrieve_agent(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)

        world.add_agent(agent)
        assert world.agent_count == 1
        assert world.has_agent("v1") is True
        assert world.get_agent("v1") is agent

    def test_add_invalid_agent_type_raises(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        with pytest.raises(TypeError, match="Expected VehicleAgent instance"):
            world.add_agent("not_an_agent")  # type: ignore

    def test_add_duplicate_agent_id_raises(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        agent1 = create_agent("v1", graph)
        agent2 = create_agent("v1", graph)

        world.add_agent(agent1)
        with pytest.raises(DuplicateAgentIdError) as exc_info:
            world.add_agent(agent2)
        assert exc_info.value.agent_id == "v1"

    def test_incompatible_road_graph_raises(self) -> None:
        graph1 = create_test_graph()
        graph2 = create_test_graph()
        world = WorldState(road_graph=graph1)

        # Agent bound to graph2 instead of graph1
        agent_diff_graph = create_agent("v_diff", graph2)
        with pytest.raises(IncompatibleAgentGraphError, match="different RoadGraph instance"):
            world.add_agent(agent_diff_graph)

    def test_get_nonexistent_agent_raises(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        assert world.has_agent("missing") is False

        with pytest.raises(AgentNotFoundError) as exc_info:
            world.get_agent("missing")
        assert exc_info.value.agent_id == "missing"

    def test_remove_agent(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)

        world.add_agent(agent)
        removed = world.remove_agent("v1")
        assert removed is agent
        assert world.agent_count == 0
        assert world.has_agent("v1") is False

    def test_remove_nonexistent_agent_raises(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        with pytest.raises(AgentNotFoundError):
            world.remove_agent("nonexistent")


class TestWorldStateDeterminismAndOrdering:
    """Test deterministic agent iteration order regardless of registration sequence."""

    def test_agent_enumeration_is_alphabetically_sorted_by_id(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)

        # Insert in non-alphabetical order
        a_z = create_agent("veh_z", graph)
        a_a = create_agent("veh_a", graph)
        a_m = create_agent("veh_m", graph)

        world.add_agent(a_z)
        world.add_agent(a_a)
        world.add_agent(a_m)

        assert world.agent_ids == ["veh_a", "veh_m", "veh_z"]
        agents = world.get_agents()
        assert [a.vehicle.id for a in agents] == ["veh_a", "veh_m", "veh_z"]


class TestWorldStateResetAndSnapshots:
    """Test baseline capture, reset semantics, and snapshot generation."""

    def test_reset_restores_agents_and_clock(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        agent.start()
        world.add_agent(agent)

        # Advance agent and clock
        world.clock.tick()
        agent.step(dt=1.0)
        assert world.clock.tick_count == 1
        assert agent.vehicle.position.x > 0.0

        # Reset world
        world.reset()
        assert world.clock.tick_count == 0
        assert world.clock.elapsed_time_s == 0.0
        assert agent.vehicle.position.x == 0.0
        assert agent.vehicle.speed_mps == 0.0
        assert agent.state == VehicleState.EN_ROUTE

    def test_save_baseline_updates_reset_target(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph)
        agent = create_agent("v1", graph)
        agent.start()
        world.add_agent(agent)

        # Move to a new position and save as baseline
        agent.step(dt=2.0)
        saved_pos = agent.vehicle.position
        world.save_baseline()

        # Move further
        agent.step(dt=2.0)
        assert agent.vehicle.position.x > saved_pos.x

        # Reset should restore to the saved baseline position, not the initial 0.0
        world.reset()
        assert agent.vehicle.position.x == saved_pos.x

    def test_get_snapshot_serializes_correctly(self) -> None:
        graph = create_test_graph()
        world = WorldState(road_graph=graph, metadata={"author": "test"})
        agent = create_agent("v1", graph)
        world.add_agent(agent)

        snap = world.get_snapshot()
        assert snap.tick == 0
        assert snap.elapsed_time_s == 0.0
        assert snap.agent_count == 1
        assert "v1" in snap.vehicles
        assert snap.metadata == {"author": "test"}

        snap_dict = snap.to_dict()
        assert snap_dict["tick"] == 0
        assert snap_dict["agent_count"] == 1
        assert snap_dict["vehicles"]["v1"]["vehicle_id"] == "v1"
        assert snap_dict["vehicles"]["v1"]["state"] == "idle"
