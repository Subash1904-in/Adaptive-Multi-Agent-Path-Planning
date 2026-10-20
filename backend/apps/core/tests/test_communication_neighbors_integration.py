"""Integration tests for dynamic neighbor tables, heartbeats, loss detection, and rollback."""

import pytest

from apps.core.communication.models import CommunicationConfig, DeliveryPolicy, NeighborStatus
from apps.core.domain.enums import VehicleType
from apps.core.domain.models import SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.planner import RoutePlanner
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


class TestNeighborSubsystemIntegration:
    """Test suite verifying neighbor table tracking integrated with SimulationEngine."""

    @pytest.fixture
    def grid_and_planner(self):
        graph = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=100.0, speed_limit_mps=15.0)
        )
        planner = RoutePlanner(road_graph=graph)
        return graph, planner

    def _setup_engine(
        self,
        graph,
        planner,
        comm_range: float = 60.0,
        heartbeat_timeout_s: float = 0.3,
        stale_grace_period_s: float = 0.5,
        v2_initial_pos: Position2D = Position2D(x=30.0, y=0.0),
    ) -> SimulationEngine:
        comm_cfg = CommunicationConfig(
            enabled=True,
            range_m=comm_range,
            broadcast_interval_s=0.1,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
            neighbor_tracking_enabled=True,
            neighbor_update_interval_s=0.1,
            heartbeat_timeout_s=heartbeat_timeout_s,
            stale_grace_period_s=stale_grace_period_s,
        )
        sim_cfg = SimulationConfig(time_step_s=0.1)
        clock = SimulationClock(time_step_s=0.1)
        world = WorldState(
            road_graph=graph,
            config=sim_cfg,
            clock=clock,
            communication_config=comm_cfg,
        )

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

        r2 = planner.find_route("node_r0_c0", "node_r0_c2").route
        v2 = Vehicle(
            id="v2",
            vehicle_type=VehicleType.STANDARD,
            position=v2_initial_pos,
            speed_mps=10.0,
        )
        a2 = VehicleAgent(vehicle=v2, road_graph=graph, route=r2)
        a2.start()
        world.add_agent(a2)

        world.save_baseline()
        return SimulationEngine(world=world)

    def test_neighbor_discovery_and_refresh_via_engine(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner
        engine = self._setup_engine(graph, planner, comm_range=60.0)

        # Tick 1: Status broadcasts are queued in transit
        res1 = engine.step()
        assert res1.tick == 1
        # In NEXT_TICK delivery policy, transit messages haven't entered inbox yet on tick 1
        t1 = engine.get_neighbor_table("v1")
        assert t1 is not None

        # Tick 2: Transit messages moved to inbox -> neighbor tables updated
        res2 = engine.step()
        assert res2.tick == 2
        active_v1 = engine.get_active_neighbors("v1")
        assert len(active_v1) == 1
        rec = active_v1[0]
        assert rec.vehicle_id == "v2"
        assert rec.status == NeighborStatus.ACTIVE
        assert rec.last_sequence_number >= 0

        # Also v2 should have discovered v1
        active_v2 = engine.get_active_neighbors("v2")
        assert len(active_v2) == 1
        assert active_v2[0].vehicle_id == "v1"

        # Tick 3: Subsequent broadcast refreshes sequence and timestamps
        prev_hb_time = rec.last_heartbeat_timestamp_s
        engine.step()
        rec_after = engine.get_neighbor_table("v1").get_neighbor("v2")
        assert rec_after.last_heartbeat_timestamp_s > prev_hb_time

    def test_no_omniscient_leakage_without_communication(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner
        engine = self._setup_engine(graph, planner, comm_range=60.0)

        # Disable v2's transmitter
        engine.world.communication_network.set_participant_availability("v2", False)

        # Step multiple ticks
        for _ in range(5):
            engine.step()

        # Despite being within 30m physical range, v1 has NO neighbor record for v2
        t1 = engine.get_neighbor_table("v1")
        assert t1.has_neighbor("v2") is False
        assert len(engine.get_known_neighbors("v1")) == 0

    def test_peer_moves_out_of_range_becomes_stale_then_removed(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner
        # Timeout at 0.3s (3 ticks), grace period 0.3s (3 ticks) -> total 6 ticks after loss
        engine = self._setup_engine(
            graph,
            planner,
            comm_range=60.0,
            heartbeat_timeout_s=0.3,
            stale_grace_period_s=0.3,
            v2_initial_pos=Position2D(x=20.0, y=0.0),
        )

        # Step 2 ticks to establish v2 as active neighbor
        engine.step()
        engine.step()
        assert len(engine.get_active_neighbors("v1")) == 1

        # Now simulate v2 transceiver hardware failure or loss of connectivity
        engine.world.communication_network.set_participant_availability("v2", False)

        # Run 3 more ticks: 0.1s each -> 0.3s elapsed without heartbeat -> STALE
        for _ in range(3):
            engine.step()

        stale_v1 = engine.get_stale_neighbors("v1")
        assert len(stale_v1) == 1
        assert stale_v1[0].vehicle_id == "v2"
        assert stale_v1[0].status == NeighborStatus.STALE

        # Run 3 more ticks: another 0.3s elapsed -> grace period expired -> REMOVED
        for _ in range(3):
            engine.step()

        known = engine.get_known_neighbors("v1")
        assert len(known) == 0

    def test_atomic_rollback_restores_neighbor_subsystem_state(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner
        engine = self._setup_engine(graph, planner)

        # Run 3 valid ticks
        engine.run(3)
        t_before = engine.get_neighbor_table("v1").capture_state()
        metrics_before = engine.world.communication_network.neighbor_manager.metrics.clone()

        # Inject failure on tick 4 in agent step
        a1 = engine.world.get_agent("v1")

        def failing_step(dt, target_accel=None):
            raise RuntimeError("Injected step failure for atomic rollback verification")

        a1.step = failing_step

        with pytest.raises(TickExecutionError) as exc_info:
            engine.step()

        assert "Injected step failure" in str(exc_info.value)
        assert engine.status == EngineStatus.FAILED

        # Neighbor table state must have rolled back exactly
        t_after = engine.get_neighbor_table("v1").capture_state()
        assert t_after["neighbors"] == t_before["neighbors"]
        assert t_after["processed_message_ids"] == t_before["processed_message_ids"]

        # Metrics must not count the failed tick
        metrics_after = engine.world.communication_network.neighbor_manager.metrics
        assert metrics_after.to_dict() == metrics_before.to_dict()

    def test_world_reset_restores_baseline_neighbors(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner
        engine = self._setup_engine(graph, planner)

        engine.run(5)
        assert len(engine.get_active_neighbors("v1")) > 0

        engine.world.reset()
        assert engine.clock.tick_count == 0
        assert engine.clock.elapsed_time_s == 0.0
        assert engine.get_neighbor_table("v1").count == 0

    def test_deterministic_neighbor_replay(self, grid_and_planner) -> None:
        graph, planner = grid_and_planner

        def run_sim():
            eng = self._setup_engine(graph, planner)
            snaps = []
            for _ in range(8):
                res = eng.step()
                table_snap = eng.get_neighbor_table("v1").get_snapshot(res.elapsed_time_s)
                snaps.append(table_snap.to_dict())
            return snaps

        run1 = run_sim()
        run2 = run_sim()

        assert run1 == run2
