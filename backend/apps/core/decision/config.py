"""Configuration settings and validation for the decision policy subsystem."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from apps.core.decision.exceptions import PolicyConfigurationError


@dataclass
class DecisionConfig:
    """Validated configuration parameters governing decision policy evaluation."""

    enabled: bool = False
    policy_type: str = "rule_based"
    weight_travel_time: float = 1.0
    weight_congestion: float = 0.5
    weight_hazard: float = 0.8
    weight_confidence: float = 0.4
    weight_stability: float = 0.2
    min_confidence_threshold: float = 0.4
    min_score_improvement: float = 0.05
    max_travel_time_norm_s: float = 300.0
    max_congestion_cost_norm: float = 100.0
    max_hazard_cost_norm: float = 100.0
    stale_information_ttl_s: float = 30.0
    max_candidates_per_evaluation: int = 10
    log_decisions: bool = True

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate all configuration attributes strictly."""
        if not isinstance(self.enabled, bool):
            raise PolicyConfigurationError("enabled must be a boolean.")

        if not isinstance(self.policy_type, str) or not self.policy_type.strip():
            raise PolicyConfigurationError("policy_type must be a non-empty string.")

        for name, val in [
            ("weight_travel_time", self.weight_travel_time),
            ("weight_congestion", self.weight_congestion),
            ("weight_hazard", self.weight_hazard),
            ("weight_confidence", self.weight_confidence),
            ("weight_stability", self.weight_stability),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise PolicyConfigurationError(f"{name} must be a real number.")
            if not math.isfinite(val) or val < 0.0:
                raise PolicyConfigurationError(f"{name} must be a non-negative finite float.")

        for name, val in [
            ("min_confidence_threshold", self.min_confidence_threshold),
            ("min_score_improvement", self.min_score_improvement),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise PolicyConfigurationError(f"{name} must be a real number.")
            if not math.isfinite(val) or not (0.0 <= val <= 1.0):
                raise PolicyConfigurationError(f"{name} must be between 0.0 and 1.0.")

        for name, val in [
            ("max_travel_time_norm_s", self.max_travel_time_norm_s),
            ("max_congestion_cost_norm", self.max_congestion_cost_norm),
            ("max_hazard_cost_norm", self.max_hazard_cost_norm),
            ("stale_information_ttl_s", self.stale_information_ttl_s),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise PolicyConfigurationError(f"{name} must be a real number.")
            if not math.isfinite(val) or val <= 0.0:
                raise PolicyConfigurationError(f"{name} must be a positive finite float.")

        if not isinstance(self.max_candidates_per_evaluation, int) or isinstance(
            self.max_candidates_per_evaluation, bool
        ):
            raise PolicyConfigurationError("max_candidates_per_evaluation must be an integer.")
        if self.max_candidates_per_evaluation <= 0:
            raise PolicyConfigurationError("max_candidates_per_evaluation must be >= 1.")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a plain dictionary."""
        return {
            "enabled": self.enabled,
            "policy_type": self.policy_type,
            "weight_travel_time": round(self.weight_travel_time, 4),
            "weight_congestion": round(self.weight_congestion, 4),
            "weight_hazard": round(self.weight_hazard, 4),
            "weight_confidence": round(self.weight_confidence, 4),
            "weight_stability": round(self.weight_stability, 4),
            "min_confidence_threshold": round(self.min_confidence_threshold, 4),
            "min_score_improvement": round(self.min_score_improvement, 4),
            "max_travel_time_norm_s": round(self.max_travel_time_norm_s, 2),
            "max_congestion_cost_norm": round(self.max_congestion_cost_norm, 2),
            "max_hazard_cost_norm": round(self.max_hazard_cost_norm, 2),
            "stale_information_ttl_s": round(self.stale_information_ttl_s, 2),
            "max_candidates_per_evaluation": self.max_candidates_per_evaluation,
            "log_decisions": self.log_decisions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionConfig:
        """Construct configuration from dictionary data."""
        return cls(
            enabled=data.get("enabled", False),
            policy_type=data.get("policy_type", "rule_based"),
            weight_travel_time=float(data.get("weight_travel_time", 1.0)),
            weight_congestion=float(data.get("weight_congestion", 0.5)),
            weight_hazard=float(data.get("weight_hazard", 0.8)),
            weight_confidence=float(data.get("weight_confidence", 0.4)),
            weight_stability=float(data.get("weight_stability", 0.2)),
            min_confidence_threshold=float(data.get("min_confidence_threshold", 0.4)),
            min_score_improvement=float(data.get("min_score_improvement", 0.05)),
            max_travel_time_norm_s=float(data.get("max_travel_time_norm_s", 300.0)),
            max_congestion_cost_norm=float(data.get("max_congestion_cost_norm", 100.0)),
            max_hazard_cost_norm=float(data.get("max_hazard_cost_norm", 100.0)),
            stale_information_ttl_s=float(data.get("stale_information_ttl_s", 30.0)),
            max_candidates_per_evaluation=int(data.get("max_candidates_per_evaluation", 10)),
            log_decisions=bool(data.get("log_decisions", True)),
        )
