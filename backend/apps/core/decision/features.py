"""Deterministic feature extraction, normalization, and hard constraint evaluation."""

from __future__ import annotations

import math
from typing import Optional

from apps.core.decision.models import CandidateRoute, DecisionContext


def normalize_travel_time(travel_time_s: float, max_norm_s: float) -> float:
    """Normalize estimated travel time to [0.0, 1.0]."""
    if not math.isfinite(travel_time_s) or travel_time_s <= 0.0:
        return 0.0
    return min(1.0, max(0.0, travel_time_s / max_norm_s))


def normalize_congestion(congestion_cost: float, max_norm: float) -> float:
    """Normalize dynamic congestion cost to [0.0, 1.0]."""
    if not math.isfinite(congestion_cost) or congestion_cost <= 0.0:
        return 0.0
    return min(1.0, max(0.0, congestion_cost / max_norm))


def normalize_hazard(hazard_penalty: float, max_norm: float) -> float:
    """Normalize hazard penalty to [0.0, 1.0]."""
    if not math.isfinite(hazard_penalty) or hazard_penalty <= 0.0:
        return 0.0
    return min(1.0, max(0.0, hazard_penalty / max_norm))


def evaluate_hard_constraints(
    candidate: CandidateRoute,
    context: DecisionContext,
) -> tuple[bool, Optional[str]]:
    """Determine whether a candidate violates any non-negotiable hard constraint.

    Hard constraints include:
    1. Traversal through known closed edges in the agent's local knowledge store.
    2. Traversal through active emergency corridor edges reserved by emergency vehicles.
    3. Disconnected or topologically invalid path structures.

    Returns:
        (is_violated, reason_description)
    """
    # 1. Check known road closures in agent's private store
    for edge_id in candidate.edge_ids:
        if edge_id in context.known_closed_edges:
            return True, f"Route traverses known closed edge '{edge_id}'."

    # 2. Check emergency corridor reservations
    for edge_id in candidate.edge_ids:
        if edge_id in context.emergency_corridor_edges:
            return True, f"Route traverses active emergency corridor edge '{edge_id}'."

    # 3. Check structural validity
    if not candidate.node_ids and candidate.estimated_travel_time_s > 0.0:
        return True, "Candidate route has empty node list with positive travel time."

    return False, None


def compute_stability_bonus(candidate: CandidateRoute) -> float:
    """Compute stability bonus for retaining the current route to prevent flapping."""
    return 1.0 if candidate.is_current_route else 0.0
