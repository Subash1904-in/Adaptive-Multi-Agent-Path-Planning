"""Integration tests for traffic signal management in WorldState.

Verifies signal registration, intersection and approach edge mapping,
duplicate detection, invalid association enforcement, queries, snapshots, and resets.
"""

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import RoadEdge, RoadNode, TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.road_graph import RoadGraph
from apps.core.signals.controller import TrafficSignalController
from apps.core.signals.exceptions import (
    DuplicateSignalError,
    InvalidIntersectionAssociationError,
    SignalNotFoundError,
)
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.models import WorldSnapshot
from apps.core.simulation.world import WorldState


class TestWorldStateSignalRegistration:
    """Tests for registering and configuring traffic signals in WorldState."""

    @pytest.fixture
    def road_network(self) -> RoadGraph:
        """Create a simple 3-node road network with an intersection."""
        graph = RoadGraph(name="test_network")
        n1 = RoadNode(id="node_west", position=Position2D(x=0.0, y=100.0))
        n2 = RoadNode(id="node_south", position=Position2D(x=100.0, y=0.0))
        n_int = RoadNode(id="node_int", position=Position2D(x=100.0, y=100.0))
        n_east = RoadNode(id="node_east", position=Position2D(x=200.0, y=100.0))

        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n_int)
        graph.add_node(n_east)

        # Incoming edges to node_int
        graph.add_edge(
            RoadEdge(
                id="edge_west_to_int",
                start_node_id="node_west",
                end_node_id="node_int",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )
        graph.add_edge(
            RoadEdge(
                id="edge_south_to_int",
                start_node_id="node_south",
                end_node_id="node_int",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )
        # Outgoing edge from node_int
        graph.add_edge(
            RoadEdge(
                id="edge_int_to_east",
                start_node_id="node_int",
                end_node_id="node_east",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )
        return graph

    def test_add_signal_via_traffic_signal_entity(self, road_network: RoadGraph) -> None:
        """Test adding a TrafficSignal directly to WorldState."""
        world = WorldState(road_graph=road_network)
        assert world.signal_count == 0

        signal = TrafficSignal(
            id="sig_int",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        ctrl = world.add_traffic_signal(signal)

        assert world.signal_count == 1
        assert world.has_signal("sig_int")
        assert world.signal_ids == ["sig_int"]
        assert world.get_signal("sig_int") is ctrl
        # Incoming edges to node_int should be automatically discovered
        assert ctrl.incoming_edge_ids == ["edge_south_to_int", "edge_west_to_int"]
        assert world.get_signal_at_node("node_int") is ctrl
        assert world.get_signal_for_edge("edge_west_to_int") is ctrl
        assert world.get_signal_for_edge("edge_south_to_int") is ctrl
        assert world.get_signal_for_edge("edge_int_to_east") is None

    def test_add_signal_via_preconfigured_controller(self, road_network: RoadGraph) -> None:
        """Test adding an already initialized TrafficSignalController."""
        world = WorldState(road_graph=road_network)
        signal = TrafficSignal(
            id="sig_int_custom",
            node_id="node_int",
            state=TrafficSignalState.GREEN,
            position=Position2D(x=100.0, y=100.0),
        )
        cfg = SignalCycleConfig(
            green_duration_s=15.0,
            yellow_duration_s=3.0,
            red_duration_s=15.0,
            initial_phase=TrafficSignalState.GREEN,
        )
        ctrl = TrafficSignalController(signal=signal, config=cfg, road_graph=road_network)
        registered_ctrl = world.add_traffic_signal(ctrl)

        assert registered_ctrl is ctrl
        assert world.signal_count == 1
        assert world.get_signal("sig_int_custom").state == TrafficSignalState.GREEN

    def test_add_duplicate_signal_id_raises(self, road_network: RoadGraph) -> None:
        """Test that registering duplicate signal ID raises DuplicateSignalError."""
        world = WorldState(road_graph=road_network)
        sig1 = TrafficSignal(
            id="sig_dup",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        world.add_traffic_signal(sig1)

        sig2 = TrafficSignal(
            id="sig_dup",
            node_id="node_west",
            state=TrafficSignalState.RED,
            position=Position2D(x=0.0, y=100.0),
        )
        with pytest.raises(DuplicateSignalError, match="already exists"):
            world.add_traffic_signal(sig2)

    def test_add_duplicate_node_signal_raises(self, road_network: RoadGraph) -> None:
        """Test that registering two signals at the same node raises DuplicateSignalError."""
        world = WorldState(road_graph=road_network)
        sig1 = TrafficSignal(
            id="sig_first",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        world.add_traffic_signal(sig1)

        sig2 = TrafficSignal(
            id="sig_second",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        with pytest.raises(DuplicateSignalError, match="already has a signal registered"):
            world.add_traffic_signal(sig2)

    def test_nonexistent_node_association_raises(self, road_network: RoadGraph) -> None:
        """Test that signal on non-existent node raises InvalidIntersectionAssociationError."""
        world = WorldState(road_graph=road_network)
        sig = TrafficSignal(
            id="sig_ghost",
            node_id="node_ghost",
            state=TrafficSignalState.RED,
            position=Position2D(x=50.0, y=50.0),
        )
        with pytest.raises(InvalidIntersectionAssociationError, match="non-existent node"):
            world.add_traffic_signal(sig)

    def test_nonexistent_incoming_edge_raises(self, road_network: RoadGraph) -> None:
        """Test that non-existent incoming edge raises InvalidIntersectionAssociationError."""
        world = WorldState(road_graph=road_network)
        sig = TrafficSignal(
            id="sig_int",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        with pytest.raises(InvalidIntersectionAssociationError, match="non-existent edge"):
            world.add_traffic_signal(sig, incoming_edge_ids=["edge_ghost"])

    def test_incoming_edge_terminating_elsewhere_raises(self, road_network: RoadGraph) -> None:
        """Test that an incoming edge terminating at another node raises error."""
        world = WorldState(road_graph=road_network)
        sig = TrafficSignal(
            id="sig_int",
            node_id="node_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=100.0),
        )
        # edge_int_to_east terminates at node_east, not node_int
        with pytest.raises(InvalidIntersectionAssociationError, match="terminates at"):
            world.add_traffic_signal(sig, incoming_edge_ids=["edge_int_to_east"])

    def test_controller_with_incompatible_graph_raises(self, road_network: RoadGraph) -> None:
        """Test that controller bound to another RoadGraph instance raises error."""
        other_graph = RoadGraph(name="other_graph")
        other_graph.add_node(RoadNode(id="node_int", position=Position2D(x=0.0, y=0.0)))
        sig = TrafficSignal(id="sig_other", node_id="node_int")
        other_ctrl = TrafficSignalController(signal=sig, road_graph=other_graph)

        world = WorldState(road_graph=road_network)
        with pytest.raises(InvalidIntersectionAssociationError, match="different RoadGraph"):
            world.add_traffic_signal(other_ctrl)

    def test_invalid_type_raises(self, road_network: RoadGraph) -> None:
        """Test that passing invalid type raises TypeError."""
        world = WorldState(road_graph=road_network)
        with pytest.raises(TypeError, match="Expected TrafficSignal or TrafficSignalController"):
            world.add_traffic_signal("invalid_object")  # type: ignore[arg-type]


class TestWorldStateSignalQueriesAndRemovals:
    """Tests for query, lookup, removal, snapshots, and resets in WorldState."""

    @pytest.fixture
    def world_with_signal(self) -> WorldState:
        """Create world with an intersection signal."""
        graph = RoadGraph(name="test_network")
        n1 = RoadNode(id="n_west", position=Position2D(x=0.0, y=0.0))
        n2 = RoadNode(id="n_int", position=Position2D(x=100.0, y=0.0))
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(
            RoadEdge(
                id="e_west_int",
                start_node_id="n_west",
                end_node_id="n_int",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )
        world = WorldState(road_graph=graph)
        sig = TrafficSignal(
            id="sig_int",
            node_id="n_int",
            state=TrafficSignalState.RED,
            position=Position2D(x=100.0, y=0.0),
        )
        cfg = SignalCycleConfig(
            red_duration_s=20.0,
            green_duration_s=20.0,
            yellow_duration_s=5.0,
        )
        world.add_traffic_signal(sig, config=cfg)
        return world

    def test_get_signal_nonexistent_raises(self, world_with_signal: WorldState) -> None:
        """Test that get_signal with invalid ID raises SignalNotFoundError."""
        with pytest.raises(SignalNotFoundError, match="was not found"):
            world_with_signal.get_signal("sig_ghost")

    def test_query_signal_and_edge(self, world_with_signal: WorldState) -> None:
        """Test query_signal and query_signal_for_edge."""
        # At clock t=0.0
        q = world_with_signal.query_signal("sig_int")
        assert q.state == TrafficSignalState.RED
        assert q.remaining_phase_s == pytest.approx(20.0)
        assert q.time_to_green_s == pytest.approx(20.0)

        # Query via edge approach
        q_edge = world_with_signal.query_signal_for_edge("e_west_int")
        assert q_edge is not None
        assert q_edge.signal_id == "sig_int"
        assert q_edge.state == TrafficSignalState.RED

        # Query on uncontrolled edge returns None
        assert world_with_signal.query_signal_for_edge("e_ghost") is None

    def test_query_nonexistent_signal_raises(self, world_with_signal: WorldState) -> None:
        """Test that querying non-existent signal raises SignalNotFoundError."""
        with pytest.raises(SignalNotFoundError, match="was not found"):
            world_with_signal.query_signal("sig_ghost")

    def test_remove_signal_cleans_up_mappings(self, world_with_signal: WorldState) -> None:
        """Test that remove_signal removes controller and cleans up edge/node lookups."""
        assert world_with_signal.signal_count == 1
        removed = world_with_signal.remove_signal("sig_int")
        assert removed.id == "sig_int"
        assert world_with_signal.signal_count == 0
        assert world_with_signal.has_signal("sig_int") is False
        assert world_with_signal.get_signal_at_node("n_int") is None
        assert world_with_signal.get_signal_for_edge("e_west_int") is None

    def test_remove_nonexistent_signal_raises(self, world_with_signal: WorldState) -> None:
        """Test that removing non-existent signal raises SignalNotFoundError."""
        with pytest.raises(SignalNotFoundError, match="was not found"):
            world_with_signal.remove_signal("sig_ghost")

    def test_world_snapshot_includes_signals(self, world_with_signal: WorldState) -> None:
        """Test that WorldSnapshot includes serialized signal data."""
        snap = world_with_signal.get_snapshot()
        assert isinstance(snap, WorldSnapshot)
        assert "sig_int" in snap.signals
        sig_snap = snap.signals["sig_int"]
        assert sig_snap.signal_id == "sig_int"
        assert sig_snap.node_id == "n_int"
        assert sig_snap.state == TrafficSignalState.RED

        d = snap.to_dict()
        assert "signals" in d
        assert "sig_int" in d["signals"]
        assert d["signals"]["sig_int"]["state"] == "red"

    def test_world_reset_restores_signal_phases(self, world_with_signal: WorldState) -> None:
        """Test that world.reset() restores signals to t=0 baseline."""
        # Advance clock to 25.0s (GREEN phase)
        world_with_signal.update_signals(25.0)
        assert world_with_signal.get_signal("sig_int").state == TrafficSignalState.GREEN

        world_with_signal.reset()
        assert world_with_signal.clock.tick_count == 0
        assert world_with_signal.get_signal("sig_int").state == TrafficSignalState.RED
        assert world_with_signal.get_signal("sig_int").remaining_phase_s == pytest.approx(20.0)

    def test_auto_registration_from_synthetic_city(self) -> None:
        """Test that WorldState auto-registers pre-existing signals from synthetic city grid."""
        city = generate_synthetic_city_grid(config=CityGridConfig(rows=4, cols=4, spacing_m=100.0))
        # Synthetic city has internal signals: r1_c1, r1_c2, r2_c1, r2_c2 (4 signals)
        assert len(city.get_traffic_signals()) == 4

        world = WorldState(road_graph=city)
        assert world.signal_count == 4
        # Every internal signal should be registered
        for sig_id in city.get_traffic_signals().keys():
            # In city generator, signal.node_id is key
            sig = city.get_traffic_signals()[sig_id]
            assert world.has_signal(sig.id)
            ctrl = world.get_signal(sig.id)
            assert ctrl.node_id == sig.node_id
            # 4 incoming edges to an internal intersection in a grid
            assert len(ctrl.incoming_edge_ids) == 4
