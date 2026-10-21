"""Central manager orchestrating decision policies, history, and metrics."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from apps.core.decision.config import DecisionConfig
from apps.core.decision.metrics import DecisionMetrics
from apps.core.decision.models import (
    CandidateRoute,
    DecisionContext,
    DecisionRecord,
    DecisionResult,
)
from apps.core.decision.policy import DecisionPolicy, RuleBasedDecisionPolicy


class DecisionManager:
    """Coordinates local agent decision evaluations, maintains audit logs, and tracks metrics."""

    def __init__(
        self,
        config: Optional[DecisionConfig] = None,
        policy: Optional[DecisionPolicy] = None,
    ) -> None:
        self.config: DecisionConfig = config or DecisionConfig()
        self.policy: DecisionPolicy = policy or RuleBasedDecisionPolicy(self.config)
        self.metrics: DecisionMetrics = DecisionMetrics()

        self._last_decisions: dict[str, DecisionResult] = {}
        self._decision_history: dict[str, list[DecisionResult]] = {}
        self._records: list[DecisionRecord] = []

    def evaluate_decision(
        self,
        context: DecisionContext,
        candidates: Sequence[CandidateRoute],
        applied: bool = False,
    ) -> DecisionResult:
        """Evaluate candidate routes for an agent, updating history and telemetry.

        Args:
            context: Agent-isolated decision context.
            candidates: Sequence of candidate routes for evaluation.
            applied: Whether an accepted route change will be immediately applied.

        Returns:
            Authoritative DecisionResult.
        """
        result = self.policy.evaluate(context, candidates)

        # Update manager state and metrics
        self._last_decisions[context.agent_id] = result
        self._decision_history.setdefault(context.agent_id, []).append(result)

        if self.config.log_decisions:
            rec = DecisionRecord(
                record_id=f"rec_{len(self._records):06d}",
                decision_id=result.decision_id,
                agent_id=result.agent_id,
                timestamp_s=result.timestamp_s,
                outcome=result.outcome,
                reason_code=result.reason_code,
                selected_candidate_id=result.selected_candidate_id,
                candidate_count=len(candidates),
                applied=applied,
            )
            self._records.append(rec)

        self.metrics.record_decision(result, applied=applied)
        return result

    def get_last_decision(self, agent_id: str) -> Optional[DecisionResult]:
        """Retrieve the most recent decision result for an agent."""
        return self._last_decisions.get(agent_id)

    def get_decision_history(self, agent_id: str) -> list[DecisionResult]:
        """Retrieve the full chronological decision history for an agent."""
        return list(self._decision_history.get(agent_id, []))

    def capture_state(self) -> dict[str, Any]:
        """Capture an atomic snapshot of decision manager state for engine rollback."""
        return {
            "metrics": self.metrics.capture_state(),
            "last_decisions": dict(self._last_decisions),
            "decision_history": {k: list(v) for k, v in self._decision_history.items()},
            "records": list(self._records),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore decision manager state from an atomic rollback snapshot."""
        if "metrics" in state:
            self.metrics.restore_state(state["metrics"])
        self._last_decisions = dict(state.get("last_decisions", {}))
        self._decision_history = {
            k: list(v) for k, v in state.get("decision_history", {}).items()
        }
        self._records = list(state.get("records", []))

    def reset(self) -> None:
        """Reset decision manager to initial state."""
        self.metrics.reset()
        self._last_decisions.clear()
        self._decision_history.clear()
        self._records.clear()
