"""Deterministic candidate route scoring, normalization, and tie-breaking."""

from __future__ import annotations

from typing import Sequence

from apps.core.decision.config import DecisionConfig
from apps.core.decision.features import (
    compute_stability_bonus,
    evaluate_hard_constraints,
    normalize_congestion,
    normalize_hazard,
    normalize_travel_time,
)
from apps.core.decision.models import CandidateRoute, CandidateScore, DecisionContext


class CandidateScorer:
    """Evaluates and scores candidate routes against decision configurations."""

    def __init__(self, config: DecisionConfig) -> None:
        self.config = config

    def score_candidate(
        self,
        candidate: CandidateRoute,
        context: DecisionContext,
    ) -> CandidateScore:
        """Score an individual candidate route deterministically.

        Formula:
            S(c) = -w_t * T_norm - w_g * G_norm - w_h * H_norm + w_c * C + w_r * R

        Hard constraints:
            If a candidate violates a hard constraint (e.g. road closure or emergency corridor),
            raw_score is set to -Infinity and hard_constraint_violated is set to True.
        """
        is_violated, reason = evaluate_hard_constraints(candidate, context)
        t_norm = normalize_travel_time(
            candidate.estimated_travel_time_s, self.config.max_travel_time_norm_s
        )
        g_norm = normalize_congestion(
            candidate.congestion_cost, self.config.max_congestion_cost_norm
        )
        h_norm = normalize_hazard(candidate.hazard_penalty, self.config.max_hazard_cost_norm)
        confidence = max(0.0, min(1.0, candidate.confidence))
        stability = compute_stability_bonus(candidate)

        if is_violated:
            raw_score = -float("inf")
        else:
            raw_score = (
                -self.config.weight_travel_time * t_norm
                - self.config.weight_congestion * g_norm
                - self.config.weight_hazard * h_norm
                + self.config.weight_confidence * confidence
                + self.config.weight_stability * stability
            )

        return CandidateScore(
            candidate_id=candidate.candidate_id,
            raw_score=raw_score,
            normalized_travel_time=t_norm,
            normalized_congestion=g_norm,
            normalized_hazard=h_norm,
            confidence=confidence,
            stability_bonus=stability,
            hard_constraint_violated=is_violated,
            violation_reason=reason,
        )

    def rank_candidates(
        self,
        candidates: Sequence[CandidateRoute],
        scores: dict[str, CandidateScore],
    ) -> list[CandidateRoute]:
        """Rank candidate routes deterministically based on score, confidence, and tie-breakers.

        Tie-breaking precedence:
        1. Higher raw score (descending)
        2. Higher confidence (descending)
        3. Shorter estimated travel time (ascending)
        4. Candidate ID string lexicographical order (ascending)
        """

        def sort_key(c: CandidateRoute) -> tuple[float, float, float, str]:
            score = scores.get(c.candidate_id)
            score_val = score.raw_score if score is not None else -float("inf")
            # Invert for descending order:
            # -score_val: smaller is better (so higher score comes first)
            # -c.confidence: smaller is better (so higher confidence comes first)
            return (
                -score_val,
                -c.confidence,
                c.estimated_travel_time_s,
                c.candidate_id,
            )

        return sorted(candidates, key=sort_key)
