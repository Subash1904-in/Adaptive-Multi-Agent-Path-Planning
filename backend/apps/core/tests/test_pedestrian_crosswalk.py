"""Unit tests for Crosswalk geometry, corridor bounds, waiting areas, and signal mapping."""

import math

import pytest

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.values import Position2D
from apps.core.pedestrians.crosswalk import Crosswalk
from apps.core.pedestrians.exceptions import InvalidCrosswalkError
from apps.core.pedestrians.models import (
    PedestrianSignalState,
)

SignalState = TrafficSignalState


class TestCrosswalkGeometryAndValidation:
    """Test crosswalk geometry validation, corridor boundaries, and projection."""

    def test_valid_crosswalk_creation(self) -> None:
        cw = Crosswalk(
            crosswalk_id="cw_main",
            entry_point=(10.0, 0.0),
            exit_point=(10.0, 10.0),
            width_m=4.0,
        )
        assert cw.crosswalk_id == "cw_main"
        assert cw.entry_point == Position2D(x=10.0, y=0.0)
        assert cw.exit_point == Position2D(x=10.0, y=10.0)
        assert cw.width_m == 4.0
        assert math.isclose(cw.length_m, 10.0, abs_tol=1e-5)

    def test_invalid_crosswalk_empty_id_rejected(self) -> None:
        with pytest.raises(InvalidCrosswalkError):
            Crosswalk(
                crosswalk_id="",
                entry_point=(0.0, 0.0),
                exit_point=(0.0, 5.0),
            )

    def test_invalid_crosswalk_identical_endpoints_rejected(self) -> None:
        with pytest.raises(InvalidCrosswalkError):
            Crosswalk(
                crosswalk_id="cw_zero_len",
                entry_point=(5.0, 5.0),
                exit_point=(5.0, 5.0),
            )

    def test_invalid_crosswalk_non_positive_width_rejected(self) -> None:
        with pytest.raises(InvalidCrosswalkError):
            Crosswalk(
                crosswalk_id="cw_bad_w",
                entry_point=(0.0, 0.0),
                exit_point=(0.0, 5.0),
                width_m=0.0,
            )
        with pytest.raises(InvalidCrosswalkError):
            Crosswalk(
                crosswalk_id="cw_neg_w",
                entry_point=(0.0, 0.0),
                exit_point=(0.0, 5.0),
                width_m=-2.0,
            )

    def test_invalid_crosswalk_non_finite_coords_rejected(self) -> None:
        with pytest.raises(InvalidCrosswalkError):
            Crosswalk(
                crosswalk_id="cw_inf",
                entry_point=(float("inf"), 0.0),
                exit_point=(0.0, 5.0),
            )


class TestCrosswalkCorridorAndWaitingArea:
    """Test spatial point membership in crosswalk corridor and waiting area detection."""

    def test_point_inside_corridor(self) -> None:
        # Crosswalk along x=10 from y=0 to y=10 with width 4.0 (half-width 2.0: x in [8.0, 12.0])
        cw = Crosswalk(
            crosswalk_id="cw_test",
            entry_point=(10.0, 0.0),
            exit_point=(10.0, 10.0),
            width_m=4.0,
        )
        # Center of crosswalk
        assert cw.is_point_inside(Position2D(x=10.0, y=5.0)) is True
        # Near entry
        assert cw.is_point_inside(Position2D(x=10.0, y=0.5)) is True
        # Within lateral bounds: x=11.5, y=5.0
        assert cw.is_point_inside(Position2D(x=11.5, y=5.0)) is True

        # Outside lateral bounds: x=13.0, y=5.0
        assert cw.is_point_inside(Position2D(x=13.0, y=5.0)) is False
        # Outside longitudinal bounds: before entry (y=-1.0)
        assert cw.is_point_inside(Position2D(x=10.0, y=-1.0)) is False
        # Outside longitudinal bounds: past exit (y=11.0)
        assert cw.is_point_inside(Position2D(x=10.0, y=11.0)) is False

    def test_waiting_area_detection(self) -> None:
        cw = Crosswalk(
            crosswalk_id="cw_wait",
            entry_point=(10.0, 0.0),
            exit_point=(10.0, 10.0),
            width_m=4.0,
        )
        # Point right at entry point
        assert cw.is_at_waiting_area(Position2D(x=10.0, y=0.0), buffer_m=1.5) is True
        # Point 1 meter before entry
        assert cw.is_at_waiting_area(Position2D(x=10.0, y=-1.0), buffer_m=1.5) is True
        # Point far from entry
        assert cw.is_at_waiting_area(Position2D(x=10.0, y=-5.0), buffer_m=1.5) is False

    def test_signal_mapping_unsignalized(self) -> None:
        cw = Crosswalk(
            crosswalk_id="cw_unsig",
            entry_point=(0.0, 0.0),
            exit_point=(0.0, 10.0),
            signal_controller_id=None,
        )
        assert cw.get_pedestrian_signal_state({}) == PedestrianSignalState.WALK

    def test_signal_mapping_signalized(self) -> None:
        cw = Crosswalk(
            crosswalk_id="cw_sig",
            entry_point=(0.0, 0.0),
            exit_point=(0.0, 10.0),
            signal_controller_id="sig_01",
        )
        # Conflicting vehicle approach is RED -> Pedestrian gets WALK
        assert (
            cw.get_pedestrian_signal_state({"sig_01": SignalState.RED})
            == PedestrianSignalState.WALK
        )
        # Conflicting vehicle approach is YELLOW -> Pedestrian gets CLEARANCE
        assert (
            cw.get_pedestrian_signal_state({"sig_01": SignalState.YELLOW})
            == PedestrianSignalState.CLEARANCE
        )
        # Conflicting vehicle approach is GREEN -> Pedestrian gets DONT_WALK
        assert (
            cw.get_pedestrian_signal_state({"sig_01": SignalState.GREEN})
            == PedestrianSignalState.DONT_WALK
        )

    def test_crosswalk_to_dict_serialization(self) -> None:
        cw = Crosswalk(
            crosswalk_id="cw_serial",
            entry_point=(10.0, 20.0),
            exit_point=(10.0, 30.0),
            width_m=3.5,
            associated_intersection_id="node_01",
            associated_road_segment_ids=("edge_01",),
            signal_controller_id="sig_01",
        )
        d = cw.to_dict()
        assert d["crosswalk_id"] == "cw_serial"
        assert d["entry_point"] == {"x": 10.0, "y": 20.0}
        assert d["exit_point"] == {"x": 10.0, "y": 30.0}
        assert d["width_m"] == 3.5
        assert d["associated_intersection_id"] == "node_01"
        assert d["associated_road_segment_ids"] == ["edge_01"]
        assert d["signal_controller_id"] == "sig_01"
