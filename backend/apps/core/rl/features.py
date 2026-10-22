"""Observation feature extraction and space definition for AMAPP RL environments.

Extracts typed, bounded, and deterministic observations from authoritative simulation state
without leaking future information or mutating the simulation world.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from apps.core.kinematics.vehicle_agent import VehicleAgent
    from apps.core.simulation.world import WorldState

from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.rl.exceptions import ObservationError

OBSERVATION_FEATURE_NAMES = (
    "pos_x",
    "pos_y",
    "speed_norm",
    "heading_sin",
    "heading_cos",
    "dest_pos_x",
    "dest_pos_y",
    "rel_dest_dx",
    "rel_dest_dy",
    "euclidean_dist_norm",
    "remaining_route_distance_norm",
    "route_progress_ratio",
    "is_en_route",
    "is_blocked",
    "is_arrived",
    "current_edge_speed_limit_norm",
    "current_edge_length_norm",
    "current_edge_congestion",
    "current_edge_is_closed",
    "num_outgoing_edges_norm",
    "upcoming_signal_state",
    "upcoming_signal_dist_norm",
    "nearest_vehicle_dist_norm",
    "nearest_vehicle_rel_speed_norm",
    "nearest_vehicle_bearing_sin",
    "nearest_vehicle_bearing_cos",
    "active_incident_count_norm",
    "nearest_closure_dist_norm",
    "emergency_vehicle_nearby",
    "consecutive_invalid_actions_norm",
    "step_fraction",
    "reserved_padding",
)


def _get_graph_bounds(world: WorldState) -> tuple[float, float, float, float, float]:
    """Compute (min_x, min_y, max_x, max_y, diag_span) of the road graph nodes."""
    nodes = world.road_graph.nodes()
    if not nodes:
        return -100.0, -100.0, 100.0, 100.0, 200.0 * math.sqrt(2)

    xs = [n.position.x for n in nodes]
    ys = [n.position.y for n in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max(max_x - min_x, 10.0)
    span_y = max(max_y - min_y, 10.0)
    diag = math.hypot(span_x, span_y)
    return min_x, min_y, max_x, max_y, max(diag, 10.0)


def extract_agent_observation(
    agent: VehicleAgent,
    world: WorldState,
    max_outgoing_actions: int = 8,
    consecutive_invalid_actions: int = 0,
    step_count: int = 0,
    max_steps: int = 200,
) -> np.ndarray:
    """Extract a 32-dimensional continuous observation vector for an agent.

    All features are strictly normalized and bounded in [-1.0, 1.0], using only
    authoritative local and observable world state.
    """
    v = agent.vehicle
    min_x, min_y, max_x, max_y, diag_span = _get_graph_bounds(world)

    # 1-2. Position normalized to [-1.0, 1.0]
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    norm_x = float(np.clip(2.0 * (v.position.x - min_x) / span_x - 1.0, -1.0, 1.0))
    norm_y = float(np.clip(2.0 * (v.position.y - min_y) / span_y - 1.0, -1.0, 1.0))

    # 3. Speed normalized
    max_speed = 30.0
    speed_norm = float(np.clip(v.speed_mps / max_speed, 0.0, 1.0))

    # 4-5. Heading sin/cos
    heading_sin = float(np.clip(math.sin(v.heading_rad), -1.0, 1.0))
    heading_cos = float(np.clip(math.cos(v.heading_rad), -1.0, 1.0))

    # 6-7. Destination position
    dest_pos = Position2D(x=v.position.x, y=v.position.y)
    if v.target_node_id and world.road_graph.has_node(v.target_node_id):
        dest_node = world.road_graph.get_node(v.target_node_id)
        dest_pos = dest_node.position
    dest_norm_x = float(np.clip(2.0 * (dest_pos.x - min_x) / span_x - 1.0, -1.0, 1.0))
    dest_norm_y = float(np.clip(2.0 * (dest_pos.y - min_y) / span_y - 1.0, -1.0, 1.0))

    # 8-10. Relative distance to destination
    dx = dest_pos.x - v.position.x
    dy = dest_pos.y - v.position.y
    rel_dx = float(np.clip(dx / diag_span, -1.0, 1.0))
    rel_dy = float(np.clip(dy / diag_span, -1.0, 1.0))
    euc_dist = math.hypot(dx, dy)
    euc_dist_norm = float(np.clip(euc_dist / diag_span, 0.0, 1.0))

    # 11-12. Route progress
    rem_dist = agent.remaining_route_distance_m
    tot_dist = max(agent.total_route_distance_m, 1.0)
    rem_dist_norm = float(np.clip(rem_dist / tot_dist, 0.0, 1.0))
    progress_ratio = float(np.clip(1.0 - rem_dist_norm, 0.0, 1.0))

    # 13-15. State flags
    is_en_route = 1.0 if agent.state == VehicleState.EN_ROUTE else 0.0
    is_blocked = 1.0 if agent.state in (VehicleState.BLOCKED, VehicleState.STOPPED) else 0.0
    is_arrived = 1.0 if agent.state == VehicleState.ARRIVED else 0.0

    # 16-19. Current edge features
    curr_edge = agent.current_edge
    edge_speed_limit_norm = 0.5
    edge_len_norm = 0.1
    edge_congestion = 0.0
    edge_closed = 0.0
    if curr_edge is not None:
        edge_speed_limit_norm = float(np.clip(curr_edge.speed_limit_mps / max_speed, 0.0, 1.0))
        edge_len_norm = float(np.clip(curr_edge.length_m / 500.0, 0.0, 1.0))
        if hasattr(world, "incident_manager") and world.incident_manager is not None:
            if world.incident_manager.is_edge_closed(curr_edge.id):
                edge_closed = 1.0
            cong_mult = world.incident_manager.get_congestion_multiplier(curr_edge.id)
            if cong_mult > 1.0:
                edge_congestion = float(np.clip((cong_mult - 1.0) / 4.0, 0.0, 1.0))

    # 20. Outgoing edges count from upcoming anchor node
    upcoming_node_id = None
    if curr_edge is not None:
        upcoming_node_id = curr_edge.end_node_id
    elif v.current_node_id:
        upcoming_node_id = v.current_node_id

    outgoing_count = 0
    if upcoming_node_id and world.road_graph.has_node(upcoming_node_id):
        outgoing_edges = world.road_graph.get_outgoing_edges(upcoming_node_id)
        outgoing_count = len(outgoing_edges)
    outgoing_norm = float(np.clip(outgoing_count / max(1, max_outgoing_actions), 0.0, 1.0))

    # 21-22. Traffic signal ahead
    signal_state_val = 0.0
    signal_dist_val = 1.0
    if upcoming_node_id:
        signals = [
            s for s in world.get_signals() if getattr(s, "node_id", None) == upcoming_node_id
        ]
        if signals:
            sig = signals[0]
            st = (
                sig.state.value
                if hasattr(sig.state, "value")
                else str(sig.state)
            )
            if "GREEN" in st.upper():
                signal_state_val = 0.33
            elif "YELLOW" in st.upper():
                signal_state_val = 0.66
            elif "RED" in st.upper():
                signal_state_val = 1.0
            if world.road_graph.has_node(upcoming_node_id):
                n_pos = world.road_graph.get_node(upcoming_node_id).position
                s_dist = math.hypot(n_pos.x - v.position.x, n_pos.y - v.position.y)
                signal_dist_val = float(np.clip(s_dist / 100.0, 0.0, 1.0))

    # 23-26. Nearest other vehicle
    nearest_v_dist = 1.0
    nearest_v_rel_speed = 0.0
    nearest_v_sin = 0.0
    nearest_v_cos = 1.0
    min_dist = float("inf")
    closest_v = None

    for other_agent in world.get_agents():
        ov = other_agent.vehicle
        if ov.id == v.id:
            continue
        dist = math.hypot(ov.position.x - v.position.x, ov.position.y - v.position.y)
        if dist < min_dist:
            min_dist = dist
            closest_v = ov

    if closest_v is not None and min_dist < 100.0:
        nearest_v_dist = float(np.clip(min_dist / 100.0, 0.0, 1.0))
        nearest_v_rel_speed = float(
            np.clip((closest_v.speed_mps - v.speed_mps) / max_speed, -1.0, 1.0)
        )
        angle = math.atan2(closest_v.position.y - v.position.y, closest_v.position.x - v.position.x)
        rel_angle = angle - v.heading_rad
        nearest_v_sin = float(np.clip(math.sin(rel_angle), -1.0, 1.0))
        nearest_v_cos = float(np.clip(math.cos(rel_angle), -1.0, 1.0))

    # 27-28. Incidents & Closures
    incident_count_norm = 0.0
    nearest_closure_dist_norm = 1.0
    if hasattr(world, "incident_manager") and world.incident_manager is not None:
        active_all = world.incident_manager.list_active()
        incident_count_norm = float(np.clip(len(active_all) / 10.0, 0.0, 1.0))
        for inc in active_all:
            if (
                getattr(inc, "incident_type", None)
                and getattr(inc.incident_type, "value", "") == "road_closure"
            ):
                if inc.affected_edge_id and world.road_graph.has_edge(inc.affected_edge_id):
                    edge = world.road_graph.get_edge(inc.affected_edge_id)
                    n_start = world.road_graph.get_node(edge.start_node_id).position
                    c_dist = math.hypot(n_start.x - v.position.x, n_start.y - v.position.y)
                    nearest_closure_dist_norm = min(
                        nearest_closure_dist_norm, float(np.clip(c_dist / 200.0, 0.0, 1.0))
                    )

    # 29. Emergency vehicle nearby
    emergency_nearby = 0.0
    if hasattr(world, "emergency_manager") and world.emergency_manager is not None:
        if hasattr(world.emergency_manager, "get_awareness"):
            awareness = world.emergency_manager.get_awareness(v.id)
            if awareness is not None and getattr(awareness, "is_active", False):
                emergency_nearby = 1.0
        if emergency_nearby == 0.0 and hasattr(world.emergency_manager, "active_requests"):
            for req in world.emergency_manager.active_requests.values():
                if req.vehicle_id != v.id and world.has_agent(req.vehicle_id):
                    ev = world.get_agent(req.vehicle_id).vehicle
                    d_em = math.hypot(ev.position.x - v.position.x, ev.position.y - v.position.y)
                    if d_em < 100.0:
                        emergency_nearby = 1.0
                        break

    # 30. Consecutive invalid actions
    invalid_norm = float(np.clip(consecutive_invalid_actions / 10.0, 0.0, 1.0))

    # 31. Step fraction
    step_frac = float(np.clip(step_count / max(1, max_steps), 0.0, 1.0))

    # 32. Reserved padding
    reserved = 0.0

    features = np.array(
        [
            norm_x,
            norm_y,
            speed_norm,
            heading_sin,
            heading_cos,
            dest_norm_x,
            dest_norm_y,
            rel_dx,
            rel_dy,
            euc_dist_norm,
            rem_dist_norm,
            progress_ratio,
            is_en_route,
            is_blocked,
            is_arrived,
            edge_speed_limit_norm,
            edge_len_norm,
            edge_congestion,
            edge_closed,
            outgoing_norm,
            signal_state_val,
            signal_dist_val,
            nearest_v_dist,
            nearest_v_rel_speed,
            nearest_v_sin,
            nearest_v_cos,
            incident_count_norm,
            nearest_closure_dist_norm,
            emergency_nearby,
            invalid_norm,
            step_frac,
            reserved,
        ],
        dtype=np.float32,
    )

    if not np.isfinite(features).all():
        bad_idx = np.where(~np.isfinite(features))[0]
        bad_names = [OBSERVATION_FEATURE_NAMES[i] for i in bad_idx]
        raise ObservationError(
            f"Non-finite values detected in observation features: {bad_names}",
            agent_id=v.id,
            details={"bad_indices": bad_idx.tolist(), "bad_names": bad_names},
        )

    return features
