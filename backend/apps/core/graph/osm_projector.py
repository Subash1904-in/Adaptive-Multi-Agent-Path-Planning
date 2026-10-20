"""Local planar coordinate projector for geographic road networks.

Projects spherical WGS84 latitude and longitude coordinates into Cartesian
2D planar coordinates in meters (Position2D) suitable for local simulation.
"""

import math

from apps.core.domain.values import GeoCoordinate, Position2D
from apps.core.graph.osm_exceptions import InvalidBoundingBoxError

# WGS84 volumetric mean Earth radius in meters
EARTH_RADIUS_M: float = 6_371_000.0


class LocalPlanarProjector:
    """Conformal local equirectangular planar projector centered on a geographic origin.

    Maps spherical (lat, lon) coordinates in degrees to a Euclidean Cartesian
    reference frame (x, y) in meters where:
    - Origin (origin_lat, origin_lon) maps to (0.0, 0.0).
    - +x points due East (increasing longitude in meters).
    - +y points due North (increasing latitude in meters).

    For simulation areas spanning <= 25 km, distance distortion is < 0.05%,
    providing exact meter-based Euclidean mechanics without depending on
    external C projection binaries or PROJ database files.
    """

    def __init__(self, origin_lat: float, origin_lon: float) -> None:
        if not isinstance(origin_lat, (int, float)) or not math.isfinite(origin_lat):
            raise InvalidBoundingBoxError(f"origin_lat must be finite numeric, got {origin_lat}.")
        if not (-90.0 <= origin_lat <= 90.0):
            raise InvalidBoundingBoxError(f"origin_lat out of bounds [-90, 90]: {origin_lat}.")
        if not isinstance(origin_lon, (int, float)) or not math.isfinite(origin_lon):
            raise InvalidBoundingBoxError(f"origin_lon must be finite numeric, got {origin_lon}.")
        if not (-180.0 <= origin_lon <= 180.0):
            raise InvalidBoundingBoxError(f"origin_lon out of bounds [-180, 180]: {origin_lon}.")

        self.origin_lat = float(origin_lat)
        self.origin_lon = float(origin_lon)
        self.origin_lat_rad = math.radians(self.origin_lat)
        self.origin_lon_rad = math.radians(self.origin_lon)

    def project(self, lat: float, lon: float) -> Position2D:
        """Project (latitude, longitude) to local Cartesian Position2D in meters.

        Args:
            lat: WGS84 latitude in degrees [-90.0, 90.0].
            lon: WGS84 longitude in degrees [-180.0, 180.0].

        Returns:
            Position2D with x (East) and y (North) in meters.
        """
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise ValueError(f"Coordinates must be finite, got lat={lat}, lon={lon}.")
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Coordinates out of bounds, got lat={lat}, lon={lon}.")

        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        delta_lat = lat_rad - self.origin_lat_rad
        delta_lon = lon_rad - self.origin_lon_rad

        # Mid-latitude cosine adjustment for longitude convergence
        mid_lat_rad = (lat_rad + self.origin_lat_rad) / 2.0
        cos_mid = math.cos(mid_lat_rad)

        x = EARTH_RADIUS_M * delta_lon * cos_mid
        y = EARTH_RADIUS_M * delta_lat

        return Position2D(x=round(x, 3), y=round(y, 3))

    def unproject(self, position: Position2D) -> GeoCoordinate:
        """Inverse-project Cartesian Position2D in meters back to GeoCoordinate.

        Args:
            position: Position2D in meters relative to projector origin.

        Returns:
            GeoCoordinate with latitude and longitude in degrees.
        """
        if not isinstance(position, Position2D):
            raise ValueError(f"Expected Position2D instance, got {type(position).__name__}.")

        delta_lat_rad = position.y / EARTH_RADIUS_M
        lat_rad = self.origin_lat_rad + delta_lat_rad
        lat = math.degrees(lat_rad)

        mid_lat_rad = (lat_rad + self.origin_lat_rad) / 2.0
        cos_mid = math.cos(mid_lat_rad)
        if abs(cos_mid) < 1e-9:
            lon = self.origin_lon
        else:
            delta_lon_rad = position.x / (EARTH_RADIUS_M * cos_mid)
            lon = self.origin_lon + math.degrees(delta_lon_rad)

        # Clamp to valid WGS84 boundaries
        clamped_lat = max(-90.0, min(90.0, round(lat, 7)))
        clamped_lon = max(-180.0, min(180.0, round(lon, 7)))

        return GeoCoordinate(latitude=clamped_lat, longitude=clamped_lon)
