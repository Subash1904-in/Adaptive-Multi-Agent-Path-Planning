"""Decision policy interface and deterministic rule-based implementation."""

from __future__ import annotations

import time
from typing import Protocol, Sequence, runtime_checkable

from apps.core.decision.config import DecisionConfig
from apps.core.decision.exceptions import InvalidCandidateError
from apps.core.decision.models import (
    CandidateRoute,
    CandidateScore,
    DecisionContext,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionResult,
)
from apps.core.decision.scoring import CandidateScorer


@runtime_checkable
class DecisionPolicy(Protocol):
    """Protocol defining the pluggable interface for local autonomous agent decision policies."""

    def evaluate(
        self,
        context: DecisionContext,
        candidates: Sequence[CandidateRoute],
    ) -> DecisionResult:
        """Evaluate a sequence of candidate routes against an agent's local decision context."""
        ...


class RuleBasedDecisionPolicy:
    """Deterministic, rule-based baseline decision policy.

    Evaluates candidates using configurable multi-objective weights, strictly enforces
    hard safety constraints (closures, emergency corridors), checks observation confidence,
    applies stability hysteresis bonuses, and emits structured decision outcomes.
    """

    def __init__(self, config: DecisionConfig) -> None:
        self.config = config
        self.scorer = CandidateScorer(config)

    def evaluate(
        self,
        context: DecisionContext,
        candidates: Sequence[CandidateRoute],
    ) -> DecisionResult:
        """Evaluate candidates deterministically and produce an authoritative DecisionResult.

        Execution pipeline:
        1. Validate candidate list (cardinality, uniqueness).
        2. Score candidates and evaluate hard constraints.
        3. Reject immediately if all candidates violate hard constraints.
        4. Check observation confidence threshold on top candidate.
        5. Evaluate score improvement over current route (hysteresis).
        6. Return typed DecisionResult with explicit rationale.
        """
        start_time_ns = time.perf_counter_ns()
        dec_id = (
            f"dec_{context.agent_id}_{int(context.current_time_s * 1000):d}_{len(candidates)}"
        )

        if not candidates:
            return DecisionResult(
                decision_id=dec_id,
                agent_id=context.agent_id,
                timestamp_s=context.current_time_s,
                outcome=DecisionOutcome.DEFER,
                selected_candidate_id=None,
                reason_code=DecisionReasonCode.NO_VIABLE_CANDIDATE,
                reason="No candidate routes provided for evaluation.",
                candidate_scores={},
                selected_candidate=None,
                execution_time_ms=0.0,
            )

        # Validate duplicate IDs and max candidates
        seen_ids = set()
        for c in candidates:
            if c.candidate_id in seen_ids:
                raise InvalidCandidateError(
                    f"Duplicate candidate_id '{c.candidate_id}' in candidates.",
                    candidate_id=c.candidate_id,
                )
            seen_ids.add(c.candidate_id)

        eval_candidates = candidates[: self.config.max_candidates_per_evaluation]

        # Score all candidates
        scores: dict[str, CandidateScore] = {}
        for c in eval_candidates:
            scores[c.candidate_id] = self.scorer.score_candidate(c, context)

        # Rank candidates deterministically
        ranked = self.scorer.rank_candidates(eval_candidates, scores)

        # Check if all candidates violate hard constraints
        feasible_candidates = [
            c for c in ranked if not scores[c.candidate_id].hard_constraint_violated
        ]
        if not feasible_candidates:
            elapsed_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000.0
            return DecisionResult(
                decision_id=dec_id,
                agent_id=context.agent_id,
                timestamp_s=context.current_time_s,
                outcome=DecisionOutcome.REJECT,
                selected_candidate_id=None,
                reason_code=DecisionReasonCode.HARD_CONSTRAINT_VIOLATION,
                reason="All evaluated candidate routes violate hard safety constraints.",
                candidate_scores=scores,
                selected_candidate=None,
                execution_time_ms=elapsed_ms,
                diagnostics={"violated_count": len(eval_candidates)},
            )

        best_cand = feasible_candidates[0]
        best_score = scores[best_cand.candidate_id]

        # Check confidence threshold
        if best_cand.confidence < self.config.min_confidence_threshold:
            elapsed_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000.0
            return DecisionResult(
                decision_id=dec_id,
                agent_id=context.agent_id,
                timestamp_s=context.current_time_s,
                outcome=DecisionOutcome.DEFER,
                selected_candidate_id=best_cand.candidate_id,
                reason_code=DecisionReasonCode.LOW_CONFIDENCE,
                reason=(
                    f"Top candidate confidence {best_cand.confidence:.2f} is below "
                    f"minimum threshold {self.config.min_confidence_threshold:.2f}."
                ),
                candidate_scores=scores,
                selected_candidate=best_cand,
                execution_time_ms=elapsed_ms,
            )

        # If best candidate is the current route, retain it
        if best_cand.is_current_route:
            elapsed_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000.0
            return DecisionResult(
                decision_id=dec_id,
                agent_id=context.agent_id,
                timestamp_s=context.current_time_s,
                outcome=DecisionOutcome.ACCEPT,
                selected_candidate_id=best_cand.candidate_id,
                reason_code=DecisionReasonCode.CURRENT_ROUTE_OPTIMAL,
                reason="Current route remains optimal.",
                candidate_scores=scores,
                selected_candidate=best_cand,
                execution_time_ms=elapsed_ms,
            )

        # If best candidate is an alternative, compare against current route if viable
        current_cand = next((c for c in eval_candidates if c.is_current_route), None)
        is_cur_viable = (
            current_cand is not None
            and not scores[current_cand.candidate_id].hard_constraint_violated
        )
        if is_cur_viable and current_cand is not None:
            cur_score = scores[current_cand.candidate_id].raw_score
            improvement = best_score.raw_score - cur_score
            if improvement < self.config.min_score_improvement:
                elapsed_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000.0
                return DecisionResult(
                    decision_id=dec_id,
                    agent_id=context.agent_id,
                    timestamp_s=context.current_time_s,
                    outcome=DecisionOutcome.DEFER,
                    selected_candidate_id=current_cand.candidate_id,
                    reason_code=DecisionReasonCode.INSUFFICIENT_BENEFIT,
                    reason=(
                        f"Candidate improvement {improvement:.4f} is below "
                        f"minimum required {self.config.min_score_improvement:.4f}."
                    ),
                    candidate_scores=scores,
                    selected_candidate=current_cand,
                    execution_time_ms=elapsed_ms,
                    diagnostics={"score_improvement": improvement},
                )

        # Accept the improved alternative candidate route
        elapsed_ms = (time.perf_counter_ns() - start_time_ns) / 1_000_000.0
        return DecisionResult(
            decision_id=dec_id,
            agent_id=context.agent_id,
            timestamp_s=context.current_time_s,
            outcome=DecisionOutcome.ACCEPT,
            selected_candidate_id=best_cand.candidate_id,
            reason_code=DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED,
            reason=(
                f"Accepted improved candidate route '{best_cand.candidate_id}' "
                f"with score {best_score.raw_score:.4f}."
            ),
            candidate_scores=scores,
            selected_candidate=best_cand,
            execution_time_ms=elapsed_ms,
        )
