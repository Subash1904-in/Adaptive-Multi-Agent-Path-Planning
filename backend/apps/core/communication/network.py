"""In-memory simulated Vehicle-to-Vehicle communication network.

Manages participant registrations, spatial broadcast routing, message inboxes,
message deduplication, expiration enforcement, deterministic packet loss,
multi-tick transit queues with latency, burst loss, and network degradation/recovery.
"""

import math
import random
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Optional

from apps.core.communication.discovery import SpatialPeerDiscovery
from apps.core.communication.exceptions import (
    CommunicationStateError,
    CommunicationValidationError,
    DuplicateRegistrationError,
    InvalidOutageError,
    InvalidPartitionError,
    UnknownReceiverError,
    UnknownSenderError,
)
from apps.core.communication.metrics import CommunicationMetrics
from apps.core.communication.models import (
    ChannelState,
    CommunicationConfig,
    CommunicationSnapshot,
    DeliveryPolicy,
    DeliveryStatus,
    DropReason,
    InTransitPacket,
    TemporaryLinkOutage,
    TemporaryOutage,
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

        # Multi-tick in-transit queue (Phase 14)
        self._in_transit_packets: list[InTransitPacket] = []

        # Deduplication tracking per receiver: receiver_id -> set of seen message_ids
        self._received_message_ids: dict[str, set[str]] = defaultdict(set)

        # Sequence number tracking per sender: sender_id -> highest sequence number seen
        self._sender_sequence_numbers: dict[str, int] = {}

        # PRNGs for deterministic network impairment
        self._packet_loss_rng = random.Random(
            self.config.packet_loss_seed if self.config.packet_loss_seed is not None else 42
        )
        self._latency_rng = random.Random(
            self.config.latency_seed if self.config.latency_seed is not None else 1001
        )
        self._burst_loss_rng = random.Random(
            self.config.burst_loss_seed if self.config.burst_loss_seed is not None else 2002
        )

        # Burst loss Markov channel state
        self._burst_channel_state: ChannelState = ChannelState.GOOD

        # Degradation: temporary participant outages, link outages, and network partitions
        self._temporary_outages: list[TemporaryOutage] = []
        self._temporary_link_outages: list[TemporaryLinkOutage] = []
        self._disabled_links: set[tuple[str, str]] = set()
        self._partitions: list[set[str]] = []

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
        self._in_transit_packets = [
            it for it in self._in_transit_packets
            if it.receiver_id != vehicle_id and it.packet.sender_id != vehicle_id
        ]
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
    # Network Impairment, Outages, and Partitions Controls (Phase 14)
    # -------------------------------------------------------------------------
    def is_latency_enabled(self) -> bool:
        """Return True if message latency delay is configured."""
        return self.config.max_latency_s > 0.0 or self.config.min_latency_s > 0.0

    def add_temporary_outage(self, outage: TemporaryOutage) -> None:
        """Register a temporary communication outage for a participant."""
        if not isinstance(outage, TemporaryOutage):
            raise InvalidOutageError(0, 0, "outage must be a TemporaryOutage instance.")
        if outage.target_id not in self._registered_participants:
            raise UnknownSenderError(outage.target_id)
        self._temporary_outages.append(outage)

    def add_participant_outage(
        self, vehicle_id: str, start_time_s: float, end_time_s: float
    ) -> TemporaryOutage:
        """Convenience method to register a temporary outage window for a vehicle."""
        outage = TemporaryOutage(
            target_id=vehicle_id,
            start_time_s=start_time_s,
            end_time_s=end_time_s,
        )
        self.add_temporary_outage(outage)
        return outage

    def clear_temporary_outages(self) -> None:
        """Clear all registered temporary participant outages."""
        self._temporary_outages.clear()

    def is_participant_in_outage(self, vehicle_id: str, current_time_s: float) -> bool:
        """Check if vehicle is currently experiencing an outage at current_time_s."""
        return any(
            outage.target_id == vehicle_id and outage.is_active(current_time_s)
            for outage in self._temporary_outages
        )

    def add_temporary_link_outage(self, link_outage: TemporaryLinkOutage) -> None:
        """Register a temporary link outage between two vehicles."""
        if not isinstance(link_outage, TemporaryLinkOutage):
            raise CommunicationValidationError(
                "link_outage must be a TemporaryLinkOutage instance."
            )
        self._temporary_link_outages.append(link_outage)

    def set_link_availability(
        self, sender_id: str, receiver_id: str, available: bool, bidirectional: bool = True
    ) -> None:
        """Set static link availability between sender and receiver."""
        if not available:
            self._disabled_links.add((sender_id, receiver_id))
            if bidirectional:
                self._disabled_links.add((receiver_id, sender_id))
        else:
            self._disabled_links.discard((sender_id, receiver_id))
            if bidirectional:
                self._disabled_links.discard((receiver_id, sender_id))

    def clear_link_outages(self) -> None:
        """Clear all active and scheduled link outages."""
        self._disabled_links.clear()
        self._temporary_link_outages.clear()

    def is_link_available(self, sender_id: str, receiver_id: str, current_time_s: float) -> bool:
        """Evaluate if communication link from sender to receiver is operational."""
        if (sender_id, receiver_id) in self._disabled_links:
            return False
        return not any(
            outage.matches(sender_id, receiver_id) and outage.is_active(current_time_s)
            for outage in self._temporary_link_outages
        )

    def set_partitions(self, partitions: list[set[str] | list[str]]) -> None:
        """Configure network partitions.

        Vehicles in the same partition group can communicate with each other.
        Vehicles in different partition groups cannot communicate.
        """
        parsed_partitions: list[set[str]] = []
        for part in partitions:
            if not isinstance(part, (set, list, tuple)):
                raise InvalidPartitionError("Each partition must be an iterable of vehicle IDs.")
            cleaned = {str(item).strip() for item in part if str(item).strip()}
            if cleaned:
                parsed_partitions.append(cleaned)
        self._partitions = parsed_partitions

    def clear_partitions(self) -> None:
        """Clear all network partition constraints."""
        self._partitions.clear()

    def get_partitions(self) -> list[list[str]]:
        """Return canonical sorted list of current network partitions."""
        return [sorted(p) for p in self._partitions]

    def can_communicate_partition(self, sender_id: str, receiver_id: str) -> bool:
        """Check if sender and receiver are allowed to communicate across partition boundaries."""
        if not self._partitions:
            return True

        sender_parts = [i for i, part in enumerate(self._partitions) if sender_id in part]
        receiver_parts = [i for i, part in enumerate(self._partitions) if receiver_id in part]

        # If neither is in any partition, they are not blocked by partition rules
        if not sender_parts and not receiver_parts:
            return True

        # If one is partitioned and the other isn't, or they are in distinct partitions: blocked
        return bool(set(sender_parts) & set(receiver_parts))

    # -------------------------------------------------------------------------
    # Channel State & Burst Loss (Markov Model)
    # -------------------------------------------------------------------------
    def get_channel_state(self) -> ChannelState:
        """Return current Gilbert-Elliott burst channel state."""
        return self._burst_channel_state

    def set_channel_state(self, state: ChannelState) -> None:
        """Explicitly override current burst channel state for deterministic test control."""
        if not isinstance(state, ChannelState):
            raise CommunicationValidationError(f"Invalid channel state: {state}")
        self._burst_channel_state = state

    def step_burst_channel(self) -> ChannelState:
        """Advance the two-state Markov burst loss channel state."""
        if not self.config.burst_loss_enabled:
            return self._burst_channel_state

        if self._burst_channel_state == ChannelState.GOOD:
            if self._burst_loss_rng.random() < self.config.burst_loss_p_gb:
                self._burst_channel_state = ChannelState.BAD
        else:
            if self._burst_loss_rng.random() < self.config.burst_loss_p_bg:
                self._burst_channel_state = ChannelState.GOOD
        return self._burst_channel_state

    def _sample_latency(self) -> float:
        """Sample a deterministic message latency value in simulation seconds."""
        if not self.is_latency_enabled():
            return 0.0
        if math.isclose(self.config.min_latency_s, self.config.max_latency_s):
            return self.config.min_latency_s
        return round(
            self._latency_rng.uniform(self.config.min_latency_s, self.config.max_latency_s), 6
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
        if not self.is_participant_available(sender_id) or self.is_participant_in_outage(
            sender_id, current_time_s
        ):
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
            recip_pos = candidate_positions.get(peer_id)
            if self._deliver_to_receiver(
                message=message,
                receiver_id=peer_id,
                current_time_s=current_time_s,
                receiver_position=recip_pos,
            ):
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
        if not self.is_participant_available(sender_id) or self.is_participant_in_outage(
            sender_id, current_time_s
        ):
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
        delivered = self._deliver_to_receiver(
            message=message,
            receiver_id=recipient_id,
            current_time_s=current_time_s,
            receiver_position=recip_pos,
        )
        if delivered:
            self.metrics.unicasts_successful += 1
        return delivered

    def _deliver_to_receiver(
        self,
        message: V2VMessagePacket,
        receiver_id: str,
        current_time_s: float,
        receiver_position: Optional[Position2D] = None,
    ) -> bool:
        """Evaluate receiver availability, degradation, loss, latency, and enqueue message."""
        # 1. Check receiver availability & temporary participant outage
        if not self.is_participant_available(receiver_id) or self.is_participant_in_outage(
            receiver_id, current_time_s
        ):
            self.metrics.record_drop(DropReason.RECEIVER_UNAVAILABLE)
            return False

        # 2. Check network partitions
        if not self.can_communicate_partition(message.sender_id, receiver_id):
            self.metrics.record_drop(DropReason.PARTITION_BLOCKED)
            return False

        # 3. Check link availability
        if not self.is_link_available(message.sender_id, receiver_id, current_time_s):
            self.metrics.record_drop(DropReason.LINK_UNAVAILABLE)
            return False

        # 4. Check message expiration at send time
        if message.is_expired(current_time_s):
            self.metrics.record_drop(DropReason.EXPIRED)
            return False

        # 5. Check duplicate delivery prevention at sender-acceptance stage
        if message.message_id in self._received_message_ids[receiver_id]:
            self.metrics.record_drop(DropReason.DUPLICATE)
            return False

        # 6. Check burst loss (Gilbert-Elliott Markov channel)
        if self.config.burst_loss_enabled:
            rate = (
                self.config.burst_loss_rate_good
                if self._burst_channel_state == ChannelState.GOOD
                else self.config.burst_loss_rate_bad
            )
            if rate > 0.0 and (rate >= 1.0 or self._burst_loss_rng.random() < rate):
                self.metrics.record_drop(DropReason.BURST_LOSS)
                return False

        # 7. Check distance-dependent delivery loss model
        if self.config.distance_loss_enabled and receiver_position is not None:
            dist = message.sender_position.distance_to(receiver_position)
            range_m = max(1e-6, self.config.range_m)
            ratio = min(1.0, max(0.0, dist / range_m))
            p_dist_loss = ratio ** self.config.distance_loss_exponent
            if p_dist_loss > 0.0 and (
                p_dist_loss >= 1.0 or self._packet_loss_rng.random() < p_dist_loss
            ):
                self.metrics.record_drop(DropReason.PACKET_LOSS)
                return False

        # 8. Check uniform probabilistic packet loss
        if self._should_drop_packet():
            self.metrics.record_drop(DropReason.PACKET_LOSS)
            return False

        # Record message ID in deduplication cache
        self._received_message_ids[receiver_id].add(message.message_id)

        # 9. Latency and delivery scheduling
        latency_s = self._sample_latency()
        scheduled_delivery_time_s = current_time_s + latency_s

        if latency_s == 0.0 and self.config.delivery_policy == DeliveryPolicy.SAME_TICK:
            # Immediate zero-latency SAME_TICK delivery
            self._inboxes[receiver_id].append(message)
            self.metrics.successful_deliveries += 1
            return True

        # Multi-tick or NEXT_TICK delivery queue
        in_transit = InTransitPacket(
            packet=message,
            receiver_id=receiver_id,
            send_timestamp_s=current_time_s,
            scheduled_delivery_time_s=scheduled_delivery_time_s,
            delivery_status=DeliveryStatus.QUEUED_PENDING_LATENCY,
        )
        self._in_transit_packets.append(in_transit)
        self._transit_queue[receiver_id].append(message)

        if latency_s > 0.0:
            self.metrics.packets_queued_latency += 1
        else:
            # Zero-latency NEXT_TICK: record acceptance for backward compatibility
            self.metrics.successful_deliveries += 1

        return True

    def _should_drop_packet(self) -> bool:
        """Evaluate deterministic uniform packet loss predicate."""
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

    def get_in_transit_packets(self) -> list[InTransitPacket]:
        """Return all currently in-transit packets sorted deterministically."""
        return sorted(self._in_transit_packets, key=lambda pkt: pkt.sort_key)

    def get_in_transit_count(self) -> int:
        """Return count of packets currently in transit."""
        return len(self._in_transit_packets)

    def advance_tick(self, current_time_s: float) -> None:
        """Advance communication network to next discrete simulation tick.

        Advances Markov burst-loss channel, processes in-transit packets whose
        scheduled delivery timestamp has arrived (checking recipient status,
        outages, link status, and expiration), and purges expired messages.
        """
        # Step burst channel state at tick boundary
        self.step_burst_channel()

        # 1. Process multi-tick in-transit packets
        remaining_in_transit: list[InTransitPacket] = []
        deliverable_packets: list[InTransitPacket] = []

        for pkt in self._in_transit_packets:
            if pkt.scheduled_delivery_time_s <= current_time_s:
                deliverable_packets.append(pkt)
            else:
                remaining_in_transit.append(pkt)

        # Sort deliverable packets deterministically by canonical sort_key
        deliverable_packets.sort(key=lambda item: item.sort_key)

        for in_transit in deliverable_packets:
            msg = in_transit.packet
            rec_id = in_transit.receiver_id
            sender_id = msg.sender_id
            had_latency = in_transit.scheduled_delivery_time_s > in_transit.send_timestamp_s

            # Delivery boundary checks:
            # A. Message expiration
            if msg.is_expired(current_time_s):
                self.metrics.record_drop(DropReason.EXPIRED)
                continue

            # B. Receiver availability and outages
            if not self.is_participant_available(rec_id) or self.is_participant_in_outage(
                rec_id, current_time_s
            ):
                self.metrics.record_drop(DropReason.RECEIVER_UNAVAILABLE)
                continue

            # C. Partition boundaries
            if not self.can_communicate_partition(sender_id, rec_id):
                self.metrics.record_drop(DropReason.PARTITION_BLOCKED)
                continue

            # D. Link availability
            if not self.is_link_available(sender_id, rec_id, current_time_s):
                self.metrics.record_drop(DropReason.LINK_UNAVAILABLE)
                continue

            # Successful delivery to recipient inbox
            self._inboxes[rec_id].append(msg)
            if had_latency:
                self.metrics.successful_deliveries += 1
                self.metrics.packets_delivered_latency += 1

        self._in_transit_packets = remaining_in_transit

        # Re-sync legacy _transit_queue with remaining in-transit packets
        new_transit_queue: dict[str, list[V2VMessagePacket]] = defaultdict(list)
        for pkt in self._in_transit_packets:
            new_transit_queue[pkt.receiver_id].append(pkt.packet)
        self._transit_queue = new_transit_queue

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
            "in_transit_packets": [pkt.to_dict() for pkt in self._in_transit_packets],
            "received_message_ids": {
                vid: set(mids) for vid, mids in self._received_message_ids.items()
            },
            "sender_sequence_numbers": dict(self._sender_sequence_numbers),
            "metrics": self.metrics.clone(),
            "packet_loss_rng_state": self._packet_loss_rng.getstate(),
            "latency_rng_state": self._latency_rng.getstate(),
            "burst_loss_rng_state": self._burst_loss_rng.getstate(),
            "burst_channel_state": self._burst_channel_state.value,
            "temporary_outages": [o.to_dict() for o in self._temporary_outages],
            "temporary_link_outages": [o.to_dict() for o in self._temporary_link_outages],
            "disabled_links": set(self._disabled_links),
            "partitions": [set(p) for p in self._partitions],
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
        if "in_transit_packets" in state:
            self._in_transit_packets = [
                InTransitPacket.from_dict(d) for d in state["in_transit_packets"]
            ]
        else:
            self._in_transit_packets = []

        self._received_message_ids = defaultdict(
            set, {vid: set(mids) for vid, mids in state["received_message_ids"].items()}
        )
        self._sender_sequence_numbers = dict(state["sender_sequence_numbers"])
        self.metrics = state["metrics"].clone()

        if "packet_loss_rng_state" in state:
            self._packet_loss_rng.setstate(state["packet_loss_rng_state"])
        elif "rng_state" in state:
            self._packet_loss_rng.setstate(state["rng_state"])

        if "latency_rng_state" in state:
            self._latency_rng.setstate(state["latency_rng_state"])
        if "burst_loss_rng_state" in state:
            self._burst_loss_rng.setstate(state["burst_loss_rng_state"])

        if "burst_channel_state" in state:
            self._burst_channel_state = ChannelState(state["burst_channel_state"])

        if "temporary_outages" in state:
            self._temporary_outages = [
                TemporaryOutage.from_dict(d) for d in state["temporary_outages"]
            ]
        if "temporary_link_outages" in state:
            self._temporary_link_outages = [
                TemporaryLinkOutage.from_dict(d) for d in state["temporary_link_outages"]
            ]
        if "disabled_links" in state:
            self._disabled_links = set(state["disabled_links"])
        if "partitions" in state:
            self._partitions = [set(p) for p in state["partitions"]]

        if self.neighbor_manager is not None and state.get("neighbor_manager") is not None:
            self.neighbor_manager.restore_state(state["neighbor_manager"])

    def reset(self) -> None:
        """Reset communication network back to clean baseline state."""
        self._inboxes.clear()
        self._transit_queue.clear()
        self._in_transit_packets.clear()
        self._received_message_ids.clear()
        self._sender_sequence_numbers.clear()
        self._unavailable_participants.clear()
        self._temporary_outages.clear()
        self._temporary_link_outages.clear()
        self._disabled_links.clear()
        self._partitions.clear()
        self._burst_channel_state = ChannelState.GOOD
        self.metrics.reset()

        self._packet_loss_rng = random.Random(
            self.config.packet_loss_seed if self.config.packet_loss_seed is not None else 42
        )
        self._latency_rng = random.Random(
            self.config.latency_seed if self.config.latency_seed is not None else 1001
        )
        self._burst_loss_rng = random.Random(
            self.config.burst_loss_seed if self.config.burst_loss_seed is not None else 2002
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
            + self.metrics.dropped_burst_loss
            + self.metrics.dropped_link_outage
            + self.metrics.dropped_partition
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
            in_transit_count=len(self._in_transit_packets),
            channel_state=self._burst_channel_state.value,
            active_partitions=[sorted(p) for p in self._partitions] if self._partitions else None,
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
