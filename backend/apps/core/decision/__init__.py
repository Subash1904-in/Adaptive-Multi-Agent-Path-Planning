"""Pluggable AI-style decision policies for autonomous vehicle agents.

Provides deterministic multi-objective candidate scoring, hard safety constraint enforcement,
observation confidence validation, route stability hysteresis, and structured decision telemetry.
"""

from apps.core.decision.config import DecisionConfig
from apps.core.decision.exceptions import (
    DecisionError,
    DecisionExecutionError,
    DecisionValidationError,
    InvalidCandidateError,
    PolicyConfigurationError,
    StaleRouteError,
)
from apps.core.decision.features import (
    compute_stability_bonus,
    evaluate_hard_constraints,
    normalize_congestion,
    normalize_hazard,
    normalize_travel_time,
)
from apps.core.decision.manager import DecisionManager
from apps.core.decision.metrics import DecisionMetrics
from apps.core.decision.models import (
    CandidateRoute,
    CandidateScore,
    DecisionContext,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionRecord,
    DecisionResult,
)
from apps.core.decision.policy import DecisionPolicy, RuleBasedDecisionPolicy
from apps.core.decision.scoring import CandidateScorer

__all__ = [
    "CandidateRoute",
    "CandidateScore",
    "CandidateScorer",
    "DecisionConfig",
    "DecisionContext",
    "DecisionError",
    "DecisionExecutionError",
    "DecisionManager",
    "DecisionMetrics",
    "DecisionOutcome",
    "DecisionPolicy",
    "DecisionReasonCode",
    "DecisionRecord",
    "DecisionResult",
    "DecisionValidationError",
    "InvalidCandidateError",
    "PolicyConfigurationError",
    "RuleBasedDecisionPolicy",
    "StaleRouteError",
    "compute_stability_bonus",
    "evaluate_hard_constraints",
    "normalize_congestion",
    "normalize_hazard",
    "normalize_travel_time",
]
