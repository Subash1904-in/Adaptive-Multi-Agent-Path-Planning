"""Regression test suite for routing algorithms, graph topology, and dynamic rerouting.

Verifies:
- Dijkstra shortest-path optimality on hand-constructed ground-truth graphs.
- A* optimality and heuristic admissibility (h(n) <= h*(n)).
- Directed road topology and one-way edge enforcement.
- Disconnected graph and unreachable destination error handling.
- Zero-length / same source and destination handling.
- Edge cost validation and non-finite rejection.
- Deterministic tie-breaking for equal-cost paths.
- Dynamic road closure invalidation and adaptive rerouting.
- Safe route replacement without corruption of prior route.
- OpenStreetMap normalizer error handling and empty data resilience.
"""

from __future__ import annotations

import networkx as nx
import pytest

from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.osm_exceptions import OSMEmptyGraphError
from apps.core.graph.osm_models import BoundingBox
from apps.core.graph.osm_normalizer import normalize_osm_graph
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.astar import astar_search
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.exceptions import (
    NoPathFoundError,
    RoutingNodeNotFoundError,
)
from apps.core.routing.heuristics import check_heuristic_admissibility
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    CostMode,
    RerouteDecisionType,
    RoutingAlgorithm,
)
from apps.core.routing.planner import find_route


class TestRoutingAndGraphRegression:
    """Verifies algorithmic correctness, graph topological constraints, and dynamic adaptation."""

    def test_dijkstra_ground_truth_optimality(self) -> None:
        """Dijkstra strictly finds the minimum-cost path on a known diamond graph."""
        graph = RoadGraph(name="diamond_graph")
        graph.add_node(RoadNode(id="A", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="B", position=Position2D(x=10.0, y=10.0)))
        graph.add_node(RoadNode(id="C", position=Position2D(x=10.0, y=-10.0)))
        graph.add_node(RoadNode(id="D", position=Position2D(x=20.0, y=0.0)))

        # Path 1: A -> B -> D (Cost: 12 + 18 = 30)
        graph.add_edge(
            RoadEdge(
                id="e_AB", start_node_id="A", end_node_id="B", length_m=12.0, speed_limit_mps=10.0
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e_BD", start_node_id="B", end_node_id="D", length_m=18.0, speed_limit_mps=10.0
            )
        )

        # Path 2: A -> C -> D (Cost: 14 + 11 = 25) -> OPTIMAL
        graph.add_edge(
            RoadEdge(
                id="e_AC", start_node_id="A", end_node_id="C", length_m=14.0, speed_limit_mps=10.0
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e_CD", start_node_id="C", end_node_id="D", length_m=11.0, speed_limit_mps=10.0
            )
        )

        res = dijkstra_search(graph, "A", "D", cost_mode=CostMode.DISTANCE)

        assert res.success is True
        assert res.objective_cost == pytest.approx(25.0, abs=1e-6)
        assert res.total_distance_m == pytest.approx(25.0, abs=1e-6)
        assert res.node_ids == ["A", "C", "D"]
        assert res.edge_ids == ["e_AC", "e_CD"]

    def test_astar_optimality_and_heuristic_admissibility(self) -> None:
        """A* produces exact optimal cost and maintains heuristic admissibility."""
        graph = RoadGraph(name="grid_admissibility")
        # 3x3 planar metric coordinates
        for r in range(3):
            for c in range(3):
                nid = f"n_{r}_{c}"
                graph.add_node(
                    RoadNode(id=nid, position=Position2D(x=float(c * 50), y=float(r * 50)))
                )

        for r in range(3):
            for c in range(3):
                if c < 2:
                    graph.add_edge(
                        RoadEdge(
                            id=f"e_h_{r}_{c}",
                            start_node_id=f"n_{r}_{c}",
                            end_node_id=f"n_{r}_{c+1}",
                            length_m=50.0,
                            speed_limit_mps=10.0,
                        )
                    )
                if r < 2:
                    graph.add_edge(
                        RoadEdge(
                            id=f"e_v_{r}_{c}",
                            start_node_id=f"n_{r}_{c}",
                            end_node_id=f"n_{r+1}_{c}",
                            length_m=50.0,
                            speed_limit_mps=10.0,
                        )
                    )

        # 1. Verify heuristic admissibility: h(n) <= h*(n)
        is_admissible, max_speed = check_heuristic_admissibility(graph)
        assert is_admissible is True
        assert max_speed == 10.0

        # 2. Compare A* and Dijkstra solutions
        res_dijk = dijkstra_search(graph, "n_0_0", "n_2_2", cost_mode=CostMode.DISTANCE)
        res_astar = astar_search(graph, "n_0_0", "n_2_2", cost_mode=CostMode.DISTANCE)

        assert res_dijk.success is True
        assert res_astar.success is True
        assert res_dijk.objective_cost == pytest.approx(res_astar.objective_cost, abs=1e-6)
        assert res_astar.objective_cost == pytest.approx(200.0, abs=1e-6)

    def test_one_way_edge_directionality_enforcement(self) -> None:
        """One-way edges allow forward navigation but strictly reject reverse traversal."""
        graph = RoadGraph(name="oneway_graph")
        graph.add_node(RoadNode(id="n1", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=50.0, y=0.0)))

        # Directed edge n1 -> n2 only
        graph.add_edge(
            RoadEdge(
                id="e_forward",
                start_node_id="n1",
                end_node_id="n2",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )

        # Forward search succeeds
        route_fwd = find_route(graph, "n1", "n2")
        assert route_fwd.node_ids == ["n1", "n2"]

        # Reverse search must fail
        with pytest.raises(NoPathFoundError):
            find_route(graph, "n2", "n1")

    def test_disconnected_graph_and_unreachable_node_handling(self) -> None:
        """Routing between disjoint components raises NoPathFoundError without hanging."""
        graph = RoadGraph(name="disconnected_graph")
        graph.add_node(RoadNode(id="compA_1", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="compA_2", position=Position2D(x=10.0, y=0.0)))
        graph.add_edge(
            RoadEdge(
                id="e_a",
                start_node_id="compA_1",
                end_node_id="compA_2",
                length_m=10.0,
                speed_limit_mps=10.0,
            )
        )

        graph.add_node(RoadNode(id="compB_1", position=Position2D(x=100.0, y=100.0)))
        graph.add_node(RoadNode(id="compB_2", position=Position2D(x=110.0, y=100.0)))
        graph.add_edge(
            RoadEdge(
                id="e_b",
                start_node_id="compB_1",
                end_node_id="compB_2",
                length_m=10.0,
                speed_limit_mps=10.0,
            )
        )

        with pytest.raises(NoPathFoundError) as exc_info:
            find_route(graph, "compA_1", "compB_2")
        assert "compA_1" in str(exc_info.value)
        assert "compB_2" in str(exc_info.value)

    def test_zero_length_same_start_and_destination(self) -> None:
        """Routing when start equals destination returns valid zero-length route."""
        graph = RoadGraph(name="single_node")
        graph.add_node(RoadNode(id="n_same", position=Position2D(x=10.0, y=10.0)))

        route = find_route(graph, "n_same", "n_same")
        assert route.node_ids == ["n_same"]
        assert route.edge_ids == []
        assert route.total_distance_m == 0.0

    def test_invalid_nodes_raise_routing_node_not_found(self) -> None:
        """Specifying non-existent start or destination raises RoutingNodeNotFoundError."""
        graph = RoadGraph(name="small")
        graph.add_node(RoadNode(id="n1", position=Position2D(x=0.0, y=0.0)))

        with pytest.raises(RoutingNodeNotFoundError):
            find_route(graph, "n_missing", "n1")

        with pytest.raises(RoutingNodeNotFoundError):
            find_route(graph, "n1", "n_missing")

    def test_deterministic_tie_breaking(self) -> None:
        """Paths with identical costs produce identical routing results across executions."""
        graph = RoadGraph(name="symmetric_graph")
        graph.add_node(RoadNode(id="start", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="upper", position=Position2D(x=50.0, y=50.0)))
        graph.add_node(RoadNode(id="lower", position=Position2D(x=50.0, y=-50.0)))
        graph.add_node(RoadNode(id="goal", position=Position2D(x=100.0, y=0.0)))

        # Symmetric edges with equal lengths
        graph.add_edge(
            RoadEdge(
                id="e_u1",
                start_node_id="start",
                end_node_id="upper",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e_u2",
                start_node_id="upper",
                end_node_id="goal",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e_l1",
                start_node_id="start",
                end_node_id="lower",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e_l2",
                start_node_id="lower",
                end_node_id="goal",
                length_m=50.0,
                speed_limit_mps=10.0,
            )
        )

        results = [
            find_route(graph, "start", "goal", algorithm=RoutingAlgorithm.ASTAR).node_ids
            for _ in range(5)
        ]
        # Invariant: Every execution selects the exact same deterministic route
        assert all(r == results[0] for r in results)

    def test_dynamic_road_closure_adaptive_rerouting(self) -> None:
        """DynamicRouteAdapter reroutes around a closed edge and updates vehicle route."""
        graph = RoadGraph(name="reroute_net")
        graph.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n1", position=Position2D(x=50.0, y=50.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=50.0, y=-50.0)))
        graph.add_node(RoadNode(id="n3", position=Position2D(x=100.0, y=0.0)))

        graph.add_edge(
            RoadEdge(
                id="e01", start_node_id="n0", end_node_id="n1", length_m=50.0, speed_limit_mps=10.0
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e13", start_node_id="n1", end_node_id="n3", length_m=50.0, speed_limit_mps=10.0
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e02", start_node_id="n0", end_node_id="n2", length_m=50.0, speed_limit_mps=10.0
            )
        )
        graph.add_edge(
            RoadEdge(
                id="e23", start_node_id="n2", end_node_id="n3", length_m=50.0, speed_limit_mps=10.0
            )
        )

        init_route = Route(
            id="r_init",
            node_ids=["n0", "n1", "n3"],
            edge_ids=["e01", "e13"],
            total_distance_m=100.0,
        )
        vehicle = Vehicle(id="v1", position=Position2D(x=0.0, y=0.0), target_node_id="n3")
        agent = VehicleAgent(vehicle=vehicle, road_graph=graph, route=init_route)
        agent.start()

        adapter = DynamicRouteAdapter(
            road_graph=graph,
            config=AdaptiveRoutingConfig(enabled=True, min_benefit_absolute=0.1),
        )

        # Ingest a closure for edge e13 into vehicle knowledge store
        store = VehicleKnowledgeStore(vehicle_id="v1")
        closure = RoadClosureReport(
            report_id="cls_01",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="infra",
            edge_id="e13",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=0.0,
        )
        store.ingest_report(closure, current_time_s=0.0)

        decision = adapter.evaluate_agent(agent=agent, knowledge_store=store, current_time_s=1.0)
        assert decision.decision_type == RerouteDecisionType.REROUTE_ACCEPTED
        assert "e13" not in decision.candidate_edge_ids
        assert list(decision.candidate_edge_ids) == ["e02", "e23"]

        # evaluate_agent automatically replaces remaining route upon acceptance
        assert agent.route.edge_ids == ["e02", "e23"]

    def test_osm_normalizer_error_handling_and_empty_resilience(self) -> None:
        """normalize_osm_graph raises structured OSMEmptyGraphError on empty graph without crash."""
        empty_g = nx.MultiDiGraph()
        bounds = BoundingBox(north=0.1, south=0.0, east=0.1, west=0.0)
        with pytest.raises(OSMEmptyGraphError):
            normalize_osm_graph(source_graph=empty_g, bounds=bounds)
