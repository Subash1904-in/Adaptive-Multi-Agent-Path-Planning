"""V2V packet construction, report extraction, and bounded multi-hop forwarding logic."""

import uuid
from typing import Any, Optional

from apps.core.communication.models import V2VMessagePacket
from apps.core.coordination.models import (
    CoordinationConfig,
    ReportType,
    TrafficReport,
    traffic_report_from_dict,
)
from apps.core.domain.enums import V2VMessageType
from apps.core.domain.values import Position2D


def map_report_to_message_type(report_type: ReportType) -> V2VMessageType:
    """Map a ReportType to the corresponding V2VMessageType enum."""
    if report_type == ReportType.CONGESTION:
        return V2VMessageType.CONGESTION_ALERT
    elif report_type == ReportType.HAZARD:
        return V2VMessageType.HAZARD_WARNING
    elif report_type == ReportType.ROAD_CLOSURE:
        return V2VMessageType.ROUTE_ADVISORY
    return V2VMessageType.ROUTE_ADVISORY


class DisseminationManager:
    """Encapsulates V2V message envelope serialization, deserialization, and forwarding rules."""

    @staticmethod
    def create_report_packet(
        sender_id: str,
        sender_position: Position2D,
        sender_heading_rad: float,
        sender_speed_mps: float,
        sequence_number: int,
        report: TrafficReport,
        current_time_s: float,
        max_hops: int = 3,
        recipient_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> V2VMessagePacket:
        """Package a freshly generated TrafficReport into a V2VMessagePacket for transmission.

        Args:
            sender_id: Transmitting vehicle identifier.
            sender_position: Transmitting vehicle coordinate.
            sender_heading_rad: Transmitting vehicle heading in radians.
            sender_speed_mps: Forward speed in m/s.
            sequence_number: Transmission sequence number.
            report: Typed traffic report to disseminate.
            current_time_s: Simulation timestamp at creation.
            max_hops: Permitted multi-hop forwarding budget.
            recipient_id: Optional unicast recipient; None indicates broadcast.
            correlation_id: Optional tracing identifier.

        Returns:
            Configured V2VMessagePacket ready for SimulatedCommunicationNetwork injection.
        """
        msg_id = f"v2v-coord-{uuid.uuid4().hex[:12]}"
        msg_type = map_report_to_message_type(report.report_type)

        payload: dict[str, Any] = {
            "is_coordination_report": True,
            "coordination_report": report.to_dict(),
            "origin_vehicle_id": report.reporting_vehicle_id,
            "hop_count": 0,
            "max_hops": max_hops,
            "relay_path": [sender_id],
        }

        return V2VMessagePacket(
            message_id=msg_id,
            sender_id=sender_id,
            sequence_number=sequence_number,
            timestamp_s=current_time_s,
            sender_position=sender_position,
            sender_heading_rad=sender_heading_rad,
            sender_speed_mps=sender_speed_mps,
            message_type=msg_type,
            recipient_id=recipient_id,
            expiry_timestamp_s=report.expiry_timestamp_s,
            payload=payload,
            correlation_id=correlation_id or report.report_id,
        )

    @staticmethod
    def extract_report(
        packet: V2VMessagePacket,
    ) -> Optional[tuple[TrafficReport, int, int, list[str]]]:
        """Extract typed TrafficReport and forwarding metadata from a received V2VMessagePacket.

        Args:
            packet: Incoming packet to inspect.

        Returns:
            Tuple of (report, hop_count, max_hops, relay_path), or None if packet
            does not contain a coordination report.
        """
        payload = packet.payload
        if not isinstance(payload, dict) or not payload.get("is_coordination_report"):
            return None

        report_data = payload.get("coordination_report")
        if not isinstance(report_data, dict):
            return None

        try:
            report = traffic_report_from_dict(report_data)
        except Exception:
            return None

        hop_count = int(payload.get("hop_count", 0))
        max_hops = int(payload.get("max_hops", 3))
        relay_path = list(payload.get("relay_path", [packet.sender_id]))

        return report, hop_count, max_hops, relay_path

    @staticmethod
    def is_eligible_for_forwarding(
        forwarding_vehicle_id: str,
        report: TrafficReport,
        hop_count: int,
        max_hops: int,
        relay_path: list[str],
        current_time_s: float,
        config: CoordinationConfig,
    ) -> bool:
        """Determine whether a received report can be forwarded to peers.

        Rules:
        1. Coordination must be enabled.
        2. Report category must be enabled in config.
        3. Report must not be expired.
        4. Next hop must not exceed max_hops (hop_count + 1 <= max_hops).
        5. Forwarding vehicle must NOT already be in relay_path (strict loop prevention).

        Args:
            forwarding_vehicle_id: Vehicle contemplating forwarding.
            report: Typed report extracted from packet.
            hop_count: Inbound packet hop count.
            max_hops: Inbound packet maximum hop budget.
            relay_path: Sequence of vehicle IDs that already forwarded this packet.
            current_time_s: Current simulation timestamp.
            config: Coordination configuration.

        Returns:
            True if eligible for forwarding; False otherwise.
        """
        if not config.enabled:
            return False

        if report.report_type not in config.enabled_categories:
            return False

        if report.is_expired(current_time_s):
            return False

        effective_max_hops = min(max_hops, config.max_forwarding_hops)
        if (hop_count + 1) > effective_max_hops:
            return False

        # Strict cycle / loop prevention: do not forward if vehicle already visited
        if forwarding_vehicle_id in relay_path:
            return False

        return True

    @staticmethod
    def create_forwarded_packet(
        forwarding_vehicle_id: str,
        forwarding_position: Position2D,
        forwarding_heading_rad: float,
        forwarding_speed_mps: float,
        sequence_number: int,
        report: TrafficReport,
        inbound_hop_count: int,
        max_hops: int,
        inbound_relay_path: list[str],
        current_time_s: float,
        recipient_id: Optional[str] = None,
    ) -> V2VMessagePacket:
        """Construct a new V2VMessagePacket representing the forwarded report with incremented hops.

        Preserves original report provenance and payload integrity while updating hop metadata.
        """
        msg_id = f"v2v-fwd-{uuid.uuid4().hex[:12]}"
        msg_type = map_report_to_message_type(report.report_type)

        new_relay_path = list(inbound_relay_path) + [forwarding_vehicle_id]
        payload: dict[str, Any] = {
            "is_coordination_report": True,
            "coordination_report": report.to_dict(),
            "origin_vehicle_id": report.reporting_vehicle_id,
            "hop_count": inbound_hop_count + 1,
            "max_hops": max_hops,
            "relay_path": new_relay_path,
        }

        return V2VMessagePacket(
            message_id=msg_id,
            sender_id=forwarding_vehicle_id,
            sequence_number=sequence_number,
            timestamp_s=current_time_s,
            sender_position=forwarding_position,
            sender_heading_rad=forwarding_heading_rad,
            sender_speed_mps=forwarding_speed_mps,
            message_type=msg_type,
            recipient_id=recipient_id,
            expiry_timestamp_s=report.expiry_timestamp_s,
            payload=payload,
            correlation_id=report.report_id,
        )
