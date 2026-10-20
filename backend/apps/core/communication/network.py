"""In-memory simulated Vehicle-to-Vehicle communication network.

Manages participant registrations, spatial broadcast routing, message inboxes,
message deduplication, expiration enforcement, and deterministic failure simulation.
"""

import random
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Optional

from apps.core.communication.discovery import SpatialPeerDiscovery
from apps.core.communication.exceptions import (
    CommunicationStateError,
    CommunicationValidationError,
    DuplicateRegistrationError,
    UnknownReceiverError,
    UnknownSenderError,
)
from apps.core.communication.metrics import CommunicationMetrics
from apps.core.communication.models import (
    CommunicationConfig,
    CommunicationSnapshot,
    DeliveryPolicy,
    DropReason,
    V2VMessagePacket,
)
from apps.core.communication.neighbors import NeighborManager, NeighborTable
from apps.core.domain.values import Position2D


class SimulatedCommunicationNetwork:
    """In-memory communication network coordinating peer-to-peer and broadcast V2V exchanges.

    All messaging is simulated strictly in memory with zero real socket or network overhead.
    Guarantees deterministic delivery ordering and support for atomic rollback snapshots.
    """

    def __init__(
        self,
        config: Optional[CommunicationConfig] = None,
        discovery: Optional[SpatialPeerDiscovery] = None,
    ) -> None:
        """Initialize the simulated communication network.

        Args:
            config: Optional CommunicationConfig. Defaults to 50m range, NEXT_TICK delivery.
            discovery: Optional SpatialPeerDiscovery instance.
        """
        self.config: CommunicationConfig = config or CommunicationConfig()
        self.discovery: SpatialPeerDiscovery = discovery or SpatialPeerDiscovery(
            range_m=self.config.range_m,
            max_peers=self.config.max_peers,
        )
        self.metrics: CommunicationMetrics = CommunicationMetrics()

        self._registered_participants: set[str] = set()
        self._unavailable_participants: set[str] = set()

        # Inboxes available to agents in the current tick: receiver_id -> list of packets
        self._inboxes: dict[str, list[V2VMessagePacket]] = defaultdict(list)

        # Transit queue for NEXT_TICK delivery: receiver_id -> list of packets in flight
        self._transit_queue: dict[str, list[V2VMessagePacket]] = defaultdict(list)

        # Deduplication tracking per receiver: receiver_id -> set of seen message_ids
        self._received_message_ids: dict[str, set[str]] = defaultdict(set)

        # Sequence number tracking per sender: sender_id -> highest sequence number seen
        self._sender_sequence_numbers: dict[str, int] = {}

        # Deterministic PRNG for simulated packet loss
        self._packet_loss_rng = random.Random(
            self.config.packet_loss_seed if self.config.packet_loss_seed is not None else 42
        )

        # Dynamic neighbor management subsystem
        self.neighbor_manager: Optional[NeighborManager] = None
        if self.config.neighbor_tracking_enabled:
            self.neighbor_manager = NeighborManager(
                update_interval_s=self.config.neighbor_update_interval_s,
                heartbeat_timeout_s=self.config.heartbeat_timeout_s,
                stale_grace_period_s=self.config.stale_grace_period_s,
                stale_policy=self.config.stale_policy,
            )

    # -------------------------------------------------------------------------
    # Participant Management
    # -------------------------------------------------------------------------
    def register_participant(self, vehicle_id: str) -> None:
        """Register a vehicle agent as an active communication endpoint.

        Args:
            vehicle_id: Unique identifier of the vehicle agent.

        Raises:
            DuplicateRegistrationError: If vehicle_id is already registered.
        """
        if not isinstance(vehicle_id, str) or not vehicle_id.strip():
            raise CommunicationValidationError(
                "vehicle_id must be a non-empty string.", field="vehicle_id"
            )
        if vehicle_id in self._registered_participants:
            raise DuplicateRegistrationError(vehicle_id)

        self._registered_participants.add(vehicle_id)
        if vehicle_id not in self._inboxes:
            self._inboxes[vehicle_id] = []
        if vehicle_id not in self._transit_queue:
            self._transit_queue[vehicle_id] = []
        if vehicle_id not in self._received_message_ids:
            self._received_message_ids[vehicle_id] = set()

        if self.neighbor_manager is not None:
            self.neighbor_manager.register_participant(vehicle_id)

    def unregister_participant(self, vehicle_id: str) -> None:
        """Remove a vehicle agent from the communication network."""
        self._registered_participants.discard(vehicle_id)
        self._unavailable_participants.discard(vehicle_id)
        self._inboxes.pop(vehicle_id, None)
        self._transit_queue.pop(vehicle_id, None)
        self._received_message_ids.pop(vehicle_id, None)
        self._sender_sequence_numbers.pop(vehicle_id, None)
        if self.neighbor_manager is not None:
            self.neighbor_manager.unregister_participant(vehicle_id)

    def is_participant_registered(self, vehicle_id: str) -> bool:
        """Check if a vehicle is registered."""
        return vehicle_id in self._registered_participants

    def set_participant_availability(self, vehicle_id: str, available: bool) -> None:
        """Simulate hardware/transceiver status for testing communication resilience.

        Args:
            vehicle_id: Registered vehicle identifier.
            available: If False, vehicle cannot transmit or receive messages.
        """
        if vehicle_id not in self._registered_participants:
            raise UnknownSenderError(vehicle_id)
        if available:
            self._unavailable_participants.discard(vehicle_id)
        else:
            self._unavailable_participants.add(vehicle_id)

    def is_participant_available(self, vehicle_id: str) -> bool:
        """Check if a registered vehicle endpoint is currently available."""
        return (
            vehicle_id in self._registered_participants
            and vehicle_id not in self._unavailable_participants
        )

    # -------------------------------------------------------------------------
    # Transmission & Delivery
    # -------------------------------------------------------------------------
    def broadcast(
        self,
        message: V2VMessagePacket,
        candidate_positions: Mapping[str, Position2D],
        current_time_s: float,
    ) -> list[str]:
        """Broadcast a message to all eligible peer vehicles within spatial range R.

        Args:
            message: Validated, immutable V2VMessagePacket.
            candidate_positions: Mapping from vehicle_id to Position2D.
            current_time_s: Current simulation timestamp in seconds.

        Returns:
            List of recipient vehicle IDs that successfully received or enqueued the packet.
        """
        if not self.config.enabled:
            return []

        self._validate_message_for_dispatch(message)
        self.metrics.broadcasts_attempted += 1

        if message.is_expired(current_time_s):
            self.metrics.record_drop(DropReason.EXPIRED)
            return []

        sender_id = message.sender_id
        if not self.is_participant_available(sender_id):
            self.metrics.record_drop(DropReason.SENDER_UNAVAILABLE)
            return []

        # Track sender sequence number
        self._sender_sequence_numbers[sender_id] = max(
            self._sender_sequence_numbers.get(sender_id, -1),
            message.sequence_number,
        )

        # 1. Spatial peer discovery
        peers = self.discovery.find_peers(
            sender_id=sender_id,
            sender_position=message.sender_position,
            candidates=candidate_positions,
        )
        self.metrics.peers_discovered_total += len(peers)

        # Count out-of-range candidates (excluding sender)
        out_of_range_count = max(0, len(candidate_positions) - 1 - len(peers))
        self.metrics.dropped_out_of_range += out_of_range_count

        successful_receivers: list[str] = []
        for peer_id in peers:
            self.metrics.delivery_attempts += 1
            if self._deliver_to_receiver(message, peer_id, current_time_s):
                successful_receivers.append(peer_id)

        if successful_receivers:
            self.metrics.broadcasts_successful += 1

        return successful_receivers

    def send_unicast(
        self,
        message: V2VMessagePacket,
        candidate_positions: Mapping[str, Position2D],
        current_time_s: float,
    ) -> bool:
        """Transmit a targeted unicast message to a specific recipient.

        Args:
            message: V2VMessagePacket with non-empty recipient_id.
            candidate_positions: Mapping from vehicle_id to Position2D.
            current_time_s: Current simulation timestamp.

        Returns:
            True if message was delivered or enqueued for recipient; False otherwise.
        """
        if not self.config.enabled:
            return False

        self._validate_message_for_dispatch(message)
        if not message.recipient_id:
            raise CommunicationValidationError(
                "send_unicast requires a non-empty recipient_id on the message.",
                field="recipient_id",
            )
        self.metrics.unicasts_attempted += 1

        if message.is_expired(current_time_s):
            self.metrics.record_drop(DropReason.EXPIRED)
            return False

        recipient_id = message.recipient_id
        if recipient_id not in self._registered_participants:
            raise UnknownReceiverError(recipient_id)

        sender_id = message.sender_id

        if not self.is_participant_available(sender_id):
            self.metrics.record_drop(DropReason.SENDER_UNAVAILABLE)
            return False

        # Self-exclusion: cannot unicast to self
        if recipient_id == sender_id:
            self.metrics.record_drop(DropReason.INVALID_MESSAGE)
            return False

        # Check spatial range
        if recipient_id not in candidate_positions:
            self.metrics.record_drop(DropReason.OUT_OF_RANGE)
            return False

        recip_pos = candidate_positions[recipient_id]
        dist = message.sender_position.distance_to(recip_pos)
        if dist > self.discovery.range_m:
            self.metrics.record_drop(DropReason.OUT_OF_RANGE)
            return False

        self.metrics.delivery_attempts += 1
        delivered = self._deliver_to_receiver(message, recipient_id, current_time_s)
        if delivered:
            self.metrics.unicasts_successful += 1
        return delivered

    def _deliver_to_receiver(
        self,
        message: V2VMessagePacket,
        receiver_id: str,
        current_time_s: float,
    ) -> bool:
        """Evaluate receiver availability, deduplication, packet loss, and enqueue message."""
        # Check receiver availability
        if not self.is_participant_available(receiver_id):
            self.metrics.record_drop(DropReason.RECEIVER_UNAVAILABLE)
            return False

        # Check simulated packet loss
        if self._should_drop_packet():
            self.metrics.record_drop(DropReason.PACKET_LOSS)
            return False

        # Check message expiration
        if message.is_expired(current_time_s):
            self.metrics.record_drop(DropReason.EXPIRED)
            return False

        # Check duplicate delivery
        if message.message_id in self._received_message_ids[receiver_id]:
            self.metrics.record_drop(DropReason.DUPLICATE)
            return False

        # Record message ID in deduplication cache
        self._received_message_ids[receiver_id].add(message.message_id)

        # Enqueue based on configured delivery policy
        if self.config.delivery_policy == DeliveryPolicy.SAME_TICK:
            self._inboxes[receiver_id].append(message)
        else:
            # NEXT_TICK delivery: held in transit until next simulation tick
            self._transit_queue[receiver_id].append(message)

        self.metrics.successful_deliveries += 1
        return True

    def _should_drop_packet(self) -> bool:
        """Evaluate deterministic packet loss predicate."""
        if self.config.packet_loss_rate <= 0.0:
            return False
        if self.config.packet_loss_rate >= 1.0:
            return True
        return self._packet_loss_rng.random() < self.config.packet_loss_rate

    def _validate_message_for_dispatch(self, message: V2VMessagePacket) -> None:
        """Verify message validity and sender registration prior to dispatch."""
        if not isinstance(message, V2VMessagePacket):
            self.metrics.record_drop(DropReason.INVALID_MESSAGE)
            raise CommunicationValidationError(
                f"Expected V2VMessagePacket, got {type(message).__name__}."
            )
        if message.sender_id not in self._registered_participants:
            self.metrics.record_drop(DropReason.SENDER_UNAVAILABLE)
            raise UnknownSenderError(message.sender_id)

    # -------------------------------------------------------------------------
    # Inbox Management & Tick Progression
    # -------------------------------------------------------------------------
    def get_inbox(self, vehicle_id: str) -> list[V2VMessagePacket]:
        """Inspect deliverable messages currently in a vehicle's inbox without clearing them."""
        if vehicle_id not in self._registered_participants:
            raise UnknownReceiverError(vehicle_id)
        return list(self._inboxes.get(vehicle_id, []))

    def clear_inbox(self, vehicle_id: str) -> list[V2VMessagePacket]:
        """Drain and return all deliverable messages from a vehicle's inbox."""
        if vehicle_id not in self._registered_participants:
            raise UnknownReceiverError(vehicle_id)
        messages = list(self._inboxes.get(vehicle_id, []))
        self._inboxes[vehicle_id].clear()
        return messages

    def advance_tick(self, current_time_s: float) -> None:
        """Advance communication network to next discrete simulation tick.

        Moves transit messages into active inboxes for NEXT_TICK delivery policy,
        and purges any messages whose simulation expiry timestamp has elapsed.
        """
        # 1. Flush transit queue into active inboxes
        for receiver_id, transit_msgs in self._transit_queue.items():
            if receiver_id in self._inboxes:
                # Filter out expired messages during transit
                valid_msgs = []
                for msg in transit_msgs:
                    if msg.is_expired(current_time_s):
                        self.metrics.record_drop(DropReason.EXPIRED)
                    else:
                        valid_msgs.append(msg)
                self._inboxes[receiver_id].extend(valid_msgs)
            transit_msgs.clear()

        # 2. Purge expired messages from current inboxes
        for receiver_id, inbox in self._inboxes.items():
            unexpired = []
            for msg in inbox:
                if msg.is_expired(current_time_s):
                    self.metrics.record_drop(DropReason.EXPIRED)
                else:
                    unexpired.append(msg)
            self._inboxes[receiver_id] = unexpired

    # -------------------------------------------------------------------------
    # State Snapshotting, Rollback & Reset
    # -------------------------------------------------------------------------
    def capture_state(self) -> dict[str, Any]:
        """Capture isolated mutable communication state for atomic engine rollback."""
        return {
            "registered_participants": set(self._registered_participants),
            "unavailable_participants": set(self._unavailable_participants),
            "inboxes": {vid: list(msgs) for vid, msgs in self._inboxes.items()},
            "transit_queue": {vid: list(msgs) for vid, msgs in self._transit_queue.items()},
            "received_message_ids": {
                vid: set(mids) for vid, mids in self._received_message_ids.items()
            },
            "sender_sequence_numbers": dict(self._sender_sequence_numbers),
            "metrics": self.metrics.clone(),
            "rng_state": self._packet_loss_rng.getstate(),
            "neighbor_manager": (
                self.neighbor_manager.capture_state() if self.neighbor_manager else None
            ),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore exact communication state from a captured rollback snapshot."""
        if not isinstance(state, dict):
            raise CommunicationStateError("Rollback state must be a dictionary.")

        self._registered_participants = set(state["registered_participants"])
        self._unavailable_participants = set(state["unavailable_participants"])
        self._inboxes = defaultdict(
            list, {vid: list(msgs) for vid, msgs in state["inboxes"].items()}
        )
        self._transit_queue = defaultdict(
            list, {vid: list(msgs) for vid, msgs in state["transit_queue"].items()}
        )
        self._received_message_ids = defaultdict(
            set, {vid: set(mids) for vid, mids in state["received_message_ids"].items()}
        )
        self._sender_sequence_numbers = dict(state["sender_sequence_numbers"])
        self.metrics = state["metrics"].clone()
        self._packet_loss_rng.setstate(state["rng_state"])
        if self.neighbor_manager is not None and state.get("neighbor_manager") is not None:
            self.neighbor_manager.restore_state(state["neighbor_manager"])

    def reset(self) -> None:
        """Reset communication network back to clean baseline state."""
        self._inboxes.clear()
        self._transit_queue.clear()
        self._received_message_ids.clear()
        self._sender_sequence_numbers.clear()
        self._unavailable_participants.clear()
        self.metrics.reset()
        self._packet_loss_rng = random.Random(
            self.config.packet_loss_seed if self.config.packet_loss_seed is not None else 42
        )
        if self.neighbor_manager is not None:
            self.neighbor_manager.reset()

        for vid in self._registered_participants:
            self._inboxes[vid] = []
            self._transit_queue[vid] = []
            self._received_message_ids[vid] = set()
            if self.neighbor_manager is not None:
                self.neighbor_manager.register_participant(vid)

    def get_snapshot(self, current_time_s: float = 0.0) -> CommunicationSnapshot:
        """Produce an immutable point-in-time snapshot for inclusion in WorldSnapshot."""
        inbox_counts = {vid: len(msgs) for vid, msgs in self._inboxes.items()}
        total_dropped = (
            self.metrics.dropped_out_of_range
            + self.metrics.dropped_packet_loss
            + self.metrics.dropped_unavailable
            + self.metrics.dropped_expired
            + self.metrics.dropped_duplicate
            + self.metrics.dropped_invalid
        )
        neighbor_tables_snap = None
        neighbor_metrics_snap = None
        if self.neighbor_manager is not None:
            snap_dict = self.neighbor_manager.get_snapshot(current_time_s)
            neighbor_tables_snap = snap_dict["tables"]
            neighbor_metrics_snap = snap_dict["metrics"]

        return CommunicationSnapshot(
            enabled=self.config.enabled,
            range_m=self.config.range_m,
            delivery_policy=self.config.delivery_policy.value,
            total_broadcasts=self.metrics.broadcasts_attempted,
            total_delivered=self.metrics.successful_deliveries,
            total_dropped=total_dropped,
            pending_inbox_counts=inbox_counts,
            sequence_counters=dict(self._sender_sequence_numbers),
            neighbor_tables=neighbor_tables_snap,
            neighbor_metrics=neighbor_metrics_snap,
        )

    # -------------------------------------------------------------------------
    # Neighbor Subsystem Delegation
    # -------------------------------------------------------------------------
    def get_neighbor_table(self, vehicle_id: str) -> Optional[NeighborTable]:
        """Retrieve the NeighborTable for a vehicle, or None if disabled/unregistered."""
        if self.neighbor_manager is not None and self.neighbor_manager.has_table(vehicle_id):
            return self.neighbor_manager.get_table(vehicle_id)
        return None

    def update_neighbor_tables(
        self,
        candidate_positions: Mapping[str, Position2D],
        current_time_s: float,
    ) -> None:
        """Process messages currently in vehicle inboxes to refresh neighbor tables."""
        if not self.config.enabled or self.neighbor_manager is None:
            return

        for vid in sorted(self._registered_participants):
            inbox = self._inboxes.get(vid, [])
            pos = candidate_positions.get(vid)
            if pos is not None and inbox:
                self.neighbor_manager.process_inbox(
                    vehicle_id=vid,
                    messages=inbox,
                    observer_position=pos,
                    current_time_s=current_time_s,
                )

    def perform_neighbor_maintenance(self, current_time_s: float) -> None:
        """Perform heartbeat timeout and neighbor expiration maintenance."""
        if not self.config.enabled or self.neighbor_manager is None:
            return
        self.neighbor_manager.perform_maintenance(current_time_s)
