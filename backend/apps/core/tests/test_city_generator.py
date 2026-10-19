"""Unit tests for the deterministic synthetic city grid generator."""

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.graph.exceptions import GraphValidationError
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid


class TestCityGridConfig:
    """Validation tests for CityGridConfig parameters."""

    def test_default_config(self) -> None:
        cfg = CityGridConfig()
        assert cfg.rows == 3
        assert cfg.cols == 3
        assert cfg.spacing_m == 100.0
        assert cfg.speed_limit_mps == 13.89
        assert cfg.lanes == 1
        assert cfg.bidirectional is True
        assert cfg.signalized_intersections is None
        assert cfg.signal_cycle_s == 60.0
        assert cfg.speed_variance_mps == 0.0
        assert cfg.seed == 42

    @pytest.mark.parametrize("rows, cols", [
        (1, 3),
        (3, 1),
        (-2, 3),
        (3, 0),
    ])
    def test_dimensions_less_than_two_rejected(self, rows: int, cols: int) -> None:
        with pytest.raises(GraphValidationError):
            CityGridConfig(rows=rows, cols=cols)

    @pytest.mark.parametrize("spacing", [0.0, -50.0])
    def test_invalid_spacing_rejected(self, spacing: float) -> None:
        with pytest.raises(GraphValidationError):
            CityGridConfig(spacing_m=spacing)

    @pytest.mark.parametrize("speed", [0.0, -10.0])
    def test_invalid_speed_limit_rejected(self, speed: float) -> None:
        with pytest.raises(GraphValidationError):
            CityGridConfig(speed_limit_mps=speed)

    @pytest.mark.parametrize("lanes", [0, -1])
    def test_invalid_lanes_rejected(self, lanes: int) -> None:
        with pytest.raises(GraphValidationError):
            CityGridConfig(lanes=lanes)

    @pytest.mark.parametrize("variance", [-1.0, 15.0])  # 15.0 >= speed_limit_mps (13.89)
    def test_invalid_speed_variance_rejected(self, variance: float) -> None:
        with pytest.raises(GraphValidationError):
            CityGridConfig(speed_variance_mps=variance)

    def test_out_of_bounds_signalized_intersection_rejected(self) -> None:
        with pytest.raises(GraphValidationError) as exc_info:
            CityGridConfig(rows=3, cols=3, signalized_intersections=[(3, 1)])
        assert "outside grid bounds" in str(exc_info.value)


class TestCityGridGeneration:
    """Tests for synthetic city grid topology, connectivity, and signals."""

    def test_default_3x3_grid_generation(self) -> None:
        cfg = CityGridConfig(rows=3, cols=3, spacing_m=100.0)
        graph = generate_synthetic_city_grid(cfg)

        # 1. Node count: 3x3 = 9 nodes
        assert graph.node_count == 9

        # 2. Check node IDs and positions
        for r in range(3):
            for c in range(3):
                node_id = f"node_r{r}_c{c}"
                assert graph.has_node(node_id)
                node = graph.get_node(node_id)
                assert node.position.x == c * 100.0
                assert node.position.y == r * 100.0

        # 3. Edge count:
        # Horizontal: 3 rows * 2 segments * 2 directions = 12
        # Vertical: 3 cols * 2 segments * 2 directions = 12
        # Total = 24 directed edges
        assert graph.edge_count == 24

        # 4. Invariants on all edges
        for edge in graph.edges():
            assert edge.length_m == 100.0
            assert edge.speed_limit_mps == 13.89
            assert edge.lanes == 1
            assert graph.has_node(edge.start_node_id)
            assert graph.has_node(edge.end_node_id)

        # 5. Connectivity
        assert graph.is_weakly_connected()
        assert graph.is_strongly_connected()

        # 6. Alternative paths between diagonal corners
        assert graph.has_alternative_paths("node_r0_c0", "node_r2_c2")
        assert graph.has_alternative_paths("node_r2_c2", "node_r0_c0")

        # 7. Traffic signals: center intersection (1, 1) should be signalized by default
        assert graph.signal_count == 1
        signal = graph.get_traffic_signal("node_r1_c1")
        assert signal is not None
        assert signal.node_id == "node_r1_c1"
        assert signal.state == TrafficSignalState.RED
        assert signal.cycle_duration_s == 60.0
        assert signal.remaining_phase_s == 30.0

    def test_one_way_grid_generation(self) -> None:
        cfg = CityGridConfig(rows=3, cols=3, bidirectional=False)
        graph = generate_synthetic_city_grid(cfg)

        assert graph.node_count == 9
        # In one-way mode, only forward edges are created (East and North)
        # Horizontal: 3 rows * 2 segments * 1 = 6
        # Vertical: 3 cols * 2 segments * 1 = 6
        # Total = 12 edges
        assert graph.edge_count == 12

        # One-way grid without cycles is weakly connected, but not strongly connected
        assert graph.is_weakly_connected()
        assert not graph.is_strongly_connected()

        # Path from origin to destination exists, but reverse path does not
        assert graph.is_reachable("node_r0_c0", "node_r2_c2")
        assert not graph.is_reachable("node_r2_c2", "node_r0_c0")

    def test_custom_signalized_intersections(self) -> None:
        cfg = CityGridConfig(
            rows=3,
            cols=3,
            signalized_intersections=[(0, 0), (2, 2)],
        )
        graph = generate_synthetic_city_grid(cfg)

        assert graph.signal_count == 2
        assert graph.get_traffic_signal("node_r0_c0") is not None
        assert graph.get_traffic_signal("node_r2_c2") is not None
        assert graph.get_traffic_signal("node_r1_c1") is None

    def test_custom_grid_dimensions(self) -> None:
        cfg = CityGridConfig(rows=4, cols=5, spacing_m=75.0)
        graph = generate_synthetic_city_grid(cfg)

        assert graph.node_count == 20
        # Horizontal: 4 rows * 4 segments * 2 = 32
        # Vertical: 5 cols * 3 segments * 2 = 30
        # Total = 62
        assert graph.edge_count == 62

        # Internal intersections: (rows - 2) * (cols - 2) = 2 * 3 = 6 signals
        assert graph.signal_count == 6
        assert graph.is_strongly_connected()

    def test_deterministic_reproducibility(self) -> None:
        cfg1 = CityGridConfig(rows=3, cols=4, seed=123)
        cfg2 = CityGridConfig(rows=3, cols=4, seed=123)

        graph1 = generate_synthetic_city_grid(cfg1)
        graph2 = generate_synthetic_city_grid(cfg2)

        assert graph1.node_ids() == graph2.node_ids()
        assert graph1.edge_ids() == graph2.edge_ids()

        for node_id in graph1.node_ids():
            assert graph1.get_node(node_id) == graph2.get_node(node_id)

        for edge_id in graph1.edge_ids():
            assert graph1.get_edge(edge_id) == graph2.get_edge(edge_id)

        assert graph1.to_dict() == graph2.to_dict()

    def test_deterministic_seeded_variation(self) -> None:
        # When variance is enabled, same seed produces identical speed limits,
        # different seeds produce different speed limits.
        cfg_seed_a1 = CityGridConfig(rows=3, cols=3, speed_variance_mps=3.0, seed=100)
        cfg_seed_a2 = CityGridConfig(rows=3, cols=3, speed_variance_mps=3.0, seed=100)
        cfg_seed_b = CityGridConfig(rows=3, cols=3, speed_variance_mps=3.0, seed=999)

        g_a1 = generate_synthetic_city_grid(cfg_seed_a1)
        g_a2 = generate_synthetic_city_grid(cfg_seed_a2)
        g_b = generate_synthetic_city_grid(cfg_seed_b)

        # Identical seed produces identical speeds
        speeds_a1 = [e.speed_limit_mps for e in g_a1.edges()]
        speeds_a2 = [e.speed_limit_mps for e in g_a2.edges()]
        speeds_b = [e.speed_limit_mps for e in g_b.edges()]

        assert speeds_a1 == speeds_a2
        assert speeds_a1 != speeds_b  # Different seeds vary deterministically
