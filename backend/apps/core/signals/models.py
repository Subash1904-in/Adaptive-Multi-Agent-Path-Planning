"""Data models and cycle configuration for intersection traffic signals.

Provides validated cycle configurations, immutable point-in-time signal snapshots,
and typed query results for vehicle navigation queries.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from apps.core.domain.enums import TrafficSignalState
from apps.core.signals.exceptions import InvalidSignalCycleError


@dataclass(frozen=True)
class SignalCycleConfig:
    """Validated phase timing and duration parameters for a traffic signal cycle.

    Enforces the deterministic cyclic progression:
        RED -> GREEN -> YELLOW -> RED
    """

    green_duration_s: float = 30.0
    yellow_duration_s: float = 5.0
    red_duration_s: float = 30.0
    initial_phase: TrafficSignalState = TrafficSignalState.RED
    phase_offset_s: float = 0.0

    def __post_init__(self) -> None:
        """Validate durations and offset parameters."""
        for name, val in [
            ("green_duration_s", self.green_duration_s),
            ("yellow_duration_s", self.yellow_duration_s),
            ("red_duration_s", self.red_duration_s),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise InvalidSignalCycleError(
                    f"{name} must be a numeric float, got {type(val).__name__}."
                )
            if not math.isfinite(val):
                raise InvalidSignalCycleError(f"{name} must be a finite float, got {val}.")
            if val <= 0.0:
                raise InvalidSignalCycleError(f"{name} must be strictly positive, got {val}.")

        if not isinstance(self.initial_phase, TrafficSignalState):
            raise InvalidSignalCycleError(
                f"initial_phase must be a TrafficSignalState enum, got {self.initial_phase}."
            )

        if not isinstance(self.phase_offset_s, (int, float)) or isinstance(
            self.phase_offset_s, bool
        ):
            raise InvalidSignalCycleError(
                f"phase_offset_s must be numeric, got {type(self.phase_offset_s).__name__}."
            )
        if not math.isfinite(self.phase_offset_s):
            raise InvalidSignalCycleError(
                f"phase_offset_s must be finite, got {self.phase_offset_s}."
            )
        if self.phase_offset_s < 0.0:
            raise InvalidSignalCycleError(
                f"phase_offset_s must be non-negative, got {self.phase_offset_s}."
            )

        total = self.green_duration_s + self.yellow_duration_s + self.red_duration_s
        if self.phase_offset_s >= total:
            raise InvalidSignalCycleError(
                f"phase_offset_s ({self.phase_offset_s}s) must be strictly less than "
                f"total cycle duration ({total}s)."
            )

    @property
    def total_cycle_duration_s(self) -> float:
        """Full period duration of one complete signal cycle in seconds."""
        return self.green_duration_s + self.yellow_duration_s + self.red_duration_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        return {
            "green_duration_s": round(self.green_duration_s, 3),
            "yellow_duration_s": round(self.yellow_duration_s, 3),
            "red_duration_s": round(self.red_duration_s, 3),
            "initial_phase": self.initial_phase.value,
            "phase_offset_s": round(self.phase_offset_s, 3),
            "total_cycle_duration_s": round(self.total_cycle_duration_s, 3),
        }


@dataclass(frozen=True)
class SignalSnapshot:
    """Immutable point-in-time state of an individual traffic signal."""

    signal_id: str
    node_id: str
    state: TrafficSignalState
    remaining_phase_s: float
    elapsed_in_phase_s: float
    cycle_duration_s: float
    incoming_edge_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize signal snapshot to a plain JSON-compatible dictionary."""
        return {
            "signal_id": self.signal_id,
            "node_id": self.node_id,
            "state": self.state.value,
            "remaining_phase_s": round(self.remaining_phase_s, 4),
            "elapsed_in_phase_s": round(self.elapsed_in_phase_s, 4),
            "cycle_duration_s": round(self.cycle_duration_s, 3),
            "incoming_edge_ids": list(self.incoming_edge_ids),
        }


@dataclass(frozen=True)
class SignalQueryResult:
    """Structured query response for vehicle approach queries."""

    signal_id: str
    node_id: str
    state: TrafficSignalState
    remaining_phase_s: float
    time_to_green_s: float
    time_to_red_s: float
    incoming_edge_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize query result to a plain JSON-compatible dictionary."""
        return {
            "signal_id": self.signal_id,
            "node_id": self.node_id,
            "state": self.state.value,
            "remaining_phase_s": round(self.remaining_phase_s, 4),
            "time_to_green_s": round(self.time_to_green_s, 4),
            "time_to_red_s": round(self.time_to_red_s, 4),
            "incoming_edge_ids": list(self.incoming_edge_ids),
        }
