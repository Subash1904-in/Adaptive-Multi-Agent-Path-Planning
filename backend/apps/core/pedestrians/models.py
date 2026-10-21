"""Data models, enums, and configuration for pedestrian agents."""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from apps.core.domain.values import Position2D
from apps.core.pedestrians.exceptions import (
    InvalidPedestrianConfigError,
    InvalidPedestrianStateError,
)


class PedestrianLifecycleState(str, Enum):
    """Explicit lifecycle state of a pedestrian agent."""

    IDLE = "idle"
    APPROACHING_CROSSWALK = "approaching_crosswalk"
    WAITING_TO_CROSS = "waiting_to_cross"
    CROSSING = "crossing"
    WALKING = "walking"
    ARRIVED = "arrived"
    BLOCKED = "blocked"


class PedestrianSignalState(str, Enum):
    """Pedestrian crossing indication signal state."""

    WALK = "walk"
    CLEARANCE = "clearance"
    DONT_WALK = "dont_walk"


@dataclass(frozen=True)
class PedestrianConfig:
    """Validated configuration parameters for pedestrian agents.

    Units:
        - Speeds: meters per second (m/s).
        - Dimensions: meters (m).
        - Tolerances: meters (m).
    """

    walking_speed_mps: float = 1.4  # Average pedestrian walking speed (~5 km/h)
    max_speed_mps: float = 2.0
    length_m: float = 0.6  # Longitudinal bounding box depth
    width_m: float = 0.6  # Lateral bounding box width (shoulder-to-shoulder)
    arrival_tolerance_m: float = 0.5  # Proximity threshold to register arrival at target
    waiting_distance_m: float = 1.5  # Proximity threshold to crosswalk entry to begin waiting

    def __post_init__(self) -> None:
        """Validate physical parameters and thresholds."""
        for name, val in [
            ("walking_speed_mps", self.walking_speed_mps),
            ("max_speed_mps", self.max_speed_mps),
            ("length_m", self.length_m),
            ("width_m", self.width_m),
            ("arrival_tolerance_m", self.arrival_tolerance_m),
            ("waiting_distance_m", self.waiting_distance_m),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise InvalidPedestrianConfigError(
                    f"Parameter '{name}' must be numeric, got {type(val).__name__}."
                )
            if not math.isfinite(val):
                raise InvalidPedestrianConfigError(f"Parameter '{name}' must be finite, got {val}.")
            if val <= 0.0:
                raise InvalidPedestrianConfigError(
                    f"Parameter '{name}' must be strictly positive, got {val}."
                )

        if self.walking_speed_mps > self.max_speed_mps:
            raise InvalidPedestrianConfigError(
                f"walking_speed_mps ({self.walking_speed_mps}) cannot exceed "
                f"max_speed_mps ({self.max_speed_mps})."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        return {
            "walking_speed_mps": round(self.walking_speed_mps, 3),
            "max_speed_mps": round(self.max_speed_mps, 3),
            "length_m": round(self.length_m, 3),
            "width_m": round(self.width_m, 3),
            "arrival_tolerance_m": round(self.arrival_tolerance_m, 3),
            "waiting_distance_m": round(self.waiting_distance_m, 3),
        }


@dataclass(frozen=True)
class PedestrianStepResult:
    """Deterministic step outcome for a pedestrian agent over a simulation tick."""

    pedestrian_id: str
    old_position: Position2D
    new_position: Position2D
    old_state: PedestrianLifecycleState
    new_state: PedestrianLifecycleState
    speed_mps: float
    heading_rad: float
    waiting_time_s: float
    crosswalk_id: Optional[str]
    arrived: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize step result to dictionary."""
        return {
            "pedestrian_id": self.pedestrian_id,
            "old_position": self.old_position.to_dict(),
            "new_position": self.new_position.to_dict(),
            "old_state": self.old_state.value,
            "new_state": self.new_state.value,
            "speed_mps": round(self.speed_mps, 4),
            "heading_rad": round(self.heading_rad, 4),
            "waiting_time_s": round(self.waiting_time_s, 4),
            "crosswalk_id": self.crosswalk_id,
            "arrived": self.arrived,
        }


# Legal state transition rules
LEGAL_PEDESTRIAN_TRANSITIONS: dict[PedestrianLifecycleState, set[PedestrianLifecycleState]] = {
    PedestrianLifecycleState.IDLE: {
        PedestrianLifecycleState.APPROACHING_CROSSWALK,
        PedestrianLifecycleState.WAITING_TO_CROSS,
        PedestrianLifecycleState.CROSSING,
        PedestrianLifecycleState.WALKING,
        PedestrianLifecycleState.BLOCKED,
    },
    PedestrianLifecycleState.APPROACHING_CROSSWALK: {
        PedestrianLifecycleState.WAITING_TO_CROSS,
        PedestrianLifecycleState.CROSSING,
        PedestrianLifecycleState.BLOCKED,
        PedestrianLifecycleState.ARRIVED,
    },
    PedestrianLifecycleState.WAITING_TO_CROSS: {
        PedestrianLifecycleState.CROSSING,
        PedestrianLifecycleState.BLOCKED,
    },
    PedestrianLifecycleState.CROSSING: {
        PedestrianLifecycleState.ARRIVED,
        PedestrianLifecycleState.WALKING,
        PedestrianLifecycleState.BLOCKED,
    },
    PedestrianLifecycleState.WALKING: {
        PedestrianLifecycleState.APPROACHING_CROSSWALK,
        PedestrianLifecycleState.WAITING_TO_CROSS,
        PedestrianLifecycleState.ARRIVED,
        PedestrianLifecycleState.BLOCKED,
    },
    PedestrianLifecycleState.ARRIVED: set(),  # Terminal state
    PedestrianLifecycleState.BLOCKED: {
        PedestrianLifecycleState.APPROACHING_CROSSWALK,
        PedestrianLifecycleState.WAITING_TO_CROSS,
        PedestrianLifecycleState.CROSSING,
        PedestrianLifecycleState.WALKING,
    },
}


def validate_pedestrian_transition(
    current_state: PedestrianLifecycleState,
    next_state: PedestrianLifecycleState,
    pedestrian_id: str = "",
) -> bool:
    """Validate that transition from current_state to next_state is legal.

    Returns:
        True if the transition is legal.

    Raises:
        InvalidPedestrianStateError: If transition is not in LEGAL_PEDESTRIAN_TRANSITIONS.
    """
    if current_state == next_state:
        return True
    legal = LEGAL_PEDESTRIAN_TRANSITIONS.get(current_state, set())
    if next_state not in legal:
        raise InvalidPedestrianStateError(
            f"Illegal state transition for pedestrian '{pedestrian_id}': "
            f"cannot transition from {current_state.value} to {next_state.value}."
        )
    return True
