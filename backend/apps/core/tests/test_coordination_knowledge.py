"""Unit tests for Phase 13 vehicle-private knowledge store and belief tracking."""

import pytest

from apps.core.coordination.exceptions import (
    DuplicateReportError,
    ExpiredReportError,
)
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    BeliefStatus,
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    HazardReport,
    HazardSeverity,
    HazardType,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadEdge, RoadGraph, RoadNode


@pytest.fixture
def sample_graph() -> RoadGraph:
    """Fixture producing a simple 2-node, 1-edge road graph."""
    g = RoadGraph(name="test_graph")
    g.add_node(RoadNode(id="node_A", position=Position2D(x=0.0, y=0.0)))
    g.add_node(RoadNode(id="node_B", position=Position2D(x=100.0, y=0.0)))
    g.add_edge(
        RoadEdge(
            id="edge_AB",
            start_node_id="node_A",
            end_node_id="node_B",
            length_m=100.0,
            speed_limit_mps=15.0,
        )
    )
    return g


class TestVehicleKnowledgeStore:
    """Tests for VehicleKnowledgeStore operations, isolation, queries, and rollback."""

    def test_store_isolation_between_vehicles(self) -> None:
        store_1 = VehicleKnowledgeStore(vehicle_id="veh_1")
        store_2 = VehicleKnowledgeStore(vehicle_id="veh_2")

        report = CongestionReport(
            report_id="cong_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=10.0,
            congestion_level=CongestionLevel.HIGH,
        )

        store_1.add_observation(report, current_time_s=10.0)

        # Vehicle 1 has report and belief
        assert store_1.report_count == 1
        assert store_1.belief_count == 1
        assert store_1.get_report("cong_1") is not None
        assert store_1.get_belief("congestion:edge_AB") is not None

        # Vehicle 2 has zero leakage
        assert store_2.report_count == 0
        assert store_2.belief_count == 0
        assert store_2.get_report("cong_1") is None
        assert store_2.get_belief("congestion:edge_AB") is None

    def test_add_observation_and_duplicate_rejection(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        report = RoadClosureReport(
            report_id="closure_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=5.0,
            closure_status=RoadClosureStatus.CLOSED,
        )

        assert store.add_observation(report, current_time_s=5.0) is True

        # Duplicate observation with same report_id raises DuplicateReportError
        with pytest.raises(DuplicateReportError):
            store.add_observation(report, current_time_s=5.0)

    def test_add_expired_observation_raises(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        expired_report = CongestionReport(
            report_id="cong_exp",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=5.0,
            expiry_timestamp_s=10.0,
        )

        with pytest.raises(ExpiredReportError):
            store.add_observation(expired_report, current_time_s=15.0)

    def test_ingest_received_report_duplicate_and_expiration(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        report = HazardReport(
            report_id="haz_1",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_2",
            hazard_type=HazardType.DEBRIS,
            severity=HazardSeverity.MEDIUM,
            edge_id="edge_AB",
            timestamp_s=12.0,
            expiry_timestamp_s=30.0,
            confidence=0.8,
        )

        # Ingestion succeeds
        assert store.ingest_report(report, current_time_s=12.0) is True
        assert store.report_count == 1

        # Duplicate ingestion is gracefully rejected (returns False, no duplicate entries)
        assert store.ingest_report(report, current_time_s=15.0) is False
        assert store.report_count == 1

        # Expired report is rejected
        expired_report = HazardReport(
            report_id="haz_2",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_3",
            hazard_type=HazardType.ANIMAL,
            severity=HazardSeverity.LOW,
            edge_id="edge_AB",
            timestamp_s=5.0,
            expiry_timestamp_s=10.0,
        )
        assert store.ingest_report(expired_report, current_time_s=15.0) is False
        assert store.report_count == 1

    def test_deterministic_query_ordering(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")

        r1 = CongestionReport(
            report_id="cong_A",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_2",
            edge_id="edge_AB",
            timestamp_s=5.0,
        )
        r2 = CongestionReport(
            report_id="cong_B",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_3",
            edge_id="edge_AB",
            timestamp_s=15.0,
        )
        r3 = CongestionReport(
            report_id="cong_C",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_4",
            edge_id="edge_AB",
            timestamp_s=10.0,
        )

        store.ingest_report(r1, current_time_s=5.0)
        store.ingest_report(r2, current_time_s=15.0)
        store.ingest_report(r3, current_time_s=10.0)

        results = store.query_reports(edge_id="edge_AB")
        # Ordered by -timestamp_s: cong_B (15.0) -> cong_C (10.0) -> cong_A (5.0)
        assert [r.report_id for r in results] == ["cong_B", "cong_C", "cong_A"]

    def test_query_filtering(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")

        r_cong = CongestionReport(
            report_id="cong_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_2",
            edge_id="edge_1",
            timestamp_s=1.0,
        )
        r_closure = RoadClosureReport(
            report_id="close_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_2",
            edge_id="edge_1",
            timestamp_s=2.0,
        )
        r_other_edge = CongestionReport(
            report_id="cong_2",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_2",
            edge_id="edge_2",
            timestamp_s=3.0,
        )

        store.ingest_report(r_cong, current_time_s=1.0)
        store.ingest_report(r_closure, current_time_s=2.0)
        store.ingest_report(r_other_edge, current_time_s=3.0)

        # Filter by edge
        assert len(store.query_reports(edge_id="edge_1")) == 2
        assert len(store.query_reports(edge_id="edge_2")) == 1

        # Filter by type
        assert len(store.query_reports(report_type=ReportType.ROAD_CLOSURE)) == 1
        assert len(store.query_reports(report_type=ReportType.CONGESTION)) == 2

        # Combined filter
        edge1_closures = store.query_reports(edge_id="edge_1", report_type=ReportType.ROAD_CLOSURE)
        assert len(edge1_closures) == 1
        assert edge1_closures[0].report_id == "close_1"

    def test_expire_entries_transitions_beliefs(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        report = RoadClosureReport(
            report_id="close_exp",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_2",
            edge_id="edge_AB",
            timestamp_s=5.0,
            expiry_timestamp_s=20.0,
        )

        store.ingest_report(report, current_time_s=5.0)
        belief = store.get_belief("closure:edge_AB")
        assert belief is not None
        assert belief.status == BeliefStatus.ACTIVE

        # Before expiry: active queries include it
        assert len(store.get_beliefs(active_only=True, current_time_s=19.0)) == 1

        # At or after expiry
        reports_exp, beliefs_exp = store.expire_entries(current_time_s=25.0)
        assert reports_exp == 1
        assert beliefs_exp == 1

        expired_belief = store.get_belief("closure:edge_AB")
        assert expired_belief is not None
        assert expired_belief.status == BeliefStatus.EXPIRED

        # Active query now excludes it
        assert len(store.get_beliefs(active_only=True, current_time_s=25.0)) == 0

    def test_immutable_snapshot(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        report = CongestionReport(
            report_id="cong_snap",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=5.0,
        )
        store.add_observation(report, current_time_s=5.0)

        snap = store.get_snapshot(current_time_s=5.0)
        assert snap.vehicle_id == "veh_1"
        assert snap.report_count == 1
        assert snap.belief_count == 1
        assert "cong_snap" in snap.reports

        # Modifying store does not alter past snapshot
        report2 = CongestionReport(
            report_id="cong_snap2",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=6.0,
        )
        store.add_observation(report2, current_time_s=6.0)
        assert snap.report_count == 1
        assert store.report_count == 2

    def test_atomic_rollback_capture_and_restore(self) -> None:
        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        report1 = CongestionReport(
            report_id="cong_rb_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="edge_AB",
            timestamp_s=5.0,
        )
        store.add_observation(report1, current_time_s=5.0)
        store.mark_report_forwarded("cong_rb_1")

        # Capture pre-tick state
        snapshot = store.capture_state()

        # Step advances store
        report2 = RoadClosureReport(
            report_id="close_rb_2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_2",
            edge_id="edge_AB",
            timestamp_s=6.0,
        )
        store.ingest_report(report2, current_time_s=6.0)
        store.mark_report_forwarded("close_rb_2")

        assert store.report_count == 2
        assert store.has_forwarded_report("close_rb_2") is True

        # Rollback
        store.restore_state(snapshot)

        assert store.report_count == 1
        assert store.get_report("close_rb_2") is None
        assert store.has_seen_report("close_rb_2") is False
        assert store.has_forwarded_report("close_rb_2") is False
        assert store.get_report("cong_rb_1") is not None
        assert store.has_forwarded_report("cong_rb_1") is True

    def test_cache_size_eviction(self) -> None:
        cfg = CoordinationConfig(max_cache_size=2)
        store = VehicleKnowledgeStore(vehicle_id="veh_1", config=cfg)

        r1 = CongestionReport(
            report_id="r1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=1.0,
        )
        r2 = CongestionReport(
            report_id="r2",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=2.0,
        )
        r3 = CongestionReport(
            report_id="r3",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=3.0,
        )

        store.ingest_report(r1, current_time_s=1.0)
        store.ingest_report(r2, current_time_s=2.0)
        assert store.report_count == 2

        # Ingesting 3rd report evicts r1 (oldest timestamp)
        store.ingest_report(r3, current_time_s=3.0)
        assert store.report_count == 2
        assert store.get_report("r1") is None
        assert store.get_report("r2") is not None
        assert store.get_report("r3") is not None

    def test_authoritative_graph_is_never_mutated(self, sample_graph: RoadGraph) -> None:
        initial_edges = len(sample_graph.edge_ids())
        assert sample_graph.has_edge("edge_AB") is True

        store = VehicleKnowledgeStore(vehicle_id="veh_1")
        closure_report = RoadClosureReport(
            report_id="closure_x",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_2",
            edge_id="edge_AB",
            timestamp_s=10.0,
            closure_status=RoadClosureStatus.CLOSED,
        )

        store.ingest_report(closure_report, current_time_s=10.0)

        # Vehicle's belief reflects closure
        belief = store.get_belief("closure:edge_AB")
        assert belief is not None
        assert belief.attributes["closure_status"] == RoadClosureStatus.CLOSED.value

        # Crucial architectural guarantee: Authoritative RoadGraph is completely unchanged!
        assert len(sample_graph.edge_ids()) == initial_edges
        assert sample_graph.has_edge("edge_AB") is True
