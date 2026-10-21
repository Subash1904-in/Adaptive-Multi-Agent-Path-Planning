"""Cumulative and point-in-time metrics tracking for the emergency priority subsystem."""

from dataclasses import dataclass
from typing import Any


@dataclass
class EmergencyMetrics:
    """Accumulated performance and operational counters for emergency priority operations."""

    requests_created: int = 0
    requests_accepted: int = 0
    requests_denied: int = 0
    requests_cancelled: int = 0
    requests_completed: int = 0
    requests_expired: int = 0

    corridors_created: int = 0
    corridors_updated: int = 0
    corridor_conflicts: int = 0

    yield_requests_issued: int = 0
    yield_requests_acknowledged: int = 0

    signal_priority_grants: int = 0
    signal_priority_denials: int = 0

    safety_interventions: int = 0
    stale_messages_ignored: int = 0

    # Point-in-time active gauges
    active_emergency_vehicles: int = 0
    active_corridors: int = 0

    # Time tracking
    total_emergency_travel_time_s: float = 0.0
    total_corridor_delay_s: float = 0.0

    def capture_state(self) -> dict[str, Any]:
        """Capture deep copy of metrics state for atomic rollback."""
        return {
            "requests_created": self.requests_created,
            "requests_accepted": self.requests_accepted,
            "requests_denied": self.requests_denied,
            "requests_cancelled": self.requests_cancelled,
            "requests_completed": self.requests_completed,
            "requests_expired": self.requests_expired,
            "corridors_created": self.corridors_created,
            "corridors_updated": self.corridors_updated,
            "corridor_conflicts": self.corridor_conflicts,
            "yield_requests_issued": self.yield_requests_issued,
            "yield_requests_acknowledged": self.yield_requests_acknowledged,
            "signal_priority_grants": self.signal_priority_grants,
            "signal_priority_denials": self.signal_priority_denials,
            "safety_interventions": self.safety_interventions,
            "stale_messages_ignored": self.stale_messages_ignored,
            "active_emergency_vehicles": self.active_emergency_vehicles,
            "active_corridors": self.active_corridors,
            "total_emergency_travel_time_s": self.total_emergency_travel_time_s,
            "total_corridor_delay_s": self.total_corridor_delay_s,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore metrics state from snapshot during rollback."""
        self.requests_created = state["requests_created"]
        self.requests_accepted = state["requests_accepted"]
        self.requests_denied = state["requests_denied"]
        self.requests_cancelled = state["requests_cancelled"]
        self.requests_completed = state["requests_completed"]
        self.requests_expired = state["requests_expired"]
        self.corridors_created = state["corridors_created"]
        self.corridors_updated = state["corridors_updated"]
        self.corridor_conflicts = state["corridor_conflicts"]
        self.yield_requests_issued = state["yield_requests_issued"]
        self.yield_requests_acknowledged = state["yield_requests_acknowledged"]
        self.signal_priority_grants = state["signal_priority_grants"]
        self.signal_priority_denials = state["signal_priority_denials"]
        self.safety_interventions = state["safety_interventions"]
        self.stale_messages_ignored = state["stale_messages_ignored"]
        self.active_emergency_vehicles = state["active_emergency_vehicles"]
        self.active_corridors = state["active_corridors"]
        self.total_emergency_travel_time_s = state["total_emergency_travel_time_s"]
        self.total_corridor_delay_s = state["total_corridor_delay_s"]

    def reset(self) -> None:
        """Reset all metrics to initial zero values."""
        self.requests_created = 0
        self.requests_accepted = 0
        self.requests_denied = 0
        self.requests_cancelled = 0
        self.requests_completed = 0
        self.requests_expired = 0
        self.corridors_created = 0
        self.corridors_updated = 0
        self.corridor_conflicts = 0
        self.yield_requests_issued = 0
        self.yield_requests_acknowledged = 0
        self.signal_priority_grants = 0
        self.signal_priority_denials = 0
        self.safety_interventions = 0
        self.stale_messages_ignored = 0
        self.active_emergency_vehicles = 0
        self.active_corridors = 0
        self.total_emergency_travel_time_s = 0.0
        self.total_corridor_delay_s = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to a JSON-compatible dictionary."""
        return {
            "requests_created": self.requests_created,
            "requests_accepted": self.requests_accepted,
            "requests_denied": self.requests_denied,
            "requests_cancelled": self.requests_cancelled,
            "requests_completed": self.requests_completed,
            "requests_expired": self.requests_expired,
            "corridors_created": self.corridors_created,
            "corridors_updated": self.corridors_updated,
            "corridor_conflicts": self.corridor_conflicts,
            "yield_requests_issued": self.yield_requests_issued,
            "yield_requests_acknowledged": self.yield_requests_acknowledged,
            "signal_priority_grants": self.signal_priority_grants,
            "signal_priority_denials": self.signal_priority_denials,
            "safety_interventions": self.safety_interventions,
            "stale_messages_ignored": self.stale_messages_ignored,
            "active_emergency_vehicles": self.active_emergency_vehicles,
            "active_corridors": self.active_corridors,
            "total_emergency_travel_time_s": round(self.total_emergency_travel_time_s, 4),
            "total_corridor_delay_s": round(self.total_corridor_delay_s, 4),
        }
