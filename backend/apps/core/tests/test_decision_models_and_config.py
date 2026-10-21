"""Unit tests for Phase 19 decision models, configuration, validation, and exceptions."""

import pytest

from apps.core.decision.config import DecisionConfig
from apps.core.decision.exceptions import (
    DecisionError,
    DecisionValidationError,
    InvalidCandidateError,
    PolicyConfigurationError,
)
from apps.core.decision.models import (
    CandidateRoute,
    CandidateScore,
    DecisionContext,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionRecord,
    DecisionResult,
)


def test_decision_outcome_and_reason_code_enums():
    """Verify enum values for decision outcomes and reason codes."""
    assert DecisionOutcome.ACCEPT.value == "accept"
    assert DecisionOutcome.REJECT.value == "reject"
    assert DecisionOutcome.DEFER.value == "defer"
    assert DecisionOutcome.REEVALUATE.value == "reevaluate"

    assert DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED.value == "improved_route_accepted"
    assert DecisionReasonCode.HARD_CONSTRAINT_VIOLATION.value == "hard_constraint_violation"
    assert DecisionReasonCode.LOW_CONFIDENCE.value == "low_confidence"
    assert DecisionReasonCode.CURRENT_ROUTE_OPTIMAL.value == "current_route_optimal"


def test_candidate_route_valid_and_serialization():
    """Verify CandidateRoute construction and serialization."""
    cand = CandidateRoute(
        candidate_id="cand_1",
        node_ids=("n1", "n2", "n3"),
        edge_ids=("e1", "e2"),
        estimated_travel_time_s=12.5,
        total_distance_m=100.0,
        objective_cost=15.0,
        congestion_cost=2.0,
        hazard_penalty=1.0,
        confidence=0.85,
        source="planner",
        is_current_route=False,
    )
    assert cand.candidate_id == "cand_1"
    d = cand.to_dict()
    assert d["candidate_id"] == "cand_1"
    assert d["estimated_travel_time_s"] == 12.5
    assert d["confidence"] == 0.85
    assert d["is_current_route"] is False


def test_candidate_route_invalid_fields():
    """Verify that CandidateRoute raises InvalidCandidateError for invalid attributes."""
    with pytest.raises(InvalidCandidateError):
        CandidateRoute(
            candidate_id="",
            node_ids=("n1",),
            edge_ids=(),
            estimated_travel_time_s=10.0,
        )

    with pytest.raises(InvalidCandidateError):
        CandidateRoute(
            candidate_id="c1",
            node_ids=("n1",),
            edge_ids=(),
            estimated_travel_time_s=-5.0,
        )

    with pytest.raises(InvalidCandidateError):
        CandidateRoute(
            candidate_id="c1",
            node_ids=("n1",),
            edge_ids=(),
            estimated_travel_time_s=10.0,
            confidence=1.5,
        )


def test_candidate_score_valid_and_serialization():
    """Verify CandidateScore construction and to_dict serialization."""
    score = CandidateScore(
        candidate_id="c1",
        raw_score=0.75,
        normalized_travel_time=0.2,
        normalized_congestion=0.1,
        normalized_hazard=0.0,
        confidence=0.9,
        stability_bonus=0.0,
        hard_constraint_violated=False,
    )
    d = score.to_dict()
    assert d["candidate_id"] == "c1"
    assert d["raw_score"] == 0.75
    assert d["hard_constraint_violated"] is False


def test_candidate_score_non_finite_raw_score():
    """Verify CandidateScore raises error for NaN raw score."""
    with pytest.raises(DecisionValidationError):
        CandidateScore(
            candidate_id="c1",
            raw_score=float("nan"),
            normalized_travel_time=0.0,
            normalized_congestion=0.0,
            normalized_hazard=0.0,
            confidence=1.0,
            stability_bonus=0.0,
        )


def test_decision_context_valid_and_serialization():
    """Verify DecisionContext initialization and dictionary conversion."""
    ctx = DecisionContext(
        agent_id="veh_1",
        current_time_s=10.5,
        destination_node_id="dest_node",
        current_node_id="n1",
        current_edge_id="e1",
        current_route_id="r1",
        current_cost=20.0,
        current_route_edge_ids=("e1", "e2"),
        known_closed_edges=frozenset({"e3"}),
        known_congestion_levels={"e1": 1.2},
        known_hazards={"e2": 5.0},
        emergency_corridor_edges=frozenset({"e4"}),
        confidence=0.95,
    )
    d = ctx.to_dict()
    assert d["agent_id"] == "veh_1"
    assert d["destination_node_id"] == "dest_node"
    assert d["known_closed_edges"] == ["e3"]
    assert d["emergency_corridor_edges"] == ["e4"]
    assert d["confidence"] == 0.95


def test_decision_context_invalid():
    """Verify DecisionContext raises validation errors on bad inputs."""
    with pytest.raises(DecisionValidationError):
        DecisionContext(agent_id="", current_time_s=0.0, destination_node_id="dest")

    with pytest.raises(DecisionValidationError):
        DecisionContext(agent_id="v1", current_time_s=-1.0, destination_node_id="dest")

    with pytest.raises(DecisionValidationError):
        DecisionContext(
            agent_id="v1",
            current_time_s=0.0,
            destination_node_id="",
        )


def test_decision_result_and_record_serialization():
    """Verify DecisionResult and DecisionRecord serialization."""
    res = DecisionResult(
        decision_id="dec_1",
        agent_id="veh_1",
        timestamp_s=5.0,
        outcome=DecisionOutcome.ACCEPT,
        selected_candidate_id="cand_1",
        reason_code=DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED,
        reason="Route accepted.",
        execution_time_ms=1.2,
    )
    d = res.to_dict()
    assert d["decision_id"] == "dec_1"
    assert d["outcome"] == "accept"
    assert d["reason_code"] == "improved_route_accepted"

    rec = DecisionRecord(
        record_id="rec_1",
        decision_id="dec_1",
        agent_id="veh_1",
        timestamp_s=5.0,
        outcome=DecisionOutcome.ACCEPT,
        reason_code=DecisionReasonCode.IMPROVED_ROUTE_ACCEPTED,
        selected_candidate_id="cand_1",
        candidate_count=2,
        applied=True,
    )
    rd = rec.to_dict()
    assert rd["record_id"] == "rec_1"
    assert rd["applied"] is True


def test_decision_config_defaults_and_roundtrip():
    """Verify DecisionConfig default attributes, validation, and dict conversion."""
    cfg = DecisionConfig()
    assert cfg.enabled is False
    assert cfg.policy_type == "rule_based"
    assert cfg.weight_travel_time == 1.0
    assert cfg.min_confidence_threshold == 0.4

    d = cfg.to_dict()
    cfg2 = DecisionConfig.from_dict(d)
    assert cfg2.enabled == cfg.enabled
    assert cfg2.weight_travel_time == cfg.weight_travel_time
    assert cfg2.min_confidence_threshold == cfg.min_confidence_threshold


def test_decision_config_invalid():
    """Verify DecisionConfig validation detects erroneous parameters."""
    with pytest.raises(PolicyConfigurationError):
        DecisionConfig(enabled="yes")  # type: ignore

    with pytest.raises(PolicyConfigurationError):
        DecisionConfig(weight_travel_time=-1.0)

    with pytest.raises(PolicyConfigurationError):
        DecisionConfig(min_confidence_threshold=1.5)

    with pytest.raises(PolicyConfigurationError):
        DecisionConfig(max_candidates_per_evaluation=0)


def test_decision_exceptions_hierarchy():
    """Verify exception hierarchy matches expected inheritance."""
    assert issubclass(DecisionValidationError, DecisionError)
    assert issubclass(PolicyConfigurationError, DecisionValidationError)
    assert issubclass(InvalidCandidateError, DecisionValidationError)
