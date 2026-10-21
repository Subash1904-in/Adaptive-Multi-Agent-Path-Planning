"""Unit tests for Phase 19 DecisionPolicy outcomes and decision rationales."""

import pytest

from apps.core.decision.config import DecisionConfig
from apps.core.decision.exceptions import InvalidCandidateError
from apps.core.decision.models import (
    CandidateRoute,
    DecisionContext,
    DecisionOutcome,
    DecisionReasonCode,
)
from apps.core.decision.policy import RuleBasedDecisionPolicy


def test_policy_empty_candidates():
    """Verify empty candidate list produces DEFER outcome with NO_VIABLE_CANDIDATE."""
    cfg = DecisionConfig()
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    res = policy.evaluate(ctx, [])
    assert res.outcome == DecisionOutcome.DEFER
    assert res.reason_code == DecisionReasonCode.NO_VIABLE_CANDIDATE
    assert res.selected_candidate_id is None


def test_policy_duplicate_candidates_error():
    """Verify duplicate candidate IDs raise InvalidCandidateError."""
    cfg = DecisionConfig()
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    c1 = CandidateRoute(
        candidate_id="dup_id",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=10.0,
    )
    c2 = CandidateRoute(
        candidate_id="dup_id",
        node_ids=("n1", "n3"),
        edge_ids=("e2",),
        estimated_travel_time_s=12.0,
    )

    with pytest.raises(InvalidCandidateError):
        policy.evaluate(ctx, [c1, c2])


def test_policy_all_candidates_violate_hard_constraints():
    """Verify REJECT outcome when all evaluated candidates violate hard safety constraints."""
    cfg = DecisionConfig()
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(
        agent_id="v1",
        current_time_s=0.0,
        destination_node_id="dest",
        known_closed_edges=frozenset({"e_closed"}),
    )

    c1 = CandidateRoute(
        candidate_id="c1",
        node_ids=("n1", "n2"),
        edge_ids=("e_closed",),
        estimated_travel_time_s=10.0,
    )
    res = policy.evaluate(ctx, [c1])
    assert res.outcome == DecisionOutcome.REJECT
    assert res.reason_code == DecisionReasonCode.HARD_CONSTRAINT_VIOLATION
    assert res.selected_candidate_id is None


def test_policy_low_confidence_deferral():
    """Verify DEFER outcome when top candidate confidence is below threshold."""
    cfg = DecisionConfig(min_confidence_threshold=0.7)
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    cand = CandidateRoute(
        candidate_id="cand_low_conf",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=10.0,
        confidence=0.5,
    )
    res = policy.evaluate(ctx, [cand])
    assert res.outcome == DecisionOutcome.DEFER
    assert res.reason_code == DecisionReasonCode.LOW_CONFIDENCE
    assert res.selected_candidate_id == "cand_low_conf"


def test_policy_current_route_optimal():
    """Verify ACCEPT outcome retaining current route when it is top-ranked."""
    cfg = DecisionConfig()
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    cur = CandidateRoute(
        candidate_id="cur_route",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=10.0,
        is_current_route=True,
    )
    alt = CandidateRoute(
        candidate_id="alt_route",
        node_ids=("n1", "n3", "n2"),
        edge_ids=("e2", "e3"),
        estimated_travel_time_s=30.0,
        is_current_route=False,
    )

    res = policy.evaluate(ctx, [cur, alt])
    assert res.outcome == DecisionOutcome.ACCEPT
    assert res.reason_code == DecisionReasonCode.CURRENT_ROUTE_OPTIMAL
    assert res.selected_candidate_id == "cur_route"


def test_policy_insufficient_benefit_hysteresis():
    """Verify DEFER outcome retaining current route when alternative score gain is marginal."""
    cfg = DecisionConfig(
        weight_travel_time=1.0,
        weight_stability=0.0,
        min_score_improvement=0.10,
        max_travel_time_norm_s=100.0,
    )
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    # cur: 20s travel time -> norm 0.20 -> score -0.20
    cur = CandidateRoute(
        candidate_id="cur_route",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=20.0,
        is_current_route=True,
    )
    # alt: 18s travel time -> norm 0.18 -> score -0.18
    # improvement = -0.18 - (-0.20) = 0.02 < 0.10 required
    alt = CandidateRoute(
        candidate_id="alt_route",
        node_ids=("n1", "n3", "n2"),
        edge_ids=("e2", "e3"),
        estimated_travel_time_s=18.0,
        is_current_route=False,
    )

    res = policy.evaluate(ctx, [cur, alt])
    assert res.outcome == DecisionOutcome.DEFER
    assert res.reason_code == DecisionReasonCode.INSUFFICIENT_BENEFIT
    assert res.selected_candidate_id == "cur_route"


def test_policy_improved_route_accepted():
    """Verify ACCEPT outcome when alternative candidate significantly improves score."""
    cfg = DecisionConfig(
        weight_travel_time=1.0,
        weight_stability=0.0,
        min_score_improvement=0.10,
        max_travel_time_norm_s=100.0,
    )
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(agent_id="v1", current_time_s=0.0, destination_node_id="dest")

    # cur: 50s travel time -> norm 0.50 -> score -0.50
    cur = CandidateRoute(
        candidate_id="cur_route",
        node_ids=("n1", "n2"),
        edge_ids=("e1",),
        estimated_travel_time_s=50.0,
        is_current_route=True,
    )
    # alt: 20s travel time -> norm 0.20 -> score -0.20
    # improvement = -0.20 - (-0.50) = 0.30 >= 0.10
    alt = CandidateRoute(
        candidate_id="alt_route",
        node_ids=("n1", "n3", "n2"),
        edge_ids=("e2", "e3"),
        estimated_travel_time_s=20.0,
        is_current_route=False,
    )

    res = policy.evaluate(ctx, [cur, alt])
    assert res.outcome == DecisionOutcome.ACCEPT
    assert res.reason_code == DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED
    assert res.selected_candidate_id == "alt_route"


def test_policy_current_route_closure_accepts_alternative():
    """Verify that if current route has a hard closure, alternative route is accepted."""
    cfg = DecisionConfig(min_score_improvement=0.20)
    policy = RuleBasedDecisionPolicy(cfg)
    ctx = DecisionContext(
        agent_id="v1",
        current_time_s=0.0,
        destination_node_id="dest",
        known_closed_edges=frozenset({"e_closed"}),
    )

    cur = CandidateRoute(
        candidate_id="cur_route",
        node_ids=("n1", "n2"),
        edge_ids=("e_closed",),
        estimated_travel_time_s=10.0,
        is_current_route=True,
    )
    alt = CandidateRoute(
        candidate_id="alt_route",
        node_ids=("n1", "n3", "n2"),
        edge_ids=("e_open1", "e_open2"),
        estimated_travel_time_s=12.0,
        is_current_route=False,
    )

    res = policy.evaluate(ctx, [cur, alt])
    assert res.outcome == DecisionOutcome.ACCEPT
    assert res.reason_code == DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED
    assert res.selected_candidate_id == "alt_route"
