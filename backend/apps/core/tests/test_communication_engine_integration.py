"""Integration tests for V2V communication with WorldState, SimulationEngine, and Scenarios."""

import pytest

from apps.core.communication.models import CommunicationConfig, DeliveryPolicy
from apps.core.domain.enums import VehicleType
from apps.core.domain.models import SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.models import CostMode, RoutingAlgorithm
from apps.core.routing.planner import RoutePlanner
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
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


class TestSimulationEngineCommunicationIntegration:
    """Test suite verifying communication integration into SimulationEngine stepping."""

    @pytest.fixture
    def grid_and_planner(self):
        graph = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=100.0, speed_limit_mps=15.0)
        )
        planner = RoutePlanner(road_graph=graph)
        return graph, planner

    def _setup_engine(self, graph, planner, v2v_enabled=True, comm_range=150.0):
        comm_cfg = CommunicationConfig(
            enabled=v2v_enabled,
            range_m=comm_range,
            broadcast_interval_s=0.1,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
        )
        sim_cfg = SimulationConfig(time_step_s=0.1)
        clock = SimulationClock(time_step_s=0.1)
        world = WorldState(
            road_graph=graph,
            config=sim_cfg,
            clock=clock,
            communication_config=comm_cfg,
        )

        # Vehicle 1: starts at node_r0_c0, goes to node_r0_c2
        r1 = planner.find_route("node_r0_c0", "node_r0_c2").route
        v1 = Vehicle(
            id="v1",
            vehicle_type=VehicleType.STANDARD,
            position=Position2D(x=0.0, y=0.0),
            speed_mps=10.0,
        )
        a1 = VehicleAgent(vehicle=v1, road_graph=graph, route=r1)
        a1.start()
        world.add_agent(a1)

        # Vehicle 2: starts at node_r0_c1 (100m away from node_r0_c0), goes to node_r0_c2
        r2 = planner.find_route("node_r0_c1", "node_r0_c2").route
        v2 = Vehicle(
            id="v2",
            vehicle_type=VehicleType.STANDARD,
            position=Position2D(x=100.0, y=0.0),
            speed_mps=10.0,
        )
        a2 = VehicleAgent(vehicle=v2, road_graph=graph, route=r2)
        a2.start()
        world.add_agent(a2)

        engine = SimulationEngine(world=world)
        return world, engine, a1, a2

    def test_communication_auto_registered_with_world_agents(self, grid_and_planner):
        graph, planner = grid_and_planner
        world, engine, a1, a2 = self._setup_engine(graph, planner, v2v_enabled=True)

        # Both agents must be registered in the communication network
        assert world.communication_network.is_participant_registered("v1") is True
        assert world.communication_network.is_participant_registered("v2") is True
        assert world.communication_network.config.enabled is True

    def test_scheduled_broadcast_on_engine_step(self, grid_and_planner):
        """Engine step triggers periodic broadcasts and NEXT_TICK delivery."""
        graph, planner = grid_and_planner
        # Distance between (0, 0) and (100, 0) is 100m <= 150m range
        world, engine, a1, a2 = self._setup_engine(
            graph, planner, v2v_enabled=True, comm_range=150.0
        )

        # Tick 1: t advances from 0.0 to 0.1
        # Broadcast scheduled at t=0.0 before agent motion
        # Messages placed in transit queue for NEXT_TICK delivery
        res1 = engine.step()
        assert res1.tick == 1
        assert res1.communication_metrics is not None
        assert res1.communication_metrics["broadcasts_attempted"] == 2
        assert res1.communication_metrics["successful_deliveries"] == 2

        # In Tick 1, delivery policy is NEXT_TICK, so inboxes in step 1 had transit messages
        # After Tick 1 completes, the transit queue has messages for delivery on Tick 2
        # Advance to Tick 2: advance_tick flushes transit messages to inboxes
        res2 = engine.step()
        assert res2.tick == 2

        # Both v1 and v2 now have deliverable messages from the previous tick!
        inbox_v1 = engine.get_vehicle_inbox("v1")
        inbox_v2 = engine.get_vehicle_inbox("v2")
        assert len(inbox_v1) >= 1
        assert len(inbox_v2) >= 1
        assert inbox_v1[0].sender_id == "v2"
        assert inbox_v2[0].sender_id == "v1"

    def test_communication_does_not_mutate_kinematics(self, grid_and_planner):
        """V2V communication must NOT alter vehicle movement or position by itself in Phase 11."""
        graph, planner = grid_and_planner
        # Run with V2V enabled
        world_on, engine_on, a1_on, _ = self._setup_engine(graph, planner, v2v_enabled=True)
        engine_on.step()

        # Run with V2V disabled
        world_off, engine_off, a1_off, _ = self._setup_engine(graph, planner, v2v_enabled=False)
        engine_off.step()

        # Motion and position must be exactly identical
        assert a1_on.vehicle.position == a1_off.vehicle.position
        assert a1_on.vehicle.speed_mps == a1_off.vehicle.speed_mps
        assert a1_on.vehicle.heading_rad == a1_off.vehicle.heading_rad

    def test_atomic_rollback_restores_communication_state(self, grid_and_planner):
        """If an agent throws an exception during step(), comm state must be rolled back."""
        graph, planner = grid_and_planner
        world, engine, a1, a2 = self._setup_engine(graph, planner, v2v_enabled=True)

        # Baseline metrics
        assert world.communication_network.metrics.broadcasts_attempted == 0

        # Inject an error into a2.step to trigger engine rollback
        def failing_step(*args, **kwargs):
            raise RuntimeError("Injected stepping failure for rollback test")

        a2.step = failing_step  # type: ignore[method-assign]

        with pytest.raises(TickExecutionError):
            engine.step()

        assert engine.status == EngineStatus.FAILED

        # Communication state must be rolled back to pre-tick baseline!
        assert world.communication_network.metrics.broadcasts_attempted == 0
        assert world.communication_network.metrics.successful_deliveries == 0
        assert world.communication_network._transit_queue["v1"] == []
        assert world.communication_network._transit_queue["v2"] == []

    def test_engine_reset_restores_communication(self, grid_and_planner):
        graph, planner = grid_and_planner
        world, engine, a1, a2 = self._setup_engine(graph, planner, v2v_enabled=True)

        engine.step()
        engine.step()
        assert world.communication_network.metrics.broadcasts_attempted > 0

        # Reset engine
        engine.reset()
        assert engine.current_tick == 0
        assert world.communication_network.metrics.broadcasts_attempted == 0
        assert engine.get_vehicle_inbox("v1") == []
        assert engine.get_vehicle_inbox("v2") == []

    def test_scenario_runner_with_v2v_config(self, grid_and_planner):
        """A full scenario with explicit V2V configuration executes and captures metrics."""
        grid_cfg = CityGridConfig(rows=2, cols=2, spacing_m=50.0, speed_limit_mps=15.0)
        v2v_cfg = CommunicationConfig(
            enabled=True,
            range_m=60.0,
            broadcast_interval_s=0.1,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
        )
        scenario = ScenarioDefinition(
            metadata=ScenarioMetadata(id="sc_v2v", name="V2V Scenario"),
            road_network=RoadNetworkDefinition(
                source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
                grid_config=grid_cfg,
            ),
            vehicles=(
                VehicleScenarioDefinition(
                    vehicle_id="veh_1",
                    start_node_id="node_r0_c0",
                    destination_node_id="node_r0_c1",
                    algorithm=RoutingAlgorithm.DIJKSTRA,
                    cost_mode=CostMode.DISTANCE,
                ),
                VehicleScenarioDefinition(
                    vehicle_id="veh_2",
                    start_node_id="node_r0_c1",
                    destination_node_id="node_r0_c0",
                    algorithm=RoutingAlgorithm.DIJKSTRA,
                    cost_mode=CostMode.DISTANCE,
                ),
            ),
            time_step_s=0.1,
            max_ticks=5,
            v2v_config=v2v_cfg,
        )

        builder = ScenarioBuilder(scenario=scenario)
        context = builder.build()
        runner = ScenarioRunner(context=context)

        result = runner.run(ticks=3)
        assert result.completed_ticks == 3

        # Final snapshot must contain communication details
        snap = result.final_world_snapshot.to_dict()
        assert snap["communication"] is not None
        assert snap["communication"]["enabled"] is True
        assert snap["communication"]["range_m"] == 60.0
        assert snap["communication"]["total_broadcasts"] > 0

    def test_convenience_methods_on_simulation_engine(self, grid_and_planner):
        graph, planner = grid_and_planner
        world, engine, a1, a2 = self._setup_engine(
            graph, planner, v2v_enabled=True, comm_range=150.0
        )

        # discover_peers
        peers = engine.discover_peers("v1")
        assert peers == ["v2"]

        # get_vehicle_inbox and clear_vehicle_inbox
        assert engine.get_vehicle_inbox("v1") == []
        drained = engine.clear_vehicle_inbox("v1")
        assert drained == []
