from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Callable, Optional

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.graph.road_graph import RoadGraph

if TYPE_CHECKING:
    from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.evaluator import DynamicEdgeCostEvaluator
from apps.core.routing.exceptions import NoPathFoundError
from apps.core.routing.metrics import AdaptiveRoutingMetrics
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    CostMode,
    RerouteDecision,
    RerouteDecisionType,
)
from apps.core.routing.planner import RoutePlanner


class DynamicRouteAdapter:
    """Orchestrates decentralized adaptive rerouting policies for vehicle agents.

    Evaluates vehicle remaining paths against local traffic beliefs, enforces
    benefit thresholds and cooldowns, suppresses oscillations, and safely
    replaces active route suffixes.
    """

    def __init__(
        self,
        road_graph: RoadGraph,
        config: Optional[AdaptiveRoutingConfig] = None,
        decision_manager: Optional[Any] = None,
        emergency_manager: Optional[Any] = None,
    ) -> None:
        self.road_graph: RoadGraph = road_graph
        self.config: AdaptiveRoutingConfig = config or AdaptiveRoutingConfig()
        self.decision_manager: Optional[Any] = decision_manager
        self.emergency_manager: Optional[Any] = emergency_manager
        self.planner: RoutePlanner = RoutePlanner(road_graph)
        self.metrics: AdaptiveRoutingMetrics = AdaptiveRoutingMetrics()

        self._last_reroute_time: dict[str, float] = {}
        self._last_belief_fingerprints: dict[str, str] = {}
        self._last_decisions: dict[str, RerouteDecision] = {}

    def get_evaluator(
        self, knowledge_store: Optional[VehicleKnowledgeStore]
    ) -> DynamicEdgeCostEvaluator:
        """Create a DynamicEdgeCostEvaluator bound to this adapter's graph and config."""
        return DynamicEdgeCostEvaluator(
            road_graph=self.road_graph,
            knowledge_store=knowledge_store,
            config=self.config,
        )

    def _compute_belief_fingerprint(
        self,
        knowledge_store: Optional[VehicleKnowledgeStore],
        current_time_s: float,
    ) -> str:
        """Derive a deterministic fingerprint of active beliefs in a knowledge store."""
        if knowledge_store is None:
            return "no_store"

        active_beliefs = knowledge_store.get_beliefs(
            active_only=True, current_time_s=current_time_s
        )
        if not active_beliefs:
            return "empty"

        tokens = []
        for bid in sorted(active_beliefs.keys()):
            b = active_beliefs[bid]
            attr_items = sorted(
                (k, str(v)) for k, v in b.attributes.items() if k != "disputed_with"
            )
            tokens.append(f"{bid}:{b.status.value}:{b.confidence:.2f}:{attr_items}")
        return "|".join(tokens)

    def evaluate_agent(
        self,
        agent: VehicleAgent,
        knowledge_store: Optional[VehicleKnowledgeStore],
        current_time_s: float,
    ) -> RerouteDecision:
        """Evaluate an individual vehicle agent for potential adaptive route adjustment.

        Args:
            agent: The active VehicleAgent to evaluate.
            knowledge_store: The vehicle's private VehicleKnowledgeStore.
            current_time_s: Current simulation timestamp.

        Returns:
            RerouteDecision: Structured outcome with evaluated costs and route metadata.
        """
        vid = agent.vehicle.id

        if not self.config.enabled:
            return RerouteDecision(
                decision_type=RerouteDecisionType.NO_CHANGE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=0.0,
                reason="Adaptive routing is disabled.",
            )

        if agent.is_arrived:
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.DESTINATION_REACHED,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=0.0,
                reason="Vehicle already arrived at destination.",
            )
            self._last_decisions[vid] = dec
            return dec

        if not agent.route or not agent._segments:
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.NO_CHANGE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=0.0,
                reason="Vehicle has no active route assigned.",
            )
            self._last_decisions[vid] = dec
            return dec

        if knowledge_store is None:
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.NO_CHANGE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=0.0,
                reason="No vehicle knowledge store available.",
            )
            self._last_decisions[vid] = dec
            return dec

        self.metrics.record_evaluation()

        # Cooldown check
        last_time = self._last_reroute_time.get(vid)
        if (
            last_time is not None
            and (current_time_s - last_time) < self.config.reroute_cooldown_s - 1e-9
        ):
            self.metrics.record_cooldown_suppression()
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.COOLDOWN_ACTIVE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=0.0,
                reason=(
                    f"Cooldown active: {current_time_s - last_time:.2f}s elapsed "
                    f"< {self.config.reroute_cooldown_s:.2f}s cooldown."
                ),
            )
            self._last_decisions[vid] = dec
            return dec

        # Dynamic evaluator
        evaluator = DynamicEdgeCostEvaluator(self.road_graph, knowledge_store, self.config)
        current_cost = evaluator.evaluate_remaining_route_cost(
            agent, self.config.cost_mode, current_time_s
        )

        # Repeat suppression check (skip if current route is blocked by closure)
        cur_fp = self._compute_belief_fingerprint(knowledge_store, current_time_s)
        fp_key = f"{cur_fp}:edge_{agent.current_edge_index}"
        if (
            self.config.repeat_suppression
            and math.isfinite(current_cost)
            and self._last_belief_fingerprints.get(vid) == fp_key
        ):
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.NO_FRESH_INFORMATION,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=current_cost,
                reason="No fresh information or motion state change since last evaluation.",
            )
            self._last_decisions[vid] = dec
            return dec

        # Determine connection node and pro-rated cost of current edge
        at_origin = agent.is_idle or (
            agent.current_edge_index == 0 and agent.distance_along_segment_m < 1e-6
        )
        if at_origin:
            resume_node_id = agent._segments[0].start_node_id
            cur_edge_rem_cost = 0.0
        else:
            cur_seg = agent._segments[agent.current_edge_index]
            resume_node_id = cur_seg.end_node_id
            rem_dist = max(0.0, cur_seg.length_m - agent.distance_along_segment_m)
            fraction = (rem_dist / cur_seg.length_m) if cur_seg.length_m > 1e-6 else 0.0
            cur_edge = self.road_graph.get_edge(cur_seg.edge_id)
            cur_edge_rem_cost = fraction * evaluator.calculate_dynamic_edge_cost(
                cur_edge, self.config.cost_mode, current_time_s
            )

        # Check if already at or directly arriving at target destination
        if resume_node_id == agent.vehicle.target_node_id:
            self._last_belief_fingerprints[vid] = fp_key
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.NO_CHANGE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=current_cost,
                reason="Current edge terminates directly at target destination.",
            )
            self._last_decisions[vid] = dec
            return dec

        # Plan candidate route from resume_node_id to target destination
        closed_edges = evaluator.get_closed_edges(current_time_s)
        if closed_edges:
            self.metrics.record_closure_applied()

        self.metrics.record_candidate_computed()

        def dynamic_cost_fn(edge: Any, mode: CostMode) -> float:
            return evaluator.calculate_dynamic_edge_cost(edge, mode, current_time_s)

        try:
            routing_res = self.planner.find_route(
                start_node_id=resume_node_id,
                destination_node_id=agent.vehicle.target_node_id,
                algorithm=self.config.algorithm,
                cost_mode=self.config.cost_mode,
                closed_edge_ids=closed_edges,
                edge_cost_fn=dynamic_cost_fn,
            )
        except NoPathFoundError:
            self.metrics.record_no_route()
            self._last_belief_fingerprints[vid] = fp_key
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.NO_ALTERNATIVE_ROUTE,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=current_cost,
                reason=(
                    f"No viable alternative path from '{resume_node_id}' "
                    f"to '{agent.vehicle.target_node_id}'."
                ),
            )
            self._last_decisions[vid] = dec
            return dec

        candidate_cost = cur_edge_rem_cost + routing_res.objective_cost
        self._last_belief_fingerprints[vid] = fp_key

        # Benefit calculation and decision policy
        if self.decision_manager is not None and self.decision_manager.config.enabled:
            from apps.core.decision.models import (
                CandidateRoute,
                DecisionContext,
                DecisionOutcome,
            )

            corridor_edges = set()
            if self.emergency_manager and getattr(self.emergency_manager.config, "enabled", False):
                check_em = getattr(
                    self.emergency_manager, "is_emergency_vehicle", lambda _vid: False
                )
                if not check_em(vid):
                    corridors_dict = getattr(self.emergency_manager, "corridors", {})
                    for corr in corridors_dict.values():
                        corridor_edges.update(corr.edge_ids)

            if at_origin:
                cur_rem_edges = [s.edge_id for s in agent._segments]
                cur_rem_nodes = [s.start_node_id for s in agent._segments] + (
                    [agent._segments[-1].end_node_id] if agent._segments else []
                )
            else:
                cur_rem_edges = [s.edge_id for s in agent._segments[agent.current_edge_index :]]
                cur_rem_nodes = [agent._segments[agent.current_edge_index].start_node_id] + [
                    s.end_node_id for s in agent._segments[agent.current_edge_index :]
                ]

            # Assess observation confidence from local knowledge store
            cand_conf = 1.0
            if knowledge_store is not None:
                beliefs = knowledge_store.get_beliefs(
                    active_only=True, current_time_s=current_time_s
                )
                c_confs = [
                    b.confidence
                    for b in beliefs.values()
                    if hasattr(b, "edge_id") and b.edge_id in routing_res.edge_ids
                ]
                if c_confs:
                    cand_conf = sum(c_confs) / len(c_confs)

            cand_opt = CandidateRoute(
                candidate_id=f"cand_{vid}_{routing_res.route.id}",
                node_ids=tuple(routing_res.node_ids),
                edge_ids=tuple(routing_res.edge_ids),
                estimated_travel_time_s=routing_res.estimated_duration_s,
                total_distance_m=routing_res.total_distance_m,
                objective_cost=candidate_cost,
                confidence=cand_conf,
                source="adaptive_routing",
                is_current_route=False,
                route=routing_res.route,
            )

            cur_opt = CandidateRoute(
                candidate_id=f"cur_{vid}_{agent.route.id}",
                node_ids=tuple(cur_rem_nodes),
                edge_ids=tuple(cur_rem_edges),
                estimated_travel_time_s=current_cost if math.isfinite(current_cost) else 9999.0,
                total_distance_m=agent.total_route_distance_m,
                objective_cost=current_cost if math.isfinite(current_cost) else 9999.0,
                confidence=1.0,
                source="active_route",
                is_current_route=True,
                route=agent.route,
            )

            dec_ctx = DecisionContext(
                agent_id=vid,
                current_time_s=current_time_s,
                destination_node_id=agent.vehicle.target_node_id,
                current_node_id=agent.vehicle.current_node_id,
                current_edge_id=agent.vehicle.current_edge_id,
                current_route_id=agent.route.id,
                current_cost=current_cost,
                current_route_edge_ids=tuple(cur_rem_edges),
                known_closed_edges=frozenset(closed_edges),
                emergency_corridor_edges=frozenset(corridor_edges),
            )

            dec_result = self.decision_manager.evaluate_decision(
                context=dec_ctx,
                candidates=[cand_opt, cur_opt],
                applied=True,
            )

            if (
                dec_result.outcome == DecisionOutcome.ACCEPT
                and dec_result.selected_candidate_id == cand_opt.candidate_id
            ):
                accept = True
                benefit = (
                    current_cost - candidate_cost if math.isfinite(current_cost) else float("inf")
                )
                req_benefit = 0.0
            else:
                accept = False
                if dec_result.outcome == DecisionOutcome.REJECT:
                    self.metrics.record_insufficient_benefit()
                    dec = RerouteDecision(
                        decision_type=RerouteDecisionType.REROUTE_REJECTED,
                        vehicle_id=vid,
                        timestamp_s=current_time_s,
                        current_cost=current_cost,
                        candidate_cost=candidate_cost,
                        cost_improvement=(
                            current_cost - candidate_cost if math.isfinite(current_cost) else None
                        ),
                        old_route_id=agent.route.id,
                        reason=f"Policy rejected route: {dec_result.reason}",
                    )
                    self._last_decisions[vid] = dec
                    return dec
                elif dec_result.outcome == DecisionOutcome.DEFER:
                    self.metrics.record_insufficient_benefit()
                    dec = RerouteDecision(
                        decision_type=RerouteDecisionType.INSUFFICIENT_BENEFIT,
                        vehicle_id=vid,
                        timestamp_s=current_time_s,
                        current_cost=current_cost,
                        candidate_cost=candidate_cost,
                        cost_improvement=(
                            current_cost - candidate_cost if math.isfinite(current_cost) else None
                        ),
                        old_route_id=agent.route.id,
                        reason=f"Policy deferred route change: {dec_result.reason}",
                    )
                    self._last_decisions[vid] = dec
                    return dec
                else:
                    self.metrics.record_insufficient_benefit()
                    dec = RerouteDecision(
                        decision_type=RerouteDecisionType.NO_CHANGE,
                        vehicle_id=vid,
                        timestamp_s=current_time_s,
                        current_cost=current_cost,
                        candidate_cost=candidate_cost,
                        cost_improvement=0.0,
                        old_route_id=agent.route.id,
                        reason=f"Policy decided: {dec_result.reason}",
                    )
                    self._last_decisions[vid] = dec
                    return dec
        else:
            if math.isinf(current_cost):
                # Active road closure on current route: accept alternative immediately
                benefit = float("inf")
                accept = True
                req_benefit = 0.0
            else:
                benefit = current_cost - candidate_cost
                req_benefit = max(
                    self.config.min_absolute_benefit,
                    self.config.min_relative_benefit * current_cost,
                )
                accept = benefit >= req_benefit - 1e-9

        if accept:
            # Verify candidate route does not exactly duplicate remaining route
            if not math.isinf(current_cost):
                if at_origin:
                    cur_edges = [s.edge_id for s in agent._segments]
                else:
                    cur_edges = [s.edge_id for s in agent._segments[agent.current_edge_index + 1 :]]
                if list(routing_res.edge_ids) == cur_edges:
                    self.metrics.record_insufficient_benefit()
                    dec = RerouteDecision(
                        decision_type=RerouteDecisionType.INSUFFICIENT_BENEFIT,
                        vehicle_id=vid,
                        timestamp_s=current_time_s,
                        current_cost=current_cost,
                        candidate_cost=candidate_cost,
                        cost_improvement=0.0,
                        old_route_id=agent.route.id,
                        reason="Candidate route is topologically identical to current route.",
                    )
                    self._last_decisions[vid] = dec
                    return dec

            old_route_id = agent.route.id
            new_route = agent.replace_remaining_route(routing_res.route, resume_node_id)
            self._last_reroute_time[vid] = current_time_s

            if math.isfinite(benefit):
                savings = benefit
            elif math.isfinite(routing_res.objective_cost):
                savings = routing_res.objective_cost
            else:
                savings = 0.0
            self.metrics.record_accepted(vid, savings)

            reason_str = (
                f"Reroute accepted: cost improved by {benefit:.2f} (required: {req_benefit:.2f})."
                if math.isfinite(benefit)
                else "Reroute accepted: avoided road closure on active route."
            )
            dec = RerouteDecision(
                decision_type=RerouteDecisionType.REROUTE_ACCEPTED,
                vehicle_id=vid,
                timestamp_s=current_time_s,
                current_cost=current_cost,
                candidate_cost=candidate_cost,
                cost_improvement=benefit,
                old_route_id=old_route_id,
                new_route_id=new_route.id,
                candidate_node_ids=tuple(routing_res.node_ids),
                candidate_edge_ids=tuple(routing_res.edge_ids),
                reason=reason_str,
            )
            self._last_decisions[vid] = dec
            return dec

        # Insufficient benefit
        self.metrics.record_insufficient_benefit()
        dec = RerouteDecision(
            decision_type=RerouteDecisionType.INSUFFICIENT_BENEFIT,
            vehicle_id=vid,
            timestamp_s=current_time_s,
            current_cost=current_cost,
            candidate_cost=candidate_cost,
            cost_improvement=benefit,
            old_route_id=agent.route.id,
            candidate_node_ids=tuple(routing_res.node_ids),
            candidate_edge_ids=tuple(routing_res.edge_ids),
            reason=f"Benefit {benefit:.2f} below required threshold {req_benefit:.2f}.",
        )
        self._last_decisions[vid] = dec
        return dec

    def step(
        self,
        agents: list[VehicleAgent],
        get_knowledge_store_fn: Callable[[str], Optional[VehicleKnowledgeStore]],
        current_time_s: float,
    ) -> list[RerouteDecision]:
        """Execute adaptive routing evaluation across all agents in deterministic order.

        Args:
            agents: Sequence of registered VehicleAgents.
            get_knowledge_store_fn: Callback retrieving an agent's VehicleKnowledgeStore.
            current_time_s: Current simulation timestamp.

        Returns:
            List of RerouteDecisions in deterministic vehicle ID order.
        """
        decisions: list[RerouteDecision] = []
        for agent in sorted(agents, key=lambda a: a.vehicle.id):
            k_store = get_knowledge_store_fn(agent.vehicle.id)
            dec = self.evaluate_agent(agent, k_store, current_time_s)
            decisions.append(dec)
        return decisions

    def capture_state(self) -> dict[str, Any]:
        """Capture lightweight snapshot of internal adapter state for atomic rollback."""
        return {
            "metrics": self.metrics.clone(),
            "last_reroute_time": dict(self._last_reroute_time),
            "last_belief_fingerprints": dict(self._last_belief_fingerprints),
            "last_decisions": dict(self._last_decisions),
        }

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        """Restore internal adapter state from a captured snapshot."""
        self.metrics = snapshot["metrics"].clone()
        self._last_reroute_time = dict(snapshot["last_reroute_time"])
        self._last_belief_fingerprints = dict(snapshot["last_belief_fingerprints"])
        self._last_decisions = dict(snapshot["last_decisions"])

    def reset(self) -> None:
        """Reset metrics, cooldown timers, fingerprints, and cached decisions."""
        self.metrics.reset()
        self._last_reroute_time.clear()
        self._last_belief_fingerprints.clear()
        self._last_decisions.clear()
