"""Kinematics and agent lifecycle exceptions for the AMAPP simulation platform.

All exceptions inherit from `DomainException` for consistency with core domain error handling.
"""

from typing import Optional

from apps.core.domain.exceptions import DomainException


class KinematicsError(DomainException):
    """Base exception for all vehicle kinematics and lifecycle operations."""

    pass


class InvalidKinematicsConfigError(KinematicsError):
    """Raised when a kinematics configuration contains invalid or non-physical parameters."""

    def __init__(self, message: str, param: Optional[str] = None) -> None:
        super().__init__(message)
        self.param = param


class InvalidMotionInputError(KinematicsError):
    """Raised when motion integration inputs (e.g. dt, acceleration, speed) are invalid."""

    def __init__(self, message: str, field_name: Optional[str] = None) -> None:
        super().__init__(message)
        self.field_name = field_name


class InvalidRouteError(KinematicsError):
    """Raised when an assigned navigation route cannot be traversed or validated."""

    def __init__(self, message: str, route_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.route_id = route_id


class InvalidLifecycleTransitionError(KinematicsError):
    """Raised when an invalid vehicle agent lifecycle transition is attempted."""

    def __init__(
        self, message: str, from_state: Optional[str] = None, to_state: Optional[str] = None
    ) -> None:
        super().__init__(message)
        self.from_state = from_state
        self.to_state = to_state
