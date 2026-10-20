"""Integration tests for SimulationEngine adaptive routing, tick boundaries, and atomic rollback."""

from unittest.mock import patch

import pytest

from apps.core.coordination.models import (
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    RerouteDecisionType,
)
from apps.core.scenarios import (
    create_adaptive_reroute_closure_scenario,
    create_adaptive_reroute_congestion_scenario,
    create_adaptive_reroute_cooldown_scenario,
    create_adaptive_reroute_current_edge_continuation_scenario,
    create_adaptive_reroute_delayed_network_scenario,
    create_adaptive_reroute_hazard_scenario,
    create_adaptive_reroute_insufficient_benefit_scenario,
    create_adaptive_reroute_no_alternative_scenario,
    create_adaptive_reroute_stale_report_scenario,
    run_scenario,
)
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.world import WorldState


@pytest.fixture
def branching_world() -> tuple[WorldState, SimulationEngine, VehicleAgent]:
    """World with two alternative routes from n0 to n3.

    Upper: n0 -> n1 -> n3 (e01: 100m, e13: 100m)
    Lower: n0 -> n2 -> n3 (e02: 100m, e23: 100m)
    """
    g = RoadGraph(name="branching_network")
    g.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=50.0)))
    g.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=100.0)))
    g.add_node(RoadNode(id="n2", position=Position2D(x=100.0, y=0.0)))
    g.add_node(RoadNode(id="n3", position=Position2D(x=200.0, y=50.0)))

    g.add_edge(
        RoadEdge(
            id="e01", start_node_id="n0", end_node_id="n1", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e13", start_node_id="n1", end_node_id="n3", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e02", start_node_id="n0", end_node_id="n2", length_m=100.0, speed_limit_mps=10.0
        )
    )
    g.add_edge(
        RoadEdge(
            id="e23", start_node_id="n2", end_node_id="n3", length_m=100.0, speed_limit_mps=10.0
        )
    )

    initial_route = Route(
        id="route_upper",
        node_ids=["n0", "n1", "n3"],
        edge_ids=["e01", "e13"],
        total_distance_m=200.0,
    )
    v = Vehicle(
        id="veh_01",
        position=Position2D(x=0.0, y=50.0),
        target_node_id="n3",
    )
    agent = VehicleAgent(vehicle=v, road_graph=g, route=initial_route)
    agent.start()

    clock = SimulationClock(time_step_s=0.1)
    world = WorldState(
        road_graph=g,
        clock=clock,
        coordination_config=CoordinationConfig(enabled=True),
        adaptive_routing_config=AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=0.1,
            min_relative_benefit=0.01,
        ),
    )
    world.add_agent(agent)
    world.save_baseline()

    engine = SimulationEngine(world=world)
    return world, engine, agent


class TestSimulationEngineAdaptiveRouting:
    """Test suite for engine-level adaptive routing integration and rollback."""

    def test_routing_decisions_emitted_in_tick_result(
        self, branching_world: tuple[WorldState, SimulationEngine, VehicleAgent]
    ) -> None:
        """Engine step records routing decisions and metrics in TickResult."""
        world, engine, agent = branching_world

        # Ingest a closure belief into agent's store
        store = world.coordination_manager.get_store("veh_01")
        assert store is not None
        closure = RoadClosureReport(
            report_id="cls_e13",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_other",
            edge_id="e13",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=0.0,
            expiry_timestamp_s=50.0,
        )
        store.ingest_report(closure, current_time_s=0.0)

        tick_res = engine.step()
        assert tick_res.routing_decisions is not None
        decs = {d["vehicle_id"]: d for d in tick_res.routing_decisions}
        assert "veh_01" in decs
        dec = decs["veh_01"]
        assert dec["decision_type"] == RerouteDecisionType.REROUTE_ACCEPTED.value
        assert tick_res.routing_metrics["reroutes_accepted"] >= 1

        # Verify agent switched to lower path (e02 -> e23)
        assert [s.edge_id for s in agent._segments] == ["e02", "e23"]

    def test_multi_vehicle_private_knowledge_isolation_in_engine(
        self, branching_world: tuple[WorldState, SimulationEngine, VehicleAgent]
    ) -> None:
        """Vehicle 1 with closure belief reroutes; Vehicle 2 retains original route."""
        world, engine, agent1 = branching_world
        g = world.road_graph

        # Add vehicle 2 with identical initial upper route
        route2 = Route(
            id="route_upper_v2",
            node_ids=["n0", "n1", "n3"],
            edge_ids=["e01", "e13"],
            total_distance_m=200.0,
        )
        v2 = Vehicle(id="veh_02", position=Position2D(x=0.0, y=50.0), target_node_id="n3")
        agent2 = VehicleAgent(vehicle=v2, road_graph=g, route=route2)
        agent2.start()
        world.add_agent(agent2)
        world.save_baseline()

        # Ingest closure strictly into veh_01's store
        store1 = world.coordination_manager.get_store("veh_01")
        assert store1 is not None
        closure = RoadClosureReport(
            report_id="cls_v1_only",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_source",
            edge_id="e13",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=0.0,
            expiry_timestamp_s=50.0,
        )
        store1.ingest_report(closure, current_time_s=0.0)

        tick_res = engine.step()
        decs = {d["vehicle_id"]: d for d in tick_res.routing_decisions}
        assert decs["veh_01"]["decision_type"] == "reroute_accepted"
        assert decs["veh_02"]["decision_type"] == "insufficient_benefit"

        # veh_01 rerouted to lower path; veh_02 remains on upper path
        assert [s.edge_id for s in agent1._segments] == ["e02", "e23"]
        assert [s.edge_id for s in agent2._segments] == ["e01", "e13"]

    def test_atomic_rollback_on_kinematics_failure(
        self, branching_world: tuple[WorldState, SimulationEngine, VehicleAgent]
    ) -> None:
        """A failure during kinematics restores pre-tick routes, kinematics, and metrics."""
        world, engine, agent = branching_world
        orig_route_id = agent.route.id
        orig_segments = [s.edge_id for s in agent._segments]
        orig_time = world.clock.elapsed_time_s

        # Ingest closure that will cause an accepted reroute in tick
        store = world.coordination_manager.get_store("veh_01")
        assert store is not None
        store.ingest_report(
            RoadClosureReport(
                report_id="cls_rb",
                report_type=ReportType.ROAD_CLOSURE,
                reporting_vehicle_id="veh_other",
                edge_id="e13",
                closure_status=RoadClosureStatus.CLOSED,
                timestamp_s=0.0,
                expiry_timestamp_s=50.0,
            ),
            current_time_s=0.0,
        )

        # Inject failure during agent.step (kinematics phase)
        with patch.object(agent, "step", side_effect=RuntimeError("Simulated kinematic failure")):
            with pytest.raises(TickExecutionError):
                engine.step()

        # Route must be rolled back to pre-tick route!
        assert agent.route.id == orig_route_id
        assert [s.edge_id for s in agent._segments] == orig_segments
        assert world.clock.elapsed_time_s == orig_time
        assert world.adaptive_routing_adapter.metrics.reroutes_accepted == 0

    def test_reset_restores_original_routes_and_adapter_state(
        self, branching_world: tuple[WorldState, SimulationEngine, VehicleAgent]
    ) -> None:
        """Engine reset restores baseline routes, cleared metrics, and pristine adapter state."""
        world, engine, agent = branching_world
        orig_route_id = agent.route.id
        orig_segments = [s.edge_id for s in agent._segments]

        # Ingest closure and step
        store = world.coordination_manager.get_store("veh_01")
        assert store is not None
        store.ingest_report(
            RoadClosureReport(
                report_id="cls_res",
                report_type=ReportType.ROAD_CLOSURE,
                reporting_vehicle_id="veh_other",
                edge_id="e13",
                closure_status=RoadClosureStatus.CLOSED,
                timestamp_s=0.0,
                expiry_timestamp_s=50.0,
            ),
            current_time_s=0.0,
        )
        engine.step()
        assert agent.route.id != orig_route_id

        # Reset world
        world.reset()
        assert agent.route.id == orig_route_id
        assert [s.edge_id for s in agent._segments] == orig_segments
        assert world.adaptive_routing_adapter.metrics.reroutes_accepted == 0

    def test_deterministic_replay_produces_identical_decisions_and_history(
        self, branching_world: tuple[WorldState, SimulationEngine, VehicleAgent]
    ) -> None:
        """Scenario run twice from baseline yields identical decisions and snapshots."""
        world, engine, agent = branching_world

        store = world.coordination_manager.get_store("veh_01")
        assert store is not None
        store.ingest_report(
            CongestionReport(
                report_id="cong_det",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_other",
                edge_id="e01",
                congestion_level=CongestionLevel.SEVERE,
                timestamp_s=0.0,
                expiry_timestamp_s=50.0,
            ),
            current_time_s=0.0,
        )

        res1 = engine.step()
        snap1 = world.get_snapshot()

        world.reset()
        # Re-ingest
        store = world.coordination_manager.get_store("veh_01")
        assert store is not None
        store.ingest_report(
            CongestionReport(
                report_id="cong_det",
                report_type=ReportType.CONGESTION,
                reporting_vehicle_id="veh_other",
                edge_id="e01",
                congestion_level=CongestionLevel.SEVERE,
                timestamp_s=0.0,
                expiry_timestamp_s=50.0,
            ),
            current_time_s=0.0,
        )

        res2 = engine.step()
        snap2 = world.get_snapshot()

        assert res1.routing_decisions == res2.routing_decisions
        assert res1.routing_metrics == res2.routing_metrics
        assert snap1.to_dict() == snap2.to_dict()


class TestScenarioRunnerAdaptiveScenarios:
    """Verification of Phase 15 standard deterministic scenario fixtures."""

    def test_run_adaptive_reroute_closure_scenario(self) -> None:
        """Run closure scenario fixture and verify successful completion."""
        scn = create_adaptive_reroute_closure_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success
        assert res.completed_ticks == 10
        assert res.final_world_snapshot.routing is not None

    def test_run_adaptive_reroute_congestion_scenario(self) -> None:
        """Run congestion avoidance scenario fixture."""
        scn = create_adaptive_reroute_congestion_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success
        assert res.completed_ticks == 10

    def test_run_adaptive_reroute_hazard_scenario(self) -> None:
        """Run hazard avoidance scenario fixture."""
        scn = create_adaptive_reroute_hazard_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_insufficient_benefit_scenario(self) -> None:
        """Run insufficient benefit scenario fixture."""
        scn = create_adaptive_reroute_insufficient_benefit_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_cooldown_scenario(self) -> None:
        """Run cooldown scenario fixture."""
        scn = create_adaptive_reroute_cooldown_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_stale_report_scenario(self) -> None:
        """Run stale report scenario fixture."""
        scn = create_adaptive_reroute_stale_report_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_no_alternative_scenario(self) -> None:
        """Run no alternative scenario fixture."""
        scn = create_adaptive_reroute_no_alternative_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_continuation_scenario(self) -> None:
        """Run current edge continuation scenario fixture."""
        scn = create_adaptive_reroute_current_edge_continuation_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success

    def test_run_adaptive_reroute_delayed_network_scenario(self) -> None:
        """Run delayed network scenario fixture."""
        scn = create_adaptive_reroute_delayed_network_scenario(max_ticks=10)
        res = run_scenario(scn)
        assert res.is_success
