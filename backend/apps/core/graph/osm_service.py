"""High-level service orchestrating OpenStreetMap acquisition, normalization, and fallback.

Coordinates geographic input validation, network acquisition (via OSMnx or custom provider),
graph normalization, and deterministic offline fallback to synthetic city grids.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

import networkx as nx

from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.osm_acquisition import acquire_osm_graph
from apps.core.graph.osm_exceptions import (
    InvalidBoundingBoxError,
    OSMEmptyGraphError,
    OSMImportError,
    OSMNotInstalledError,
    OSMServiceUnavailableError,
    OSMTimeoutError,
)
from apps.core.graph.osm_models import OSMImportConfig, OSMImportResult
from apps.core.graph.osm_normalizer import normalize_osm_graph

DEFAULT_FALLBACK_GRID = CityGridConfig(
    rows=4,
    cols=4,
    spacing_m=100.0,
    speed_limit_mps=13.89,
    lanes=2,
    bidirectional=True,
    signalized_intersections=None,
    seed=42,
)


def import_osm_road_network(
    config: OSMImportConfig,
    acquisition_fn: Optional[Callable[[OSMImportConfig], nx.MultiDiGraph]] = None,
) -> OSMImportResult:
    """Import a road network from OpenStreetMap or fall back to a synthetic grid.

    Args:
        config: Configuration governing geographic bounds, mode, and fallback policy.
        acquisition_fn: Optional override for external acquisition (useful for testing).

    Returns:
        OSMImportResult containing the RoadGraph and structured import metadata.

    Raises:
        InvalidBoundingBoxError: If bounding box coordinates or dimensions are invalid
            (never masked by synthetic fallback).
        OSMNotInstalledError: If OSMnx is missing and allow_fallback is False.
        OSMServiceUnavailableError: If OSM service fails and allow_fallback is False.
        OSMTimeoutError: If OSM service times out and allow_fallback is False.
        OSMEmptyGraphError: If OSM returns no road data and allow_fallback is False.
        OSMImportError: For other unrecoverable import failures when fallback is disabled.
    """
    if not isinstance(config, OSMImportConfig):
        raise ValueError(
            f"config must be an instance of OSMImportConfig, got {type(config).__name__}."
        )

    # Validate bounds explicitly — invalid bounding box must NEVER silently fall back
    if not hasattr(config.bounds, "north"):
        raise InvalidBoundingBoxError("Invalid bounding box object supplied.")

    fn = acquisition_fn if acquisition_fn is not None else acquire_osm_graph

    try:
        raw_graph = fn(config)
        road_graph, skipped = normalize_osm_graph(raw_graph, bounds=config.bounds)

        return OSMImportResult(
            graph=road_graph,
            source_type="osm",
            bounds=config.bounds,
            network_mode=config.network_mode,
            node_count=len(road_graph.nodes()),
            edge_count=len(road_graph.edges()),
            skipped_records=skipped,
            fallback_used=False,
            fallback_reason=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "provider": "OpenStreetMap/Overpass",
                "normalizer": "AMAPPRoadGraphNormalizer",
            },
        )
    except (
        OSMNotInstalledError,
        OSMServiceUnavailableError,
        OSMTimeoutError,
        OSMEmptyGraphError,
        OSMImportError,
    ) as err:
        if not config.allow_fallback:
            raise

        # Generate deterministic synthetic city grid as offline fallback
        fallback_cfg = config.fallback_config or DEFAULT_FALLBACK_GRID
        synth_graph = generate_synthetic_city_grid(fallback_cfg)

        fallback_meta: dict[str, Any] = {
            "original_error_type": type(err).__name__,
            "original_error_message": str(err),
            "fallback_seed": fallback_cfg.seed,
            "grid_dimensions": f"{fallback_cfg.rows}x{fallback_cfg.cols}",
            "spacing_m": fallback_cfg.spacing_m,
        }

        return OSMImportResult(
            graph=synth_graph,
            source_type="synthetic_fallback",
            bounds=config.bounds,
            network_mode=config.network_mode,
            node_count=len(synth_graph.nodes()),
            edge_count=len(synth_graph.edges()),
            skipped_records=0,
            fallback_used=True,
            fallback_reason=f"{type(err).__name__}: {err}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=fallback_meta,
        )
