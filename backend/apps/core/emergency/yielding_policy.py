"""Deterministic yielding policy for non-emergency vehicles interacting with corridors."""

import math
from typing import Optional, Sequence

from apps.core.domain.enums import TrafficSignalState
from apps.core.emergency.models import (
    EmergencyAwarenessRecord,
    EmergencyConfig,
    EmergencyCorridor,
    YieldActionType,
    YieldDecision,
    YieldRequest,
)
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.models import PedestrianLifecycleState
from apps.core.signals.controller import TrafficSignalController


class YieldingPolicy:
    """Evaluates and enforces deterministic yielding actions for non-emergency vehicles."""

    def __init__(self, config: Optional[EmergencyConfig] = None) -> None:
        self.config = config or EmergencyConfig()

    def evaluate_vehicle_yield(
        self,
        agent: VehicleAgent,
        awareness: Optional[EmergencyAwarenessRecord],
        corridors: Sequence[EmergencyCorridor],
        signals: Sequence[TrafficSignalController],
        pedestrians: Optional[Sequence[PedestrianAgent]] = None,
        yield_requests: Optional[Sequence[YieldRequest]] = None,
        emergency_agents: Optional[Sequence[VehicleAgent]] = None,
        current_time_s: float = 0.0,
    ) -> YieldDecision:
        """Determine whether vehicle must yield, decelerate, or stop for an emergency corridor.

        Respects traffic signals, crosswalk occupancy, vehicle kinematics, and local awareness.
        """
        vid = agent.vehicle.id
        curr_edge = agent.vehicle.current_edge_id
        curr_node = agent.vehicle.current_node_id

        # 1. Check if vehicle has an active explicit YieldRequest directed at it
        if yield_requests:
            for y_req in yield_requests:
                if y_req.target_vehicle_id == vid and not y_req.is_expired(current_time_s):
                    # Check safety constraints: do not enter occupied crosswalk or red signal
                    if self._is_at_red_signal(agent, signals):
                        return YieldDecision(
                            vehicle_id=vid,
                            action=YieldActionType.STOP_BEFORE_INTERSECTION,
                            effective_decel_mps2=self.config.yield_decel_mps2,
                            reason="Halted at red signal while yielding to emergency vehicle",
                            source_yield_id=y_req.yield_id,
                        )
                    if self._is_crosswalk_occupied(agent, pedestrians):
                        return YieldDecision(
                            vehicle_id=vid,
                            action=YieldActionType.STOP_BEFORE_INTERSECTION,
                            effective_decel_mps2=self.config.yield_decel_mps2,
                            reason="Halted before crosswalk with active pedestrians",
                            source_yield_id=y_req.yield_id,
                        )

                    decel = min(
                        agent.config.max_deceleration_mps2,
                        max(y_req.target_decel_mps2, self.config.yield_decel_mps2),
                    )
                    return YieldDecision(
                        vehicle_id=vid,
                        action=y_req.recommended_action,
                        effective_decel_mps2=decel,
                        reason=f"Obeying explicit yield request {y_req.yield_id}",
                        source_yield_id=y_req.yield_id,
                    )

        # 2. Check local awareness of active emergency corridors
        if awareness and awareness.is_active:
            # Check if vehicle is currently on an edge or approaching a node in the corridor
            is_on_corridor_edge = curr_edge and curr_edge in awareness.corridor_edges
            is_at_corridor_node = curr_node and curr_node in awareness.corridor_nodes

            # Proximity check to the emergency vehicle if positions known
            is_in_proximity = False
            if emergency_agents:
                for em_ag in emergency_agents:
                    if em_ag.vehicle.id == awareness.emergency_vehicle_id:
                        dx = em_ag.vehicle.position.x - agent.vehicle.position.x
                        dy = em_ag.vehicle.position.y - agent.vehicle.position.y
                        dist = math.hypot(dx, dy)
                        if dist <= self.config.yielding_distance_m:
                            is_in_proximity = True
                            break

            if is_on_corridor_edge or is_at_corridor_node or is_in_proximity:
                # Must yield safely
                if self._is_at_red_signal(agent, signals):
                    return YieldDecision(
                        vehicle_id=vid,
                        action=YieldActionType.STOP_BEFORE_INTERSECTION,
                        effective_decel_mps2=self.config.yield_decel_mps2,
                        reason="Stopped before signalized corridor intersection",
                    )
                if self._is_crosswalk_occupied(agent, pedestrians):
                    return YieldDecision(
                        vehicle_id=vid,
                        action=YieldActionType.STOP_BEFORE_INTERSECTION,
                        effective_decel_mps2=self.config.yield_decel_mps2,
                        reason="Stopped before occupied crosswalk along corridor",
                    )

                decel = min(agent.config.max_deceleration_mps2, self.config.yield_decel_mps2)
                return YieldDecision(
                    vehicle_id=vid,
                    action=YieldActionType.YIELD_TO_EMERGENCY,
                    effective_decel_mps2=decel,
                    reason=f"Yielding to active corridor of {awareness.emergency_vehicle_id}",
                )

        # 3. Default: continue normal driving
        return YieldDecision(
            vehicle_id=vid,
            action=YieldActionType.CONTINUE,
            effective_decel_mps2=0.0,
            reason="No active emergency priority conflict",
        )

    @staticmethod
    def _is_at_red_signal(
        agent: VehicleAgent,
        signals: Sequence[TrafficSignalController],
    ) -> bool:
        """Check whether vehicle is approaching a RED signal on its active segment."""
        current_segment = getattr(agent, "current_segment", None)
        if not current_segment:
            return False
        edge_id = (
            getattr(current_segment, "edge_id", None)
            or getattr(agent.vehicle, "current_edge_id", None)
        )
        if not edge_id:
            return False
        for sig in signals:
            if sig.controls_edge(edge_id) and sig.state == TrafficSignalState.RED:
                # Approaching red signal near end of segment
                seg_len = getattr(current_segment, "length_m", 50.0)
                dist_along = getattr(agent, "distance_along_segment_m", 0.0)
                rem_dist = seg_len - dist_along
                if rem_dist <= 25.0:
                    return True
        return False

    @staticmethod
    def _is_crosswalk_occupied(
        agent: VehicleAgent,
        pedestrians: Optional[Sequence[PedestrianAgent]],
    ) -> bool:
        """Check whether pedestrians are actively crossing ahead."""
        if not pedestrians:
            return False
        for ped in pedestrians:
            if ped.state == PedestrianLifecycleState.CROSSING:
                dx = ped.position.x - agent.vehicle.position.x
                dy = ped.position.y - agent.vehicle.position.y
                dist = math.hypot(dx, dy)
                if dist <= 15.0:
                    return True
        return False
