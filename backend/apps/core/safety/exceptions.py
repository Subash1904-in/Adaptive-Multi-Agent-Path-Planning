"""Exception hierarchy for the AMAPP safety, collision detection, and avoidance subsystem."""

from typing import Optional


class SafetyError(Exception):
    """Base exception for all safety-related domain and operational errors."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidSafetyConfigError(SafetyError):
    """Raised when safety configuration parameters fail validation invariants."""

    def __init__(
        self,
        message: str,
        param_name: Optional[str] = None,
        param_value: Optional[object] = None,
    ) -> None:
        super().__init__(message, details={"param_name": param_name, "param_value": param_value})
        self.param_name = param_name
        self.param_value = param_value


class GeometryValidationError(SafetyError):
    """Raised when vehicle bounding box geometry or coordinates fail validation."""

    def __init__(
        self,
        message: str,
        vehicle_id: Optional[str] = None,
        field_name: Optional[str] = None,
    ) -> None:
        super().__init__(message, details={"vehicle_id": vehicle_id, "field_name": field_name})
        self.vehicle_id = vehicle_id
        self.field_name = field_name


class ControlApplicationError(SafetyError):
    """Raised when safety control overrides cannot be safely applied to vehicle kinematics."""

    def __init__(
        self,
        message: str,
        vehicle_id: Optional[str] = None,
        target_accel: Optional[float] = None,
    ) -> None:
        super().__init__(message, details={"vehicle_id": vehicle_id, "target_accel": target_accel})
        self.vehicle_id = vehicle_id
        self.target_accel = target_accel
