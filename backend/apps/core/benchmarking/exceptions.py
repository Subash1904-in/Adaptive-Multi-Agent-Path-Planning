"""Exceptions for the AMAPP benchmarking subsystem."""

from typing import Optional

from apps.core.domain.exceptions import DomainException


class BenchmarkError(DomainException):
    """Base exception for all benchmarking operations."""

    pass


class UnsupportedAlgorithmError(BenchmarkError):
    """Raised when a requested routing algorithm is unknown, unregistered, or unimplemented."""

    def __init__(
        self,
        algorithm_id: str,
        message: Optional[str] = None,
        available_algorithms: Optional[list[str]] = None,
    ) -> None:
        avail_str = f" Available algorithms: {available_algorithms}" if available_algorithms else ""
        msg = (
            message
            or f"Routing algorithm '{algorithm_id}' is not supported or not implemented.{avail_str}"
        )
        super().__init__(msg, field="algorithm_id")
        self.algorithm_id = algorithm_id
        self.available_algorithms = available_algorithms or []


class UnsupportedScenarioError(BenchmarkError):
    """Raised when a requested benchmark scenario is unknown or unregistered."""

    def __init__(
        self,
        scenario_id: str,
        message: Optional[str] = None,
        available_scenarios: Optional[list[str]] = None,
    ) -> None:
        avail_str = f" Available scenarios: {available_scenarios}" if available_scenarios else ""
        msg = message or f"Benchmark scenario '{scenario_id}' is not registered.{avail_str}"
        super().__init__(msg, field="scenario_id")
        self.scenario_id = scenario_id
        self.available_scenarios = available_scenarios or []


class BenchmarkExecutionError(BenchmarkError):
    """Raised when an unrecoverable error occurs during benchmark orchestration."""

    def __init__(
        self,
        message: str,
        scenario_id: Optional[str] = None,
        algorithm_id: Optional[str] = None,
        trial_index: Optional[int] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.scenario_id = scenario_id
        self.algorithm_id = algorithm_id
        self.trial_index = trial_index
        self.cause = cause


class BenchmarkExportError(BenchmarkError):
    """Raised when benchmark result export fails due to invalid paths or I/O."""

    pass
