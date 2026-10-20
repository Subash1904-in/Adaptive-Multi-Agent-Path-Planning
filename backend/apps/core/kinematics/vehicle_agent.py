"""VehicleAgent abstraction for individual vehicle lifecycle and route following.

This module coordinates an individual Vehicle entity advancing along a planned Route
over a directed RoadGraph according to deterministic kinematics.
"""

from dataclasses import dataclass
from typing import Optional

from apps.core.domain.enums import VehicleState
from apps.core.domain.models import RoadEdge, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.exceptions import (
    InvalidLifecycleTransitionError,
    InvalidRouteError,
)
from apps.core.kinematics.models import KinematicsConfig, MotionStepResult
from apps.core.kinematics.motion import (
    compute_heading,
    integrate_motion,
    interpolate_position,
    validate_motion_inputs,
)


@dataclass(frozen=True)
class RouteSegment:
    """Internal representation of a directed route segment between two consecutive nodes."""

    edge_id: str
    start_node_id: str
    end_node_id: str
    length_m: float
    speed_limit_mps: float
    start_pos: Position2D
    end_pos: Position2D
    heading_rad: float


class VehicleAgent:
    """Agent coordinator managing lifecycle, motion stepping, and route tracking for a Vehicle.

    Operates strictly on an individual vehicle basis without a global simulation clock.
    Step calls are caller-driven and 100% deterministic.
    """

    def __init__(
        self,
        vehicle: Vehicle,
        road_graph: RoadGraph,
        route: Optional[Route] = None,
        config: Optional[KinematicsConfig] = None,
    ) -> None:
        """Initialize the vehicle agent.

        Args:
            vehicle: Authoritative Vehicle domain entity.
            road_graph: RoadGraph providing topological connectivity and node positions.
            route: Optional initial planned Route to assign.
            config: Optional physical kinematics limits and parameters.
        """
        if not isinstance(vehicle, Vehicle):
            raise TypeError(f"Expected Vehicle instance, got {type(vehicle).__name__}.")
        if not isinstance(road_graph, RoadGraph):
            raise TypeError(f"Expected RoadGraph instance, got {type(road_graph).__name__}.")

        self.vehicle: Vehicle = vehicle
        self.road_graph: RoadGraph = road_graph
        self.config: KinematicsConfig = config or KinematicsConfig()
        self.route: Optional[Route] = None
        self._segments: list[RouteSegment] = []
        self.current_edge_index: int = 0
        self.distance_along_segment_m: float = 0.0
        self.total_route_distance_m: float = 0.0

        if route is not None:
            self.assign_route(route)

    @property
    def state(self) -> VehicleState:
        """Current operational lifecycle state of the vehicle."""
        return self.vehicle.state

    @property
    def is_idle(self) -> bool:
        """True if the vehicle has not yet started route navigation."""
        return self.state == VehicleState.IDLE

    @property
    def is_en_route(self) -> bool:
        """True if the vehicle is actively following an assigned route."""
        return self.state == VehicleState.EN_ROUTE

    @property
    def is_blocked(self) -> bool:
        """True if the vehicle is paused or temporarily blocked."""
        return self.state in (VehicleState.BLOCKED, VehicleState.STOPPED)

    @property
    def is_arrived(self) -> bool:
        """True if the vehicle has reached its final route destination."""
        return self.state == VehicleState.ARRIVED

    @property
    def current_edge(self) -> Optional[RoadEdge]:
        """RoadEdge currently occupied by the vehicle, or None if idle/arrived/unassigned."""
        if not self._segments or self.is_arrived:
            return None
        if 0 <= self.current_edge_index < len(self._segments):
            edge_id = self._segments[self.current_edge_index].edge_id
            return self.road_graph.get_edge(edge_id)
        return None

    @property
    def remaining_route_distance_m(self) -> float:
        """Total physical distance in meters remaining to the final destination."""
        if not self._segments or self.is_arrived:
            return 0.0
        if self.current_edge_index >= len(self._segments):
            return 0.0

        cur_seg = self._segments[self.current_edge_index]
        rem_cur = max(0.0, cur_seg.length_m - self.distance_along_segment_m)
        rem_future = sum(s.length_m for s in self._segments[self.current_edge_index + 1 :])
        return rem_cur + rem_future

    def assign_route(self, route: Route) -> None:
        """Assign and validate a planned Route against the road graph.

        Raises:
            InvalidRouteError: If the route is not a Route instance, contains missing nodes/edges,
                               or violates directed graph connectivity.
        """
        if not isinstance(route, Route):
            raise InvalidRouteError(f"Expected Route instance, got {type(route).__name__}.")
        if len(route.node_ids) < 2:
            raise InvalidRouteError(
                f"Route must contain at least 2 nodes, got {len(route.node_ids)}.",
                route_id=route.id,
            )

        # 1. Validate all nodes exist in the road graph
        for nid in route.node_ids:
            if not self.road_graph.has_node(nid):
                raise InvalidRouteError(
                    f"Route node '{nid}' does not exist in the road graph.",
                    route_id=route.id,
                )

        # 2. Resolve and validate directed edges connecting consecutive nodes
        resolved_segments: list[RouteSegment] = []
        num_hops = len(route.node_ids) - 1

        if route.edge_ids:
            if len(route.edge_ids) != num_hops:
                raise InvalidRouteError(
                    f"Route has {len(route.node_ids)} nodes ({num_hops} hops) "
                    f"but {len(route.edge_ids)} edge_ids.",
                    route_id=route.id,
                )
            for i, eid in enumerate(route.edge_ids):
                if not self.road_graph.has_edge(eid):
                    raise InvalidRouteError(
                        f"Route edge '{eid}' does not exist in the road graph.",
                        route_id=route.id,
                    )
                edge = self.road_graph.get_edge(eid)
                u = route.node_ids[i]
                v = route.node_ids[i + 1]
                if edge.start_node_id != u or edge.end_node_id != v:
                    raise InvalidRouteError(
                        f"Route edge '{eid}' connects "
                        f"'{edge.start_node_id}' -> '{edge.end_node_id}', "
                        f"but route specifies '{u}' -> '{v}'.",
                        route_id=route.id,
                    )
                u_node = self.road_graph.get_node(u)
                v_node = self.road_graph.get_node(v)
                heading = compute_heading(
                    u_node.position, v_node.position, self.vehicle.heading_rad
                )
                resolved_segments.append(
                    RouteSegment(
                        edge_id=edge.id,
                        start_node_id=u,
                        end_node_id=v,
                        length_m=edge.length_m,
                        speed_limit_mps=edge.speed_limit_mps,
                        start_pos=u_node.position,
                        end_pos=v_node.position,
                        heading_rad=heading,
                    )
                )
        else:
            for i in range(num_hops):
                u = route.node_ids[i]
                v = route.node_ids[i + 1]
                edge = self.road_graph.get_edge_between(u, v)
                if edge is None:
                    raise InvalidRouteError(
                        f"No directed edge connects '{u}' -> '{v}' in the road graph.",
                        route_id=route.id,
                    )
                u_node = self.road_graph.get_node(u)
                v_node = self.road_graph.get_node(v)
                heading = compute_heading(
                    u_node.position, v_node.position, self.vehicle.heading_rad
                )
                resolved_segments.append(
                    RouteSegment(
                        edge_id=edge.id,
                        start_node_id=u,
                        end_node_id=v,
                        length_m=edge.length_m,
                        speed_limit_mps=edge.speed_limit_mps,
                        start_pos=u_node.position,
                        end_pos=v_node.position,
                        heading_rad=heading,
                    )
                )

        self.route = route
        self._segments = resolved_segments
        self.total_route_distance_m = sum(s.length_m for s in resolved_segments)
        self.current_edge_index = 0
        self.distance_along_segment_m = 0.0

        # Synchronize vehicle domain entity
        self.vehicle.route_id = route.id
        self.vehicle.target_node_id = route.node_ids[-1]

        # If vehicle is currently idle, place at the start of the route
        if self.vehicle.state == VehicleState.IDLE:
            first_seg = self._segments[0]
            self.vehicle.position = first_seg.start_pos
            self.vehicle.heading_rad = first_seg.heading_rad
            self.vehicle.current_node_id = first_seg.start_node_id
            self.vehicle.current_edge_id = first_seg.edge_id
            # Preserve existing initial speed if non-zero, otherwise default to 0.0
            self.vehicle.speed_mps = max(0.0, self.vehicle.speed_mps)

    def start(self) -> None:
        """Transition vehicle from IDLE to EN_ROUTE.

        Raises:
            InvalidLifecycleTransitionError: If vehicle has no route, is paused, or already arrived.
        """
        if self.is_arrived:
            raise InvalidLifecycleTransitionError(
                "Cannot start a vehicle that has already arrived. "
                "Call reset() or assign a new route first.",
                from_state=self.state.value,
                to_state=VehicleState.EN_ROUTE.value,
            )
        if self.is_blocked:
            raise InvalidLifecycleTransitionError(
                f"Vehicle is currently in '{self.state.value}' state. "
                "Call resume() instead of start().",
                from_state=self.state.value,
                to_state=VehicleState.EN_ROUTE.value,
            )
        if self.route is None or not self._segments:
            raise InvalidLifecycleTransitionError(
                "Cannot start vehicle without a valid assigned route.",
                from_state=self.state.value,
                to_state=VehicleState.EN_ROUTE.value,
            )

        self.vehicle.state = VehicleState.EN_ROUTE

    def pause(self) -> None:
        """Pause or block progress along the route (transitions EN_ROUTE to BLOCKED)."""
        self.block()

    def block(self) -> None:
        """Block or pause progress along the route (transitions EN_ROUTE to BLOCKED).

        Preserves exact position and progress along the active segment while bringing speed to 0.
        """
        if self.is_blocked:
            return  # Idempotent no-op
        if not self.is_en_route:
            raise InvalidLifecycleTransitionError(
                f"Cannot block vehicle in '{self.state.value}' state (must be en_route).",
                from_state=self.state.value,
                to_state=VehicleState.BLOCKED.value,
            )

        self.vehicle.state = VehicleState.BLOCKED
        self.vehicle.speed_mps = 0.0

    def resume(self) -> None:
        """Resume route following from paused or blocked state (BLOCKED to EN_ROUTE)."""
        if self.is_en_route:
            return  # Idempotent no-op
        if not self.is_blocked:
            raise InvalidLifecycleTransitionError(
                f"Cannot resume vehicle in '{self.state.value}' state "
                "(must be blocked or stopped).",
                from_state=self.state.value,
                to_state=VehicleState.EN_ROUTE.value,
            )

        self.vehicle.state = VehicleState.EN_ROUTE

    def reset(self, route: Optional[Route] = None) -> None:
        """Reset vehicle state to IDLE and re-initialize progress.

        Args:
            route: Optional new route to assign. If omitted, resets to start of current route.
        """
        self.vehicle.state = VehicleState.IDLE
        self.vehicle.speed_mps = 0.0
        if route is not None:
            self.assign_route(route)
        elif self.route is not None:
            self.assign_route(self.route)
        else:
            self.current_edge_index = 0
            self.distance_along_segment_m = 0.0

    def step(self, dt: float, target_accel: Optional[float] = None) -> MotionStepResult:
        """Advance the vehicle agent by a discrete simulation time step dt.

        Args:
            dt: Simulation time step in seconds (must be finite and > 0.0).
            target_accel: Optional commanded acceleration in m/s^2. If None, defaults
                          to accelerating smoothly to the road or vehicle speed limit.

        Returns:
            MotionStepResult containing comprehensive step metrics and updated state.
        """
        validate_motion_inputs(dt, target_accel, self.vehicle.speed_mps)

        prev_pos = self.vehicle.position
        prev_speed = self.vehicle.speed_mps

        # If not actively en route, the vehicle remains stationary
        if not self.is_en_route:
            return MotionStepResult(
                previous_position=prev_pos,
                new_position=prev_pos,
                previous_speed_mps=prev_speed,
                new_speed_mps=prev_speed if self.is_idle else 0.0,
                applied_acceleration_mps2=0.0,
                distance_traveled_m=0.0,
                remaining_route_distance_m=self.remaining_route_distance_m,
                current_edge_id=self.vehicle.current_edge_id,
                current_node_id=self.vehicle.current_node_id,
                state=self.state,
                arrived=self.is_arrived,
                heading_rad=self.vehicle.heading_rad,
                dt_s=dt,
            )

        cur_seg = self._segments[self.current_edge_index]
        remaining_dist = self.remaining_route_distance_m

        # Compute default acceleration command if none was explicitly supplied
        if target_accel is None:
            effective_speed_cap = (
                min(self.config.max_speed_mps, cur_seg.speed_limit_mps)
                if self.config.enforce_road_speed_limits
                else self.config.max_speed_mps
            )
            if self.vehicle.speed_mps < effective_speed_cap - 1e-4:
                cmd_accel = self.config.max_acceleration_mps2
            elif self.vehicle.speed_mps > effective_speed_cap + 1e-4:
                cmd_accel = -self.config.max_deceleration_mps2
            else:
                cmd_accel = 0.0
        else:
            cmd_accel = target_accel

        new_speed, applied_accel, dist_to_move = integrate_motion(
            current_speed=self.vehicle.speed_mps,
            target_accel=cmd_accel,
            dt=dt,
            config=self.config,
            speed_limit=cur_seg.speed_limit_mps,
            distance_limit=remaining_dist,
        )

        actual_dist_moved = dist_to_move
        remaining_step_dist = dist_to_move

        # Advance along one or multiple road segments
        while remaining_step_dist > 0.0 and self.current_edge_index < len(self._segments):
            seg = self._segments[self.current_edge_index]
            seg_len = seg.length_m

            # Zero-length road segment handling policy: instant progression
            if seg_len <= 1e-6:
                if self.current_edge_index == len(self._segments) - 1:
                    # Final node reached
                    self.vehicle.position = seg.end_pos
                    self.vehicle.heading_rad = seg.heading_rad
                    self.vehicle.state = VehicleState.ARRIVED
                    self.vehicle.speed_mps = 0.0
                    self.vehicle.current_node_id = seg.end_node_id
                    self.vehicle.current_edge_id = None
                    remaining_step_dist = 0.0
                    break
                else:
                    self.current_edge_index += 1
                    self.distance_along_segment_m = 0.0
                    continue

            rem_on_seg = seg_len - self.distance_along_segment_m

            if remaining_step_dist < rem_on_seg - 1e-7:
                # Normal advancement within current segment
                self.distance_along_segment_m += remaining_step_dist
                fraction = self.distance_along_segment_m / seg_len
                self.vehicle.position = interpolate_position(seg.start_pos, seg.end_pos, fraction)
                self.vehicle.heading_rad = seg.heading_rad
                self.vehicle.speed_mps = new_speed
                self.vehicle.current_edge_id = seg.edge_id
                self.vehicle.current_node_id = None
                remaining_step_dist = 0.0
            else:
                # Cross or reach the endpoint of current segment
                remaining_step_dist -= rem_on_seg
                if self.current_edge_index == len(self._segments) - 1:
                    # Reached final route destination
                    self.distance_along_segment_m = seg_len
                    self.vehicle.position = seg.end_pos
                    self.vehicle.heading_rad = seg.heading_rad
                    self.vehicle.state = VehicleState.ARRIVED
                    self.vehicle.speed_mps = 0.0
                    self.vehicle.current_node_id = seg.end_node_id
                    self.vehicle.current_edge_id = None
                    remaining_step_dist = 0.0
                    break
                else:
                    # Advance to next directed segment
                    self.current_edge_index += 1
                    self.distance_along_segment_m = 0.0
                    next_seg = self._segments[self.current_edge_index]
                    self.vehicle.position = next_seg.start_pos
                    self.vehicle.heading_rad = next_seg.heading_rad
                    self.vehicle.current_edge_id = next_seg.edge_id
                    self.vehicle.current_node_id = next_seg.start_node_id
                    self.vehicle.speed_mps = new_speed

        return MotionStepResult(
            previous_position=prev_pos,
            new_position=self.vehicle.position,
            previous_speed_mps=prev_speed,
            new_speed_mps=self.vehicle.speed_mps,
            applied_acceleration_mps2=applied_accel,
            distance_traveled_m=actual_dist_moved,
            remaining_route_distance_m=self.remaining_route_distance_m,
            current_edge_id=self.vehicle.current_edge_id,
            current_node_id=self.vehicle.current_node_id,
            state=self.state,
            arrived=self.is_arrived,
            heading_rad=self.vehicle.heading_rad,
            dt_s=dt,
        )
