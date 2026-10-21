"""Structured telemetry and aggregate metrics for decision policy evaluation."""

from __future__ import annotations

from typing import Any

from apps.core.decision.models import DecisionOutcome, DecisionReasonCode, DecisionResult


class DecisionMetrics:
    """Accumulates point-in-time and aggregate metrics for decision policy evaluations."""

    def __init__(self) -> None:
        self.decisions_evaluated: int = 0
        self.candidates_evaluated: int = 0
        self.candidates_rejected: int = 0
        self.decisions_accepted: int = 0
        self.decisions_deferred: int = 0
        self.reevaluations_requested: int = 0
        self.low_confidence_decisions: int = 0
        self.hard_constraint_rejections: int = 0
        self.stale_suggestion_rejections: int = 0
        self.route_changes_accepted: int = 0
        self.route_changes_rejected: int = 0
        self.decision_errors: int = 0
        self.total_execution_time_ms: float = 0.0

    def record_decision(self, result: DecisionResult, applied: bool = False) -> None:
        """Record an evaluated decision result and its outcome."""
        self.decisions_evaluated += 1
        self.candidates_evaluated += len(result.candidate_scores)
        self.total_execution_time_ms += result.execution_time_ms

        if result.outcome == DecisionOutcome.ACCEPT:
            self.decisions_accepted += 1
            if applied and result.reason_code == DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED:
                self.route_changes_accepted += 1
        elif result.outcome == DecisionOutcome.DEFER:
            self.decisions_deferred += 1
            if result.reason_code == DecisionReasonCode.LOW_CONFIDENCE:
                self.low_confidence_decisions += 1
        elif result.outcome == DecisionOutcome.REEVALUATE:
            self.reevaluations_requested += 1
        elif result.outcome == DecisionOutcome.REJECT:
            self.candidates_rejected += len(result.candidate_scores)
            self.route_changes_rejected += 1
            if result.reason_code == DecisionReasonCode.HARD_CONSTRAINT_VIOLATION:
                self.hard_constraint_rejections += 1
            elif result.reason_code == DecisionReasonCode.STALE_INFORMATION:
                self.stale_suggestion_rejections += 1

    def record_error(self) -> None:
        """Record a decision policy evaluation error."""
        self.decision_errors += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a plain dictionary."""
        avg_latency = (
            self.total_execution_time_ms / self.decisions_evaluated
            if self.decisions_evaluated > 0
            else 0.0
        )
        return {
            "decisions_evaluated": self.decisions_evaluated,
            "candidates_evaluated": self.candidates_evaluated,
            "candidates_rejected": self.candidates_rejected,
            "decisions_accepted": self.decisions_accepted,
            "decisions_deferred": self.decisions_deferred,
            "reevaluations_requested": self.reevaluations_requested,
            "low_confidence_decisions": self.low_confidence_decisions,
            "hard_constraint_rejections": self.hard_constraint_rejections,
            "stale_suggestion_rejections": self.stale_suggestion_rejections,
            "route_changes_accepted": self.route_changes_accepted,
            "route_changes_rejected": self.route_changes_rejected,
            "decision_errors": self.decision_errors,
            "total_execution_time_ms": round(self.total_execution_time_ms, 3),
            "average_latency_ms": round(avg_latency, 3),
        }

    def capture_state(self) -> dict[str, Any]:
        """Capture an atomic snapshot of current metric counters for rollback."""
        return {
            "decisions_evaluated": self.decisions_evaluated,
            "candidates_evaluated": self.candidates_evaluated,
            "candidates_rejected": self.candidates_rejected,
            "decisions_accepted": self.decisions_accepted,
            "decisions_deferred": self.decisions_deferred,
            "reevaluations_requested": self.reevaluations_requested,
            "low_confidence_decisions": self.low_confidence_decisions,
            "hard_constraint_rejections": self.hard_constraint_rejections,
            "stale_suggestion_rejections": self.stale_suggestion_rejections,
            "route_changes_accepted": self.route_changes_accepted,
            "route_changes_rejected": self.route_changes_rejected,
            "decision_errors": self.decision_errors,
            "total_execution_time_ms": self.total_execution_time_ms,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore metric counters from an atomic rollback snapshot."""
        self.decisions_evaluated = state.get("decisions_evaluated", 0)
        self.candidates_evaluated = state.get("candidates_evaluated", 0)
        self.candidates_rejected = state.get("candidates_rejected", 0)
        self.decisions_accepted = state.get("decisions_accepted", 0)
        self.decisions_deferred = state.get("decisions_deferred", 0)
        self.reevaluations_requested = state.get("reevaluations_requested", 0)
        self.low_confidence_decisions = state.get("low_confidence_decisions", 0)
        self.hard_constraint_rejections = state.get("hard_constraint_rejections", 0)
        self.stale_suggestion_rejections = state.get("stale_suggestion_rejections", 0)
        self.route_changes_accepted = state.get("route_changes_accepted", 0)
        self.route_changes_rejected = state.get("route_changes_rejected", 0)
        self.decision_errors = state.get("decision_errors", 0)
        self.total_execution_time_ms = state.get("total_execution_time_ms", 0.0)

    def reset(self) -> None:
        """Reset all counters to zero."""
        self.__init__()
