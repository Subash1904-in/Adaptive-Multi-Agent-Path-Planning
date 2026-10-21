"""Subsystem coordinator managing knowledge stores, V2V packet routing, and metrics."""

from typing import Any, Optional

from apps.core.communication.models import V2VMessagePacket
from apps.core.coordination.dissemination import DisseminationManager
from apps.core.coordination.exceptions import (
    CoordinationStateError,
    InvalidRoadEdgeError,
    UnknownSourceVehicleError,
)
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.models import (
    CoordinationConfig,
    CoordinationMetrics,
    CoordinationSnapshot,
    TrafficReport,
)
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph


class CoordinationManager:
    """Manages the decentralized knowledge sharing subsystem across all simulation vehicles.

    Attributes:
        config: System-wide coordination parameters.
        road_graph: Optional RoadGraph reference for validating edge references in reports.
        metrics: Telemetry counters for coordination events.
    """

    def __init__(
        self,
        config: Optional[CoordinationConfig] = None,
        road_graph: Optional[RoadGraph] = None,
    ) -> None:
        self.config: CoordinationConfig = config or CoordinationConfig()
        self.road_graph: Optional[RoadGraph] = road_graph
        self.metrics: CoordinationMetrics = CoordinationMetrics()
        self._stores: dict[str, VehicleKnowledgeStore] = {}
        self._sequences: dict[str, int] = {}

    @property
    def vehicle_count(self) -> int:
        """Total number of vehicles registered with the coordination manager."""
        return len(self._stores)

    @property
    def registered_vehicle_ids(self) -> list[str]:
        """Deterministic sorted list of registered vehicle IDs."""
        return sorted(self._stores.keys())

    def register_vehicle(self, vehicle_id: str) -> VehicleKnowledgeStore:
        """Register a vehicle agent to maintain a private knowledge store.

        Args:
            vehicle_id: Unique vehicle identifier.

        Returns:
            The newly created or existing VehicleKnowledgeStore.
        """
        if vehicle_id not in self._stores:
            self._stores[vehicle_id] = VehicleKnowledgeStore(
                vehicle_id=vehicle_id,
                config=self.config,
            )
            self._sequences[vehicle_id] = 0
        return self._stores[vehicle_id]

    def unregister_vehicle(self, vehicle_id: str) -> None:
        """Remove a vehicle from coordination management."""
        self._stores.pop(vehicle_id, None)
        self._sequences.pop(vehicle_id, None)

    def has_vehicle(self, vehicle_id: str) -> bool:
        """Check whether a vehicle is registered."""
        return vehicle_id in self._stores

    def get_store(self, vehicle_id: str) -> VehicleKnowledgeStore:
        """Retrieve the private knowledge store of a specific vehicle.

        Raises:
            UnknownSourceVehicleError: If vehicle_id is not registered.
        """
        if vehicle_id not in self._stores:
            raise UnknownSourceVehicleError(vehicle_id)
        return self._stores[vehicle_id]

    def publish_observation(
        self,
        vehicle_id: str,
        report: TrafficReport,
        current_time_s: float,
    ) -> bool:
        """Record a local observation directly made by a vehicle agent.

        Args:
            vehicle_id: Reporting vehicle identifier.
            report: Validated traffic report.
            current_time_s: Current simulation timestamp.

        Returns:
            True if observation was successfully added and fused.

        Raises:
            UnknownSourceVehicleError: If vehicle_id is not registered.
            InvalidRoadEdgeError: If report references an edge missing from road graph.
        """
        if not self.has_vehicle(vehicle_id):
            raise UnknownSourceVehicleError(vehicle_id)

        # Validate edge in road graph if available
        edge_id = getattr(report, "edge_id", None)
        if edge_id and self.road_graph is not None and not self.road_graph.has_edge(edge_id):
            self.metrics.reports_rejected_invalid += 1
            raise InvalidRoadEdgeError(edge_id)

        store = self.get_store(vehicle_id)
        initial_beliefs = store.belief_count
        success = store.add_observation(report, current_time_s=current_time_s)
        if success:
            self.metrics.reports_created += 1
            self.metrics.reports_accepted += 1
            if store.belief_count > initial_beliefs:
                self.metrics.beliefs_created += 1
            else:
                self.metrics.beliefs_updated += 1
        return success

    def ingest_report(self, report: TrafficReport, current_time_s: float = 0.0) -> int:
        """Broadcast and ingest an authoritative traffic report into all registered vehicle stores.

        Args:
            report: The authoritative traffic report (e.g. from incident injection).
            current_time_s: Current authoritative simulation time.

        Returns:
            int: Number of vehicle knowledge stores that accepted and fused the report.
        """
        if not self.config.enabled:
            return 0
        accepted_count = 0
        for store in self._stores.values():
            if store.ingest_report(report, current_time_s=current_time_s):
                accepted_count += 1
        return accepted_count

    def process_inbox_messages(
        self,
        vehicle_id: str,
        inbox_packets: list[V2VMessagePacket],
        vehicle_position: Position2D,
        vehicle_heading_rad: float,
        vehicle_speed_mps: float,
        current_time_s: float,
    ) -> list[V2VMessagePacket]:
        """Ingest received V2V packets for a vehicle and prepare bounded forwarding packets.

        Args:
            vehicle_id: Receiving vehicle identifier.
            inbox_packets: List of packets delivered to this vehicle's inbox.
            vehicle_position: Current vehicle coordinates.
            vehicle_heading_rad: Current vehicle heading.
            vehicle_speed_mps: Current forward speed.
            current_time_s: Current authoritative simulation time.

        Returns:
            List of new V2VMessagePackets generated for multi-hop forwarding.
        """
        if not self.config.enabled:
            return []

        store = self.register_vehicle(vehicle_id)
        forward_packets: list[V2VMessagePacket] = []

        for packet in inbox_packets:
            extraction = DisseminationManager.extract_report(packet)
            if extraction is None:
                continue

            report, hop_count, max_hops, relay_path = extraction
            self.metrics.reports_received += 1

            # Validate edge against graph if graph is present
            edge_id = getattr(report, "edge_id", None)
            if edge_id and self.road_graph is not None and not self.road_graph.has_edge(edge_id):
                self.metrics.reports_rejected_invalid += 1
                continue

            # Check duplicate
            if store.has_seen_report(report.report_id):
                self.metrics.reports_rejected_duplicate += 1
                continue

            # Check expired
            if report.is_expired(current_time_s):
                self.metrics.reports_rejected_expired += 1
                continue

            # Check trust
            if report.confidence < self.config.trust_threshold:
                self.metrics.reports_rejected_untrusted += 1
                continue

            # Ingest into vehicle-private knowledge store
            initial_beliefs = store.belief_count
            accepted = store.ingest_report(report, current_time_s=current_time_s)
            if not accepted:
                continue

            self.metrics.reports_accepted += 1
            if store.belief_count > initial_beliefs:
                self.metrics.beliefs_created += 1
            else:
                self.metrics.beliefs_updated += 1

            # Multi-hop forwarding evaluation
            if not store.has_forwarded_report(report.report_id):
                eligible = DisseminationManager.is_eligible_for_forwarding(
                    forwarding_vehicle_id=vehicle_id,
                    report=report,
                    hop_count=hop_count,
                    max_hops=max_hops,
                    relay_path=relay_path,
                    current_time_s=current_time_s,
                    config=self.config,
                )

                if eligible:
                    seq = self._sequences.get(vehicle_id, 0) + 1
                    self._sequences[vehicle_id] = seq

                    fwd_packet = DisseminationManager.create_forwarded_packet(
                        forwarding_vehicle_id=vehicle_id,
                        forwarding_position=vehicle_position,
                        forwarding_heading_rad=vehicle_heading_rad,
                        forwarding_speed_mps=vehicle_speed_mps,
                        sequence_number=seq,
                        report=report,
                        inbound_hop_count=hop_count,
                        max_hops=max_hops,
                        inbound_relay_path=relay_path,
                        current_time_s=current_time_s,
                    )
                    store.mark_report_forwarded(report.report_id)
                    forward_packets.append(fwd_packet)
                    self.metrics.reports_forwarded += 1
                else:
                    if vehicle_id in relay_path:
                        self.metrics.forwarding_loops_prevented += 1
                    if (hop_count + 1) > min(max_hops, self.config.max_forwarding_hops):
                        self.metrics.forwarding_hops_exceeded += 1

        return forward_packets

    def perform_maintenance(self, current_time_s: float) -> None:
        """Perform routine expiration maintenance across all registered stores."""
        for store in self._stores.values():
            reports_exp, beliefs_exp = store.expire_entries(current_time_s)
            self.metrics.beliefs_expired += beliefs_exp

    def capture_state(self) -> dict[str, Any]:
        """Capture an isolated snapshot of stores, metrics, and sequences for atomic rollback."""
        return {
            "stores": {vid: s.capture_state() for vid, s in self._stores.items()},
            "metrics": self.metrics.to_dict(),
            "sequences": dict(self._sequences),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Atomically restore coordination subsystem state from a snapshot.

        Args:
            state: Dictionary produced by capture_state().

        Raises:
            CoordinationStateError: If snapshot is malformed.
        """
        if not isinstance(state, dict) or "stores" not in state or "metrics" not in state:
            raise CoordinationStateError("Malformed coordination rollback snapshot.")

        try:
            # Restore existing stores
            snap_stores = state["stores"]
            current_vids = set(self._stores.keys())
            snap_vids = set(snap_stores.keys())

            # Remove any stores that were created during the aborted step
            for vid in current_vids - snap_vids:
                del self._stores[vid]

            # Restore snapshot stores
            for vid, s_state in snap_stores.items():
                if vid not in self._stores:
                    self._stores[vid] = VehicleKnowledgeStore(vehicle_id=vid, config=self.config)
                self._stores[vid].restore_state(s_state)

            # Restore metrics and sequences
            self.metrics = CoordinationMetrics(**state["metrics"])
            self._sequences = dict(state.get("sequences", {}))
        except Exception as exc:
            raise CoordinationStateError(
                f"Failed to restore coordination manager state: {exc}"
            ) from exc

    def reset(self) -> None:
        """Reset all stores, metrics, and state counters."""
        self._stores.clear()
        self._sequences.clear()
        self.metrics.reset()

    def get_snapshot(self, current_time_s: float = 0.0) -> CoordinationSnapshot:
        """Generate a system-wide point-in-time snapshot of the coordination subsystem."""
        total_reports = sum(s.report_count for s in self._stores.values())
        total_beliefs = sum(s.belief_count for s in self._stores.values())
        stores_snap = {
            vid: s.get_snapshot(current_time_s=current_time_s)
            for vid, s in sorted(self._stores.items())
        }

        return CoordinationSnapshot(
            enabled=self.config.enabled,
            vehicle_count=len(self._stores),
            total_reports=total_reports,
            total_beliefs=total_beliefs,
            metrics=self.metrics.to_dict(),
            stores=stores_snap,
        )
