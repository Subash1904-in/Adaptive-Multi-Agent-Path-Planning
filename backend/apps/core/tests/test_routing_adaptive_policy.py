"""Unit and policy tests for adaptive rerouting decision policy, cooldowns, and hysteresis."""

import math

import pytest

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    CongestionLevel,
    CongestionReport,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.enums import VehicleState
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    RerouteDecisionType,
)


@pytest.fixture
def diamond_graph() -> RoadGraph:
    """Create a diamond road graph with two alternative paths of equal baseline cost.

    Top path:    n_start -> n_top -> n_dest  (e_top1: 100m, e_top2: 100m)
    Bottom path: n_start -> n_bot -> n_dest  (e_bot1: 100m, e_bot2: 100m)
    """
    g = RoadGraph(name="diamond_graph")
    g.add_node(RoadNode(id="n_start", position=Position2D(x=0.0, y=50.0)))
    g.add_node(RoadNode(id="n_top", position=Position2D(x=100.0, y=100.0)))
    g.add_node(RoadNode(id="n_bot", position=Position2D(x=100.0, y=0.0)))
    g.add_node(RoadNode(id="n_dest", position=Position2D(x=200.0, y=50.0)))

    # All edges: 100m, 10m/s -> 10s traversal
    g.add_edge(
        RoadEdge(
            id="e_top1",
            start_node_id="n_start",
            end_node_id="n_top",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
    )
    g.add_edge(
        RoadEdge(
            id="e_top2",
            start_node_id="n_top",
            end_node_id="n_dest",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
    )
    g.add_edge(
        RoadEdge(
            id="e_bot1",
            start_node_id="n_start",
            end_node_id="n_bot",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
    )
    g.add_edge(
        RoadEdge(
            id="e_bot2",
            start_node_id="n_bot",
            end_node_id="n_dest",
            length_m=100.0,
            speed_limit_mps=10.0,
        )
    )
    return g


@pytest.fixture
def sample_vehicle_agent(diamond_graph: RoadGraph) -> tuple[VehicleAgent, VehicleKnowledgeStore]:
    """Create a VehicleAgent following the top path (n_start -> n_top -> n_dest)."""
    route = Route(
        id="route_top",
        node_ids=["n_start", "n_top", "n_dest"],
        edge_ids=["e_top1", "e_top2"],
        total_distance_m=200.0,
        estimated_duration_s=20.0,
    )
    v = Vehicle(
        id="veh_01",
        position=Position2D(x=0.0, y=50.0),
        target_node_id="n_dest",
    )
    agent = VehicleAgent(vehicle=v, road_graph=diamond_graph, route=route)
    agent.start()

    store = VehicleKnowledgeStore(vehicle_id="veh_01")
    return agent, store


class TestAdaptiveRoutingPolicy:
    """Test suite for DynamicRouteAdapter decision policies."""

    def test_disabled_policy_returns_no_change(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """When adaptive routing is disabled, evaluation immediately returns NO_CHANGE."""
        agent, store = sample_vehicle_agent
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=False),
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.NO_CHANGE
        assert dec.vehicle_id == "veh_01"

    def test_destination_reached_suppresses_rerouting(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Arrived vehicles return DESTINATION_REACHED and bypass planning."""
        agent, store = sample_vehicle_agent
        agent.vehicle.state = VehicleState.ARRIVED
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.DESTINATION_REACHED

    def test_closure_triggers_immediate_reroute_acceptance(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Reported closure on active route triggers immediate reroute if alternative exists."""
        agent, store = sample_vehicle_agent
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )

        # Ingest closure on top path (e_top2)
        closure = RoadClosureReport(
            report_id="cls_top",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_other",
            edge_id="e_top2",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=1.0,
            expiry_timestamp_s=100.0,
        )
        store.ingest_report(closure, current_time_s=1.0)

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
        assert dec.new_route_id is not None
        assert math.isinf(dec.current_cost)
        assert dec.cost_improvement == float("inf")
        # Agent's new route should now avoid e_top2 and use bottom path
        assert "e_bot1" in [s.edge_id for s in agent._segments]
        assert "e_bot2" in [s.edge_id for s in agent._segments]

    def test_no_alternative_route_when_destination_blocked(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """When all paths to destination are closed, NO_ALTERNATIVE_ROUTE is returned."""
        agent, store = sample_vehicle_agent
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )

        # Close both top and bottom incoming edges to n_dest
        store.ingest_report(
            RoadClosureReport(
                report_id="cls_1",
                report_type=ReportType.ROAD_CLOSURE,
                reporting_vehicle_id="veh_02",
                edge_id="e_top2",
                closure_status=RoadClosureStatus.CLOSED,
                timestamp_s=1.0,
                expiry_timestamp_s=100.0,
            ),
            current_time_s=1.0,
        )
        store.ingest_report(
            RoadClosureReport(
                report_id="cls_2",
                report_type=ReportType.ROAD_CLOSURE,
                reporting_vehicle_id="veh_03",
                edge_id="e_bot2",
                closure_status=RoadClosureStatus.CLOSED,
                timestamp_s=1.0,
                expiry_timestamp_s=100.0,
            ),
            current_time_s=1.0,
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.NO_ALTERNATIVE_ROUTE
        assert adapter.metrics.no_route_outcomes == 1

    def test_significant_congestion_triggers_reroute(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Severe congestion that exceeds thresholds triggers accepted reroute."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=5.0,
            min_relative_benefit=0.10,
            congestion_multipliers={"severe": 4.0},
        )
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # Baseline: top path = 20s.
        # Report severe congestion on e_top1: 10s * 4 = 40s -> top path = 50s.
        # Bottom path = 20s. Benefit = 50 - 20 = 30s >= max(5.0, 0.10 * 50 = 5.0).
        store.ingest_report(
            CongestionReport(
                report_id="cong_top",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_02",
                edge_id="e_top1",
                congestion_level=CongestionLevel.SEVERE,
                timestamp_s=1.0,
                expiry_timestamp_s=60.0,
            ),
            current_time_s=1.0,
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
        assert dec.cost_improvement == pytest.approx(30.0)
        assert adapter.metrics.accepted_reroutes == 1

    def test_insufficient_absolute_benefit_rejected(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Improvement below min_absolute_benefit is rejected as INSUFFICIENT_BENEFIT."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=100.0,  # High threshold
            min_relative_benefit=0.01,
            congestion_multipliers={"moderate": 2.0},
        )
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # Moderate congestion on e_top1: 10s * 2 = 20s -> top path = 30s.
        # Bottom path = 20s. Benefit = 10s < 100.0s.
        store.ingest_report(
            CongestionReport(
                report_id="cong_mod",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_02",
                edge_id="e_top1",
                congestion_level=CongestionLevel.MODERATE,
                timestamp_s=1.0,
                expiry_timestamp_s=60.0,
            ),
            current_time_s=1.0,
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.INSUFFICIENT_BENEFIT
        assert dec.cost_improvement == pytest.approx(10.0)
        assert adapter.metrics.insufficient_benefit_suppressions == 1

    def test_insufficient_relative_benefit_rejected(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Improvement below min_relative_benefit is rejected as INSUFFICIENT_BENEFIT."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=1.0,
            min_relative_benefit=0.50,  # Requires 50% improvement
            congestion_multipliers={"low": 1.2},
        )
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # Low congestion on e_top1: 10s * 1.2 = 12s -> top path = 22s.
        # Bottom path = 20s. Benefit = 2s. Required = 0.50 * 22s = 11s.
        store.ingest_report(
            CongestionReport(
                report_id="cong_low",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_02",
                edge_id="e_top1",
                congestion_level=CongestionLevel.LOW,
                timestamp_s=1.0,
                expiry_timestamp_s=60.0,
            ),
            current_time_s=1.0,
        )

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.INSUFFICIENT_BENEFIT
        assert dec.cost_improvement == pytest.approx(2.0)

    def test_rerouting_cooldown_prevents_subsequent_recalculation(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """After an accepted reroute, evaluations within cooldown return COOLDOWN_ACTIVE."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=1.0,
            reroute_cooldown_s=10.0,
            congestion_multipliers={"severe": 4.0},
        )
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # 1. First evaluation: accepted reroute at t = 1.0s
        store.ingest_report(
            CongestionReport(
                report_id="cong_1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_02",
                edge_id="e_top1",
                congestion_level=CongestionLevel.SEVERE,
                timestamp_s=1.0,
                expiry_timestamp_s=60.0,
            ),
            current_time_s=1.0,
        )
        dec1 = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec1.decision_type == RerouteDecisionType.REROUTE_ACCEPTED

        # 2. Second evaluation at t = 5.0s (within 10s cooldown)
        dec2 = adapter.evaluate_agent(agent, store, current_time_s=5.0)
        assert dec2.decision_type == RerouteDecisionType.COOLDOWN_ACTIVE
        assert adapter.metrics.cooldown_suppressions == 1

        # 3. Third evaluation at t = 12.0s (past cooldown)
        dec3 = adapter.evaluate_agent(agent, store, current_time_s=12.0)
        assert dec3.decision_type != RerouteDecisionType.COOLDOWN_ACTIVE

    def test_repeat_suppression_prevents_redundant_graph_search(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """Unchanged local beliefs and route progress suppress redundant recalculation."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(
            enabled=True,
            repeat_suppression=True,
            min_absolute_benefit=100.0,  # reject to avoid cooldown
        )
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # Ingest a report
        store.ingest_report(
            CongestionReport(
                report_id="cong_rep",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_02",
                edge_id="e_top1",
                congestion_level=CongestionLevel.LOW,
                timestamp_s=1.0,
                expiry_timestamp_s=60.0,
            ),
            current_time_s=1.0,
        )

        dec1 = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec1.decision_type == RerouteDecisionType.INSUFFICIENT_BENEFIT

        # Second evaluation with unchanged beliefs and route progress
        dec2 = adapter.evaluate_agent(agent, store, current_time_s=2.0)
        assert dec2.decision_type == RerouteDecisionType.NO_FRESH_INFORMATION

    def test_expired_closure_restores_original_path_eligibility(
        self,
        diamond_graph: RoadGraph,
        sample_vehicle_agent: tuple[VehicleAgent, VehicleKnowledgeStore],
    ) -> None:
        """When a closure expires, the edge becomes available again for routing."""
        agent, store = sample_vehicle_agent
        cfg = AdaptiveRoutingConfig(enabled=True, min_absolute_benefit=0.1)
        adapter = DynamicRouteAdapter(road_graph=diamond_graph, config=cfg)

        # Report closure on bottom path with short TTL
        store.ingest_report(
            RoadClosureReport(
                report_id="cls_short",
                report_type=ReportType.ROAD_CLOSURE,
                reporting_vehicle_id="veh_02",
                edge_id="e_bot1",
                closure_status=RoadClosureStatus.CLOSED,
                timestamp_s=1.0,
                expiry_timestamp_s=5.0,
            ),
            current_time_s=1.0,
        )

        # At t = 2.0, e_bot1 is closed
        evaluator_active = adapter.get_evaluator(store)
        assert evaluator_active.is_edge_closed("e_bot1", current_time_s=2.0)

        # At t = 6.0, e_bot1 is expired and open again
        evaluator_expired = adapter.get_evaluator(store)
        assert not evaluator_expired.is_edge_closed("e_bot1", current_time_s=6.0)

    def test_step_processes_agents_in_deterministic_order(self, diamond_graph: RoadGraph) -> None:
        """DynamicRouteAdapter.step processes agents in sorted vehicle ID order."""
        v_b = Vehicle(id="veh_b", position=Position2D(x=0.0, y=50.0), target_node_id="n_dest")
        v_a = Vehicle(id="veh_a", position=Position2D(x=0.0, y=50.0), target_node_id="n_dest")

        route = Route(
            id="r",
            node_ids=["n_start", "n_top", "n_dest"],
            edge_ids=["e_top1", "e_top2"],
            total_distance_m=200.0,
        )
        agent_b = VehicleAgent(vehicle=v_b, road_graph=diamond_graph, route=route)
        agent_a = VehicleAgent(vehicle=v_a, road_graph=diamond_graph, route=route)
        agent_b.start()
        agent_a.start()

        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )

        # Pass agents in reversed order
        decisions = adapter.step(
            agents=[agent_b, agent_a],
            get_knowledge_store_fn=lambda vid: VehicleKnowledgeStore(vehicle_id=vid),
            current_time_s=1.0,
        )

        # Decisions must be strictly sorted by vehicle_id
        assert len(decisions) == 2
        assert decisions[0].vehicle_id == "veh_a"
        assert decisions[1].vehicle_id == "veh_b"

    def test_evaluate_agent_without_route_or_target(self, diamond_graph: RoadGraph) -> None:
        """Agent without route or target returns NO_CHANGE."""
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )
        v = Vehicle(id="v_noroute", position=Position2D(x=0.0, y=50.0), target_node_id=None)
        agent = VehicleAgent(vehicle=v, road_graph=diamond_graph, route=None)
        store = VehicleKnowledgeStore(vehicle_id="v_noroute")

        dec = adapter.evaluate_agent(agent, store, current_time_s=1.0)
        assert dec.decision_type == RerouteDecisionType.NO_CHANGE

    def test_adapter_state_capture_and_restore(self, diamond_graph: RoadGraph) -> None:
        """Capture and restore preserves cooldown timestamps and belief fingerprints."""
        adapter = DynamicRouteAdapter(
            road_graph=diamond_graph,
            config=AdaptiveRoutingConfig(enabled=True),
        )
        adapter._last_reroute_time["veh_01"] = 12.5
        adapter._last_belief_fingerprints["veh_01"] = "hash_xyz"

        snap = adapter.capture_state()
        adapter.reset()
        assert len(adapter._last_reroute_time) == 0
        assert len(adapter._last_belief_fingerprints) == 0

        adapter.restore_state(snap)
        assert adapter._last_reroute_time["veh_01"] == 12.5
        assert adapter._last_belief_fingerprints["veh_01"] == "hash_xyz"
