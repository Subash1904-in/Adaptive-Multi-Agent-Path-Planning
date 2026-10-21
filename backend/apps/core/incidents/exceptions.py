"""Exceptions for the traffic incident management and scenario injection subsystem."""

from typing import Any, Optional


class IncidentError(Exception):
    """Base exception for all incident-related errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class IncidentValidationError(IncidentError):
    """Raised when an incident request violates schema constraints or parameter bounds."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.field = field


class IncidentNotFoundError(IncidentError):
    """Raised when an incident identifier cannot be found or is already resolved."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(
            f"Incident '{incident_id}' not found.",
            details={"incident_id": incident_id},
        )
        self.incident_id = incident_id


class InvalidIncidentTargetError(IncidentValidationError):
    """Raised when an incident references a non-existent edge or intersection/signal node."""

    def __init__(
        self,
        message: str,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            field=f"affected_{target_type}_id" if target_type else None,
            details={"target_id": target_id, "target_type": target_type},
        )
        self.target_id = target_id
        self.target_type = target_type


class TerminalRunIncidentError(IncidentError):
    """Raised when attempting to inject or mutate incidents on a terminal simulation."""

    def __init__(self, run_id: str, lifecycle_state: str) -> None:
        super().__init__(
            f"Cannot mutate incidents on run '{run_id}' in terminal state '{lifecycle_state}'.",
            details={"run_id": run_id, "lifecycle_state": lifecycle_state},
        )
        self.run_id = run_id
        self.lifecycle_state = lifecycle_state


class DuplicateIncidentIdError(IncidentValidationError):
    """Raised when attempting to create an incident with an already existing ID."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(
            f"Incident with ID '{incident_id}' already exists.",
            field="id",
            details={"incident_id": incident_id},
        )
        self.incident_id = incident_id
