"""Domain exceptions for the emergency vehicle priority and corridor subsystem."""

from typing import Optional


class EmergencyError(Exception):
    """Base exception for all emergency priority domain errors."""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or "EMERGENCY_ERROR"


class InvalidEmergencyTypeError(EmergencyError):
    """Raised when an unapproved or malformed emergency vehicle type is encountered."""

    def __init__(self, message: str, emergency_type: Optional[str] = None) -> None:
        super().__init__(message, code="INVALID_EMERGENCY_TYPE")
        self.emergency_type = emergency_type


class InvalidEmergencyStateError(EmergencyError):
    """Raised when an illegal transition or invalid state is attempted."""

    def __init__(
        self,
        message: str,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
    ) -> None:
        super().__init__(message, code="INVALID_EMERGENCY_STATE")
        self.from_state = from_state
        self.to_state = to_state


class DuplicateEmergencyActivationError(EmergencyError):
    """Raised when an emergency vehicle is activated while already in an active emergency."""

    def __init__(self, message: str, vehicle_id: Optional[str] = None) -> None:
        super().__init__(message, code="DUPLICATE_EMERGENCY_ACTIVATION")
        self.vehicle_id = vehicle_id


class EmergencyVehicleNotFoundError(EmergencyError):
    """Raised when a referenced emergency vehicle does not exist in the registry."""

    def __init__(self, message: str, vehicle_id: Optional[str] = None) -> None:
        super().__init__(message, code="EMERGENCY_VEHICLE_NOT_FOUND")
        self.vehicle_id = vehicle_id


class CorridorPlanningError(EmergencyError):
    """Raised when an emergency corridor cannot be planned or resolved."""

    def __init__(self, message: str, corridor_id: Optional[str] = None) -> None:
        super().__init__(message, code="CORRIDOR_PLANNING_ERROR")
        self.corridor_id = corridor_id


class UnreachableEmergencyDestinationError(CorridorPlanningError):
    """Raised when an emergency vehicle destination is unreachable in the road graph."""

    def __init__(
        self,
        message: str,
        vehicle_id: Optional[str] = None,
        destination_node_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, corridor_id=None)
        self.code = "UNREACHABLE_EMERGENCY_DESTINATION"
        self.vehicle_id = vehicle_id
        self.destination_node_id = destination_node_id


class CorridorReservationConflictError(EmergencyError):
    """Raised when conflicting corridor reservations cannot be safely reconciled."""

    def __init__(
        self,
        message: str,
        edge_or_node_id: Optional[str] = None,
        active_request_id: Optional[str] = None,
        competing_request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, code="CORRIDOR_RESERVATION_CONFLICT")
        self.edge_or_node_id = edge_or_node_id
        self.active_request_id = active_request_id
        self.competing_request_id = competing_request_id


class SignalPriorityError(EmergencyError):
    """Raised when a signal priority operation violates safety constraints or fails."""

    def __init__(self, message: str, signal_id: Optional[str] = None) -> None:
        super().__init__(message, code="SIGNAL_PRIORITY_ERROR")
        self.signal_id = signal_id


class InvalidYieldRequestError(EmergencyError):
    """Raised when a yield request is malformed, targets a non-existent agent, or is illegal."""

    def __init__(self, message: str, target_vehicle_id: Optional[str] = None) -> None:
        super().__init__(message, code="INVALID_YIELD_REQUEST")
        self.target_vehicle_id = target_vehicle_id
