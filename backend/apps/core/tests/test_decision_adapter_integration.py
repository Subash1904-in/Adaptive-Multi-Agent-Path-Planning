"""Integration tests for DynamicRouteAdapter with DecisionManager and local knowledge."""

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    ReportType,
)
from apps.core.decision.config import DecisionConfig
from apps.core.decision.manager import DecisionManager
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    RerouteDecisionType,
)
from apps.core.routing.planner import RoutePlanner


def _create_test_env():
    """Helper creating a 3x3 grid network, planner, and initial vehicle agent."""
    graph = generate_synthetic_city_grid(
        CityGridConfig(rows=3, cols=3, spacing_m=100.0, bidirectional=True)
    )
    planner = RoutePlanner(graph)

    # Route: (0,0) -> (0,1) -> (0,2)
    route_res = planner.find_route("node_r0_c0", "node_r0_c2")
    vehicle = Vehicle(
        id="veh_1",
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=5.0,
        current_node_id="node_r0_c0",
        target_node_id="node_r0_c2",
    )
    agent = VehicleAgent(vehicle, road_graph=graph)
    agent.assign_route(route_res.route)
    return graph, planner, agent


def test_adapter_decision_manager_accepts_reroute():
    """Verify that when policy accepts a candidate route, the agent's route is updated."""
    graph, planner, agent = _create_test_env()
    old_node_ids = list(agent.route.node_ids)

    dec_cfg = DecisionConfig(
        enabled=True,
        weight_travel_time=1.0,
        min_score_improvement=0.01,
    )
    dec_mgr = DecisionManager(dec_cfg)

    adapt_cfg = AdaptiveRoutingConfig(
        enabled=True,
        reroute_cooldown_s=0.0,
        repeat_suppression=False,
    )
    adapter = DynamicRouteAdapter(
        road_graph=graph,
        config=adapt_cfg,
        decision_manager=dec_mgr,
    )

    k_store = VehicleKnowledgeStore("veh_1")
    # Add road closure on direct edge: edge_r0_c0_to_r0_c1
    k_store._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    dec = adapter.evaluate_agent(agent, k_store, current_time_s=1.0)
    assert dec.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
    assert list(agent.route.node_ids) != old_node_ids
    assert "edge_r0_c0_to_r0_c1" not in [s.edge_id for s in agent._segments]
    assert dec_mgr.metrics.decisions_accepted >= 1
    assert dec_mgr.metrics.route_changes_accepted >= 1


def test_adapter_decision_manager_rejects_candidate():
    """Verify that when policy rejects a candidate, route is not mutated."""
    graph, planner, agent = _create_test_env()
    old_route_id = agent.route.id

    dec_cfg = DecisionConfig(enabled=True)
    dec_mgr = DecisionManager(dec_cfg)

    adapter = DynamicRouteAdapter(
        road_graph=graph,
        config=AdaptiveRoutingConfig(enabled=True, reroute_cooldown_s=0.0),
        decision_manager=dec_mgr,
    )

    k_store = VehicleKnowledgeStore("veh_1")
    # Current route is clean and optimal; alternative will have lower score
    dec = adapter.evaluate_agent(agent, k_store, current_time_s=1.0)
    # Since current route is optimal, adapter should not reroute
    assert dec.decision_type != RerouteDecisionType.REROUTE_ACCEPTED
    assert agent.route.id == old_route_id


def test_local_knowledge_isolation_between_agents():
    """Verify local knowledge store isolation prevents state leakage across vehicles."""
    graph, planner, agent1 = _create_test_env()

    veh2 = Vehicle(
        id="veh_2",
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=5.0,
        current_node_id="node_r0_c0",
        target_node_id="node_r0_c2",
    )
    agent2 = VehicleAgent(veh2, road_graph=graph)
    route_res = planner.find_route("node_r0_c0", "node_r0_c2")
    agent2.assign_route(route_res.route)

    dec_mgr = DecisionManager(DecisionConfig(enabled=True))
    adapter = DynamicRouteAdapter(
        road_graph=graph,
        config=AdaptiveRoutingConfig(enabled=True, reroute_cooldown_s=0.0),
        decision_manager=dec_mgr,
    )

    store1 = VehicleKnowledgeStore("veh_1")
    store2 = VehicleKnowledgeStore("veh_2")

    # Only vehicle 1 observes the closure
    store1._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    # Evaluate agent 1 -> reroutes
    dec1 = adapter.evaluate_agent(agent1, store1, current_time_s=1.0)
    assert dec1.decision_type == RerouteDecisionType.REROUTE_ACCEPTED

    # Evaluate agent 2 -> retains direct route (unaware of closure)
    dec2 = adapter.evaluate_agent(agent2, store2, current_time_s=1.0)
    assert dec2.decision_type != RerouteDecisionType.REROUTE_ACCEPTED
    assert "edge_r0_c0_to_r0_c1" in [s.edge_id for s in agent2._segments]


def test_backward_compatibility_when_policy_disabled():
    """Verify that when decision_config is disabled, baseline Phase 15 behavior is preserved."""
    graph, planner, agent = _create_test_env()
    old_node_ids = list(agent.route.node_ids)

    dec_cfg = DecisionConfig(enabled=False)
    dec_mgr = DecisionManager(dec_cfg)

    adapter = DynamicRouteAdapter(
        road_graph=graph,
        config=AdaptiveRoutingConfig(enabled=True, reroute_cooldown_s=0.0),
        decision_manager=dec_mgr,
    )

    k_store = VehicleKnowledgeStore("veh_1")
    # Road closure triggers immediate reroute under Phase 15 baseline
    k_store._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    dec = adapter.evaluate_agent(agent, k_store, current_time_s=1.0)
    assert dec.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
    assert list(agent.route.node_ids) != old_node_ids
    assert "edge_r0_c0_to_r0_c1" not in [s.edge_id for s in agent._segments]
