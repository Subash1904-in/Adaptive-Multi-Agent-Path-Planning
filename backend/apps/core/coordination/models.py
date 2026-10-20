"""Data models, report contracts, and configuration for decentralized V2V coordination."""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from apps.core.coordination.exceptions import (
    CoordinationValidationError,
    InvalidReportError,
)
from apps.core.domain.values import Position2D


class ReportType(str, Enum):
    """Semantic category of shared decentralized traffic report."""

    CONGESTION = "congestion"
    ROAD_CLOSURE = "road_closure"
    HAZARD = "hazard"


class CongestionLevel(str, Enum):
    """Discrete bounded classification of traffic congestion level."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


class RoadClosureStatus(str, Enum):
    """Status classification of a road closure or reopening report."""

    CLOSED = "closed"
    REOPENED = "reopened"
    WITHDRAWN = "withdrawn"


class HazardType(str, Enum):
    """Specific category of roadway physical hazard or disruption."""

    ACCIDENT = "accident"
    DEBRIS = "debris"
    WEATHER = "weather"
    ROADWORK = "roadwork"
    ANIMAL = "animal"
    OBSTACLE = "obstacle"


class HazardSeverity(str, Enum):
    """Impact severity level of a roadway hazard."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BeliefStatus(str, Enum):
    """Operational validity status of a vehicle's local belief."""

    ACTIVE = "active"
    EXPIRED = "expired"
    DISPUTED = "disputed"


class FusionPolicy(str, Enum):
    """Information fusion strategy for merging and resolving conflicting reports."""

    LATEST_EVIDENCE = "latest_evidence"
    HIGHEST_CONFIDENCE = "highest_confidence"
    WEIGHTED_AVERAGE = "weighted_average"


def _validate_finite_float(val: Any, name: str, min_val: Optional[float] = None) -> float:
    """Validate that val is a real finite float."""
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise CoordinationValidationError(f"{name} must be a real number, got {val!r}.", field=name)
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        raise CoordinationValidationError(f"{name} must be finite, got {f}.", field=name)
    if min_val is not None and f < min_val:
        raise CoordinationValidationError(f"{name} must be >= {min_val}, got {f}.", field=name)
    return f


@dataclass(frozen=True)
class BaseTrafficReport:
    """Immutable base class for all typed traffic reports shared via V2V.

    Attributes:
        report_id: Unique identifier for this report.
        report_type: Category of traffic information (CONGESTION, ROAD_CLOSURE, HAZARD).
        reporting_vehicle_id: Vehicle identifier that originated the report.
        timestamp_s: Simulation timestamp in seconds when the observation was recorded.
        expiry_timestamp_s: Optional simulation timestamp when the report expires.
        confidence: Normalized confidence value in [0.0, 1.0].
        provenance: Sequence of vehicle identifiers in the relay path.
        sequence_number: Monotonically increasing sequence number per reporting vehicle.
        schema_version: Schema contract version string.
        metadata: Arbitrary additional structured diagnostic data.
    """

    report_id: str
    report_type: ReportType
    reporting_vehicle_id: str
    timestamp_s: float
    expiry_timestamp_s: Optional[float] = None
    confidence: float = 1.0
    provenance: tuple[str, ...] = field(default_factory=tuple)
    sequence_number: int = 0
    schema_version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise InvalidReportError("report_id must be a non-empty string.", field="report_id")
        if not isinstance(self.reporting_vehicle_id, str) or not self.reporting_vehicle_id.strip():
            raise InvalidReportError(
                "reporting_vehicle_id must be a non-empty string.",
                field="reporting_vehicle_id",
            )
        if not isinstance(self.report_type, ReportType):
            try:
                object.__setattr__(self, "report_type", ReportType(self.report_type))
            except ValueError as exc:
                raise InvalidReportError(
                    f"Invalid report_type '{self.report_type}'.",
                    field="report_type",
                ) from exc

        t_val = _validate_finite_float(self.timestamp_s, "timestamp_s", min_val=0.0)
        object.__setattr__(self, "timestamp_s", t_val)

        if self.expiry_timestamp_s is not None:
            exp_val = _validate_finite_float(self.expiry_timestamp_s, "expiry_timestamp_s")
            if exp_val <= t_val:
                raise InvalidReportError(
                    f"expiry_timestamp_s ({exp_val}) must be greater than timestamp_s ({t_val}).",
                    field="expiry_timestamp_s",
                )
            object.__setattr__(self, "expiry_timestamp_s", exp_val)

        conf_val = _validate_finite_float(self.confidence, "confidence", min_val=0.0)
        if conf_val > 1.0:
            raise InvalidReportError(
                f"confidence must be in [0.0, 1.0], got {conf_val}.", field="confidence"
            )
        object.__setattr__(self, "confidence", conf_val)

        if (
            not isinstance(self.sequence_number, int)
            or isinstance(self.sequence_number, bool)
            or self.sequence_number < 0
        ):
            raise InvalidReportError(
                f"sequence_number must be a non-negative integer, got {self.sequence_number!r}.",
                field="sequence_number",
            )

        if not isinstance(self.provenance, tuple):
            if isinstance(self.provenance, list):
                object.__setattr__(self, "provenance", tuple(self.provenance))
            else:
                raise InvalidReportError(
                    "provenance must be a sequence of strings.", field="provenance"
                )

        for p in self.provenance:
            if not isinstance(p, str) or not p.strip():
                raise InvalidReportError(
                    "Provenance elements must be non-empty strings.", field="provenance"
                )

    def is_expired(self, current_time_s: float) -> bool:
        """Evaluate if this report is expired relative to authoritative simulation time."""
        if self.expiry_timestamp_s is None:
            return False
        return (current_time_s - self.expiry_timestamp_s) >= -1e-9

    def to_dict(self) -> dict[str, Any]:
        """Convert report to a JSON-compatible dictionary."""
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "reporting_vehicle_id": self.reporting_vehicle_id,
            "timestamp_s": round(self.timestamp_s, 6),
            "expiry_timestamp_s": (
                round(self.expiry_timestamp_s, 6) if self.expiry_timestamp_s is not None else None
            ),
            "confidence": round(self.confidence, 4),
            "provenance": list(self.provenance),
            "sequence_number": self.sequence_number,
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        """Serialize report to a deterministic JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(frozen=True)
class CongestionReport(BaseTrafficReport):
    """Typed report describing observed roadway edge congestion.

    Attributes:
        edge_id: Road network edge identifier experiencing congestion.
        congestion_level: Qualitative classification (LOW, MODERATE, HIGH, SEVERE).
        estimated_speed_mps: Optional estimated traversal speed in m/s (>= 0.0).
        travel_time_factor: Optional relative delay factor (> 0.0, e.g. 1.5 = 50% slower).
    """

    edge_id: str = ""
    congestion_level: CongestionLevel = CongestionLevel.MODERATE
    estimated_speed_mps: Optional[float] = None
    travel_time_factor: Optional[float] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.edge_id, str) or not self.edge_id.strip():
            raise InvalidReportError("edge_id must be a non-empty string.", field="edge_id")

        if not isinstance(self.congestion_level, CongestionLevel):
            try:
                object.__setattr__(self, "congestion_level", CongestionLevel(self.congestion_level))
            except ValueError as exc:
                raise InvalidReportError(
                    f"Invalid congestion_level '{self.congestion_level}'.",
                    field="congestion_level",
                ) from exc

        if self.estimated_speed_mps is not None:
            s_val = _validate_finite_float(
                self.estimated_speed_mps, "estimated_speed_mps", min_val=0.0
            )
            object.__setattr__(self, "estimated_speed_mps", s_val)

        if self.travel_time_factor is not None:
            f_val = _validate_finite_float(
                self.travel_time_factor, "travel_time_factor", min_val=0.001
            )
            object.__setattr__(self, "travel_time_factor", f_val)

    def to_dict(self) -> dict[str, Any]:
        """Convert congestion report to a JSON-compatible dictionary."""
        d = super().to_dict()
        d.update(
            {
                "edge_id": self.edge_id,
                "congestion_level": self.congestion_level.value,
                "estimated_speed_mps": (
                    round(self.estimated_speed_mps, 4)
                    if self.estimated_speed_mps is not None
                    else None
                ),
                "travel_time_factor": (
                    round(self.travel_time_factor, 4)
                    if self.travel_time_factor is not None
                    else None
                ),
            }
        )
        return d


@dataclass(frozen=True)
class RoadClosureReport(BaseTrafficReport):
    """Typed report describing road closure or reopening status for an edge.

    Attributes:
        edge_id: Road network edge identifier.
        closure_status: Operational state (CLOSED, REOPENED, WITHDRAWN).
        reason: Optional human-readable or coded reason for closure/reopening.
    """

    edge_id: str = ""
    closure_status: RoadClosureStatus = RoadClosureStatus.CLOSED
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.edge_id, str) or not self.edge_id.strip():
            raise InvalidReportError("edge_id must be a non-empty string.", field="edge_id")

        if not isinstance(self.closure_status, RoadClosureStatus):
            try:
                object.__setattr__(self, "closure_status", RoadClosureStatus(self.closure_status))
            except ValueError as exc:
                raise InvalidReportError(
                    f"Invalid closure_status '{self.closure_status}'.",
                    field="closure_status",
                ) from exc

    def to_dict(self) -> dict[str, Any]:
        """Convert road closure report to a JSON-compatible dictionary."""
        d = super().to_dict()
        d.update(
            {
                "edge_id": self.edge_id,
                "closure_status": self.closure_status.value,
                "reason": self.reason,
            }
        )
        return d


@dataclass(frozen=True)
class HazardReport(BaseTrafficReport):
    """Typed report describing a localized roadway hazard.

    Attributes:
        hazard_type: Classification of hazard (ACCIDENT, DEBRIS, WEATHER, etc.).
        severity: Impact severity (LOW, MEDIUM, HIGH, CRITICAL).
        edge_id: Optional edge identifier where hazard is located.
        position: Optional spatial coordinate of the hazard.
        description: Optional textual description.
    """

    hazard_type: HazardType = HazardType.ACCIDENT
    severity: HazardSeverity = HazardSeverity.MEDIUM
    edge_id: Optional[str] = None
    position: Optional[Position2D] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.hazard_type, HazardType):
            try:
                object.__setattr__(self, "hazard_type", HazardType(self.hazard_type))
            except ValueError as exc:
                raise InvalidReportError(
                    f"Invalid hazard_type '{self.hazard_type}'.",
                    field="hazard_type",
                ) from exc

        if not isinstance(self.severity, HazardSeverity):
            try:
                object.__setattr__(self, "severity", HazardSeverity(self.severity))
            except ValueError as exc:
                raise InvalidReportError(
                    f"Invalid severity '{self.severity}'.",
                    field="severity",
                ) from exc

        if self.edge_id is None and self.position is None:
            raise InvalidReportError(
                "HazardReport must specify at least edge_id or position.",
                field="location",
            )

        if self.edge_id is not None and (
            not isinstance(self.edge_id, str) or not self.edge_id.strip()
        ):
            raise InvalidReportError(
                "edge_id must be a non-empty string when provided.", field="edge_id"
            )

        if self.position is not None and not isinstance(self.position, Position2D):
            raise InvalidReportError(
                "position must be an instance of Position2D.", field="position"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert hazard report to a JSON-compatible dictionary."""
        d = super().to_dict()
        d.update(
            {
                "hazard_type": self.hazard_type.value,
                "severity": self.severity.value,
                "edge_id": self.edge_id,
                "position": (
                    {"x": round(self.position.x, 4), "y": round(self.position.y, 4)}
                    if self.position is not None
                    else None
                ),
                "description": self.description,
            }
        )
        return d


TrafficReport = Union[CongestionReport, RoadClosureReport, HazardReport]


def traffic_report_from_dict(data: dict[str, Any]) -> TrafficReport:
    """Construct a typed TrafficReport subclass from a dictionary representation."""
    if not isinstance(data, dict):
        raise InvalidReportError("Report data must be a dictionary.", field="data")

    raw_type = data.get("report_type")
    if not raw_type:
        raise InvalidReportError(
            "Missing required 'report_type' in report data.", field="report_type"
        )

    try:
        rtype = ReportType(raw_type)
    except ValueError as exc:
        raise InvalidReportError(
            f"Unsupported report_type '{raw_type}'.", field="report_type"
        ) from exc

    common_kwargs = {
        "report_id": data.get("report_id", ""),
        "report_type": rtype,
        "reporting_vehicle_id": data.get("reporting_vehicle_id", ""),
        "timestamp_s": data.get("timestamp_s", 0.0),
        "expiry_timestamp_s": data.get("expiry_timestamp_s"),
        "confidence": data.get("confidence", 1.0),
        "provenance": tuple(data.get("provenance", ())),
        "sequence_number": data.get("sequence_number", 0),
        "schema_version": data.get("schema_version", "1.0.0"),
        "metadata": dict(data.get("metadata", {})),
    }

    if rtype == ReportType.CONGESTION:
        return CongestionReport(
            **common_kwargs,
            edge_id=data.get("edge_id", ""),
            congestion_level=CongestionLevel(
                data.get("congestion_level", CongestionLevel.MODERATE.value)
            ),
            estimated_speed_mps=data.get("estimated_speed_mps"),
            travel_time_factor=data.get("travel_time_factor"),
        )
    elif rtype == ReportType.ROAD_CLOSURE:
        return RoadClosureReport(
            **common_kwargs,
            edge_id=data.get("edge_id", ""),
            closure_status=RoadClosureStatus(
                data.get("closure_status", RoadClosureStatus.CLOSED.value)
            ),
            reason=data.get("reason"),
        )
    elif rtype == ReportType.HAZARD:
        pos_data = data.get("position")
        pos = (
            Position2D(x=float(pos_data["x"]), y=float(pos_data["y"]))
            if pos_data and isinstance(pos_data, dict) and "x" in pos_data and "y" in pos_data
            else None
        )
        return HazardReport(
            **common_kwargs,
            hazard_type=HazardType(data.get("hazard_type", HazardType.ACCIDENT.value)),
            severity=HazardSeverity(data.get("severity", HazardSeverity.MEDIUM.value)),
            edge_id=data.get("edge_id"),
            position=pos,
            description=data.get("description"),
        )
    else:
        raise InvalidReportError(f"Unhandled report type: {rtype}.", field="report_type")


@dataclass(frozen=True)
class BeliefRecord:
    """A vehicle's local interpretation and confidence in a traffic condition.

    Attributes:
        belief_id: Unique deterministic belief identifier (e.g. 'congestion:edge_1').
        belief_type: Category of information (CONGESTION, ROAD_CLOSURE, HAZARD).
        target_id: Identifier of target entity (edge ID or hazard key).
        status: Operational status (ACTIVE, EXPIRED, DISPUTED).
        confidence: Current fused confidence in [0.0, 1.0].
        last_evidence_timestamp_s: Simulation timestamp of most recent supporting evidence.
        expiry_timestamp_s: Optional expiry timestamp when belief becomes invalid.
        evidence_report_ids: Deterministic tuple of report IDs contributing to this belief.
        evidence_sources: Distinct vehicle IDs that provided evidence.
        attributes: Category-specific interpreted properties (e.g. congestion_level).
        dispute_reason: Diagnostic explanation if status is DISPUTED.
    """

    belief_id: str
    belief_type: ReportType
    target_id: str
    status: BeliefStatus = BeliefStatus.ACTIVE
    confidence: float = 1.0
    last_evidence_timestamp_s: float = 0.0
    expiry_timestamp_s: Optional[float] = None
    evidence_report_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_sources: tuple[str, ...] = field(default_factory=tuple)
    attributes: dict[str, Any] = field(default_factory=dict)
    dispute_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.belief_id, str) or not self.belief_id.strip():
            raise CoordinationValidationError(
                "belief_id must be a non-empty string.", field="belief_id"
            )
        if not isinstance(self.target_id, str) or not self.target_id.strip():
            raise CoordinationValidationError(
                "target_id must be a non-empty string.", field="target_id"
            )
        if not isinstance(self.belief_type, ReportType):
            object.__setattr__(self, "belief_type", ReportType(self.belief_type))
        if not isinstance(self.status, BeliefStatus):
            object.__setattr__(self, "status", BeliefStatus(self.status))

        conf = _validate_finite_float(self.confidence, "confidence", min_val=0.0)
        if conf > 1.0:
            raise CoordinationValidationError(
                "confidence must be in [0.0, 1.0].", field="confidence"
            )
        object.__setattr__(self, "confidence", conf)

        t_val = _validate_finite_float(
            self.last_evidence_timestamp_s, "last_evidence_timestamp_s", min_val=0.0
        )
        object.__setattr__(self, "last_evidence_timestamp_s", t_val)

        if self.expiry_timestamp_s is not None:
            exp_val = _validate_finite_float(self.expiry_timestamp_s, "expiry_timestamp_s")
            object.__setattr__(self, "expiry_timestamp_s", exp_val)

    def is_expired(self, current_time_s: float) -> bool:
        """Check if belief has expired relative to current simulation time."""
        if self.expiry_timestamp_s is None:
            return False
        return (current_time_s - self.expiry_timestamp_s) >= -1e-9

    def to_dict(self) -> dict[str, Any]:
        """Serialize belief record to a JSON-compatible dictionary."""
        return {
            "belief_id": self.belief_id,
            "belief_type": self.belief_type.value,
            "target_id": self.target_id,
            "status": self.status.value,
            "confidence": round(self.confidence, 4),
            "last_evidence_timestamp_s": round(self.last_evidence_timestamp_s, 6),
            "expiry_timestamp_s": (
                round(self.expiry_timestamp_s, 6) if self.expiry_timestamp_s is not None else None
            ),
            "evidence_report_ids": list(self.evidence_report_ids),
            "evidence_sources": list(self.evidence_sources),
            "attributes": dict(self.attributes),
            "dispute_reason": self.dispute_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BeliefRecord":
        """Reconstruct BeliefRecord from dictionary."""
        return cls(
            belief_id=data["belief_id"],
            belief_type=ReportType(data["belief_type"]),
            target_id=data["target_id"],
            status=BeliefStatus(data.get("status", BeliefStatus.ACTIVE.value)),
            confidence=float(data.get("confidence", 1.0)),
            last_evidence_timestamp_s=float(data.get("last_evidence_timestamp_s", 0.0)),
            expiry_timestamp_s=(
                float(data["expiry_timestamp_s"])
                if data.get("expiry_timestamp_s") is not None
                else None
            ),
            evidence_report_ids=tuple(data.get("evidence_report_ids", ())),
            evidence_sources=tuple(data.get("evidence_sources", ())),
            attributes=dict(data.get("attributes", {})),
            dispute_reason=data.get("dispute_reason"),
        )


@dataclass(frozen=True)
class CoordinationConfig:
    """Configuration governing decentralized V2V traffic knowledge dissemination.

    Attributes:
        enabled: Master toggle for decentralized coordination subsystem.
        default_report_ttl_s: Default validity duration for newly generated reports.
        max_forwarding_hops: Maximum permitted relay hops for multi-hop dissemination.
        max_cache_size: Maximum reports cached per vehicle for deduplication.
        enabled_categories: Allowed report types for transmission and ingestion.
        fusion_policy: Conflict resolution and merging policy.
        trust_threshold: Minimum confidence required for report acceptance.
        dispute_grace_window_s: Window in seconds for identifying conflicting concurrent reports.
    """

    enabled: bool = True
    default_report_ttl_s: float = 30.0
    max_forwarding_hops: int = 3
    max_cache_size: int = 1000
    enabled_categories: tuple[ReportType, ...] = (
        ReportType.CONGESTION,
        ReportType.ROAD_CLOSURE,
        ReportType.HAZARD,
    )
    fusion_policy: FusionPolicy = FusionPolicy.LATEST_EVIDENCE
    trust_threshold: float = 0.0
    dispute_grace_window_s: float = 1.0

    def __post_init__(self) -> None:
        ttl = _validate_finite_float(self.default_report_ttl_s, "default_report_ttl_s", min_val=0.1)
        object.__setattr__(self, "default_report_ttl_s", ttl)

        if (
            not isinstance(self.max_forwarding_hops, int)
            or isinstance(self.max_forwarding_hops, bool)
            or self.max_forwarding_hops < 0
        ):
            raise CoordinationValidationError(
                f"max_forwarding_hops must be a non-negative integer, "
                f"got {self.max_forwarding_hops!r}.",
                field="max_forwarding_hops",
            )

        if (
            not isinstance(self.max_cache_size, int)
            or isinstance(self.max_cache_size, bool)
            or self.max_cache_size <= 0
        ):
            raise CoordinationValidationError(
                f"max_cache_size must be a positive integer, got {self.max_cache_size!r}.",
                field="max_cache_size",
            )

        trust = _validate_finite_float(self.trust_threshold, "trust_threshold", min_val=0.0)
        if trust > 1.0:
            raise CoordinationValidationError(
                "trust_threshold must be in [0.0, 1.0].", field="trust_threshold"
            )
        object.__setattr__(self, "trust_threshold", trust)

        window = _validate_finite_float(
            self.dispute_grace_window_s, "dispute_grace_window_s", min_val=0.0
        )
        object.__setattr__(self, "dispute_grace_window_s", window)

        if not isinstance(self.fusion_policy, FusionPolicy):
            try:
                object.__setattr__(self, "fusion_policy", FusionPolicy(self.fusion_policy))
            except ValueError as exc:
                raise CoordinationValidationError(
                    f"Invalid fusion_policy '{self.fusion_policy}'.",
                    field="fusion_policy",
                ) from exc

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a JSON-compatible dictionary."""
        return {
            "enabled": self.enabled,
            "default_report_ttl_s": round(self.default_report_ttl_s, 4),
            "max_forwarding_hops": self.max_forwarding_hops,
            "max_cache_size": self.max_cache_size,
            "enabled_categories": [c.value for c in self.enabled_categories],
            "fusion_policy": self.fusion_policy.value,
            "trust_threshold": round(self.trust_threshold, 4),
            "dispute_grace_window_s": round(self.dispute_grace_window_s, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoordinationConfig":
        """Construct CoordinationConfig from a dictionary."""
        categories = tuple(
            ReportType(c)
            for c in data.get(
                "enabled_categories",
                [
                    ReportType.CONGESTION.value,
                    ReportType.ROAD_CLOSURE.value,
                    ReportType.HAZARD.value,
                ],
            )
        )
        return cls(
            enabled=data.get("enabled", True),
            default_report_ttl_s=float(data.get("default_report_ttl_s", 30.0)),
            max_forwarding_hops=int(data.get("max_forwarding_hops", 3)),
            max_cache_size=int(data.get("max_cache_size", 1000)),
            enabled_categories=categories,
            fusion_policy=FusionPolicy(
                data.get("fusion_policy", FusionPolicy.LATEST_EVIDENCE.value)
            ),
            trust_threshold=float(data.get("trust_threshold", 0.0)),
            dispute_grace_window_s=float(data.get("dispute_grace_window_s", 1.0)),
        )


@dataclass
class CoordinationMetrics:
    """Deterministic telemetry counters for decentralized knowledge exchange."""

    reports_created: int = 0
    reports_received: int = 0
    reports_accepted: int = 0
    reports_rejected_invalid: int = 0
    reports_rejected_expired: int = 0
    reports_rejected_duplicate: int = 0
    reports_rejected_untrusted: int = 0
    reports_forwarded: int = 0
    forwarding_loops_prevented: int = 0
    forwarding_hops_exceeded: int = 0
    beliefs_created: int = 0
    beliefs_updated: int = 0
    beliefs_expired: int = 0
    conflicts_detected: int = 0
    disputes_flagged: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert metrics to a plain dictionary."""
        return {
            "reports_created": self.reports_created,
            "reports_received": self.reports_received,
            "reports_accepted": self.reports_accepted,
            "reports_rejected_invalid": self.reports_rejected_invalid,
            "reports_rejected_expired": self.reports_rejected_expired,
            "reports_rejected_duplicate": self.reports_rejected_duplicate,
            "reports_rejected_untrusted": self.reports_rejected_untrusted,
            "reports_forwarded": self.reports_forwarded,
            "forwarding_loops_prevented": self.forwarding_loops_prevented,
            "forwarding_hops_exceeded": self.forwarding_hops_exceeded,
            "beliefs_created": self.beliefs_created,
            "beliefs_updated": self.beliefs_updated,
            "beliefs_expired": self.beliefs_expired,
            "conflicts_detected": self.conflicts_detected,
            "disputes_flagged": self.disputes_flagged,
        }

    def copy(self) -> "CoordinationMetrics":
        """Return an independent copy for atomic rollback snapshotting."""
        return CoordinationMetrics(**self.to_dict())

    def reset(self) -> None:
        """Reset all counters to zero."""
        for key in list(self.__dict__.keys()):
            setattr(self, key, 0)


@dataclass(frozen=True)
class KnowledgeStoreSnapshot:
    """Immutable snapshot of a vehicle's private knowledge store."""

    vehicle_id: str
    report_count: int
    active_report_count: int
    belief_count: int
    active_belief_count: int
    reports: dict[str, dict[str, Any]]
    beliefs: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "report_count": self.report_count,
            "active_report_count": self.active_report_count,
            "belief_count": self.belief_count,
            "active_belief_count": self.active_belief_count,
            "reports": {k: dict(v) for k, v in self.reports.items()},
            "beliefs": {k: dict(v) for k, v in self.beliefs.items()},
        }


@dataclass(frozen=True)
class CoordinationSnapshot:
    """System-wide snapshot of decentralized coordination subsystem state."""

    enabled: bool
    vehicle_count: int
    total_reports: int
    total_beliefs: int
    metrics: dict[str, int]
    stores: dict[str, KnowledgeStoreSnapshot]

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "enabled": self.enabled,
            "vehicle_count": self.vehicle_count,
            "total_reports": self.total_reports,
            "total_beliefs": self.total_beliefs,
            "metrics": dict(self.metrics),
            "stores": {vid: s.to_dict() for vid, s in self.stores.items()},
        }
