"""Unit tests for the OSM graph normalization pipeline."""

import networkx as nx
import pytest

from apps.core.domain.values import GeoCoordinate, Position2D
from apps.core.graph.osm_exceptions import OSMEmptyGraphError
from apps.core.graph.osm_models import BoundingBox
from apps.core.graph.osm_normalizer import (
    HIGHWAY_DEFAULT_SPEEDS_MPS,
    normalize_osm_graph,
    parse_lanes,
    parse_speed_limit,
)


@pytest.fixture
def sample_bounds() -> BoundingBox:
    """Standard bounding box centered in a sample city area."""
    return BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)


@pytest.fixture
def sample_multigraph() -> nx.MultiDiGraph:
    """Fixture creating a small 4-node OSM-like MultiDiGraph."""
    G = nx.MultiDiGraph()
    # Add 4 nodes forming a square
    G.add_node(101, y=37.770, x=-122.420, street_count=2)
    G.add_node(102, y=37.770, x=-122.415, street_count=3)
    G.add_node(103, y=37.775, x=-122.420, street_count=3)
    G.add_node(104, y=37.775, x=-122.415, street_count=2)

    # Directed one-way edge 101 -> 102
    G.add_edge(
        101,
        102,
        key=0,
        osmid=1001,
        highway="primary",
        name="Market Street",
        length=440.0,
        maxspeed="50 km/h",
        lanes=2,
        oneway=True,
    )

    # Two-way edge 101 <-> 103 (OSMnx provides both directions)
    G.add_edge(
        101,
        103,
        key=0,
        osmid=1002,
        highway="residential",
        name="Mission Street",
        length=556.0,
        maxspeed="30",
        lanes=1,
        oneway=False,
    )
    G.add_edge(
        103,
        101,
        key=0,
        osmid=1002,
        highway="residential",
        name="Mission Street",
        length=556.0,
        maxspeed="30",
        lanes=1,
        oneway=False,
    )

    # Two-way edge 102 -> 104 without explicit reverse edge in source
    G.add_edge(
        102,
        104,
        key=0,
        osmid=1003,
        highway="secondary",
        name="7th Street",
        length=556.0,
        maxspeed="25 mph",
        lanes="2",
        oneway=False,
    )

    return G


class TestOSMNodeNormalization:
    """Test node conversion and geometric projection during normalization."""

    def test_normalize_valid_nodes(
        self, sample_bounds: BoundingBox, sample_multigraph: nx.MultiDiGraph
    ) -> None:
        """Valid source nodes are converted into RoadNode domain entities."""
        road_graph, skipped = normalize_osm_graph(sample_multigraph, sample_bounds)

        assert len(road_graph.nodes()) == 4
        assert road_graph.has_node("osm_node_101")
        assert road_graph.has_node("osm_node_102")

        node_101 = road_graph.get_node("osm_node_101")
        assert isinstance(node_101.position, Position2D)
        assert isinstance(node_101.geo_coordinate, GeoCoordinate)
        assert node_101.geo_coordinate.latitude == 37.770
        assert node_101.geo_coordinate.longitude == -122.420
        # Southwest origin check: node 101 is at south/west, so position is (0.0, 0.0)
        assert node_101.position.x == 0.0
        assert node_101.position.y == 0.0

    def test_malformed_nodes_skipped(self, sample_bounds: BoundingBox) -> None:
        """Nodes with missing, non-finite, or out-of-bound coords are skipped."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.770, x=-122.420)  # valid
        G.add_node(2, y=None, x=-122.415)    # missing lat
        G.add_node(3, y=37.775, x=float("inf"))  # non-finite lon
        G.add_node(4, y=95.0, x=-122.415)    # out of bounds lat

        road_graph, skipped = normalize_osm_graph(G, sample_bounds)
        assert len(road_graph.nodes()) == 1
        assert road_graph.has_node("osm_node_1")
        assert skipped == 3

    def test_empty_graph_raises_error(self, sample_bounds: BoundingBox) -> None:
        """An empty source graph raises OSMEmptyGraphError."""
        G = nx.MultiDiGraph()
        with pytest.raises(OSMEmptyGraphError, match="No usable nodes"):
            normalize_osm_graph(G, sample_bounds)


class TestOSMEdgeNormalization:
    """Test directed edge conversion, attributes, and topology."""

    def test_oneway_and_twoway_edges(
        self, sample_bounds: BoundingBox, sample_multigraph: nx.MultiDiGraph
    ) -> None:
        """Oneway edges produce single directed edges; twoway produce opposing edges."""
        road_graph, skipped = normalize_osm_graph(sample_multigraph, sample_bounds)

        # 101 -> 102 was oneway: forward edge exists, reverse does NOT
        assert road_graph.has_edge_between("osm_node_101", "osm_node_102")
        assert not road_graph.has_edge_between("osm_node_102", "osm_node_101")

        # 101 <-> 103 was bidirectional: both directions exist
        assert road_graph.has_edge_between("osm_node_101", "osm_node_103")
        assert road_graph.has_edge_between("osm_node_103", "osm_node_101")

        # 102 <-> 104 had only forward edge in source, normalizer synthesized reverse
        assert road_graph.has_edge_between("osm_node_102", "osm_node_104")
        assert road_graph.has_edge_between("osm_node_104", "osm_node_102")

    def test_edge_attribute_parsing(
        self, sample_bounds: BoundingBox, sample_multigraph: nx.MultiDiGraph
    ) -> None:
        """Edge attributes (speed limit, lanes, name, length) are accurately parsed."""
        road_graph, _ = normalize_osm_graph(sample_multigraph, sample_bounds)

        edge_market = road_graph.get_edge("osm_edge_101_102")
        assert edge_market.name == "Market Street"
        assert edge_market.lanes == 2
        assert edge_market.length_m == 440.0
        # "50 km/h" -> 50 / 3.6 = 13.89 m/s
        assert edge_market.speed_limit_mps == pytest.approx(13.89, rel=1e-2)

        # "25 mph" on 102 -> 104: 25 * 0.44704 = 11.18 m/s
        edge_7th = road_graph.get_edge("osm_edge_102_104")
        assert edge_7th.speed_limit_mps == pytest.approx(11.18, rel=1e-2)

    def test_missing_endpoints_skipped(self, sample_bounds: BoundingBox) -> None:
        """Edges referencing nonexistent endpoint nodes are skipped."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.770, x=-122.420)
        G.add_node(2, y=37.775, x=-122.420)
        # Edge to missing node 999
        G.add_edge(1, 999, key=0, length=100.0, oneway=True)

        road_graph, skipped = normalize_osm_graph(G, sample_bounds)
        assert len(road_graph.nodes()) == 2
        assert len(road_graph.edges()) == 0
        # 1 uninitialized node (nx automatically adds node 999 with no coords) + 1 edge
        assert skipped == 2

    def test_self_loops_skipped(self, sample_bounds: BoundingBox) -> None:
        """Self-loop edges (u == v) are skipped."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.770, x=-122.420)
        G.add_edge(1, 1, key=0, length=10.0, oneway=True)

        road_graph, skipped = normalize_osm_graph(G, sample_bounds)
        assert len(road_graph.edges()) == 0
        assert skipped == 1

    def test_parallel_edges_skipped(self, sample_bounds: BoundingBox) -> None:
        """Parallel edges between same endpoints are skipped to maintain simple DiGraph."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.770, x=-122.420)
        G.add_node(2, y=37.775, x=-122.420)
        # Add primary edge
        G.add_edge(1, 2, key=0, length=100.0, oneway=True)
        # Add parallel edge
        G.add_edge(1, 2, key=1, length=105.0, oneway=True)

        road_graph, skipped = normalize_osm_graph(G, sample_bounds)
        assert len(road_graph.edges()) == 1
        assert skipped == 1


class TestAttributeParsers:
    """Test parse_speed_limit and parse_lanes helper functions."""

    def test_parse_speed_limit_units(self) -> None:
        """Speed limits in km/h, mph, and numeric strings are converted to m/s."""
        assert parse_speed_limit({"speed_kph": 60}) == pytest.approx(16.67, rel=1e-2)
        assert parse_speed_limit({"maxspeed": "60 km/h"}) == pytest.approx(16.67, rel=1e-2)
        assert parse_speed_limit({"maxspeed": "40 mph"}) == pytest.approx(17.88, rel=1e-2)
        assert parse_speed_limit({"maxspeed": "50"}) == pytest.approx(13.89, rel=1e-2)
        assert parse_speed_limit({"maxspeed": ["50", "40"]}) == pytest.approx(13.89, rel=1e-2)

    def test_parse_speed_limit_fallbacks(self) -> None:
        """Missing speed limit falls back to highway table or default."""
        expected_motorway = HIGHWAY_DEFAULT_SPEEDS_MPS["motorway"]
        expected_residential = HIGHWAY_DEFAULT_SPEEDS_MPS["residential"]
        assert parse_speed_limit({}, highway_type="motorway") == expected_motorway
        assert parse_speed_limit({}, highway_type="residential") == expected_residential
        assert parse_speed_limit({}, highway_type="unknown_type", default_speed_mps=15.0) == 15.0

    def test_parse_lanes(self) -> None:
        """Lanes are parsed from integers, strings, lists, or highway fallbacks."""
        assert parse_lanes({"lanes": 3}) == 3
        assert parse_lanes({"lanes": "2"}) == 2
        assert parse_lanes({"lanes": "3;2"}) == 3
        assert parse_lanes({"lanes": ["4", "2"]}) == 4
        assert parse_lanes({}, highway_type="motorway") == 3
        assert parse_lanes({}, highway_type="unknown_type", default_lanes=1) == 1

    def test_calculated_length_fallback(self, sample_bounds: BoundingBox) -> None:
        """If source edge lacks length, normalizer computes projected Euclidean length."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=37.770, x=-122.420)
        G.add_node(2, y=37.770, x=-122.410)  # ~880m East
        # Missing 'length' key
        G.add_edge(1, 2, key=0, oneway=True)

        road_graph, _ = normalize_osm_graph(G, sample_bounds)
        edge = road_graph.get_edge("osm_edge_1_2")
        assert edge.length_m > 800.0
        assert edge.length_m < 950.0
