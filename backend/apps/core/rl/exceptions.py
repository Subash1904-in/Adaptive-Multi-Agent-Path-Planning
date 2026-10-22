"""Domain exceptions for the Reinforcement Learning (RL) environment subsystem."""

from __future__ import annotations

from typing import Any, Optional


class RLEnvironmentError(Exception):
    """Base exception for all RL environment errors."""

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause


class InvalidActionError(RLEnvironmentError):
    """Raised when an action is out of range or fundamentally malformed."""

    def __init__(
        self,
        message: str,
        action: Any,
        agent_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        d = details or {}
        d.update({"action": action, "agent_id": agent_id})
        super().__init__(message, details=d)
        self.action = action
        self.agent_id = agent_id


class ObservationError(RLEnvironmentError):
    """Raised when observation computation encounters invalid or non-finite values."""

    def __init__(
        self,
        message: str,
        agent_id: Optional[str] = None,
        feature_name: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        d = details or {}
        d.update({"agent_id": agent_id, "feature_name": feature_name})
        super().__init__(message, details=d)
        self.agent_id = agent_id
        self.feature_name = feature_name


class ScenarioResetError(RLEnvironmentError):
    """Raised when resetting the environment scenario fails."""

    def __init__(
        self,
        message: str,
        scenario_id: Optional[str] = None,
        seed: Optional[int] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details = {"scenario_id": scenario_id, "seed": seed, "cause": str(cause) if cause else None}
        super().__init__(message, details=details)
        self.scenario_id = scenario_id
        self.seed = seed
        self.cause = cause


class ActionMaskError(RLEnvironmentError):
    """Raised when action mask derivation encounters inconsistent state."""

    def __init__(
        self,
        message: str,
        agent_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        d = details or {}
        d["agent_id"] = agent_id
        super().__init__(message, details=d)
        self.agent_id = agent_id


class AgentNotFoundError(RLEnvironmentError):
    """Raised when the specified agent is not found in the world state."""

    def __init__(
        self,
        message: str,
        agent_id: str,
        available_agents: Optional[list[str]] = None,
    ) -> None:
        details = {"agent_id": agent_id, "available_agents": available_agents or []}
        super().__init__(message, details=details)
        self.agent_id = agent_id
        self.available_agents = available_agents or []
