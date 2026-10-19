"""Deterministic synthetic city grid generator for AMAPP.

Generates reproducible road network graphs with planar coordinates,
directed edges, traffic signals, and verified connectivity without
requiring internet access or external geospatial services.
"""

import random
from dataclasses import dataclass
from typing import Optional

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import RoadEdge, RoadNode, TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.graph.exceptions import GraphValidationError
from apps.core.graph.road_graph import RoadGraph


@dataclass(frozen=True)
class CityGridConfig:
    """Configuration parameters for deterministic synthetic city grid generation.

    Attributes:
        rows: Number of intersection rows (>= 2).
        cols: Number of intersection columns (>= 2).
        spacing_m: Distance between adjacent intersections in meters (> 0.0).
        speed_limit_mps: Default roadway speed limit in meters per second (> 0.0).
        lanes: Number of lanes per road segment (>= 1).
        bidirectional: If True, generates opposing directed edges for two-way streets.
        signalized_intersections: Explicit (row, col) coordinates for traffic signals.
            If None, all internal 4-way intersections are signalized.
        signal_cycle_s: Full traffic signal cycle duration in seconds (> 0.0).
        speed_variance_mps: Optional randomized variation range for speed limits.
            Governed deterministically by seed. Defaults to 0.0 (uniform speeds).
        seed: Pseudorandom generator seed for deterministic reproducibility.
    """

    rows: int = 3
    cols: int = 3
    spacing_m: float = 100.0
    speed_limit_mps: float = 13.89  # ~50 km/h
    lanes: int = 1
    bidirectional: bool = True
    signalized_intersections: Optional[list[tuple[int, int]]] = None
    signal_cycle_s: float = 60.0
    speed_variance_mps: float = 0.0
    seed: int = 42

    def __post_init__(self) -> None:
        if not isinstance(self.rows, int) or self.rows < 2:
            raise GraphValidationError(
                f"rows must be an integer >= 2, got {self.rows}.", field="rows"
            )
        if not isinstance(self.cols, int) or self.cols < 2:
            raise GraphValidationError(
                f"cols must be an integer >= 2, got {self.cols}.", field="cols"
            )
        if not isinstance(self.spacing_m, (int, float)) or self.spacing_m <= 0.0:
            raise GraphValidationError(
                f"spacing_m must be strictly positive (> 0.0), got {self.spacing_m}.",
                field="spacing_m",
            )
        if not isinstance(self.speed_limit_mps, (int, float)) or self.speed_limit_mps <= 0.0:
            raise GraphValidationError(
                f"speed_limit_mps must be strictly positive (> 0.0), got {self.speed_limit_mps}.",
                field="speed_limit_mps",
            )
        if not isinstance(self.lanes, int) or self.lanes < 1:
            raise GraphValidationError(
                f"lanes must be an integer >= 1, got {self.lanes}.", field="lanes"
            )
        if not isinstance(self.bidirectional, bool):
            raise GraphValidationError(
                f"bidirectional must be a boolean, got {self.bidirectional}.",
                field="bidirectional",
            )
        if not isinstance(self.signal_cycle_s, (int, float)) or self.signal_cycle_s <= 0.0:
            raise GraphValidationError(
                f"signal_cycle_s must be strictly positive (> 0.0), got {self.signal_cycle_s}.",
                field="signal_cycle_s",
            )
        if not isinstance(self.speed_variance_mps, (int, float)) or self.speed_variance_mps < 0.0:
            raise GraphValidationError(
                "speed_variance_mps must be non-negative (>= 0.0).",
                field="speed_variance_mps",
            )
        if self.speed_variance_mps >= self.speed_limit_mps:
            raise GraphValidationError(
                f"speed_variance_mps ({self.speed_variance_mps}) must be smaller than "
                f"speed_limit_mps ({self.speed_limit_mps}).",
                field="speed_variance_mps",
            )
        if not isinstance(self.seed, int):
            raise GraphValidationError(
                f"seed must be an integer, got {self.seed}.", field="seed"
            )

        if self.signalized_intersections is not None:
            if not isinstance(self.signalized_intersections, list):
                raise GraphValidationError(
                    "signalized_intersections must be a list of (row, col) tuples or None.",
                    field="signalized_intersections",
                )
            for item in self.signalized_intersections:
                if not isinstance(item, tuple) or len(item) != 2:
                    raise GraphValidationError(
                        f"Invalid intersection tuple: {item}.",
                        field="signalized_intersections",
                    )
                r, c = item
                if not (0 <= r < self.rows and 0 <= c < self.cols):
                    raise GraphValidationError(
                        f"Intersection ({r}, {c}) is outside grid bounds "
                        f"[0..{self.rows - 1}, 0..{self.cols - 1}].",
                        field="signalized_intersections",
                    )


def generate_synthetic_city_grid(config: Optional[CityGridConfig] = None) -> RoadGraph:
    """Generate a deterministic synthetic city road network graph.

    Args:
        config: Grid configuration. Defaults to 3x3 grid with 100m spacing.

    Returns:
        A fully validated, strongly connected RoadGraph.
    """
    cfg = config or CityGridConfig()
    rng = random.Random(cfg.seed)

    graph_name = f"synthetic_city_{cfg.rows}x{cfg.cols}_seed{cfg.seed}"
    graph = RoadGraph(name=graph_name)

    # 1. Create RoadNodes with deterministic IDs and planar coordinates
    node_matrix: dict[tuple[int, int], RoadNode] = {}
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            node_id = f"node_r{r}_c{c}"
            pos = Position2D(x=float(c * cfg.spacing_m), y=float(r * cfg.spacing_m))
            node = RoadNode(
                id=node_id,
                position=pos,
                attributes={"row": r, "col": c, "is_boundary": (
                    r == 0 or r == cfg.rows - 1 or c == 0 or c == cfg.cols - 1
                )},
            )
            graph.add_node(node)
            node_matrix[(r, c)] = node

    # Helper function to compute edge speed limit
    def _get_speed_limit() -> float:
        if cfg.speed_variance_mps > 0.0:
            delta = rng.uniform(-cfg.speed_variance_mps, cfg.speed_variance_mps)
            return round(cfg.speed_limit_mps + delta, 2)
        return cfg.speed_limit_mps

    # 2. Create Horizontal RoadEdges (East-West)
    for r in range(cfg.rows):
        for c in range(cfg.cols - 1):
            u = node_matrix[(r, c)]
            v = node_matrix[(r, c + 1)]
            edge_length = round(u.position.distance_to(v.position), 2)

            # Eastbound edge
            east_edge_id = f"edge_r{r}_c{c}_to_r{r}_c{c + 1}"
            graph.add_edge(
                RoadEdge(
                    id=east_edge_id,
                    start_node_id=u.id,
                    end_node_id=v.id,
                    length_m=edge_length,
                    speed_limit_mps=_get_speed_limit(),
                    lanes=cfg.lanes,
                    name=f"Street_{r}_East",
                    attributes={"direction": "east", "row": r},
                )
            )

            # Westbound edge (if bidirectional)
            if cfg.bidirectional:
                west_edge_id = f"edge_r{r}_c{c + 1}_to_r{r}_c{c}"
                graph.add_edge(
                    RoadEdge(
                        id=west_edge_id,
                        start_node_id=v.id,
                        end_node_id=u.id,
                        length_m=edge_length,
                        speed_limit_mps=_get_speed_limit(),
                        lanes=cfg.lanes,
                        name=f"Street_{r}_West",
                        attributes={"direction": "west", "row": r},
                    )
                )

    # 3. Create Vertical RoadEdges (North-South)
    for c in range(cfg.cols):
        for r in range(cfg.rows - 1):
            u = node_matrix[(r, c)]
            v = node_matrix[(r + 1, c)]
            edge_length = round(u.position.distance_to(v.position), 2)

            # Northbound edge
            north_edge_id = f"edge_r{r}_c{c}_to_r{r + 1}_c{c}"
            graph.add_edge(
                RoadEdge(
                    id=north_edge_id,
                    start_node_id=u.id,
                    end_node_id=v.id,
                    length_m=edge_length,
                    speed_limit_mps=_get_speed_limit(),
                    lanes=cfg.lanes,
                    name=f"Avenue_{c}_North",
                    attributes={"direction": "north", "col": c},
                )
            )

            # Southbound edge (if bidirectional)
            if cfg.bidirectional:
                south_edge_id = f"edge_r{r + 1}_c{c}_to_r{r}_c{c}"
                graph.add_edge(
                    RoadEdge(
                        id=south_edge_id,
                        start_node_id=v.id,
                        end_node_id=u.id,
                        length_m=edge_length,
                        speed_limit_mps=_get_speed_limit(),
                        lanes=cfg.lanes,
                        name=f"Avenue_{c}_South",
                        attributes={"direction": "south", "col": c},
                    )
                )

    # 4. Create Traffic Signals
    signal_coords = cfg.signalized_intersections
    if signal_coords is None:
        # Default: internal intersections (nodes with degree >= 4)
        signal_coords = [
            (r, c)
            for r in range(1, cfg.rows - 1)
            for c in range(1, cfg.cols - 1)
        ]

    for r, c in signal_coords:
        node = node_matrix[(r, c)]
        sig_id = f"sig_r{r}_c{c}"
        signal = TrafficSignal(
            id=sig_id,
            node_id=node.id,
            state=TrafficSignalState.RED,
            position=node.position,
            cycle_duration_s=cfg.signal_cycle_s,
            remaining_phase_s=cfg.signal_cycle_s / 2.0,
        )
        graph.add_traffic_signal(signal)

    # 5. Validate topology and connectivity
    graph.validate_topology()
    return graph
