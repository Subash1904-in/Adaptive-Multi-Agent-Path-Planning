"""Unit tests for Phase 19 feature extraction, normalization, and candidate scoring."""

import math

from apps.core.decision.config import DecisionConfig
from apps.core.decision.features import (
    compute_stability_bonus,
    evaluate_hard_constraints,
    normalize_congestion,
    normalize_hazard,
    normalize_travel_time,
)
from apps.core.decision.models import CandidateRoute, DecisionContext
from apps.core.decision.scoring import CandidateScorer


def test_feature_normalization():
    """Verify normalization functions clamp values cleanly between 0.0 and 1.0."""
    assert normalize_travel_time(0.0, 100.0) == 0.0
    assert normalize_travel_time(50.0, 100.0) == 0.5
    assert normalize_travel_time(150.0, 100.0) == 1.0
    assert normalize_travel_time(-10.0, 100.0) == 0.0

    assert normalize_congestion(20.0, 50.0) == 0.4
    assert normalize_congestion(60.0, 50.0) == 1.0

    assert normalize_hazard(15.0, 30.0) == 0.5
    assert normalize_hazard(40.0, 30.0) == 1.0


def test_stability_bonus():
    """Verify stability bonus identifies active route."""
    c_cur = CandidateRoute(
        candidate_id="cur",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=10.0,
        is_current_route=True,
    )
    c_alt = CandidateRoute(
        candidate_id="alt",
        node_ids=("n1", "n3", "n2"),
        edge_ids=("e2", "e3"),
        estimated_travel_time_s=8.0,
        is_current_route=False,
    )
    assert compute_stability_bonus(c_cur) == 1.0
    assert compute_stability_bonus(c_alt) == 0.0


def test_hard_constraint_evaluation():
    """Verify detection of road closures and emergency corridor violations."""
    ctx = DecisionContext(
        agent_id="veh_1",
        current_time_s=0.0,
        destination_node_id="dest",
        known_closed_edges=frozenset({"edge_closed"}),
        emergency_corridor_edges=frozenset({"edge_corridor"}),
    )

    c_clean = CandidateRoute(
        candidate_id="clean",
        node_ids=("n1", "n2"),
        edge_ids=("edge_open",),
        estimated_travel_time_s=10.0,
    )
    is_viol, reason = evaluate_hard_constraints(c_clean, ctx)
    assert not is_viol
    assert reason is None

    c_closed = CandidateRoute(
        candidate_id="closed",
        node_ids=("n1", "n2"),
        edge_ids=("edge_closed",),
        estimated_travel_time_s=10.0,
    )
    is_viol, reason = evaluate_hard_constraints(c_closed, ctx)
    assert is_viol
    assert "known closed edge" in str(reason)

    c_corr = CandidateRoute(
        candidate_id="corridor",
        node_ids=("n1", "n2"),
        edge_ids=("edge_corridor",),
        estimated_travel_time_s=10.0,
    )
    is_viol, reason = evaluate_hard_constraints(c_corr, ctx)
    assert is_viol
    assert "emergency corridor edge" in str(reason)


def test_candidate_scorer_formula():
    """Verify candidate scoring formula adheres to configured weights."""
    cfg = DecisionConfig(
        weight_travel_time=1.0,
        weight_congestion=0.5,
        weight_hazard=0.8,
        weight_confidence=0.4,
        weight_stability=0.2,
        max_travel_time_norm_s=100.0,
        max_congestion_cost_norm=50.0,
        max_hazard_cost_norm=50.0,
    )
    scorer = CandidateScorer(cfg)
    ctx = DecisionContext(
        agent_id="veh_1",
        current_time_s=0.0,
        destination_node_id="dest",
    )

    cand = CandidateRoute(
        candidate_id="c1",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=50.0,  # t_norm = 0.5
        congestion_cost=10.0,  # g_norm = 0.2
        hazard_penalty=5.0,  # h_norm = 0.1
        confidence=0.8,
        is_current_route=True,  # stability = 1.0
    )

    score = scorer.score_candidate(cand, ctx)
    # Expected: -1.0*(0.5) - 0.5*(0.2) - 0.8*(0.1) + 0.4*(0.8) + 0.2*(1.0)
    # = -0.5 - 0.1 - 0.08 + 0.32 + 0.2 = -0.16
    assert math.isclose(score.raw_score, -0.16, abs_tol=1e-5)
    assert not score.hard_constraint_violated


def test_candidate_scorer_hard_constraint_violation():
    """Verify hard constraint violation results in -inf score."""
    cfg = DecisionConfig()
    scorer = CandidateScorer(cfg)
    ctx = DecisionContext(
        agent_id="veh_1",
        current_time_s=0.0,
        destination_node_id="dest",
        known_closed_edges=frozenset({"e_blocked"}),
    )

    cand = CandidateRoute(
        candidate_id="c_blocked",
        node_ids=("n1", "n2"),
        edge_ids=("e_blocked",),
        estimated_travel_time_s=5.0,
    )
    score = scorer.score_candidate(cand, ctx)
    assert math.isinf(score.raw_score)
    assert score.raw_score < 0
    assert score.hard_constraint_violated is True
    assert score.violation_reason is not None


def test_deterministic_ranking_and_tie_breaking():
    """Verify deterministic ranking order and multi-tier tie-breaking."""
    cfg = DecisionConfig()
    scorer = CandidateScorer(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="d")

    # c1: higher score
    c1 = CandidateRoute(
        candidate_id="c1",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=20.0,
        confidence=0.9,
    )
    # c2: lower score (longer travel time and lower confidence)
    c2 = CandidateRoute(
        candidate_id="c2",
        node_ids=("n1", "n2"),
        edge_ids=("e2",),
        estimated_travel_time_s=150.0,
        confidence=0.5,
    )
    # c3: identical score to c1, but lower confidence
    c3 = CandidateRoute(
        candidate_id="c3",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=20.0,
        confidence=0.5,
    )
    # c4: identical score and confidence to c1, but candidate_id "c0"
    c4 = CandidateRoute(
        candidate_id="c0",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=20.0,
        confidence=0.9,
    )

    candidates = [c2, c1, c3, c4]
    scores = {c.candidate_id: scorer.score_candidate(c, ctx) for c in candidates}

    ranked = scorer.rank_candidates(candidates, scores)
    # c0 and c1 have identical score & confidence; "c0" < "c1" lexicographically.
    # Therefore order: c0, c1, c3 (lower conf), c2 (lower score)
    ranked_ids = [c.candidate_id for c in ranked]
    assert ranked_ids == ["c0", "c1", "c3", "c2"]

    # Verify candidate input permutation invariance
    permuted = [c1, c3, c2, c4]
    ranked_perm = scorer.rank_candidates(permuted, scores)
    assert [c.candidate_id for c in ranked_perm] == ["c0", "c1", "c3", "c2"]
