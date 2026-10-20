"""SafetyManager coordinating detection, avoidance policy, metrics, and event buffering."""

from typing import Any, Optional, Sequence

from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.detection import CollisionDetector
from apps.core.safety.metrics import SafetyMetrics
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    SafetyEvent,
    SafetyEventType,
    VehicleControlOverride,
    VehiclePairCollision,
)
from apps.core.safety.policy import SafetyPolicy


class SafetyManager:
    """Authoritative coordinator managing vehicle safety evaluations, policies, and metrics."""

    def __init__(self, config: Optional[SafetyConfig] = None) -> None:
        """Initialize the safety manager with configuration, detector, policy, and metrics.

        Args:
            config: Optional SafetyConfig instance. If omitted, uses default parameters.
        """
        self.config: SafetyConfig = config or SafetyConfig()
        self.detector: CollisionDetector = CollisionDetector(config=self.config)
        self.policy: SafetyPolicy = SafetyPolicy(config=self.config)
        self.metrics: SafetyMetrics = SafetyMetrics()
        self.events: list[SafetyEvent] = []
        self._event_counter: int = 0

    def evaluate_and_stage(
        self,
        agents: Sequence[VehicleAgent],
        current_time_s: float,
        scenario_id: Optional[str] = None,
        pedestrians: Optional[Sequence[Any]] = None,
    ) -> tuple[
        dict[str, VehicleControlOverride], list[VehiclePairCollision], list[SafetyEvent]
    ]:
        """Evaluate multi-vehicle and pedestrian conflicts, stage control overrides,
        and log safety events.

        Args:
            agents: Sequence of VehicleAgent instances in current world state.
            current_time_s: Current simulation elapsed time in seconds.
            scenario_id: Optional scenario identifier for event metadata.
            pedestrians: Optional sequence of PedestrianAgent instances in current world state.

        Returns:
            Tuple of:
            - Dict mapping vehicle_id to VehicleControlOverride
            - List of evaluated VehiclePairCollision records
            - List of newly logged SafetyEvent objects in this tick
        """
        if not self.config.enabled:
            return ({}, [], [])

        pair_collisions = self.detector.detect_all_conflicts(agents, pedestrians=pedestrians)
        overrides = self.policy.resolve_conflicts(agents, pair_collisions)

        new_events: list[SafetyEvent] = []

        # 1. Update pair metrics and record events
        for pair in pair_collisions:
            is_near_miss = (
                not pair.is_overlap
                and pair.distance_m <= self.config.near_miss_distance_m
                and pair.risk_level in (CollisionRiskLevel.IMMINENT, CollisionRiskLevel.HIGH_RISK)
            )
            is_potential = pair.risk_level in (
                CollisionRiskLevel.CAUTION,
                CollisionRiskLevel.HIGH_RISK,
                CollisionRiskLevel.IMMINENT,
            )
            is_ttc_violated = pair.ttc_s is not None and pair.ttc_s <= self.config.ttc_caution_s

            self.metrics.record_pair_observation(
                separation_m=pair.distance_m,
                ttc_s=pair.ttc_s,
                is_overlap=pair.is_overlap,
                is_near_miss=is_near_miss,
                is_separation_violated=pair.separation_violated,
                is_ttc_violated=is_ttc_violated,
                is_potential_collision=is_potential,
            )

            # Generate structured event record if condition met and logging enabled
            if self.config.log_events and (pair.is_overlap or is_near_miss):
                self._event_counter += 1
                evt_type = (
                    SafetyEventType.COLLISION if pair.is_overlap else SafetyEventType.NEAR_MISS
                )
                if pair.is_pedestrian_conflict:
                    v_ids: tuple[str, ...] = (pair.vehicle_a_id,)
                    ped_id: Optional[str] = pair.pedestrian_id
                else:
                    v_ids = (pair.vehicle_a_id, pair.vehicle_b_id)
                    ped_id = None

                event = SafetyEvent(
                    event_id=f"evt_{self._event_counter:06d}",
                    sim_time_s=current_time_s,
                    vehicle_ids=v_ids,
                    event_type=evt_type,
                    risk_category=pair.risk_level,
                    measured_separation_m=pair.distance_m,
                    estimated_ttc_s=pair.ttc_s,
                    action_taken_a=pair.recommended_action_a,
                    action_taken_b=pair.recommended_action_b,
                    is_overlap=pair.is_overlap,
                    scenario_id=scenario_id,
                    pedestrian_id=ped_id,
                )
                new_events.append(event)
                self.events.append(event)

        # 2. Update override metrics
        for override in overrides.values():
            if override.action_type != SafetyActionType.NONE:
                self.metrics.record_override_action(override.action_type.value)

        return (overrides, pair_collisions, new_events)

    def capture_state(self) -> dict[str, Any]:
        """Capture atomic rollback state of metrics, event buffer, and counter."""
        return {
            "metrics": self.metrics.capture_state(),
            "events": list(self.events),
            "event_counter": self._event_counter,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Atomically restore metrics, event buffer, and counter from snapshot."""
        self.metrics.restore_state(state["metrics"])
        self.events = list(state["events"])
        self._event_counter = state["event_counter"]

    def reset(self) -> None:
        """Reset metrics counters, event buffer, and event counter."""
        self.metrics.reset()
        self.events.clear()
        self._event_counter = 0
