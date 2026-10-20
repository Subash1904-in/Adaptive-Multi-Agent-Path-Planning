"""Comprehensive unit tests for safety geometry, OBB, and SAT overlap detection."""

import math

import pytest

from apps.core.domain.models import Vehicle
from apps.core.domain.values import Dimensions2D, Position2D
from apps.core.safety.exceptions import GeometryValidationError
from apps.core.safety.geometry import (
    OrientedBoundingBox2D,
    check_obb_overlap_sat,
    compute_obb_separation_distance,
    point_to_segment_distance,
)


class TestSafetyGeometryValidation:
    """Tests for input validation and invariants of OrientedBoundingBox2D."""

    def test_valid_obb_construction(self):
        obb = OrientedBoundingBox2D(
            center_x=10.0,
            center_y=20.0,
            length_m=4.5,
            width_m=2.0,
            heading_rad=0.0,
            vehicle_id="veh_1",
        )
        assert obb.center_x == 10.0
        assert obb.center_y == 20.0
        assert obb.length_m == 4.5
        assert obb.width_m == 2.0
        assert obb.heading_rad == 0.0
        assert obb.vehicle_id == "veh_1"
        assert math.isclose(obb.bounding_radius_m, math.hypot(2.25, 1.0))

    def test_rejects_non_finite_coordinates(self):
        with pytest.raises(GeometryValidationError, match="must be finite"):
            OrientedBoundingBox2D(
                center_x=float("nan"), center_y=0.0,
                length_m=4.5, width_m=2.0, heading_rad=0.0,
            )

        with pytest.raises(GeometryValidationError, match="must be finite"):
            OrientedBoundingBox2D(
                center_x=0.0, center_y=float("inf"),
                length_m=4.5, width_m=2.0, heading_rad=0.0,
            )

    def test_rejects_non_positive_dimensions(self):
        with pytest.raises(GeometryValidationError, match="strictly positive"):
            OrientedBoundingBox2D(
                center_x=0.0, center_y=0.0,
                length_m=0.0, width_m=2.0, heading_rad=0.0,
            )

        with pytest.raises(GeometryValidationError, match="strictly positive"):
            OrientedBoundingBox2D(
                center_x=0.0, center_y=0.0,
                length_m=4.5, width_m=-1.0, heading_rad=0.0,
            )

    def test_rejects_non_finite_heading(self):
        with pytest.raises(GeometryValidationError, match="must be finite"):
            OrientedBoundingBox2D(
                center_x=0.0, center_y=0.0,
                length_m=4.5, width_m=2.0, heading_rad=float("nan"),
            )

    def test_from_vehicle_factory(self):
        vehicle = Vehicle(
            id="v_test",
            position=Position2D(x=15.0, y=25.0),
            heading_rad=math.pi / 2,
            dimensions=Dimensions2D(length_m=5.0, width_m=2.2),
        )
        obb = OrientedBoundingBox2D.from_vehicle(vehicle)
        assert obb.center_x == 15.0
        assert obb.center_y == 25.0
        assert obb.length_m == 5.0
        assert obb.width_m == 2.2
        assert obb.heading_rad == math.pi / 2
        assert obb.vehicle_id == "v_test"

    def test_from_vehicle_rejects_non_vehicle(self):
        with pytest.raises(GeometryValidationError, match="Expected Vehicle instance"):
            OrientedBoundingBox2D.from_vehicle("not_a_vehicle")


class TestPointToSegmentDistance:
    """Tests for 2D point to segment distance calculation."""

    def test_point_on_segment(self):
        d = point_to_segment_distance(5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert math.isclose(d, 0.0, abs_tol=1e-7)

    def test_point_perpendicular_to_midpoint(self):
        d = point_to_segment_distance(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        assert math.isclose(d, 3.0, abs_tol=1e-7)

    def test_point_beyond_endpoint_a(self):
        d = point_to_segment_distance(-4.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert math.isclose(d, 4.0, abs_tol=1e-7)

    def test_point_beyond_endpoint_b(self):
        d = point_to_segment_distance(13.0, 4.0, 0.0, 0.0, 10.0, 0.0)
        assert math.isclose(d, 5.0, abs_tol=1e-7)  # 3-4-5 triangle


class TestSATCollisionChecks:
    """Tests for Separating Axis Theorem overlap detection."""

    @staticmethod
    def _make_box(
        x: float, y: float, length: float = 4.0, width: float = 2.0, heading: float = 0.0
    ) -> OrientedBoundingBox2D:
        return OrientedBoundingBox2D(
            center_x=x, center_y=y, length_m=length, width_m=width, heading_rad=heading
        )

    def test_identical_position_boxes_overlap(self):
        box_a = self._make_box(0.0, 0.0)
        box_b = self._make_box(0.0, 0.0)
        assert check_obb_overlap_sat(box_a, box_b) is True
        assert compute_obb_separation_distance(box_a, box_b) == 0.0

    def test_distant_boxes_do_not_overlap(self):
        box_a = self._make_box(0.0, 0.0)
        box_b = self._make_box(100.0, 0.0)
        assert check_obb_overlap_sat(box_a, box_b) is False
        assert compute_obb_separation_distance(box_a, box_b) == 96.0  # 100 - (2 + 2)

    def test_parallel_vehicles_rear_end_overlap(self):
        # Both facing East (heading=0.0). Length=4.0. Front of A is at x=+2. Rear of B is at x=+1.
        box_a = self._make_box(0.0, 0.0)
        box_b = self._make_box(3.0, 0.0)
        assert check_obb_overlap_sat(box_a, box_b) is True
        assert compute_obb_separation_distance(box_a, box_b) == 0.0

    def test_parallel_vehicles_separated_headway(self):
        # Front of A at x=2, rear of B at x=4. Gap is 2.0m.
        box_a = self._make_box(0.0, 0.0)
        box_b = self._make_box(6.0, 0.0)
        assert check_obb_overlap_sat(box_a, box_b) is False
        dist = compute_obb_separation_distance(box_a, box_b)
        assert math.isclose(dist, 2.0, abs_tol=1e-5)

    def test_perpendicular_vehicles_t_bone_collision(self):
        # Box A heading East (0.0) along X-axis. Center at (0, 0), length=4, width=2.
        # Box B heading North (pi/2) along Y-axis. Center at (0, 1), length=4, width=2.
        box_a = self._make_box(0.0, 0.0, heading=0.0)
        box_b = self._make_box(0.0, 1.0, heading=math.pi / 2)
        assert check_obb_overlap_sat(box_a, box_b) is True
        assert compute_obb_separation_distance(box_a, box_b) == 0.0

    def test_perpendicular_vehicles_clearing_intersection(self):
        # Box A at (0, 0), extends X in [-2, 2], Y in [-1, 1].
        # Box B heading North at (0, 5), length=4 (Y in [3, 7]), width=2 (X in [-1, 1]).
        # Gap along Y is 3.0 - 1.0 = 2.0m.
        box_a = self._make_box(0.0, 0.0, heading=0.0)
        box_b = self._make_box(0.0, 5.0, heading=math.pi / 2)
        assert check_obb_overlap_sat(box_a, box_b) is False
        dist = compute_obb_separation_distance(box_a, box_b)
        assert math.isclose(dist, 2.0, abs_tol=1e-5)

    def test_rotated_diagonal_boxes_collision(self):
        # Box A at (0, 0) rotated 45 deg (pi/4).
        # Box B at (2.0, 2.0) rotated 45 deg (pi/4).
        box_a = self._make_box(0.0, 0.0, heading=math.pi / 4)
        box_b = self._make_box(2.0, 2.0, heading=math.pi / 4)
        assert check_obb_overlap_sat(box_a, box_b) is True

    def test_boundary_touching_policy(self):
        # Box A extends X in [-2, 2]. Box B starts at X=2.0 (center at 4.0, length=4.0).
        # Distance along X is exactly 4.0, sum of half lengths is 2.0 + 2.0 = 4.0.
        box_a = self._make_box(0.0, 0.0)
        box_b = self._make_box(4.0, 0.0)

        # When touching_is_overlap is True, boundary touching counts as overlap
        assert check_obb_overlap_sat(box_a, box_b, touching_is_overlap=True) is True
        # When touching_is_overlap is False, strict overlap is required
        assert check_obb_overlap_sat(box_a, box_b, touching_is_overlap=False) is False
