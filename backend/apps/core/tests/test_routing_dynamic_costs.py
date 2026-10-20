"""Unit and property tests for dynamic edge cost evaluation using vehicle-private knowledge."""

import math

import pytest

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    CongestionLevel,
    CongestionReport,
    HazardReport,
    HazardSeverity,
    HazardType,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.costs import calculate_edge_cost
from apps.core.routing.evaluator import DynamicEdgeCostEvaluator
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode


@pytest.fixture
def test_graph() -> RoadGraph:
    """Create a simple 3-node, 2-edge graph for cost testing."""
    g = RoadGraph(name="test_costs_graph")
    g.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
    g.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=0.0)))
    g.add_node(RoadNode(id="n2", position=Position2D(x=200.0, y=0.0)))

    # e0: 100m, 10m/s -> travel_time = 10s
    e0 = RoadEdge(
        id="e0",
        start_node_id="n0",
        end_node_id="n1",
        length_m=100.0,
        speed_limit_mps=10.0,
    )
    # e1: 100m, 20m/s -> travel_time = 5s
    e1 = RoadEdge(
        id="e1",
        start_node_id="n1",
        end_node_id="n2",
        length_m=100.0,
        speed_limit_mps=20.0,
    )
    g.add_edge(e0)
    g.add_edge(e1)
    return g


class TestDynamicEdgeCostEvaluator:
    """Test suite for DynamicEdgeCostEvaluator."""

    def test_baseline_costs_remain_unchanged(self, test_graph: RoadGraph) -> None:
        """Baseline graph and edge objects must remain immutable during evaluation."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        edge = test_graph.get_edge("e0")
        base_cost = calculate_edge_cost(edge, CostMode.TRAVEL_TIME)
        eval_cost = evaluator.calculate_dynamic_edge_cost(edge, CostMode.TRAVEL_TIME)

        assert eval_cost == pytest.approx(base_cost)
        assert edge.length_m == 100.0
        assert edge.speed_limit_mps == 10.0

    def test_congestion_multiplier_alters_evaluated_cost(self, test_graph: RoadGraph) -> None:
        """Reported congestion levels apply validated multiplicative penalties."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        cfg = AdaptiveRoutingConfig(
            congestion_multipliers={
                "low": 1.2,
                "moderate": 1.8,
                "severe": 3.0,
                "extreme": 6.0,
            }
        )
        evaluator = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store, config=cfg
        )

        edge = test_graph.get_edge("e0")
        base_cost = calculate_edge_cost(edge, CostMode.TRAVEL_TIME)  # 10.0s

        report = CongestionReport(
            report_id="cong_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            congestion_level=CongestionLevel.SEVERE,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(report, current_time_s=1.0)

        eval_cost = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=2.0
        )
        assert eval_cost == pytest.approx(base_cost * 3.0)

    def test_road_closure_blocks_affected_edge(self, test_graph: RoadGraph) -> None:
        """Active road closure belief makes edge cost infinite and marks it closed."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        edge = test_graph.get_edge("e0")
        closure_report = RoadClosureReport(
            report_id="cls_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            closure_status=RoadClosureStatus.CLOSED,
            reason="Construction",
            timestamp_s=1.0,
            expiry_timestamp_s=100.0,
        )
        store.ingest_report(closure_report, current_time_s=1.0)

        closed_edges = evaluator.get_closed_edges(current_time_s=5.0)
        assert "e0" in closed_edges
        assert evaluator.is_edge_closed("e0", current_time_s=5.0)

        eval_cost = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=5.0
        )
        assert math.isinf(eval_cost)

    def test_reopening_removes_closure_restriction(self, test_graph: RoadGraph) -> None:
        """Reopening report superseding closure removes the edge restriction."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        edge = test_graph.get_edge("e0")
        base_cost = calculate_edge_cost(edge, CostMode.TRAVEL_TIME)

        closure = RoadClosureReport(
            report_id="cls_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=1.0,
            expiry_timestamp_s=100.0,
        )
        store.ingest_report(closure, current_time_s=1.0)
        assert evaluator.is_edge_closed("e0", current_time_s=2.0)

        reopening = RoadClosureReport(
            report_id="cls_2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_03",
            edge_id="e0",
            closure_status=RoadClosureStatus.REOPENED,
            timestamp_s=3.0,
            expiry_timestamp_s=100.0,
        )
        store.ingest_report(reopening, current_time_s=3.0)

        assert not evaluator.is_edge_closed("e0", current_time_s=4.0)
        eval_cost = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=4.0
        )
        assert eval_cost == pytest.approx(base_cost)

    def test_hazard_penalties_apply_only_to_mapped_edges(self, test_graph: RoadGraph) -> None:
        """Hazard reports apply penalties strictly to their target edges."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        cfg = AdaptiveRoutingConfig(
            hazard_penalties={"low": 5.0, "medium": 15.0, "high": 25.0, "critical": 50.0}
        )
        evaluator = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store, config=cfg
        )

        e0 = test_graph.get_edge("e0")
        e1 = test_graph.get_edge("e1")
        base_e0 = calculate_edge_cost(e0, CostMode.TRAVEL_TIME)
        base_e1 = calculate_edge_cost(e1, CostMode.TRAVEL_TIME)

        hazard = HazardReport(
            report_id="haz_1",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            hazard_type=HazardType.DEBRIS,
            severity=HazardSeverity.HIGH,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(hazard, current_time_s=1.0)

        assert evaluator.get_hazard_penalty("e0", current_time_s=2.0) == 25.0
        assert evaluator.get_hazard_penalty("e1", current_time_s=2.0) == 0.0

        eval_e0 = evaluator.calculate_dynamic_edge_cost(
            e0, CostMode.TRAVEL_TIME, current_time_s=2.0
        )
        eval_e1 = evaluator.calculate_dynamic_edge_cost(
            e1, CostMode.TRAVEL_TIME, current_time_s=2.0
        )

        assert eval_e0 == pytest.approx(base_e0 + 25.0)
        assert eval_e1 == pytest.approx(base_e1)

    def test_unmapped_hazard_handled_explicitly(self, test_graph: RoadGraph) -> None:
        """Hazards without edge_id or on unknown edges do not apply penalties to graph edges."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        cfg = AdaptiveRoutingConfig(
            hazard_penalties={"low": 5.0, "medium": 15.0, "high": 30.0, "critical": 60.0}
        )
        evaluator = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store, config=cfg
        )

        unmapped = HazardReport(
            report_id="haz_unmapped",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_02",
            edge_id=None,
            position=Position2D(x=999.0, y=999.0),
            hazard_type=HazardType.OBSTACLE,
            severity=HazardSeverity.HIGH,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(unmapped, current_time_s=1.0)

        assert evaluator.get_hazard_penalty("e0", current_time_s=2.0) == 0.0
        assert evaluator.get_hazard_penalty("e1", current_time_s=2.0) == 0.0

    def test_stale_or_expired_report_does_not_alter_cost(self, test_graph: RoadGraph) -> None:
        """Beliefs past their expiry timestamp must not influence edge evaluation."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        edge = test_graph.get_edge("e0")
        base_cost = calculate_edge_cost(edge, CostMode.TRAVEL_TIME)

        closure = RoadClosureReport(
            report_id="cls_exp",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=1.0,
            expiry_timestamp_s=6.0,
        )
        store.ingest_report(closure, current_time_s=1.0)

        # Active at t = 5.0
        assert evaluator.is_edge_closed("e0", current_time_s=5.0)

        # Expired at t = 7.0
        assert not evaluator.is_edge_closed("e0", current_time_s=7.0)
        cost_at_7 = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=7.0
        )
        assert cost_at_7 == pytest.approx(base_cost)

    def test_disputed_beliefs_follow_configured_policy(self, test_graph: RoadGraph) -> None:
        """Disputed closure blocks edge under conservative policy, but permits under permissive."""
        # 1. Conservative (default)
        store_cons = VehicleKnowledgeStore(vehicle_id="v_cons")
        eval_cons = DynamicEdgeCostEvaluator(
            road_graph=test_graph,
            knowledge_store=store_cons,
            config=AdaptiveRoutingConfig(disputed_closure_policy="conservative"),
        )

        disputed_belief = BeliefRecord(
            belief_id="belief_closure_e0",
            belief_type=ReportType.ROAD_CLOSURE,
            target_id="e0",
            status=BeliefStatus.DISPUTED,
            confidence=0.5,
            last_evidence_timestamp_s=1.0,
            expiry_timestamp_s=50.0,
            attributes={"closure_status": "closed"},
        )
        store_cons._beliefs["belief_closure_e0"] = disputed_belief

        assert eval_cons.is_edge_closed("e0", current_time_s=2.0)

        # 2. Permissive
        store_perm = VehicleKnowledgeStore(vehicle_id="v_perm")
        eval_perm = DynamicEdgeCostEvaluator(
            road_graph=test_graph,
            knowledge_store=store_perm,
            config=AdaptiveRoutingConfig(disputed_closure_policy="permissive"),
        )
        store_perm._beliefs["belief_closure_e0"] = disputed_belief

        assert not eval_perm.is_edge_closed("e0", current_time_s=2.0)

    def test_costs_are_finite_non_negative_and_deterministic(self, test_graph: RoadGraph) -> None:
        """Edge costs must always be >= 0, finite for open edges, and bit-identical across runs."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        edge = test_graph.get_edge("e0")
        c1 = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=10.0
        )
        c2 = evaluator.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=10.0
        )

        assert c1 == c2
        assert math.isfinite(c1)
        assert c1 > 0.0

    def test_vehicle_private_knowledge_isolation(self, test_graph: RoadGraph) -> None:
        """Vehicle 1 with traffic knowledge computes different cost than Vehicle 2."""
        store1 = VehicleKnowledgeStore(vehicle_id="veh_01")
        store2 = VehicleKnowledgeStore(vehicle_id="veh_02")

        cfg = AdaptiveRoutingConfig(congestion_multipliers={"severe": 4.0})
        evaluator1 = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store1, config=cfg
        )
        evaluator2 = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store2, config=cfg
        )

        report = CongestionReport(
            report_id="cong_iso",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_03",
            edge_id="e0",
            congestion_level=CongestionLevel.SEVERE,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store1.ingest_report(report, current_time_s=1.0)

        edge = test_graph.get_edge("e0")
        cost1 = evaluator1.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=5.0
        )
        cost2 = evaluator2.calculate_dynamic_edge_cost(
            edge, CostMode.TRAVEL_TIME, current_time_s=5.0
        )

        assert cost1 > cost2
        assert cost2 == pytest.approx(calculate_edge_cost(edge, CostMode.TRAVEL_TIME))

    def test_pro_rated_remaining_route_cost(self, test_graph: RoadGraph) -> None:
        """Current edge cost is pro-rated according to vehicle progress."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        route = Route(
            id="r_test",
            node_ids=["n0", "n1", "n2"],
            edge_ids=["e0", "e1"],
            total_distance_m=200.0,
            estimated_duration_s=15.0,
        )

        v = Vehicle(
            id="veh_01",
            position=Position2D(x=0.0, y=0.0),
            target_node_id="n2",
        )
        agent = VehicleAgent(vehicle=v, road_graph=test_graph, route=route)
        agent.start()

        # Step agent halfway across e0 (length 100m, speed limit 10m/s)
        agent.current_edge_index = 0
        agent.distance_along_segment_m = 50.0  # 50% traversed

        # Remaining on e0: 50m / 10m/s = 5s.
        # Future e1: 100m / 20m/s = 5s.
        # Total = 10s.
        rem_cost = evaluator.evaluate_remaining_route_cost(agent, CostMode.TRAVEL_TIME)
        assert rem_cost == pytest.approx(10.0)

    def test_remaining_route_cost_infinite_on_closed_downstream_edge(
        self, test_graph: RoadGraph
    ) -> None:
        """When downstream edge is closed, remaining route cost returns infinity."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        route = Route(
            id="r_test",
            node_ids=["n0", "n1", "n2"],
            edge_ids=["e0", "e1"],
            total_distance_m=200.0,
            estimated_duration_s=15.0,
        )

        v = Vehicle(
            id="veh_01",
            position=Position2D(x=0.0, y=0.0),
            target_node_id="n2",
        )
        agent = VehicleAgent(vehicle=v, road_graph=test_graph, route=route)
        agent.start()
        agent.current_edge_index = 0

        # Close downstream edge e1
        closure = RoadClosureReport(
            report_id="cls_downstream",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_02",
            edge_id="e1",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=1.0,
            expiry_timestamp_s=100.0,
        )
        store.ingest_report(closure, current_time_s=1.0)

        rem_cost = evaluator.evaluate_remaining_route_cost(
            agent, CostMode.TRAVEL_TIME, current_time_s=2.0
        )
        assert math.isinf(rem_cost)

    def test_evaluator_without_knowledge_store(self, test_graph: RoadGraph) -> None:
        """Evaluator without knowledge store returns baseline costs and open roads."""
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=None)
        assert not evaluator.is_edge_closed("e0")
        assert evaluator.get_congestion_multiplier("e0") == 1.0
        assert evaluator.get_hazard_penalty("e0") == 0.0

    def test_low_confidence_beliefs_ignored(self, test_graph: RoadGraph) -> None:
        """Beliefs with confidence below threshold are ignored."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        cfg = AdaptiveRoutingConfig(min_confidence_threshold=0.8)
        evaluator = DynamicEdgeCostEvaluator(
            road_graph=test_graph, knowledge_store=store, config=cfg
        )

        closure = RoadClosureReport(
            report_id="cls_low_conf",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            closure_status=RoadClosureStatus.CLOSED,
            confidence=0.5,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(closure, current_time_s=1.0)
        assert not evaluator.is_edge_closed("e0", current_time_s=1.0)

    def test_travel_time_factor_congestion_attribute(self, test_graph: RoadGraph) -> None:
        """Direct travel_time_factor attribute in congestion belief is applied."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)

        rep = CongestionReport(
            report_id="cong_ttf",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            congestion_level=CongestionLevel.MODERATE,
            travel_time_factor=3.5,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(rep, current_time_s=1.0)
        assert evaluator.get_congestion_multiplier("e0", current_time_s=2.0) == 3.5

    def test_distance_cost_mode_with_hazard(self, test_graph: RoadGraph) -> None:
        """Distance cost mode adds hazard penalty directly to length in meters."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=store)
        edge = test_graph.get_edge("e0")

        hazard = HazardReport(
            report_id="haz_dist",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_02",
            edge_id="e0",
            hazard_type=HazardType.OBSTACLE,
            severity=HazardSeverity.LOW,
            timestamp_s=1.0,
            expiry_timestamp_s=60.0,
        )
        store.ingest_report(hazard, current_time_s=1.0)

        cost = evaluator.calculate_dynamic_edge_cost(edge, CostMode.DISTANCE, current_time_s=2.0)
        assert cost == pytest.approx(100.0 + 5.0)

    def test_evaluate_remaining_route_cost_completed_or_empty(self, test_graph: RoadGraph) -> None:
        """Completed or empty route returns 0.0 remaining cost."""
        evaluator = DynamicEdgeCostEvaluator(road_graph=test_graph, knowledge_store=None)
        route = Route(
            id="r_done",
            node_ids=["n0", "n1"],
            edge_ids=["e0"],
            total_distance_m=100.0,
        )
        v = Vehicle(id="v1", position=Position2D(x=100.0, y=0.0), target_node_id="n1")
        agent = VehicleAgent(vehicle=v, road_graph=test_graph, route=route)
        agent.start()
        agent.current_edge_index = 1  # beyond end
        assert evaluator.evaluate_remaining_route_cost(agent, CostMode.TRAVEL_TIME) == 0.0
