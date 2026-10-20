"""Acquisition adapter for downloading road network data via OSMnx.

Provides defensive optional dependency handling, error classification,
and clean boundary isolation between external HTTP services and internal logic.
"""

from typing import TYPE_CHECKING, Any

from apps.core.graph.osm_exceptions import (
    OSMEmptyGraphError,
    OSMNotInstalledError,
    OSMServiceUnavailableError,
    OSMTimeoutError,
)
from apps.core.graph.osm_models import OSMImportConfig

if TYPE_CHECKING:
    import networkx as nx


def is_osmnx_available() -> bool:
    """Check whether the optional OSMnx library is installed in the current environment."""
    try:
        import osmnx  # noqa: F401
        return True
    except ImportError:
        return False


def acquire_osm_graph(config: OSMImportConfig) -> "nx.MultiDiGraph":
    """Acquire a road network graph from OpenStreetMap via OSMnx.

    Args:
        config: Validated OSM import configuration.

    Returns:
        A NetworkX MultiDiGraph downloaded from OSM.

    Raises:
        OSMNotInstalledError: If osmnx is not installed.
        OSMTimeoutError: If the external Overpass request times out.
        OSMServiceUnavailableError: If the network request fails.
        OSMEmptyGraphError: If no nodes or edges were returned for the bounds.
    """
    if not is_osmnx_available():
        raise OSMNotInstalledError(
            "The 'osmnx' library is not installed in the environment. "
            "Install optional OSM support via 'pip install osmnx'."
        )

    import osmnx as ox

    try:
        # Configure request timeout on OSMnx settings
        ox.settings.timeout = int(config.timeout)

        # OSMnx 2.x expects bbox=(left/west, bottom/south, right/east, top/north)
        bbox = config.bounds.to_osmnx_bbox()

        graph: Any = ox.graph_from_bbox(
            bbox=bbox,
            network_type=config.network_mode,
            simplify=True,
            retain_all=True,
            custom_filter=config.custom_filter,
        )
    except TimeoutError as err:
        raise OSMTimeoutError(
            f"OSM acquisition timed out after {config.timeout}s: {err}"
        ) from err
    except Exception as err:
        err_msg = str(err)
        err_type = type(err).__name__

        # Handle requests or urllib timeout exceptions
        if "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
            raise OSMTimeoutError(
                f"OSM Overpass service timed out after {config.timeout}s: {err_msg}"
            ) from err

        # Handle empty response errors from OSMnx
        if "no data elements" in err_msg.lower() or "empty" in err_msg.lower():
            raise OSMEmptyGraphError(
                f"Overpass API returned no road elements for bounds {config.bounds.to_dict()}."
            ) from err

        # Handle general connection/HTTP failures
        raise OSMServiceUnavailableError(
            f"Failed to acquire OSM road data ({err_type}): {err_msg}"
        ) from err

    if graph is None or len(graph.nodes) == 0:
        raise OSMEmptyGraphError(
            f"Overpass API returned 0 nodes for bounding box {config.bounds.to_dict()}."
        )

    return graph
