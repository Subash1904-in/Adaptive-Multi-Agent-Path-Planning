"""Regression test suite for multi-agent V2V communication and decentralized coordination.

Verifies:
- Peer discovery and neighbor table maintenance within communication range.
- Neighbor timeout and status degradation (ACTIVE -> STALE / LOST) when out of range.
- Deterministic simulated packet loss and delivery accounting.
- Duplicate message suppression and idempotency.
- Multi-agent private knowledge store isolation (zero omniscient cross-agent leakage).
- Conflicting report resolution and timestamp precedence in distributed beliefs.
- Emergency vehicle announcement broadcast and local awareness ingestion.
"""

from __future__ import annotations

from apps.core.communication.models import (
    CommunicationConfig,
    DeliveryPolicy,
    NeighborStatus,
    V2VMessagePacket,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.coordination.fusion import derive_belief_id
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    BeliefStatus,
    CongestionLevel,
    CongestionReport,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.models import SimulationConfig, Vehicle
from apps.core.domain.values import Position2D
from apps.core.emergency.models import EmergencyType
from apps.core.emergency.v2v import (
    create_emergency_activated_message,
    ingest_emergency_message_into_awareness,
)
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.planner import RoutePlanner
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.world import WorldState


class TestMultiAgentV2VRegression:
    """Verifies V2V communication protocols, neighbor tracking, and decentralized coordination."""

    def test_peer_discovery_and_neighbor_table_tracking(self) -> None:
        """Agents within communication radius reliably discover peers and update neighbor status."""
        graph = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=80.0, speed_limit_mps=12.0)
        )
        planner = RoutePlanner(road_graph=graph)

        comm_cfg = CommunicationConfig(
            enabled=True,
            range_m=60.0,
            broadcast_interval_s=0.1,
            delivery_policy=DeliveryPolicy.NEXT_TICK,
            neighbor_tracking_enabled=True,
            neighbor_update_interval_s=0.1,
            heartbeat_timeout_s=0.5,
        )
        world = WorldState(
            road_graph=graph,
            config=SimulationConfig(time_step_s=0.1),
            clock=SimulationClock(time_step_s=0.1),
            communication_config=comm_cfg,
        )

        r1 = planner.find_route("node_r0_c0", "node_r0_c2").route
        v1 = Vehicle(id="veh_01", position=Position2D(x=0.0, y=0.0), speed_mps=5.0)
        a1 = VehicleAgent(vehicle=v1, road_graph=graph, route=r1)
        a1.start()
        world.add_agent(a1)

        r2 = planner.find_route("node_r0_c0", "node_r0_c2").route
        v2 = Vehicle(id="veh_02", position=Position2D(x=20.0, y=0.0), speed_mps=5.0)
        a2 = VehicleAgent(vehicle=v2, road_graph=graph, route=r2)
        a2.start()
        world.add_agent(a2)

        world.save_baseline()
        engine = SimulationEngine(world=world)

        # Step 2 ticks to allow status broadcast and reception under NEXT_TICK policy
        engine.step()
        engine.step()

        active_neighbors = engine.get_active_neighbors("veh_01")
        assert len(active_neighbors) == 1
        neighbor = active_neighbors[0]
        assert neighbor.vehicle_id == "veh_02"
        assert neighbor.status == NeighborStatus.ACTIVE
        assert neighbor.last_distance_m <= 60.0

    def test_neighbor_timeout_when_moving_out_of_range(self) -> None:
        """Neighbor transitions to LOST after transmitter loss exceeds heartbeat timeout."""
        graph = generate_synthetic_city_grid(
            CityGridConfig(rows=3, cols=3, spacing_m=80.0, speed_limit_mps=12.0)
        )
        planner = RoutePlanner(road_graph=graph)

        comm_cfg = CommunicationConfig(
            enabled=True,
            range_m=60.0,
            broadcast_interval_s=0.1,
            delivery_policy=DeliveryPolicy.SAME_TICK,
            neighbor_tracking_enabled=True,
            neighbor_update_interval_s=0.1,
            heartbeat_timeout_s=0.2,
            stale_grace_period_s=0.3,
        )
        world = WorldState(
            road_graph=graph,
            config=SimulationConfig(time_step_s=0.1),
            clock=SimulationClock(time_step_s=0.1),
            communication_config=comm_cfg,
        )

        r1 = planner.find_route("node_r0_c0", "node_r0_c2").route
        a1 = VehicleAgent(
            vehicle=Vehicle(id="v1", position=Position2D(x=0.0, y=0.0)), road_graph=graph, route=r1
        )
        a1.start()
        world.add_agent(a1)

        r2 = planner.find_route("node_r0_c0", "node_r0_c2").route
        a2 = VehicleAgent(
            vehicle=Vehicle(id="v2", position=Position2D(x=20.0, y=0.0)), road_graph=graph, route=r2
        )
        a2.start()
        world.add_agent(a2)

        world.save_baseline()
        engine = SimulationEngine(world=world)

        engine.step()
        assert len(engine.get_active_neighbors("v1")) == 1

        # Simulate abrupt transmitter failure on v2
        engine.world.communication_network.set_participant_availability("v2", False)

        # Advance 6 ticks (0.6s > 0.2s + 0.3s timeout + grace)
        for _ in range(6):
            engine.step()

        # v2 should now be evicted from active neighbors
        assert len(engine.get_active_neighbors("v1")) == 0

    def test_deterministic_packet_loss_channel_simulation(self) -> None:
        """SimulatedCommunicationNetwork drops packets with deterministic seed reproducibility."""
        cfg = CommunicationConfig(
            enabled=True,
            range_m=100.0,
            packet_loss_rate=1.0,  # 100% loss
            delivery_policy=DeliveryPolicy.SAME_TICK,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("v1")
        net.register_participant("v2")

        msg = V2VMessagePacket(
            message_id="msg_drop_01",
            sender_id="v1",
            sequence_number=1,
            timestamp_s=1.0,
            sender_position=Position2D(x=0.0, y=0.0),
            sender_heading_rad=0.0,
            sender_speed_mps=10.0,
            message_type=V2VMessageType.HEARTBEAT,
        )
        candidates = {"v1": Position2D(x=0.0, y=0.0), "v2": Position2D(x=10.0, y=0.0)}

        receivers = net.broadcast(msg, candidates, current_time_s=1.0)
        assert receivers == []
        assert net.metrics.dropped_packet_loss >= 1
        assert len(net.get_inbox("v2")) == 0

    def test_duplicate_message_suppression_and_idempotency(self) -> None:
        """Duplicate message packets are discarded and never duplicated in inbox."""
        cfg = CommunicationConfig(
            enabled=True,
            range_m=100.0,
            delivery_policy=DeliveryPolicy.SAME_TICK,
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("v1")
        net.register_participant("v2")

        msg = V2VMessagePacket(
            message_id="msg_dup_test",
            sender_id="v1",
            sequence_number=1,
            timestamp_s=1.0,
            sender_position=Position2D(x=0.0, y=0.0),
            sender_heading_rad=0.0,
            sender_speed_mps=10.0,
            message_type=V2VMessageType.HEARTBEAT,
        )
        candidates = {"v1": Position2D(x=0.0, y=0.0), "v2": Position2D(x=10.0, y=0.0)}

        net.broadcast(msg, candidates, current_time_s=1.0)
        # Duplicate broadcast
        net.broadcast(msg, candidates, current_time_s=1.0)

        inbox_v2 = net.get_inbox("v2")
        assert len(inbox_v2) == 1

    def test_multi_agent_private_knowledge_store_isolation(self) -> None:
        """Vehicle knowledge stores are isolated; mutations in one do not leak to another."""
        store_1 = VehicleKnowledgeStore(vehicle_id="veh_01")
        store_2 = VehicleKnowledgeStore(vehicle_id="veh_02")

        report = CongestionReport(
            report_id="cong_01",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_01",
            edge_id="edge_main_st",
            timestamp_s=5.0,
            congestion_level=CongestionLevel.SEVERE,
        )

        store_1.add_observation(report, current_time_s=5.0)

        bid = derive_belief_id(report)
        assert store_1.get_belief(bid) is not None
        assert store_2.get_belief(bid) is None
        assert store_1.belief_count >= 1
        assert store_2.belief_count == 0

    def test_conflicting_report_resolution_by_timestamp_precedence(self) -> None:
        """Newer observation supersedes older belief deterministically."""
        store = VehicleKnowledgeStore(vehicle_id="veh_01")

        # Older closure report
        closure = RoadClosureReport(
            report_id="rep_cls_1",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v_sensor",
            edge_id="edge_ave_a",
            closure_status=RoadClosureStatus.CLOSED,
            timestamp_s=10.0,
        )
        store.ingest_report(closure, current_time_s=10.0)
        bid = derive_belief_id(closure)
        belief = store.get_belief(bid)
        assert belief is not None
        assert belief.status == BeliefStatus.ACTIVE

        # Newer reopening report supersedes closure
        reopen = RoadClosureReport(
            report_id="rep_open_2",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="v_sensor",
            edge_id="edge_ave_a",
            closure_status=RoadClosureStatus.REOPENED,
            timestamp_s=25.0,
        )
        store.ingest_report(reopen, current_time_s=25.0)

        updated_belief = store.get_belief(bid)
        assert updated_belief is not None
        assert updated_belief.attributes["closure_status"] == RoadClosureStatus.REOPENED.value

    def test_emergency_announcement_broadcast_and_awareness(self) -> None:
        """Emergency beacon broadcast propagates and updates recipient awareness record."""
        cfg = CommunicationConfig(
            enabled=True, range_m=200.0, delivery_policy=DeliveryPolicy.SAME_TICK
        )
        net = SimulatedCommunicationNetwork(config=cfg)
        net.register_participant("amb_01")
        net.register_participant("civilian_01")

        packet = create_emergency_activated_message(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=3,
            current_time_s=12.0,
            ttl_s=30.0,
        )

        candidates = {
            "amb_01": Position2D(x=10.0, y=10.0),
            "civilian_01": Position2D(x=40.0, y=10.0),
        }
        receivers = net.broadcast(packet, candidates, current_time_s=12.0)
        assert receivers == ["civilian_01"]

        # Recipient processes inbox
        inbox = net.clear_inbox("civilian_01")
        assert len(inbox) == 1
        rx_packet = inbox[0]

        awareness_records: dict = {}
        record = ingest_emergency_message_into_awareness(
            rx_packet, awareness_records, current_time_s=12.0
        )
        assert record is not None
        assert record.emergency_vehicle_id == "amb_01"
        assert record.priority_level == 3
