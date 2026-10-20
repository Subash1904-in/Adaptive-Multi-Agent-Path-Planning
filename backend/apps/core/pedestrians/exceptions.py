"""Exceptions for pedestrian agents, crosswalks, and signal interactions."""

from typing import Any, Optional


class PedestrianError(Exception):
    """Base exception for all pedestrian and crosswalk errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.details: dict[str, Any] = details or {}


class InvalidPedestrianStateError(PedestrianError):
    """Raised when an illegal pedestrian state transition or state value is encountered."""


class InvalidPedestrianConfigError(PedestrianError):
    """Raised when pedestrian configuration parameters violate physical invariants."""


class InvalidCrosswalkError(PedestrianError):
    """Raised when crosswalk geometry, coordinates, or references are invalid."""


class CrosswalkNotFoundError(PedestrianError):
    """Raised when a referenced crosswalk does not exist in the simulation world."""


class PedestrianKinematicsError(PedestrianError):
    """Raised when pedestrian kinematics integration fails or produces non-finite coordinates."""


class DuplicatePedestrianError(PedestrianError):
    """Raised when registering a pedestrian with an already existing ID."""


class PedestrianNotFoundError(PedestrianError):
    """Raised when a requested pedestrian ID does not exist."""

