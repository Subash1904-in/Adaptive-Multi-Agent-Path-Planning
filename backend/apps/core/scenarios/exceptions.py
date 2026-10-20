"""Scenario subsystem exceptions for AMAPP.

Defines the error hierarchy for scenario configuration validation, builder assembly,
and execution orchestration. All inherit from DomainException to ensure unified error handling.
"""

from typing import Any, Optional

from apps.core.domain.exceptions import DomainException


class ScenarioError(DomainException):
    """Base exception for all scenario orchestration errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class ScenarioValidationError(ScenarioError):
    """Raised when a scenario configuration fails structural or semantic validation."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(details or {})
        if field is not None:
            details["field"] = field
        super().__init__(message, details=details)
        self.field = field


class UnreachableDestinationError(ScenarioValidationError):
    """Raised when a vehicle agent's destination cannot be reached from its start node."""

    def __init__(
        self,
        vehicle_id: str,
        start_node_id: str,
        destination_node_id: str,
        message: Optional[str] = None,
    ) -> None:
        msg = message or (
            f"Vehicle '{vehicle_id}' cannot reach destination '{destination_node_id}' "
            f"from start node '{start_node_id}'."
        )
        super().__init__(
            msg,
            field="destination_node_id",
            details={
                "vehicle_id": vehicle_id,
                "start_node_id": start_node_id,
                "destination_node_id": destination_node_id,
            },
        )
        self.vehicle_id = vehicle_id
        self.start_node_id = start_node_id
        self.destination_node_id = destination_node_id


class ScenarioBuilderError(ScenarioError):
    """Raised when graph, signal, agent, or world state assembly fails."""

    def __init__(
        self,
        message: str,
        scenario_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details: dict[str, Any] = {}
        if scenario_id:
            details["scenario_id"] = scenario_id
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details=details)
        self.scenario_id = scenario_id
        self.cause = cause


class ScenarioExecutionError(ScenarioError):
    """Raised when scenario execution encounters an unrecoverable runtime error."""

    def __init__(
        self,
        message: str,
        scenario_id: Optional[str] = None,
        tick: Optional[int] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details: dict[str, Any] = {}
        if scenario_id:
            details["scenario_id"] = scenario_id
        if tick is not None:
            details["tick"] = tick
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details=details)
        self.scenario_id = scenario_id
        self.tick = tick
        self.cause = cause


class ScenarioResetError(ScenarioError):
    """Raised when resetting scenario state to its initial baseline fails."""

    def __init__(
        self,
        message: str,
        scenario_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        details: dict[str, Any] = {}
        if scenario_id:
            details["scenario_id"] = scenario_id
        if cause:
            details["cause"] = str(cause)
        super().__init__(message, details=details)
        self.scenario_id = scenario_id
        self.cause = cause
