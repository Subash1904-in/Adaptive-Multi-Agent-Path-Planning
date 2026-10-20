"""Normalization pipeline converting raw OSM network graphs into domain RoadGraph.

Converts NetworkX graphs (MultiDiGraph or DiGraph) obtained from OSMnx or test
fixtures into strictly validated AMAPP RoadNode and RoadEdge domain entities.
"""

import math
from typing import Any, Optional

import networkx as nx

from apps.core.domain.models import RoadEdge, RoadNode
from apps.core.domain.values import GeoCoordinate
from apps.core.graph.osm_exceptions import OSMEmptyGraphError
from apps.core.graph.osm_models import BoundingBox
from apps.core.graph.osm_projector import LocalPlanarProjector
from apps.core.graph.road_graph import RoadGraph

# Highway classification speed limit defaults (in meters per second)
HIGHWAY_DEFAULT_SPEEDS_MPS: dict[str, float] = {
    "motorway": 30.0,        # ~108 km/h
    "motorway_link": 22.22,  # ~80 km/h
    "trunk": 25.0,           # ~90 km/h
    "trunk_link": 19.44,     # ~70 km/h
    "primary": 16.67,        # ~60 km/h
    "primary_link": 13.89,   # ~50 km/h
    "secondary": 13.89,      # ~50 km/h
    "secondary_link": 11.11, # ~40 km/h
    "tertiary": 11.11,       # ~40 km/h
    "tertiary_link": 8.33,   # ~30 km/h
    "residential": 8.33,     # ~30 km/h
    "living_street": 5.56,   # ~20 km/h
    "service": 5.56,         # ~20 km/h
    "unclassified": 8.33,    # ~30 km/h
}

HIGHWAY_DEFAULT_LANES: dict[str, int] = {
    "motorway": 3,
    "trunk": 2,
    "primary": 2,
    "secondary": 1,
    "tertiary": 1,
    "residential": 1,
    "service": 1,
}


def parse_speed_limit(
    data: dict[str, Any],
    highway_type: Optional[str] = None,
    default_speed_mps: float = 13.89,
) -> float:
    """Parse speed limit in meters per second from OSM edge data.

    Supports 'speed_kph', numeric 'maxspeed', string 'maxspeed' with units
    (km/h, mph), and falls back to road classification defaults.
    """
    # 1. Direct speed_kph attribute from OSMnx
    speed_kph = data.get("speed_kph")
    if isinstance(speed_kph, (int, float)) and math.isfinite(speed_kph) and speed_kph > 0.0:
        return round(float(speed_kph) / 3.6, 2)

    # 2. OSM 'maxspeed' tag
    maxspeed = data.get("maxspeed")
    if isinstance(maxspeed, list) and maxspeed:
        maxspeed = maxspeed[0]

    if isinstance(maxspeed, (int, float)) and math.isfinite(maxspeed) and maxspeed > 0.0:
        return round(float(maxspeed) / 3.6, 2)

    if isinstance(maxspeed, str):
        cleaned = maxspeed.strip().lower()
        if "mph" in cleaned:
            parts = cleaned.replace("mph", "").strip().split()
            if parts and parts[0].replace(".", "", 1).isdigit():
                return round(float(parts[0]) * 0.44704, 2)
        elif "km/h" in cleaned or "kph" in cleaned:
            parts = cleaned.replace("km/h", "").replace("kph", "").strip().split()
            if parts and parts[0].replace(".", "", 1).isdigit():
                return round(float(parts[0]) / 3.6, 2)
        elif cleaned.replace(".", "", 1).isdigit():
            val = float(cleaned)
            if val > 0.0:
                return round(val / 3.6, 2)

    # 3. Fallback based on highway type
    if highway_type and highway_type in HIGHWAY_DEFAULT_SPEEDS_MPS:
        return HIGHWAY_DEFAULT_SPEEDS_MPS[highway_type]

    return default_speed_mps


def parse_lanes(
    data: dict[str, Any],
    highway_type: Optional[str] = None,
    default_lanes: int = 1,
) -> int:
    """Parse lane count as an integer >= 1 from OSM edge data."""
    lanes = data.get("lanes")
    if isinstance(lanes, list) and lanes:
        lanes = lanes[0]

    if isinstance(lanes, int) and lanes >= 1:
        return lanes

    if isinstance(lanes, str):
        cleaned = lanes.strip().split(";")[0].split(",")[0]
        if cleaned.isdigit() and int(cleaned) >= 1:
            return int(cleaned)

    if highway_type and highway_type in HIGHWAY_DEFAULT_LANES:
        return HIGHWAY_DEFAULT_LANES[highway_type]

    return default_lanes


def is_oneway(data: dict[str, Any]) -> bool:
    """Determine whether an OSM way is restricted to one-way travel."""
    oneway = data.get("oneway")
    if isinstance(oneway, bool):
        return oneway
    if isinstance(oneway, (int, float)):
        return int(oneway) == 1
    if isinstance(oneway, str):
        return oneway.strip().lower() in {"yes", "true", "1", "-1", "reverse"}
    return False


def normalize_osm_graph(
    source_graph: nx.Graph,
    bounds: BoundingBox,
    projector: Optional[LocalPlanarProjector] = None,
    default_speed_mps: float = 13.89,
    default_lanes: int = 1,
) -> tuple[RoadGraph, int]:
    """Normalize a raw NetworkX graph into an authoritative RoadGraph.

    Args:
        source_graph: Input NetworkX graph (MultiDiGraph or DiGraph).
        bounds: Geographic bounding box of the imported area.
        projector: Optional LocalPlanarProjector; constructed from bounds origin if None.
        default_speed_mps: Fallback speed limit in meters per second.
        default_lanes: Fallback lane count.

    Returns:
        Tuple of (road_graph, skipped_records).

    Raises:
        OSMEmptyGraphError: If no valid nodes could be normalized.
    """
    if projector is None:
        projector = LocalPlanarProjector(bounds.south, bounds.west)

    road_graph = RoadGraph()
    skipped_records = 0

    # -------------------------------------------------------------------------
    # 1. Normalize Nodes
    # -------------------------------------------------------------------------
    for n, data in source_graph.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")

        # Validate coordinate existence and finiteness
        if lat is None or lon is None:
            skipped_records += 1
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            skipped_records += 1
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            skipped_records += 1
            continue
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            skipped_records += 1
            continue

        node_id = f"osm_node_{n}"
        pos = projector.project(float(lat), float(lon))
        geo = GeoCoordinate(latitude=float(lat), longitude=float(lon))

        cleaned_attrs = {
            "osm_id": str(n),
            "street_count": data.get("street_count", 0),
        }

        road_node = RoadNode(
            id=node_id,
            position=pos,
            geo_coordinate=geo,
            attributes=cleaned_attrs,
        )

        try:
            road_graph.add_node(road_node)
        except Exception:
            skipped_records += 1

    if len(road_graph.nodes()) == 0:
        raise OSMEmptyGraphError(
            f"No usable nodes could be normalized within bounding box {bounds.to_dict()}."
        )

    # -------------------------------------------------------------------------
    # 2. Normalize Directed Edges
    # -------------------------------------------------------------------------
    # Support both MultiDiGraph (u, v, key, data) and DiGraph (u, v, data)
    edge_iter = (
        source_graph.edges(keys=True, data=True)
        if source_graph.is_multigraph()
        else (
            (u, v, None, data)
            for u, v, data in source_graph.edges(data=True)
        )
    )

    for u, v, key, data in edge_iter:
        u_id = f"osm_node_{u}"
        v_id = f"osm_node_{v}"

        # Endpoints must exist in normalized graph
        if not road_graph.has_node(u_id) or not road_graph.has_node(v_id):
            skipped_records += 1
            continue

        # Prevent self-loops
        if u_id == v_id:
            skipped_records += 1
            continue

        # Extract attributes
        highway_raw = data.get("highway")
        highway = highway_raw[0] if isinstance(highway_raw, list) and highway_raw else highway_raw
        if not isinstance(highway, str):
            highway = None

        name_raw = data.get("name")
        name = name_raw[0] if isinstance(name_raw, list) and name_raw else name_raw
        if not isinstance(name, str):
            name = None

        speed_mps = parse_speed_limit(
            data,
            highway_type=highway,
            default_speed_mps=default_speed_mps,
        )
        lanes = parse_lanes(data, highway_type=highway, default_lanes=default_lanes)

        # Length in meters
        length_val = data.get("length")
        if isinstance(length_val, (int, float)) and math.isfinite(length_val) and length_val > 0.0:
            length_m = round(float(length_val), 3)
        else:
            node_u = road_graph.get_node(u_id)
            node_v = road_graph.get_node(v_id)
            length_m = round(node_u.position.distance_to(node_v.position), 3)

        if length_m <= 0.0:
            skipped_records += 1
            continue

        oneway = is_oneway(data)
        edge_attrs = {
            "osm_way_id": str(data.get("osmid", "")),
            "highway": highway,
            "oneway": oneway,
        }

        # Deterministic edge ID
        key_suffix = f"_{key}" if key is not None and key != 0 else ""
        forward_edge_id = f"osm_edge_{u}_{v}{key_suffix}"

        # Add forward edge (u -> v)
        if road_graph.has_edge_between(u_id, v_id) or road_graph.has_edge(forward_edge_id):
            # Parallel connection: simple graph preserves primary, skips duplicate
            skipped_records += 1
        else:
            forward_edge = RoadEdge(
                id=forward_edge_id,
                start_node_id=u_id,
                end_node_id=v_id,
                length_m=length_m,
                speed_limit_mps=speed_mps,
                lanes=lanes,
                name=name,
                attributes=edge_attrs,
            )
            road_graph.add_edge(forward_edge)

        # Synthesize reverse edge (v -> u) if two-way and not already present
        if not oneway:
            reverse_edge_id = f"osm_edge_{v}_{u}{key_suffix}"
            if (
                not road_graph.has_edge_between(v_id, u_id)
                and not road_graph.has_edge(reverse_edge_id)
            ):
                rev_attrs = {**edge_attrs, "synthesized_reverse": True}
                reverse_edge = RoadEdge(
                    id=reverse_edge_id,
                    start_node_id=v_id,
                    end_node_id=u_id,
                    length_m=length_m,
                    speed_limit_mps=speed_mps,
                    lanes=lanes,
                    name=name,
                    attributes=rev_attrs,
                )
                road_graph.add_edge(reverse_edge)

    return road_graph, skipped_records
