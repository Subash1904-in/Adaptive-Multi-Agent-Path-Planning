"""Periodic broadcast scheduler for vehicle status messages using simulation clock time."""

import math
from typing import TYPE_CHECKING, Any, Optional, Union

from apps.core.communication.exceptions import InvalidBroadcastIntervalError
from apps.core.communication.models import V2VMessagePacket
from apps.core.communication.protocol import create_status_message

if TYPE_CHECKING:
    from apps.core.domain.models import Vehicle
    from apps.core.kinematics.vehicle_agent import VehicleAgent
    from apps.core.simulation.models import VehicleSnapshot


class BroadcastScheduler:
    """Manages periodic dispatch of vehicle status messages synchronized with SimulationClock.

    Guarantees:
    - Pure simulation-time scheduling with zero wall-clock dependencies or background threads.
    - Monotonically increasing per-vehicle sequence numbers starting at 0.
    - Exactly one broadcast per scheduled interval boundary.
    - Deterministic scheduling independent of agent iteration order.
    - Safe state capture and restoration for atomic rollback.
    """

    def __init__(
        self,
        broadcast_interval_s: float = 0.1,
        message_ttl_s: Optional[float] = 1.0,
    ) -> None:
        """Initialize the broadcast scheduler.

        Args:
            broadcast_interval_s: Period in seconds between consecutive broadcasts (> 0.0).
            message_ttl_s: Optional time-to-live in seconds for generated packets.

        Raises:
            InvalidBroadcastIntervalError: If interval is non-positive or non-finite.
        """
        if (
            not isinstance(broadcast_interval_s, (int, float))
            or not math.isfinite(broadcast_interval_s)
            or broadcast_interval_s <= 0.0
        ):
            raise InvalidBroadcastIntervalError(broadcast_interval_s)

        self.broadcast_interval_s: float = float(broadcast_interval_s)
        self.message_ttl_s: Optional[float] = (
            float(message_ttl_s) if message_ttl_s is not None else None
        )

        # vehicle_id -> simulation time when next broadcast is due
        self._next_broadcast_time: dict[str, float] = {}

        # vehicle_id -> last emitted sequence number
        self._sequence_numbers: dict[str, int] = {}

    def is_broadcast_due(self, vehicle_id: str, current_time_s: float) -> bool:
        """Evaluate whether a periodic status broadcast is due for the specified vehicle.

        Args:
            vehicle_id: Vehicle identifier.
            current_time_s: Current simulation timestamp from authoritative clock.

        Returns:
            True if current_time_s >= next scheduled broadcast boundary; False otherwise.
        """
        # If never scheduled, the first broadcast is due immediately at current_time_s
        if vehicle_id not in self._next_broadcast_time:
            return True

        # Use small numerical tolerance (1e-9) to handle discrete float precision
        return current_time_s >= (self._next_broadcast_time[vehicle_id] - 1e-9)

    def create_broadcast(
        self,
        vehicle: Union["Vehicle", "VehicleAgent", "VehicleSnapshot"],
        current_time_s: float,
        custom_payload: Optional[dict[str, Any]] = None,
    ) -> V2VMessagePacket:
        """Generate a periodic status message, increment sequence counter, and advance schedule.

        Args:
            vehicle: Vehicle entity, VehicleAgent, or VehicleSnapshot.
            current_time_s: Current authoritative simulation time.
            custom_payload: Optional user-defined dictionary for the message payload.

        Returns:
            A newly constructed, immutable V2VMessagePacket.
        """
        if hasattr(vehicle, "vehicle"):
            vid = vehicle.vehicle.id
        elif hasattr(vehicle, "vehicle_id"):
            vid = vehicle.vehicle_id
        elif hasattr(vehicle, "id"):
            vid = vehicle.id
        else:
            raise TypeError(f"Unsupported vehicle type: {type(vehicle).__name__}.")

        # Increment monotonic sequence counter
        seq = self._sequence_numbers.get(vid, -1) + 1
        self._sequence_numbers[vid] = seq

        # Advance next scheduled broadcast time
        self._next_broadcast_time[vid] = current_time_s + self.broadcast_interval_s

        return create_status_message(
            vehicle=vehicle,
            sequence_number=seq,
            timestamp_s=current_time_s,
            ttl_s=self.message_ttl_s,
            custom_payload=custom_payload,
        )

    def capture_state(self) -> dict[str, Any]:
        """Capture mutable scheduler state for atomic simulation rollback."""
        return {
            "next_broadcast_time": dict(self._next_broadcast_time),
            "sequence_numbers": dict(self._sequence_numbers),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore scheduler state from a captured rollback snapshot."""
        self._next_broadcast_time = dict(state.get("next_broadcast_time", {}))
        self._sequence_numbers = dict(state.get("sequence_numbers", {}))

    def reset(self) -> None:
        """Reset all scheduler state back to initial baseline."""
        self._next_broadcast_time.clear()
        self._sequence_numbers.clear()
