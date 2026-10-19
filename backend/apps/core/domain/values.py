"""Immutable value types for the AMAPP simulation domain.

All value types are immutable dataclasses (frozen=True) with strict
input validation and zero external scientific dependencies.
"""

import math
from dataclasses import dataclass
from typing import Any

from apps.core.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Position2D:
    """Two-dimensional planar coordinate in meters within the simulation world frame.

    Attributes:
        x: X-coordinate in meters (East / right).
        y: Y-coordinate in meters (North / up).
    """

    x: float
    y: float

    def __post_init__(self) -> None:
        if not isinstance(self.x, (int, float)) or not isinstance(self.y, (int, float)):
            raise DomainValidationError(
                "Position2D coordinates must be numeric.", field="position"
            )
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise DomainValidationError(
                "Position2D coordinates must be finite numbers.", field="position"
            )
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))

    def distance_to(self, other: "Position2D") -> float:
        """Calculate Euclidean distance in meters to another 2D position."""
        if not isinstance(other, Position2D):
            raise DomainValidationError(
                "Cannot compute distance to non-Position2D object.", field="position"
            )
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position2D":
        if not isinstance(data, dict):
            raise DomainValidationError(
                "Position2D data must be a dictionary.", field="position"
            )
        if "x" not in data or "y" not in data:
            raise DomainValidationError(
                "Position2D requires 'x' and 'y' fields.", field="position"
            )
        return cls(x=data["x"], y=data["y"])


@dataclass(frozen=True)
class GeoCoordinate:
    """Geographic WGS84 coordinates for real-world OpenStreetMap alignment.

    Attributes:
        latitude: Latitude in decimal degrees (-90.0 to 90.0).
        longitude: Longitude in decimal degrees (-180.0 to 180.0).
    """

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.latitude, (int, float)) or not isinstance(
            self.longitude, (int, float)
        ):
            raise DomainValidationError(
                "GeoCoordinate values must be numeric.", field="geo_coordinate"
            )
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude):
            raise DomainValidationError(
                "GeoCoordinate values must be finite numbers.", field="geo_coordinate"
            )
        if not -90.0 <= self.latitude <= 90.0:
            raise DomainValidationError(
                f"Latitude {self.latitude} out of bounds [-90.0, 90.0].",
                field="latitude",
            )
        if not -180.0 <= self.longitude <= 180.0:
            raise DomainValidationError(
                f"Longitude {self.longitude} out of bounds [-180.0, 180.0].",
                field="longitude",
            )
        object.__setattr__(self, "latitude", float(self.latitude))
        object.__setattr__(self, "longitude", float(self.longitude))

    def to_dict(self) -> dict[str, float]:
        return {"latitude": self.latitude, "longitude": self.longitude}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeoCoordinate":
        if not isinstance(data, dict):
            raise DomainValidationError(
                "GeoCoordinate data must be a dictionary.", field="geo_coordinate"
            )
        if "latitude" not in data or "longitude" not in data:
            raise DomainValidationError(
                "GeoCoordinate requires 'latitude' and 'longitude' fields.",
                field="geo_coordinate",
            )
        return cls(latitude=data["latitude"], longitude=data["longitude"])


@dataclass(frozen=True)
class Dimensions2D:
    """Physical bounding dimensions (footprint) of an entity in meters.

    Attributes:
        length_m: Longitudinal length in meters (> 0.0).
        width_m: Lateral width in meters (> 0.0).
    """

    length_m: float
    width_m: float

    def __post_init__(self) -> None:
        if not isinstance(self.length_m, (int, float)) or not isinstance(
            self.width_m, (int, float)
        ):
            raise DomainValidationError(
                "Dimensions2D values must be numeric.", field="dimensions"
            )
        if not math.isfinite(self.length_m) or not math.isfinite(self.width_m):
            raise DomainValidationError(
                "Dimensions2D values must be finite numbers.", field="dimensions"
            )
        if self.length_m <= 0.0:
            raise DomainValidationError(
                f"Length must be strictly positive, got {self.length_m}.",
                field="length_m",
            )
        if self.width_m <= 0.0:
            raise DomainValidationError(
                f"Width must be strictly positive, got {self.width_m}.",
                field="width_m",
            )
        object.__setattr__(self, "length_m", float(self.length_m))
        object.__setattr__(self, "width_m", float(self.width_m))

    def to_dict(self) -> dict[str, float]:
        return {"length_m": self.length_m, "width_m": self.width_m}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dimensions2D":
        if not isinstance(data, dict):
            raise DomainValidationError(
                "Dimensions2D data must be a dictionary.", field="dimensions"
            )
        if "length_m" not in data or "width_m" not in data:
            raise DomainValidationError(
                "Dimensions2D requires 'length_m' and 'width_m' fields.",
                field="dimensions",
            )
        return cls(length_m=data["length_m"], width_m=data["width_m"])
