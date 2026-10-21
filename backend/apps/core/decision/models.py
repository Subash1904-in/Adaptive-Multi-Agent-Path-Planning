"""Domain models, candidate structures, scoring outputs, and decision results."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from apps.core.decision.exceptions import DecisionValidationError, InvalidCandidateError
from apps.core.domain.models import Route
from apps.core.domain.serialization import to_dict as domain_to_dict


class DecisionOutcome(str, Enum):
    """Possible outcomes of an autonomous agent's decision policy evaluation."""

    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    REEVALUATE = "reevaluate"


class DecisionReasonCode(str, Enum):
    """Machine-readable taxonomy of rationales behind a decision outcome."""

    IMPROVED_ROUTE_ACCEPTED = "improved_route_accepted"
    CURRENT_ROUTE_OPTIMAL = "current_route_optimal"
    INSUFFICIENT_BENEFIT = "insufficient_benefit"
    HARD_CONSTRAINT_VIOLATION = "hard_constraint_violation"
    ROAD_CLOSURE_BLOCKED = "road_closure_blocked"
    EMERGENCY_CORRIDOR_BLOCKED = "emergency_corridor_blocked"
    LOW_CONFIDENCE = "low_confidence"
    STALE_INFORMATION = "stale_information"
    NO_VIABLE_CANDIDATE = "no_viable_candidate"
    INVALID_CANDIDATE = "invalid_candidate"
    COOLDOWN_ACTIVE = "cooldown_active"
    POLICY_DISABLED = "policy_disabled"


@dataclass(frozen=True)
class CandidateRoute:
    """Represents a candidate route or trajectory option submitted for evaluation."""

    candidate_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_travel_time_s: float
    total_distance_m: float = 0.0
    objective_cost: float = 0.0
    congestion_cost: float = 0.0
    hazard_penalty: float = 0.0
    confidence: float = 1.0
    source: str = "default"
    route_version: int = 1
    is_current_route: bool = False
    route: Optional[Route] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.candidate_id or not isinstance(self.candidate_id, str):
            raise InvalidCandidateError("candidate_id must be a non-empty string.")
        if not isinstance(self.node_ids, (tuple, list)):
            raise InvalidCandidateError("node_ids must be a sequence of node identifiers.")
        if not isinstance(self.edge_ids, (tuple, list)):
            raise InvalidCandidateError("edge_ids must be a sequence of edge identifiers.")
        if not math.isfinite(self.estimated_travel_time_s) or self.estimated_travel_time_s < 0.0:
            raise InvalidCandidateError(
                "estimated_travel_time_s must be a non-negative finite float."
            )
        if not math.isfinite(self.total_distance_m) or self.total_distance_m < 0.0:
            raise InvalidCandidateError("total_distance_m must be a non-negative finite float.")
        if not math.isfinite(self.objective_cost) or self.objective_cost < 0.0:
            raise InvalidCandidateError("objective_cost must be a non-negative finite float.")
        if not math.isfinite(self.congestion_cost) or self.congestion_cost < 0.0:
            raise InvalidCandidateError("congestion_cost must be a non-negative finite float.")
        if not math.isfinite(self.hazard_penalty) or self.hazard_penalty < 0.0:
            raise InvalidCandidateError("hazard_penalty must be a non-negative finite float.")
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise InvalidCandidateError("confidence must be a float between 0.0 and 1.0 inclusive.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate route to a dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "estimated_travel_time_s": round(self.estimated_travel_time_s, 3),
            "total_distance_m": round(self.total_distance_m, 3),
            "objective_cost": round(self.objective_cost, 4),
            "congestion_cost": round(self.congestion_cost, 4),
            "hazard_penalty": round(self.hazard_penalty, 4),
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "route_version": self.route_version,
            "is_current_route": self.is_current_route,
            "route": domain_to_dict(self.route) if self.route is not None else None,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CandidateScore:
    """Normalized scoring terms and hard-constraint status for a single candidate."""

    candidate_id: str
    raw_score: float
    normalized_travel_time: float
    normalized_congestion: float
    normalized_hazard: float
    confidence: float
    stability_bonus: float
    hard_constraint_violated: bool = False
    violation_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.raw_score):
            if not (self.hard_constraint_violated and self.raw_score == float("-inf")):
                raise DecisionValidationError("raw_score must be a finite float.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate score to a dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "raw_score": (
                -float("inf") if self.raw_score == float("-inf") else round(self.raw_score, 4)
            ),
            "normalized_travel_time": round(self.normalized_travel_time, 4),
            "normalized_congestion": round(self.normalized_congestion, 4),
            "normalized_hazard": round(self.normalized_hazard, 4),
            "confidence": round(self.confidence, 4),
            "stability_bonus": round(self.stability_bonus, 4),
            "hard_constraint_violated": self.hard_constraint_violated,
            "violation_reason": self.violation_reason,
        }


@dataclass(frozen=True)
class DecisionContext:
    """Agent-isolated decision context capturing local observation state and constraints."""

    agent_id: str
    current_time_s: float
    destination_node_id: str
    current_node_id: Optional[str] = None
    current_edge_id: Optional[str] = None
    current_route_id: Optional[str] = None
    current_cost: float = 0.0
    current_route_edge_ids: tuple[str, ...] = field(default_factory=tuple)
    known_closed_edges: frozenset[str] = field(default_factory=frozenset)
    known_congestion_levels: dict[str, float] = field(default_factory=dict)
    known_hazards: dict[str, float] = field(default_factory=dict)
    emergency_corridor_edges: frozenset[str] = field(default_factory=frozenset)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id or not isinstance(self.agent_id, str):
            raise DecisionValidationError("agent_id must be a non-empty string.")
        if not self.destination_node_id or not isinstance(self.destination_node_id, str):
            raise DecisionValidationError("destination_node_id must be a non-empty string.")
        if not math.isfinite(self.current_time_s) or self.current_time_s < 0.0:
            raise DecisionValidationError("current_time_s must be non-negative finite float.")
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise DecisionValidationError("confidence must be a float between 0.0 and 1.0.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize decision context to a dictionary."""
        return {
            "agent_id": self.agent_id,
            "current_time_s": round(self.current_time_s, 4),
            "destination_node_id": self.destination_node_id,
            "current_node_id": self.current_node_id,
            "current_edge_id": self.current_edge_id,
            "current_route_id": self.current_route_id,
            "current_cost": (
                round(self.current_cost, 4) if math.isfinite(self.current_cost) else "Infinity"
            ),
            "current_route_edge_ids": list(self.current_route_edge_ids),
            "known_closed_edges": sorted(self.known_closed_edges),
            "known_congestion_levels": dict(self.known_congestion_levels),
            "known_hazards": dict(self.known_hazards),
            "emergency_corridor_edges": sorted(self.emergency_corridor_edges),
            "confidence": round(self.confidence, 4),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionResult:
    """Structured decision output produced by policy evaluation."""

    decision_id: str
    agent_id: str
    timestamp_s: float
    outcome: DecisionOutcome
    selected_candidate_id: Optional[str]
    reason_code: DecisionReasonCode
    reason: str
    candidate_scores: dict[str, CandidateScore] = field(default_factory=dict)
    selected_candidate: Optional[CandidateRoute] = None
    execution_time_ms: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize decision result to a dictionary."""
        return {
            "decision_id": self.decision_id,
            "agent_id": self.agent_id,
            "timestamp_s": round(self.timestamp_s, 4),
            "outcome": self.outcome.value,
            "selected_candidate_id": self.selected_candidate_id,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "candidate_scores": {
                cid: score.to_dict() for cid, score in self.candidate_scores.items()
            },
            "selected_candidate": (
                self.selected_candidate.to_dict() if self.selected_candidate is not None else None
            ),
            "execution_time_ms": round(self.execution_time_ms, 3),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class DecisionRecord:
    """Immutable audit record representing a point-in-time policy evaluation event."""

    record_id: str
    decision_id: str
    agent_id: str
    timestamp_s: float
    outcome: DecisionOutcome
    reason_code: DecisionReasonCode
    selected_candidate_id: Optional[str]
    candidate_count: int
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize audit record to a dictionary."""
        return {
            "record_id": self.record_id,
            "decision_id": self.decision_id,
            "agent_id": self.agent_id,
            "timestamp_s": round(self.timestamp_s, 4),
            "outcome": self.outcome.value,
            "reason_code": self.reason_code.value,
            "selected_candidate_id": self.selected_candidate_id,
            "candidate_count": self.candidate_count,
            "applied": self.applied,
        }
