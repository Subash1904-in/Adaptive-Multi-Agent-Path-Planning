"""Deterministic metrics tracking for pedestrian agents, crossings, and conflicts."""

from typing import Any

from apps.core.pedestrians.models import (
    PedestrianLifecycleState,
    PedestrianStepResult,
)


class PedestrianMetrics:
    """Tracks cumulative and point-in-time statistics for pedestrian operations."""

    def __init__(self) -> None:
        self.active_count: int = 0
        self.waiting_count: int = 0
        self.crossing_count: int = 0
        self.arrived_count: int = 0
        self.crossings_started: int = 0
        self.crossings_completed: int = 0
        self.total_waiting_time_s: float = 0.0
        self.pedestrian_vehicle_conflicts: int = 0
        self.pedestrian_near_misses: int = 0
        self.pedestrian_collisions: int = 0

    def record_step(self, res: PedestrianStepResult) -> None:
        """Update metrics based on an individual pedestrian's step outcome."""
        if (
            res.old_state != PedestrianLifecycleState.CROSSING
            and res.new_state == PedestrianLifecycleState.CROSSING
        ):
            self.crossings_started += 1

        if (
            res.old_state == PedestrianLifecycleState.CROSSING
            and res.new_state == PedestrianLifecycleState.ARRIVED
        ):
            self.crossings_completed += 1

    def update_point_in_time_counts(self, agents: list[Any]) -> None:
        """Update instantaneous active, waiting, and crossing counts from agent list."""
        self.active_count = sum(1 for a in agents if a.state != PedestrianLifecycleState.ARRIVED)
        self.waiting_count = sum(
            1 for a in agents if a.state == PedestrianLifecycleState.WAITING_TO_CROSS
        )
        self.crossing_count = sum(1 for a in agents if a.state == PedestrianLifecycleState.CROSSING)
        self.arrived_count = sum(1 for a in agents if a.state == PedestrianLifecycleState.ARRIVED)
        self.total_waiting_time_s = sum(a.waiting_time_s for a in agents)

    def record_safety_event(self, is_collision: bool, is_near_miss: bool) -> None:
        """Record pedestrian-vehicle conflict occurrences."""
        self.pedestrian_vehicle_conflicts += 1
        if is_collision:
            self.pedestrian_collisions += 1
        if is_near_miss:
            self.pedestrian_near_misses += 1

    def capture_state(self) -> dict[str, Any]:
        """Capture atomic rollback snapshot of metrics."""
        return {
            "active_count": self.active_count,
            "waiting_count": self.waiting_count,
            "crossing_count": self.crossing_count,
            "arrived_count": self.arrived_count,
            "crossings_started": self.crossings_started,
            "crossings_completed": self.crossings_completed,
            "total_waiting_time_s": self.total_waiting_time_s,
            "pedestrian_vehicle_conflicts": self.pedestrian_vehicle_conflicts,
            "pedestrian_near_misses": self.pedestrian_near_misses,
            "pedestrian_collisions": self.pedestrian_collisions,
        }

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        """Atomically restore metrics state from snapshot."""
        self.active_count = snapshot["active_count"]
        self.waiting_count = snapshot["waiting_count"]
        self.crossing_count = snapshot["crossing_count"]
        self.arrived_count = snapshot["arrived_count"]
        self.crossings_started = snapshot["crossings_started"]
        self.crossings_completed = snapshot["crossings_completed"]
        self.total_waiting_time_s = snapshot["total_waiting_time_s"]
        self.pedestrian_vehicle_conflicts = snapshot["pedestrian_vehicle_conflicts"]
        self.pedestrian_near_misses = snapshot["pedestrian_near_misses"]
        self.pedestrian_collisions = snapshot["pedestrian_collisions"]

    def reset(self) -> None:
        """Reset all counters and metrics to zero."""
        self.active_count = 0
        self.waiting_count = 0
        self.crossing_count = 0
        self.arrived_count = 0
        self.crossings_started = 0
        self.crossings_completed = 0
        self.total_waiting_time_s = 0.0
        self.pedestrian_vehicle_conflicts = 0
        self.pedestrian_near_misses = 0
        self.pedestrian_collisions = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to dictionary."""
        return {
            "active_count": self.active_count,
            "active_pedestrians": self.active_count,
            "waiting_count": self.waiting_count,
            "waiting_pedestrians": self.waiting_count,
            "crossing_count": self.crossing_count,
            "arrived_count": self.arrived_count,
            "crossings_started": self.crossings_started,
            "crossings_completed": self.crossings_completed,
            "total_waiting_time_s": round(self.total_waiting_time_s, 3),
            "pedestrian_vehicle_conflicts": self.pedestrian_vehicle_conflicts,
            "pedestrian_near_misses": self.pedestrian_near_misses,
            "pedestrian_collisions": self.pedestrian_collisions,
        }
