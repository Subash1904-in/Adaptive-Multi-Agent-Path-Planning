"""OpenStreetMap (OSM) domain and import exceptions.

Provides a structured exception hierarchy for geographic validation,
network acquisition, optional dependency detection, and graph normalization.
"""

from apps.core.graph.exceptions import GraphException


class OSMImportError(GraphException):
    """Base exception for all OSM import and normalization failures."""


class InvalidBoundingBoxError(OSMImportError):
    """Raised when geographic bounding box coordinates or dimensions are invalid."""

    def __init__(self, message: str, field: str = "bounds") -> None:
        super().__init__(message)
        self.field = field


class OSMNotInstalledError(OSMImportError):
    """Raised when OSMnx optional dependency is requested but not installed."""


class OSMServiceUnavailableError(OSMImportError):
    """Raised when the external Overpass/OSM service is unreachable or errors."""


class OSMTimeoutError(OSMServiceUnavailableError):
    """Raised when an external OSM acquisition request times out."""


class OSMEmptyGraphError(OSMImportError):
    """Raised when an OSM query returns an empty graph with no usable nodes/edges."""


class OSMNormalizationError(OSMImportError):
    """Raised when raw OSM data cannot be normalized into a valid internal RoadGraph."""
