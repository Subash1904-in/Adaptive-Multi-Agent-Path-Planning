"""Dynamic neighbor tables, heartbeats, and neighbor loss detection subsystem.

Maintains per-vehicle neighbor tables tracking communicating peers, last observed
telemetry, heartbeat freshness, timeout transitions (stale/removed), and atomic snapshots.
"""

import math
from dataclasses import dataclass
from typing import Any, Optional

from apps.core.communication.exceptions import (
    InvalidNeighborDataError,
    NeighborNotFoundError,
    SelfNeighborError,
)
from apps.core.communication.models import (
    NeighborStatus,
    StaleNeighborPolicy,
    V2VMessagePacket,
)
from apps.core.domain.values import Position2D


@dataclass(frozen=True)
class NeighborRecord:
    """Immutable record representing communication knowledge about a nearby vehicle.

    Attributes:
        vehicle_id: Unique identifier of the neighbor vehicle.
        last_position: Planar position observed from the latest accepted message.
        last_distance_m: Distance from local vehicle at latest message reception.
        last_speed_mps: Instantaneous forward speed in meters per second (>= 0.0).
        last_heading_rad: Heading orientation in radians.
        last_seen_timestamp_s: Simulation timestamp when last communication was received.
        last_heartbeat_timestamp_s: Simulation timestamp of latest accepted heartbeat.
        last_sequence_number: Monotonically increasing sequence number from sender.
        status: Freshness status (ACTIVE or STALE).
        last_message_id: Optional identifier of the most recent accepted packet.
    """

    vehicle_id: str
    last_position: Position2D
    last_distance_m: float
    last_speed_mps: float
    last_heading_rad: float
    last_seen_timestamp_s: float
    last_heartbeat_timestamp_s: float
    last_sequence_number: int
    status: NeighborStatus = NeighborStatus.ACTIVE
    last_message_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.vehicle_id, str) or not self.vehicle_id.strip():
            raise InvalidNeighborDataError(
                "vehicle_id must be a non-empty string.", field="vehicle_id"
            )
        if not isinstance(self.last_position, Position2D):
            raise InvalidNeighborDataError(
                f"last_position must be Position2D, got {type(self.last_position).__name__}.",
                field="last_position",
            )
        if (
            not isinstance(self.last_distance_m, (int, float))
            or not math.isfinite(self.last_distance_m)
            or self.last_distance_m < 0.0
        ):
            msg = (
                f"last_distance_m must be a finite non-negative number, got "
                f"{self.last_distance_m}."
            )
            raise InvalidNeighborDataError(msg, field="last_distance_m")
        if (
            not isinstance(self.last_speed_mps, (int, float))
            or not math.isfinite(self.last_speed_mps)
            or self.last_speed_mps < 0.0
        ):
            raise InvalidNeighborDataError(
                f"last_speed_mps must be a finite non-negative number, got {self.last_speed_mps}.",
                field="last_speed_mps",
            )
        if not isinstance(self.last_heading_rad, (int, float)) or not math.isfinite(
            self.last_heading_rad
        ):
            raise InvalidNeighborDataError(
                f"last_heading_rad must be a finite number, got {self.last_heading_rad}.",
                field="last_heading_rad",
            )
        if (
            not isinstance(self.last_seen_timestamp_s, (int, float))
            or not math.isfinite(self.last_seen_timestamp_s)
            or self.last_seen_timestamp_s < 0.0
        ):
            msg = (
                f"last_seen_timestamp_s must be a finite non-negative number, got "
                f"{self.last_seen_timestamp_s}."
            )
            raise InvalidNeighborDataError(msg, field="last_seen_timestamp_s")
        if (
            not isinstance(self.last_heartbeat_timestamp_s, (int, float))
            or not math.isfinite(self.last_heartbeat_timestamp_s)
            or self.last_heartbeat_timestamp_s < 0.0
        ):
            msg = (
                f"last_heartbeat_timestamp_s must be a finite non-negative number, got "
                f"{self.last_heartbeat_timestamp_s}."
            )
            raise InvalidNeighborDataError(msg, field="last_heartbeat_timestamp_s")
        if (
            not isinstance(self.last_sequence_number, int)
            or isinstance(self.last_sequence_number, bool)
            or self.last_sequence_number < 0
        ):
            msg = (
                f"last_sequence_number must be a non-negative integer, got "
                f"{self.last_sequence_number}."
            )
            raise InvalidNeighborDataError(msg, field="last_sequence_number")
        if not isinstance(self.status, NeighborStatus):

            raise InvalidNeighborDataError(f"Invalid status: {self.status}.", field="status")
        if self.last_message_id is not None and (
            not isinstance(self.last_message_id, str) or not self.last_message_id.strip()
        ):
            raise InvalidNeighborDataError(
                "last_message_id must be a non-empty string when provided.",
                field="last_message_id",
            )

        object.__setattr__(self, "last_distance_m", float(self.last_distance_m))
        object.__setattr__(self, "last_speed_mps", float(self.last_speed_mps))
        object.__setattr__(self, "last_heading_rad", float(self.last_heading_rad))
        object.__setattr__(self, "last_seen_timestamp_s", float(self.last_seen_timestamp_s))
        object.__setattr__(
            self, "last_heartbeat_timestamp_s", float(self.last_heartbeat_timestamp_s)
        )

    def time_until_expiration(self, current_time_s: float, timeout_s: float) -> float:
        """Calculate simulation seconds remaining until this neighbor reaches heartbeat timeout."""
        return max(0.0, (self.last_heartbeat_timestamp_s + timeout_s) - current_time_s)

    def to_dict(self) -> dict[str, Any]:
        """Serialize neighbor record to a deterministic JSON-compatible dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "last_position": self.last_position.to_dict(),
            "last_distance_m": round(self.last_distance_m, 4),
            "last_speed_mps": round(self.last_speed_mps, 4),
            "last_heading_rad": round(self.last_heading_rad, 6),
            "last_seen_timestamp_s": round(self.last_seen_timestamp_s, 6),
            "last_heartbeat_timestamp_s": round(self.last_heartbeat_timestamp_s, 6),
            "last_sequence_number": self.last_sequence_number,
            "status": self.status.value,
            "last_message_id": self.last_message_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NeighborRecord":
        """Deserialize neighbor record from dictionary."""
        if not isinstance(data, dict):
            raise InvalidNeighborDataError(
                "NeighborRecord data must be a dictionary.", field="record"
            )
        pos_raw = data.get("last_position")
        if not isinstance(pos_raw, dict) or "x" not in pos_raw or "y" not in pos_raw:
            raise InvalidNeighborDataError(
                "last_position must be a dict containing 'x' and 'y'.",
                field="last_position",
            )
        pos = Position2D(x=pos_raw["x"], y=pos_raw["y"])
        status_raw = data.get("status", NeighborStatus.ACTIVE.value)
        try:
            status = NeighborStatus(status_raw)
        except ValueError as exc:
            raise InvalidNeighborDataError(
                f"Unknown status '{status_raw}'.", field="status"
            ) from exc

        return cls(
            vehicle_id=str(data["vehicle_id"]),
            last_position=pos,
            last_distance_m=data["last_distance_m"],
            last_speed_mps=data["last_speed_mps"],
            last_heading_rad=data["last_heading_rad"],
            last_seen_timestamp_s=data["last_seen_timestamp_s"],
            last_heartbeat_timestamp_s=data["last_heartbeat_timestamp_s"],
            last_sequence_number=data["last_sequence_number"],
            status=status,
            last_message_id=data.get("last_message_id"),
        )


@dataclass(frozen=True)
class NeighborTableSnapshot:
    """Immutable point-in-time snapshot of a vehicle's neighbor table."""

    owner_vehicle_id: str
    timestamp_s: float
    neighbors: dict[str, dict[str, Any]]
    known_neighbor_ids: tuple[str, ...]
    active_neighbor_ids: tuple[str, ...]
    stale_neighbor_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to JSON-compatible dictionary."""
        return {
            "owner_vehicle_id": self.owner_vehicle_id,
            "timestamp_s": round(self.timestamp_s, 6),
            "neighbors": dict(self.neighbors),
            "known_neighbor_ids": list(self.known_neighbor_ids),
            "active_neighbor_ids": list(self.active_neighbor_ids),
            "stale_neighbor_ids": list(self.stale_neighbor_ids),
        }


@dataclass
class NeighborMetrics:
    """Deterministic telemetry counters for neighbor table and heartbeat operations."""

    new_neighbors_discovered: int = 0
    neighbor_records_refreshed: int = 0
    neighbors_marked_stale: int = 0
    neighbors_removed: int = 0
    heartbeats_received: int = 0
    invalid_or_expired_heartbeats_rejected: int = 0
    duplicate_or_out_of_order_rejected: int = 0
    update_cycles_executed: int = 0

    def reset(self) -> None:
        """Reset all metric counters to zero."""
        self.new_neighbors_discovered = 0
        self.neighbor_records_refreshed = 0
        self.neighbors_marked_stale = 0
        self.neighbors_removed = 0
        self.heartbeats_received = 0
        self.invalid_or_expired_heartbeats_rejected = 0
        self.duplicate_or_out_of_order_rejected = 0
        self.update_cycles_executed = 0

    def clone(self) -> "NeighborMetrics":
        """Produce an isolated deep copy for atomic rollback."""
        return NeighborMetrics(
            new_neighbors_discovered=self.new_neighbors_discovered,
            neighbor_records_refreshed=self.neighbor_records_refreshed,
            neighbors_marked_stale=self.neighbors_marked_stale,
            neighbors_removed=self.neighbors_removed,
            heartbeats_received=self.heartbeats_received,
            invalid_or_expired_heartbeats_rejected=self.invalid_or_expired_heartbeats_rejected,
            duplicate_or_out_of_order_rejected=self.duplicate_or_out_of_order_rejected,
            update_cycles_executed=self.update_cycles_executed,
        )

    def to_dict(self) -> dict[str, int]:
        """Convert metrics to dictionary."""
        return {
            "new_neighbors_discovered": self.new_neighbors_discovered,
            "neighbor_records_refreshed": self.neighbor_records_refreshed,
            "neighbors_marked_stale": self.neighbors_marked_stale,
            "neighbors_removed": self.neighbors_removed,
            "heartbeats_received": self.heartbeats_received,
            "invalid_or_expired_heartbeats_rejected": self.invalid_or_expired_heartbeats_rejected,
            "duplicate_or_out_of_order_rejected": self.duplicate_or_out_of_order_rejected,
            "update_cycles_executed": self.update_cycles_executed,
        }


class NeighborTable:
    """Per-vehicle table tracking known communication neighbors and their telemetry state.

    Maintains strict invariants:
    - A vehicle cannot be its own neighbor.
    - Deterministic sorted iteration order.
    - Out-of-order and duplicate messages are rejected.
    - Fresh valid heartbeats restore stale neighbors.
    - Distance is computed from local vehicle position at message reception.
    """

    def __init__(self, owner_vehicle_id: str) -> None:
        """Initialize empty neighbor table for owner vehicle.

        Args:
            owner_vehicle_id: Vehicle ID owning this table.
        """
        if not isinstance(owner_vehicle_id, str) or not owner_vehicle_id.strip():
            raise InvalidNeighborDataError(
                "owner_vehicle_id must be a non-empty string.", field="owner_vehicle_id"
            )
        self.owner_vehicle_id: str = owner_vehicle_id
        self._neighbors: dict[str, NeighborRecord] = {}
        self._processed_message_ids: set[str] = set()

    @property
    def count(self) -> int:
        """Total number of maintained neighbor records."""
        return len(self._neighbors)

    def has_neighbor(self, neighbor_id: str) -> bool:
        """Check whether a neighbor ID is currently maintained in the table."""
        return neighbor_id in self._neighbors

    def get_neighbor(self, neighbor_id: str) -> NeighborRecord:
        """Retrieve the NeighborRecord for a neighbor ID.

        Raises:
            NeighborNotFoundError: If neighbor is not in table.
        """
        if neighbor_id not in self._neighbors:
            raise NeighborNotFoundError(neighbor_id)
        return self._neighbors[neighbor_id]

    def get_all_neighbors(self) -> list[NeighborRecord]:
        """Enumerate all maintained neighbor records in deterministic sorted ID order."""
        return [self._neighbors[nid] for nid in sorted(self._neighbors.keys())]

    def get_active_neighbors(self) -> list[NeighborRecord]:
        """Enumerate active neighbor records in deterministic sorted ID order."""
        return [
            self._neighbors[nid]
            for nid in sorted(self._neighbors.keys())
            if self._neighbors[nid].status == NeighborStatus.ACTIVE
        ]

    def get_stale_neighbors(self) -> list[NeighborRecord]:
        """Enumerate stale neighbor records in deterministic sorted ID order."""
        return [
            self._neighbors[nid]
            for nid in sorted(self._neighbors.keys())
            if self._neighbors[nid].status == NeighborStatus.STALE
        ]

    def get_known_ids(self) -> list[str]:
        """Return deterministic sorted list of all neighbor IDs."""
        return sorted(self._neighbors.keys())

    def add_or_refresh(
        self,
        message: V2VMessagePacket,
        observer_position: Position2D,
        current_time_s: float,
        metrics: Optional[NeighborMetrics] = None,
    ) -> bool:
        """Process a valid received message packet to add or refresh a neighbor record.

        Args:
            message: Validated V2VMessagePacket received from peer.
            observer_position: Current position of the receiving (owner) vehicle.
            current_time_s: Current simulation timestamp.
            metrics: Optional NeighborMetrics counter to update.

        Returns:
            True if the record was successfully added or refreshed; False if rejected.

        Raises:
            SelfNeighborError: If message sender_id matches owner_vehicle_id.
            InvalidNeighborDataError: If message data is invalid.
        """
        if message.sender_id == self.owner_vehicle_id:
            raise SelfNeighborError(self.owner_vehicle_id)

        # Expiry check
        if message.is_expired(current_time_s):
            if metrics:
                metrics.invalid_or_expired_heartbeats_rejected += 1
            return False

        # Duplicate message ID check
        if message.message_id in self._processed_message_ids:
            if metrics:
                metrics.duplicate_or_out_of_order_rejected += 1
            return False

        existing = self._neighbors.get(message.sender_id)
        if existing is not None:
            # Monotonic sequence check: older or duplicate sequence numbers rejected
            if message.sequence_number <= existing.last_sequence_number:
                if metrics:
                    metrics.duplicate_or_out_of_order_rejected += 1
                return False

        # Compute observed distance
        distance_m = observer_position.distance_to(message.sender_position)

        new_record = NeighborRecord(
            vehicle_id=message.sender_id,
            last_position=message.sender_position,
            last_distance_m=distance_m,
            last_speed_mps=message.sender_speed_mps,
            last_heading_rad=message.sender_heading_rad,
            last_seen_timestamp_s=current_time_s,
            last_heartbeat_timestamp_s=message.timestamp_s,
            last_sequence_number=message.sequence_number,
            status=NeighborStatus.ACTIVE,
            last_message_id=message.message_id,
        )

        self._neighbors[message.sender_id] = new_record
        self._processed_message_ids.add(message.message_id)

        if metrics:
            metrics.heartbeats_received += 1
            if existing is None:
                metrics.new_neighbors_discovered += 1
            else:
                metrics.neighbor_records_refreshed += 1

        return True

    def mark_stale(
        self,
        neighbor_id: str,
        metrics: Optional[NeighborMetrics] = None,
    ) -> None:
        """Transition an existing neighbor to STALE status."""
        if neighbor_id not in self._neighbors:
            raise NeighborNotFoundError(neighbor_id)
        rec = self._neighbors[neighbor_id]
        if rec.status != NeighborStatus.STALE:
            updated = NeighborRecord(
                vehicle_id=rec.vehicle_id,
                last_position=rec.last_position,
                last_distance_m=rec.last_distance_m,
                last_speed_mps=rec.last_speed_mps,
                last_heading_rad=rec.last_heading_rad,
                last_seen_timestamp_s=rec.last_seen_timestamp_s,
                last_heartbeat_timestamp_s=rec.last_heartbeat_timestamp_s,
                last_sequence_number=rec.last_sequence_number,
                status=NeighborStatus.STALE,
                last_message_id=rec.last_message_id,
            )
            self._neighbors[neighbor_id] = updated
            if metrics:
                metrics.neighbors_marked_stale += 1

    def remove_neighbor(
        self,
        neighbor_id: str,
        metrics: Optional[NeighborMetrics] = None,
    ) -> Optional[NeighborRecord]:
        """Remove a neighbor record from the table."""
        rec = self._neighbors.pop(neighbor_id, None)
        if rec is not None and metrics:
            metrics.neighbors_removed += 1
        return rec

    def clear(self) -> None:
        """Clear all neighbor records and message tracking."""
        self._neighbors.clear()
        self._processed_message_ids.clear()

    def perform_maintenance(
        self,
        current_time_s: float,
        timeout_s: float,
        grace_period_s: Optional[float] = None,
        policy: StaleNeighborPolicy = StaleNeighborPolicy.STALE_THEN_REMOVE,
        metrics: Optional[NeighborMetrics] = None,
    ) -> None:
        """Process heartbeat timeouts and stale-neighbor removals deterministically.

        Stale condition: current_time_s - last_heartbeat_timestamp_s >= timeout_s - 1e-9.
        Removal condition under STALE_THEN_REMOVE:
            current_time_s - last_heartbeat_timestamp_s >= timeout_s + grace_period_s - 1e-9.
        """
        eps = 1e-9
        to_remove: list[str] = []
        to_stale: list[str] = []

        # Iterate in sorted deterministic order
        for nid in sorted(self._neighbors.keys()):
            rec = self._neighbors[nid]
            elapsed_since_hb = current_time_s - rec.last_heartbeat_timestamp_s

            if policy == StaleNeighborPolicy.REMOVE_IMMEDIATELY:
                if elapsed_since_hb >= (timeout_s - eps):
                    to_remove.append(nid)
            elif policy == StaleNeighborPolicy.STALE_THEN_REMOVE:
                effective_grace = grace_period_s if grace_period_s is not None else 0.0
                if elapsed_since_hb >= (timeout_s + effective_grace - eps):
                    to_remove.append(nid)
                elif elapsed_since_hb >= (timeout_s - eps) and rec.status != NeighborStatus.STALE:
                    to_stale.append(nid)
            elif policy == StaleNeighborPolicy.MARK_STALE:
                if elapsed_since_hb >= (timeout_s - eps) and rec.status != NeighborStatus.STALE:
                    to_stale.append(nid)

        for nid in to_stale:
            self.mark_stale(nid, metrics=metrics)

        for nid in to_remove:
            self.remove_neighbor(nid, metrics=metrics)

    def capture_state(self) -> dict[str, Any]:
        """Capture mutable state for rollback."""
        return {
            "owner_vehicle_id": self.owner_vehicle_id,
            "neighbors": {nid: rec.to_dict() for nid, rec in self._neighbors.items()},
            "processed_message_ids": set(self._processed_message_ids),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from captured rollback dictionary."""
        self.owner_vehicle_id = state["owner_vehicle_id"]
        self._neighbors = {
            nid: NeighborRecord.from_dict(raw) for nid, raw in state["neighbors"].items()
        }
        self._processed_message_ids = set(state["processed_message_ids"])

    def get_snapshot(self, current_time_s: float) -> NeighborTableSnapshot:
        """Construct an immutable point-in-time snapshot."""
        return NeighborTableSnapshot(
            owner_vehicle_id=self.owner_vehicle_id,
            timestamp_s=current_time_s,
            neighbors={nid: self._neighbors[nid].to_dict() for nid in sorted(self._neighbors)},
            known_neighbor_ids=tuple(sorted(self._neighbors.keys())),
            active_neighbor_ids=tuple(
                [
                    nid
                    for nid in sorted(self._neighbors.keys())
                    if self._neighbors[nid].status == NeighborStatus.ACTIVE
                ]
            ),
            stale_neighbor_ids=tuple(
                [
                    nid
                    for nid in sorted(self._neighbors.keys())
                    if self._neighbors[nid].status == NeighborStatus.STALE
                ]
            ),
        )


class NeighborManager:
    """Subsystem managing per-vehicle neighbor tables, message ingestion, and maintenance."""

    def __init__(
        self,
        update_interval_s: float = 0.1,
        heartbeat_timeout_s: float = 0.5,
        stale_grace_period_s: Optional[float] = 1.0,
        stale_policy: StaleNeighborPolicy = StaleNeighborPolicy.STALE_THEN_REMOVE,
    ) -> None:
        """Initialize the neighbor manager.

        Args:
            update_interval_s: Discrete interval between table maintenance cycles.
            heartbeat_timeout_s: Seconds before a neighbor without heartbeat is marked stale.
            stale_grace_period_s: Optional seconds after stale transition before removal.
            stale_policy: Expiration policy (STALE_THEN_REMOVE default).
        """
        self.update_interval_s: float = update_interval_s
        self.heartbeat_timeout_s: float = heartbeat_timeout_s
        self.stale_grace_period_s: Optional[float] = stale_grace_period_s
        self.stale_policy: StaleNeighborPolicy = stale_policy

        self._tables: dict[str, NeighborTable] = {}
        self.metrics: NeighborMetrics = NeighborMetrics()

    def register_participant(self, vehicle_id: str) -> None:
        """Create a neighbor table for a registered vehicle if not already present."""
        if vehicle_id not in self._tables:
            self._tables[vehicle_id] = NeighborTable(owner_vehicle_id=vehicle_id)

    def unregister_participant(self, vehicle_id: str) -> None:
        """Remove a vehicle's neighbor table and clean up references in peer tables."""
        self._tables.pop(vehicle_id, None)
        # Also clean up the unregistered vehicle from other tables
        for table in self._tables.values():
            table.remove_neighbor(vehicle_id)

    def get_table(self, vehicle_id: str) -> NeighborTable:
        """Retrieve the NeighborTable for a vehicle.

        Raises:
            NeighborNotFoundError: If vehicle is not registered.
        """
        if vehicle_id not in self._tables:
            raise NeighborNotFoundError(
                f"No neighbor table for vehicle '{vehicle_id}'.",
                neighbor_id=vehicle_id,
            )
        return self._tables[vehicle_id]

    def has_table(self, vehicle_id: str) -> bool:
        """Check whether a table exists for a vehicle ID."""
        return vehicle_id in self._tables

    def process_inbox(
        self,
        vehicle_id: str,
        messages: list[V2VMessagePacket],
        observer_position: Position2D,
        current_time_s: float,
    ) -> int:
        """Ingest messages from a vehicle's inbox to update its neighbor table.

        Args:
            vehicle_id: Vehicle ID of the table owner.
            messages: List of V2VMessagePackets received in the inbox.
            observer_position: Current position of the receiver.
            current_time_s: Authoritative simulation timestamp.

        Returns:
            Number of successfully added or refreshed neighbor records.
        """
        if vehicle_id not in self._tables:
            return 0

        table = self._tables[vehicle_id]
        accepted = 0
        for msg in messages:
            if table.add_or_refresh(
                message=msg,
                observer_position=observer_position,
                current_time_s=current_time_s,
                metrics=self.metrics,
            ):
                accepted += 1
        return accepted

    def perform_maintenance(self, current_time_s: float) -> None:
        """Execute heartbeat timeout and stale/removal maintenance across all tables."""
        self.metrics.update_cycles_executed += 1
        for vid in sorted(self._tables.keys()):
            self._tables[vid].perform_maintenance(
                current_time_s=current_time_s,
                timeout_s=self.heartbeat_timeout_s,
                grace_period_s=self.stale_grace_period_s,
                policy=self.stale_policy,
                metrics=self.metrics,
            )

    def capture_state(self) -> dict[str, Any]:
        """Capture isolated mutable state of all tables and metrics for rollback."""
        return {
            "tables": {vid: table.capture_state() for vid, table in self._tables.items()},
            "metrics": self.metrics.clone(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore exact state of all tables and metrics from rollback dict."""
        self._tables = {}
        for vid, t_state in state["tables"].items():
            table = NeighborTable(owner_vehicle_id=vid)
            table.restore_state(t_state)
            self._tables[vid] = table
        self.metrics = state["metrics"].clone()

    def reset(self) -> None:
        """Reset all tables and metrics back to empty baseline."""
        for table in self._tables.values():
            table.clear()
        self.metrics.reset()

    def get_snapshot(self, current_time_s: float) -> dict[str, Any]:
        """Generate point-in-time snapshot summary across all neighbor tables."""
        return {
            "tables": {
                vid: self._tables[vid].get_snapshot(current_time_s).to_dict()
                for vid in sorted(self._tables.keys())
            },
            "metrics": self.metrics.to_dict(),
        }
