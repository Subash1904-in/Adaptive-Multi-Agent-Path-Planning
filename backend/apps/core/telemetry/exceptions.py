"""Exception taxonomy for the telemetry and scenario execution subsystem.

Defines structured exceptions for telemetry validation, stream retention, schema evolution,
run lifecycle transitions, limits validation, and serialization exports.
All inherit from DomainException to ensure unified domain error handling.
"""

from typing import Any, Optional

from apps.core.domain.exceptions import DomainException


class TelemetryError(DomainException):
    """Base exception for all telemetry and scenario runner errors."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        run_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, field=field)
        self.run_id = run_id
        self.details = details or {}


class TelemetryValidationError(TelemetryError):
    """Raised when a telemetry record fails schema validation or constraints."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        run_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, field=field, run_id=run_id, details=details)


class UnsupportedSchemaError(TelemetryError):
    """Raised when an unrecognized or unsupported telemetry schema version is encountered."""

    def __init__(
        self,
        message: str,
        schema_version: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        details = {"schema_version": schema_version} if schema_version else {}
        super().__init__(message, field="schema_version", run_id=run_id, details=details)
        self.schema_version = schema_version


class TelemetryRetentionOverflowError(TelemetryError):
    """Raised when critical telemetry cannot be retained due to capacity or strict retention."""

    def __init__(
        self,
        message: str,
        capacity: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> None:
        details = {"capacity": capacity} if capacity is not None else {}
        super().__init__(message, field="capacity", run_id=run_id, details=details)
        self.capacity = capacity


class ExportSizeLimitExceededError(TelemetryError):
    """Raised when serialized simulation result export exceeds configured byte limit."""

    def __init__(
        self,
        message: str,
        size_bytes: Optional[int] = None,
        max_bytes: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> None:
        details = {"size_bytes": size_bytes, "max_bytes": max_bytes}
        super().__init__(message, field="max_export_bytes", run_id=run_id, details=details)
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class RunStateTransitionError(TelemetryError):
    """Raised when an invalid lifecycle state transition is attempted on a scenario run."""

    def __init__(
        self,
        message: str,
        current_state: Optional[str] = None,
        target_state: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        details = {"current_state": current_state, "target_state": target_state}
        super().__init__(message, field="lifecycle_state", run_id=run_id, details=details)
        self.current_state = current_state
        self.target_state = target_state


class InvalidExecutionLimitsError(TelemetryError):
    """Raised when execution limits (e.g., max_ticks, max_duration_s) are invalid."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        run_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, field=field, run_id=run_id, details=details)


class CancellationError(TelemetryError):
    """Raised when a run cancellation request fails or is invalid."""

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, field="cancellation", run_id=run_id, details=details)


class DuplicateRunIdError(TelemetryError):
    """Raised when attempting to execute with a duplicate or conflicting run ID."""

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, field="run_id", run_id=run_id)


class ScenarioFinalizationError(TelemetryError):
    """Raised when finalization of a simulation run or metrics summary fails."""

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {"cause": str(cause)} if cause else {}
        super().__init__(message, run_id=run_id, details=details)
        self.cause = cause


class InvalidMetricValueError(TelemetryError):
    """Raised when an aggregated or computed metric value violates validity constraints."""

    def __init__(
        self,
        message: str,
        metric_name: Optional[str] = None,
        value: Any = None,
        run_id: Optional[str] = None,
    ) -> None:
        details = {"metric_name": metric_name, "value": value}
        super().__init__(message, field=metric_name, run_id=run_id, details=details)
        self.metric_name = metric_name
        self.value = value
