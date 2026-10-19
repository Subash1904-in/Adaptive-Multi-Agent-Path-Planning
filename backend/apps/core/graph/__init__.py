"""AMAPP Road Graph and City Network Package.

Provides the RoadGraph directed graph abstraction, synthetic city grid generator,
and topological validation tools.
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
from apps.core.graph.road_graph import RoadGraph

__all__ = [
    # Graph Core
    "RoadGraph",
    # Generator
    "CityGridConfig",
    "generate_synthetic_city_grid",
    # Exceptions
    "GraphException",
    "GraphValidationError",
    "NodeNotFoundError",
    "EdgeNotFoundError",
    "DuplicateEntityError",
]
