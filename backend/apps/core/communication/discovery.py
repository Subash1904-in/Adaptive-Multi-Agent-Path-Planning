"""Spatial peer discovery for Vehicle-to-Vehicle communication.

Discovers eligible peer vehicles located within a configurable Euclidean communication
radius R using the 2D planar coordinate frame of the AMAPP simulation.
"""

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Optional

from apps.core.communication.exceptions import InvalidRangeError
from apps.core.domain.values import Position2D

if TYPE_CHECKING:
    from apps.core.simulation.models import WorldSnapshot


class SpatialPeerDiscovery:
    """Discovers nearby communicating vehicles based on Euclidean distance in meters.

    Invariants:
    1. Self-exclusion: The sender is never returned as its own peer.
    2. Exact boundary inclusion: A peer located exactly at distance d == R is eligible.
    3. Boundary exclusion: Any peer at d > R is excluded.
    4. Deterministic ordering: Results are ordered by ascending distance, with ties broken
       alphabetically by vehicle identifier.
    5. No side-effects: Queries do not mutate world state, vehicles, or snapshots.
    """

    def __init__(
        self,
        range_m: float = 50.0,
        max_peers: Optional[int] = None,
    ) -> None:
        """Initialize peer discovery with a configured communication radius.

        Args:
            range_m: Maximum communication radius in planar meters (must be > 0.0).
            max_peers: Optional upper bound on discovered peer count.

        Raises:
            InvalidRangeError: If range_m is non-numeric, non-finite, or <= 0.0.
            ValueError: If max_peers is not a positive integer.
        """
        if (
            not isinstance(range_m, (int, float))
            or not math.isfinite(range_m)
            or range_m <= 0.0
        ):
            raise InvalidRangeError(range_m)

        if max_peers is not None:
            if not isinstance(max_peers, int) or isinstance(max_peers, bool) or max_peers <= 0:
                raise ValueError(f"max_peers must be a positive integer, got {max_peers}.")

        self.range_m: float = float(range_m)
        self.max_peers: Optional[int] = max_peers

    def find_peers(
        self,
        sender_id: str,
        sender_position: Position2D,
        candidates: Mapping[str, Position2D],
    ) -> list[str]:
        """Discover eligible communicating peers within the configured radius R.

        Args:
            sender_id: Identifier of the transmitting vehicle (excluded from results).
            sender_position: 2D planar position of the sender.
            candidates: Mapping from vehicle_id to Position2D.

        Returns:
            List of eligible peer vehicle IDs sorted deterministically by (distance, vehicle_id).
        """
        results_with_distance = self.find_peers_with_distances(
            sender_id=sender_id,
            sender_position=sender_position,
            candidates=candidates,
        )
        return [peer_id for peer_id, _ in results_with_distance]

    def find_peers_with_distances(
        self,
        sender_id: str,
        sender_position: Position2D,
        candidates: Mapping[str, Position2D],
    ) -> list[tuple[str, float]]:
        """Discover eligible peers and return their IDs alongside exact Euclidean distances.

        Args:
            sender_id: Identifier of transmitting vehicle.
            sender_position: 2D planar position of the sender.
            candidates: Mapping from vehicle_id to Position2D.

        Returns:
            List of tuples `(peer_id, distance_m)` sorted by `(round(d, 6), peer_id)`.
        """
        eligible: list[tuple[float, str]] = []

        for peer_id, peer_pos in candidates.items():
            # 1. Self-exclusion rule
            if peer_id == sender_id:
                continue

            # 2. Skip candidates with invalid or missing positions
            if not isinstance(peer_pos, Position2D):
                continue
            if not math.isfinite(peer_pos.x) or not math.isfinite(peer_pos.y):
                continue

            # 3. Compute Euclidean planar distance in meters
            dist = sender_position.distance_to(peer_pos)

            # 4. Range boundary evaluation (d <= R)
            if dist <= self.range_m:
                eligible.append((dist, peer_id))

        # 5. Deterministic sorting: distance ascending, then vehicle_id ascending
        eligible.sort(key=lambda item: (round(item[0], 6), item[1]))

        # 6. Apply optional peer count limit
        if self.max_peers is not None:
            eligible = eligible[: self.max_peers]

        return [(peer_id, dist) for dist, peer_id in eligible]

    def find_peers_from_snapshot(
        self,
        sender_id: str,
        snapshot: "WorldSnapshot",
    ) -> list[str]:
        """Discover eligible peers directly from an immutable WorldSnapshot.

        Args:
            sender_id: Transmitting vehicle ID.
            snapshot: Authoritative WorldSnapshot.

        Returns:
            List of discovered peer IDs.

        Raises:
            KeyError: If sender_id is not present in the snapshot vehicles.
        """
        if sender_id not in snapshot.vehicles:
            raise KeyError(f"Sender vehicle '{sender_id}' not found in WorldSnapshot.")

        sender_pos = snapshot.vehicles[sender_id].position
        candidates = {vid: snap.position for vid, snap in snapshot.vehicles.items()}

        return self.find_peers(
            sender_id=sender_id,
            sender_position=sender_pos,
            candidates=candidates,
        )


def brute_force_reference(
    sender_id: str,
    sender_position: Position2D,
    candidates: Mapping[str, Position2D],
    range_m: float,
    max_peers: Optional[int] = None,
) -> list[str]:
    """Reference implementation of spatial peer discovery for test verification.

    Implements the discovery rule:
        d = sqrt((x2 - x1)^2 + (y2 - y1)^2) <= R
    """
    eligible = []
    for vid, pos in candidates.items():
        if vid == sender_id or not isinstance(pos, Position2D):
            continue
        dx = pos.x - sender_position.x
        dy = pos.y - sender_position.y
        dist = math.hypot(dx, dy)
        if dist <= range_m:
            eligible.append((round(dist, 6), vid))

    eligible.sort(key=lambda x: (x[0], x[1]))
    if max_peers is not None:
        eligible = eligible[:max_peers]
    return [vid for _, vid in eligible]
