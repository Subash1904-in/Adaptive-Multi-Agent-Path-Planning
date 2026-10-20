"""Unit tests for PedestrianAgent, PedestrianConfig, and pedestrian kinematics."""

import math

import pytest

from apps.core.domain.values import Position2D
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.exceptions import (
    InvalidPedestrianConfigError,
    InvalidPedestrianStateError,
    PedestrianKinematicsError,
)
from apps.core.pedestrians.models import (
    PedestrianConfig,
    PedestrianLifecycleState,
    validate_pedestrian_transition,
)


class TestPedestrianModelsAndConfig:
    """Test pedestrian configuration validation and lifecycle state transitions."""

    def test_default_config_valid(self) -> None:
        cfg = PedestrianConfig()
        assert cfg.walking_speed_mps == 1.4
        assert cfg.max_speed_mps == 2.0
        assert cfg.length_m == 0.6
        assert cfg.width_m == 0.6
        assert cfg.arrival_tolerance_m == 0.5
        assert cfg.waiting_distance_m == 1.5

    def test_invalid_walking_speed_rejected(self) -> None:
        with pytest.raises(InvalidPedestrianConfigError):
            PedestrianConfig(walking_speed_mps=-1.0)
        with pytest.raises(InvalidPedestrianConfigError):
            PedestrianConfig(walking_speed_mps=float("nan"))
        with pytest.raises(InvalidPedestrianConfigError):
            PedestrianConfig(walking_speed_mps=3.0, max_speed_mps=2.0)

    def test_invalid_dimensions_rejected(self) -> None:
        with pytest.raises(InvalidPedestrianConfigError):
            PedestrianConfig(length_m=-0.5)
        with pytest.raises(InvalidPedestrianConfigError):
            PedestrianConfig(width_m=0.0)

    def test_legal_lifecycle_transitions(self) -> None:
        # IDLE -> WALKING
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.IDLE, PedestrianLifecycleState.WALKING
        )
        # IDLE -> APPROACHING_CROSSWALK
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.IDLE, PedestrianLifecycleState.APPROACHING_CROSSWALK
        )
        # APPROACHING_CROSSWALK -> WAITING_TO_CROSS
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.APPROACHING_CROSSWALK,
            PedestrianLifecycleState.WAITING_TO_CROSS,
        )
        # WAITING_TO_CROSS -> CROSSING
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.WAITING_TO_CROSS, PedestrianLifecycleState.CROSSING
        )
        # CROSSING -> ARRIVED
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.CROSSING, PedestrianLifecycleState.ARRIVED
        )
        # Same state transition is valid (no-op)
        assert validate_pedestrian_transition(
            PedestrianLifecycleState.CROSSING, PedestrianLifecycleState.CROSSING
        )

    def test_illegal_lifecycle_transitions_rejected(self) -> None:
        with pytest.raises(InvalidPedestrianStateError):
            validate_pedestrian_transition(
                PedestrianLifecycleState.IDLE, PedestrianLifecycleState.ARRIVED
            )
        with pytest.raises(InvalidPedestrianStateError):
            validate_pedestrian_transition(
                PedestrianLifecycleState.ARRIVED, PedestrianLifecycleState.CROSSING
            )
        with pytest.raises(InvalidPedestrianStateError):
            validate_pedestrian_transition(
                PedestrianLifecycleState.WAITING_TO_CROSS, PedestrianLifecycleState.ARRIVED
            )


class TestPedestrianKinematics:
    """Test pedestrian motion integration, bounds, and destination arrival."""

    def test_pedestrian_creation_and_start(self) -> None:
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            initial_position=(0.0, 0.0),
            destination_point=(10.0, 0.0),
        )
        assert ped.pedestrian_id == "ped_01"
        assert ped.state == PedestrianLifecycleState.IDLE
        assert ped.position == Position2D(x=0.0, y=0.0)
        assert ped.destination_point == (10.0, 0.0)

        ped.start()
        assert ped.state == PedestrianLifecycleState.WALKING
        assert ped.is_active is True

    def test_pedestrian_creation_invalid_id_rejected(self) -> None:
        with pytest.raises(InvalidPedestrianStateError):
            PedestrianAgent(
                pedestrian_id="",
                initial_position=(0.0, 0.0),
                destination_point=(10.0, 0.0),
            )

    def test_pedestrian_creation_non_finite_coords_rejected(self) -> None:
        with pytest.raises(PedestrianKinematicsError):
            PedestrianAgent(
                pedestrian_id="ped_inf",
                initial_position=(float("inf"), 0.0),
                destination_point=(10.0, 0.0),
            )

    def test_walking_motion_towards_target(self) -> None:
        ped = PedestrianAgent(
            pedestrian_id="ped_02",
            initial_position=(0.0, 0.0),
            destination_point=(10.0, 0.0),
            config=PedestrianConfig(walking_speed_mps=2.0),
        )
        ped.start()
        res = ped.step(dt=1.0)

        assert res.old_state == PedestrianLifecycleState.WALKING
        assert res.new_state == PedestrianLifecycleState.WALKING
        assert math.isclose(ped.position.x, 2.0, abs_tol=1e-5)
        assert math.isclose(ped.position.y, 0.0, abs_tol=1e-5)
        assert math.isclose(ped.speed_mps, 2.0, abs_tol=1e-5)
        assert math.isclose(ped.heading_rad, 0.0, abs_tol=1e-5)

    def test_pedestrian_arrives_at_destination(self) -> None:
        ped = PedestrianAgent(
            pedestrian_id="ped_03",
            initial_position=(9.0, 0.0),
            destination_point=(10.0, 0.0),
            config=PedestrianConfig(walking_speed_mps=1.5, arrival_tolerance_m=0.5),
        )
        ped.start()
        res = ped.step(dt=1.0)

        assert res.arrived is True
        assert ped.state == PedestrianLifecycleState.ARRIVED
        assert ped.speed_mps == 0.0
        assert math.isclose(ped.position.x, 10.0, abs_tol=1e-5)
        assert math.isclose(ped.position.y, 0.0, abs_tol=1e-5)

        # Inactive / arrived pedestrian does not advance further
        res2 = ped.step(dt=1.0)
        assert res2.old_state == PedestrianLifecycleState.ARRIVED
        assert res2.new_state == PedestrianLifecycleState.ARRIVED

    def test_zero_length_target_handling(self) -> None:
        ped = PedestrianAgent(
            pedestrian_id="ped_zero",
            initial_position=(5.0, 5.0),
            destination_point=(5.0, 5.0),
        )
        ped.start()
        res = ped.step(dt=0.5)

        assert res.arrived is True
        assert ped.state == PedestrianLifecycleState.ARRIVED
        assert ped.speed_mps == 0.0

    def test_pedestrian_capture_and_restore_state(self) -> None:
        ped = PedestrianAgent(
            pedestrian_id="ped_snap",
            initial_position=(0.0, 0.0),
            destination_point=(20.0, 0.0),
            config=PedestrianConfig(walking_speed_mps=1.0),
        )
        ped.start()
        ped.step(dt=5.0)

        snapshot = ped.capture_state()
        assert math.isclose(snapshot["position"].x, 5.0, abs_tol=1e-5)

        # Step further
        ped.step(dt=5.0)
        assert math.isclose(ped.position.x, 10.0, abs_tol=1e-5)

        # Restore from snapshot
        ped.restore_state(snapshot)
        assert math.isclose(ped.position.x, 5.0, abs_tol=1e-5)
        assert ped.state == PedestrianLifecycleState.WALKING
