"""Unit tests for Phase 13 typed traffic reports, beliefs, and coordination configuration models."""

import json

import pytest

from apps.core.coordination.exceptions import (
    CoordinationValidationError,
    InvalidReportError,
)
from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    CoordinationMetrics,
    FusionPolicy,
    HazardReport,
    HazardSeverity,
    HazardType,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
    traffic_report_from_dict,
)
from apps.core.domain.values import Position2D


class TestCongestionReport:
    """Tests for typed CongestionReport construction, validation, and serialization."""

    def test_valid_congestion_report_defaults(self) -> None:
        report = CongestionReport(
            report_id="cong-001",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh-1",
            edge_id="edge-north-1",
            timestamp_s=12.5,
        )
        assert report.report_id == "cong-001"
        assert report.report_type == ReportType.CONGESTION
        assert report.reporting_vehicle_id == "veh-1"
        assert report.edge_id == "edge-north-1"
        assert report.timestamp_s == 12.5
        assert report.expiry_timestamp_s is None
        assert report.confidence == 1.0
        assert report.congestion_level == CongestionLevel.MODERATE
        assert report.estimated_speed_mps is None
        assert report.travel_time_factor is None
        assert report.schema_version == "1.0.0"
        assert not report.is_expired(10.0)
        assert not report.is_expired(100.0)

    def test_valid_congestion_report_all_fields(self) -> None:
        report = CongestionReport(
            report_id="cong-002",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh-2",
            edge_id="edge-east-2",
            timestamp_s=5.0,
            expiry_timestamp_s=25.0,
            confidence=0.85,
            provenance=("veh-1", "veh-2"),
            sequence_number=3,
            congestion_level=CongestionLevel.SEVERE,
            estimated_speed_mps=2.5,
            travel_time_factor=3.0,
            metadata={"source": "camera"},
        )
        assert report.expiry_timestamp_s == 25.0
        assert report.confidence == 0.85
        assert report.provenance == ("veh-1", "veh-2")
        assert report.sequence_number == 3
        assert report.congestion_level == CongestionLevel.SEVERE
        assert report.estimated_speed_mps == 2.5
        assert report.travel_time_factor == 3.0
        assert not report.is_expired(24.9)
        assert report.is_expired(25.0)
        assert report.is_expired(30.0)

    def test_invalid_report_id_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="report_id"):
            CongestionReport(
                report_id="",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=1.0,
            )

    def test_invalid_reporting_vehicle_id_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="reporting_vehicle_id"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="   ",
                edge_id="edge-1",
                timestamp_s=1.0,
            )

    def test_invalid_edge_id_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="edge_id"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="",
                timestamp_s=1.0,
            )

    def test_invalid_timestamp_raises(self) -> None:
        with pytest.raises(CoordinationValidationError, match="timestamp_s"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=-1.0,
            )
        with pytest.raises(CoordinationValidationError, match="timestamp_s"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=float("nan"),
            )

    def test_expiry_less_than_timestamp_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="expiry_timestamp_s"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=10.0,
                expiry_timestamp_s=5.0,
            )

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="confidence"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=1.0,
                confidence=1.5,
            )
        with pytest.raises(CoordinationValidationError, match="confidence"):
            CongestionReport(
                report_id="cong-1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh-1",
                edge_id="edge-1",
                timestamp_s=1.0,
                confidence=-0.1,
            )

    def test_serialization_round_trip(self) -> None:
        original = CongestionReport(
            report_id="cong-003",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh-1",
            edge_id="edge-south-3",
            timestamp_s=10.0,
            expiry_timestamp_s=40.0,
            confidence=0.9,
            provenance=("veh-1",),
            sequence_number=1,
            congestion_level=CongestionLevel.HIGH,
            estimated_speed_mps=4.2,
            travel_time_factor=2.1,
            metadata={"notes": "heavy traffic"},
        )
        d = original.to_dict()
        reconstructed = traffic_report_from_dict(d)
        assert isinstance(reconstructed, CongestionReport)
        assert reconstructed.report_id == original.report_id
        assert reconstructed.congestion_level == original.congestion_level
        assert reconstructed.estimated_speed_mps == original.estimated_speed_mps
        assert reconstructed.travel_time_factor == original.travel_time_factor
        assert reconstructed.confidence == original.confidence
        assert reconstructed.provenance == original.provenance

        # JSON serialization stability
        json_str = original.to_json()
        assert "cong-003" in json_str
        parsed_json = json.loads(json_str)
        assert parsed_json["congestion_level"] == "high"


class TestRoadClosureReport:
    """Tests for typed RoadClosureReport."""

    def test_valid_closure_report(self) -> None:
        report = RoadClosureReport(
            report_id="close-001",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh-infra",
            edge_id="edge-closed-1",
            timestamp_s=15.0,
            expiry_timestamp_s=60.0,
            closure_status=RoadClosureStatus.CLOSED,
            reason="Construction works",
        )
        assert report.closure_status == RoadClosureStatus.CLOSED
        assert report.reason == "Construction works"
        assert not report.is_expired(50.0)
        assert report.is_expired(60.0)

    def test_reopen_report(self) -> None:
        report = RoadClosureReport(
            report_id="close-002",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh-3",
            edge_id="edge-closed-1",
            timestamp_s=70.0,
            closure_status=RoadClosureStatus.REOPENED,
            reason="Cleared",
        )
        assert report.closure_status == RoadClosureStatus.REOPENED

    def test_serialization_round_trip(self) -> None:
        report = RoadClosureReport(
            report_id="close-003",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh-2",
            edge_id="edge-5",
            timestamp_s=2.0,
            closure_status=RoadClosureStatus.CLOSED,
            reason="Sinkhole",
        )
        d = report.to_dict()
        reconstructed = traffic_report_from_dict(d)
        assert isinstance(reconstructed, RoadClosureReport)
        assert reconstructed.closure_status == RoadClosureStatus.CLOSED
        assert reconstructed.reason == "Sinkhole"


class TestHazardReport:
    """Tests for typed HazardReport."""

    def test_valid_hazard_with_edge(self) -> None:
        report = HazardReport(
            report_id="haz-001",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh-4",
            hazard_type=HazardType.ACCIDENT,
            severity=HazardSeverity.CRITICAL,
            edge_id="edge-main-1",
            timestamp_s=8.0,
            description="Two car collision",
        )
        assert report.hazard_type == HazardType.ACCIDENT
        assert report.severity == HazardSeverity.CRITICAL
        assert report.edge_id == "edge-main-1"
        assert report.position is None

    def test_valid_hazard_with_position(self) -> None:
        report = HazardReport(
            report_id="haz-002",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh-5",
            hazard_type=HazardType.DEBRIS,
            severity=HazardSeverity.LOW,
            position=Position2D(x=105.5, y=210.25),
            timestamp_s=12.0,
        )
        assert report.position == Position2D(x=105.5, y=210.25)
        assert report.edge_id is None

    def test_missing_location_raises(self) -> None:
        with pytest.raises(InvalidReportError, match="specify at least edge_id or position"):
            HazardReport(
                report_id="haz-003",
                report_type=ReportType.HAZARD,
                reporting_vehicle_id="veh-5",
                hazard_type=HazardType.WEATHER,
                timestamp_s=1.0,
            )

    def test_serialization_round_trip(self) -> None:
        report = HazardReport(
            report_id="haz-004",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh-1",
            hazard_type=HazardType.ROADWORK,
            severity=HazardSeverity.HIGH,
            edge_id="edge-2",
            position=Position2D(x=50.0, y=75.0),
            timestamp_s=3.0,
            description="Lane blocked",
        )
        d = report.to_dict()
        reconstructed = traffic_report_from_dict(d)
        assert isinstance(reconstructed, HazardReport)
        assert reconstructed.hazard_type == HazardType.ROADWORK
        assert reconstructed.severity == HazardSeverity.HIGH
        assert reconstructed.position == Position2D(x=50.0, y=75.0)


class TestBeliefRecord:
    """Tests for BeliefRecord model."""

    def test_belief_record_lifecycle(self) -> None:
        belief = BeliefRecord(
            belief_id="congestion:edge-1",
            belief_type=ReportType.CONGESTION,
            target_id="edge-1",
            status=BeliefStatus.ACTIVE,
            confidence=0.8,
            last_evidence_timestamp_s=10.0,
            expiry_timestamp_s=40.0,
            evidence_report_ids=("cong-1", "cong-2"),
            evidence_sources=("veh-1", "veh-2"),
            attributes={"congestion_level": "high"},
        )
        assert belief.belief_id == "congestion:edge-1"
        assert not belief.is_expired(39.9)
        assert belief.is_expired(40.0)

        d = belief.to_dict()
        reconstructed = BeliefRecord.from_dict(d)
        assert reconstructed.belief_id == belief.belief_id
        assert reconstructed.confidence == 0.8
        assert reconstructed.evidence_sources == ("veh-1", "veh-2")
        assert reconstructed.attributes["congestion_level"] == "high"


class TestCoordinationConfigAndMetrics:
    """Tests for CoordinationConfig validation and CoordinationMetrics."""

    def test_default_config(self) -> None:
        cfg = CoordinationConfig()
        assert cfg.enabled is True
        assert cfg.default_report_ttl_s == 30.0
        assert cfg.max_forwarding_hops == 3
        assert cfg.max_cache_size == 1000
        assert cfg.fusion_policy == FusionPolicy.LATEST_EVIDENCE
        assert cfg.trust_threshold == 0.0

        d = cfg.to_dict()
        reconstructed = CoordinationConfig.from_dict(d)
        assert reconstructed.enabled == cfg.enabled
        assert reconstructed.default_report_ttl_s == cfg.default_report_ttl_s
        assert reconstructed.max_forwarding_hops == cfg.max_forwarding_hops

    def test_invalid_config_raises(self) -> None:
        with pytest.raises(CoordinationValidationError, match="default_report_ttl_s"):
            CoordinationConfig(default_report_ttl_s=-5.0)

        with pytest.raises(CoordinationValidationError, match="max_forwarding_hops"):
            CoordinationConfig(max_forwarding_hops=-1)

        with pytest.raises(CoordinationValidationError, match="max_cache_size"):
            CoordinationConfig(max_cache_size=0)

        with pytest.raises(CoordinationValidationError, match="trust_threshold"):
            CoordinationConfig(trust_threshold=1.5)

    def test_metrics_lifecycle(self) -> None:
        metrics = CoordinationMetrics()
        metrics.reports_created += 2
        metrics.reports_received += 5
        metrics.reports_accepted += 4
        metrics.reports_forwarded += 3
        metrics.conflicts_detected += 1

        copy_m = metrics.copy()
        assert copy_m.reports_created == 2
        assert copy_m.reports_forwarded == 3

        metrics.reset()
        assert metrics.reports_created == 0
        assert metrics.reports_received == 0
        # Copy should remain unchanged
        assert copy_m.reports_created == 2


class TestCoordinationExceptions:
    """Tests for Phase 13 explicit coordination exception types."""

    def test_all_exception_types_and_context(self) -> None:
        from apps.core.coordination.exceptions import (
            ConflictingReportError,
            CoordinationError,
            CoordinationStateError,
            CoordinationValidationError,
            DuplicateReportError,
            ExpiredReportError,
            ForwardingLimitExceededError,
            InvalidReportError,
            InvalidRoadEdgeError,
            UnknownSourceVehicleError,
        )

        e_base = CoordinationError("base error", extra="info")
        assert str(e_base) == "base error"
        assert e_base.context["extra"] == "info"

        e_val = CoordinationValidationError("val error", field="test_field")
        assert e_val.field == "test_field"

        e_rep = InvalidReportError("bad report", field="report_id")
        assert e_rep.field == "report_id"

        e_veh = UnknownSourceVehicleError("veh_unknown")
        assert e_veh.vehicle_id == "veh_unknown"
        assert "veh_unknown" in str(e_veh)

        e_edge = InvalidRoadEdgeError("edge_99")
        assert e_edge.edge_id == "edge_99"
        assert e_edge.field == "edge_id"

        e_exp = ExpiredReportError(report_id="rep_1", expiry_timestamp_s=10.0, current_time_s=15.0)
        assert e_exp.report_id == "rep_1"
        assert e_exp.expiry_timestamp_s == 10.0
        assert e_exp.current_time_s == 15.0

        e_dup = DuplicateReportError("rep_dup")
        assert e_dup.report_id == "rep_dup"

        e_conf = ConflictingReportError("unresolvable conflict")
        assert "conflict" in str(e_conf)

        e_fwd = ForwardingLimitExceededError("rep_fwd", current_hops=4, max_hops=3)
        assert e_fwd.report_id == "rep_fwd"
        assert e_fwd.current_hops == 4
        assert e_fwd.max_hops == 3

        e_state = CoordinationStateError("rollback failed")
        assert "rollback failed" in str(e_state)
