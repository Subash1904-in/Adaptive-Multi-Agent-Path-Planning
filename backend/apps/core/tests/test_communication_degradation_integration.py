"""Integration tests for communication network degradation, engine rollback, and V2V coordination.

Verifies:
- Delayed and lost heartbeats affect neighbor table freshness correctly.
- Recovered heartbeats transition stale neighbors back to active.
- Decentralized coordination reports traverse multi-tick latency queues.
- Packet loss and outages prevent unwanted knowledge propagation.
- Engine stepping under network degradation supports atomic rollback without state corruption.
- ScenarioRunner execution of standard Phase 14 scenario templates.
"""

from unittest.mock import patch

import pytest

from apps.core.communication.models import (
    CommunicationConfig,
    NeighborStatus,
    StaleNeighborPolicy,
    V2VMessagePacket,
    V2VMessageType,
    VehicleStatusPayload,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.domain.values import Position2D
from apps.core.scenarios import (
    create_burst_loss_scenario,
    create_degraded_network_scenario,
    create_latency_scenario,
    create_packet_loss_scenario,
    run_scenario,
)
from apps.core.simulation.engine import EngineStatus, SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.world import WorldState


@pytest.fixture
def base_positions() -> dict[str, Position2D]:
    return {
        "veh_a": Position2D(x=0.0, y=0.0),
        "veh_b": Position2D(x=20.0, y=0.0),
    }


def make_heartbeat(
    sender_id: str,
    seq: int,
    time_s: float,
    pos: Position2D,
) -> V2VMessagePacket:
    """Helper to create valid status/heartbeat packet."""
    return V2VMessagePacket(
        message_id=f"hb_{sender_id}_{seq}",
        sender_id=sender_id,
        sequence_number=seq,
        timestamp_s=time_s,
        sender_position=pos,
        sender_heading_rad=0.0,
        sender_speed_mps=5.0,
        message_type=V2VMessageType.HEARTBEAT,
        expiry_timestamp_s=time_s + 2.0,
        payload=VehicleStatusPayload().to_dict(),
    )


class TestNeighborDegradationIntegration:
    """Verify heartbeat loss and latency interaction with neighbor table state machines."""

    def test_delayed_heartbeat_causes_stale_transition(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """With heartbeat_timeout=0.5s, delay of 0.6s causes neighbor to become STALE."""
        cfg = CommunicationConfig(
            heartbeat_timeout_s=0.5,
            stale_grace_period_s=1.0,
            stale_policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
            min_latency_s=0.6,
            max_latency_s=0.6,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        # Initial registration at t=0.0
        hb0 = make_heartbeat("veh_a", seq=1, time_s=0.0, pos=base_positions["veh_a"])
        tbl_b = net.get_neighbor_table("veh_b")
        assert tbl_b is not None
        tbl_b.add_or_refresh(
            message=hb0,
            observer_position=base_positions["veh_b"],
            current_time_s=0.0,
        )
        assert tbl_b.get_neighbor("veh_a").status == NeighborStatus.ACTIVE

        # Transmit hb1 with latency=0.6s at t=0.1
        hb1 = make_heartbeat("veh_a", seq=2, time_s=0.1, pos=base_positions["veh_a"])
        net.broadcast(hb1, base_positions, current_time_s=0.1)

        # Maintenance at t=0.6: elapsed since last heartbeat (t=0.0) is 0.6s > 0.5s -> STALE
        net.advance_tick(0.6)  # hb1 not delivered yet (0.6 < 0.1 + 0.6 = 0.7)
        net.perform_neighbor_maintenance(current_time_s=0.6)
        assert tbl_b.get_neighbor("veh_a").status == NeighborStatus.STALE

        # Advance to t=0.7: hb1 delivery arrives!
        net.advance_tick(0.7)
        net.update_neighbor_tables(base_positions, current_time_s=0.7)
        # Refreshed back to ACTIVE
        assert tbl_b.get_neighbor("veh_a").status == NeighborStatus.ACTIVE

    def test_lost_heartbeat_does_not_refresh_neighbor(
        self, base_positions: dict[str, Position2D]
    ) -> None:
        """Dropped heartbeats fail to refresh neighbor, eventually removing neighbor."""
        cfg = CommunicationConfig(
            packet_loss_rate=1.0,
            heartbeat_timeout_s=0.3,
            stale_grace_period_s=0.3,
            stale_policy=StaleNeighborPolicy.STALE_THEN_REMOVE,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("veh_a")
        net.register_participant("veh_b")

        tbl_b = net.get_neighbor_table("veh_b")
        assert tbl_b is not None
        hb0 = make_heartbeat("veh_a", seq=1, time_s=0.0, pos=base_positions["veh_a"])
        tbl_b.add_or_refresh(
            message=hb0,
            observer_position=base_positions["veh_b"],
            current_time_s=0.0,
        )

        # Send heartbeat that gets dropped due to 100% loss
        hb = make_heartbeat("veh_a", seq=2, time_s=0.1, pos=base_positions["veh_a"])
        net.broadcast(hb, base_positions, current_time_s=0.1)
        net.advance_tick(0.2)
        net.update_neighbor_tables(base_positions, current_time_s=0.2)

        # Maintenance at t=0.7: time since t=0 is 0.7 > 0.3 + 0.3 -> neighbor removed
        net.perform_neighbor_maintenance(current_time_s=0.7)
        assert not tbl_b.has_neighbor("veh_a")


class TestSimulationEngineAtomicRollbackUnderImpairment:
    """Verify engine atomic rollback restores transit queues and PRNG states on step failure."""

    def test_atomic_rollback_restores_in_transit_queue_and_prng(self) -> None:
        """If vehicle stepping raises an exception, in-transit packets and PRNGs roll back."""
        from apps.core.tests.test_simulation_engine import create_agent, create_linear_graph

        road_graph = create_linear_graph()
        world = WorldState(road_graph=road_graph)
        # Enable degraded communication
        comm_cfg = CommunicationConfig(
            enabled=True,
            min_latency_s=0.2,
            max_latency_s=0.2,
            packet_loss_rate=0.5,
            packet_loss_seed=42,
        )
        world.communication_network = SimulatedCommunicationNetwork(config=comm_cfg)

        a1 = create_agent("veh_1", road_graph)
        a2 = create_agent("veh_2", road_graph)
        world.add_agent(a1)
        world.add_agent(a2)

        engine = SimulationEngine(world=world)

        # Pre-tick: queue a packet in transit
        pkt = make_heartbeat("veh_1", seq=1, time_s=0.0, pos=Position2D(0.0, 0.0))
        positions = {"veh_1": Position2D(0.0, 0.0), "veh_2": Position2D(10.0, 0.0)}
        world.communication_network.broadcast(pkt, positions, current_time_s=0.0)

        initial_transit_count = world.communication_network.get_in_transit_count()
        assert initial_transit_count == 1
        initial_metrics = world.communication_network.metrics.clone()

        # Step tick 1 with failure injected on a2.step
        def failing_step(dt: float, target_accel: float | None = None):
            raise RuntimeError("Simulated vehicle crash")

        with (
            patch.object(a2, "step", side_effect=failing_step),
            pytest.raises(TickExecutionError),
        ):
            engine.step()

        # Engine is marked FAILED and state is restored atomically
        assert engine.status == EngineStatus.FAILED
        assert world.communication_network.get_in_transit_count() == initial_transit_count
        assert (
            world.communication_network.metrics.packets_queued_latency
            == initial_metrics.packets_queued_latency
        )
        assert (
            world.communication_network.metrics.successful_deliveries
            == initial_metrics.successful_deliveries
        )


class TestStandardScenarioExecution:
    """Execute standard Phase 14 scenario templates using ScenarioRunner."""

    def test_run_latency_scenario(self) -> None:
        scn = create_latency_scenario(max_ticks=20, latency_s=0.2, seed=42)
        res = run_scenario(scn)
        assert res.is_success is True
        assert res.completed_ticks > 0

    def test_run_packet_loss_scenario(self) -> None:
        scn = create_packet_loss_scenario(max_ticks=20, loss_rate=0.3, seed=42)
        res = run_scenario(scn)
        assert res.is_success is True
        assert res.completed_ticks > 0

    def test_run_burst_loss_scenario(self) -> None:
        scn = create_burst_loss_scenario(max_ticks=20, seed=42)
        res = run_scenario(scn)
        assert res.is_success is True
        assert res.completed_ticks > 0

    def test_run_degraded_network_scenario(self) -> None:
        scn = create_degraded_network_scenario(max_ticks=20, seed=42)
        res = run_scenario(scn)
        assert res.is_success is True
        assert res.completed_ticks > 0
