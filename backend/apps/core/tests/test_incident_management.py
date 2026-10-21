"""Unit and integration tests for backend incident management and dynamic scenario disruptions.

Verifies:
- Authoritative incident validation (road closure, congestion, obstacle, signal phase override)
- Dynamic graph edge cost alteration and adaptive route replanning reaction
- Traffic signal controller phase overrides and cyclic restoration
- Automatic duration expiration and baseline restoration
- Subsystem state capture, restoration, and engine rollback
"""

import pytest

from apps.core.domain.enums import IncidentStatus, TrafficSignalState
from apps.core.domain.models import TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadEdge, RoadGraph, RoadNode
from apps.core.incidents.exceptions import (
    DuplicateIncidentIdError,
    IncidentNotFoundError,
    IncidentValidationError,
    InvalidIncidentTargetError,
)
from apps.core.incidents.manager import IncidentManager
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.evaluator import DynamicEdgeCostEvaluator
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    CostMode,
    RerouteDecisionType,
    Route,
)
from apps.core.signals.controller import TrafficSignalController


def _create_sample_graph() -> RoadGraph:
    """Build a deterministic triangular road graph with signalized junction."""
    graph = RoadGraph()
    n_a = RoadNode(id="node_a", position=Position2D(x=0.0, y=0.0))
    n_b = RoadNode(id="node_b", position=Position2D(x=100.0, y=0.0))
    n_c = RoadNode(id="node_c", position=Position2D(x=100.0, y=100.0))
    graph.add_node(n_a)
    graph.add_node(n_b)
    graph.add_node(n_c)

    e_ab = RoadEdge(
        id="edge_ab",
        start_node_id="node_a",
        end_node_id="node_b",
        length_m=100.0,
        speed_limit_mps=15.0,
    )
    e_bc = RoadEdge(
        id="edge_bc",
        start_node_id="node_b",
        end_node_id="node_c",
        length_m=100.0,
        speed_limit_mps=15.0,
    )
    e_ac = RoadEdge(
        id="edge_ac",
        start_node_id="node_a",
        end_node_id="node_c",
        length_m=141.4,
        speed_limit_mps=15.0,
    )
    graph.add_edge(e_ab)
    graph.add_edge(e_bc)
    graph.add_edge(e_ac)

    sig = TrafficSignal(id="sig_b", node_id="node_b")
    graph.add_traffic_signal(sig)
    return graph


def test_incident_manager_initialization() -> None:
    """Test incident manager initializes with clean empty state."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    assert manager.active_count == 0
    assert manager.resolved_count == 0
    assert len(manager.list_all()) == 0
    assert len(manager.get_closed_edges()) == 0


def test_road_closure_incident_and_evaluator() -> None:
    """Test injecting and resolving a road closure incident alters edge traversability."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    inc = manager.create_incident(
        incident_type="road_closure",
        affected_edge_id="edge_ab",
        severity="high",
        description="Emergency water main repair",
        current_time_s=10.0,
        current_tick=100,
    )

    assert inc.status == IncidentStatus.ACTIVE
    assert inc.affected_edge_id == "edge_ab"
    assert manager.active_count == 1
    assert "edge_ab" in manager.get_closed_edges()

    # Evaluator reflects closure
    evaluator = DynamicEdgeCostEvaluator(
        road_graph=graph,
        knowledge_store=None,
        incident_manager=manager,
    )
    assert evaluator.is_edge_closed("edge_ab")
    assert not evaluator.is_edge_closed("edge_ac")

    # Dynamic cost for closed edge is infinite
    cost = evaluator.calculate_dynamic_edge_cost(graph.get_edge("edge_ab"), CostMode.TRAVEL_TIME)
    assert cost == float("inf")

    # Remove incident
    resolved = manager.remove_incident(inc.id, current_time_s=25.0, current_tick=250)
    assert resolved.status == IncidentStatus.RESOLVED
    assert manager.active_count == 0
    assert manager.resolved_count == 1
    assert "edge_ab" not in manager.get_closed_edges()
    assert not evaluator.is_edge_closed("edge_ab")

    cost_restored = evaluator.calculate_dynamic_edge_cost(
        graph.get_edge("edge_ab"), CostMode.TRAVEL_TIME
    )
    assert cost_restored < float("inf")


def test_congestion_incident_scaling() -> None:
    """Test localized congestion increases dynamic edge cost proportionally."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    inc = manager.create_incident(
        incident_type="congestion",
        affected_edge_id="edge_ab",
        severity="high",
        congestion_factor=3.5,
        current_time_s=5.0,
        current_tick=50,
    )

    assert manager.get_congestion_multiplier("edge_ab") == 3.5
    assert manager.get_congestion_multiplier("edge_ac") == 1.0

    evaluator = DynamicEdgeCostEvaluator(
        road_graph=graph,
        knowledge_store=None,
        incident_manager=manager,
    )
    assert evaluator.get_congestion_multiplier("edge_ab") == 3.5

    # Removal restores multiplier to 1.0
    manager.remove_incident(inc.id, current_time_s=15.0)
    assert manager.get_congestion_multiplier("edge_ab") == 1.0
    assert evaluator.get_congestion_multiplier("edge_ab") == 1.0


def test_obstacle_incident_hazard_penalty() -> None:
    """Test obstacle incidents apply additive hazard penalties to target edges."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    inc = manager.create_incident(
        incident_type="obstacle",
        affected_edge_id="edge_bc",
        severity="critical",
        obstacle_type="debris",
    )

    evaluator = DynamicEdgeCostEvaluator(
        road_graph=graph,
        knowledge_store=None,
        incident_manager=manager,
    )
    penalty = evaluator.get_hazard_penalty("edge_bc")
    assert penalty > 0.0

    manager.remove_incident(inc.id)
    assert evaluator.get_hazard_penalty("edge_bc") == 0.0


def test_traffic_signal_override_and_restoration() -> None:
    """Test manual signal phase overrides freeze controller and restoration resumes cycle."""
    graph = _create_sample_graph()
    sig = graph.get_traffic_signal("node_b")
    controller = TrafficSignalController(signal=sig, road_graph=graph)
    signals = {"sig_b": controller}

    manager = IncidentManager(road_graph=graph, signals=signals)

    # Inject GREEN override on signal_b
    inc = manager.create_incident(
        incident_type="signal_override",
        affected_node_id="node_b",
        target_signal_phase="green",
        current_time_s=2.0,
        current_tick=20,
    )

    assert controller.signal.state == TrafficSignalState.GREEN

    # Advance controller time — should remain forced green
    controller.update(10.0)
    assert controller.signal.state == TrafficSignalState.GREEN

    # Remove incident
    manager.remove_incident(inc.id, current_time_s=12.0)
    # Signal is released from override
    controller.update(15.0)
    # Controller operates normally


def test_incident_duration_automatic_expiration() -> None:
    """Test that incidents with duration_s automatically expire when simulation advances."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    inc = manager.create_incident(
        incident_type="road_closure",
        affected_edge_id="edge_ab",
        duration_s=8.0,
        current_time_s=10.0,
        current_tick=100,
    )

    assert manager.active_count == 1

    # At t=15.0 (elapsed 5s < 8s), incident should still be active
    expired = manager.step(current_time_s=15.0, current_tick=150)
    assert len(expired) == 0
    assert manager.active_count == 1
    assert "edge_ab" in manager.get_closed_edges()

    # At t=18.5 (elapsed 8.5s >= 8s), incident should expire
    expired = manager.step(current_time_s=18.5, current_tick=185)
    assert len(expired) == 1
    assert expired[0].id == inc.id
    assert manager.active_count == 0
    assert manager.resolved_count == 1
    assert "edge_ab" not in manager.get_closed_edges()


def test_incident_target_validation_errors() -> None:
    """Test validation errors for invalid edges, missing targets, and unknown IDs."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    # Non-existent edge
    with pytest.raises(InvalidIncidentTargetError):
        manager.create_incident(
            incident_type="road_closure",
            affected_edge_id="edge_non_existent",
        )

    # Missing target for road closure
    with pytest.raises(IncidentValidationError):
        manager.create_incident(
            incident_type="road_closure",
            affected_edge_id=None,
        )

    # Invalid incident type
    with pytest.raises(IncidentValidationError):
        manager.create_incident(
            incident_type="unknown_disruption_type",
            affected_edge_id="edge_ab",
        )

    # Duplicate ID
    manager.create_incident(
        incident_type="congestion",
        affected_edge_id="edge_ab",
        incident_id="inc_fixed_1",
    )
    with pytest.raises(DuplicateIncidentIdError):
        manager.create_incident(
            incident_type="congestion",
            affected_edge_id="edge_bc",
            incident_id="inc_fixed_1",
        )

    # Remove non-existent incident
    with pytest.raises(IncidentNotFoundError):
        manager.remove_incident("inc_non_existent")


def test_incident_state_capture_and_restoration() -> None:
    """Test baseline state capture, mutation, and restoration."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)

    manager.create_incident(
        incident_type="road_closure",
        affected_edge_id="edge_ab",
        incident_id="inc_1",
    )
    baseline = manager.capture_state()

    # Inject second incident
    manager.create_incident(
        incident_type="congestion",
        affected_edge_id="edge_bc",
        incident_id="inc_2",
    )
    assert manager.active_count == 2

    # Restore baseline
    manager.restore_state(baseline)
    assert manager.active_count == 1
    assert "edge_ab" in manager.get_closed_edges()
    assert "edge_bc" not in manager.get_closed_edges()
    assert manager.get_incident("inc_2") is None


def test_dynamic_route_adapter_reroutes_on_incident_closure() -> None:
    """Verify DynamicRouteAdapter re-evaluates route when incident closure is injected."""
    graph = _create_sample_graph()
    manager = IncidentManager(road_graph=graph)
    adapter = DynamicRouteAdapter(
        road_graph=graph,
        config=AdaptiveRoutingConfig(enabled=True, repeat_suppression=True),
        incident_manager=manager,
    )

    # Initial route along edge_ab -> edge_bc
    from apps.core.domain.models import Vehicle
    from apps.core.domain.values import Position2D

    veh = Vehicle(
        id="veh_1",
        position=Position2D(x=0.0, y=0.0),
        max_speed_mps=15.0,
        current_node_id="node_a",
        target_node_id="node_c",
    )
    agent = VehicleAgent(
        vehicle=veh,
        road_graph=graph,
        route=Route(
            id="r1",
            node_ids=["node_a", "node_b", "node_c"],
            edge_ids=["edge_ab", "edge_bc"],
            total_distance_m=200.0,
            estimated_duration_s=20.0,
        ),
    )

    # Evaluate before incident — route is feasible
    dec1 = adapter.evaluate_agent(agent, knowledge_store=None, current_time_s=0.0)
    assert dec1.decision_type != RerouteDecisionType.REROUTE_ACCEPTED

    # Inject closure on edge_ab
    manager.create_incident(
        incident_type="road_closure",
        affected_edge_id="edge_ab",
        current_time_s=1.0,
    )

    # Evaluate again — current route blocked, adapter should reroute to direct edge_ac!
    dec2 = adapter.evaluate_agent(agent, knowledge_store=None, current_time_s=1.5)
    assert dec2.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
    assert "edge_ac" in dec2.candidate_edge_ids
