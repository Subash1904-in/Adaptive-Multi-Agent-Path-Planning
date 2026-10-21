"""Emergency corridor planning, route evaluation, and temporary reservation logic."""

from typing import Optional, Sequence

from apps.core.emergency.exceptions import (
    UnreachableEmergencyDestinationError,
)
from apps.core.emergency.models import (
    CorridorReservation,
    EmergencyConfig,
    EmergencyCorridor,
    PriorityRequest,
    ReservationConflictPolicy,
)
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.models import CostMode, RoutingAlgorithm
from apps.core.routing.planner import RoutePlanner


class EmergencyCorridorPlanner:
    """Plans prioritized route corridors and generates temporary road reservations."""

    def __init__(self, road_graph: RoadGraph, config: Optional[EmergencyConfig] = None) -> None:
        self.road_graph = road_graph
        self.config = config or EmergencyConfig()
        self._router = RoutePlanner(road_graph)

    def plan_corridor(
        self,
        request: PriorityRequest,
        start_node_id: str,
        destination_node_id: str,
        current_time_s: float,
        closed_edge_ids: Optional[set[str]] = None,
        lookahead_edges: Optional[int] = None,
    ) -> EmergencyCorridor:
        """Calculate optimal path and construct an EmergencyCorridor proposal.

        Args:
            request: Active PriorityRequest.
            start_node_id: Current start or nearest intersection node.
            destination_node_id: Target incident or response node.
            current_time_s: Current simulation elapsed time in seconds.
            closed_edge_ids: Optional set of closed edge IDs to avoid.
            lookahead_edges: Optional override of number of corridor edges to reserve.

        Returns:
            Constructed EmergencyCorridor.

        Raises:
            UnreachableEmergencyDestinationError: If no valid route exists on road graph.
        """
        if not self.road_graph.has_node(start_node_id):
            raise UnreachableEmergencyDestinationError(
                f"Start node '{start_node_id}' does not exist on road graph.",
                vehicle_id=request.vehicle_id,
                destination_node_id=destination_node_id,
            )
        if not self.road_graph.has_node(destination_node_id):
            raise UnreachableEmergencyDestinationError(
                f"Destination node '{destination_node_id}' does not exist on road graph.",
                vehicle_id=request.vehicle_id,
                destination_node_id=destination_node_id,
            )

        if start_node_id == destination_node_id:
            # Already at destination
            return EmergencyCorridor(
                corridor_id=f"corridor_{request.request_id}",
                request_id=request.request_id,
                vehicle_id=request.vehicle_id,
                edge_ids=(),
                node_ids=(start_node_id,),
                creation_time_s=current_time_s,
                expiry_time_s=current_time_s + self.config.default_corridor_ttl_s,
            )

        # Plan route with A* using travel time optimization
        routing_result = self._router.find_route(
            start_node_id=start_node_id,
            destination_node_id=destination_node_id,
            algorithm=RoutingAlgorithm.ASTAR,
            cost_mode=CostMode.TRAVEL_TIME,
            closed_edge_ids=closed_edge_ids,
        )

        if not routing_result.success or not routing_result.route:
            raise UnreachableEmergencyDestinationError(
                f"No route found from '{start_node_id}' to '{destination_node_id}' "
                f"for emergency vehicle '{request.vehicle_id}'.",
                vehicle_id=request.vehicle_id,
                destination_node_id=destination_node_id,
            )

        route = routing_result.route
        limit = lookahead_edges or self.config.corridor_lookahead_edges
        selected_edges = tuple(route.edge_ids[:limit])
        selected_nodes = tuple(route.node_ids[: len(selected_edges) + 1])

        corridor_id = f"corridor_{request.request_id}"
        expiry = current_time_s + self.config.default_corridor_ttl_s

        return EmergencyCorridor(
            corridor_id=corridor_id,
            request_id=request.request_id,
            vehicle_id=request.vehicle_id,
            edge_ids=selected_edges,
            node_ids=selected_nodes,
            creation_time_s=current_time_s,
            expiry_time_s=expiry,
            version=1,
            is_active=True,
            is_released=False,
        )

    def evaluate_and_create_reservations(
        self,
        corridor: EmergencyCorridor,
        request: PriorityRequest,
        existing_reservations: Sequence[CorridorReservation],
        current_time_s: float,
    ) -> tuple[list[CorridorReservation], list[str]]:
        """Evaluate conflict-free reservation of corridor edges and nodes.

        Returns:
            Tuple of (granted_reservations, conflicting_elements).
        """
        granted: list[CorridorReservation] = []
        conflicts: list[str] = []

        # Map active existing reservations by element
        active_res_by_element: dict[str, list[CorridorReservation]] = {}
        for r in existing_reservations:
            if not r.is_expired(current_time_s):
                elem = r.edge_id or r.node_id
                if elem:
                    active_res_by_element.setdefault(elem, []).append(r)

        # Check edge elements
        counter = 0
        for edge_id in corridor.edge_ids:
            counter += 1
            has_conflict = False
            if edge_id in active_res_by_element:
                for existing in active_res_by_element[edge_id]:
                    if existing.vehicle_id == corridor.vehicle_id:
                        continue  # Self-reservation is allowed/extended

                    # Conflict policy resolution
                    if self.config.conflict_policy == ReservationConflictPolicy.STRICT_PRIORITY:
                        # Lower number = higher priority
                        if request.priority_level < existing.priority_level:
                            # Higher priority preempts
                            continue
                        elif request.priority_level == existing.priority_level:
                            # Tie breaker: earlier creation time, then stable vehicle ID
                            req_key = (request.creation_time_s, request.vehicle_id)
                            ex_key = (existing.start_time_s, existing.vehicle_id)
                            if req_key < ex_key:
                                continue

                    has_conflict = True
                    conflicts.append(f"edge:{edge_id}")
                    break

            if not has_conflict:
                res = CorridorReservation(
                    reservation_id=f"res_{corridor.corridor_id}_e_{counter}",
                    corridor_id=corridor.corridor_id,
                    request_id=corridor.request_id,
                    vehicle_id=corridor.vehicle_id,
                    priority_level=request.priority_level,
                    edge_id=edge_id,
                    node_id=None,
                    start_time_s=current_time_s,
                    expiry_time_s=corridor.expiry_time_s,
                )
                granted.append(res)

        # Check intersection node elements
        node_counter = 0
        for node_id in corridor.node_ids:
            node_counter += 1
            has_conflict = False
            if node_id in active_res_by_element:
                for existing in active_res_by_element[node_id]:
                    if existing.vehicle_id == corridor.vehicle_id:
                        continue

                    if self.config.conflict_policy == ReservationConflictPolicy.STRICT_PRIORITY:
                        if request.priority_level < existing.priority_level:
                            continue
                        elif request.priority_level == existing.priority_level:
                            req_key = (request.creation_time_s, request.vehicle_id)
                            ex_key = (existing.start_time_s, existing.vehicle_id)
                            if req_key < ex_key:
                                continue

                    has_conflict = True
                    conflicts.append(f"node:{node_id}")
                    break

            if not has_conflict:
                res = CorridorReservation(
                    reservation_id=f"res_{corridor.corridor_id}_n_{node_counter}",
                    corridor_id=corridor.corridor_id,
                    request_id=corridor.request_id,
                    vehicle_id=corridor.vehicle_id,
                    priority_level=request.priority_level,
                    edge_id=None,
                    node_id=node_id,
                    start_time_s=current_time_s,
                    expiry_time_s=corridor.expiry_time_s,
                )
                granted.append(res)

        return granted, conflicts
