"""Simulation subsystem exceptions.

Defines the error hierarchy for simulation clock, world state, and simulation engine.
All exceptions inherit from DomainException to maintain unified error handling.
"""

from typing import Any, Optional

from apps.core.domain.exceptions import DomainException


class SimulationError(DomainException):
    """Base exception for all simulation subsystem errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class InvalidTimeStepError(SimulationError):
    """Raised when an invalid, non-finite, non-positive, or out-of-bounds dt is supplied."""

    def __init__(self, message: str, dt_s: Optional[float] = None) -> None:
        details = {"dt_s": dt_s} if dt_s is not None else {}
        super().__init__(message, details=details)
        self.dt_s = dt_s


class ClockStateError(SimulationError):
    """Raised when an invalid clock operation or state transition is requested."""

    def __init__(self, message: str, current_state: Optional[str] = None) -> None:
        details = {"current_state": current_state} if current_state is not None else {}
        super().__init__(message, details=details)
        self.current_state = current_state


class DuplicateAgentIdError(SimulationError):
    """Raised when attempting to add an agent whose identifier already exists in the world."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent with id '{agent_id}' already exists in the world state.",
            details={"agent_id": agent_id},
        )
        self.agent_id = agent_id


class AgentNotFoundError(SimulationError):
    """Raised when requesting an agent that does not exist in the world state."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent with id '{agent_id}' was not found in the world state.",
            details={"agent_id": agent_id},
        )
        self.agent_id = agent_id


class IncompatibleAgentGraphError(SimulationError):
    """Raised when an agent's road graph or route is incompatible with the world graph."""

    def __init__(self, message: str, agent_id: Optional[str] = None) -> None:
        details = {"agent_id": agent_id} if agent_id is not None else {}
        super().__init__(message, details=details)
        self.agent_id = agent_id


class EngineStateError(SimulationError):
    """Raised when an operation is invalid for the engine's current state."""

    def __init__(self, message: str, current_state: Optional[str] = None) -> None:
        details = {"current_state": current_state} if current_state is not None else {}
        super().__init__(message, details=details)
        self.current_state = current_state


class TickExecutionError(SimulationError):
    """Raised when a failure occurs during a simulation tick, triggering atomic rollback."""

    def __init__(self, message: str, tick: int, cause: Optional[Exception] = None) -> None:
        details = {"tick": tick, "cause": str(cause) if cause else None}
        super().__init__(message, details=details)
        self.tick = tick
        self.cause = cause
