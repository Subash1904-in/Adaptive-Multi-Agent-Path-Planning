"""Crosswalk and pedestrian crossing corridor geometry models."""

import math
from typing import Any, Optional, Sequence, Union

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.exceptions import DomainValidationError
from apps.core.domain.values import Position2D
from apps.core.pedestrians.exceptions import InvalidCrosswalkError
from apps.core.pedestrians.models import PedestrianSignalState


class Crosswalk:
    """Designated pedestrian crossing corridor across one or more road approaches.

    Attributes:
        id: Unique crosswalk identifier.
        node_id: Associated intersection or road network node ID.
        road_edge_ids: Tuple of road edge IDs crossed by this crosswalk.
        entry_point: Starting curb / staging position in world coordinates (meters).
        exit_point: Destination curb position across the street in world coordinates.
        width_m: Lateral width of the crossing corridor in meters.
        signal_id: Optional identifier of the associated traffic signal controller.
        bidirectional: Whether pedestrians can traverse in either direction.
        waiting_radius_m: Radius around entry/exit points treated as pedestrian waiting area.
    """

    def __init__(
        self,
        id: Optional[str] = None,
        crosswalk_id: Optional[str] = None,
        node_id: Optional[str] = None,
        associated_intersection_id: Optional[str] = None,
        road_edge_ids: Optional[Sequence[str]] = None,
        associated_road_segment_ids: Optional[Sequence[str]] = None,
        entry_point: Union[Position2D, tuple[float, float], list[float]] = (0.0, 0.0),
        exit_point: Union[Position2D, tuple[float, float], list[float]] = (0.0, 1.0),
        width_m: float = 3.0,
        signal_id: Optional[str] = None,
        signal_controller_id: Optional[str] = None,
        bidirectional: bool = True,
        waiting_radius_m: float = 2.0,
        walk_signal_phase: Optional[str] = None,
        clearance_signal_phase: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize and validate a crosswalk corridor."""
        self.walk_signal_phase = walk_signal_phase
        self.clearance_signal_phase = clearance_signal_phase
        self.metadata = metadata or {}
        final_id = id if id is not None else crosswalk_id
        if not final_id or not isinstance(final_id, str):
            raise InvalidCrosswalkError("Crosswalk ID must be a non-empty string.")
        self.id: str = final_id

        final_node = node_id if node_id is not None else associated_intersection_id
        self.node_id: str = final_node if final_node is not None else ""

        final_edges = road_edge_ids if road_edge_ids is not None else associated_road_segment_ids
        self.road_edge_ids: tuple[str, ...] = tuple(final_edges) if final_edges is not None else ()

        # Entry point conversion
        try:
            if isinstance(entry_point, (tuple, list)):
                if len(entry_point) != 2:
                    raise InvalidCrosswalkError(
                        f"entry_point sequence must have 2 elements, got {entry_point}."
                    )
                self.entry_point = Position2D(x=float(entry_point[0]), y=float(entry_point[1]))
            elif isinstance(entry_point, Position2D):
                self.entry_point = entry_point
            else:
                raise InvalidCrosswalkError(
                    "entry_point must be an instance of Position2D or a 2-tuple."
                )

            # Exit point conversion
            if isinstance(exit_point, (tuple, list)):
                if len(exit_point) != 2:
                    raise InvalidCrosswalkError(
                        f"exit_point sequence must have 2 elements, got {exit_point}."
                    )
                self.exit_point = Position2D(x=float(exit_point[0]), y=float(exit_point[1]))
            elif isinstance(exit_point, Position2D):
                self.exit_point = exit_point
            else:
                raise InvalidCrosswalkError(
                    "exit_point must be an instance of Position2D or a 2-tuple."
                )
        except (DomainValidationError, ValueError) as exc:
            raise InvalidCrosswalkError(f"Invalid crosswalk endpoint: {exc}") from exc

        for p_name, pt in [("entry_point", self.entry_point), ("exit_point", self.exit_point)]:
            if not math.isfinite(pt.x) or not math.isfinite(pt.y):
                raise InvalidCrosswalkError(
                    f"{p_name} coordinates must be finite, got ({pt.x}, {pt.y})."
                )

        length = math.hypot(
            self.exit_point.x - self.entry_point.x, self.exit_point.y - self.entry_point.y
        )
        if length <= 1e-4:
            raise InvalidCrosswalkError(
                f"Crosswalk '{self.id}' entry_point and exit_point cannot be identical (length=0)."
            )

        if not isinstance(width_m, (int, float)) or isinstance(width_m, bool):
            raise InvalidCrosswalkError(f"width_m must be numeric, got {type(width_m).__name__}.")
        if not math.isfinite(width_m) or width_m <= 0.0:
            raise InvalidCrosswalkError(
                f"width_m must be strictly positive and finite, got {width_m}."
            )
        self.width_m: float = float(width_m)

        final_sig = signal_id if signal_id is not None else signal_controller_id
        if final_sig is not None and (not isinstance(final_sig, str) or not final_sig):
            raise InvalidCrosswalkError("signal_id must be a non-empty string or None.")
        self.signal_id: Optional[str] = final_sig

        self.bidirectional: bool = bool(bidirectional)

        if not isinstance(waiting_radius_m, (int, float)) or isinstance(waiting_radius_m, bool):
            raise InvalidCrosswalkError(
                f"waiting_radius_m must be numeric, got {type(waiting_radius_m).__name__}."
            )
        if not math.isfinite(waiting_radius_m) or waiting_radius_m <= 0.0:
            raise InvalidCrosswalkError(
                f"waiting_radius_m must be strictly positive and finite, got {waiting_radius_m}."
            )
        self.waiting_radius_m: float = float(waiting_radius_m)

    @property
    def crosswalk_id(self) -> str:
        """Alias for id."""
        return self.id

    @property
    def associated_intersection_id(self) -> str:
        """Alias for node_id."""
        return self.node_id

    @property
    def associated_road_segment_ids(self) -> tuple[str, ...]:
        """Alias for road_edge_ids."""
        return self.road_edge_ids

    @property
    def signal_controller_id(self) -> Optional[str]:
        """Alias for signal_id."""
        return self.signal_id

    @property
    def length_m(self) -> float:
        """Euclidean span distance between entry and exit points in meters."""
        return math.hypot(
            self.exit_point.x - self.entry_point.x, self.exit_point.y - self.entry_point.y
        )

    def is_point_inside(self, point: Position2D, tolerance_m: float = 0.1) -> bool:
        """Determine if a 2D position lies inside the rectangular crosswalk corridor."""
        if not math.isfinite(point.x) or not math.isfinite(point.y):
            return False

        dx = self.exit_point.x - self.entry_point.x
        dy = self.exit_point.y - self.entry_point.y
        length = self.length_m
        if length <= 1e-6:
            return False

        # Unit vector along crosswalk length (entry -> exit)
        ux = dx / length
        uy = dy / length

        # Vector from entry to point
        px = point.x - self.entry_point.x
        py = point.y - self.entry_point.y

        # Longitudinal projection t along centerline
        t = px * ux + py * uy
        if t < -tolerance_m or t > length + tolerance_m:
            return False

        # Lateral projection distance d_lat perpendicular to centerline
        # Normal vector is (-uy, ux)
        d_lat = abs(px * (-uy) + py * ux)
        half_width = self.width_m / 2.0
        return d_lat <= half_width + tolerance_m

    def is_at_waiting_area(
        self, point: Position2D, buffer_m: Optional[float] = None, at_exit: bool = False
    ) -> bool:
        """Check if a position is within the waiting/staging radius of entry or exit."""
        ref = self.exit_point if at_exit else self.entry_point
        radius = buffer_m if buffer_m is not None else self.waiting_radius_m
        dist = math.hypot(point.x - ref.x, point.y - ref.y)
        return dist <= radius

    def get_pedestrian_signal_state(
        self, signal_state_or_map: Union[Optional[TrafficSignalState], dict[str, Any], Any] = None
    ) -> PedestrianSignalState:
        """Derive pedestrian crossing signal indication from intersection traffic signal state.

        Traffic signal integration mapping:
            - When vehicle approach is RED: Pedestrians have right-of-way (WALK).
            - When vehicle approach is YELLOW: Clearance phase (CLEARANCE - finish crossing).
            - When vehicle approach is GREEN: Vehicles have right-of-way (DONT_WALK).
            - If crosswalk is unsignalized (signal_id is None): Always WALK.
        """
        if self.signal_id is None:
            return PedestrianSignalState.WALK

        sig_state = None
        if isinstance(signal_state_or_map, dict):
            sig_state = signal_state_or_map.get(self.signal_id)
        else:
            sig_state = signal_state_or_map

        if sig_state is None:
            return PedestrianSignalState.WALK

        # Compare either as TrafficSignalState enum or string value
        val = (sig_state.value if hasattr(sig_state, "value") else str(sig_state)).upper()
        if val == "RED":
            return PedestrianSignalState.WALK
        if val == "YELLOW":
            return PedestrianSignalState.CLEARANCE
        if val == "GREEN":
            return PedestrianSignalState.DONT_WALK
        return PedestrianSignalState.DONT_WALK

    def to_dict(self) -> dict[str, Any]:
        """Serialize crosswalk definition to dictionary."""
        return {
            "id": self.id,
            "crosswalk_id": self.id,
            "node_id": self.node_id,
            "associated_intersection_id": self.node_id,
            "road_edge_ids": list(self.road_edge_ids),
            "associated_road_segment_ids": list(self.road_edge_ids),
            "entry_point": self.entry_point.to_dict(),
            "exit_point": self.exit_point.to_dict(),
            "width_m": round(self.width_m, 3),
            "length_m": round(self.length_m, 3),
            "signal_id": self.signal_id,
            "signal_controller_id": self.signal_id,
            "bidirectional": self.bidirectional,
            "waiting_radius_m": round(self.waiting_radius_m, 3),
        }
