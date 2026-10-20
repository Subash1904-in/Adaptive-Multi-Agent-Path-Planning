"""Data models, configuration, and result objects for OpenStreetMap import."""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from apps.core.graph.generator import CityGridConfig
from apps.core.graph.osm_exceptions import InvalidBoundingBoxError
from apps.core.graph.road_graph import RoadGraph

SUPPORTED_NETWORK_MODES = frozenset({"drive", "drive_service", "walk", "bike", "all"})


@dataclass(frozen=True)
class BoundingBox:
    """A validated geographic bounding box in WGS84 coordinates.

    Coordinates use standard geographic conventions:
    - Latitude: [-90.0, 90.0] degrees (South to North).
    - Longitude: [-180.0, 180.0] degrees (West to East).

    Invariants enforced:
    - All coordinates must be finite numeric values.
    - north must be strictly greater than south.
    - east must be strictly greater than west.
    - Area span is bounded by safety limits to prevent runaway downloads.
    """

    north: float
    south: float
    east: float
    west: float

    MAX_LAT_SPAN_DEG: ClassVar[float] = 0.25  # ~27.8 km
    MAX_LON_SPAN_DEG: ClassVar[float] = 0.25  # ~20-27 km

    def __post_init__(self) -> None:
        for name, val in [
            ("north", self.north),
            ("south", self.south),
            ("east", self.east),
            ("west", self.west),
        ]:
            if not isinstance(val, (int, float)):
                raise InvalidBoundingBoxError(
                    f"BoundingBox {name} must be a numeric value, got {type(val).__name__}.",
                    field=name,
                )
            if not math.isfinite(val):
                raise InvalidBoundingBoxError(
                    f"BoundingBox {name} must be a finite number, got {val}.",
                    field=name,
                )

        if not (-90.0 <= self.south <= 90.0):
            raise InvalidBoundingBoxError(
                f"BoundingBox south must be within [-90.0, 90.0], got {self.south}.",
                field="south",
            )
        if not (-90.0 <= self.north <= 90.0):
            raise InvalidBoundingBoxError(
                f"BoundingBox north must be within [-90.0, 90.0], got {self.north}.",
                field="north",
            )
        if not (-180.0 <= self.west <= 180.0):
            raise InvalidBoundingBoxError(
                f"BoundingBox west must be within [-180.0, 180.0], got {self.west}.",
                field="west",
            )
        if not (-180.0 <= self.east <= 180.0):
            raise InvalidBoundingBoxError(
                f"BoundingBox east must be within [-180.0, 180.0], got {self.east}.",
                field="east",
            )

        if self.north <= self.south:
            raise InvalidBoundingBoxError(
                f"BoundingBox north ({self.north}) must be greater than south ({self.south}).",
                field="north",
            )
        if self.east <= self.west:
            raise InvalidBoundingBoxError(
                f"BoundingBox east ({self.east}) must be greater than west ({self.west}).",
                field="east",
            )

        lat_span = self.north - self.south
        lon_span = self.east - self.west
        if lat_span > self.MAX_LAT_SPAN_DEG:
            raise InvalidBoundingBoxError(
                f"BoundingBox latitude span ({lat_span:.4f}°) exceeds maximum allowed span "
                f"({self.MAX_LAT_SPAN_DEG}°).",
                field="lat_span",
            )
        if lon_span > self.MAX_LON_SPAN_DEG:
            raise InvalidBoundingBoxError(
                f"BoundingBox longitude span ({lon_span:.4f}°) exceeds maximum allowed span "
                f"({self.MAX_LON_SPAN_DEG}°).",
                field="lon_span",
            )

    @property
    def center_lat(self) -> float:
        """Return the center latitude of the bounding box."""
        return (self.north + self.south) / 2.0

    @property
    def center_lon(self) -> float:
        """Return the center longitude of the bounding box."""
        return (self.east + self.west) / 2.0

    def to_osmnx_bbox(self) -> tuple[float, float, float, float]:
        """Convert to OSMnx 2.x bbox tuple: (left/west, bottom/south, right/east, top/north)."""
        return (self.west, self.south, self.east, self.north)

    def to_dict(self) -> dict[str, float]:
        """Export bounding box coordinates as a dictionary."""
        return {
            "north": self.north,
            "south": self.south,
            "east": self.east,
            "west": self.west,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundingBox":
        """Construct a BoundingBox from a dictionary."""
        if not isinstance(data, dict):
            raise InvalidBoundingBoxError(
                f"Expected dictionary for BoundingBox, got {type(data).__name__}."
            )
        required = {"north", "south", "east", "west"}
        missing = required - set(data.keys())
        if missing:
            raise InvalidBoundingBoxError(
                f"Missing required BoundingBox fields: {sorted(missing)}."
            )
        return cls(
            north=float(data["north"]),
            south=float(data["south"]),
            east=float(data["east"]),
            west=float(data["west"]),
        )


@dataclass(frozen=True)
class OSMImportConfig:
    """Configuration governing the OSM road-network acquisition and normalization."""

    bounds: BoundingBox
    network_mode: str = "drive"
    allow_fallback: bool = False
    fallback_config: Optional[CityGridConfig] = None
    timeout: float = 30.0
    custom_filter: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.bounds, BoundingBox):
            raise InvalidBoundingBoxError(
                f"bounds must be an instance of BoundingBox, got {type(self.bounds).__name__}.",
                field="bounds",
            )
        if (
            not isinstance(self.network_mode, str)
            or self.network_mode not in SUPPORTED_NETWORK_MODES
        ):
            raise ValueError(
                f"Unsupported network_mode '{self.network_mode}'. "
                f"Must be one of {sorted(SUPPORTED_NETWORK_MODES)}."
            )
        if (
            not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or self.timeout <= 0.0
        ):
            raise ValueError(f"timeout must be a positive finite number, got {self.timeout}.")
        if self.fallback_config is not None and not isinstance(
            self.fallback_config, CityGridConfig
        ):
            raise ValueError(
                "fallback_config must be an instance of CityGridConfig, "
                f"got {type(self.fallback_config).__name__}."
            )


@dataclass(frozen=True)
class OSMImportResult:
    """Structured result of an OSM road-network acquisition or synthetic fallback."""

    graph: RoadGraph
    source_type: str  # "osm" | "synthetic_fallback"
    bounds: BoundingBox
    network_mode: str
    node_count: int
    edge_count: int
    skipped_records: int
    fallback_used: bool
    fallback_reason: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize import result metadata (excluding large graph internals)."""
        return {
            "source_type": self.source_type,
            "bounds": self.bounds.to_dict(),
            "network_mode": self.network_mode,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "skipped_records": self.skipped_records,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
