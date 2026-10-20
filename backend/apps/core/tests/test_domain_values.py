"""Unit tests for AMAPP domain value types (Position2D, GeoCoordinate, Dimensions2D)."""

import math

import pytest

from apps.core.domain.exceptions import DomainValidationError
from apps.core.domain.values import Dimensions2D, GeoCoordinate, Position2D


class TestPosition2D:
    """Test suite for planar Position2D value object."""

    def test_valid_construction(self) -> None:
        pos = Position2D(x=10.5, y=-25.0)
        assert pos.x == 10.5
        assert pos.y == -25.0
        assert isinstance(pos.x, float)
        assert isinstance(pos.y, float)

    def test_integer_conversion(self) -> None:
        pos = Position2D(x=10, y=20)
        assert pos.x == 10.0
        assert pos.y == 20.0
        assert isinstance(pos.x, float)

    @pytest.mark.parametrize(
        "invalid_x, invalid_y",
        [
            ("10", 20),
            (10, None),
            ([10], 20),
            ({}, 20),
        ],
    )
    def test_non_numeric_coordinates_rejected(self, invalid_x: object, invalid_y: object) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            Position2D(x=invalid_x, y=invalid_y)  # type: ignore[arg-type]
        assert "must be numeric" in str(exc_info.value)

    @pytest.mark.parametrize(
        "x_val, y_val",
        [
            (float("nan"), 0.0),
            (0.0, float("inf")),
            (float("-inf"), 0.0),
        ],
    )
    def test_non_finite_coordinates_rejected(self, x_val: float, y_val: float) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            Position2D(x=x_val, y=y_val)
        assert "finite numbers" in str(exc_info.value)

    def test_distance_to_calculation(self) -> None:
        p1 = Position2D(x=0.0, y=0.0)
        p2 = Position2D(x=3.0, y=4.0)
        assert math.isclose(p1.distance_to(p2), 5.0)
        assert math.isclose(p2.distance_to(p1), 5.0)

    def test_distance_to_same_point(self) -> None:
        p = Position2D(x=12.5, y=-8.2)
        assert math.isclose(p.distance_to(p), 0.0)

    def test_distance_to_invalid_type_raises(self) -> None:
        p = Position2D(x=0.0, y=0.0)
        with pytest.raises(DomainValidationError):
            p.distance_to((3.0, 4.0))  # type: ignore[arg-type]

    def test_to_dict_and_from_dict(self) -> None:
        p = Position2D(x=15.2, y=-44.8)
        data = p.to_dict()
        assert data == {"x": 15.2, "y": -44.8}
        restored = Position2D.from_dict(data)
        assert restored == p

    def test_from_dict_invalid_data(self) -> None:
        with pytest.raises(DomainValidationError):
            Position2D.from_dict("not-a-dict")  # type: ignore[arg-type]
        with pytest.raises(DomainValidationError):
            Position2D.from_dict({"x": 10.0})


class TestGeoCoordinate:
    """Test suite for WGS84 GeoCoordinate value object."""

    def test_valid_construction(self) -> None:
        coord = GeoCoordinate(latitude=37.7749, longitude=-122.4194)
        assert coord.latitude == 37.7749
        assert coord.longitude == -122.4194

    def test_extreme_valid_bounds(self) -> None:
        c1 = GeoCoordinate(latitude=-90.0, longitude=-180.0)
        c2 = GeoCoordinate(latitude=90.0, longitude=180.0)
        assert c1.latitude == -90.0
        assert c2.longitude == 180.0

    @pytest.mark.parametrize(
        "lat, lon",
        [
            (-90.1, 0.0),
            (90.1, 0.0),
            (0.0, -180.1),
            (0.0, 180.1),
        ],
    )
    def test_out_of_bounds_coordinates_rejected(self, lat: float, lon: float) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            GeoCoordinate(latitude=lat, longitude=lon)
        assert "out of bounds" in str(exc_info.value)

    @pytest.mark.parametrize(
        "lat, lon",
        [
            ("37.7", -122.4),
            (37.7, None),
            (float("nan"), 0.0),
            (0.0, float("inf")),
        ],
    )
    def test_invalid_types_and_non_finite_rejected(self, lat: object, lon: object) -> None:
        with pytest.raises(DomainValidationError):
            GeoCoordinate(latitude=lat, longitude=lon)  # type: ignore[arg-type]

    def test_to_dict_and_from_dict(self) -> None:
        coord = GeoCoordinate(latitude=51.5074, longitude=-0.1278)
        data = coord.to_dict()
        assert data == {"latitude": 51.5074, "longitude": -0.1278}
        restored = GeoCoordinate.from_dict(data)
        assert restored == coord


class TestDimensions2D:
    """Test suite for physical Dimensions2D bounding footprint."""

    def test_valid_dimensions(self) -> None:
        dim = Dimensions2D(length_m=4.8, width_m=1.9)
        assert dim.length_m == 4.8
        assert dim.width_m == 1.9

    @pytest.mark.parametrize(
        "l_val, w_val",
        [
            (0.0, 2.0),
            (-1.0, 2.0),
            (4.5, 0.0),
            (4.5, -0.5),
        ],
    )
    def test_non_positive_dimensions_rejected(self, l_val: float, w_val: float) -> None:
        with pytest.raises(DomainValidationError) as exc_info:
            Dimensions2D(length_m=l_val, width_m=w_val)
        assert "strictly positive" in str(exc_info.value)

    @pytest.mark.parametrize(
        "l_val, w_val",
        [
            ("4.5", 2.0),
            (4.5, None),
            (float("nan"), 2.0),
            (4.5, float("inf")),
        ],
    )
    def test_invalid_types_and_non_finite_rejected(self, l_val: object, w_val: object) -> None:
        with pytest.raises(DomainValidationError):
            Dimensions2D(length_m=l_val, width_m=w_val)  # type: ignore[arg-type]

    def test_to_dict_and_from_dict(self) -> None:
        dim = Dimensions2D(length_m=5.0, width_m=2.2)
        data = dim.to_dict()
        assert data == {"length_m": 5.0, "width_m": 2.2}
        restored = Dimensions2D.from_dict(data)
        assert restored == dim
