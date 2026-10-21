"""Unified metrics aggregation across simulation subsystems for AMAPP.

Combines metrics from kinematics, adaptive routing, V2V communication, decentralized
coordination, collision avoidance, pedestrian interactions, dynamic emergency corridors,
and pluggable AI decision policies without mutating underlying state or double-counting.
Every aggregated metric documents its classification: cumulative, per-tick, or derived.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from apps.core.simulation.models import TickResult

METRIC_CLASSIFICATIONS = {
    "simulation.total_ticks": "cumulative: total completed discrete time steps",
    "simulation.simulated_duration_s": "cumulative: total simulated time elapsed in seconds",
    "kinematics.total_distance_traveled_m": "cumulative: total distance traveled by vehicles (m)",
    "kinematics.max_speed_observed_mps": "observed: maximum speed across all vehicles (m/s)",
    "kinematics.average_speed_mps": "derived: total_distance_traveled_m / sum_vehicle_travel_time",
    "routing.reroutes_evaluated": "cumulative: total rerouting candidate paths evaluated",
    "routing.reroutes_accepted": "cumulative: total rerouting adjustments accepted and applied",
    "routing.reroutes_rejected": "cumulative: total rerouting candidates rejected",
    "communication.messages_sent": "cumulative: total V2V communication packets sent",
    "communication.messages_delivered": "cumulative: total V2V packets successfully delivered",
    "communication.messages_lost": "cumulative: total V2V packets lost to channel degradation",
    "communication.messages_expired": "cumulative: total V2V packets expired due to TTL",
    "communication.packet_delivery_ratio": "derived: delivered / sent (None if sent == 0)",
    "coordination.conflicts_detected": "cumulative: multi-agent trajectory conflicts detected",
    "coordination.conflicts_resolved": "cumulative: multi-agent conflicts successfully resolved",
    "coordination.yield_actions": "cumulative: yielding maneuvers executed by coordinated agents",
    "safety.pair_checks": "cumulative: vehicle pair proximity checks performed by supervisor",
    "safety.near_misses": "cumulative: spatial near-miss events within hazard thresholds",
    "safety.emergency_brakes": "cumulative: emergency braking interventions applied",
    "safety.control_overrides": "cumulative: total acceleration command overrides enforced",
    "safety.actual_collisions": "cumulative: actual physical collisions recorded",
    "safety.min_separation_observed_m": "observed: minimum physical separation observed (m)",
    "safety.min_ttc_observed_s": "observed: minimum time-to-collision observed in seconds",
    "pedestrians.crosswalk_waits": "cumulative: pedestrian waiting states at crosswalk curbs",
    "pedestrians.crosswalk_crossings_completed": "cumulative: pedestrian crossings safely finished",
    "emergency.corridors_created": "cumulative: dynamic emergency corridors established",
    "emergency.corridors_active_final": "snapshot: emergency corridors active at run completion",
    "emergency.emergency_yield_actions": "cumulative: civilian yielding actions for emergency",
    "emergency.preemption_requests": "cumulative: signal/corridor preemption requests",
    "decision.evaluations_total": "cumulative: AI decision policy evaluation cycles",
    "decision.decisions_accepted": "cumulative: candidate actions accepted by decision policy",
    "decision.decisions_rejected": "cumulative: candidate actions rejected by policy/safety",
    "decision.decisions_deferred": "cumulative: candidate actions deferred to future cycles",
    "decision.decisions_reevaluated": "cumulative: actions reevaluated due to world changes",
}


@dataclass(frozen=True)
class RunMetricsSummary:
    """Immutable, typed summary of all simulation subsystem metrics for an executed run."""

    simulation: dict[str, Any]
    kinematics: dict[str, Any]
    routing: dict[str, Any]
    communication: dict[str, Any]
    coordination: dict[str, Any]
    safety: dict[str, Any]
    pedestrians: dict[str, Any]
    emergency: dict[str, Any]
    decision: dict[str, Any]
    metric_definitions: dict[str, str] = field(default_factory=lambda: dict(METRIC_CLASSIFICATIONS))

    def to_dict(self) -> dict[str, Any]:
        """Serialize run metrics summary to a plain JSON-compatible dictionary."""
        return {
            "simulation": dict(self.simulation),
            "kinematics": dict(self.kinematics),
            "routing": dict(self.routing),
            "communication": dict(self.communication),
            "coordination": dict(self.coordination),
            "safety": dict(self.safety),
            "pedestrians": dict(self.pedestrians),
            "emergency": dict(self.emergency),
            "decision": dict(self.decision),
            "metric_definitions": dict(self.metric_definitions),
        }


class MetricsAggregator:
    """Aggregates metrics across simulation subsystems without double-counting."""

    @staticmethod
    def aggregate(
        tick_history: Sequence[TickResult],
        world: Any,
        total_vehicles: int,
        arrived_vehicles: int,
        active_vehicles: int,
        terminal_state: str,
        termination_reason: str,
        elapsed_time_s: float,
        time_step_s: float,
    ) -> RunMetricsSummary:
        """Compute authoritative metrics summary from committed tick results and world state.

        Args:
            tick_history: Sequence of successfully committed TickResult instances (no failed ticks).
            world: Authoritative WorldState instance.
            total_vehicles: Count of all configured vehicles.
            arrived_vehicles: Count of vehicles that reached destination.
            active_vehicles: Count of vehicles still actively traveling.
            terminal_state: Lifecycle terminal status string.
            termination_reason: Reason for run termination.
            elapsed_time_s: Total simulated elapsed time in seconds.
            time_step_s: Simulation discrete step size.

        Returns:
            Structured RunMetricsSummary.
        """
        # 1. Simulation metrics
        pedestrians = getattr(world, "_pedestrians", {}) or {}
        arrived_peds = sum(1 for p in pedestrians.values() if getattr(p, "is_arrived", False))
        active_peds = len(pedestrians) - arrived_peds

        sim_metrics = {
            "total_ticks": len(tick_history),
            "simulated_duration_s": round(elapsed_time_s, 6),
            "time_step_s": round(time_step_s, 6),
            "terminal_state": terminal_state,
            "termination_reason": termination_reason,
            "vehicles_registered": total_vehicles,
            "vehicles_arrived": arrived_vehicles,
            "vehicles_active": active_vehicles,
            "pedestrians_registered": len(pedestrians),
            "pedestrians_arrived": arrived_peds,
            "pedestrians_active": active_peds,
        }

        # 2. Kinematics metrics
        total_dist_m = 0.0
        max_speed_mps = 0.0
        total_vehicle_travel_time_s = 0.0

        for tr in tick_history:
            for step_res in tr.step_results.values():
                speed = getattr(step_res, "new_speed_mps", 0.0)
                dist = getattr(step_res, "distance_traveled_m", 0.0)
                total_dist_m += dist
                if speed > max_speed_mps:
                    max_speed_mps = speed
                total_vehicle_travel_time_s += tr.time_step_s

        avg_speed_mps: Optional[float] = None
        if total_vehicle_travel_time_s > 0.0:
            avg_speed_mps = round(total_dist_m / total_vehicle_travel_time_s, 4)

        kinematics_metrics = {
            "total_distance_traveled_m": round(total_dist_m, 4),
            "max_speed_observed_mps": round(max_speed_mps, 4),
            "average_speed_mps": avg_speed_mps,
        }

        # 3. Routing metrics
        reroutes_eval = 0
        reroutes_acc = 0
        reroutes_rej = 0
        if hasattr(world, "adaptive_routing_adapter") and world.adaptive_routing_adapter:
            m = world.adaptive_routing_adapter.metrics
            reroutes_eval = getattr(m, "reroutes_evaluated", 0)
            reroutes_acc = getattr(m, "reroutes_accepted", 0)
            reroutes_rej = getattr(m, "reroutes_rejected", 0)
        else:
            for tr in tick_history:
                if tr.routing_metrics:
                    reroutes_eval += tr.routing_metrics.get("reroutes_evaluated", 0)
                    reroutes_acc += tr.routing_metrics.get("reroutes_accepted", 0)
                    reroutes_rej += tr.routing_metrics.get("reroutes_rejected", 0)

        routing_metrics = {
            "reroutes_evaluated": reroutes_eval,
            "reroutes_accepted": reroutes_acc,
            "reroutes_rejected": reroutes_rej,
        }

        # 4. Communication metrics
        msgs_sent = 0
        msgs_delivered = 0
        msgs_lost = 0
        msgs_expired = 0
        comms_enabled = (
            hasattr(world, "communication_network") and world.communication_network is not None
        )

        if comms_enabled:
            m = world.communication_network.metrics
            msgs_sent = getattr(m, "broadcasts_attempted", 0) + getattr(m, "unicasts_attempted", 0)
            msgs_delivered = getattr(m, "successful_deliveries", 0)
            msgs_lost = (
                getattr(m, "dropped_packet_loss", 0)
                + getattr(m, "dropped_burst_loss", 0)
                + getattr(m, "dropped_out_of_range", 0)
                + getattr(m, "dropped_link_outage", 0)
                + getattr(m, "dropped_partition", 0)
            )
            msgs_expired = getattr(m, "dropped_expired", 0)
        else:
            for tr in tick_history:
                if tr.communication_metrics:
                    msgs_sent += tr.communication_metrics.get("messages_sent", 0)
                    msgs_delivered += tr.communication_metrics.get("messages_delivered", 0)
                    msgs_lost += tr.communication_metrics.get("messages_lost", 0)
                    msgs_expired += tr.communication_metrics.get("messages_expired", 0)

        pdr: Optional[float] = None
        if comms_enabled or msgs_sent > 0:
            pdr = round(msgs_delivered / msgs_sent, 4) if msgs_sent > 0 else 1.0

        communication_metrics = {
            "messages_sent": msgs_sent,
            "messages_delivered": msgs_delivered,
            "messages_lost": msgs_lost,
            "messages_expired": msgs_expired,
            "packet_delivery_ratio": pdr,
        }

        # 5. Coordination metrics
        conflicts_det = 0
        conflicts_res = 0
        yield_acts = 0
        coord_mgr = getattr(world, "coordination_manager", None)
        if coord_mgr and hasattr(coord_mgr, "metrics"):
            cm = coord_mgr.metrics
            conflicts_det = getattr(cm, "conflicts_detected", 0)
            conflicts_res = getattr(cm, "conflicts_resolved", 0)
            yield_acts = getattr(cm, "yield_actions", 0)
        else:
            for tr in tick_history:
                if tr.coordination_metrics:
                    conflicts_det += tr.coordination_metrics.get("conflicts_detected", 0)
                    conflicts_res += tr.coordination_metrics.get("conflicts_resolved", 0)
                    yield_acts += tr.coordination_metrics.get("yield_actions", 0)

        coordination_metrics = {
            "conflicts_detected": conflicts_det,
            "conflicts_resolved": conflicts_res,
            "yield_actions": yield_acts,
        }

        # 6. Safety metrics
        pair_checks = 0
        near_misses = 0
        emergency_brakes = 0
        control_overrides = 0
        actual_collisions = 0
        min_sep: Optional[float] = None
        min_ttc: Optional[float] = None

        if hasattr(world, "safety_manager") and world.safety_manager:
            sm = world.safety_manager.metrics
            pair_checks = getattr(sm, "pair_checks", 0)
            near_misses = getattr(sm, "near_misses", 0)
            emergency_brakes = getattr(sm, "emergency_brakes", 0)
            control_overrides = getattr(sm, "control_overrides", 0)
            actual_collisions = getattr(sm, "actual_collisions", 0)
            min_sep = getattr(sm, "min_separation_observed", None)
            min_ttc = getattr(sm, "min_ttc_observed", None)
        else:
            for tr in tick_history:
                if tr.safety_metrics:
                    pair_checks += tr.safety_metrics.get("pair_checks", 0)
                    near_misses += tr.safety_metrics.get("near_misses", 0)
                    emergency_brakes += tr.safety_metrics.get("emergency_brakes", 0)
                    control_overrides += tr.safety_metrics.get("control_overrides", 0)
                    actual_collisions += tr.safety_metrics.get("actual_collisions", 0)
                    sep = tr.safety_metrics.get("min_separation_observed")
                    if sep is not None:
                        min_sep = sep if min_sep is None else min(min_sep, sep)
                    ttc = tr.safety_metrics.get("min_ttc_observed")
                    if ttc is not None:
                        min_ttc = ttc if min_ttc is None else min(min_ttc, ttc)

        safety_metrics = {
            "pair_checks": pair_checks,
            "near_misses": near_misses,
            "emergency_brakes": emergency_brakes,
            "control_overrides": control_overrides,
            "actual_collisions": actual_collisions,
            "min_separation_observed_m": round(min_sep, 4) if min_sep is not None else None,
            "min_ttc_observed_s": round(min_ttc, 4) if min_ttc is not None else None,
        }

        # 7. Pedestrian metrics
        cw_waits = 0
        cw_crossings = 0
        pm = getattr(world, "pedestrian_metrics", None)
        if pm:
            cw_waits = getattr(pm, "crosswalk_waits", 0)
            cw_crossings = getattr(pm, "crossings_completed", 0)
        else:
            for tr in tick_history:
                if tr.pedestrian_metrics:
                    cw_waits += tr.pedestrian_metrics.get("crosswalk_waits", 0)
                    cw_crossings += tr.pedestrian_metrics.get("crossings_completed", 0)

        pedestrian_metrics = {
            "crosswalk_waits": cw_waits,
            "crosswalk_crossings_completed": cw_crossings,
        }

        # 8. Emergency metrics
        corridors_created = 0
        corridors_active = 0
        em_yields = 0
        preemption_reqs = 0
        if hasattr(world, "emergency_manager") and world.emergency_manager:
            em = world.emergency_manager
            em_metrics = getattr(em, "metrics", None)
            if em_metrics:
                corridors_created = getattr(em_metrics, "corridors_created", 0)
                em_yields = getattr(em_metrics, "emergency_yield_actions", 0)
                preemption_reqs = getattr(em_metrics, "preemption_requests", 0)
            corridors_active = len(getattr(em, "corridors", {}))
        else:
            for tr in tick_history:
                if tr.emergency_metrics:
                    corridors_created += tr.emergency_metrics.get("corridors_created", 0)
                    em_yields += tr.emergency_metrics.get("emergency_yield_actions", 0)
                    preemption_reqs += tr.emergency_metrics.get("preemption_requests", 0)
                if tr.corridors:
                    corridors_active = len(tr.corridors)

        emergency_metrics = {
            "corridors_created": corridors_created,
            "corridors_active_final": corridors_active,
            "emergency_yield_actions": em_yields,
            "preemption_requests": preemption_reqs,
        }

        # 9. Decision metrics
        evals_total = 0
        dec_accepted = 0
        dec_rejected = 0
        dec_deferred = 0
        dec_reevaluated = 0
        dec_mgr = getattr(world, "decision_manager", None)
        if dec_mgr and hasattr(dec_mgr, "metrics"):
            de_metrics = dec_mgr.metrics
            evals_total = getattr(de_metrics, "evaluations_total", 0)
            dec_accepted = getattr(de_metrics, "decisions_accepted", 0)
            dec_rejected = getattr(de_metrics, "decisions_rejected", 0)
            dec_deferred = getattr(de_metrics, "decisions_deferred", 0)
            dec_reevaluated = getattr(de_metrics, "decisions_reevaluated", 0)
        else:
            for tr in tick_history:
                if tr.decision_metrics:
                    evals_total += tr.decision_metrics.get("evaluations_total", 0)
                    dec_accepted += tr.decision_metrics.get("decisions_accepted", 0)
                    dec_rejected += tr.decision_metrics.get("decisions_rejected", 0)
                    dec_deferred += tr.decision_metrics.get("decisions_deferred", 0)
                    dec_reevaluated += tr.decision_metrics.get("decisions_reevaluated", 0)

        decision_metrics = {
            "evaluations_total": evals_total,
            "decisions_accepted": dec_accepted,
            "decisions_rejected": dec_rejected,
            "decisions_deferred": dec_deferred,
            "decisions_reevaluated": dec_reevaluated,
        }

        return RunMetricsSummary(
            simulation=sim_metrics,
            kinematics=kinematics_metrics,
            routing=routing_metrics,
            communication=communication_metrics,
            coordination=coordination_metrics,
            safety=safety_metrics,
            pedestrians=pedestrian_metrics,
            emergency=emergency_metrics,
            decision=decision_metrics,
        )
