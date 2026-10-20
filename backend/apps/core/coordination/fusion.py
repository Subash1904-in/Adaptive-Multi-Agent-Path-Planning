"""Deterministic information fusion, conflict resolution, and belief-state derivation."""

from typing import Any, Optional

from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    CongestionReport,
    CoordinationConfig,
    HazardReport,
    ReportType,
    RoadClosureReport,
    TrafficReport,
)


def derive_belief_id(report: TrafficReport) -> str:
    """Generate a deterministic, canonical belief identifier for a traffic report."""
    if report.report_type == ReportType.CONGESTION:
        assert isinstance(report, CongestionReport)
        return f"congestion:{report.edge_id}"
    elif report.report_type == ReportType.ROAD_CLOSURE:
        assert isinstance(report, RoadClosureReport)
        return f"closure:{report.edge_id}"
    elif report.report_type == ReportType.HAZARD:
        assert isinstance(report, HazardReport)
        loc_key = (
            report.edge_id
            if report.edge_id
            else f"{round(report.position.x, 2)}_{round(report.position.y, 2)}"
        )
        return f"hazard:{report.hazard_type.value}:{loc_key}"
    else:
        return f"generic:{report.report_type.value}:{report.report_id}"


def derive_target_id(report: TrafficReport) -> str:
    """Extract target entity identifier (road edge or coordinate key) from a report."""
    if isinstance(report, (CongestionReport, RoadClosureReport)):
        return report.edge_id
    elif isinstance(report, HazardReport):
        if report.edge_id:
            return report.edge_id
        assert report.position is not None
        return f"{round(report.position.x, 4)},{round(report.position.y, 4)}"
    return report.report_id


class InformationFusion:
    """Pure-logic helper providing deterministic report merging and conflict resolution."""

    @staticmethod
    def fuse_single_report(
        existing_belief: Optional[BeliefRecord],
        new_report: TrafficReport,
        current_time_s: float,
        config: CoordinationConfig,
    ) -> tuple[BeliefRecord, bool, bool]:
        """Incorporate a new traffic report into an existing belief.

        Args:
            existing_belief: Current belief for the report's target, or None if first report.
            new_report: Validated traffic report to fuse.
            current_time_s: Current authoritative simulation time.
            config: Coordination configuration specifying policies and thresholds.

        Returns:
            Tuple of (updated_belief, is_new_belief, conflict_detected).
        """
        belief_id = derive_belief_id(new_report)
        target_id = derive_target_id(new_report)

        # 1. New belief creation
        if existing_belief is None:
            attributes = InformationFusion._extract_attributes(new_report)
            belief = BeliefRecord(
                belief_id=belief_id,
                belief_type=new_report.report_type,
                target_id=target_id,
                status=BeliefStatus.ACTIVE,
                confidence=new_report.confidence,
                last_evidence_timestamp_s=new_report.timestamp_s,
                expiry_timestamp_s=new_report.expiry_timestamp_s,
                evidence_report_ids=(new_report.report_id,),
                evidence_sources=(new_report.reporting_vehicle_id,),
                attributes=attributes,
                dispute_reason=None,
            )
            return belief, True, False

        # 2. Duplicate report prevention: same report ID cannot inflate confidence or alter attrs
        if new_report.report_id in existing_belief.evidence_report_ids:
            return existing_belief, False, False

        # 3. Check timestamp precedence and conflict
        conflict_detected = False
        disputed = False
        dispute_reason: Optional[str] = existing_belief.dispute_reason

        # Combine distinct sources
        existing_sources = set(existing_belief.evidence_sources)
        is_independent_source = new_report.reporting_vehicle_id not in existing_sources
        updated_sources = tuple(sorted(existing_sources | {new_report.reporting_vehicle_id}))
        updated_report_ids = tuple(
            sorted(set(existing_belief.evidence_report_ids) | {new_report.report_id})
        )

        time_diff = new_report.timestamp_s - existing_belief.last_evidence_timestamp_s

        # Evaluate conflict between reports
        has_semantic_conflict = InformationFusion._check_semantic_conflict(
            existing_belief, new_report
        )
        if has_semantic_conflict:
            conflict_detected = True

        # Precedence evaluation
        if time_diff > 1e-9:
            # Newer evidence supersedes older evidence
            chosen_attributes = InformationFusion._extract_attributes(new_report)
            chosen_timestamp = new_report.timestamp_s
            chosen_expiry = new_report.expiry_timestamp_s
            base_confidence = new_report.confidence
            status = BeliefStatus.ACTIVE
            dispute_reason = None
        elif time_diff < -1e-9:
            # Older evidence: preserve existing belief state, but register evidence if compatible
            chosen_attributes = dict(existing_belief.attributes)
            chosen_timestamp = existing_belief.last_evidence_timestamp_s
            chosen_expiry = existing_belief.expiry_timestamp_s
            base_confidence = existing_belief.confidence
            status = existing_belief.status
        else:
            # Same simulation timestamp (within 1e-9)
            if has_semantic_conflict:
                # Concurrent conflicting evidence
                if abs(new_report.confidence - existing_belief.confidence) > 1e-6:
                    # Higher confidence breaks tie
                    if new_report.confidence > existing_belief.confidence:
                        chosen_attributes = InformationFusion._extract_attributes(new_report)
                        base_confidence = new_report.confidence
                        chosen_expiry = new_report.expiry_timestamp_s
                    else:
                        chosen_attributes = dict(existing_belief.attributes)
                        base_confidence = existing_belief.confidence
                        chosen_expiry = existing_belief.expiry_timestamp_s
                    status = BeliefStatus.ACTIVE
                    dispute_reason = None
                else:
                    # Equal confidence concurrent conflict -> flag DISPUTED
                    chosen_attributes = InformationFusion._merge_disputed_attributes(
                        existing_belief, new_report
                    )
                    base_confidence = min(new_report.confidence, existing_belief.confidence) * 0.8
                    chosen_expiry = min(
                        filter(
                            None,
                            [existing_belief.expiry_timestamp_s, new_report.expiry_timestamp_s],
                        ),
                        default=None,
                    )
                    status = BeliefStatus.DISPUTED
                    disputed = True
                    dispute_reason = (
                        f"Concurrent conflicting evidence at t={new_report.timestamp_s:.2f}s "
                        f"from sources {updated_sources}."
                    )
                chosen_timestamp = new_report.timestamp_s
            else:
                # Compatible evidence at same timestamp
                chosen_attributes = InformationFusion._extract_attributes(new_report)
                base_confidence = max(existing_belief.confidence, new_report.confidence)
                chosen_timestamp = new_report.timestamp_s
                chosen_expiry = max(
                    filter(
                        None, [existing_belief.expiry_timestamp_s, new_report.expiry_timestamp_s]
                    ),
                    default=None,
                )
                status = existing_belief.status

        # Multi-source corroboration boost: bounded boost for independent confirming sources
        final_confidence = base_confidence
        if is_independent_source and not disputed and not has_semantic_conflict:
            # Corroboration: increases confidence toward 1.0 by 5% of remaining headroom per source
            boost = (1.0 - base_confidence) * 0.05
            final_confidence = min(1.0, round(base_confidence + boost, 4))

        updated_belief = BeliefRecord(
            belief_id=belief_id,
            belief_type=new_report.report_type,
            target_id=target_id,
            status=status,
            confidence=final_confidence,
            last_evidence_timestamp_s=chosen_timestamp,
            expiry_timestamp_s=chosen_expiry,
            evidence_report_ids=updated_report_ids,
            evidence_sources=updated_sources,
            attributes=chosen_attributes,
            dispute_reason=dispute_reason,
        )
        return updated_belief, False, conflict_detected

    @staticmethod
    def fuse_report_history(
        reports: list[TrafficReport],
        current_time_s: float,
        config: CoordinationConfig,
    ) -> dict[str, BeliefRecord]:
        """Deterministically fuse reports into beliefs with complete order-invariance.

        Sorts reports canonically before incremental fusion, ensuring identical results
        regardless of input report order.
        """
        # Canonical sort key:
        # (timestamp asc, sequence_number asc, confidence asc, vehicle_id asc, report_id asc)
        sorted_reports = sorted(
            reports,
            key=lambda r: (
                r.timestamp_s,
                r.sequence_number,
                r.confidence,
                r.reporting_vehicle_id,
                r.report_id,
            ),
        )

        beliefs: dict[str, BeliefRecord] = {}
        for r in sorted_reports:
            bid = derive_belief_id(r)
            existing = beliefs.get(bid)
            updated, _, _ = InformationFusion.fuse_single_report(
                existing_belief=existing,
                new_report=r,
                current_time_s=current_time_s,
                config=config,
            )
            beliefs[bid] = updated

        return beliefs

    @staticmethod
    def _extract_attributes(report: TrafficReport) -> dict[str, Any]:
        """Extract typed domain attributes from a report."""
        if isinstance(report, CongestionReport):
            return {
                "congestion_level": report.congestion_level.value,
                "estimated_speed_mps": report.estimated_speed_mps,
                "travel_time_factor": report.travel_time_factor,
            }
        elif isinstance(report, RoadClosureReport):
            return {
                "closure_status": report.closure_status.value,
                "reason": report.reason,
            }
        elif isinstance(report, HazardReport):
            return {
                "hazard_type": report.hazard_type.value,
                "severity": report.severity.value,
                "description": report.description,
            }
        return {}

    @staticmethod
    def _check_semantic_conflict(existing: BeliefRecord, new_report: TrafficReport) -> bool:
        """Determine if a new report directly contradicts the current belief."""
        if existing.belief_type != new_report.report_type:
            return False

        if isinstance(new_report, RoadClosureReport):
            existing_status = existing.attributes.get("closure_status")
            if existing_status and existing_status != new_report.closure_status.value:
                # Contradiction: e.g. CLOSED vs REOPENED
                return True
        elif isinstance(new_report, CongestionReport):
            existing_level = existing.attributes.get("congestion_level")
            if existing_level and existing_level != new_report.congestion_level.value:
                return True
        elif isinstance(new_report, HazardReport):
            existing_sev = existing.attributes.get("severity")
            if existing_sev and existing_sev != new_report.severity.value:
                return True

        return False

    @staticmethod
    def _merge_disputed_attributes(
        existing: BeliefRecord, new_report: TrafficReport
    ) -> dict[str, Any]:
        """Produce merged diagnostic attributes when reports are in disputed conflict."""
        attrs = dict(existing.attributes)
        new_attrs = InformationFusion._extract_attributes(new_report)
        attrs["disputed_with"] = new_attrs
        return attrs
