"""Integration tests for Phase 13 coordination with SimulationEngine and WorldState."""

from unittest.mock import patch

import pytest

from apps.core.communication.models import CommunicationConfig, DeliveryPolicy
from apps.core.coordination.dissemination import DisseminationManager
from apps.core.coordination.models import (
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    HazardReport,
    HazardType,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.enums import VehicleState, VehicleType
from apps.core.domain.models import Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadEdge, RoadGraph, RoadNode
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.models import (
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    VehicleScenarioDefinition,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.world import WorldState


@pytest.fixture
def linear_two_vehicle_world() -> tuple[WorldState, SimulationEngine, VehicleAgent, VehicleAgent]:
    """Fixture with two vehicles on a linear graph with V2V and coordination enabled."""
    g = RoadGraph(name="test_linear")
    g.add_node(RoadNode(id="n0", position=Position2D(x=0.0, y=0.0)))
    g.add_node(RoadNode(id="n1", position=Position2D(x=100.0, y=0.0)))
    g.add_node(RoadNode(id="n2", position=Position2D(x=200.0, y=0.0)))

    e0 = RoadEdge(
        id="e0", start_node_id="n0", end_node_id="n1", length_m=100.0, speed_limit_mps=15.0
    )
    e1 = RoadEdge(
        id="e1", start_node_id="n1", end_node_id="n2", length_m=100.0, speed_limit_mps=15.0
    )
    g.add_edge(e0)
    g.add_edge(e1)

    comm_cfg = CommunicationConfig(
        enabled=True,
        range_m=150.0,
        delivery_policy=DeliveryPolicy.SAME_TICK,
    )
    coord_cfg = CoordinationConfig(enabled=True, max_forwarding_hops=3)

    world = WorldState(
        road_graph=g,
        clock=SimulationClock(time_step_s=0.1),
        communication_config=comm_cfg,
        coordination_config=coord_cfg,
    )

    route_v1 = Route(
        id="r_v1",
        node_ids=["n0", "n1", "n2"],
        edge_ids=["e0", "e1"],
    )
    route_v2 = Route(
        id="r_v2",
        node_ids=["n0", "n1", "n2"],
        edge_ids=["e0", "e1"],
    )

    veh1 = Vehicle(
        id="veh_1",
        vehicle_type=VehicleType.STANDARD,
        state=VehicleState.IDLE,
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=5.0,
    )
    veh2 = Vehicle(
        id="veh_2",
        vehicle_type=VehicleType.STANDARD,
        state=VehicleState.IDLE,
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=5.0,
    )

    v1 = VehicleAgent(vehicle=veh1, road_graph=g, route=route_v1)
    v1.start()
    v2 = VehicleAgent(vehicle=veh2, road_graph=g, route=route_v2)
    v2.start()

    world.add_agent(v1)
    world.add_agent(v2)

    engine = SimulationEngine(world=world)
    return world, engine, v1, v2


class TestCoordinationEngineIntegration:
    """Integration test suite for engine tick progression, knowledge sharing, and rollback."""

    def test_coordination_advances_through_engine_ticks(
        self,
        linear_two_vehicle_world: tuple[WorldState, SimulationEngine, VehicleAgent, VehicleAgent],
    ) -> None:
        world, engine, v1, v2 = linear_two_vehicle_world

        # Initial step
        res1 = engine.step()
        assert res1.coordination_metrics is not None
        assert res1.coordination_metrics["reports_created"] == 0

        # veh_1 observes congestion on e1 and publishes it
        report = CongestionReport(
            report_id="cong_obs_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="e1",
            timestamp_s=world.clock.elapsed_time_s,
            congestion_level=CongestionLevel.HIGH,
        )
        assert engine.publish_traffic_observation("veh_1", report) is True

        # veh_1 now has report and belief
        store_v1 = engine.get_knowledge_store("veh_1")
        assert store_v1.report_count == 1
        assert store_v1.get_belief("congestion:e1") is not None

        # veh_2 does NOT yet have the report (until transmitted over V2V network)
        store_v2 = engine.get_knowledge_store("veh_2")
        assert store_v2.report_count == 0

        # Broadcast report over network
        pkt = DisseminationManager.create_report_packet(
            sender_id="veh_1",
            sender_position=v1.vehicle.position,
            sender_heading_rad=v1.vehicle.heading_rad,
            sender_speed_mps=v1.vehicle.speed_mps,
            sequence_number=1,
            report=report,
            current_time_s=world.clock.elapsed_time_s,
        )
        candidates = {
            "veh_1": v1.vehicle.position,
            "veh_2": v2.vehicle.position,
        }
        world.communication_network.broadcast(
            pkt, candidate_positions=candidates, current_time_s=world.clock.elapsed_time_s
        )

        # Advance engine tick: processes inbox and updates veh_2's knowledge store!
        res2 = engine.step()
        assert res2.coordination_metrics["reports_received"] >= 1
        assert res2.coordination_metrics["reports_accepted"] >= 2  # 1 created + 1 ingested

        # veh_2 has now acquired the knowledge and belief via V2V!
        assert store_v2.report_count == 1
        belief_v2 = store_v2.get_belief("congestion:e1")
        assert belief_v2 is not None
        assert belief_v2.attributes["congestion_level"] == CongestionLevel.HIGH.value
        assert belief_v2.evidence_sources == ("veh_1",)

    def test_received_reports_do_not_automatically_alter_routes(
        self,
        linear_two_vehicle_world: tuple[WorldState, SimulationEngine, VehicleAgent, VehicleAgent],
    ) -> None:
        """Phase 13 boundary test: receiving a road closure report must NOT change vehicle route."""
        world, engine, v1, v2 = linear_two_vehicle_world

        initial_edge_ids = list(v2.route.edge_ids) if v2.route else []
        assert len(initial_edge_ids) == 2

        # veh_2 receives a report that e1 is closed
        closure = RoadClosureReport(
            report_id="closure_alert_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_1",
            edge_id="e1",
            timestamp_s=world.clock.elapsed_time_s,
            closure_status=RoadClosureStatus.CLOSED,
        )

        store_v2 = engine.get_knowledge_store("veh_2")
        store_v2.ingest_report(closure, current_time_s=world.clock.elapsed_time_s)

        # Belief is updated to CLOSED
        belief = store_v2.get_belief("closure:e1")
        assert belief is not None
        assert belief.attributes["closure_status"] == RoadClosureStatus.CLOSED.value

        # Step engine
        engine.step()

        # Strict architectural guarantee: Route is NOT altered in Phase 13!
        assert v2.route is not None
        assert list(v2.route.edge_ids) == initial_edge_ids

    def test_atomic_rollback_on_engine_step_failure(
        self,
        linear_two_vehicle_world: tuple[WorldState, SimulationEngine, VehicleAgent, VehicleAgent],
    ) -> None:
        """Verify that an agent stepping failure rolls back coordination state completely."""
        world, engine, v1, v2 = linear_two_vehicle_world

        # Complete 2 successful ticks
        engine.step()
        engine.step()
        t2_snap = world.coordination_manager.get_snapshot(world.clock.elapsed_time_s)
        assert t2_snap.total_reports == 0

        # Stage a report publication right before the failing tick
        report = CongestionReport(
            report_id="cong_fail_test",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_1",
            edge_id="e1",
            timestamp_s=world.clock.elapsed_time_s,
        )
        engine.publish_traffic_observation("veh_1", report)
        assert world.coordination_manager.metrics.reports_created == 1

        # Mock v2.step to fail midway through agent stepping
        with patch.object(v2, "step", side_effect=RuntimeError("Hardware failure")):
            with pytest.raises(TickExecutionError):
                engine.step()

        # Atomic rollback must have restored coordination state to pre-tick snapshot!
        store_v1 = engine.get_knowledge_store("veh_1")
        assert store_v1.get_report("cong_fail_test") is not None
        # Pre-tick snapshot for that step was captured right at the start of step()
        # where reports_created was 1. When step failed, rollback restored that state.
        assert world.coordination_manager.metrics.reports_received == 0
        assert world.coordination_manager.metrics.reports_forwarded == 0

    def test_simulation_reset_restores_coordination_baseline(
        self,
        linear_two_vehicle_world: tuple[WorldState, SimulationEngine, VehicleAgent, VehicleAgent],
    ) -> None:
        world, engine, v1, v2 = linear_two_vehicle_world

        report = HazardReport(
            report_id="h_reset",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_1",
            edge_id="e0",
            timestamp_s=0.0,
            hazard_type=HazardType.ROADWORK,
        )
        engine.publish_traffic_observation("veh_1", report)
        assert engine.get_knowledge_store("veh_1").report_count == 1

        # Advance a few ticks
        for _ in range(5):
            engine.step()

        # Reset world
        world.reset()
        assert world.clock.tick_count == 0
        assert world.clock.elapsed_time_s == 0.0

        # Knowledge store is fresh and clean
        assert world.coordination_manager.metrics.reports_created == 0
        assert world.coordination_manager.get_store("veh_1").report_count == 0
        assert world.coordination_manager.get_store("veh_2").report_count == 0

    def test_scenario_builder_and_runner_with_coordination(self) -> None:
        """Verify complete scenario execution with coordination configuration enabled."""
        meta = ScenarioMetadata(id="scen_coord_1", name="Coordination Scenario")
        g = RoadGraph(name="grid_coord")
        g.add_node(RoadNode(id="A", position=Position2D(x=0.0, y=0.0)))
        g.add_node(RoadNode(id="B", position=Position2D(x=100.0, y=0.0)))
        g.add_edge(
            RoadEdge(
                id="e_AB", start_node_id="A", end_node_id="B", length_m=100.0, speed_limit_mps=10.0
            )
        )

        net = RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SUPPLIED_GRAPH, supplied_graph=g
        )
        vdef1 = VehicleScenarioDefinition(
            vehicle_id="veh_1", start_node_id="A", destination_node_id="B"
        )
        vdef2 = VehicleScenarioDefinition(
            vehicle_id="veh_2", start_node_id="A", destination_node_id="B"
        )

        comm_cfg = CommunicationConfig(enabled=True, range_m=200.0)
        coord_cfg = CoordinationConfig(enabled=True, max_forwarding_hops=2)

        scenario = ScenarioDefinition(
            metadata=meta,
            road_network=net,
            vehicles=(vdef1, vdef2),
            time_step_s=0.1,
            max_ticks=10,
            v2v_config=comm_cfg,
            coordination_config=coord_cfg,
        )

        builder = ScenarioBuilder(scenario=scenario)
        built = builder.build()
        assert built.world.coordination_manager.config.enabled is True
        assert built.world.coordination_manager.has_vehicle("veh_1") is True
        assert built.world.coordination_manager.has_vehicle("veh_2") is True

        runner = ScenarioRunner(context=built)
        result = runner.run(ticks=10)
        assert result.is_success is True
        assert result.completed_ticks == 10
        assert result.final_world_snapshot.coordination is not None
        assert result.final_world_snapshot.coordination["enabled"] is True

    def test_standard_coordination_scenario_fixtures(self) -> None:
        from apps.core.scenarios import (
            create_congestion_sharing_scenario,
            create_hazard_dissemination_scenario,
            create_road_closure_sharing_scenario,
            run_scenario,
        )

        scen_cong = create_congestion_sharing_scenario(max_ticks=5)
        res_cong = run_scenario(scen_cong)
        assert res_cong.is_success is True
        assert res_cong.completed_ticks == 5
        assert res_cong.final_world_snapshot.coordination is not None

        scen_close = create_road_closure_sharing_scenario(max_ticks=5)
        res_close = run_scenario(scen_close)
        assert res_close.is_success is True
        assert res_close.completed_ticks == 5

        scen_haz = create_hazard_dissemination_scenario(max_ticks=5)
        res_haz = run_scenario(scen_haz)
        assert res_haz.is_success is True
        assert res_haz.completed_ticks == 5

    def test_deterministic_replay_produces_identical_beliefs(self) -> None:
        """Verify identical runs produce identical belief states and coordination snapshots."""
        from apps.core.scenarios import create_congestion_sharing_scenario, run_scenario

        scen1 = create_congestion_sharing_scenario(max_ticks=10, seed=123)
        scen2 = create_congestion_sharing_scenario(max_ticks=10, seed=123)

        res1 = run_scenario(scen1)
        res2 = run_scenario(scen2)

        snap1 = res1.final_world_snapshot.coordination
        snap2 = res2.final_world_snapshot.coordination
        assert snap1 == snap2
