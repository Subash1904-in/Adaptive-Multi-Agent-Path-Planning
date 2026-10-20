"""V2V communication protocol, peer discovery, and networking package."""

from apps.core.communication.discovery import SpatialPeerDiscovery, brute_force_reference
from apps.core.communication.exceptions import (
    CommunicationError,
    CommunicationStateError,
    CommunicationValidationError,
    DuplicateRegistrationError,
    ExpiredMessageError,
    IncompatibleSnapshotError,
    InvalidBroadcastIntervalError,
    InvalidHeartbeatTimeoutError,
    InvalidNeighborDataError,
    InvalidRangeError,
    InvalidUpdateIntervalError,
    MessageSerializationError,
    NeighborError,
    NeighborNotFoundError,
    SelfNeighborError,
    UnknownReceiverError,
    UnknownSenderError,
)
from apps.core.communication.metrics import CommunicationMetrics
from apps.core.communication.models import (
    CommunicationConfig,
    CommunicationSnapshot,
    DeliveryPolicy,
    DropReason,
    NeighborStatus,
    StaleNeighborPolicy,
    V2VMessagePacket,
    VehicleStatusPayload,
)
from apps.core.communication.neighbors import (
    NeighborManager,
    NeighborMetrics,
    NeighborRecord,
    NeighborTable,
    NeighborTableSnapshot,
)
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.communication.protocol import (
    create_status_message,
    deserialize_message,
    serialize_message,
)
from apps.core.communication.scheduler import BroadcastScheduler

__all__ = [
    "BroadcastScheduler",
    "CommunicationConfig",
    "CommunicationError",
    "CommunicationMetrics",
    "CommunicationSnapshot",
    "CommunicationStateError",
    "CommunicationValidationError",
    "DeliveryPolicy",
    "DropReason",
    "DuplicateRegistrationError",
    "ExpiredMessageError",
    "IncompatibleSnapshotError",
    "InvalidBroadcastIntervalError",
    "InvalidHeartbeatTimeoutError",
    "InvalidNeighborDataError",
    "InvalidRangeError",
    "InvalidUpdateIntervalError",
    "MessageSerializationError",
    "NeighborError",
    "NeighborManager",
    "NeighborMetrics",
    "NeighborNotFoundError",
    "NeighborRecord",
    "NeighborStatus",
    "NeighborTable",
    "NeighborTableSnapshot",
    "SelfNeighborError",
    "SimulatedCommunicationNetwork",
    "SpatialPeerDiscovery",
    "StaleNeighborPolicy",
    "UnknownReceiverError",
    "UnknownSenderError",
    "V2VMessagePacket",
    "VehicleStatusPayload",
    "brute_force_reference",
    "create_status_message",
    "deserialize_message",
    "serialize_message",
]

