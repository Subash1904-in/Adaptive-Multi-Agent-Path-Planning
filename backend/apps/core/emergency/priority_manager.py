"""Authoritative emergency priority manager, corridor coordinator, and state registry."""

from typing import Any, Optional, Sequence

from apps.core.domain.enums import TrafficSignalState
from apps.core.emergency.corridor_planner import EmergencyCorridorPlanner
from apps.core.emergency.exceptions import (
    DuplicateEmergencyActivationError,
    EmergencyVehicleNotFoundError,
    InvalidEmergencyStateError,
)
from apps.core.emergency.metrics import EmergencyMetrics
from apps.core.emergency.models import (
    CorridorReservation,
    EmergencyAwarenessRecord,
    EmergencyConfig,
    EmergencyCorridor,
    EmergencyEvent,
    EmergencyLifecycleState,
    EmergencyType,
    PriorityRequest,
    PriorityRequestStatus,
    SignalPriorityOverride,
    YieldActionType,
    YieldRequest,
    default_priority_level_for_type,
    validate_emergency_transition,
)
from apps.core.emergency.yielding_policy import YieldingPolicy
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.models import PedestrianLifecycleState
from apps.core.signals.controller import TrafficSignalController


class EmergencyPriorityManager:
    """Central authority coordinating emergency vehicle lifecycle, corridors, and priority."""

    def __init__(self, road_graph: RoadGraph, config: Optional[EmergencyConfig] = None) -> None:
        self.road_graph = road_graph
        self.config = config or EmergencyConfig()
        self.corridor_planner = EmergencyCorridorPlanner(road_graph, self.config)
        self.yielding_policy = YieldingPolicy(self.config)
        self.metrics = EmergencyMetrics()

        # Authoritative state stores
        self.active_requests: dict[str, PriorityRequest] = {}
        self.vehicle_to_request: dict[str, str] = {}
        self.vehicle_states: dict[str, EmergencyLifecycleState] = {}
        self.corridors: dict[str, EmergencyCorridor] = {}
        self.reservations: list[CorridorReservation] = []
        self.yield_requests: list[YieldRequest] = []
        self.signal_overrides: dict[str, SignalPriorityOverride] = {}
        self.local_awareness: dict[str, dict[str, EmergencyAwarenessRecord]] = {}

        self.events: list[EmergencyEvent] = []
        self._event_counter: int = 0
        self._request_counter: int = 0
        self._yield_counter: int = 0

    def register_emergency_vehicle(
        self,
        vehicle_id: str,
        initial_state: EmergencyLifecycleState = EmergencyLifecycleState.INACTIVE,
    ) -> None:
        """Register a vehicle identifier as an emergency-capable entity."""
        self.vehicle_states[vehicle_id] = initial_state

    def is_emergency_vehicle(self, vehicle_id: str) -> bool:
        """Check whether vehicle is registered as an emergency vehicle."""
        return vehicle_id in self.vehicle_states

    def get_vehicle_state(self, vehicle_id: str) -> EmergencyLifecycleState:
        """Get current emergency lifecycle state for vehicle."""
        return self.vehicle_states.get(vehicle_id, EmergencyLifecycleState.INACTIVE)

    def activate_emergency(
        self,
        vehicle_id: str,
        emergency_type: EmergencyType,
        destination_node_id: str,
        current_time_s: float,
        priority_level: Optional[int] = None,
        ttl_s: Optional[float] = None,
        start_node_id: Optional[str] = None,
    ) -> PriorityRequest:
        """Activate emergency mode and create a priority request.

        Idempotent: if already active with matching parameters, returns existing request.
        """
        if not self.config.enabled:
            raise InvalidEmergencyStateError("Emergency priority subsystem is disabled in config.")

        # Idempotency check
        if vehicle_id in self.vehicle_to_request:
            existing_req_id = self.vehicle_to_request[vehicle_id]
            existing_req = self.active_requests.get(existing_req_id)
            if existing_req and not existing_req.is_expired(current_time_s):
                if existing_req.destination_node_id == destination_node_id:
                    return existing_req
                else:
                    raise DuplicateEmergencyActivationError(
                        f"Vehicle '{vehicle_id}' already has an active priority request "
                        f"to destination '{existing_req.destination_node_id}'.",
                        vehicle_id=vehicle_id,
                    )

        # Transition validation
        curr_state = self.get_vehicle_state(vehicle_id)
        validate_emergency_transition(curr_state, EmergencyLifecycleState.REQUESTING_PRIORITY)
        self.vehicle_states[vehicle_id] = EmergencyLifecycleState.REQUESTING_PRIORITY

        self._request_counter += 1
        req_id = f"req_em_{self._request_counter:04d}_{vehicle_id}"
        p_lvl = (
            priority_level
            if priority_level is not None
            else default_priority_level_for_type(emergency_type)
        )
        req_ttl = ttl_s or self.config.default_request_ttl_s

        request = PriorityRequest(
            request_id=req_id,
            vehicle_id=vehicle_id,
            emergency_type=emergency_type,
            priority_level=p_lvl,
            destination_node_id=destination_node_id,
            creation_time_s=current_time_s,
            ttl_s=req_ttl,
            status=PriorityRequestStatus.PENDING,
        )

        self.active_requests[req_id] = request
        self.vehicle_to_request[vehicle_id] = req_id
        self.metrics.requests_created += 1

        self._log_event(
            event_type="EMERGENCY_ACTIVATED",
            vehicle_id=vehicle_id,
            emergency_type=emergency_type,
            request_id=req_id,
            sim_time_s=current_time_s,
            details={"priority_level": p_lvl, "destination": destination_node_id},
        )

        # Plan and commit initial corridor if start node provided
        if start_node_id:
            try:
                self.plan_and_commit_corridor(
                    request_id=req_id,
                    start_node_id=start_node_id,
                    current_time_s=current_time_s,
                )
            except Exception:
                # If pathfinding fails initially, request remains pending
                pass

        return request

    def plan_and_commit_corridor(
        self,
        request_id: Optional[str] = None,
        start_node_id: str = "",
        current_time_s: float = 0.0,
        closed_edge_ids: Optional[set[str]] = None,
        vehicle_id: Optional[str] = None,
    ) -> EmergencyCorridor:
        """Plan a feasible route corridor, resolve conflicts, and commit reservations."""
        actual_req_id = request_id
        if actual_req_id is None and vehicle_id is not None:
            actual_req_id = self.vehicle_to_request.get(vehicle_id)
        elif actual_req_id is not None and actual_req_id in self.vehicle_to_request:
            actual_req_id = self.vehicle_to_request[actual_req_id]

        if not actual_req_id or actual_req_id not in self.active_requests:
            raise EmergencyVehicleNotFoundError(
                f"Priority request '{actual_req_id or vehicle_id or request_id}' not found."
            )

        request = self.active_requests[actual_req_id]
        corridor = self.corridor_planner.plan_corridor(
            request=request,
            start_node_id=start_node_id,
            destination_node_id=request.destination_node_id,
            current_time_s=current_time_s,
            closed_edge_ids=closed_edge_ids,
        )

        # Evaluate reservations against existing reservations
        granted_res, conflicts = self.corridor_planner.evaluate_and_create_reservations(
            corridor=corridor,
            request=request,
            existing_reservations=self.reservations,
            current_time_s=current_time_s,
        )

        if conflicts:
            self.metrics.corridor_conflicts += len(conflicts)
            self._log_event(
                event_type="CORRIDOR_CONFLICT",
                vehicle_id=request.vehicle_id,
                emergency_type=request.emergency_type,
                request_id=request_id,
                corridor_id=corridor.corridor_id,
                sim_time_s=current_time_s,
                details={"conflicts": conflicts},
            )

        # Commit corridor and reservations
        self.corridors[corridor.corridor_id] = corridor
        request.corridor_id = corridor.corridor_id
        request.status = PriorityRequestStatus.ACTIVE

        # Clean old reservations for this vehicle/request
        self.reservations = [
            r
            for r in self.reservations
            if r.request_id != request_id and not r.is_expired(current_time_s)
        ]
        self.reservations.extend(granted_res)

        validate_emergency_transition(
            self.get_vehicle_state(request.vehicle_id), EmergencyLifecycleState.PRIORITY_ACTIVE
        )
        self.vehicle_states[request.vehicle_id] = EmergencyLifecycleState.PRIORITY_ACTIVE

        self.metrics.corridors_created += 1
        self.metrics.requests_accepted += 1

        self._log_event(
            event_type="CORRIDOR_COMMITTED",
            vehicle_id=request.vehicle_id,
            emergency_type=request.emergency_type,
            request_id=request_id,
            corridor_id=corridor.corridor_id,
            sim_time_s=current_time_s,
            details={
                "edges": list(corridor.edge_ids),
                "nodes": list(corridor.node_ids),
                "reservations_count": len(granted_res),
            },
        )
        return corridor

    def deactivate_emergency(
        self,
        vehicle_id: str,
        current_time_s: float,
        reason: str = "completed",
    ) -> None:
        """Deactivate emergency mode, release reservations, and mark request completed."""
        curr_state = self.get_vehicle_state(vehicle_id)
        if curr_state in (EmergencyLifecycleState.COMPLETED, EmergencyLifecycleState.CANCELLED):
            return  # Idempotent

        new_state = (
            EmergencyLifecycleState.COMPLETED
            if reason == "completed"
            else EmergencyLifecycleState.CANCELLED
        )
        try:
            validate_emergency_transition(curr_state, new_state)
            self.vehicle_states[vehicle_id] = new_state
        except Exception:
            self.vehicle_states[vehicle_id] = new_state

        req_id = self.vehicle_to_request.pop(vehicle_id, None)
        if req_id and req_id in self.active_requests:
            req = self.active_requests[req_id]
            req.status = (
                PriorityRequestStatus.COMPLETED
                if reason == "completed"
                else PriorityRequestStatus.CANCELLED
            )
            req.reason = reason

            if reason == "completed":
                self.metrics.requests_completed += 1
                self.metrics.total_emergency_travel_time_s += max(
                    0.0, current_time_s - req.creation_time_s
                )
            else:
                self.metrics.requests_cancelled += 1

            if req.corridor_id and req.corridor_id in self.corridors:
                corr = self.corridors[req.corridor_id]
                corr.is_active = False
                corr.is_released = True

        # Release reservations associated with vehicle
        self.reservations = [r for r in self.reservations if r.vehicle_id != vehicle_id]

        # Release signal overrides
        self.signal_overrides = {
            sig_id: ovr
            for sig_id, ovr in self.signal_overrides.items()
            if ovr.emergency_vehicle_id != vehicle_id
        }

        # Clear yield requests
        self.yield_requests = [
            yr for yr in self.yield_requests if yr.emergency_vehicle_id != vehicle_id
        ]

        self._log_event(
            event_type="EMERGENCY_COMPLETED" if reason == "completed" else "PRIORITY_CANCELLED",
            vehicle_id=vehicle_id,
            request_id=req_id,
            sim_time_s=current_time_s,
            details={"reason": reason},
        )

    def cancel_priority(
        self, vehicle_id: str, current_time_s: float, reason: str = "cancelled"
    ) -> None:
        """Cancel active priority request and release associated reservations."""
        self.deactivate_emergency(
            vehicle_id=vehicle_id, current_time_s=current_time_s, reason=reason
        )

    def get_active_corridor(self, vehicle_id: str) -> Optional[EmergencyCorridor]:
        """Retrieve active corridor for emergency vehicle, if any."""
        req_id = self.vehicle_to_request.get(vehicle_id)
        if not req_id:
            return None
        req = self.active_requests.get(req_id)
        if not req or not req.corridor_id:
            return None
        corridor = self.corridors.get(req.corridor_id)
        if corridor and corridor.is_active:
            return corridor
        return None

    def get_active_reservations(self) -> list[CorridorReservation]:
        """Return all currently held reservations."""
        return list(self.reservations)

    def evaluate_signal_priority(
        self,
        signals: Sequence[TrafficSignalController],
        pedestrians: Optional[Sequence[PedestrianAgent]],
        current_time_s: float,
    ) -> dict[str, SignalPriorityOverride]:
        """Evaluate traffic signal priority requests for upcoming corridor intersections."""
        if not self.config.signal_priority_enabled:
            return {}

        active_nodes_in_corridors: dict[str, tuple[str, PriorityRequest]] = {}
        for corr in self.corridors.values():
            if corr.is_active and not corr.is_expired(current_time_s):
                req = self.active_requests.get(corr.request_id)
                if req and req.status == PriorityRequestStatus.ACTIVE:
                    for nid in corr.node_ids:
                        active_nodes_in_corridors[nid] = (corr.corridor_id, req)

        # Evaluate each signal controlling an intersection node in an active corridor
        for sig in signals:
            if sig.node_id in active_nodes_in_corridors:
                corr_id, req = active_nodes_in_corridors[sig.node_id]

                # Check if pedestrians are actively crossing at this intersection's crosswalks
                pedestrians_crossing = False
                if pedestrians:
                    sig_pos = getattr(sig.signal, "position", None)
                    if (
                        sig_pos is None
                        and hasattr(sig, "road_graph")
                        and sig.road_graph
                        and sig.road_graph.has_node(sig.node_id)
                    ):
                        sig_pos = sig.road_graph.get_node(sig.node_id).position

                    for ped in pedestrians:
                        if ped.state == PedestrianLifecycleState.CROSSING:
                            if sig_pos is not None and ped.position is not None:
                                dx = ped.position.x - sig_pos.x
                                dy = ped.position.y - sig_pos.y
                                dist = (dx * dx + dy * dy) ** 0.5
                                if dist <= 25.0:
                                    pedestrians_crossing = True
                                    break
                            else:
                                pedestrians_crossing = True
                                break

                if pedestrians_crossing:
                    # Invariant: Pedestrians already crossing have absolute clearance priority!
                    self.metrics.signal_priority_denials += 1
                    override = SignalPriorityOverride(
                        request_id=req.request_id,
                        signal_id=sig.id,
                        node_id=sig.node_id,
                        emergency_vehicle_id=req.vehicle_id,
                        desired_phase=TrafficSignalState.GREEN,
                        held_until_s=current_time_s,
                        is_granted=False,
                        reason="Pedestrian clearance in progress",
                    )
                    self.signal_overrides[sig.id] = override
                    if hasattr(sig, "clear_priority_override"):
                        sig.clear_priority_override()
                    continue

                # Grant priority: hold GREEN or grant priority override
                held_until = current_time_s + self.config.signal_hold_green_duration_s
                override = SignalPriorityOverride(
                    request_id=req.request_id,
                    signal_id=sig.id,
                    node_id=sig.node_id,
                    emergency_vehicle_id=req.vehicle_id,
                    desired_phase=TrafficSignalState.GREEN,
                    held_until_s=held_until,
                    is_granted=True,
                    reason="Corridor intersection priority granted",
                )
                self.signal_overrides[sig.id] = override
                self.metrics.signal_priority_grants += 1

                # If signal controller supports priority override, set it
                if hasattr(sig, "apply_priority_override"):
                    sig.apply_priority_override(
                        TrafficSignalState.GREEN,
                        self.config.signal_hold_green_duration_s,
                        current_time_s,
                        req.request_id,
                    )
                else:
                    sig.signal.state = TrafficSignalState.GREEN

        return self.signal_overrides

    def generate_yield_requests_for_corridor(
        self,
        corridor: EmergencyCorridor,
        agents: Sequence[VehicleAgent],
        current_time_s: float,
    ) -> list[YieldRequest]:
        """Issue yield requests to non-emergency vehicles on corridor edges."""
        req = self.active_requests.get(corridor.request_id)
        if not req:
            return []

        em_id = corridor.vehicle_id
        new_yields: list[YieldRequest] = []

        for agent in agents:
            vid = agent.vehicle.id
            if vid == em_id or self.is_emergency_vehicle(vid):
                continue

            curr_edge = agent.vehicle.current_edge_id
            if curr_edge and corridor.contains_edge(curr_edge):
                self._yield_counter += 1
                y_id = f"yield_{self._yield_counter:04d}_{vid}"
                yr = YieldRequest(
                    yield_id=y_id,
                    emergency_vehicle_id=em_id,
                    target_vehicle_id=vid,
                    edge_id=curr_edge,
                    node_id=None,
                    recommended_action=YieldActionType.YIELD_TO_EMERGENCY,
                    target_speed_mps=0.0,
                    target_decel_mps2=self.config.yield_decel_mps2,
                    creation_time_s=current_time_s,
                    expiry_time_s=current_time_s + 15.0,
                )
                new_yields.append(yr)
                self.metrics.yield_requests_issued += 1

        self.yield_requests.extend(new_yields)
        return new_yields

    def perform_maintenance(self, current_time_s: float) -> None:
        """Expire stale requests, corridors, reservations, and yield requests."""
        # 1. Expire stale priority requests
        for req_id, req in list(self.active_requests.items()):
            if req.status in (PriorityRequestStatus.PENDING, PriorityRequestStatus.ACTIVE):
                if req.is_expired(current_time_s):
                    req.status = PriorityRequestStatus.EXPIRED
                    self.metrics.requests_expired += 1
                    if req.vehicle_id in self.vehicle_states:
                        self.vehicle_states[req.vehicle_id] = EmergencyLifecycleState.INACTIVE
                    self.vehicle_to_request.pop(req.vehicle_id, None)

        # 2. Expire corridors
        for corr_id, corr in list(self.corridors.items()):
            if corr.is_active and corr.is_expired(current_time_s):
                corr.is_active = False
                corr.is_released = True

        # 3. Filter reservations
        self.reservations = [r for r in self.reservations if not r.is_expired(current_time_s)]

        # 4. Filter yield requests
        self.yield_requests = [y for y in self.yield_requests if not y.is_expired(current_time_s)]

        # 5. Filter signal overrides
        self.signal_overrides = {
            s_id: ovr
            for s_id, ovr in self.signal_overrides.items()
            if not ovr.is_expired(current_time_s)
        }

        # 6. Update point-in-time gauges
        active_em = sum(
            1
            for s in self.vehicle_states.values()
            if s
            in (
                EmergencyLifecycleState.REQUESTING_PRIORITY,
                EmergencyLifecycleState.PRIORITY_ACTIVE,
            )
        )
        self.metrics.active_emergency_vehicles = active_em
        self.metrics.active_corridors = sum(1 for c in self.corridors.values() if c.is_active)

    def get_all_emergency_vehicles(self) -> list[str]:
        """List all registered emergency vehicle identifiers."""
        return sorted(self.vehicle_states.keys())

    def get_registered_vehicles(self) -> list[str]:
        """List all registered emergency vehicle identifiers (alias)."""
        return self.get_all_emergency_vehicles()

    def get_awareness(self, vehicle_id: str) -> Optional[EmergencyAwarenessRecord]:
        """Retrieve highest-priority active emergency awareness record for vehicle."""
        store = self.local_awareness.get(vehicle_id)
        if not store:
            return None
        active = [r for r in store.values() if r.is_active]
        if not active:
            return None
        active.sort(key=lambda r: (r.priority_level, r.last_updated_s), reverse=True)
        return active[0]

    def evaluate_yielding_for_vehicles(
        self,
        agents: Sequence[VehicleAgent],
        signals: Sequence[TrafficSignalController],
        pedestrians: Optional[Sequence[PedestrianAgent]] = None,
        current_time_s: float = 0.0,
    ) -> dict[str, Any]:
        """Evaluate yielding decisions for all registered non-emergency vehicles."""
        decisions: dict[str, Any] = {}
        emergency_agents = [a for a in agents if self.is_emergency_vehicle(a.vehicle.id)]
        active_corrs = [
            c for c in self.corridors.values() if c.is_active and not c.is_expired(current_time_s)
        ]

        for agent in agents:
            vid = agent.vehicle.id
            if self.is_emergency_vehicle(vid):
                continue
            awareness = self.get_awareness(vid)
            dec = self.yielding_policy.evaluate_vehicle_yield(
                agent=agent,
                awareness=awareness,
                corridors=active_corrs,
                signals=signals,
                pedestrians=pedestrians,
                yield_requests=self.yield_requests,
                emergency_agents=emergency_agents,
                current_time_s=current_time_s,
            )
            decisions[vid] = dec
            if dec.action != YieldActionType.CONTINUE:
                self.metrics.yield_decisions_executed += 1
        return decisions

    def _log_event(
        self,
        event_type: str,
        vehicle_id: str,
        sim_time_s: float,
        emergency_type: Optional[EmergencyType] = None,
        request_id: Optional[str] = None,
        corridor_id: Optional[str] = None,
        target_vehicle_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an immutable audit event."""
        if not self.config.log_events:
            return
        self._event_counter += 1
        evt = EmergencyEvent(
            event_id=f"em_evt_{self._event_counter:05d}",
            sim_time_s=sim_time_s,
            event_type=event_type,
            vehicle_id=vehicle_id,
            emergency_type=emergency_type,
            request_id=request_id,
            corridor_id=corridor_id,
            target_vehicle_id=target_vehicle_id,
            details=details or {},
        )
        self.events.append(evt)

    def capture_state(self) -> dict[str, Any]:
        """Capture deep copy of entire manager state for atomic rollback."""
        return {
            "active_requests": {
                k: PriorityRequest(**v.__dict__) for k, v in self.active_requests.items()
            },
            "vehicle_to_request": dict(self.vehicle_to_request),
            "vehicle_states": dict(self.vehicle_states),
            "corridors": {k: EmergencyCorridor(**v.__dict__) for k, v in self.corridors.items()},
            "reservations": [CorridorReservation(**r.__dict__) for r in self.reservations],
            "yield_requests": [YieldRequest(**y.__dict__) for y in self.yield_requests],
            "signal_overrides": {
                k: SignalPriorityOverride(**v.__dict__)
                for k, v in self.signal_overrides.items()
            },
            "local_awareness": {
                vid: {
                    em_id: EmergencyAwarenessRecord(**rec.__dict__)
                    for em_id, rec in store.items()
                }
                for vid, store in self.local_awareness.items()
            },
            "metrics": self.metrics.capture_state(),
            "events": list(self.events),
            "event_counter": self._event_counter,
            "request_counter": self._request_counter,
            "yield_counter": self._yield_counter,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Atomically restore entire manager state from snapshot."""
        self.active_requests = {
            k: PriorityRequest(**v.__dict__) for k, v in state["active_requests"].items()
        }
        self.vehicle_to_request = dict(state["vehicle_to_request"])
        self.vehicle_states = dict(state["vehicle_states"])
        self.corridors = {k: EmergencyCorridor(**v.__dict__) for k, v in state["corridors"].items()}
        self.reservations = [CorridorReservation(**r.__dict__) for r in state["reservations"]]
        self.yield_requests = [YieldRequest(**y.__dict__) for y in state["yield_requests"]]
        self.signal_overrides = {
            k: SignalPriorityOverride(**v.__dict__) for k, v in state["signal_overrides"].items()
        }
        self.local_awareness = {
            vid: {em_id: EmergencyAwarenessRecord(**rec.__dict__) for em_id, rec in store.items()}
            for vid, store in state["local_awareness"].items()
        }
        self.metrics.restore_state(state["metrics"])
        self.events = list(state["events"])
        self._event_counter = state["event_counter"]
        self._request_counter = state["request_counter"]
        self._yield_counter = state["yield_counter"]

    def reset(self) -> None:
        """Reset manager to clean initial state."""
        self.active_requests.clear()
        self.vehicle_to_request.clear()
        self.vehicle_states.clear()
        self.corridors.clear()
        self.reservations.clear()
        self.yield_requests.clear()
        self.signal_overrides.clear()
        self.local_awareness.clear()
        self.events.clear()
        self._event_counter = 0
        self._request_counter = 0
        self._yield_counter = 0
        self.metrics.reset()
