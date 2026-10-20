"""AMAPP Road Graph and City Network Package.

Provides the RoadGraph directed graph abstraction, synthetic city grid generator,
OpenStreetMap (OSM) road-network acquisition, normalization, and topological validation tools.
"""

from apps.core.graph.exceptions import (
    DuplicateEntityError,
    EdgeNotFoundError,
    GraphException,
    GraphValidationError,
    NodeNotFoundError,
)
from apps.core.graph.generator import (
    CityGridConfig,
    generate_synthetic_city_grid,
)
from apps.core.graph.osm_acquisition import (
    acquire_osm_graph,
    is_osmnx_available,
)
from apps.core.graph.osm_exceptions import (
    InvalidBoundingBoxError,
    OSMEmptyGraphError,
    OSMImportError,
    OSMNormalizationError,
    OSMNotInstalledError,
    OSMServiceUnavailableError,
    OSMTimeoutError,
)
from apps.core.graph.osm_models import (
    BoundingBox,
    OSMImportConfig,
    OSMImportResult,
)
from apps.core.graph.osm_normalizer import (
    HIGHWAY_DEFAULT_LANES,
    HIGHWAY_DEFAULT_SPEEDS_MPS,
    normalize_osm_graph,
    parse_lanes,
    parse_speed_limit,
)
from apps.core.graph.osm_projector import (
    EARTH_RADIUS_M,
    LocalPlanarProjector,
)
from apps.core.graph.osm_service import (
    DEFAULT_FALLBACK_GRID,
    import_osm_road_network,
)
from apps.core.graph.road_graph import RoadGraph

__all__ = [
    # Graph Core
    "RoadGraph",
    # Generator
    "CityGridConfig",
    "generate_synthetic_city_grid",
    # OSM Models & Config
    "BoundingBox",
    "OSMImportConfig",
    "OSMImportResult",
    "DEFAULT_FALLBACK_GRID",
    # OSM Projection & Normalization
    "LocalPlanarProjector",
    "EARTH_RADIUS_M",
    "normalize_osm_graph",
    "parse_speed_limit",
    "parse_lanes",
    "HIGHWAY_DEFAULT_SPEEDS_MPS",
    "HIGHWAY_DEFAULT_LANES",
    # OSM Acquisition & Service
    "is_osmnx_available",
    "acquire_osm_graph",
    "import_osm_road_network",
    # Exceptions
    "GraphException",
    "GraphValidationError",
    "NodeNotFoundError",
    "EdgeNotFoundError",
    "DuplicateEntityError",
    "OSMImportError",
    "InvalidBoundingBoxError",
    "OSMNotInstalledError",
    "OSMServiceUnavailableError",
    "OSMTimeoutError",
    "OSMEmptyGraphError",
    "OSMNormalizationError",
]
