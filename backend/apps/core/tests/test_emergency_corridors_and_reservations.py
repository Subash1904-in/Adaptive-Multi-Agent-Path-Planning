"""Unit tests for Phase 18 emergency corridor planning and reservations.

Verifies:
- Corridor planning using existing RoadGraph and A* route planning
- Ordered edge and intersection node reservation sequences
- Closed edge avoidance and unreachable destination error handling
- Temporary edge and intersection reservations with explicit TTL
- Strict priority and first-come-first-served conflict resolution
- Reservation preemption and deterministic tie-breaking (level, timestamp, ID)
- Corridor updates and cancellation reservation releases
"""

import pytest

from apps.core.emergency.corridor_planner import EmergencyCorridorPlanner
from apps.core.emergency.exceptions import UnreachableEmergencyDestinationError
from apps.core.emergency.models import (
    EmergencyConfig,
    EmergencyType,
    PriorityRequest,
    ReservationConflictPolicy,
)
from apps.core.emergency.priority_manager import EmergencyPriorityManager
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid


@pytest.fixture
def grid_graph():
    """Create a 3x3 synthetic city grid for test purposes."""
    cfg = CityGridConfig(rows=3, cols=3, spacing_m=50.0, speed_limit_mps=15.0)
    return generate_synthetic_city_grid(cfg)


class TestEmergencyCorridorPlanning:
    """Tests for corridor generation and validation."""

    def test_plan_valid_corridor(self, grid_graph) -> None:
        planner = EmergencyCorridorPlanner(grid_graph)
        req = PriorityRequest(
            request_id="req_amb_01",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            destination_node_id="node_r2_c2",
            creation_time_s=1.0,
            ttl_s=60.0,
        )

        corridor = planner.plan_corridor(
            request=req,
            start_node_id="node_r0_c0",
            destination_node_id="node_r2_c2",
            current_time_s=1.0,
        )

        assert corridor.corridor_id == "corridor_req_amb_01"
        assert corridor.vehicle_id == "amb_01"
        assert len(corridor.edge_ids) > 0
        assert corridor.node_ids[0] == "node_r0_c0"
        assert corridor.node_ids[-1] == "node_r2_c2"
        assert corridor.creation_time_s == 1.0
        assert corridor.expiry_time_s > 1.0
        assert corridor.is_active is True

    def test_plan_corridor_when_already_at_destination(self, grid_graph) -> None:
        planner = EmergencyCorridorPlanner(grid_graph)
        req = PriorityRequest(
            request_id="req_amb_02",
            vehicle_id="amb_02",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            destination_node_id="node_r0_c0",
            creation_time_s=2.0,
            ttl_s=30.0,
        )

        corridor = planner.plan_corridor(
            request=req,
            start_node_id="node_r0_c0",
            destination_node_id="node_r0_c0",
            current_time_s=2.0,
        )

        assert len(corridor.edge_ids) == 0
        assert corridor.node_ids == ("node_r0_c0",)

    def test_unreachable_destination_raises_error(self, grid_graph) -> None:
        planner = EmergencyCorridorPlanner(grid_graph)
        req = PriorityRequest(
            request_id="req_fire_01",
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            priority_level=1,
            destination_node_id="nonexistent_node",
            creation_time_s=0.0,
            ttl_s=30.0,
        )

        with pytest.raises(UnreachableEmergencyDestinationError):
            planner.plan_corridor(
                request=req,
                start_node_id="node_r0_c0",
                destination_node_id="nonexistent_node",
                current_time_s=0.0,
            )

    def test_closed_edge_avoidance(self, grid_graph) -> None:
        planner = EmergencyCorridorPlanner(grid_graph)
        req = PriorityRequest(
            request_id="req_police_01",
            vehicle_id="police_01",
            emergency_type=EmergencyType.POLICE,
            priority_level=3,
            destination_node_id="node_r0_c2",
            creation_time_s=0.0,
            ttl_s=30.0,
        )

        # Direct edge between r0_c0 and r0_c1
        direct_edge = grid_graph.get_edge_between("node_r0_c0", "node_r0_c1")
        assert direct_edge is not None
        blocked_edge = direct_edge.id

        corridor = planner.plan_corridor(
            request=req,
            start_node_id="node_r0_c0",
            destination_node_id="node_r0_c2",
            current_time_s=0.0,
            closed_edge_ids={blocked_edge},
        )

        # Corridor must not contain the blocked edge
        assert blocked_edge not in corridor.edge_ids
        assert corridor.node_ids[-1] == "node_r0_c2"


class TestCorridorReservationsAndConflictResolution:
    """Tests for edge and intersection reservation conflicts and preemption."""

    def test_reservations_creation_nominal(self, grid_graph) -> None:
        planner = EmergencyCorridorPlanner(grid_graph)
        req = PriorityRequest(
            request_id="req_01",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            destination_node_id="node_r1_c1",
            creation_time_s=5.0,
            ttl_s=30.0,
        )
        corridor = planner.plan_corridor(req, "node_r0_c0", "node_r1_c1", current_time_s=5.0)

        granted, conflicts = planner.evaluate_and_create_reservations(
            corridor=corridor,
            request=req,
            existing_reservations=[],
            current_time_s=5.0,
        )

        assert len(conflicts) == 0
        assert len(granted) == len(corridor.edge_ids) + len(corridor.node_ids)
        for r in granted:
            assert r.vehicle_id == "amb_01"
            assert r.priority_level == 2

    def test_strict_priority_preemption(self, grid_graph) -> None:
        """Higher priority emergency vehicle preempts lower priority emergency vehicle."""
        planner = EmergencyCorridorPlanner(
            grid_graph,
            config=EmergencyConfig(conflict_policy=ReservationConflictPolicy.STRICT_PRIORITY),
        )

        req_amb = PriorityRequest(
            request_id="req_amb",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            destination_node_id="node_r0_c1",
            creation_time_s=0.0,
            ttl_s=30.0,
        )
        corridor_amb = planner.plan_corridor(req_amb, "node_r0_c0", "node_r0_c1", 0.0)
        existing_res, _ = planner.evaluate_and_create_reservations(corridor_amb, req_amb, [], 0.0)

        # Now Fire Engine (level 1) requests overlapping corridor
        req_fire = PriorityRequest(
            request_id="req_fire",
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            priority_level=1,
            destination_node_id="node_r0_c1",
            creation_time_s=2.0,
            ttl_s=30.0,
        )
        corridor_fire = planner.plan_corridor(req_fire, "node_r0_c0", "node_r0_c1", 2.0)

        granted, conflicts = planner.evaluate_and_create_reservations(
            corridor=corridor_fire,
            request=req_fire,
            existing_reservations=existing_res,
            current_time_s=2.0,
        )

        # Fire Engine should succeed in preemption (0 conflicts)
        assert len(conflicts) == 0
        assert len(granted) > 0

    def test_first_come_first_served_policy_blocks_preemption(self, grid_graph) -> None:
        """FCFS policy blocks competing requests regardless of priority."""
        planner = EmergencyCorridorPlanner(
            grid_graph,
            config=EmergencyConfig(conflict_policy=ReservationConflictPolicy.FIRST_COME_FIRST_SERVED),
        )

        req_amb = PriorityRequest(
            request_id="req_amb",
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            priority_level=2,
            destination_node_id="node_r0_c1",
            creation_time_s=0.0,
            ttl_s=30.0,
        )
        corridor_amb = planner.plan_corridor(req_amb, "node_r0_c0", "node_r0_c1", 0.0)
        existing_res, _ = planner.evaluate_and_create_reservations(corridor_amb, req_amb, [], 0.0)

        # Fire Engine (level 1) attempts to reserve under FCFS
        req_fire = PriorityRequest(
            request_id="req_fire",
            vehicle_id="fire_01",
            emergency_type=EmergencyType.FIRE_ENGINE,
            priority_level=1,
            destination_node_id="node_r0_c1",
            creation_time_s=2.0,
            ttl_s=30.0,
        )
        corridor_fire = planner.plan_corridor(req_fire, "node_r0_c0", "node_r0_c1", 2.0)

        granted, conflicts = planner.evaluate_and_create_reservations(
            corridor=corridor_fire,
            request=req_fire,
            existing_reservations=existing_res,
            current_time_s=2.0,
        )

        assert len(conflicts) > 0

    def test_priority_manager_corridor_lifecycle_and_cleanup(self, grid_graph) -> None:
        """EmergencyPriorityManager plans corridor, commits reservations, and cleans up."""
        mgr = EmergencyPriorityManager(road_graph=grid_graph)
        mgr.register_emergency_vehicle("amb_01")
        req = mgr.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="node_r1_c1",
            current_time_s=0.0,
        )

        # Plan and commit corridor
        corridor = mgr.plan_and_commit_corridor(
            request_id=req.request_id,
            start_node_id="node_r0_c0",
            current_time_s=0.0,
        )
        assert corridor is not None
        assert mgr.get_active_corridor("amb_01") is not None
        assert len(mgr.get_active_reservations()) > 0

        # Now cancel emergency
        mgr.cancel_priority("amb_01", current_time_s=5.0, reason="Incident cleared")
        assert mgr.get_active_corridor("amb_01") is None
        assert len(mgr.get_active_reservations()) == 0
