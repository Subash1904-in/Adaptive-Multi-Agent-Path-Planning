"""Geometric primitives, Oriented Bounding Box (OBB), and SAT overlap detection.

Provides 100% deterministic 2D oriented bounding box calculations for vehicles,
Separating Axis Theorem (SAT) collision detection, exact polygon separation distances,
and squared-distance broadphase filtering.
"""

import math
from dataclasses import dataclass
from typing import Any, Optional

from apps.core.domain.models import Vehicle
from apps.core.domain.values import Dimensions2D, Position2D
from apps.core.safety.exceptions import GeometryValidationError

EPSILON: float = 1e-7


def _validate_finite(value: float, name: str, vehicle_id: Optional[str] = None) -> float:
    """Validate that a numeric parameter is finite."""
    if not isinstance(value, (int, float)):
        raise GeometryValidationError(
            f"Expected numeric value for '{name}', got {type(value).__name__}.",
            vehicle_id=vehicle_id,
            field_name=name,
        )
    if not math.isfinite(value):
        raise GeometryValidationError(
            f"Parameter '{name}' must be finite, got {value}.",
            vehicle_id=vehicle_id,
            field_name=name,
        )
    return float(value)


def _validate_positive(value: float, name: str, vehicle_id: Optional[str] = None) -> float:
    """Validate that a dimension is strictly positive and finite."""
    val = _validate_finite(value, name, vehicle_id)
    if val <= 0.0:
        raise GeometryValidationError(
            f"Dimension '{name}' must be strictly positive (> 0.0), got {val}.",
            vehicle_id=vehicle_id,
            field_name=name,
        )
    return val


def point_to_segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Calculate the minimum Euclidean distance from point P to line segment AB.

    Args:
        px, py: Coordinates of point P.
        ax, ay: Coordinates of segment endpoint A.
        bx, by: Coordinates of segment endpoint B.

    Returns:
        Minimum Euclidean distance in meters.
    """
    dx = bx - ax
    dy = by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay)

    # Project point onto segment line parameter t in [0.0, 1.0]
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    t_clamped = max(0.0, min(1.0, t))
    closest_x = ax + t_clamped * dx
    closest_y = ay + t_clamped * dy
    return math.hypot(px - closest_x, py - closest_y)


@dataclass(frozen=True)
class OrientedBoundingBox2D:
    """Oriented bounding rectangle for a vehicle in planar simulation coordinates.

    Attributes:
        center_x: Longitudinal/lateral center X coordinate in meters.
        center_y: Longitudinal/lateral center Y coordinate in meters.
        length_m: Total vehicle longitudinal length in meters (> 0.0).
        width_m: Total vehicle lateral width in meters (> 0.0).
        heading_rad: Directional heading in radians [0, 2*pi).
        vehicle_id: Optional associated vehicle identifier.
    """

    center_x: float
    center_y: float
    length_m: float
    width_m: float
    heading_rad: float
    vehicle_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Enforce finite numeric coordinates and strictly positive dimensions."""
        cx = _validate_finite(self.center_x, "center_x", self.vehicle_id)
        cy = _validate_finite(self.center_y, "center_y", self.vehicle_id)
        l_m = _validate_positive(self.length_m, "length_m", self.vehicle_id)
        w_m = _validate_positive(self.width_m, "width_m", self.vehicle_id)
        h_rad = _validate_finite(self.heading_rad, "heading_rad", self.vehicle_id)

        object.__setattr__(self, "center_x", cx)
        object.__setattr__(self, "center_y", cy)
        object.__setattr__(self, "length_m", l_m)
        object.__setattr__(self, "width_m", w_m)
        object.__setattr__(self, "heading_rad", h_rad)

        # Precompute immutable geometric vectors and vertices
        cos_h = math.cos(h_rad)
        sin_h = math.sin(h_rad)
        f_vec = (cos_h, sin_h)
        l_vec = (-sin_h, cos_h)
        object.__setattr__(self, "_forward_unit_vector", f_vec)
        object.__setattr__(self, "_lateral_unit_vector", l_vec)
        object.__setattr__(self, "_bounding_radius_m", math.hypot(l_m / 2.0, w_m / 2.0))

        hl = l_m / 2.0
        hw = w_m / 2.0
        fx, fy = f_vec
        lx, ly = l_vec
        v0 = (cx + hl * fx + hw * lx, cy + hl * fy + hw * ly)
        v1 = (cx - hl * fx + hw * lx, cy - hl * fy + hw * ly)
        v2 = (cx - hl * fx - hw * lx, cy - hl * fy - hw * ly)
        v3 = (cx + hl * fx - hw * lx, cy + hl * fy - hw * ly)
        object.__setattr__(self, "_vertices", (v0, v1, v2, v3))

    @property
    def bounding_radius_m(self) -> float:
        """Radius of the circumscribed circle enclosing the bounding box in meters."""
        return self._bounding_radius_m

    @property
    def forward_unit_vector(self) -> tuple[float, float]:
        """Unit vector along vehicle longitudinal heading (cos(heading), sin(heading))."""
        return self._forward_unit_vector

    @property
    def lateral_unit_vector(self) -> tuple[float, float]:
        """Unit vector along vehicle lateral axis (-sin(heading), cos(heading))."""
        return self._lateral_unit_vector

    def get_vertices(self) -> list[tuple[float, float]]:
        """Compute the 4 polygon vertices in counter-clockwise order in world meters.

        Returns:
            List of 4 (x, y) tuples: [front_left, rear_left, rear_right, front_right].
        """
        return list(self._vertices)

    @classmethod
    def from_vehicle(cls, vehicle: Vehicle) -> "OrientedBoundingBox2D":
        """Construct an OrientedBoundingBox2D from an authoritative Vehicle domain entity.

        Args:
            vehicle: Authoritative Vehicle entity.

        Returns:
            OrientedBoundingBox2D matching vehicle position, dimensions, and heading.

        Raises:
            GeometryValidationError: If vehicle attributes are missing or invalid.
        """
        if not isinstance(vehicle, Vehicle):
            raise GeometryValidationError(
                f"Expected Vehicle instance, got {type(vehicle).__name__}."
            )
        pos = vehicle.position
        if not isinstance(pos, Position2D):
            raise GeometryValidationError(
                f"Vehicle {vehicle.id} has invalid position {pos}.",
                vehicle_id=vehicle.id,
                field_name="position",
            )
        dims = vehicle.dimensions
        if not isinstance(dims, Dimensions2D):
            dims = Dimensions2D(length_m=4.5, width_m=2.0)

        return cls(
            center_x=pos.x,
            center_y=pos.y,
            length_m=dims.length_m,
            width_m=dims.width_m,
            heading_rad=vehicle.heading_rad,
            vehicle_id=vehicle.id,
        )

    @classmethod
    def from_pedestrian(
        cls,
        pedestrian: Any,
        length_m: float = 0.6,
        width_m: float = 0.6,
    ) -> "OrientedBoundingBox2D":
        """Construct an OrientedBoundingBox2D from a pedestrian agent entity.

        Args:
            pedestrian: PedestrianAgent or compatible entity.
            length_m: Default longitudinal depth if not configured on agent.
            width_m: Default lateral width if not configured on agent.

        Returns:
            OrientedBoundingBox2D matching pedestrian position, dimensions, and heading.
        """
        pos = pedestrian.position
        cx = pos.x if hasattr(pos, "x") else float(pos[0])
        cy = pos.y if hasattr(pos, "y") else float(pos[1])
        heading = getattr(pedestrian, "heading_rad", 0.0)
        cfg = getattr(pedestrian, "config", None)
        l_m = getattr(cfg, "length_m", length_m) if cfg is not None else length_m
        w_m = getattr(cfg, "width_m", width_m) if cfg is not None else width_m
        pid = getattr(pedestrian, "pedestrian_id", getattr(pedestrian, "id", "pedestrian"))

        return cls(
            center_x=cx,
            center_y=cy,
            length_m=l_m,
            width_m=w_m,
            heading_rad=heading,
            vehicle_id=pid,
        )


def check_obb_overlap_sat(
    box_a: OrientedBoundingBox2D,
    box_b: OrientedBoundingBox2D,
    touching_is_overlap: bool = True,
) -> bool:
    """Test geometric overlap between two 2D oriented bounding boxes using SAT.

    Separating Axis Theorem evaluates the 4 normal axes defined by the box edges:
    2 axes from box_a and 2 axes from box_b.

    Boundary-touching policy:
    - If touching_is_overlap is True (default), boxes whose boundaries touch
      within numerical tolerance (interval gap <= 1e-7) are reported as overlapping.
    - If touching_is_overlap is False, strict overlap (gap < -1e-7) is required.

    Args:
        box_a: First oriented bounding box.
        box_b: Second oriented bounding box.
        touching_is_overlap: Whether boundary contact is treated as collision overlap.

    Returns:
        True if bounding envelopes overlap, False if a separating axis exists.
    """
    # Broadphase bounding-circle filter using squared distance
    dx = box_b.center_x - box_a.center_x
    dy = box_b.center_y - box_a.center_y
    center_dist_sq = dx * dx + dy * dy
    r_sum = box_a.bounding_radius_m + box_b.bounding_radius_m
    if center_dist_sq > (r_sum * r_sum + EPSILON):
        return False

    axes = [
        box_a.forward_unit_vector,
        box_a.lateral_unit_vector,
        box_b.forward_unit_vector,
        box_b.lateral_unit_vector,
    ]

    tolerance = EPSILON if touching_is_overlap else -EPSILON

    hl_a = box_a.length_m / 2.0
    hw_a = box_a.width_m / 2.0
    fa_x, fa_y = box_a.forward_unit_vector
    la_x, la_y = box_a.lateral_unit_vector

    hl_b = box_b.length_m / 2.0
    hw_b = box_b.width_m / 2.0
    fb_x, fb_y = box_b.forward_unit_vector
    lb_x, lb_y = box_b.lateral_unit_vector

    for ax, ay in axes:
        # Distance between box centers projected onto axis
        proj_dist = abs(dx * ax + dy * ay)

        # Projected half-extent of Box A on axis
        r_a = hl_a * abs(fa_x * ax + fa_y * ay) + hw_a * abs(la_x * ax + la_y * ay)

        # Projected half-extent of Box B on axis
        r_b = hl_b * abs(fb_x * ax + fb_y * ay) + hw_b * abs(lb_x * ax + lb_y * ay)

        # Projected interval gap: positive means separating gap
        gap = proj_dist - (r_a + r_b)

        if gap > tolerance:
            # Separating axis found: boxes do not collide
            return False

    return True


def compute_obb_separation_distance(
    box_a: OrientedBoundingBox2D,
    box_b: OrientedBoundingBox2D,
    touching_is_overlap: bool = True,
) -> float:
    """Calculate the minimum Euclidean distance between two oriented bounding boxes in meters.

    If boxes overlap according to SAT, returns 0.0.
    Otherwise, evaluates exact minimum distance between vertices and edges of both boxes.

    Args:
        box_a: First oriented bounding box.
        box_b: Second oriented bounding box.
        touching_is_overlap: Whether boundary contact yields 0.0 distance.

    Returns:
        Exact minimum separation distance in meters (>= 0.0).
    """
    if check_obb_overlap_sat(box_a, box_b, touching_is_overlap=touching_is_overlap):
        return 0.0

    va = getattr(box_a, "_vertices", None) or box_a.get_vertices()
    vb = getattr(box_b, "_vertices", None) or box_b.get_vertices()

    min_dist = float("inf")

    # 1. Distances from all vertices of A to all 4 edges of B
    for i in range(4):
        ax, ay = vb[i]
        bx, by = vb[(i + 1) % 4]
        dx = bx - ax
        dy = by - ay
        l2 = dx * dx + dy * dy
        if l2 < 1e-12:
            for px, py in va:
                d = math.hypot(px - ax, py - ay)
                if d < min_dist:
                    min_dist = d
                    if min_dist < EPSILON:
                        return 0.0
        else:
            inv_l2 = 1.0 / l2
            for px, py in va:
                t = ((px - ax) * dx + (py - ay) * dy) * inv_l2
                t_clamped = 0.0 if t <= 0.0 else (1.0 if t >= 1.0 else t)
                cx = ax + t_clamped * dx
                cy = ay + t_clamped * dy
                d = math.hypot(px - cx, py - cy)
                if d < min_dist:
                    min_dist = d
                    if min_dist < EPSILON:
                        return 0.0

    # 2. Distances from all vertices of B to all 4 edges of A
    for i in range(4):
        ax, ay = va[i]
        bx, by = va[(i + 1) % 4]
        dx = bx - ax
        dy = by - ay
        l2 = dx * dx + dy * dy
        if l2 < 1e-12:
            for px, py in vb:
                d = math.hypot(px - ax, py - ay)
                if d < min_dist:
                    min_dist = d
                    if min_dist < EPSILON:
                        return 0.0
        else:
            inv_l2 = 1.0 / l2
            for px, py in vb:
                t = ((px - ax) * dx + (py - ay) * dy) * inv_l2
                t_clamped = 0.0 if t <= 0.0 else (1.0 if t >= 1.0 else t)
                cx = ax + t_clamped * dx
                cy = ay + t_clamped * dy
                d = math.hypot(px - cx, py - cy)
                if d < min_dist:
                    min_dist = d
                    if min_dist < EPSILON:
                        return 0.0

    return max(0.0, min_dist)
