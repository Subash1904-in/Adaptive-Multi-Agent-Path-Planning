"""Traffic signal subsystem exceptions.

Defines the error hierarchy for signal configuration, controllers, and intersection associations.
All exceptions inherit from DomainException to maintain unified error handling.
"""

from typing import Any, Optional

from apps.core.domain.exceptions import DomainException


class SignalError(DomainException):
    """Base exception for all traffic signal subsystem errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class InvalidSignalCycleError(SignalError):
    """Raised when an invalid, non-positive, non-finite duration or phase offset is supplied."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


class DuplicateSignalError(SignalError):
    """Raised when attempting to register a traffic signal whose ID already exists."""

    def __init__(self, signal_id: str) -> None:
        super().__init__(
            f"TrafficSignal with id '{signal_id}' already exists in the world state.",
            details={"signal_id": signal_id},
        )
        self.signal_id = signal_id


class SignalNotFoundError(SignalError):
    """Raised when querying a traffic signal that does not exist."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            f"TrafficSignal '{identifier}' was not found.",
            details={"identifier": identifier},
        )
        self.identifier = identifier


class InvalidIntersectionAssociationError(SignalError):
    """Raised when a signal references a non-existent node or inconsistent incoming edges."""

    def __init__(self, message: str, node_id: Optional[str] = None) -> None:
        details = {"node_id": node_id} if node_id is not None else {}
        super().__init__(message, details=details)
        self.node_id = node_id
