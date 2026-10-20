"""Public API exports for decentralized V2V coordination and traffic knowledge."""

from apps.core.coordination.dissemination import (
    DisseminationManager,
    map_report_to_message_type,
)
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
from apps.core.coordination.fusion import (
    InformationFusion,
    derive_belief_id,
    derive_target_id,
)
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.manager import CoordinationManager
from apps.core.coordination.models import (
    BaseTrafficReport,
    BeliefRecord,
    BeliefStatus,
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    CoordinationMetrics,
    CoordinationSnapshot,
    FusionPolicy,
    HazardReport,
    HazardSeverity,
    HazardType,
    KnowledgeStoreSnapshot,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
    TrafficReport,
    traffic_report_from_dict,
)

__all__ = [
    # Models & enums
    "ReportType",
    "CongestionLevel",
    "RoadClosureStatus",
    "HazardType",
    "HazardSeverity",
    "BeliefStatus",
    "FusionPolicy",
    "BaseTrafficReport",
    "CongestionReport",
    "RoadClosureReport",
    "HazardReport",
    "TrafficReport",
    "traffic_report_from_dict",
    "BeliefRecord",
    "CoordinationConfig",
    "CoordinationMetrics",
    "KnowledgeStoreSnapshot",
    "CoordinationSnapshot",
    # Knowledge store
    "VehicleKnowledgeStore",
    # Information fusion
    "InformationFusion",
    "derive_belief_id",
    "derive_target_id",
    # Dissemination
    "DisseminationManager",
    "map_report_to_message_type",
    # Subsystem manager
    "CoordinationManager",
    # Exceptions
    "CoordinationError",
    "CoordinationValidationError",
    "InvalidReportError",
    "UnknownSourceVehicleError",
    "InvalidRoadEdgeError",
    "ExpiredReportError",
    "DuplicateReportError",
    "ConflictingReportError",
    "ForwardingLimitExceededError",
    "CoordinationStateError",
]
