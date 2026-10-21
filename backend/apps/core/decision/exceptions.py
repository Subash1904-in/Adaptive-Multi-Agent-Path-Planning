"""Custom domain exceptions for the decision policy subsystem."""

from typing import Any, Optional


class DecisionError(Exception):
    """Base exception for all decision policy errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DecisionValidationError(DecisionError):
    """Raised when decision inputs, context, or configurations fail validation."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        d = dict(details or {})
        if field:
            d["field"] = field
        super().__init__(message, details=d)
        self.field = field


class PolicyConfigurationError(DecisionValidationError):
    """Raised when a decision policy configuration has invalid parameters."""

    pass


class InvalidCandidateError(DecisionValidationError):
    """Raised when a candidate route is structurally invalid, empty, or unfeasible."""

    def __init__(
        self,
        message: str,
        candidate_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        d = dict(details or {})
        if candidate_id:
            d["candidate_id"] = candidate_id
        super().__init__(message, field="candidate", details=d)
        self.candidate_id = candidate_id


class StaleRouteError(DecisionError):
    """Raised when a candidate route refers to an outdated route version or topology."""

    pass


class DecisionExecutionError(DecisionError):
    """Raised when an internal error occurs during policy evaluation."""

    pass
