"""Unit tests for high-level OSM import service, error classification, and offline fallback."""

from unittest.mock import patch

import networkx as nx
import pytest

from apps.core.graph.generator import CityGridConfig
from apps.core.graph.osm_acquisition import acquire_osm_graph, is_osmnx_available
from apps.core.graph.osm_exceptions import (
    InvalidBoundingBoxError,
    OSMEmptyGraphError,
    OSMNotInstalledError,
    OSMServiceUnavailableError,
    OSMTimeoutError,
)
from apps.core.graph.osm_models import BoundingBox, OSMImportConfig
from apps.core.graph.osm_service import import_osm_road_network


@pytest.fixture
def valid_bounds() -> BoundingBox:
    """Standard valid bounding box."""
    return BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)


@pytest.fixture
def mock_osm_multigraph() -> nx.MultiDiGraph:
    """Mock raw OSMnx MultiDiGraph fixture."""
    G = nx.MultiDiGraph()
    G.add_node(1, y=37.770, x=-122.420)
    G.add_node(2, y=37.775, x=-122.415)
    G.add_edge(1, 2, key=0, length=200.0, maxspeed="50", lanes=2, oneway=True)
    return G


class TestOSMImportServiceSuccessful:
    """Test successful acquisition and normalization path."""

    def test_successful_import(
        self, valid_bounds: BoundingBox, mock_osm_multigraph: nx.MultiDiGraph
    ) -> None:
        """When acquisition succeeds, import returns OSM-sourced result."""
        config = OSMImportConfig(bounds=valid_bounds, network_mode="drive", allow_fallback=False)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            return mock_osm_multigraph

        result = import_osm_road_network(config, acquisition_fn=mock_acquire)

        assert result.source_type == "osm"
        assert result.fallback_used is False
        assert result.fallback_reason is None
        assert result.node_count == 2
        assert result.edge_count == 1
        assert result.graph.has_node("osm_node_1")
        assert result.graph.has_edge("osm_edge_1_2")


class TestOSMFallbackBehavior:
    """Test deterministic offline fallback when acquisition fails or dependency missing."""

    def test_missing_osmnx_with_fallback_enabled(self, valid_bounds: BoundingBox) -> None:
        """Missing OSMnx with allow_fallback=True returns synthetic grid."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=True)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMNotInstalledError("OSMnx is not installed.")

        result = import_osm_road_network(config, acquisition_fn=mock_acquire)

        assert result.source_type == "synthetic_fallback"
        assert result.fallback_used is True
        assert "OSMNotInstalledError" in (result.fallback_reason or "")
        assert result.node_count == 16  # default 4x4 grid
        assert len(result.graph.nodes()) == 16

    def test_missing_osmnx_with_fallback_disabled_raises(
        self, valid_bounds: BoundingBox
    ) -> None:
        """Missing OSMnx with allow_fallback=False raises OSMNotInstalledError."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=False)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMNotInstalledError("OSMnx is not installed.")

        with pytest.raises(OSMNotInstalledError, match="not installed"):
            import_osm_road_network(config, acquisition_fn=mock_acquire)

    def test_service_unavailable_with_fallback_enabled(self, valid_bounds: BoundingBox) -> None:
        """Network failure with allow_fallback=True falls back to synthetic city."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=True)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMServiceUnavailableError("Overpass connection refused.")

        result = import_osm_road_network(config, acquisition_fn=mock_acquire)

        assert result.source_type == "synthetic_fallback"
        assert result.fallback_used is True
        assert "OSMServiceUnavailableError" in (result.fallback_reason or "")

    def test_service_unavailable_with_fallback_disabled_raises(
        self, valid_bounds: BoundingBox
    ) -> None:
        """Network failure with allow_fallback=False raises OSMServiceUnavailableError."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=False)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMServiceUnavailableError("Overpass connection refused.")

        with pytest.raises(OSMServiceUnavailableError, match="refused"):
            import_osm_road_network(config, acquisition_fn=mock_acquire)

    def test_timeout_with_fallback_enabled(self, valid_bounds: BoundingBox) -> None:
        """Timeout with allow_fallback=True falls back to synthetic city."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=True)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMTimeoutError("Overpass request timed out after 30s.")

        result = import_osm_road_network(config, acquisition_fn=mock_acquire)

        assert result.source_type == "synthetic_fallback"
        assert result.fallback_used is True
        assert "OSMTimeoutError" in (result.fallback_reason or "")

    def test_timeout_with_fallback_disabled_raises(self, valid_bounds: BoundingBox) -> None:
        """Timeout with allow_fallback=False raises OSMTimeoutError."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=False)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMTimeoutError("Overpass request timed out after 30s.")

        with pytest.raises(OSMTimeoutError, match="timed out"):
            import_osm_road_network(config, acquisition_fn=mock_acquire)

    def test_empty_graph_with_fallback_enabled(self, valid_bounds: BoundingBox) -> None:
        """Empty graph with allow_fallback=True falls back to synthetic city."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=True)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMEmptyGraphError("No road elements returned.")

        result = import_osm_road_network(config, acquisition_fn=mock_acquire)

        assert result.source_type == "synthetic_fallback"
        assert result.fallback_used is True
        assert "OSMEmptyGraphError" in (result.fallback_reason or "")

    def test_empty_graph_with_fallback_disabled_raises(
        self, valid_bounds: BoundingBox
    ) -> None:
        """Empty graph with allow_fallback=False raises OSMEmptyGraphError."""
        config = OSMImportConfig(bounds=valid_bounds, allow_fallback=False)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMEmptyGraphError("No road elements returned.")

        with pytest.raises(OSMEmptyGraphError, match="No road elements"):
            import_osm_road_network(config, acquisition_fn=mock_acquire)

    def test_invalid_bounds_never_disguised_by_fallback(self) -> None:
        """Invalid bounds raise InvalidBoundingBoxError even if allow_fallback=True."""
        with pytest.raises(InvalidBoundingBoxError):
            BoundingBox(north=37.7, south=37.8, east=-122.4, west=-122.5)

    def test_fallback_determinism(self, valid_bounds: BoundingBox) -> None:
        """Repeated fallback generation produces identical graph topology."""
        cfg = OSMImportConfig(bounds=valid_bounds, allow_fallback=True)

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMServiceUnavailableError("Service down")

        res1 = import_osm_road_network(cfg, acquisition_fn=mock_acquire)
        res2 = import_osm_road_network(cfg, acquisition_fn=mock_acquire)

        assert res1.graph.node_ids() == res2.graph.node_ids()
        assert res1.graph.edge_ids() == res2.graph.edge_ids()

    def test_custom_fallback_config_respected(self, valid_bounds: BoundingBox) -> None:
        """Custom fallback_config dimensions and parameters are respected."""
        custom_fallback = CityGridConfig(rows=3, cols=5, spacing_m=80.0, seed=99)
        cfg = OSMImportConfig(
            bounds=valid_bounds,
            allow_fallback=True,
            fallback_config=custom_fallback,
        )

        def mock_acquire(_cfg: OSMImportConfig) -> nx.MultiDiGraph:
            raise OSMServiceUnavailableError("Service down")

        result = import_osm_road_network(cfg, acquisition_fn=mock_acquire)
        assert result.node_count == 15
        assert len(result.graph.nodes()) == 15
        assert result.metadata["grid_dimensions"] == "3x5"
        assert result.metadata["fallback_seed"] == 99


class TestOSMAcquisitionModule:
    """Test acquire_osm_graph error classification with mocked external calls."""

    def test_is_osmnx_available_boolean(self) -> None:
        """is_osmnx_available returns a boolean."""
        res = is_osmnx_available()
        assert isinstance(res, bool)

    def test_acquire_osm_graph_when_not_installed_raises(
        self, valid_bounds: BoundingBox
    ) -> None:
        """acquire_osm_graph raises OSMNotInstalledError if is_osmnx_available is False."""
        cfg = OSMImportConfig(bounds=valid_bounds)
        with patch("apps.core.graph.osm_acquisition.is_osmnx_available", return_value=False):
            with pytest.raises(OSMNotInstalledError, match="not installed"):
                acquire_osm_graph(cfg)

    def test_acquire_osm_graph_timeout_error_classified(
        self, valid_bounds: BoundingBox
    ) -> None:
        """TimeoutError from osmnx is classified as OSMTimeoutError."""
        cfg = OSMImportConfig(bounds=valid_bounds)
        with patch("osmnx.graph_from_bbox", side_effect=TimeoutError("Connection timed out")):
            with pytest.raises(OSMTimeoutError, match="timed out"):
                acquire_osm_graph(cfg)

    def test_acquire_osm_graph_network_error_classified(
        self, valid_bounds: BoundingBox
    ) -> None:
        """General network exception is classified as OSMServiceUnavailableError."""
        cfg = OSMImportConfig(bounds=valid_bounds)
        with patch("osmnx.graph_from_bbox", side_effect=ConnectionError("Host unreachable")):
            with pytest.raises(OSMServiceUnavailableError, match="Failed to acquire"):
                acquire_osm_graph(cfg)

    def test_acquire_osm_graph_empty_response_raises(
        self, valid_bounds: BoundingBox
    ) -> None:
        """Empty graph returned by OSMnx raises OSMEmptyGraphError."""
        cfg = OSMImportConfig(bounds=valid_bounds)
        empty_g = nx.MultiDiGraph()
        with patch("osmnx.graph_from_bbox", return_value=empty_g):
            with pytest.raises(OSMEmptyGraphError, match="0 nodes"):
                acquire_osm_graph(cfg)
