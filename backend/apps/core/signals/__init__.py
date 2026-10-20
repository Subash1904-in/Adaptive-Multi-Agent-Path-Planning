"""Traffic signal subsystem for intersection control and phase management.

Provides deterministic phase progression (RED -> GREEN -> YELLOW -> RED),
cycle configuration, and intersection approach associations.
"""

from apps.core.signals.controller import TrafficSignalController
from apps.core.signals.exceptions import (
    DuplicateSignalError,
    InvalidIntersectionAssociationError,
    InvalidSignalCycleError,
    SignalError,
    SignalNotFoundError,
)
from apps.core.signals.models import (
    SignalCycleConfig,
    SignalQueryResult,
    SignalSnapshot,
)

__all__ = [
    "DuplicateSignalError",
    "InvalidIntersectionAssociationError",
    "InvalidSignalCycleError",
    "SignalCycleConfig",
    "SignalError",
    "SignalNotFoundError",
    "SignalQueryResult",
    "SignalSnapshot",
    "TrafficSignalController",
]
