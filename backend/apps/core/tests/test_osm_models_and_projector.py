"""Unit tests for OSM bounding box, projection, and configuration models."""

import math

import pytest

from apps.core.graph.osm_exceptions import InvalidBoundingBoxError
from apps.core.graph.osm_models import BoundingBox, OSMImportConfig, OSMImportResult
from apps.core.graph.osm_projector import EARTH_RADIUS_M, LocalPlanarProjector
from apps.core.graph.road_graph import RoadGraph


class TestBoundingBox:
    """Test validation and behavior of BoundingBox value object."""

    def test_valid_bounding_box(self) -> None:
        """A valid bounding box constructs cleanly with correct properties."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        assert bbox.north == 37.78
        assert bbox.south == 37.77
        assert bbox.east == -122.41
        assert bbox.west == -122.42
        assert bbox.center_lat == pytest.approx(37.775, rel=1e-5)
        assert bbox.center_lon == pytest.approx(-122.415, rel=1e-5)

    def test_to_osmnx_bbox(self) -> None:
        """to_osmnx_bbox converts to (west, south, east, north) for OSMnx 2.x."""
        bbox = BoundingBox(north=12.98, south=12.97, east=77.60, west=77.59)
        assert bbox.to_osmnx_bbox() == (77.59, 12.97, 77.60, 12.98)

    def test_to_dict_and_from_dict(self) -> None:
        """Serialization round-trip for BoundingBox."""
        bbox = BoundingBox(north=51.51, south=51.50, east=-0.11, west=-0.12)
        data = bbox.to_dict()
        restored = BoundingBox.from_dict(data)
        assert restored == bbox

    def test_from_dict_missing_fields_raises(self) -> None:
        """from_dict raises InvalidBoundingBoxError when required fields are missing."""
        with pytest.raises(InvalidBoundingBoxError, match="Missing required"):
            BoundingBox.from_dict({"north": 10.0, "south": 9.0})

    def test_from_dict_non_dict_raises(self) -> None:
        """from_dict raises when input is not a dictionary."""
        with pytest.raises(InvalidBoundingBoxError, match="Expected dictionary"):
            BoundingBox.from_dict(["north", 10.0])  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "north,south,east,west",
        [
            ("37.8", 37.7, -122.4, -122.5),
            (37.8, None, -122.4, -122.5),
            (37.8, 37.7, [1], -122.5),
        ],
    )
    def test_non_numeric_coordinates_rejected(
        self, north: float, south: float, east: float, west: float
    ) -> None:
        """Non-numeric coordinates raise InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="numeric"):
            BoundingBox(north=north, south=south, east=east, west=west)

    @pytest.mark.parametrize(
        "north,south,east,west",
        [
            (float("nan"), 37.7, -122.4, -122.5),
            (37.8, float("inf"), -122.4, -122.5),
            (37.8, 37.7, float("-inf"), -122.5),
        ],
    )
    def test_non_finite_coordinates_rejected(
        self, north: float, south: float, east: float, west: float
    ) -> None:
        """NaN or infinite coordinates raise InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="finite"):
            BoundingBox(north=north, south=south, east=east, west=west)

    @pytest.mark.parametrize(
        "north,south,east,west",
        [
            (90.1, 80.0, 10.0, 5.0),
            (80.0, -90.1, 10.0, 5.0),
            (10.0, 5.0, 180.1, 10.0),
            (10.0, 5.0, 10.0, -180.1),
        ],
    )
    def test_out_of_range_coordinates_rejected(
        self, north: float, south: float, east: float, west: float
    ) -> None:
        """Coordinates outside valid WGS84 ranges [-90, 90] and [-180, 180] raise."""
        with pytest.raises(InvalidBoundingBoxError, match="within"):
            BoundingBox(north=north, south=south, east=east, west=west)

    def test_reversed_north_south_rejected(self) -> None:
        """north <= south raises InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="must be greater than south"):
            BoundingBox(north=37.7, south=37.8, east=-122.4, west=-122.5)

    def test_equal_north_south_rejected(self) -> None:
        """north == south raises InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="must be greater than south"):
            BoundingBox(north=37.7, south=37.7, east=-122.4, west=-122.5)

    def test_reversed_east_west_rejected(self) -> None:
        """east <= west raises InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="must be greater than west"):
            BoundingBox(north=37.8, south=37.7, east=-122.5, west=-122.4)

    def test_excessively_large_latitude_span_rejected(self) -> None:
        """Latitude span exceeding MAX_LAT_SPAN_DEG raises InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="latitude span .* exceeds"):
            BoundingBox(north=38.1, south=37.7, east=-122.4, west=-122.5)

    def test_excessively_large_longitude_span_rejected(self) -> None:
        """Longitude span exceeding MAX_LON_SPAN_DEG raises InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError, match="longitude span .* exceeds"):
            BoundingBox(north=37.8, south=37.7, east=-122.0, west=-122.3)


class TestLocalPlanarProjector:
    """Test LocalPlanarProjector geographic-to-Cartesian projection."""

    def test_origin_projects_to_zero(self) -> None:
        """The origin coordinate projects to (0.0, 0.0) meters."""
        projector = LocalPlanarProjector(origin_lat=37.77, origin_lon=-122.42)
        pos = projector.project(lat=37.77, lon=-122.42)
        assert pos.x == 0.0
        assert pos.y == 0.0

    def test_displacement_projections(self) -> None:
        """Displacements northward and eastward produce positive (x, y) in meters."""
        projector = LocalPlanarProjector(origin_lat=0.0, origin_lon=0.0)
        # 1 degree North at equator is approximately (pi / 180) * 6,371,000 = 111,194.9 m
        pos = projector.project(lat=0.01, lon=0.01)
        expected_y = (math.pi / 180.0) * 0.01 * EARTH_RADIUS_M
        assert pos.y == pytest.approx(expected_y, rel=1e-3)
        assert pos.x > 0.0
        assert pos.y > 0.0

    def test_unproject_round_trip(self) -> None:
        """Unproject accurately restores the original geographic coordinate."""
        projector = LocalPlanarProjector(origin_lat=37.77, origin_lon=-122.42)
        target_lat = 37.785
        target_lon = -122.405

        pos = projector.project(target_lat, target_lon)
        restored = projector.unproject(pos)

        assert restored.latitude == pytest.approx(target_lat, abs=1e-5)
        assert restored.longitude == pytest.approx(target_lon, abs=1e-5)

    def test_invalid_projector_origin_raises(self) -> None:
        """Invalid origin coordinates raise InvalidBoundingBoxError."""
        with pytest.raises(InvalidBoundingBoxError):
            LocalPlanarProjector(origin_lat=95.0, origin_lon=0.0)
        with pytest.raises(InvalidBoundingBoxError):
            LocalPlanarProjector(origin_lat=float("nan"), origin_lon=0.0)

    def test_project_invalid_coordinates_raises(self) -> None:
        """Non-finite or out-of-bounds coordinates raise ValueError."""
        projector = LocalPlanarProjector(origin_lat=0.0, origin_lon=0.0)
        with pytest.raises(ValueError, match="finite"):
            projector.project(float("inf"), 0.0)
        with pytest.raises(ValueError, match="out of bounds"):
            projector.project(95.0, 0.0)

    def test_unproject_invalid_type_raises(self) -> None:
        """Passing non-Position2D to unproject raises ValueError."""
        projector = LocalPlanarProjector(origin_lat=0.0, origin_lon=0.0)
        with pytest.raises(ValueError, match="Expected Position2D"):
            projector.unproject({"x": 10.0, "y": 20.0})  # type: ignore[arg-type]


class TestOSMImportConfigAndResult:
    """Test configuration and result container objects."""

    def test_valid_config(self) -> None:
        """A valid OSMImportConfig constructs cleanly."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        cfg = OSMImportConfig(bounds=bbox, network_mode="drive", allow_fallback=True)
        assert cfg.bounds == bbox
        assert cfg.network_mode == "drive"
        assert cfg.allow_fallback is True
        assert cfg.timeout == 30.0

    def test_invalid_network_mode_raises(self) -> None:
        """Unsupported network_mode raises ValueError."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        with pytest.raises(ValueError, match="Unsupported network_mode"):
            OSMImportConfig(bounds=bbox, network_mode="submarine")

    def test_invalid_timeout_raises(self) -> None:
        """Non-positive timeout raises ValueError."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        with pytest.raises(ValueError, match="timeout must be a positive finite number"):
            OSMImportConfig(bounds=bbox, timeout=-5.0)

    def test_invalid_fallback_config_raises(self) -> None:
        """Non-CityGridConfig fallback_config raises ValueError."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        with pytest.raises(ValueError, match="fallback_config must be an instance"):
            OSMImportConfig(bounds=bbox, fallback_config={"rows": 4})  # type: ignore[arg-type]

    def test_result_to_dict(self) -> None:
        """OSMImportResult serializes metadata to dictionary."""
        bbox = BoundingBox(north=37.78, south=37.77, east=-122.41, west=-122.42)
        graph = RoadGraph()
        result = OSMImportResult(
            graph=graph,
            source_type="osm",
            bounds=bbox,
            network_mode="drive",
            node_count=0,
            edge_count=0,
            skipped_records=2,
            fallback_used=False,
            fallback_reason=None,
            metadata={"test_key": "test_val"},
        )
        d = result.to_dict()
        assert d["source_type"] == "osm"
        assert d["bounds"]["north"] == 37.78
        assert d["skipped_records"] == 2
        assert d["fallback_used"] is False
        assert d["metadata"] == {"test_key": "test_val"}
