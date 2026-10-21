"""Incident management and dynamic scenario disruption subsystem.

Provides backend-authoritative incident validation, graph edge closure and congestion mutations,
traffic signal phase overrides, automatic duration expiry, and baseline restoration.
"""

from apps.core.incidents.exceptions import (
    DuplicateIncidentIdError,
    IncidentError,
    IncidentNotFoundError,
    IncidentValidationError,
    InvalidIncidentTargetError,
    TerminalRunIncidentError,
)
from apps.core.incidents.manager import (
    SUPPORTED_INCIDENT_TYPES,
    IncidentManager,
)
from apps.core.incidents.models import (
    IncidentRecord,
    IncidentSubsystemSnapshot,
)

__all__ = [
    "DuplicateIncidentIdError",
    "IncidentError",
    "IncidentManager",
    "IncidentNotFoundError",
    "IncidentRecord",
    "IncidentSubsystemSnapshot",
    "IncidentValidationError",
    "InvalidIncidentTargetError",
    "SUPPORTED_INCIDENT_TYPES",
    "TerminalRunIncidentError",
]
