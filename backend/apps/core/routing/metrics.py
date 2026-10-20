"""Deterministic metrics and counters for adaptive rerouting and dynamic costs."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptiveRoutingMetrics:
    """Deterministic telemetry counters for adaptive rerouting evaluations and replacements.

    All metrics are exact simulation-time counters; no wall-clock timing is included.
    """

    evaluations_total: int = 0
    candidate_routes_computed: int = 0
    reroutes_accepted: int = 0
    reroutes_rejected: int = 0
    cooldown_suppressions: int = 0
    insufficient_benefit_suppressions: int = 0
    no_route_outcomes: int = 0
    closure_restrictions_applied: int = 0
    congestion_multipliers_applied: int = 0
    hazard_penalties_applied: int = 0
    cost_savings_total: float = 0.0
    route_changes_by_vehicle: dict[str, int] = field(default_factory=dict)

    @property
    def accepted_reroutes(self) -> int:
        """Alias for reroutes_accepted."""
        return self.reroutes_accepted

    @property
    def rejected_reroutes(self) -> int:
        """Alias for reroutes_rejected."""
        return self.reroutes_rejected

    def record_evaluation(self) -> None:
        """Increment total evaluation counter."""
        self.evaluations_total += 1

    def record_candidate_computed(self) -> None:
        """Increment count of candidate shortest-path calculations."""
        self.candidate_routes_computed += 1

    def record_accepted(self, vehicle_id: str, cost_saving: float = 0.0) -> None:
        """Record an accepted and committed active route replacement."""
        self.reroutes_accepted += 1
        if cost_saving > 0.0:
            self.cost_savings_total += cost_saving
        self.route_changes_by_vehicle[vehicle_id] = (
            self.route_changes_by_vehicle.get(vehicle_id, 0) + 1
        )

    def record_rejected(self, vehicle_id: str) -> None:
        """Record a rejected candidate route."""
        self.reroutes_rejected += 1

    def record_cooldown_suppression(self) -> None:
        """Record an evaluation skipped due to active cooldown timer."""
        self.cooldown_suppressions += 1

    def record_insufficient_benefit(self) -> None:
        """Record candidate route rejected because improvement was below threshold."""
        self.insufficient_benefit_suppressions += 1

    def record_no_route(self) -> None:
        """Record an evaluation where no traversable alternative path existed."""
        self.no_route_outcomes += 1

    def record_closure_applied(self) -> None:
        """Record an edge excluded from routing due to active closure belief."""
        self.closure_restrictions_applied += 1

    def record_congestion_applied(self) -> None:
        """Record an edge cost adjusted by a congestion multiplier."""
        self.congestion_multipliers_applied += 1

    def record_hazard_applied(self) -> None:
        """Record an edge cost adjusted by a hazard penalty."""
        self.hazard_penalties_applied += 1

    def reset(self) -> None:
        """Reset all counters to zero."""
        self.evaluations_total = 0
        self.candidate_routes_computed = 0
        self.reroutes_accepted = 0
        self.reroutes_rejected = 0
        self.cooldown_suppressions = 0
        self.insufficient_benefit_suppressions = 0
        self.no_route_outcomes = 0
        self.closure_restrictions_applied = 0
        self.congestion_multipliers_applied = 0
        self.hazard_penalties_applied = 0
        self.cost_savings_total = 0.0
        self.route_changes_by_vehicle.clear()

    def clone(self) -> "AdaptiveRoutingMetrics":
        """Produce an independent copy of current metrics for snapshotting and rollback."""
        return AdaptiveRoutingMetrics(
            evaluations_total=self.evaluations_total,
            candidate_routes_computed=self.candidate_routes_computed,
            reroutes_accepted=self.reroutes_accepted,
            reroutes_rejected=self.reroutes_rejected,
            cooldown_suppressions=self.cooldown_suppressions,
            insufficient_benefit_suppressions=self.insufficient_benefit_suppressions,
            no_route_outcomes=self.no_route_outcomes,
            closure_restrictions_applied=self.closure_restrictions_applied,
            congestion_multipliers_applied=self.congestion_multipliers_applied,
            hazard_penalties_applied=self.hazard_penalties_applied,
            cost_savings_total=self.cost_savings_total,
            route_changes_by_vehicle=dict(self.route_changes_by_vehicle),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-compatible dictionary."""
        return {
            "evaluations_total": self.evaluations_total,
            "candidate_routes_computed": self.candidate_routes_computed,
            "reroutes_accepted": self.reroutes_accepted,
            "reroutes_rejected": self.reroutes_rejected,
            "cooldown_suppressions": self.cooldown_suppressions,
            "insufficient_benefit_suppressions": self.insufficient_benefit_suppressions,
            "no_route_outcomes": self.no_route_outcomes,
            "closure_restrictions_applied": self.closure_restrictions_applied,
            "congestion_multipliers_applied": self.congestion_multipliers_applied,
            "hazard_penalties_applied": self.hazard_penalties_applied,
            "cost_savings_total": round(self.cost_savings_total, 4),
            "route_changes_by_vehicle": dict(self.route_changes_by_vehicle),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptiveRoutingMetrics":
        """Reconstruct metrics from dictionary."""
        return cls(
            evaluations_total=int(data.get("evaluations_total", 0)),
            candidate_routes_computed=int(data.get("candidate_routes_computed", 0)),
            reroutes_accepted=int(data.get("reroutes_accepted", 0)),
            reroutes_rejected=int(data.get("reroutes_rejected", 0)),
            cooldown_suppressions=int(data.get("cooldown_suppressions", 0)),
            insufficient_benefit_suppressions=int(data.get("insufficient_benefit_suppressions", 0)),
            no_route_outcomes=int(data.get("no_route_outcomes", 0)),
            closure_restrictions_applied=int(data.get("closure_restrictions_applied", 0)),
            congestion_multipliers_applied=int(data.get("congestion_multipliers_applied", 0)),
            hazard_penalties_applied=int(data.get("hazard_penalties_applied", 0)),
            cost_savings_total=float(data.get("cost_savings_total", 0.0)),
            route_changes_by_vehicle=dict(data.get("route_changes_by_vehicle", {})),
        )
