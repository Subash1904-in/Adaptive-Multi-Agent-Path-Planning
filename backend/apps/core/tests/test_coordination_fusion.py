"""Unit tests for Phase 13 information fusion, conflict resolution, and belief-state derivation."""

import itertools

from apps.core.coordination.fusion import InformationFusion
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


class TestInformationFusion:
    """Tests for InformationFusion deterministic logic and conflict handling."""

    def test_single_report_creates_belief(self) -> None:
        report = CongestionReport(
            report_id="r1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=10.0,
            confidence=0.8,
            congestion_level=CongestionLevel.HIGH,
        )
        cfg = CoordinationConfig()
        belief, is_new, conflict = InformationFusion.fuse_single_report(
            existing_belief=None,
            new_report=report,
            current_time_s=10.0,
            config=cfg,
        )

        assert is_new is True
        assert conflict is False
        assert belief.belief_id == "congestion:e1"
        assert belief.confidence == 0.8
        assert belief.status == BeliefStatus.ACTIVE
        assert belief.evidence_report_ids == ("r1",)
        assert belief.evidence_sources == ("v1",)
        assert belief.attributes["congestion_level"] == "high"

    def test_newer_evidence_supersedes_older(self) -> None:
        cfg = CoordinationConfig()
        r1 = RoadClosureReport(
            report_id="c1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=10.0,
            closure_status=RoadClosureStatus.CLOSED,
        )
        belief_1, _, _ = InformationFusion.fuse_single_report(None, r1, 10.0, cfg)
        assert belief_1.attributes["closure_status"] == RoadClosureStatus.CLOSED.value

        # Newer report reopening the road
        r2 = RoadClosureReport(
            report_id="c2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v2",
            edge_id="e1",
            timestamp_s=25.0,
            closure_status=RoadClosureStatus.REOPENED,
        )
        belief_2, is_new, conflict = InformationFusion.fuse_single_report(belief_1, r2, 25.0, cfg)
        assert is_new is False
        assert conflict is True
        assert belief_2.attributes["closure_status"] == RoadClosureStatus.REOPENED.value
        assert belief_2.last_evidence_timestamp_s == 25.0
        assert belief_2.status == BeliefStatus.ACTIVE
        assert "c2" in belief_2.evidence_report_ids

    def test_stale_evidence_does_not_overwrite_newer(self) -> None:
        cfg = CoordinationConfig()
        # Newer report is already fused
        r_new = CongestionReport(
            report_id="r_new",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=30.0,
            congestion_level=CongestionLevel.LOW,
        )
        belief, _, _ = InformationFusion.fuse_single_report(None, r_new, 30.0, cfg)

        # Stale report arriving out-of-order
        r_old = CongestionReport(
            report_id="r_old",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v2",
            edge_id="e1",
            timestamp_s=10.0,
            congestion_level=CongestionLevel.SEVERE,
        )
        updated_belief, _, _ = InformationFusion.fuse_single_report(belief, r_old, 30.0, cfg)

        # Belief maintains newer status
        assert updated_belief.attributes["congestion_level"] == CongestionLevel.LOW.value
        assert updated_belief.last_evidence_timestamp_s == 30.0

    def test_same_timestamp_higher_confidence_wins(self) -> None:
        cfg = CoordinationConfig()
        r1 = RoadClosureReport(
            report_id="r1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=15.0,
            confidence=0.6,
            closure_status=RoadClosureStatus.CLOSED,
        )
        belief, _, _ = InformationFusion.fuse_single_report(None, r1, 15.0, cfg)

        # Same timestamp, but higher confidence says REOPENED
        r2 = RoadClosureReport(
            report_id="r2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v2",
            edge_id="e1",
            timestamp_s=15.0,
            confidence=0.9,
            closure_status=RoadClosureStatus.REOPENED,
        )
        updated_belief, _, conflict = InformationFusion.fuse_single_report(belief, r2, 15.0, cfg)

        assert conflict is True
        assert updated_belief.attributes["closure_status"] == RoadClosureStatus.REOPENED.value
        assert updated_belief.status == BeliefStatus.ACTIVE

    def test_same_timestamp_equal_confidence_conflict_flags_disputed(self) -> None:
        cfg = CoordinationConfig()
        r1 = RoadClosureReport(
            report_id="r1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=15.0,
            confidence=0.8,
            closure_status=RoadClosureStatus.CLOSED,
        )
        belief, _, _ = InformationFusion.fuse_single_report(None, r1, 15.0, cfg)

        # Same timestamp, equal confidence conflicting report
        r2 = RoadClosureReport(
            report_id="r2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v2",
            edge_id="e1",
            timestamp_s=15.0,
            confidence=0.8,
            closure_status=RoadClosureStatus.REOPENED,
        )
        updated_belief, _, conflict = InformationFusion.fuse_single_report(belief, r2, 15.0, cfg)

        assert conflict is True
        assert updated_belief.status == BeliefStatus.DISPUTED
        assert updated_belief.dispute_reason is not None
        assert "Concurrent conflicting evidence" in updated_belief.dispute_reason

    def test_duplicate_forwarding_does_not_inflate_confidence(self) -> None:
        cfg = CoordinationConfig()
        r1 = CongestionReport(
            report_id="r_exact",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=10.0,
            confidence=0.75,
            congestion_level=CongestionLevel.HIGH,
        )
        belief_1, _, _ = InformationFusion.fuse_single_report(None, r1, 10.0, cfg)
        assert belief_1.confidence == 0.75

        # Relayed copy with identical report_id arriving via different hops
        belief_2, is_new, conflict = InformationFusion.fuse_single_report(belief_1, r1, 10.0, cfg)
        assert is_new is False
        assert conflict is False
        assert belief_2.confidence == 0.75
        assert len(belief_2.evidence_report_ids) == 1

    def test_multi_source_independent_corroboration_boosts_confidence(self) -> None:
        cfg = CoordinationConfig()
        r1 = HazardReport(
            report_id="h1",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="v1",
            edge_id="e1",
            timestamp_s=10.0,
            confidence=0.8,
            hazard_type=HazardType.ACCIDENT,
            severity=HazardSeverity.HIGH,
        )
        belief_1, _, _ = InformationFusion.fuse_single_report(None, r1, 10.0, cfg)
        assert belief_1.confidence == 0.8

        # Independent report from vehicle v2 confirming the same hazard at t=10.0
        r2 = HazardReport(
            report_id="h2",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="v2",
            edge_id="e1",
            timestamp_s=10.0,
            confidence=0.8,
            hazard_type=HazardType.ACCIDENT,
            severity=HazardSeverity.HIGH,
        )
        belief_2, _, _ = InformationFusion.fuse_single_report(belief_1, r2, 10.0, cfg)
        # Corroboration boost applied: 0.8 + (1.0 - 0.8)*0.05 = 0.81
        assert belief_2.confidence == 0.81
        assert belief_2.evidence_sources == ("v1", "v2")

    def test_permutation_invariance_order_independence(self) -> None:
        """Verify that fusing an evidence set produces bit-identical beliefs regardless of order."""
        cfg = CoordinationConfig()

        reports = [
            CongestionReport(
                report_id="r1",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="v1",
                edge_id="e1",
                timestamp_s=5.0,
                confidence=0.7,
            ),
            CongestionReport(
                report_id="r2",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="v2",
                edge_id="e1",
                timestamp_s=12.0,
                confidence=0.85,
                congestion_level=CongestionLevel.HIGH,
            ),
            CongestionReport(
                report_id="r3",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="v3",
                edge_id="e1",
                timestamp_s=18.0,
                confidence=0.9,
                congestion_level=CongestionLevel.SEVERE,
            ),
        ]

        # Canonical baseline fusion
        canonical_beliefs = InformationFusion.fuse_report_history(
            reports, current_time_s=20.0, config=cfg
        )
        canonical_target = canonical_beliefs["congestion:e1"]

        # Test all permutations of report ingestion order
        for perm in itertools.permutations(reports):
            perm_beliefs = InformationFusion.fuse_report_history(
                list(perm), current_time_s=20.0, config=cfg
            )
            perm_target = perm_beliefs["congestion:e1"]

            assert perm_target.belief_id == canonical_target.belief_id
            assert perm_target.confidence == canonical_target.confidence
            assert (
                perm_target.last_evidence_timestamp_s == canonical_target.last_evidence_timestamp_s
            )
            assert perm_target.attributes == canonical_target.attributes
            assert perm_target.evidence_report_ids == canonical_target.evidence_report_ids
            assert perm_target.evidence_sources == canonical_target.evidence_sources
