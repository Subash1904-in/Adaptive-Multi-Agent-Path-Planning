"""Domain models and value types for the AMAPP route planning subsystem."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Union

from apps.core.domain.models import Route
from apps.core.domain.serialization import to_dict as domain_to_dict
from apps.core.routing.exceptions import InvalidReroutePolicyError, InvalidRoutingRequestError


class CostMode(str, Enum):
    """Optimization objectives supported by AMAPP route planners."""

    DISTANCE = "distance"
    TRAVEL_TIME = "travel_time"


class RoutingAlgorithm(str, Enum):
    """Shortest-path search algorithms supported by AMAPP route planners."""

    DIJKSTRA = "dijkstra"
    ASTAR = "astar"


@dataclass
class RoutingRequest:
    """Configuration parameters for a single-agent route planning query."""

    start_node_id: str
    destination_node_id: str
    cost_mode: CostMode = CostMode.TRAVEL_TIME
    algorithm: RoutingAlgorithm = RoutingAlgorithm.ASTAR
    closed_edge_ids: set[str] = field(default_factory=set)
    edge_cost_fn: Optional[Callable[..., float]] = None

    def __post_init__(self) -> None:
        if not self.start_node_id or not isinstance(self.start_node_id, str):
            raise InvalidRoutingRequestError(
                "start_node_id must be a non-empty string.", field="start_node_id"
            )
        if not self.destination_node_id or not isinstance(self.destination_node_id, str):
            raise InvalidRoutingRequestError(
                "destination_node_id must be a non-empty string.", field="destination_node_id"
            )
        if not isinstance(self.cost_mode, CostMode):
            try:
                self.cost_mode = CostMode(self.cost_mode)
            except ValueError:
                valid_modes = [m.value for m in CostMode]
                raise InvalidRoutingRequestError(
                    f"Invalid cost_mode '{self.cost_mode}'. Must be one of {valid_modes}.",
                    field="cost_mode",
                )
        if not isinstance(self.algorithm, RoutingAlgorithm):
            try:
                self.algorithm = RoutingAlgorithm(self.algorithm)
            except ValueError:
                valid_algos = [a.value for a in RoutingAlgorithm]
                raise InvalidRoutingRequestError(
                    f"Invalid algorithm '{self.algorithm}'. Must be one of {valid_algos}.",
                    field="algorithm",
                )
        if not isinstance(self.closed_edge_ids, (set, list, tuple)):
            raise InvalidRoutingRequestError(
                "closed_edge_ids must be a set, list, or tuple of edge IDs.",
                field="closed_edge_ids",
            )
        self.closed_edge_ids = set(self.closed_edge_ids)
        if self.edge_cost_fn is not None and not callable(self.edge_cost_fn):
            raise InvalidRoutingRequestError(
                "edge_cost_fn must be a callable if provided.", field="edge_cost_fn"
            )


@dataclass
class RoutingResult:
    """Comprehensive, typed output produced by Dijkstra and A* path planners."""

    success: bool
    algorithm: RoutingAlgorithm
    cost_mode: CostMode
    start_node_id: str
    destination_node_id: str
    node_ids: list[str]
    edge_ids: list[str]
    total_distance_m: float
    estimated_duration_s: float
    objective_cost: float
    nodes_expanded: int
    edges_examined: int
    execution_time_ms: float
    route: Optional[Route] = None

    def __post_init__(self) -> None:
        if self.total_distance_m < 0.0:
            raise InvalidRoutingRequestError("total_distance_m must be non-negative.")
        if self.estimated_duration_s < 0.0:
            raise InvalidRoutingRequestError("estimated_duration_s must be non-negative.")
        if self.objective_cost < 0.0:
            raise InvalidRoutingRequestError("objective_cost must be non-negative.")
        if self.nodes_expanded < 0:
            raise InvalidRoutingRequestError("nodes_expanded must be non-negative.")
        if self.edges_examined < 0:
            raise InvalidRoutingRequestError("edges_examined must be non-negative.")
        if self.execution_time_ms < 0.0:
            raise InvalidRoutingRequestError("execution_time_ms must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        """Convert routing result to a JSON-serializable dictionary."""
        return {
            "success": self.success,
            "algorithm": self.algorithm.value,
            "cost_mode": self.cost_mode.value,
            "start_node_id": self.start_node_id,
            "destination_node_id": self.destination_node_id,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "total_distance_m": round(self.total_distance_m, 3),
            "estimated_duration_s": round(self.estimated_duration_s, 3),
            "objective_cost": round(self.objective_cost, 4),
            "nodes_expanded": self.nodes_expanded,
            "edges_examined": self.edges_examined,
            "execution_time_ms": round(self.execution_time_ms, 3),
            "route": domain_to_dict(self.route) if self.route is not None else None,
        }


class RerouteDecisionType(str, Enum):
    """Classification of adaptive rerouting evaluation outcomes."""

    NO_CHANGE = "no_change"
    REROUTE_ACCEPTED = "reroute_accepted"
    INSUFFICIENT_BENEFIT = "insufficient_benefit"
    COOLDOWN_ACTIVE = "cooldown_active"
    NO_ALTERNATIVE_ROUTE = "no_alternative_route"
    CURRENT_ROUTE_INVALID = "current_route_invalid"
    NO_FRESH_INFORMATION = "no_fresh_information"
    DESTINATION_REACHED = "destination_reached"
    REROUTE_REJECTED = "reroute_rejected"


@dataclass(frozen=True)
class RerouteDecision:
    """Structured decision output emitted when evaluating an active vehicle route."""

    decision_type: RerouteDecisionType
    vehicle_id: str
    timestamp_s: float
    current_cost: float
    candidate_cost: Optional[float] = None
    cost_improvement: Optional[float] = None
    old_route_id: Optional[str] = None
    new_route_id: Optional[str] = None
    candidate_node_ids: tuple[str, ...] = field(default_factory=tuple)
    candidate_edge_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to a JSON-compatible dictionary."""
        return {
            "decision_type": self.decision_type.value,
            "vehicle_id": self.vehicle_id,
            "timestamp_s": round(self.timestamp_s, 4),
            "current_cost": (
                round(self.current_cost, 4) if math.isfinite(self.current_cost) else "Infinity"
            ),
            "candidate_cost": (
                round(self.candidate_cost, 4)
                if self.candidate_cost is not None and math.isfinite(self.candidate_cost)
                else None
            ),
            "cost_improvement": (
                round(self.cost_improvement, 4)
                if self.cost_improvement is not None and math.isfinite(self.cost_improvement)
                else (str(self.cost_improvement) if self.cost_improvement is not None else None)
            ),
            "old_route_id": self.old_route_id,
            "new_route_id": self.new_route_id,
            "candidate_node_ids": list(self.candidate_node_ids),
            "candidate_edge_ids": list(self.candidate_edge_ids),
            "reason": self.reason,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass
class AdaptiveRoutingConfig:
    """Configuration settings governing decentralized adaptive rerouting and dynamic costs."""

    enabled: bool = False
    min_absolute_benefit: float = 5.0
    min_relative_benefit: float = 0.10
    reroute_cooldown_s: float = 5.0
    min_confidence_threshold: float = 0.5
    disputed_closure_policy: str = "conservative"
    congestion_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "low": 1.0,
            "moderate": 1.5,
            "high": 2.5,
            "severe": 4.0,
        }
    )
    hazard_penalties: dict[str, float] = field(
        default_factory=lambda: {
            "low": 5.0,
            "medium": 15.0,
            "high": 30.0,
            "critical": 60.0,
        }
    )
    current_edge_continuation_policy: str = "finish_edge"
    repeat_suppression: bool = True
    algorithm: RoutingAlgorithm = RoutingAlgorithm.ASTAR
    cost_mode: CostMode = CostMode.TRAVEL_TIME

    def __init__(
        self,
        enabled: bool = False,
        min_absolute_benefit: Optional[float] = None,
        min_relative_benefit: Optional[float] = None,
        reroute_cooldown_s: Optional[float] = None,
        min_confidence_threshold: float = 0.5,
        disputed_closure_policy: str = "conservative",
        congestion_multipliers: Optional[dict[str, float]] = None,
        hazard_penalties: Optional[dict[str, float]] = None,
        current_edge_continuation_policy: Optional[str] = None,
        repeat_suppression: bool = True,
        algorithm: Union[RoutingAlgorithm, str] = RoutingAlgorithm.ASTAR,
        cost_mode: Union[CostMode, str] = CostMode.TRAVEL_TIME,
        # Recognized aliases
        min_benefit_absolute: Optional[float] = None,
        min_benefit_relative: Optional[float] = None,
        cooldown_s: Optional[float] = None,
        cooldown_ticks: Optional[Union[int, float]] = None,
        default_hazard_penalty: Optional[float] = None,
        current_edge_policy: Optional[str] = None,
        **extra_kwargs: Any,
    ) -> None:
        self.enabled = enabled

        # Absolute benefit
        if min_absolute_benefit is not None:
            self.min_absolute_benefit = float(min_absolute_benefit)
        elif min_benefit_absolute is not None:
            self.min_absolute_benefit = float(min_benefit_absolute)
        else:
            self.min_absolute_benefit = 5.0

        # Relative benefit
        if min_relative_benefit is not None:
            self.min_relative_benefit = float(min_relative_benefit)
        elif min_benefit_relative is not None:
            self.min_relative_benefit = float(min_benefit_relative)
        else:
            self.min_relative_benefit = 0.10

        # Cooldown
        if reroute_cooldown_s is not None:
            self.reroute_cooldown_s = float(reroute_cooldown_s)
        elif cooldown_s is not None:
            self.reroute_cooldown_s = float(cooldown_s)
        elif cooldown_ticks is not None:
            self.reroute_cooldown_s = float(cooldown_ticks) * 0.1
        else:
            self.reroute_cooldown_s = 5.0

        self.min_confidence_threshold = min_confidence_threshold
        self.disputed_closure_policy = disputed_closure_policy

        if congestion_multipliers is not None:
            self.congestion_multipliers = dict(congestion_multipliers)
        else:
            self.congestion_multipliers = {
                "low": 1.0,
                "moderate": 1.5,
                "high": 2.5,
                "severe": 4.0,
            }

        if hazard_penalties is not None:
            self.hazard_penalties = dict(hazard_penalties)
        else:
            self.hazard_penalties = {
                "low": 5.0,
                "medium": 15.0,
                "high": 30.0,
                "critical": 60.0,
            }

        if default_hazard_penalty is not None:
            self.hazard_penalties["default"] = float(default_hazard_penalty)
            for k in ("low", "medium", "high", "critical"):
                self.hazard_penalties.setdefault(k, float(default_hazard_penalty))

        if current_edge_continuation_policy is not None:
            self.current_edge_continuation_policy = current_edge_continuation_policy
        elif current_edge_policy is not None:
            self.current_edge_continuation_policy = current_edge_policy
        else:
            self.current_edge_continuation_policy = "finish_edge"

        self.repeat_suppression = repeat_suppression
        self.algorithm = (
            RoutingAlgorithm(algorithm)
            if not isinstance(algorithm, RoutingAlgorithm)
            else algorithm
        )
        self.cost_mode = CostMode(cost_mode) if not isinstance(cost_mode, CostMode) else cost_mode

        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise InvalidReroutePolicyError(
                f"enabled must be a boolean, got {type(self.enabled).__name__}."
            )
        if not isinstance(self.repeat_suppression, bool):
            raise InvalidReroutePolicyError(
                f"repeat_suppression must be a boolean, got "
                f"{type(self.repeat_suppression).__name__}."
            )

        # Validate numerical thresholds
        for name, val, min_val in [
            ("min_absolute_benefit", self.min_absolute_benefit, 0.0),
            ("min_relative_benefit", self.min_relative_benefit, 0.0),
            ("reroute_cooldown_s", self.reroute_cooldown_s, 0.0),
            ("min_confidence_threshold", self.min_confidence_threshold, 0.0),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise InvalidReroutePolicyError(f"{name} must be a real number, got {val!r}.")
            f_val = float(val)
            if math.isnan(f_val) or math.isinf(f_val) or f_val < min_val:
                raise InvalidReroutePolicyError(
                    f"{name} must be finite and >= {min_val}, got {f_val}."
                )

        if self.min_confidence_threshold > 1.0:
            raise InvalidReroutePolicyError(
                f"min_confidence_threshold must be in [0.0, 1.0], "
                f"got {self.min_confidence_threshold}."
            )

        if self.disputed_closure_policy not in ("conservative", "permissive"):
            raise InvalidReroutePolicyError(
                f"disputed_closure_policy must be 'conservative' or 'permissive', "
                f"got '{self.disputed_closure_policy}'."
            )

        if self.current_edge_continuation_policy not in ("finish_edge",):
            raise InvalidReroutePolicyError(
                f"Unsupported current_edge_continuation_policy "
                f"'{self.current_edge_continuation_policy}'."
            )

        if not isinstance(self.congestion_multipliers, dict):
            raise InvalidReroutePolicyError("congestion_multipliers must be a dictionary.")
        for k, v in self.congestion_multipliers.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidReroutePolicyError(f"Congestion multiplier for '{k}' must be numeric.")
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv) or fv < 1.0:
                raise InvalidReroutePolicyError(
                    f"Congestion multiplier for '{k}' must be finite and >= 1.0, got {fv}."
                )

        if not isinstance(self.hazard_penalties, dict):
            raise InvalidReroutePolicyError("hazard_penalties must be a dictionary.")
        for k, v in self.hazard_penalties.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidReroutePolicyError(f"Hazard penalty for '{k}' must be numeric.")
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv) or fv < 0.0:
                raise InvalidReroutePolicyError(
                    f"Hazard penalty for '{k}' must be finite and >= 0.0, got {fv}."
                )

        if not isinstance(self.algorithm, RoutingAlgorithm):
            try:
                self.algorithm = RoutingAlgorithm(self.algorithm)
            except ValueError:
                raise InvalidReroutePolicyError(f"Unsupported algorithm '{self.algorithm}'.")

        if not isinstance(self.cost_mode, CostMode):
            try:
                self.cost_mode = CostMode(self.cost_mode)
            except ValueError:
                raise InvalidReroutePolicyError(f"Unsupported cost_mode '{self.cost_mode}'.")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "min_absolute_benefit": round(self.min_absolute_benefit, 4),
            "min_relative_benefit": round(self.min_relative_benefit, 4),
            "reroute_cooldown_s": round(self.reroute_cooldown_s, 4),
            "min_confidence_threshold": round(self.min_confidence_threshold, 4),
            "disputed_closure_policy": self.disputed_closure_policy,
            "congestion_multipliers": {
                k: round(v, 4) for k, v in self.congestion_multipliers.items()
            },
            "hazard_penalties": {k: round(v, 4) for k, v in self.hazard_penalties.items()},
            "current_edge_continuation_policy": self.current_edge_continuation_policy,
            "repeat_suppression": self.repeat_suppression,
            "algorithm": self.algorithm.value,
            "cost_mode": self.cost_mode.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptiveRoutingConfig":
        """Reconstruct configuration from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            min_absolute_benefit=float(data.get("min_absolute_benefit", 5.0)),
            min_relative_benefit=float(data.get("min_relative_benefit", 0.10)),
            reroute_cooldown_s=float(data.get("reroute_cooldown_s", 5.0)),
            min_confidence_threshold=float(data.get("min_confidence_threshold", 0.5)),
            disputed_closure_policy=data.get("disputed_closure_policy", "conservative"),
            congestion_multipliers=dict(
                data.get(
                    "congestion_multipliers",
                    {
                        "low": 1.0,
                        "moderate": 1.5,
                        "high": 2.5,
                        "severe": 4.0,
                    },
                )
            ),
            hazard_penalties=dict(
                data.get(
                    "hazard_penalties",
                    {
                        "low": 5.0,
                        "medium": 15.0,
                        "high": 30.0,
                        "critical": 60.0,
                    },
                )
            ),
            current_edge_continuation_policy=data.get(
                "current_edge_continuation_policy", "finish_edge"
            ),
            repeat_suppression=data.get("repeat_suppression", True),
            algorithm=RoutingAlgorithm(data.get("algorithm", RoutingAlgorithm.ASTAR.value)),
            cost_mode=CostMode(data.get("cost_mode", CostMode.TRAVEL_TIME.value)),
        )
