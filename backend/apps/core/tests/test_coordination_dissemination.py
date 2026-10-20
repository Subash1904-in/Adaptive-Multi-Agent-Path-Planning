"""Unit and integration tests for Phase 13 V2V report dissemination and multi-hop forwarding."""

from apps.core.communication.models import CommunicationConfig, DeliveryPolicy
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.coordination.dissemination import DisseminationManager
from apps.core.coordination.manager import CoordinationManager
from apps.core.coordination.models import (
    CongestionLevel,
    CongestionReport,
    CoordinationConfig,
    HazardReport,
    HazardType,
    ReportType,
    RoadClosureReport,
)
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D


class TestDisseminationPackaging:
    """Tests for packet envelope serialization, extraction, and mapping."""

    def test_create_and_extract_congestion_packet(self) -> None:
        report = CongestionReport(
            report_id="c_pkt_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_A",
            edge_id="edge_1",
            timestamp_s=10.0,
            congestion_level=CongestionLevel.HIGH,
        )

        packet = DisseminationManager.create_report_packet(
            sender_id="veh_A",
            sender_position=Position2D(x=10.0, y=20.0),
            sender_heading_rad=0.0,
            sender_speed_mps=12.0,
            sequence_number=1,
            report=report,
            current_time_s=10.0,
            max_hops=3,
        )

        assert packet.sender_id == "veh_A"
        assert packet.message_type == V2VMessageType.CONGESTION_ALERT
        assert packet.payload["is_coordination_report"] is True
        assert packet.payload["origin_vehicle_id"] == "veh_A"
        assert packet.payload["hop_count"] == 0
        assert packet.payload["relay_path"] == ["veh_A"]

        # Extraction round trip
        extracted = DisseminationManager.extract_report(packet)
        assert extracted is not None
        ext_report, hop_count, max_hops, relay_path = extracted
        assert isinstance(ext_report, CongestionReport)
        assert ext_report.report_id == "c_pkt_1"
        assert hop_count == 0
        assert max_hops == 3
        assert relay_path == ["veh_A"]

    def test_create_and_extract_hazard_and_closure_packets(self) -> None:
        haz = HazardReport(
            report_id="h_pkt",
            report_type=ReportType.HAZARD,
            reporting_vehicle_id="veh_A",
            edge_id="edge_2",
            timestamp_s=5.0,
            hazard_type=HazardType.ACCIDENT,
        )
        haz_pkt = DisseminationManager.create_report_packet(
            sender_id="veh_A",
            sender_position=Position2D(x=0.0, y=0.0),
            sender_heading_rad=0.0,
            sender_speed_mps=0.0,
            sequence_number=1,
            report=haz,
            current_time_s=5.0,
        )
        assert haz_pkt.message_type == V2VMessageType.HAZARD_WARNING

        closure = RoadClosureReport(
            report_id="close_pkt",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_A",
            edge_id="edge_3",
            timestamp_s=5.0,
        )
        close_pkt = DisseminationManager.create_report_packet(
            sender_id="veh_A",
            sender_position=Position2D(x=0.0, y=0.0),
            sender_heading_rad=0.0,
            sender_speed_mps=0.0,
            sequence_number=2,
            report=closure,
            current_time_s=5.0,
        )
        assert close_pkt.message_type == V2VMessageType.ROUTE_ADVISORY


class TestMultiHopDissemination:
    """Tests for multi-hop propagation, loop prevention, and forwarding hop limits."""

    def test_multi_hop_propagation_reaches_indirect_peer(self) -> None:
        """Topology: veh_A (x=0) <--- 80m ---> veh_B (x=80) <--- 80m ---> veh_C (x=160).

        Radio range = 100m.
        veh_A and veh_C cannot communicate directly (distance = 160m > 100m).
        Report from veh_A must propagate to veh_C through veh_B.
        """
        comm_cfg = CommunicationConfig(
            enabled=True, range_m=100.0, delivery_policy=DeliveryPolicy.SAME_TICK
        )
        coord_cfg = CoordinationConfig(enabled=True, max_forwarding_hops=3)

        network = SimulatedCommunicationNetwork(config=comm_cfg)
        coord_mgr = CoordinationManager(config=coord_cfg)

        network.register_participant("veh_A")
        network.register_participant("veh_B")
        network.register_participant("veh_C")

        coord_mgr.register_vehicle("veh_A")
        coord_mgr.register_vehicle("veh_B")
        coord_mgr.register_vehicle("veh_C")

        positions = {
            "veh_A": Position2D(x=0.0, y=0.0),
            "veh_B": Position2D(x=80.0, y=0.0),
            "veh_C": Position2D(x=160.0, y=0.0),
        }

        # Step 1: veh_A creates report and broadcasts it
        report = CongestionReport(
            report_id="cong_multihop_1",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_A",
            edge_id="edge_target",
            timestamp_s=1.0,
            congestion_level=CongestionLevel.SEVERE,
        )
        coord_mgr.publish_observation("veh_A", report, current_time_s=1.0)

        pkt_A = DisseminationManager.create_report_packet(
            sender_id="veh_A",
            sender_position=positions["veh_A"],
            sender_heading_rad=0.0,
            sender_speed_mps=10.0,
            sequence_number=1,
            report=report,
            current_time_s=1.0,
            max_hops=3,
        )
        network.broadcast(pkt_A, candidate_positions=positions, current_time_s=1.0)

        # In SAME_TICK, veh_B inbox has msg; veh_C inbox is EMPTY (out of range from veh_A)
        assert len(network.get_inbox("veh_B")) == 1
        assert len(network.get_inbox("veh_C")) == 0

        # Step 2: veh_B processes inbox, ingests report, and forwards to peers
        fwd_packets = coord_mgr.process_inbox_messages(
            vehicle_id="veh_B",
            inbox_packets=network.get_inbox("veh_B"),
            vehicle_position=positions["veh_B"],
            vehicle_heading_rad=0.0,
            vehicle_speed_mps=10.0,
            current_time_s=1.0,
        )
        assert len(fwd_packets) == 1
        fwd_pkt = fwd_packets[0]
        assert fwd_pkt.sender_id == "veh_B"
        assert fwd_pkt.payload["hop_count"] == 1
        assert fwd_pkt.payload["relay_path"] == ["veh_A", "veh_B"]

        # veh_B broadcasts the forwarded packet
        network.clear_inbox("veh_B")
        network.broadcast(fwd_pkt, candidate_positions=positions, current_time_s=1.0)

        # Step 3: veh_C now receives the forwarded packet from veh_B!
        inbox_C = network.get_inbox("veh_C")
        assert len(inbox_C) == 1

        fwd_C = coord_mgr.process_inbox_messages(
            vehicle_id="veh_C",
            inbox_packets=inbox_C,
            vehicle_position=positions["veh_C"],
            vehicle_heading_rad=0.0,
            vehicle_speed_mps=10.0,
            current_time_s=1.0,
        )

        # veh_C has the belief populated from veh_A's report!
        store_C = coord_mgr.get_store("veh_C")
        belief_C = store_C.get_belief("congestion:edge_target")
        assert belief_C is not None
        assert belief_C.attributes["congestion_level"] == CongestionLevel.SEVERE.value
        assert belief_C.evidence_sources == ("veh_A",)

        # veh_C could forward further, hop_count is now 2 <= max_hops 3
        assert len(fwd_C) == 1
        assert fwd_C[0].payload["hop_count"] == 2
        assert fwd_C[0].payload["relay_path"] == ["veh_A", "veh_B", "veh_C"]

    def test_loop_prevention_stops_cycle_back_to_origin(self) -> None:
        """Verify that a packet relayed back to origin A is dropped without re-forwarding."""
        coord_cfg = CoordinationConfig(enabled=True, max_forwarding_hops=5)
        coord_mgr = CoordinationManager(config=coord_cfg)
        coord_mgr.register_vehicle("veh_A")

        report = CongestionReport(
            report_id="cong_loop_test",
            report_type=ReportType.CONGESTION,
            reporting_vehicle_id="veh_A",
            edge_id="edge_1",
            timestamp_s=2.0,
        )
        coord_mgr.publish_observation("veh_A", report, current_time_s=2.0)

        # Simulate inbound packet that has already traversed veh_A -> veh_B -> returning to veh_A
        loop_pkt = DisseminationManager.create_forwarded_packet(
            forwarding_vehicle_id="veh_B",
            forwarding_position=Position2D(x=50.0, y=0.0),
            forwarding_heading_rad=0.0,
            forwarding_speed_mps=10.0,
            sequence_number=1,
            report=report,
            inbound_hop_count=1,
            max_hops=5,
            inbound_relay_path=["veh_A", "veh_B"],
            current_time_s=2.0,
        )

        # veh_A receives the packet containing itself in relay_path
        fwd_list = coord_mgr.process_inbox_messages(
            vehicle_id="veh_A",
            inbox_packets=[loop_pkt],
            vehicle_position=Position2D(x=0.0, y=0.0),
            vehicle_heading_rad=0.0,
            vehicle_speed_mps=10.0,
            current_time_s=2.0,
        )

        # Loop detected and suppressed: veh_A does NOT forward it again!
        assert len(fwd_list) == 0
        assert (
            coord_mgr.metrics.reports_rejected_duplicate >= 1
            or coord_mgr.metrics.forwarding_loops_prevented >= 1
        )

    def test_max_hops_enforcement_stops_forwarding(self) -> None:
        coord_cfg = CoordinationConfig(enabled=True, max_forwarding_hops=1)
        coord_mgr = CoordinationManager(config=coord_cfg)

        report = RoadClosureReport(
            report_id="close_hops_test",
            report_type=ReportType.ROAD_CLOSURE,
            reporting_vehicle_id="veh_A",
            edge_id="edge_1",
            timestamp_s=1.0,
        )

        # Packet with hop_count = 1 already (next hop would be 2 > max 1)
        pkt = DisseminationManager.create_forwarded_packet(
            forwarding_vehicle_id="veh_B",
            forwarding_position=Position2D(x=50.0, y=0.0),
            forwarding_heading_rad=0.0,
            forwarding_speed_mps=10.0,
            sequence_number=1,
            report=report,
            inbound_hop_count=1,
            max_hops=1,
            inbound_relay_path=["veh_A", "veh_B"],
            current_time_s=1.0,
        )

        fwd_list = coord_mgr.process_inbox_messages(
            vehicle_id="veh_C",
            inbox_packets=[pkt],
            vehicle_position=Position2D(x=100.0, y=0.0),
            vehicle_heading_rad=0.0,
            vehicle_speed_mps=10.0,
            current_time_s=1.0,
        )

        # veh_C ingests the report into local store
        store_C = coord_mgr.get_store("veh_C")
        assert store_C.report_count == 1
        # But does NOT forward it because hop limit was reached
        assert len(fwd_list) == 0
        assert coord_mgr.metrics.forwarding_hops_exceeded >= 1
