"""Tests for vehicle-pedestrian collision detection, safe separation, and safety overrides.

Verifies:
- OBB-based geometric overlap detection between vehicle and pedestrian agents using SAT.
- Near-miss detection within safe lateral and headway envelopes.
- Time-to-collision (TTC) and closing speed estimation with pedestrian entities.
- Safe separation maintenance without unwarranted braking interventions.
- SafetyManager staging emergency or strong braking overrides with pedestrian IDs recorded.
- Multi-vehicle and multi-pedestrian conflict detection order-independence.
- Accurate reporting of unavoidable collisions without false prevention claims.
"""

import math

import pytest

from apps.core.domain.models import RoadEdge, RoadNode, Route, Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.models import PedestrianLifecycleState
from apps.core.safety.detection import CollisionDetector
from apps.core.safety.manager import SafetyManager
from apps.core.safety.models import (
    CollisionRiskLevel,
    SafetyActionType,
    SafetyConfig,
    SafetyEventType,
)


@pytest.fixture
def base_safety_config() -> SafetyConfig:
    """Fixture providing safety configuration for vehicle-pedestrian evaluation."""
    return SafetyConfig(
        enabled=True,
        min_separation_m=2.0,
        reaction_time_s=0.5,
        ttc_imminent_s=0.8,
        ttc_high_risk_s=1.8,
        ttc_caution_s=3.0,
        near_miss_distance_m=2.0,
        emergency_decel_mps2=6.0,
        strong_decel_mps2=4.0,
        gentle_decel_mps2=2.0,
        pedestrian_length_m=0.6,
        pedestrian_width_m=0.6,
        log_events=True,
    )


class TestPedestrianCollisionAndSafety:
    """Tests for pedestrian safety detection and manager integration."""

    def test_vehicle_pedestrian_obb_overlap(self, base_safety_config: SafetyConfig) -> None:
        """Geometric overlap occurs when vehicle and pedestrian bounding boxes intersect."""
        detector = CollisionDetector(config=base_safety_config)

        # Vehicle centered at (50.0, 0.0), length 4.5m, width 1.8m
        # Footprint: x in [47.75, 52.25], y in [-0.9, 0.9]
        v = Vehicle(id="veh_01", position=Position2D(x=50.0, y=0.0), speed_mps=5.0, heading_rad=0.0)

        # Pedestrian directly inside vehicle footprint at (50.5, 0.2)
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=50.5, y=0.2),
            state=PedestrianLifecycleState.CROSSING,
        )

        conflict = detector.evaluate_vehicle_pedestrian(vehicle=v, pedestrian=ped)
        assert conflict.is_overlap is True
        assert conflict.risk_level == CollisionRiskLevel.COLLISION
        assert conflict.is_pedestrian_conflict is True
        assert conflict.pedestrian_id == "ped_01"
        assert conflict.recommended_action_a == SafetyActionType.EMERGENCY_BRAKE
        assert math.isclose(conflict.distance_m, 0.0, abs_tol=1e-5)

    def test_vehicle_pedestrian_near_miss_detection(self, base_safety_config: SafetyConfig) -> None:
        """Vehicle passing in close proximity to pedestrian triggers a near-miss classification."""
        detector = CollisionDetector(config=base_safety_config)

        # Vehicle at (45.0, 0.0) moving East at 10.0 m/s (half length = 2.25m -> front at x=47.25m)
        v = Vehicle(
            id="veh_01",
            position=Position2D(x=45.0, y=0.0),
            speed_mps=10.0,
            heading_rad=0.0,
        )

        # Pedestrian at (48.0, 0.0) directly ahead -> separation is only ~0.45m!
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=48.0, y=0.0),
            state=PedestrianLifecycleState.CROSSING,
        )

        conflict = detector.evaluate_vehicle_pedestrian(vehicle=v, pedestrian=ped)
        assert conflict.is_overlap is False
        assert conflict.risk_level in (CollisionRiskLevel.IMMINENT, CollisionRiskLevel.HIGH_RISK)
        assert conflict.separation_violated is True
        assert conflict.ttc_s is not None and conflict.ttc_s < 1.0

    def test_closing_speed_and_ttc_with_pedestrian(self, base_safety_config: SafetyConfig) -> None:
        """TTC is accurately estimated based on vehicle speed and pedestrian separation."""
        detector = CollisionDetector(config=base_safety_config)

        # Vehicle at x=20.0 moving East at 10.0 m/s
        v = Vehicle(
            id="veh_01",
            position=Position2D(x=20.0, y=0.0),
            speed_mps=10.0,
            heading_rad=0.0,
        )
        # Pedestrian at x=50.0 stationary
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=50.0, y=0.0),
            state=PedestrianLifecycleState.CROSSING,
        )

        conflict = detector.evaluate_vehicle_pedestrian(vehicle=v, pedestrian=ped)
        assert math.isclose(conflict.closing_speed_mps, 10.0, abs_tol=0.1)
        # Distance between bounding boxes: 30 - 2.25 - 0.3 = 27.45m
        assert conflict.ttc_s is not None
        assert math.isclose(conflict.ttc_s, 27.45 / 10.0, abs_tol=0.2)

    def test_safe_separation_no_unwarranted_braking(self, base_safety_config: SafetyConfig) -> None:
        """Vehicles sufficiently separated from pedestrians incur no braking action."""
        detector = CollisionDetector(config=base_safety_config)

        # Vehicle at x=0.0, y=0.0 heading East
        v = Vehicle(id="veh_01", position=Position2D(x=0.0, y=0.0), speed_mps=8.0, heading_rad=0.0)
        # Pedestrian far off at x=200.0, y=50.0
        ped = PedestrianAgent(
            pedestrian_id="ped_01",
            position=Position2D(x=200.0, y=50.0),
            state=PedestrianLifecycleState.WALKING,
        )

        conflict = detector.evaluate_vehicle_pedestrian(vehicle=v, pedestrian=ped)
        assert conflict.risk_level == CollisionRiskLevel.SAFE
        assert conflict.recommended_action_a == SafetyActionType.NONE
        assert conflict.action_a_decel == 0.0

    def test_safety_manager_pedestrian_event_logging(
        self, base_safety_config: SafetyConfig
    ) -> None:
        """SafetyManager logs SafetyEvent records with pedestrian_id and appropriate event type."""
        manager = SafetyManager(config=base_safety_config)

        graph = RoadGraph(name="test_graph")
        graph.add_node(RoadNode(id="n1", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=100.0, y=0.0)))
        graph.add_edge(
            RoadEdge(
                id="e1",
                start_node_id="n1",
                end_node_id="n2",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )

        v = Vehicle(
            id="veh_lead",
            position=Position2D(x=0.0, y=0.0),
            speed_mps=10.0,
            heading_rad=0.0,
        )
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])
        agent = VehicleAgent(vehicle=v, road_graph=graph, route=route)
        agent.start()
        # Explicitly place vehicle in close proximity to crossing pedestrian
        agent.vehicle.position = Position2D(x=45.0, y=0.0)

        # Crossing pedestrian directly in path
        ped = PedestrianAgent(
            pedestrian_id="ped_crosser",
            position=Position2D(x=47.5, y=0.0),
            state=PedestrianLifecycleState.CROSSING,
        )

        overrides, pairs, events = manager.evaluate_and_stage(
            agents=[agent],
            current_time_s=5.0,
            pedestrians=[ped],
        )

        assert "veh_lead" in overrides
        assert overrides["veh_lead"].action_type in (
            SafetyActionType.EMERGENCY_BRAKE,
            SafetyActionType.STRONG_BRAKE,
        )
        assert len(events) > 0
        ped_evt = next((e for e in events if e.pedestrian_id == "ped_crosser"), None)
        assert ped_evt is not None
        assert ped_evt.vehicle_ids == ("veh_lead",)
        assert ped_evt.sim_time_s == 5.0

    def test_multi_vehicle_multi_pedestrian_conflict_evaluation(
        self, base_safety_config: SafetyConfig
    ) -> None:
        """Multiple vehicles and pedestrians evaluate deterministically without order bias."""
        detector = CollisionDetector(config=base_safety_config)

        graph = RoadGraph(name="multi_graph")
        graph.add_node(RoadNode(id="n1", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=100.0, y=0.0)))
        graph.add_edge(
            RoadEdge(
                id="e1",
                start_node_id="n1",
                end_node_id="n2",
                length_m=100.0,
                speed_limit_mps=15.0,
            )
        )
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])

        ag1 = VehicleAgent(
            vehicle=Vehicle(id="v1", position=Position2D(x=0.0, y=0.0), speed_mps=5.0),
            road_graph=graph,
            route=route,
        )
        ag2 = VehicleAgent(
            vehicle=Vehicle(id="v2", position=Position2D(x=0.0, y=0.0), speed_mps=5.0),
            road_graph=graph,
            route=route,
        )
        ag1.start()
        ag2.start()
        ag1.vehicle.position = Position2D(x=10.0, y=0.0)
        ag2.vehicle.position = Position2D(x=30.0, y=0.0)

        p1 = PedestrianAgent(
            pedestrian_id="p1",
            position=Position2D(x=12.0, y=0.0),
            state=PedestrianLifecycleState.CROSSING,
        )
        p2 = PedestrianAgent(
            pedestrian_id="p2",
            position=Position2D(x=50.0, y=0.0),
            state=PedestrianLifecycleState.WAITING_TO_CROSS,
        )

        conflicts1 = detector.detect_all_conflicts([ag1, ag2], pedestrians=[p1, p2])
        conflicts2 = detector.detect_all_conflicts([ag2, ag1], pedestrians=[p2, p1])

        # Conflict count: 1 vehicle-vehicle pair + (2 vehicles * 2 pedestrians) = 5 pairs
        assert len(conflicts1) == 5
        assert len(conflicts2) == 5

        # Compare pair keys
        def pair_key(c):
            return (c.vehicle_a_id, c.vehicle_b_id, c.is_pedestrian_conflict)

        expected = sorted([pair_key(c) for c in conflicts2])
        actual = sorted([pair_key(c) for c in conflicts1])
        assert actual == expected

    def test_unavoidable_collision_truthfully_recorded(
        self, base_safety_config: SafetyConfig
    ) -> None:
        """Physical overlap at high speed and zero distance is truthfully reported as COLLISION."""
        manager = SafetyManager(config=base_safety_config)

        graph = RoadGraph(name="unavoidable_graph")
        graph.add_node(RoadNode(id="n1", position=Position2D(x=0.0, y=0.0)))
        graph.add_node(RoadNode(id="n2", position=Position2D(x=100.0, y=0.0)))
        graph.add_edge(
            RoadEdge(
                id="e1",
                start_node_id="n1",
                end_node_id="n2",
                length_m=100.0,
                speed_limit_mps=25.0,
            )
        )
        route = Route(id="r1", node_ids=["n1", "n2"], edge_ids=["e1"])

        # Vehicle traveling at high speed (20 m/s) with max_speed_mps=30.0
        agent = VehicleAgent(
            vehicle=Vehicle(
                id="fast_veh",
                position=Position2D(x=0.0, y=0.0),
                speed_mps=20.0,
                max_speed_mps=30.0,
            ),
            road_graph=graph,
            route=route,
        )
        agent.start()
        agent.vehicle.position = Position2D(x=50.0, y=0.0)

        # Pedestrian directly overlapping center
        ped = PedestrianAgent(
            pedestrian_id="trapped_ped",
            position=Position2D(x=50.0, y=0.0),
            state=PedestrianLifecycleState.CROSSING,
        )

        overrides, pairs, events = manager.evaluate_and_stage(
            agents=[agent],
            current_time_s=1.0,
            pedestrians=[ped],
        )

        collision_evts = [e for e in events if e.is_overlap]
        assert len(collision_evts) == 1
        assert collision_evts[0].event_type == SafetyEventType.COLLISION
        assert collision_evts[0].pedestrian_id == "trapped_ped"
        assert collision_evts[0].vehicle_ids == ("fast_veh",)
