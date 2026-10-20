"""Domain-specific exceptions for decentralized V2V coordination and traffic knowledge sharing."""

from typing import Any, Optional


class CoordinationError(Exception):
    """Base exception for all decentralized coordination and knowledge-sharing errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = kwargs


class CoordinationValidationError(CoordinationError):
    """Raised when coordination configuration, message payload, or report fails validation."""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(message, field=field, **kwargs)
        self.field = field


class InvalidReportError(CoordinationValidationError):
    """Raised when a traffic report contains invalid attributes, IDs, or timestamps."""


class UnknownSourceVehicleError(CoordinationError):
    """Raised when a report originates from or is submitted to an unregistered vehicle."""

    def __init__(self, vehicle_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Unknown or unregistered source vehicle: '{vehicle_id}'."
        super().__init__(msg, vehicle_id=vehicle_id)
        self.vehicle_id = vehicle_id


class InvalidRoadEdgeError(CoordinationValidationError):
    """Raised when a traffic report references an edge not present in the road graph."""

    def __init__(self, edge_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Road edge '{edge_id}' does not exist in the road graph."
        super().__init__(msg, edge_id=edge_id, field="edge_id")
        self.edge_id = edge_id


class ExpiredReportError(CoordinationError):
    """Raised when attempting to accept or ingest an expired report as current."""

    def __init__(
        self,
        report_id: str,
        expiry_timestamp_s: float,
        current_time_s: float,
        message: Optional[str] = None,
    ) -> None:
        msg = message or (
            f"Report '{report_id}' has expired "
            f"(expiry={expiry_timestamp_s}s, current={current_time_s}s)."
        )
        super().__init__(
            msg,
            report_id=report_id,
            expiry_timestamp_s=expiry_timestamp_s,
            current_time_s=current_time_s,
        )
        self.report_id = report_id
        self.expiry_timestamp_s = expiry_timestamp_s
        self.current_time_s = current_time_s


class DuplicateReportError(CoordinationError):
    """Raised when a duplicate report ID is encountered where strict deduplication is enforced."""

    def __init__(self, report_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Duplicate traffic report '{report_id}' detected."
        super().__init__(msg, report_id=report_id)
        self.report_id = report_id


class ConflictingReportError(CoordinationError):
    """Raised when conflicting traffic reports cannot be resolved under the active fusion policy."""


class ForwardingLimitExceededError(CoordinationError):
    """Raised when report forwarding exceeds maximum hop limit or hop budget."""

    def __init__(
        self,
        report_id: str,
        current_hops: int,
        max_hops: int,
        message: Optional[str] = None,
    ) -> None:
        msg = message or (
            f"Report '{report_id}' exceeded maximum forwarding hops "
            f"({current_hops} > {max_hops})."
        )
        super().__init__(
            msg,
            report_id=report_id,
            current_hops=current_hops,
            max_hops=max_hops,
        )
        self.report_id = report_id
        self.current_hops = current_hops
        self.max_hops = max_hops


class CoordinationStateError(CoordinationError):
    """Raised when capturing, applying, or restoring coordination rollback state fails."""
