"""Domain exceptions for V2V communication and spatial peer discovery."""

from typing import Any, Optional

from apps.core.domain.exceptions import DomainException


class CommunicationError(DomainException):
    """Base exception for all vehicle-to-vehicle communication subsystem errors."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, field=field)
        self.details: dict[str, Any] = dict(details or {})


class CommunicationValidationError(CommunicationError, ValueError):
    """Raised when message fields, configurations, or parameters fail validation."""

    pass


class UnknownSenderError(CommunicationError, KeyError):
    """Raised when a transmitting vehicle is not registered in the communication network."""

    def __init__(self, sender_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Transmitting vehicle '{sender_id}' is not registered in the network."
        super().__init__(msg, field="sender_id", details={"sender_id": sender_id})
        self.sender_id = sender_id


class UnknownReceiverError(CommunicationError, KeyError):
    """Raised when a unicast target vehicle is not registered in the communication network."""

    def __init__(self, recipient_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Recipient vehicle '{recipient_id}' is not registered in the network."
        super().__init__(msg, field="recipient_id", details={"recipient_id": recipient_id})
        self.recipient_id = recipient_id


class DuplicateRegistrationError(CommunicationError, ValueError):
    """Raised when attempting to register a vehicle that is already registered."""

    def __init__(self, vehicle_id: str, message: Optional[str] = None) -> None:
        msg = (
            message or f"Vehicle '{vehicle_id}' is already registered in the communication network."
        )
        super().__init__(msg, field="vehicle_id", details={"vehicle_id": vehicle_id})
        self.vehicle_id = vehicle_id


class InvalidRangeError(CommunicationValidationError):
    """Raised when communication range is non-positive or non-finite."""

    def __init__(self, range_m: Any, message: Optional[str] = None) -> None:
        msg = message or f"Communication range must be a finite positive number, got {range_m}."
        super().__init__(msg, field="range_m", details={"range_m": range_m})
        self.range_m = range_m


class InvalidBroadcastIntervalError(CommunicationValidationError):
    """Raised when broadcast interval is non-positive or non-finite."""

    def __init__(self, interval_s: Any, message: Optional[str] = None) -> None:
        msg = message or f"Broadcast interval must be a finite positive number, got {interval_s}."
        super().__init__(msg, field="broadcast_interval_s", details={"interval_s": interval_s})
        self.interval_s = interval_s


class ExpiredMessageError(CommunicationError, ValueError):
    """Raised when an expired message is submitted or delivered."""

    def __init__(self, message_id: str, expiry_s: float, current_time_s: float) -> None:
        msg = (
            f"Message '{message_id}' has expired (expiry: {expiry_s:.3f}s <= "
            f"current: {current_time_s:.3f}s)."
        )
        super().__init__(
            msg,
            field="expiry_timestamp_s",
            details={
                "message_id": message_id,
                "expiry_timestamp_s": expiry_s,
                "current_time_s": current_time_s,
            },
        )
        self.message_id = message_id
        self.expiry_s = expiry_s
        self.current_time_s = current_time_s


class MessageSerializationError(CommunicationError, ValueError):
    """Raised when message serialization or deserialization fails due to malformed data."""

    pass


class IncompatibleSnapshotError(CommunicationError, ValueError):
    """Raised when a world snapshot lacks required spatial or entity data for peer discovery."""

    pass


class CommunicationStateError(CommunicationError, RuntimeError):
    """Raised when the communication subsystem is in an invalid state for an operation."""

    pass


class NeighborError(CommunicationError):
    """Base exception for neighbor-management subsystem errors."""

    pass


class SelfNeighborError(NeighborError, ValueError):
    """Raised when a vehicle attempts to record itself as its own neighbor."""

    def __init__(self, vehicle_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Vehicle '{vehicle_id}' cannot be its own neighbor."
        super().__init__(msg, field="vehicle_id", details={"vehicle_id": vehicle_id})
        self.vehicle_id = vehicle_id


class NeighborNotFoundError(NeighborError, KeyError):
    """Raised when a requested neighbor ID does not exist in the neighbor table."""

    def __init__(self, neighbor_id: str, message: Optional[str] = None) -> None:
        msg = message or f"Neighbor '{neighbor_id}' was not found in the neighbor table."
        super().__init__(msg, field="neighbor_id", details={"neighbor_id": neighbor_id})
        self.neighbor_id = neighbor_id


class InvalidNeighborDataError(NeighborError, CommunicationValidationError):
    """Raised when neighbor record data, sequence numbers, or timestamps are invalid."""

    pass


class InvalidHeartbeatTimeoutError(CommunicationValidationError):
    """Raised when heartbeat timeout is non-positive or non-finite."""

    def __init__(self, timeout_s: Any, message: Optional[str] = None) -> None:
        msg = message or f"Heartbeat timeout must be a finite positive number, got {timeout_s}."
        super().__init__(msg, field="heartbeat_timeout_s", details={"timeout_s": timeout_s})
        self.timeout_s = timeout_s


class InvalidUpdateIntervalError(CommunicationValidationError):
    """Raised when neighbor update interval is non-positive or non-finite."""

    def __init__(self, interval_s: Any, message: Optional[str] = None) -> None:
        msg = (
            message
            or f"Neighbor update interval must be a finite positive number, got {interval_s}."
        )
        super().__init__(
            msg, field="neighbor_update_interval_s", details={"interval_s": interval_s}
        )
        self.interval_s = interval_s
