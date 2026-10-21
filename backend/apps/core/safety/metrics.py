"""Deterministic safety metrics collection and rollback state preservation."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SafetyMetrics:
    """Cumulative and point-in-time safety metrics counters.

    Attributes:
        pair_checks: Total vehicle pairs evaluated for collision risk.
        potential_collisions: Total conflict pairs classified CAUTION, HIGH_RISK, or IMMINENT.
        actual_collisions: Total pairs experiencing physical geometric bounding box overlap.
        near_misses: Total pairs within near-miss threshold without geometric overlap.
        ttc_violations: Total pairs violating caution TTC threshold.
        separation_violations: Total pairs violating safe separation distance.
        gentle_brakes: Total gentle deceleration overrides commanded.
        strong_brakes: Total strong deceleration overrides commanded.
        emergency_brakes: Total emergency braking overrides commanded.
        control_overrides: Total safety control overrides applied to vehicle agents.
        conflicts_resolved: Total conflicts where safe deceleration was commanded.
        unresolved_conflicts: Total conflicts resulting in actual geometric overlap.
        min_separation_observed: Minimum boundary separation observed across all runs in meters.
        min_ttc_observed: Minimum non-zero TTC observed across all runs in seconds.
    """

    pair_checks: int = 0
    potential_collisions: int = 0
    actual_collisions: int = 0
    near_misses: int = 0
    ttc_violations: int = 0
    separation_violations: int = 0
    gentle_brakes: int = 0
    strong_brakes: int = 0
    emergency_brakes: int = 0
    control_overrides: int = 0
    conflicts_resolved: int = 0
    unresolved_conflicts: int = 0
    min_separation_observed: Optional[float] = None
    min_ttc_observed: Optional[float] = None

    def record_pair_observation(
        self,
        separation_m: float,
        ttc_s: Optional[float],
        is_overlap: bool,
        is_near_miss: bool,
        is_separation_violated: bool,
        is_ttc_violated: bool,
        is_potential_collision: bool,
    ) -> None:
        """Record observations from a single pairwise evaluation."""
        self.pair_checks += 1

        if is_overlap:
            self.actual_collisions += 1
            self.unresolved_conflicts += 1
        elif is_near_miss:
            self.near_misses += 1

        if is_potential_collision:
            self.potential_collisions += 1

        if is_separation_violated:
            self.separation_violations += 1

        if is_ttc_violated:
            self.ttc_violations += 1

        # Track minimum observed separation
        if self.min_separation_observed is None or separation_m < self.min_separation_observed:
            self.min_separation_observed = separation_m

        # Track minimum observed TTC
        if ttc_s is not None and ttc_s >= 0.0:
            if self.min_ttc_observed is None or ttc_s < self.min_ttc_observed:
                self.min_ttc_observed = ttc_s

    def record_override_action(self, action_type_val: str) -> None:
        """Record a commanded safety control override."""
        self.control_overrides += 1
        if action_type_val == "gentle_brake":
            self.gentle_brakes += 1
            self.conflicts_resolved += 1
        elif action_type_val == "strong_brake":
            self.strong_brakes += 1
            self.conflicts_resolved += 1
        elif action_type_val == "emergency_brake":
            self.emergency_brakes += 1
            self.conflicts_resolved += 1

    def capture_state(self) -> dict[str, Any]:
        """Capture an exact point-in-time snapshot for atomic rollback."""
        return {
            "pair_checks": self.pair_checks,
            "potential_collisions": self.potential_collisions,
            "actual_collisions": self.actual_collisions,
            "near_misses": self.near_misses,
            "ttc_violations": self.ttc_violations,
            "separation_violations": self.separation_violations,
            "gentle_brakes": self.gentle_brakes,
            "strong_brakes": self.strong_brakes,
            "emergency_brakes": self.emergency_brakes,
            "control_overrides": self.control_overrides,
            "conflicts_resolved": self.conflicts_resolved,
            "unresolved_conflicts": self.unresolved_conflicts,
            "min_separation_observed": self.min_separation_observed,
            "min_ttc_observed": self.min_ttc_observed,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore metrics counters from a captured rollback snapshot."""
        self.pair_checks = state["pair_checks"]
        self.potential_collisions = state["potential_collisions"]
        self.actual_collisions = state["actual_collisions"]
        self.near_misses = state["near_misses"]
        self.ttc_violations = state["ttc_violations"]
        self.separation_violations = state["separation_violations"]
        self.gentle_brakes = state["gentle_brakes"]
        self.strong_brakes = state["strong_brakes"]
        self.emergency_brakes = state["emergency_brakes"]
        self.control_overrides = state["control_overrides"]
        self.conflicts_resolved = state["conflicts_resolved"]
        self.unresolved_conflicts = state["unresolved_conflicts"]
        self.min_separation_observed = state["min_separation_observed"]
        self.min_ttc_observed = state["min_ttc_observed"]

    def reset(self) -> None:
        """Reset all metric counters to zero."""
        self.pair_checks = 0
        self.potential_collisions = 0
        self.actual_collisions = 0
        self.near_misses = 0
        self.ttc_violations = 0
        self.separation_violations = 0
        self.gentle_brakes = 0
        self.strong_brakes = 0
        self.emergency_brakes = 0
        self.control_overrides = 0
        self.conflicts_resolved = 0
        self.unresolved_conflicts = 0
        self.min_separation_observed = None
        self.min_ttc_observed = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to a JSON-compatible dictionary."""
        return {
            "pair_checks": self.pair_checks,
            "potential_collisions": self.potential_collisions,
            "actual_collisions": self.actual_collisions,
            "near_misses": self.near_misses,
            "ttc_violations": self.ttc_violations,
            "separation_violations": self.separation_violations,
            "gentle_brakes": self.gentle_brakes,
            "strong_brakes": self.strong_brakes,
            "emergency_brakes": self.emergency_brakes,
            "control_overrides": self.control_overrides,
            "conflicts_resolved": self.conflicts_resolved,
            "unresolved_conflicts": self.unresolved_conflicts,
            "min_separation_observed": (
                round(self.min_separation_observed, 4)
                if self.min_separation_observed is not None
                else None
            ),
            "min_ttc_observed": (
                round(self.min_ttc_observed, 4) if self.min_ttc_observed is not None else None
            ),
        }
