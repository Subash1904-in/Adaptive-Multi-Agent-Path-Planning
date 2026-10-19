"""Domain-level exceptions for AMAPP simulation domain models."""

from typing import Optional


class DomainException(Exception):
    """Base exception for all AMAPP simulation domain errors."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        if self.field:
            return f"[{self.field}] {self.message}"
        return self.message


class DomainValidationError(DomainException, ValueError):
    """Raised when a domain model or value object fails invariant validation."""

    pass


class SerializationError(DomainException, ValueError):
    """Raised when serialization or deserialization fails due to malformed data."""

    pass
