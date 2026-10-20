"""Communication metrics tracking for simulated V2V interactions."""

from dataclasses import dataclass
from typing import Any

from apps.core.communication.models import DropReason


@dataclass
class CommunicationMetrics:
    """Accumulator for discrete communication statistics across simulation ticks.

    Attributes:
        broadcasts_attempted: Number of broadcast dispatch requests initiated.
        broadcasts_successful: Number of broadcasts that reached at least one peer.
        unicasts_attempted: Number of targeted unicast transmissions initiated.
        unicasts_successful: Number of unicast deliveries successfully received.
        delivery_attempts: Total individual message-to-receiver delivery attempts.
        successful_deliveries: Total individual message deliveries successfully enqueued/received.
        dropped_out_of_range: Deliveries not attempted due to spatial distance exceeding range.
        dropped_packet_loss: Deliveries dropped due to simulated deterministic packet loss.
        dropped_unavailable: Deliveries dropped because sender or receiver was marked unavailable.
        dropped_expired: Messages dropped because their simulation expiry timestamp elapsed.
        dropped_duplicate: Messages dropped because receiver already processed this message ID.
        dropped_invalid: Messages dropped due to validation failure or malformed structure.
        peers_discovered_total: Cumulative sum of discovered peers across all discovery queries.
    """

    broadcasts_attempted: int = 0
    broadcasts_successful: int = 0
    unicasts_attempted: int = 0
    unicasts_successful: int = 0
    delivery_attempts: int = 0
    successful_deliveries: int = 0
    dropped_out_of_range: int = 0
    dropped_packet_loss: int = 0
    dropped_unavailable: int = 0
    dropped_expired: int = 0
    dropped_duplicate: int = 0
    dropped_invalid: int = 0
    peers_discovered_total: int = 0

    def record_drop(self, reason: DropReason) -> None:
        """Increment the appropriate drop counter according to DropReason."""
        if reason == DropReason.OUT_OF_RANGE:
            self.dropped_out_of_range += 1
        elif reason == DropReason.PACKET_LOSS:
            self.dropped_packet_loss += 1
        elif reason in (DropReason.RECEIVER_UNAVAILABLE, DropReason.SENDER_UNAVAILABLE):
            self.dropped_unavailable += 1
        elif reason == DropReason.EXPIRED:
            self.dropped_expired += 1
        elif reason == DropReason.DUPLICATE:
            self.dropped_duplicate += 1
        elif reason == DropReason.INVALID_MESSAGE:
            self.dropped_invalid += 1

    def reset(self) -> None:
        """Reset all metric counters back to zero."""
        self.broadcasts_attempted = 0
        self.broadcasts_successful = 0
        self.unicasts_attempted = 0
        self.unicasts_successful = 0
        self.delivery_attempts = 0
        self.successful_deliveries = 0
        self.dropped_out_of_range = 0
        self.dropped_packet_loss = 0
        self.dropped_unavailable = 0
        self.dropped_expired = 0
        self.dropped_duplicate = 0
        self.dropped_invalid = 0
        self.peers_discovered_total = 0

    def clone(self) -> "CommunicationMetrics":
        """Produce an exact detached copy of the current metrics for rollback snapshots."""
        return CommunicationMetrics(
            broadcasts_attempted=self.broadcasts_attempted,
            broadcasts_successful=self.broadcasts_successful,
            unicasts_attempted=self.unicasts_attempted,
            unicasts_successful=self.unicasts_successful,
            delivery_attempts=self.delivery_attempts,
            successful_deliveries=self.successful_deliveries,
            dropped_out_of_range=self.dropped_out_of_range,
            dropped_packet_loss=self.dropped_packet_loss,
            dropped_unavailable=self.dropped_unavailable,
            dropped_expired=self.dropped_expired,
            dropped_duplicate=self.dropped_duplicate,
            dropped_invalid=self.dropped_invalid,
            peers_discovered_total=self.peers_discovered_total,
        )

    def to_dict(self) -> dict[str, int]:
        """Convert metrics to a plain dictionary for serialization."""
        return {
            "broadcasts_attempted": self.broadcasts_attempted,
            "broadcasts_successful": self.broadcasts_successful,
            "unicasts_attempted": self.unicasts_attempted,
            "unicasts_successful": self.unicasts_successful,
            "delivery_attempts": self.delivery_attempts,
            "successful_deliveries": self.successful_deliveries,
            "dropped_out_of_range": self.dropped_out_of_range,
            "dropped_packet_loss": self.dropped_packet_loss,
            "dropped_unavailable": self.dropped_unavailable,
            "dropped_expired": self.dropped_expired,
            "dropped_duplicate": self.dropped_duplicate,
            "dropped_invalid": self.dropped_invalid,
            "peers_discovered_total": self.peers_discovered_total,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommunicationMetrics":
        """Instantiate metrics from a dictionary."""
        return cls(
            broadcasts_attempted=int(data.get("broadcasts_attempted", 0)),
            broadcasts_successful=int(data.get("broadcasts_successful", 0)),
            unicasts_attempted=int(data.get("unicasts_attempted", 0)),
            unicasts_successful=int(data.get("unicasts_successful", 0)),
            delivery_attempts=int(data.get("delivery_attempts", 0)),
            successful_deliveries=int(data.get("successful_deliveries", 0)),
            dropped_out_of_range=int(data.get("dropped_out_of_range", 0)),
            dropped_packet_loss=int(data.get("dropped_packet_loss", 0)),
            dropped_unavailable=int(data.get("dropped_unavailable", 0)),
            dropped_expired=int(data.get("dropped_expired", 0)),
            dropped_duplicate=int(data.get("dropped_duplicate", 0)),
            dropped_invalid=int(data.get("dropped_invalid", 0)),
            peers_discovered_total=int(data.get("peers_discovered_total", 0)),
        )
