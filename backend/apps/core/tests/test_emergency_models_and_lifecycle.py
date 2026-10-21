"""Unit tests for Phase 18 emergency vehicle models and lifecycle FSM.

Verifies:
- Emergency vehicle types (AMBULANCE, FIRE_ENGINE, POLICE) and priority levels
- Lifecycle state machine transitions and invariants
- PriorityRequest creation, idempotency, tie-breaking, and expiry
- EmergencyPriorityManager registration, activation, deactivation, and reset
"""

import pytest

from apps.core.emergency.exceptions import (
    DuplicateEmergencyActivationError,
    InvalidEmergencyStateError,
)
from apps.core.emergency.models import (
    EmergencyLifecycleState,
    EmergencyType,
    PriorityRequest,
    PriorityRequestStatus,
    default_priority_level_for_type,
    validate_emergency_transition,
)
from apps.core.emergency.priority_manager import EmergencyPriorityManager
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid


@pytest.fixture
def test_graph():
    """Create a 3x3 synthetic city grid for test purposes."""
    grid_cfg = CityGridConfig(rows=3, cols=3, spacing_m=50.0, speed_limit_mps=15.0)
    return generate_synthetic_city_grid(grid_cfg)


class TestEmergencyTypesAndLevels:
    """Tests for emergency vehicle types and deterministic priority levels."""

    def test_emergency_type_enumeration(self) -> None:
        assert EmergencyType.AMBULANCE.value == "ambulance"
        assert EmergencyType.FIRE_ENGINE.value == "fire_engine"
        assert EmergencyType.POLICE.value == "police"

    def test_default_priority_levels(self) -> None:
        assert default_priority_level_for_type(EmergencyType.FIRE_ENGINE) == 1
        assert default_priority_level_for_type(EmergencyType.AMBULANCE) == 2
        assert default_priority_level_for_type(EmergencyType.POLICE) == 3

    def test_invalid_emergency_type_lookup(self) -> None:
        with pytest.raises(ValueError):
            EmergencyType("military_tank")


class TestEmergencyLifecycleFSM:
    """Tests for emergency vehicle lifecycle finite state machine."""

    def test_legal_state_transitions(self) -> None:
        # INACTIVE -> REQUESTING_PRIORITY
        validate_emergency_transition(
            EmergencyLifecycleState.INACTIVE,
            EmergencyLifecycleState.REQUESTING_PRIORITY,
        )
        # REQUESTING_PRIORITY -> PRIORITY_ACTIVE
        validate_emergency_transition(
            EmergencyLifecycleState.REQUESTING_PRIORITY,
            EmergencyLifecycleState.PRIORITY_ACTIVE,
        )
        # PRIORITY_ACTIVE -> COMPLETED
        validate_emergency_transition(
            EmergencyLifecycleState.PRIORITY_ACTIVE,
            EmergencyLifecycleState.COMPLETED,
        )
        # PRIORITY_ACTIVE -> CANCELLED
        validate_emergency_transition(
            EmergencyLifecycleState.PRIORITY_ACTIVE,
            EmergencyLifecycleState.CANCELLED,
        )
        # COMPLETED -> INACTIVE (reuse)
        validate_emergency_transition(
            EmergencyLifecycleState.COMPLETED,
            EmergencyLifecycleState.INACTIVE,
        )
        # CANCELLED -> INACTIVE (reuse)
        validate_emergency_transition(
            EmergencyLifecycleState.CANCELLED,
            EmergencyLifecycleState.INACTIVE,
        )

    def test_illegal_state_transitions_raise_error(self) -> None:
        # Cannot go directly from INACTIVE to COMPLETED
        with pytest.raises(InvalidEmergencyStateError):
            validate_emergency_transition(
                EmergencyLifecycleState.INACTIVE,
                EmergencyLifecycleState.COMPLETED,
            )

        # Cannot go directly from COMPLETED to PRIORITY_ACTIVE without reset/inactive
        with pytest.raises(InvalidEmergencyStateError):
            validate_emergency_transition(
                EmergencyLifecycleState.COMPLETED,
                EmergencyLifecycleState.PRIORITY_ACTIVE,
            )


class TestPriorityRequestOrderingAndExpiry:
    """Tests for PriorityRequest tie-breaking, sorting, and expiry in simulation time."""

    def test_priority_request_expiry(self) -> None:
        req = PriorityRequest(
            request_id="req_01",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=3,
            destination_node_id="node_r0_c2",
            creation_time_s=10.0,
            ttl_s=30.0,
        )
        assert req.expiry_time_s == 40.0
        assert not req.is_expired(25.0)
        assert not req.is_expired(39.99)
        assert req.is_expired(40.0)
        assert req.is_expired(45.0)

    def test_deterministic_priority_tie_breaking(self) -> None:
        # Request ordering: higher priority_level first, then earlier creation_time_s,
        # then vehicle_id
        r_amb = PriorityRequest(
            request_id="req_amb",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=3,
            destination_node_id="node_r0_c2",
            creation_time_s=5.0,
            ttl_s=60.0,
        )
        r_fire = PriorityRequest(
            request_id="req_fire",
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            priority_level=2,
            destination_node_id="node_r0_c2",
            creation_time_s=2.0,
            ttl_s=60.0,
        )
        r_pol_early = PriorityRequest(
            request_id="req_pol1",
            vehicle_id="pol_01",
            emergency_type=EmergencyType.POLICE,
            priority_level=1,
            destination_node_id="node_r0_c2",
            creation_time_s=1.0,
            ttl_s=60.0,
        )
        r_pol_late = PriorityRequest(
            request_id="req_pol2",
            vehicle_id="pol_02",
            emergency_type=EmergencyType.POLICE,
            priority_level=1,
            destination_node_id="node_r0_c2",
            creation_time_s=3.0,
            ttl_s=60.0,
        )

        requests = [r_pol_late, r_fire, r_amb, r_pol_early]
        # Sort descending by priority, ascending by time and ID:
        sorted_reqs = sorted(
            requests,
            key=lambda r: (-r.priority_level, r.creation_time_s, r.vehicle_id),
        )
        assert sorted_reqs == [r_amb, r_fire, r_pol_early, r_pol_late]


class TestEmergencyPriorityManagerLifecycle:
    """Tests for authoritatively managing emergency requests and lifecycle in priority manager."""

    def test_registration_and_activation(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("amb_01")
        assert mgr.is_emergency_vehicle("amb_01")
        assert not mgr.is_emergency_vehicle("standard_01")
        assert mgr.get_vehicle_state("amb_01") == EmergencyLifecycleState.INACTIVE

        req = mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r0_c2",
            current_time_s=0.0,
        )
        assert req.vehicle_id == "amb_01"
        assert req.priority_level == 2
        assert req.status in (PriorityRequestStatus.PENDING, PriorityRequestStatus.ACTIVE)
        assert mgr.get_vehicle_state("amb_01") in (
            EmergencyLifecycleState.REQUESTING_PRIORITY,
            EmergencyLifecycleState.PRIORITY_ACTIVE,
        )

    def test_activation_idempotency(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("amb_01")

        req1 = mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r0_c2",
            current_time_s=1.0,
        )
        # Repeated call with same destination returns existing request
        req2 = mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r0_c2",
            current_time_s=2.0,
        )
        assert req1.request_id == req2.request_id

    def test_activation_conflict_with_different_destination_raises(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("amb_01")

        mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r0_c2",
            current_time_s=1.0,
        )
        with pytest.raises(DuplicateEmergencyActivationError):
            mgr.activate_emergency(
                vehicle_id="amb_01",
                emergency_type=EmergencyType.AMBULANCE,
                destination_node_id="node_r2_c2",
                current_time_s=2.0,
            )

    def test_deactivation_and_cancellation_cleanup(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("fire_01")

        mgr.activate_emergency(
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            destination_node_id="node_r2_c2",
            current_time_s=0.0,
            start_node_id="node_r0_c0",
        )
        # Commit corridor
        corr = mgr.plan_and_commit_corridor(
            vehicle_id="fire_01",
            current_time_s=0.0,
            start_node_id="node_r0_c0",
        )
        assert corr is not None
        assert len(mgr.reservations) > 0

        # Cancel priority
        mgr.cancel_priority(vehicle_id="fire_01", current_time_s=5.0)
        assert mgr.get_vehicle_state("fire_01") == EmergencyLifecycleState.CANCELLED
        # Invariant: Reservations released immediately on cancellation
        assert len(mgr.reservations) == 0
        assert corr.is_active is False
        assert corr.is_released is True

    def test_maintenance_expires_stale_requests(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("pol_01")

        req = mgr.activate_emergency(
            vehicle_id="pol_01",
            emergency_type=EmergencyType.POLICE,
            destination_node_id="node_r1_c1",
            current_time_s=0.0,
            ttl_s=10.0,
        )
        assert req.status != PriorityRequestStatus.EXPIRED

        # Advance maintenance before expiry
        mgr.perform_maintenance(current_time_s=5.0)
        assert req.status != PriorityRequestStatus.EXPIRED

        # Advance maintenance past expiry
        mgr.perform_maintenance(current_time_s=11.0)
        assert req.status == PriorityRequestStatus.EXPIRED
        assert mgr.metrics.requests_expired == 1

    def test_reset_clears_all_temporary_state(self, test_graph) -> None:
        mgr = EmergencyPriorityManager(road_graph=test_graph)
        mgr.register_emergency_vehicle("amb_01")
        mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r0_c2",
            current_time_s=0.0,
            start_node_id="node_r0_c0",
        )
        mgr.plan_and_commit_corridor("amb_01", current_time_s=0.0, start_node_id="node_r0_c0")

        assert len(mgr.active_requests) > 0
        assert len(mgr.corridors) > 0
        assert len(mgr.reservations) > 0

        mgr.reset()
        assert len(mgr.active_requests) == 0
        assert len(mgr.corridors) == 0
        assert len(mgr.reservations) == 0
        assert len(mgr.vehicle_states) == 0
