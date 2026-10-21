"""SimulationEngine orchestrating authoritative clock and vehicle-agent stepping.

Implements deterministic ordered tick sequencing, atomic tick rollback on failure,
pause/resume/single-step semantics, and point-in-time snapshot access.
"""

from typing import Any, Optional

from apps.core.communication.models import V2VMessagePacket
from apps.core.communication.neighbors import NeighborRecord, NeighborTable
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import TrafficReport
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D
from apps.core.emergency.models import EmergencyLifecycleState, YieldActionType
from apps.core.emergency.v2v import ingest_emergency_message_into_awareness
from apps.core.kinematics.models import MotionStepResult
from apps.core.pedestrians.models import PedestrianSignalState
from apps.core.safety.models import SafetyEventType
from apps.core.signals.models import SignalQueryResult
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.exceptions import EngineStateError, TickExecutionError
from apps.core.simulation.models import EngineStatus, TickResult, WorldSnapshot
from apps.core.simulation.world import WorldState


class SimulationEngine:
    """Simulation execution coordinator and authoritative tick sequencer.

    Orchestrates the SimulationClock and WorldState, ensuring that all eligible agents
    receive identical discrete time steps, deterministic iteration ordering, and
    atomic rollback guarantees if an unexpected error occurs during stepping.
    """

    def __init__(self, world: WorldState) -> None:
        """Initialize the simulation engine with a world state.

        Args:
            world: Authoritative WorldState container.

        Raises:
            TypeError: If world is not an instance of WorldState.
        """
        if not isinstance(world, WorldState):
            raise TypeError(f"Expected WorldState instance, got {type(world).__name__}.")

        self.world: WorldState = world
        self.status: EngineStatus = EngineStatus.INITIALIZED
        self.last_tick_result: Optional[TickResult] = None

    @property
    def clock(self) -> SimulationClock:
        """Authoritative SimulationClock belonging to the world state."""
        return self.world.clock

    @property
    def time_step_s(self) -> float:
        """Fixed discrete step size in seconds."""
        return self.clock.time_step_s

    @property
    def current_tick(self) -> int:
        """Current integer tick count."""
        return self.clock.tick_count

    @property
    def elapsed_time_s(self) -> float:
        """Current simulated elapsed time in seconds."""
        return self.clock.elapsed_time_s

    @property
    def is_paused(self) -> bool:
        """True if the engine or clock is paused."""
        return self.status == EngineStatus.PAUSED or self.clock.is_paused

    @property
    def is_running(self) -> bool:
        """True if the engine is running and unpaused."""
        return self.status == EngineStatus.RUNNING and self.clock.is_running

    def pause(self) -> None:
        """Pause simulation execution.

        Idempotent if already paused. Preserves agent positions and route progress.
        """
        self.status = EngineStatus.PAUSED
        self.world.clock.pause()

    def resume(self) -> None:
        """Resume simulation execution from a paused state.

        Raises:
            EngineStateError: If the engine is in a FAILED state.
        """
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot resume an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )
        self.status = EngineStatus.RUNNING
        self.world.clock.resume()

    def stop(self) -> None:
        """Stop simulation execution."""
        self.status = EngineStatus.STOPPED

    def reset(self) -> None:
        """Reset the simulation world and clock to initial baseline states.

        Restores all registered vehicles to their initial registration positions,
        speeds, headings, and states, and resets tick counter and elapsed time to 0.
        """
        self.world.reset()
        self.status = EngineStatus.INITIALIZED
        self.last_tick_result = None

    def step(self, target_accels: Optional[dict[str, float]] = None) -> TickResult:
        """Advance the entire simulation world by exactly one discrete time step dt.

        Execution ordering:
        1. Validates engine status.
        2. Determines eligible agents in stable identifier order.
        3. Captures lightweight rollback states of all agents.
        4. Advances each agent with identical dt.
           If any agent fails, rolls back all agents atomically and marks engine FAILED.
        5. Advances the authoritative clock exactly once.
        6. Constructs and returns the immutable TickResult.

        Args:
            target_accels: Optional mapping of vehicle_id to commanded acceleration in m/s^2.

        Returns:
            TickResult containing tick index, elapsed time, and per-agent motion results.

        Raises:
            EngineStateError: If the engine is in FAILED or STOPPED state.
            TickExecutionError: If any agent stepping fails (with atomic rollback applied).
        """
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot step an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )
        if self.status == EngineStatus.STOPPED:
            raise EngineStateError(
                "Cannot step an engine in STOPPED state.",
                current_state=self.status.value,
            )

        # Allow single-stepping while paused; otherwise ensure status is RUNNING
        is_single_step = self.is_paused
        if self.status == EngineStatus.INITIALIZED and not is_single_step:
            self.status = EngineStatus.RUNNING

        agents = self.world.get_agents()
        dt = self.clock.time_step_s

        # 1. Capture atomic rollback snapshots of agents, signals, communication, and routing
        rollback_states: dict[str, tuple] = {}
        for agent in agents:
            v = agent.vehicle
            rollback_states[v.id] = (
                agent.state,
                Position2D(x=v.position.x, y=v.position.y),
                v.heading_rad,
                v.speed_mps,
                v.current_node_id,
                v.current_edge_id,
                agent.current_edge_index,
                agent.distance_along_segment_m,
                agent.route,
                list(agent._segments),
                agent.total_route_distance_m,
                v.route_id,
                v.target_node_id,
            )

        signal_rollback_states: dict[str, tuple] = {
            ctrl.id: (
                ctrl.signal.state,
                ctrl.signal.remaining_phase_s,
                (
                    ctrl.get_priority_override_state()
                    if hasattr(ctrl, "get_priority_override_state")
                    else (None, 0.0, None)
                ),
            )
            for ctrl in self.world.get_signals()
        }

        pedestrian_rollback_states: dict[str, dict[str, Any]] = {
            ped.pedestrian_id: ped.capture_state()
            for ped in self.world.get_pedestrians()
        }
        pedestrian_metrics_rollback = self.world.pedestrian_metrics.capture_state()

        comm_rollback = None
        sched_rollback = None
        coord_rollback = None
        routing_rollback = None
        safety_rollback = None
        emergency_rollback = None
        if self.world.communication_network.config.enabled:
            comm_rollback = self.world.communication_network.capture_state()
            sched_rollback = self.world.broadcast_scheduler.capture_state()
        if self.world.coordination_manager.config.enabled:
            coord_rollback = self.world.coordination_manager.capture_state()
        if (
            hasattr(self.world, "adaptive_routing_adapter")
            and self.world.adaptive_routing_adapter
            and self.world.adaptive_routing_adapter.config.enabled
        ):
            routing_rollback = self.world.adaptive_routing_adapter.capture_state()
        if (
            hasattr(self.world, "safety_manager")
            and self.world.safety_manager
            and self.world.safety_manager.config.enabled
        ):
            safety_rollback = self.world.safety_manager.capture_state()
        if hasattr(self.world, "emergency_manager") and self.world.emergency_manager:
            emergency_rollback = self.world.emergency_manager.capture_state()
        decision_rollback = None
        if (
            hasattr(self.world, "decision_manager")
            and self.world.decision_manager
            and self.world.decision_manager.config.enabled
        ):
            decision_rollback = self.world.decision_manager.capture_state()

        # 2. Advance communication network tick (moves transit messages to inboxes)
        if self.world.communication_network.config.enabled:
            self.world.communication_network.advance_tick(self.clock.elapsed_time_s)

            candidate_positions = {
                agent.vehicle.id: Position2D(x=agent.vehicle.position.x, y=agent.vehicle.position.y)
                for agent in agents
            }

            # Ingest valid received messages into neighbor tables
            self.world.communication_network.update_neighbor_tables(
                candidate_positions=candidate_positions,
                current_time_s=self.clock.elapsed_time_s,
            )

            # Perform heartbeat timeout and neighbor expiration maintenance
            self.world.communication_network.perform_neighbor_maintenance(
                current_time_s=self.clock.elapsed_time_s,
            )

            # Perform due periodic status broadcasts before agent motion
            for agent in agents:
                vid = agent.vehicle.id
                if self.world.broadcast_scheduler.is_broadcast_due(vid, self.clock.elapsed_time_s):
                    broadcast_packet = self.world.broadcast_scheduler.create_broadcast(
                        vehicle=agent,
                        current_time_s=self.clock.elapsed_time_s,
                    )
                    self.world.communication_network.broadcast(
                        message=broadcast_packet,
                        candidate_positions=candidate_positions,
                        current_time_s=self.clock.elapsed_time_s,
                    )

            # If same-tick delivery is active, process newly broadcasted packets
            # into neighbor tables
            self.world.communication_network.update_neighbor_tables(
                candidate_positions=candidate_positions,
                current_time_s=self.clock.elapsed_time_s,
            )

            # Ingest coordination reports from inboxes and process multi-hop forwarding
            if self.world.coordination_manager.config.enabled:
                all_fwd_packets = []
                for agent in agents:
                    vid = agent.vehicle.id
                    inbox = self.world.communication_network.get_inbox(vid)
                    if inbox:
                        fwd_packets = self.world.coordination_manager.process_inbox_messages(
                            vehicle_id=vid,
                            inbox_packets=inbox,
                            vehicle_position=Position2D(
                                x=agent.vehicle.position.x, y=agent.vehicle.position.y
                            ),
                            vehicle_heading_rad=agent.vehicle.heading_rad,
                            vehicle_speed_mps=agent.vehicle.speed_mps,
                            current_time_s=self.clock.elapsed_time_s,
                        )
                        all_fwd_packets.extend(fwd_packets)

                for fwd_pkt in all_fwd_packets:
                    self.world.communication_network.broadcast(
                        message=fwd_pkt,
                        candidate_positions=candidate_positions,
                        current_time_s=self.clock.elapsed_time_s,
                    )

                self.world.coordination_manager.perform_maintenance(
                    current_time_s=self.clock.elapsed_time_s,
                )

            # Ingest emergency V2V messages from inboxes into local awareness
            if (
                hasattr(self.world, "emergency_manager")
                and self.world.emergency_manager
                and self.world.emergency_manager.config.enabled
            ):
                emergency_msg_types = {
                    V2VMessageType.EMERGENCY_ACTIVATED,
                    V2VMessageType.PRIORITY_REQUEST,
                    V2VMessageType.CORRIDOR_PROPOSED,
                    V2VMessageType.YIELD_REQUEST,
                    V2VMessageType.YIELD_ACKNOWLEDGED,
                    V2VMessageType.CORRIDOR_UPDATED,
                    V2VMessageType.PRIORITY_CANCELLED,
                    V2VMessageType.EMERGENCY_COMPLETED,
                }
                for agent in agents:
                    vid = agent.vehicle.id
                    inbox = self.world.communication_network.get_inbox(vid)
                    if inbox:
                        vid_store = self.world.emergency_manager.local_awareness.setdefault(vid, {})
                        for pkt in inbox:
                            if pkt.message_type in emergency_msg_types:
                                ingest_emergency_message_into_awareness(
                                    packet=pkt,
                                    awareness_store=vid_store,
                                    current_time_s=self.clock.elapsed_time_s,
                                )

        # 2.5, 2.7 & 3. Evaluate adaptive rerouting, safety overrides, yielding,
        # and advance each agent
        step_results: dict[str, MotionStepResult] = {}
        pedestrian_step_results: dict[str, Any] = {}
        routing_decisions = []
        safety_overrides = {}
        safety_events = []
        yield_decisions = {}
        try:
            # Perform emergency priority manager maintenance (expirations, TTL cleanup)
            if hasattr(self.world, "emergency_manager") and self.world.emergency_manager:
                self.world.emergency_manager.perform_maintenance(
                    current_time_s=self.clock.elapsed_time_s
                )

            # Evaluate emergency signal priority and vehicle yielding decisions
            if (
                hasattr(self.world, "emergency_manager")
                and self.world.emergency_manager
                and self.world.emergency_manager.config.enabled
            ):
                for agent in agents:
                    vid = agent.vehicle.id
                    if self.world.emergency_manager.is_emergency_vehicle(vid):
                        st = self.world.emergency_manager.get_vehicle_state(vid)
                        if st in (
                            EmergencyLifecycleState.REQUESTING_PRIORITY,
                            EmergencyLifecycleState.PRIORITY_ACTIVE,
                        ):
                            if not self.world.emergency_manager.get_active_corridor(vid):
                                start_node = agent.vehicle.current_node_id or (
                                    agent.route.node_ids[0]
                                    if agent.route and agent.route.node_ids
                                    else None
                                )
                                if start_node:
                                    try:
                                        self.world.emergency_manager.plan_and_commit_corridor(
                                            vehicle_id=vid,
                                            start_node_id=start_node,
                                            current_time_s=self.clock.elapsed_time_s,
                                        )
                                    except Exception:
                                        pass

                self.world.emergency_manager.evaluate_signal_priority(
                    signals=self.world.get_signals(),
                    pedestrians=self.world.get_pedestrians(),
                    current_time_s=self.clock.elapsed_time_s,
                )
                yield_decisions = self.world.emergency_manager.evaluate_yielding_for_vehicles(
                    agents=agents,
                    signals=self.world.get_signals(),
                    pedestrians=self.world.get_pedestrians(),
                    current_time_s=self.clock.elapsed_time_s,
                )

            if (
                hasattr(self.world, "adaptive_routing_adapter")
                and self.world.adaptive_routing_adapter
                and self.world.adaptive_routing_adapter.config.enabled
            ):
                for agent in agents:
                    vid = agent.vehicle.id
                    k_store = (
                        self.world.coordination_manager.get_store(vid)
                        if self.world.coordination_manager.config.enabled
                        else None
                    )
                    dec = self.world.adaptive_routing_adapter.evaluate_agent(
                        agent=agent,
                        knowledge_store=k_store,
                        current_time_s=self.clock.elapsed_time_s,
                    )
                    routing_decisions.append(dec)

            # Evaluate safety detection and stage collision avoidance overrides
            if (
                hasattr(self.world, "safety_manager")
                and self.world.safety_manager
                and self.world.safety_manager.config.enabled
            ):
                scenario_id = self.world.metadata.get("scenario_id")
                (
                    safety_overrides,
                    _pair_conflicts,
                    safety_events,
                ) = self.world.safety_manager.evaluate_and_stage(
                    agents=agents,
                    current_time_s=self.clock.elapsed_time_s,
                    scenario_id=scenario_id,
                    pedestrians=self.world.get_pedestrians(),
                )
                for evt in safety_events:
                    if evt.pedestrian_id:
                        self.world.pedestrian_metrics.record_safety_event(
                            is_collision=evt.is_overlap,
                            is_near_miss=(evt.event_type == SafetyEventType.NEAR_MISS),
                        )

            # Advance vehicles
            for agent in agents:
                vid = agent.vehicle.id
                caller_accel = target_accels.get(vid) if target_accels else None

                # Yielding deceleration calculation
                yielding_accel = None
                if vid in yield_decisions:
                    y_dec = yield_decisions[vid]
                    if y_dec.action in (
                        YieldActionType.YIELD_TO_EMERGENCY,
                        YieldActionType.STOP_BEFORE_INTERSECTION,
                        YieldActionType.CLEAR_CORRIDOR,
                        YieldActionType.REDUCE_SPEED,
                    ):
                        yielding_accel = -abs(y_dec.effective_decel_mps2)

                if caller_accel is not None and yielding_accel is not None:
                    effective_accel = min(caller_accel, yielding_accel)
                elif yielding_accel is not None:
                    effective_accel = yielding_accel
                else:
                    effective_accel = caller_accel

                if vid in safety_overrides:
                    # Safety deceleration override takes supreme precedence over all movement
                    safety_accel = safety_overrides[vid].target_acceleration_mps2
                    if effective_accel is not None:
                        effective_accel = min(effective_accel, safety_accel)
                    else:
                        effective_accel = safety_accel

                step_res = agent.step(dt=dt, target_accel=effective_accel)
                step_results[vid] = step_res

            # Advance pedestrians
            current_signal_states = {c.id: c.signal.state for c in self.world.get_signals()}
            for ped in self.world.get_pedestrians():
                cw = None
                ped_sig = PedestrianSignalState.WALK
                if ped.current_crosswalk_id and self.world.has_crosswalk(ped.current_crosswalk_id):
                    cw = self.world.get_crosswalk(ped.current_crosswalk_id)
                    ped_sig = cw.get_pedestrian_signal_state(current_signal_states)

                ped_res = ped.step(
                    dt=dt,
                    crosswalk=cw,
                    signal_state=ped_sig,
                )
                pedestrian_step_results[ped.pedestrian_id] = ped_res
                self.world.pedestrian_metrics.record_step(ped_res)

            self.world.pedestrian_metrics.update_point_in_time_counts(
                self.world.get_pedestrians()
            )
        except Exception as exc:
            # Atomic rollback: restore all agents, signals, comms, coord, routing,
            # safety, pedestrians
            for agent in agents:
                vid = agent.vehicle.id
                if vid in rollback_states:
                    (
                        r_state,
                        r_pos,
                        r_heading,
                        r_speed,
                        r_nid,
                        r_eid,
                        r_eidx,
                        r_dist,
                        r_route,
                        r_segs,
                        r_tot_dist,
                        r_rid,
                        r_tid,
                    ) = rollback_states[vid]
                    agent.vehicle.state = r_state
                    agent.vehicle.position = Position2D(x=r_pos.x, y=r_pos.y)
                    agent.vehicle.heading_rad = r_heading
                    agent.vehicle.speed_mps = r_speed
                    agent.vehicle.current_node_id = r_nid
                    agent.vehicle.current_edge_id = r_eid
                    agent.current_edge_index = r_eidx
                    agent.distance_along_segment_m = r_dist
                    agent.route = r_route
                    agent._segments = list(r_segs)
                    agent.total_route_distance_m = r_tot_dist
                    agent.vehicle.route_id = r_rid
                    agent.vehicle.target_node_id = r_tid

            for ctrl in self.world.get_signals():
                if ctrl.id in signal_rollback_states:
                    r_sig_state, r_sig_rem, r_override = signal_rollback_states[ctrl.id]
                    ctrl.signal.state = r_sig_state
                    ctrl.signal.remaining_phase_s = r_sig_rem
                    if hasattr(ctrl, "restore_priority_override_state"):
                        ctrl.restore_priority_override_state(*r_override)

            for ped in self.world.get_pedestrians():
                if ped.pedestrian_id in pedestrian_rollback_states:
                    ped.restore_state(pedestrian_rollback_states[ped.pedestrian_id])
            if pedestrian_metrics_rollback is not None:
                self.world.pedestrian_metrics.restore_state(pedestrian_metrics_rollback)

            if comm_rollback is not None:
                self.world.communication_network.restore_state(comm_rollback)
            if sched_rollback is not None:
                self.world.broadcast_scheduler.restore_state(sched_rollback)
            if coord_rollback is not None:
                self.world.coordination_manager.restore_state(coord_rollback)
            if routing_rollback is not None and hasattr(self.world, "adaptive_routing_adapter"):
                self.world.adaptive_routing_adapter.restore_state(routing_rollback)
            if safety_rollback is not None and hasattr(self.world, "safety_manager"):
                self.world.safety_manager.restore_state(safety_rollback)
            if emergency_rollback is not None and hasattr(self.world, "emergency_manager"):
                self.world.emergency_manager.restore_state(emergency_rollback)
            if decision_rollback is not None and hasattr(self.world, "decision_manager"):
                self.world.decision_manager.restore_state(decision_rollback)

            self.status = EngineStatus.FAILED
            raise TickExecutionError(
                f"Tick {self.clock.tick_count + 1} failed during agent execution: {exc}",
                tick=self.clock.tick_count + 1,
                cause=exc,
            ) from exc

        # 4. Advance authoritative clock exactly once
        new_tick = self.clock.tick(force=is_single_step)

        # 5. Synchronize all traffic signals to new simulation time
        self.world.update_signals(self.clock.elapsed_time_s)

        # 6. Construct typed tick result
        arrived_ids = [vid for vid, r in step_results.items() if r.arrived]
        active_ids = [vid for vid, r in step_results.items() if not r.arrived]
        signal_states = {c.id: c.signal.state for c in self.world.get_signals()}
        comm_metrics = None
        if self.world.communication_network.config.enabled:
            comm_metrics = self.world.communication_network.metrics.to_dict()

        coord_metrics = None
        if self.world.coordination_manager.config.enabled:
            coord_metrics = self.world.coordination_manager.metrics.to_dict()

        routing_metrics = None
        if (
            hasattr(self.world, "adaptive_routing_adapter")
            and self.world.adaptive_routing_adapter
            and self.world.adaptive_routing_adapter.config.enabled
        ):
            routing_metrics = self.world.adaptive_routing_adapter.metrics.to_dict()

        routing_dec_dicts = (
            [d.to_dict() for d in routing_decisions] if routing_decisions else None
        )

        safety_metrics = None
        if (
            hasattr(self.world, "safety_manager")
            and self.world.safety_manager.config.enabled
        ):
            safety_metrics = self.world.safety_manager.metrics.to_dict()

        safety_evt_dicts = (
            [e.to_dict() for e in safety_events] if safety_events else None
        )

        ped_metrics_dict = (
            self.world.pedestrian_metrics.to_dict()
            if (self.world.pedestrian_count > 0 or self.world.crosswalk_count > 0)
            else None
        )

        em_metrics = None
        em_events = None
        corridors_dict = None
        if hasattr(self.world, "emergency_manager") and self.world.emergency_manager:
            em_metrics = self.world.emergency_manager.metrics.to_dict()
            em_events = [e.to_dict() for e in self.world.emergency_manager.events]
            corridors_dict = {
                cid: c.to_dict()
                for cid, c in self.world.emergency_manager.corridors.items()
                if c.is_active
            }

        tick_result = TickResult(
            tick=new_tick,
            elapsed_time_s=self.clock.elapsed_time_s,
            time_step_s=dt,
            agent_count=len(step_results),
            step_results=step_results,
            arrived_agent_ids=arrived_ids,
            active_agent_ids=active_ids,
            signal_states=signal_states,
            communication_metrics=comm_metrics,
            coordination_metrics=coord_metrics,
            routing_metrics=routing_metrics,
            routing_decisions=routing_dec_dicts,
            safety_metrics=safety_metrics,
            safety_events=safety_evt_dicts,
            pedestrian_step_results=pedestrian_step_results,
            pedestrian_metrics=ped_metrics_dict,
            emergency_metrics=em_metrics,
            emergency_events=em_events,
            corridors=corridors_dict,
            yield_decisions=(
                {vid: dec.to_dict() for vid, dec in yield_decisions.items()}
                if yield_decisions
                else None
            ),
            decision_metrics=(
                self.world.decision_manager.metrics.to_dict()
                if (
                    hasattr(self.world, "decision_manager")
                    and self.world.decision_manager
                    and self.world.decision_manager.config.enabled
                )
                else None
            ),
            decision_records=(
                [r.to_dict() for r in self.world.decision_manager._records]
                if (
                    hasattr(self.world, "decision_manager")
                    and self.world.decision_manager
                    and self.world.decision_manager.config.enabled
                )
                else None
            ),
        )

        self.last_tick_result = tick_result
        return tick_result

    def run(
        self,
        ticks: int,
        target_accels_by_tick: Optional[list[dict[str, float]]] = None,
    ) -> list[TickResult]:
        """Execute a sequence of discrete simulation ticks.

        Args:
            ticks: Number of ticks to advance (must be integer > 0).
            target_accels_by_tick: Optional list of per-tick acceleration mappings.

        Returns:
            List of TickResult objects for each executed tick.

        Raises:
            ValueError: If ticks is not a positive integer.
            EngineStateError: If the engine is paused, stopped, or failed.
        """
        if not isinstance(ticks, int) or ticks <= 0:
            raise ValueError(f"ticks must be a positive integer, got {ticks}.")
        if self.is_paused:
            raise EngineStateError(
                "Cannot run multiple ticks while engine is paused. Call resume() or step().",
                current_state=self.status.value,
            )
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot run an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )

        results: list[TickResult] = []
        for i in range(ticks):
            accels = (
                target_accels_by_tick[i]
                if target_accels_by_tick and i < len(target_accels_by_tick)
                else None
            )
            res = self.step(target_accels=accels)
            results.append(res)

        return results

    def get_snapshot(self) -> WorldSnapshot:
        """Expose an immutable snapshot of the current world, agent, and signal states."""
        return self.world.get_snapshot()

    def query_signal(self, signal_id: str) -> SignalQueryResult:
        """Query state and timing for a traffic signal at the current simulation time.

        Args:
            signal_id: Unique traffic signal identifier.

        Returns:
            SignalQueryResult containing current state and time to next phase transitions.
        """
        return self.world.query_signal(signal_id, sim_time_s=self.clock.elapsed_time_s)

    def query_signal_for_edge(self, edge_id: str) -> Optional[SignalQueryResult]:
        """Query state and timing for the signal governing an incoming road edge approach.

        Args:
            edge_id: Incoming directed road edge identifier.

        Returns:
            SignalQueryResult if the edge terminates at a signalized intersection, else None.
        """
        return self.world.query_signal_for_edge(edge_id, sim_time_s=self.clock.elapsed_time_s)

    def broadcast_v2v(self, message: V2VMessagePacket) -> list[str]:
        """Broadcast a V2V message across all eligible vehicle agents within range.

        Args:
            message: V2VMessagePacket to broadcast.

        Returns:
            List of vehicle IDs that successfully received or enqueued the message.
        """
        candidates = {
            a.vehicle.id: Position2D(x=a.vehicle.position.x, y=a.vehicle.position.y)
            for a in self.world.get_agents()
        }
        return self.world.communication_network.broadcast(
            message=message,
            candidate_positions=candidates,
            current_time_s=self.clock.elapsed_time_s,
        )

    def send_v2v_unicast(self, message: V2VMessagePacket) -> bool:
        """Transmit a targeted unicast V2V message to a specific recipient.

        Args:
            message: V2VMessagePacket with non-empty recipient_id.

        Returns:
            True if delivered or enqueued; False otherwise.
        """
        candidates = {
            a.vehicle.id: Position2D(x=a.vehicle.position.x, y=a.vehicle.position.y)
            for a in self.world.get_agents()
        }
        return self.world.communication_network.send_unicast(
            message=message,
            candidate_positions=candidates,
            current_time_s=self.clock.elapsed_time_s,
        )

    def get_vehicle_inbox(self, vehicle_id: str) -> list[V2VMessagePacket]:
        """Inspect deliverable messages in a vehicle agent's inbox."""
        return self.world.communication_network.get_inbox(vehicle_id)

    def clear_vehicle_inbox(self, vehicle_id: str) -> list[V2VMessagePacket]:
        """Drain deliverable messages from a vehicle agent's inbox."""
        return self.world.communication_network.clear_inbox(vehicle_id)

    def discover_peers(self, vehicle_id: str) -> list[str]:
        """Discover communicating vehicle peers within range for a registered vehicle."""
        agent = self.world.get_agent(vehicle_id)
        candidates = {
            a.vehicle.id: Position2D(x=a.vehicle.position.x, y=a.vehicle.position.y)
            for a in self.world.get_agents()
        }
        return self.world.communication_network.discovery.find_peers(
            sender_id=vehicle_id,
            sender_position=agent.vehicle.position,
            candidates=candidates,
        )

    def get_neighbor_table(self, vehicle_id: str) -> Optional[NeighborTable]:
        """Retrieve the neighbor table for a vehicle agent."""
        return self.world.communication_network.get_neighbor_table(vehicle_id)

    def get_known_neighbors(self, vehicle_id: str) -> list[NeighborRecord]:
        """Retrieve all known neighbor records for a vehicle agent in deterministic order."""
        table = self.get_neighbor_table(vehicle_id)
        return table.get_all_neighbors() if table else []

    def get_active_neighbors(self, vehicle_id: str) -> list[NeighborRecord]:
        """Retrieve active neighbor records for a vehicle agent."""
        table = self.get_neighbor_table(vehicle_id)
        return table.get_active_neighbors() if table else []

    def get_stale_neighbors(self, vehicle_id: str) -> list[NeighborRecord]:
        """Retrieve stale neighbor records for a vehicle agent."""
        table = self.get_neighbor_table(vehicle_id)
        return table.get_stale_neighbors() if table else []

    def get_knowledge_store(self, vehicle_id: str) -> VehicleKnowledgeStore:
        """Retrieve private knowledge store for a specific registered vehicle."""
        return self.world.get_knowledge_store(vehicle_id)

    def publish_traffic_observation(
        self,
        vehicle_id: str,
        report: TrafficReport,
    ) -> bool:
        """Record and fuse a locally observed traffic event generated by a vehicle."""
        return self.world.coordination_manager.publish_observation(
            vehicle_id=vehicle_id,
            report=report,
            current_time_s=self.clock.elapsed_time_s,
        )
