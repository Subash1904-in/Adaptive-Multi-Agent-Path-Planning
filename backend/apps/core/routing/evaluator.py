from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    ReportType,
)
from apps.core.domain.models import RoadEdge
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.costs import calculate_edge_cost
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode

if TYPE_CHECKING:
    from apps.core.kinematics.vehicle_agent import VehicleAgent


class DynamicEdgeCostEvaluator:
    """Evaluates scalar road edge costs combining baseline geometry and vehicle-private beliefs.

    Operates strictly on the querying vehicle's VehicleKnowledgeStore. Does not access
    global ground truth or other vehicles' private stores.
    """

    def __init__(
        self,
        road_graph: RoadGraph,
        knowledge_store: Optional[VehicleKnowledgeStore],
        config: Optional[AdaptiveRoutingConfig] = None,
        incident_manager: Optional[Any] = None,
    ) -> None:
        self.road_graph: RoadGraph = road_graph
        self.knowledge_store: Optional[VehicleKnowledgeStore] = knowledge_store
        self.config: AdaptiveRoutingConfig = config or AdaptiveRoutingConfig()
        self.incident_manager: Optional[Any] = incident_manager

    def get_closed_edges(self, current_time_s: float = 0.0) -> set[str]:
        """Identify set of directed road edge IDs currently considered impassable.

        Args:
            current_time_s: Current simulation timestamp.

        Returns:
            Set of closed road edge IDs according to local beliefs and active incidents.
        """
        closed_edges: set[str] = set()

        # Incorporate authoritative incident closures if incident manager is attached
        if self.incident_manager is not None:
            closed_edges.update(self.incident_manager.get_closed_edges(current_time_s))

        if self.knowledge_store is None:
            return closed_edges

        active_beliefs = self.knowledge_store.get_beliefs(
            active_only=True, current_time_s=current_time_s
        )

        for belief in active_beliefs.values():
            if belief.belief_type != ReportType.ROAD_CLOSURE:
                continue
            if belief.confidence < self.config.min_confidence_threshold:
                continue

            status_val = belief.attributes.get("closure_status")
            status_str = str(status_val).lower() if status_val is not None else ""
            if status_str in ("closed", "roadclosurestatus.closed"):
                if belief.status == BeliefStatus.ACTIVE:
                    closed_edges.add(belief.target_id)
                elif belief.status == BeliefStatus.DISPUTED:
                    if self.config.disputed_closure_policy == "conservative":
                        closed_edges.add(belief.target_id)

        return closed_edges

    def is_edge_closed(self, edge_id: str, current_time_s: float = 0.0) -> bool:
        """Check whether a specific edge is closed under current local beliefs."""
        return edge_id in self.get_closed_edges(current_time_s)

    def get_congestion_multiplier(self, edge_id: str, current_time_s: float = 0.0) -> float:
        """Derive multiplicative congestion penalty factor for a specific edge.

        Args:
            edge_id: Road edge identifier.
            current_time_s: Current simulation timestamp.

        Returns:
            float: Multiplier >= 1.0 (1.0 indicates free flow / no congestion).
        """
        base_mult = 1.0
        if self.incident_manager is not None:
            base_mult = max(
                base_mult, self.incident_manager.get_congestion_multiplier(edge_id, current_time_s)
            )

        if self.knowledge_store is None:
            return base_mult

        belief: Optional[BeliefRecord] = self.knowledge_store.get_belief(f"congestion:{edge_id}")
        if belief is None or belief.is_expired(current_time_s):
            return base_mult

        if belief.confidence < self.config.min_confidence_threshold:
            return base_mult

        if (
            belief.status == BeliefStatus.DISPUTED
            and self.config.disputed_closure_policy == "permissive"
        ):
            return base_mult

        # Direct travel time factor from report takes precedence if > 1.0
        ttf = belief.attributes.get("travel_time_factor")
        if ttf is not None:
            try:
                ttf_float = float(ttf)
                if ttf_float >= 1.0 and math.isfinite(ttf_float):
                    return max(base_mult, ttf_float)
            except (ValueError, TypeError):
                pass

        # Qualitative congestion level mapping
        level = belief.attributes.get("congestion_level")
        if level is not None:
            mult = self.config.congestion_multipliers.get(str(level).lower(), 1.0)
            return max(base_mult, float(mult))

        return base_mult

    def get_hazard_penalty(self, edge_id: str, current_time_s: float = 0.0) -> float:
        """Derive additive penalty for localized hazards affecting a specific edge.

        Args:
            edge_id: Road edge identifier.
            current_time_s: Current simulation timestamp.

        Returns:
            float: Additive hazard penalty >= 0.0.
        """
        total_penalty = 0.0
        if self.incident_manager is not None:
            total_penalty += self.incident_manager.get_hazard_penalty(edge_id, current_time_s)

        if self.knowledge_store is None:
            return total_penalty

        active_beliefs = self.knowledge_store.get_beliefs(
            active_only=True, current_time_s=current_time_s
        )

        for belief in active_beliefs.values():
            if belief.belief_type != ReportType.HAZARD:
                continue
            if belief.confidence < self.config.min_confidence_threshold:
                continue

            # Associate hazard with road edge
            matches_edge = (
                belief.target_id == edge_id or belief.attributes.get("edge_id") == edge_id
            )
            if not matches_edge:
                continue

            sev = str(belief.attributes.get("severity", "medium")).lower()
            pen = self.config.hazard_penalties.get(
                sev, self.config.hazard_penalties.get("default", 15.0)
            )
            total_penalty += max(0.0, float(pen))

        return total_penalty

    def calculate_dynamic_edge_cost(
        self,
        edge: RoadEdge,
        cost_mode: CostMode,
        current_time_s: float = 0.0,
    ) -> float:
        """Calculate the vehicle-specific scalar traversal cost of an edge.

        Formula:
            C_v(e) = C_0(e) * M_congestion(e) + P_hazard(e)

        Args:
            edge: Directed RoadEdge domain instance.
            cost_mode: Optimization objective (DISTANCE or TRAVEL_TIME).
            current_time_s: Current simulation timestamp.

        Returns:
            float: Finite positive scalar traversal cost.
        """
        if self.is_edge_closed(edge.id, current_time_s):
            return float("inf")

        base_cost = calculate_edge_cost(edge, cost_mode)
        multiplier = self.get_congestion_multiplier(edge.id, current_time_s)
        penalty = self.get_hazard_penalty(edge.id, current_time_s)

        total_cost = base_cost * multiplier + penalty
        if not math.isfinite(total_cost) or total_cost <= 0.0:
            return base_cost
        return total_cost

    def evaluate_remaining_route_cost(
        self,
        agent: VehicleAgent,
        cost_mode: CostMode,
        current_time_s: float = 0.0,
    ) -> float:
        """Evaluate total dynamic cost of an agent's remaining active route.

        Pro-rates progress along the current edge and sums dynamic costs of all
        subsequent edges. Returns infinity if any remaining edge is closed.

        Args:
            agent: VehicleAgent to evaluate.
            cost_mode: Optimization objective.
            current_time_s: Current simulation timestamp.

        Returns:
            float: Total remaining dynamic cost (or float('inf') if blocked).
        """
        if agent.is_arrived:
            return 0.0
        if not agent.route or not agent._segments:
            return 0.0

        closed_edges = self.get_closed_edges(current_time_s)

        if agent.is_idle:
            total_cost = 0.0
            for seg in agent._segments:
                if seg.edge_id in closed_edges:
                    return float("inf")
                edge = self.road_graph.get_edge(seg.edge_id)
                total_cost += self.calculate_dynamic_edge_cost(edge, cost_mode, current_time_s)
            return total_cost

        # Vehicle is actively EN_ROUTE or BLOCKED
        cur_idx = agent.current_edge_index
        if cur_idx >= len(agent._segments):
            return 0.0

        # Check future untraversed segments for closures
        for j in range(cur_idx + 1, len(agent._segments)):
            if agent._segments[j].edge_id in closed_edges:
                return float("inf")

        # Pro-rate current segment
        cur_seg = agent._segments[cur_idx]
        cur_edge = self.road_graph.get_edge(cur_seg.edge_id)
        rem_dist = max(0.0, cur_seg.length_m - agent.distance_along_segment_m)
        fraction_rem = (rem_dist / cur_seg.length_m) if cur_seg.length_m > 1e-6 else 0.0

        cur_cost = fraction_rem * self.calculate_dynamic_edge_cost(
            cur_edge, cost_mode, current_time_s
        )

        future_cost = 0.0
        for j in range(cur_idx + 1, len(agent._segments)):
            edge = self.road_graph.get_edge(agent._segments[j].edge_id)
            future_cost += self.calculate_dynamic_edge_cost(edge, cost_mode, current_time_s)

        return cur_cost + future_cost
