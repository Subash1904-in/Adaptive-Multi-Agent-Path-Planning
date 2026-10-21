"""Operational metrics, live KPIs, and simulation analytics aggregator for AMAPP.

Provides deterministic, backend-authoritative calculation of:
- Trip completion statistics and travel-time distributions
  (mean, median, p90, p95, min, max, histogram)
- Intersection and node crossing throughput (total crossings, rate per simulation minute, by node)
- Safety and collision analytics (collisions, near-misses, rates per minute, extrema)
- V2V communication efficiency (PDR, loss rate, loss breakdown by cause, latency queue status)
- Adaptive routing performance (evaluated vs accepted counts, acceptance rate)
- Active traffic incidents grouped by type and status
- Bounded time-series telemetry for responsive operational charting
"""

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from apps.core.simulation.models import TickResult


def _percentile(values: Sequence[float], p: float) -> Optional[float]:
    """Calculate percentile p in [0.0, 100.0] using linear interpolation.

    Returns None if values is empty.
    """
    if not values:
        return None
    sorted_v = sorted(values)
    if len(sorted_v) == 1:
        return sorted_v[0]
    rank = (p / 100.0) * (len(sorted_v) - 1)
    low_idx = int(math.floor(rank))
    high_idx = int(math.ceil(rank))
    if low_idx == high_idx:
        return sorted_v[low_idx]
    weight = rank - low_idx
    return sorted_v[low_idx] * (1.0 - weight) + sorted_v[high_idx] * weight


@dataclass(frozen=True)
class HistogramBin:
    """Discrete frequency bin for continuous distributions."""

    bin_start_s: float
    bin_end_s: float
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_start_s": round(self.bin_start_s, 2),
            "bin_end_s": round(self.bin_end_s, 2),
            "count": self.count,
        }


@dataclass(frozen=True)
class TravelTimeDistribution:
    """Travel-time distribution statistics for completed vehicle trips."""

    sample_count: int
    mean_s: Optional[float]
    median_s: Optional[float]
    p90_s: Optional[float]
    p95_s: Optional[float]
    min_s: Optional[float]
    max_s: Optional[float]
    bins: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "mean_s": round(self.mean_s, 2) if self.mean_s is not None else None,
            "median_s": round(self.median_s, 2) if self.median_s is not None else None,
            "p90_s": round(self.p90_s, 2) if self.p90_s is not None else None,
            "p95_s": round(self.p95_s, 2) if self.p95_s is not None else None,
            "min_s": round(self.min_s, 2) if self.min_s is not None else None,
            "max_s": round(self.max_s, 2) if self.max_s is not None else None,
            "bins": self.bins,
        }


@dataclass(frozen=True)
class TripAnalytics:
    """Trip completion and travel time analytics."""

    total_trips: int
    completed_trips: int
    active_trips: int
    completion_rate_pct: Optional[float]
    travel_time: TravelTimeDistribution

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_trips": self.total_trips,
            "completed_trips": self.completed_trips,
            "active_trips": self.active_trips,
            "completion_rate_pct": (
                round(self.completion_rate_pct, 2)
                if self.completion_rate_pct is not None
                else None
            ),
            "travel_time": self.travel_time.to_dict(),
        }


@dataclass(frozen=True)
class ThroughputAnalytics:
    """Intersection and road network throughput metrics."""

    total_crossings: int
    crossings_per_minute: float
    signalized_crossings: int
    unsignalized_crossings: int
    top_intersections: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_crossings": self.total_crossings,
            "crossings_per_minute": round(self.crossings_per_minute, 2),
            "signalized_crossings": self.signalized_crossings,
            "unsignalized_crossings": self.unsignalized_crossings,
            "top_intersections": self.top_intersections,
        }


@dataclass(frozen=True)
class SafetyAnalytics:
    """Collision, near-miss, and vehicle hazard metrics."""

    actual_collisions: int
    near_misses: int
    emergency_brakes: int
    control_overrides: int
    min_separation_observed_m: Optional[float]
    min_ttc_observed_s: Optional[float]
    collision_rate_per_minute: float
    near_miss_rate_per_minute: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "actual_collisions": self.actual_collisions,
            "near_misses": self.near_misses,
            "emergency_brakes": self.emergency_brakes,
            "control_overrides": self.control_overrides,
            "min_separation_observed_m": (
                round(self.min_separation_observed_m, 2)
                if self.min_separation_observed_m is not None
                else None
            ),
            "min_ttc_observed_s": (
                round(self.min_ttc_observed_s, 2)
                if self.min_ttc_observed_s is not None
                else None
            ),
            "collision_rate_per_minute": round(self.collision_rate_per_minute, 2),
            "near_miss_rate_per_minute": round(self.near_miss_rate_per_minute, 2),
        }


@dataclass(frozen=True)
class CommunicationAnalytics:
    """V2V communication packet delivery ratio, losses, and latency queue stats."""

    messages_sent: int
    messages_delivered: int
    messages_lost: int
    messages_expired: int
    packet_delivery_ratio: Optional[float]
    packet_loss_rate: Optional[float]
    loss_by_reason: dict[str, int]
    latency_packets_queued: int
    latency_packets_delivered: int
    latency_continuous_ms: Optional[float] = None
    disclaimer: str = (
        "Continuous latency in milliseconds is not tracked by the discrete channel model."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "messages_lost": self.messages_lost,
            "messages_expired": self.messages_expired,
            "packet_delivery_ratio": (
                round(self.packet_delivery_ratio, 4)
                if self.packet_delivery_ratio is not None
                else None
            ),
            "pdr": (
                round(self.packet_delivery_ratio, 4)
                if self.packet_delivery_ratio is not None
                else None
            ),
            "packet_loss_rate": (
                round(self.packet_loss_rate, 4)
                if self.packet_loss_rate is not None
                else None
            ),
            "loss_rate": (
                round(self.packet_loss_rate, 4)
                if self.packet_loss_rate is not None
                else None
            ),
            "loss_by_reason": dict(self.loss_by_reason),
            "loss_breakdown": dict(self.loss_by_reason),
            "latency_packets_queued": self.latency_packets_queued,
            "latency_packets_delivered": self.latency_packets_delivered,
            "latency_continuous_ms": self.latency_continuous_ms,
            "latency_ms_available": False,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class RoutingAnalytics:
    """Adaptive rerouting decisions, candidate evaluations, and acceptance rate."""

    reroutes_evaluated: int
    reroutes_accepted: int
    reroutes_rejected: int
    acceptance_rate_pct: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reroutes_evaluated": self.reroutes_evaluated,
            "reroutes_accepted": self.reroutes_accepted,
            "reroutes_rejected": self.reroutes_rejected,
            "acceptance_rate_pct": (
                round(self.acceptance_rate_pct, 2)
                if self.acceptance_rate_pct is not None
                else None
            ),
        }


@dataclass(frozen=True)
class IncidentAnalytics:
    """Traffic incident counts and classification breakdown."""

    total_active_incidents: int
    active_by_type: dict[str, int]
    resolved_incidents: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_active_incidents": self.total_active_incidents,
            "total_active": self.total_active_incidents,
            "active_by_type": dict(self.active_by_type),
            "resolved_incidents": self.resolved_incidents,
        }


@dataclass(frozen=True)
class TimeSeriesPoint:
    """Sampled metric tuple at a specific discrete simulation tick."""

    tick: int
    timestamp_s: float
    completed_trips: int
    active_vehicles: int
    total_distance_m: float
    avg_speed_mps: float
    intersection_crossings: int
    v2v_pdr: Optional[float]
    collisions: int
    near_misses: int
    reroutes_accepted: int
    active_incidents: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "timestamp_s": round(self.timestamp_s, 2),
            "completed_trips": self.completed_trips,
            "active_vehicles": self.active_vehicles,
            "total_distance_m": round(self.total_distance_m, 1),
            "avg_speed_mps": round(self.avg_speed_mps, 2),
            "intersection_crossings": self.intersection_crossings,
            "v2v_pdr": round(self.v2v_pdr, 4) if self.v2v_pdr is not None else None,
            "collisions": self.collisions,
            "near_misses": self.near_misses,
            "reroutes_accepted": self.reroutes_accepted,
            "active_incidents": self.active_incidents,
        }


class OperationalAnalyticsAggregator:
    """Authoritative aggregator computing comprehensive operational analytics
    for simulation runs.
    """

    @classmethod
    def compute(
        cls,
        tick_history: Sequence[TickResult],
        world: Any,
        elapsed_time_s: float,
        time_step_s: float,
        max_time_series_points: int = 100,
        time_window_start_s: Optional[float] = None,
        time_window_end_s: Optional[float] = None,
    ) -> dict[str, Any]:
        """Compute full operational analytics package from authoritative simulation state."""
        # Optional time window filtering on tick_history
        filtered_ticks = list(tick_history)
        if time_window_start_s is not None or time_window_end_s is not None:
            filtered_ticks = [
                tr
                for tr in filtered_ticks
                if (time_window_start_s is None or tr.elapsed_time_s >= time_window_start_s)
                and (time_window_end_s is None or tr.elapsed_time_s <= time_window_end_s)
            ]

        effective_duration = elapsed_time_s
        if time_window_start_s is not None and time_window_end_s is not None:
            effective_duration = max(0.0, time_window_end_s - time_window_start_s)
        elif filtered_ticks:
            effective_duration = filtered_ticks[-1].elapsed_time_s - (
                time_window_start_s or 0.0
            )

        trips = cls._compute_trips(world, tick_history)
        throughput = cls._compute_throughput(world, filtered_ticks, effective_duration)
        safety = cls._compute_safety(world, filtered_ticks, effective_duration)
        comms = cls._compute_communication(world, filtered_ticks)
        routing = cls._compute_routing(world, filtered_ticks)
        incidents = cls._compute_incidents(world)
        time_series = cls._build_time_series(
            tick_history=filtered_ticks,
            world=world,
            max_points=max_time_series_points,
        )

        return {
            "trips": trips.to_dict(),
            "throughput": throughput.to_dict(),
            "safety": safety.to_dict(),
            "communication": comms.to_dict(),
            "routing": routing.to_dict(),
            "incidents": incidents.to_dict(),
            "time_series": [pt.to_dict() for pt in time_series],
        }

    @classmethod
    def _compute_trips(cls, world: Any, tick_history: Sequence[TickResult]) -> TripAnalytics:
        """Compute completed trips, completion rates, and travel-time distributions."""
        agents = world.get_agents() if hasattr(world, "get_agents") else []
        total_trips = len(agents)

        # Track exact arrival simulation time for each completed vehicle
        arrival_times: dict[str, float] = {}
        for tr in tick_history:
            for vid in tr.arrived_agent_ids:
                if vid not in arrival_times:
                    arrival_times[vid] = tr.elapsed_time_s

        # Fallback to current world state for any agents marked arrived
        for a in agents:
            vid = getattr(a, "id", None) or (
                getattr(a.vehicle, "id", None) if hasattr(a, "vehicle") else None
            )
            if vid and getattr(a, "is_arrived", False) and vid not in arrival_times:
                arrival_times[vid] = (
                    tick_history[-1].elapsed_time_s if tick_history else 0.0
                )

        completed_trips = len(arrival_times)
        active_trips = max(0, total_trips - completed_trips)
        completion_rate = (
            (completed_trips / total_trips * 100.0) if total_trips > 0 else None
        )

        # Travel times in seconds (start time is assumed t=0.0 in current AMAPP scenarios)
        travel_times = sorted(arrival_times.values())
        sample_count = len(travel_times)

        if sample_count > 0:
            mean_s = sum(travel_times) / sample_count
            median_s = _percentile(travel_times, 50.0)
            p90_s = _percentile(travel_times, 90.0)
            p95_s = _percentile(travel_times, 95.0)
            min_s = travel_times[0]
            max_s = travel_times[-1]

            # Construct histogram bins (5 bins across min-max range, or 1 bin if identical)
            bins: list[dict[str, Any]] = []
            if max_s > min_s + 1e-6:
                num_bins = min(5, sample_count)
                bin_width = (max_s - min_s) / num_bins
                bin_counts = [0] * num_bins
                for tt in travel_times:
                    idx = int((tt - min_s) / bin_width)
                    if idx >= num_bins:
                        idx = num_bins - 1
                    bin_counts[idx] += 1
                for i in range(num_bins):
                    b_start = min_s + i * bin_width
                    b_end = min_s + (i + 1) * bin_width
                    bins.append(HistogramBin(b_start, b_end, bin_counts[i]).to_dict())
            else:
                bins.append(
                    HistogramBin(min_s, max_s + 1.0, sample_count).to_dict()
                )

            distribution = TravelTimeDistribution(
                sample_count=sample_count,
                mean_s=mean_s,
                median_s=median_s,
                p90_s=p90_s,
                p95_s=p95_s,
                min_s=min_s,
                max_s=max_s,
                bins=bins,
            )
        else:
            distribution = TravelTimeDistribution(
                sample_count=0,
                mean_s=None,
                median_s=None,
                p90_s=None,
                p95_s=None,
                min_s=None,
                max_s=None,
                bins=[],
            )

        return TripAnalytics(
            total_trips=total_trips,
            completed_trips=completed_trips,
            active_trips=active_trips,
            completion_rate_pct=completion_rate,
            travel_time=distribution,
        )

    @classmethod
    def _compute_throughput(
        cls, world: Any, tick_history: Sequence[TickResult], elapsed_time_s: float
    ) -> ThroughputAnalytics:
        """Trace verified intersection crossings from vehicle edge transitions."""
        road_graph = getattr(world, "road_graph", None)
        signals = getattr(world, "_signals", {}) or {}
        signalized_nodes = {s.node_id for s in signals.values()} if signals else set()

        # Track previous occupied edge per vehicle to identify confirmed node transitions
        prev_edges: dict[str, str] = {}
        crossings_by_node: dict[str, int] = {}
        total_crossings = 0
        signalized_count = 0
        unsignalized_count = 0

        for tr in tick_history:
            for vid, step_res in tr.step_results.items():
                cur_edge_id = (
                    getattr(step_res, "current_edge_id", None)
                    if hasattr(step_res, "current_edge_id")
                    else (step_res.get("current_edge_id") if isinstance(step_res, dict) else None)
                )
                prev_edge_id = prev_edges.get(vid)

                if prev_edge_id and cur_edge_id and prev_edge_id != cur_edge_id:
                    # Vehicle transitioned from prev_edge to cur_edge
                    # The intermediate crossed node is prev_edge.end_node_id
                    crossed_node = None
                    if road_graph:
                        if hasattr(road_graph, "has_edge") and not road_graph.has_edge(
                            prev_edge_id
                        ):
                            edge_obj = None
                        elif hasattr(road_graph, "get_edge"):
                            edge_obj = road_graph.get_edge(prev_edge_id)
                        else:
                            edge_obj = None
                        if edge_obj:
                            crossed_node = getattr(edge_obj, "end_node_id", None)

                    if crossed_node:
                        total_crossings += 1
                        crossings_by_node[crossed_node] = (
                            crossings_by_node.get(crossed_node, 0) + 1
                        )
                        if crossed_node in signalized_nodes:
                            signalized_count += 1
                        else:
                            unsignalized_count += 1

                if cur_edge_id:
                    prev_edges[vid] = cur_edge_id

        # Calculate rate per simulation minute
        minutes = elapsed_time_s / 60.0 if elapsed_time_s > 0.0 else 0.0
        cpm = (total_crossings / minutes) if minutes > 0.0 else 0.0

        top_nodes = [
            {"node_id": nid, "crossings": count, "is_signalized": nid in signalized_nodes}
            for nid, count in sorted(
                crossings_by_node.items(), key=lambda item: item[1], reverse=True
            )[:5]
        ]

        return ThroughputAnalytics(
            total_crossings=total_crossings,
            crossings_per_minute=cpm,
            signalized_crossings=signalized_count,
            unsignalized_crossings=unsignalized_count,
            top_intersections=top_nodes,
        )

    @classmethod
    def _compute_safety(
        cls, world: Any, tick_history: Sequence[TickResult], elapsed_time_s: float
    ) -> SafetyAnalytics:
        """Aggregate safety metrics and calculate incident rates per simulation minute."""
        collisions = 0
        near_misses = 0
        emergency_brakes = 0
        control_overrides = 0
        min_sep: Optional[float] = None
        min_ttc: Optional[float] = None

        if hasattr(world, "safety_manager") and world.safety_manager:
            sm = world.safety_manager.metrics
            if isinstance(sm, dict):
                collisions = sm.get("actual_collisions", 0)
                near_misses = sm.get("near_misses", 0)
                emergency_brakes = sm.get("emergency_brakes", 0) or sm.get("emergency_stops", 0)
                control_overrides = sm.get("control_overrides", 0)
                min_sep = sm.get("min_separation_observed") or sm.get("min_observed_headway_m")
                min_ttc = sm.get("min_ttc_observed") or sm.get("min_observed_ttc_s")
            else:
                collisions = getattr(sm, "actual_collisions", 0)
                near_misses = getattr(sm, "near_misses", 0)
                emergency_brakes = getattr(sm, "emergency_brakes", 0)
                control_overrides = getattr(sm, "control_overrides", 0)
                min_sep = getattr(sm, "min_separation_observed", None) or getattr(
                    sm, "min_observed_headway_m", None
                )
                min_ttc = getattr(sm, "min_ttc_observed", None) or getattr(
                    sm, "min_observed_ttc_s", None
                )
        else:
            for tr in tick_history:
                if tr.safety_metrics:
                    collisions += tr.safety_metrics.get("actual_collisions", 0)
                    near_misses += tr.safety_metrics.get("near_misses", 0)
                    emergency_brakes += tr.safety_metrics.get("emergency_brakes", 0)
                    control_overrides += tr.safety_metrics.get("control_overrides", 0)
                    s = tr.safety_metrics.get("min_separation_observed")
                    if s is not None:
                        min_sep = s if min_sep is None else min(min_sep, s)
                    t = tr.safety_metrics.get("min_ttc_observed")
                    if t is not None:
                        min_ttc = t if min_ttc is None else min(min_ttc, t)

        minutes = elapsed_time_s / 60.0 if elapsed_time_s > 0.0 else 0.0
        cpm = (collisions / minutes) if minutes > 0.0 else 0.0
        nmpm = (near_misses / minutes) if minutes > 0.0 else 0.0

        return SafetyAnalytics(
            actual_collisions=collisions,
            near_misses=near_misses,
            emergency_brakes=emergency_brakes,
            control_overrides=control_overrides,
            min_separation_observed_m=min_sep,
            min_ttc_observed_s=min_ttc,
            collision_rate_per_minute=cpm,
            near_miss_rate_per_minute=nmpm,
        )

    @classmethod
    def _compute_communication(
        cls, world: Any, tick_history: Sequence[TickResult]
    ) -> CommunicationAnalytics:
        """Extract packet delivery ratio, drops by reason, and latency queue counters."""
        sent = 0
        delivered = 0
        lost = 0
        expired = 0
        loss_by_reason: dict[str, int] = {
            "packet_loss": 0,
            "burst_loss": 0,
            "out_of_range": 0,
            "link_outage": 0,
            "partition": 0,
            "expired": 0,
            "snr_fading": 0,
            "hidden_terminal": 0,
        }
        queued_lat = 0
        deliv_lat = 0

        if hasattr(world, "communication_network") and world.communication_network:
            cm = world.communication_network.metrics
            if isinstance(cm, dict):
                sent = cm.get("messages_sent", 0) or (
                    cm.get("broadcasts_attempted", 0) + cm.get("unicasts_attempted", 0)
                )
                delivered = cm.get("messages_delivered", 0) or cm.get("successful_deliveries", 0)
                lost = cm.get("messages_lost", 0)
                expired = cm.get("messages_expired", 0)
                loss_by_reason["packet_loss"] = cm.get("dropped_packet_loss", 0)
                loss_by_reason["burst_loss"] = cm.get("dropped_burst_loss", 0)
                loss_by_reason["out_of_range"] = (
                    cm.get("messages_lost_out_of_range", 0) or cm.get("dropped_out_of_range", 0)
                )
                loss_by_reason["link_outage"] = cm.get("dropped_link_outage", 0)
                loss_by_reason["partition"] = cm.get("dropped_partition", 0)
                loss_by_reason["expired"] = expired or cm.get("dropped_expired", 0)
                loss_by_reason["snr_fading"] = cm.get("messages_lost_snr", 0)
                loss_by_reason["hidden_terminal"] = cm.get("messages_lost_hidden_terminal", 0)
                if lost == 0:
                    lost = sum(loss_by_reason.values())
                queued_lat = cm.get("packets_queued_latency", 0)
                deliv_lat = cm.get("packets_delivered_latency", 0)
            else:
                sent = getattr(cm, "broadcasts_attempted", 0) + getattr(
                    cm, "unicasts_attempted", 0
                )
                delivered = getattr(cm, "successful_deliveries", 0)
                loss_by_reason["packet_loss"] = getattr(cm, "dropped_packet_loss", 0)
                loss_by_reason["burst_loss"] = getattr(cm, "dropped_burst_loss", 0)
                loss_by_reason["out_of_range"] = getattr(cm, "dropped_out_of_range", 0)
                loss_by_reason["link_outage"] = getattr(cm, "dropped_link_outage", 0)
                loss_by_reason["partition"] = getattr(cm, "dropped_partition", 0)
                loss_by_reason["expired"] = getattr(cm, "dropped_expired", 0)
                lost = sum(loss_by_reason.values())
                expired = loss_by_reason["expired"]
                queued_lat = getattr(cm, "packets_queued_latency", 0)
                deliv_lat = getattr(cm, "packets_delivered_latency", 0)
        else:
            for tr in tick_history:
                if tr.communication_metrics:
                    sent += tr.communication_metrics.get("messages_sent", 0)
                    delivered += tr.communication_metrics.get("messages_delivered", 0)
                    lost += tr.communication_metrics.get("messages_lost", 0)
                    expired += tr.communication_metrics.get("messages_expired", 0)

        pdr: Optional[float] = None
        if sent > 0:
            pdr = round(delivered / sent, 4)

        loss_rate: Optional[float] = None
        if sent > 0:
            loss_rate = round(lost / sent, 4)

        return CommunicationAnalytics(
            messages_sent=sent,
            messages_delivered=delivered,
            messages_lost=lost,
            messages_expired=expired,
            packet_delivery_ratio=pdr,
            packet_loss_rate=loss_rate,
            loss_by_reason=loss_by_reason,
            latency_packets_queued=queued_lat,
            latency_packets_delivered=deliv_lat,
        )

    @classmethod
    def _compute_routing(
        cls, world: Any, tick_history: Sequence[TickResult]
    ) -> RoutingAnalytics:
        """Compute rerouting adjustments and acceptance rate."""
        evals = 0
        accepted = 0
        rejected = 0

        if hasattr(world, "adaptive_routing_adapter") and world.adaptive_routing_adapter:
            rm = world.adaptive_routing_adapter.metrics
            evals = getattr(rm, "reroutes_evaluated", 0)
            accepted = getattr(rm, "reroutes_accepted", 0)
            rejected = getattr(rm, "reroutes_rejected", 0)
        else:
            for tr in tick_history:
                if tr.routing_metrics:
                    evals += tr.routing_metrics.get("reroutes_evaluated", 0)
                    accepted += tr.routing_metrics.get("reroutes_accepted", 0)
                    rejected += tr.routing_metrics.get("reroutes_rejected", 0)

        rate = (accepted / evals * 100.0) if evals > 0 else None
        return RoutingAnalytics(
            reroutes_evaluated=evals,
            reroutes_accepted=accepted,
            reroutes_rejected=rejected,
            acceptance_rate_pct=rate,
        )

    @classmethod
    def _compute_incidents(cls, world: Any) -> IncidentAnalytics:
        """Extract active and resolved incidents by exact domain enum."""
        inc_mgr = getattr(world, "incident_manager", None)
        active_list: Sequence[Any] = []
        resolved_count = 0

        if inc_mgr is not None:
            if hasattr(inc_mgr, "list_active"):
                active_list = inc_mgr.list_active()
            elif hasattr(inc_mgr, "_active_incidents"):
                active_list = list(inc_mgr._active_incidents.values())

            if hasattr(inc_mgr, "resolved_count"):
                resolved_count = inc_mgr.resolved_count
            elif hasattr(inc_mgr, "_resolved_incidents"):
                resolved_count = len(inc_mgr._resolved_incidents)
        elif hasattr(world, "active_incidents"):
            active_val = getattr(world, "active_incidents")
            active_list = (
                list(active_val.values()) if isinstance(active_val, dict) else list(active_val)
            )

        by_type: dict[str, int] = {}
        for inc in active_list:
            t_name = getattr(inc, "incident_type", None)
            t_str = t_name.value if hasattr(t_name, "value") else str(t_name or "unknown")
            by_type[t_str] = by_type.get(t_str, 0) + 1

        return IncidentAnalytics(
            total_active_incidents=len(active_list),
            active_by_type=by_type,
            resolved_incidents=resolved_count,
        )

    @classmethod
    def _build_time_series(
        cls,
        tick_history: Sequence[TickResult],
        world: Any,
        max_points: int = 100,
    ) -> list[TimeSeriesPoint]:
        """Generate bounded, uniform discrete time-series points across tick history."""
        if not tick_history:
            return []

        total_ticks = len(tick_history)
        if total_ticks <= max_points:
            indices = list(range(total_ticks))
        else:
            step = (total_ticks - 1) / (max_points - 1)
            indices = [int(round(i * step)) for i in range(max_points)]
            # Ensure unique, sorted indices
            indices = sorted(list(set(indices)))

        points: list[TimeSeriesPoint] = []
        cum_dist = 0.0
        cum_crossings = 0
        cum_collisions = 0
        cum_near_misses = 0
        cum_reroutes = 0
        prev_edges: dict[str, str] = {}
        road_graph = getattr(world, "road_graph", None)
        active_inc_count = len(getattr(world, "active_incidents", {}) or {})

        for idx, tr in enumerate(tick_history):
            # Accumulate metrics up to this tick
            for vid, step_res in tr.step_results.items():
                cum_dist += getattr(step_res, "distance_traveled_m", 0.0) or 0.0
                cur_e = (
                    getattr(step_res, "current_edge_id", None)
                    if hasattr(step_res, "current_edge_id")
                    else (step_res.get("current_edge_id") if isinstance(step_res, dict) else None)
                )
                prev_e = prev_edges.get(vid)
                if prev_e and cur_e and prev_e != cur_e:
                    if road_graph and road_graph.has_edge(prev_e):
                        cum_crossings += 1
                if cur_e:
                    prev_edges[vid] = cur_e

            if tr.safety_metrics:
                cum_collisions += tr.safety_metrics.get("actual_collisions", 0)
                cum_near_misses += tr.safety_metrics.get("near_misses", 0)

            if tr.routing_metrics:
                cum_reroutes += tr.routing_metrics.get("reroutes_accepted", 0)

            if idx in indices:
                # Calculate point average speed
                active_count = len(tr.active_agent_ids)
                completed_count = len(tr.arrived_agent_ids)
                point_speeds = [
                    getattr(res, "new_speed_mps", 0.0)
                    if hasattr(res, "new_speed_mps")
                    else (res.get("new_speed_mps", 0.0) if isinstance(res, dict) else 0.0)
                    for res in tr.step_results.values()
                ]
                avg_speed = (
                    sum(point_speeds) / len(point_speeds) if point_speeds else 0.0
                )

                # Point PDR
                pdr = None
                if tr.communication_metrics:
                    s = tr.communication_metrics.get("messages_sent", 0)
                    d = tr.communication_metrics.get("messages_delivered", 0)
                    if s > 0:
                        pdr = round(d / s, 4)

                points.append(
                    TimeSeriesPoint(
                        tick=tr.tick,
                        timestamp_s=tr.elapsed_time_s,
                        completed_trips=completed_count,
                        active_vehicles=active_count,
                        total_distance_m=cum_dist,
                        avg_speed_mps=avg_speed,
                        intersection_crossings=cum_crossings,
                        v2v_pdr=pdr,
                        collisions=cum_collisions,
                        near_misses=cum_near_misses,
                        reroutes_accepted=cum_reroutes,
                        active_incidents=active_inc_count,
                    )
                )

        return points
