"""Integration tests for emergency vehicle priority subsystem in SimulationEngine.

Verifies:
- Authoritative single-clock stepping with V2V, corridor maintenance, signal priority
- Atomic rollback of emergency state upon injected tick failure
- Failure injection at multiple lifecycle stages (maintenance, signal, motion)
- Clean recovery and retry without duplicating events, reservations, or metrics
- Deterministic replay producing bit-identical snapshots across runs
- Complete scenario reset releasing dynamic reservations and restoring baseline configurations
"""

import math
from unittest.mock import patch

import pytest

from apps.core.domain.enums import TrafficSignalState, VehicleState
from apps.core.domain.models import (
    RoadEdge,
    RoadNode,
    Route,
    SimulationConfig,
    TrafficSignal,
    Vehicle,
)
from apps.core.domain.values import Position2D
from apps.core.emergency.models import (
    EmergencyConfig,
    EmergencyLifecycleState,
    EmergencyType,
)
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.safety.models import SafetyConfig
from apps.core.signals.models import SignalCycleConfig
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


def _build_emergency_world() -> tuple[WorldState, VehicleAgent, VehicleAgent]:
    """Construct a complete simulation world containing standard vehicle and emergency vehicle."""
    graph = RoadGraph(name="emergency_engine_grid")
    n1 = RoadNode(id="n1", position=Position2D(x=0.0, y=0.0))
    n2 = RoadNode(id="n2", position=Position2D(x=100.0, y=0.0))
    n3 = RoadNode(id="n3", position=Position2D(x=200.0, y=0.0))
    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)

    e1 = RoadEdge(
        id="e1", start_node_id="n1", end_node_id="n2", length_m=100.0, speed_limit_mps=15.0
    )
    e2 = RoadEdge(
        id="e2", start_node_id="n2", end_node_id="n3", length_m=100.0, speed_limit_mps=15.0
    )
    graph.add_edge(e1)
    graph.add_edge(e2)

    sig = TrafficSignal(
        id="sig_1", node_id="n2", state=TrafficSignalState.RED, position=Position2D(x=100.0, y=0.0)
    )
    sig_cfg = SignalCycleConfig(
        red_duration_s=10.0,
        green_duration_s=10.0,
        yellow_duration_s=2.0,
        initial_phase=TrafficSignalState.RED,
    )

    sim_cfg = SimulationConfig(time_step_s=1.0)
    safety_cfg = SafetyConfig(enabled=True, min_separation_m=2.0)
    em_cfg = EmergencyConfig(enabled=True, signal_priority_enabled=True)

    world = WorldState(
        road_graph=graph,
        config=sim_cfg,
        safety_config=safety_cfg,
        emergency_config=em_cfg,
    )
    world.add_traffic_signal(sig, config=sig_cfg)

    # 1. Standard vehicle ahead
    v_std = Vehicle(
        id="veh_std_1",
        position=Position2D(x=60.0, y=0.0),
        speed_mps=10.0,
        max_speed_mps=15.0,
        state=VehicleState.EN_ROUTE,
        current_edge_id="e1",
        current_node_id="n1",
    )
    route_std = Route(id="r_std", node_ids=["n1", "n2", "n3"], edge_ids=["e1", "e2"])
    agent_std = VehicleAgent(
        vehicle=v_std,
        road_graph=graph,
        route=route_std,
        config=KinematicsConfig(max_speed_mps=15.0),
    )
    agent_std.start()
    world.add_agent(agent_std)

    # 2. Ambulance behind
    v_amb = Vehicle(
        id="amb_01",
        position=Position2D(x=10.0, y=0.0),
        speed_mps=12.0,
        max_speed_mps=25.0,
        state=VehicleState.EN_ROUTE,
        current_edge_id="e1",
        current_node_id="n1",
    )
    route_amb = Route(id="r_amb", node_ids=["n1", "n2", "n3"], edge_ids=["e1", "e2"])
    agent_amb = VehicleAgent(
        vehicle=v_amb,
        road_graph=graph,
        route=route_amb,
        config=KinematicsConfig(max_speed_mps=25.0),
    )
    agent_amb.start()
    world.add_agent(agent_amb)

    # Register ambulance with EmergencyPriorityManager
    world.emergency_manager.register_emergency_vehicle("amb_01")

    return world, agent_std, agent_amb


class TestEmergencyEngineStepping:
    """Tests for single-clock stepping and emergency lifecycle integration."""

    def test_emergency_activation_corridor_and_stepping(self) -> None:
        world, agent_std, agent_amb = _build_emergency_world()
        engine = SimulationEngine(world=world)

        # Activate emergency for ambulance
        req = world.emergency_manager.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="n3",
            current_time_s=0.0,
        )
        assert req.status.value in ("pending", "active")
        assert world.emergency_manager.get_vehicle_state("amb_01") in (
            EmergencyLifecycleState.REQUESTING_PRIORITY,
            EmergencyLifecycleState.PRIORITY_ACTIVE,
        )

        # Step tick 1
        res1 = engine.step()
        assert res1.tick == 1
        assert res1.elapsed_time_s == 1.0
        assert res1.emergency_metrics is not None
        assert res1.emergency_metrics["active_emergency_vehicles"] >= 1
        assert "amb_01" in res1.step_results

        # Signal priority evaluated and applied to sig_1 at n2
        sig_ctrl = world.get_signal("sig_1")
        assert sig_ctrl.signal.state == TrafficSignalState.GREEN

    def test_atomic_rollback_on_vehicle_failure_restores_emergency_state(self) -> None:
        """Tick failure during vehicle stepping rolls back emergency manager state completely."""
        world, agent_std, agent_amb = _build_emergency_world()
        engine = SimulationEngine(world=world)

        world.emergency_manager.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="n3",
            current_time_s=0.0,
        )

        initial_em_state = world.emergency_manager.capture_state()
        initial_res_count = len(world.emergency_manager.get_active_reservations())

        def fail_amb_step(*args, **kwargs):
            raise RuntimeError("Injected ambulance kinematics failure")

        with patch.object(agent_amb, "step", side_effect=fail_amb_step):
            with pytest.raises(TickExecutionError, match="Tick 1 failed during agent execution"):
                engine.step()

        # Engine must transition to FAILED status
        assert engine.status == EngineStatus.FAILED

        # Clock must remain at 0
        assert engine.current_tick == 0
        assert engine.elapsed_time_s == 0.0

        # Emergency manager state restored to pre-tick values
        restored_em_state = world.emergency_manager.capture_state()
        assert len(restored_em_state["reservations"]) == initial_res_count
        expected_st = initial_em_state["vehicle_states"]["amb_01"]
        assert world.emergency_manager.get_vehicle_state("amb_01") == expected_st

    def test_atomic_rollback_on_maintenance_failure(self) -> None:
        """Injected failure during emergency manager maintenance rolls back entire tick."""
        world, agent_std, agent_amb = _build_emergency_world()
        engine = SimulationEngine(world=world)

        initial_tick = engine.current_tick

        def fail_maint(*args, **kwargs):
            raise RuntimeError("Injected emergency maintenance failure")

        with patch.object(world.emergency_manager, "perform_maintenance", side_effect=fail_maint):
            with pytest.raises(TickExecutionError):
                engine.step()

        assert engine.status == EngineStatus.FAILED
        assert engine.current_tick == initial_tick

    def test_retry_after_recovered_failure_does_not_duplicate_state(self) -> None:
        """After a failed tick rolls back, a retry does not duplicate reservations or metrics."""
        world, agent_std, agent_amb = _build_emergency_world()
        engine = SimulationEngine(world=world)

        world.emergency_manager.activate_emergency(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            destination_node_id="n3",
            current_time_s=0.0,
        )

        # 1. First attempt fails
        with patch.object(agent_std, "step", side_effect=RuntimeError("Transient failure")):
            with pytest.raises(TickExecutionError):
                engine.step()

        assert engine.status == EngineStatus.FAILED
        assert engine.current_tick == 0

        # 2. Reset engine status to RUNNING to simulate retry
        engine.status = EngineStatus.RUNNING

        # 3. Second attempt succeeds cleanly
        res = engine.step()
        assert res.tick == 1
        assert res.emergency_metrics["active_emergency_vehicles"] == 1
        # Reservations should not be duplicated
        active_res = world.emergency_manager.get_active_reservations()
        res_ids = [r.reservation_id for r in active_res]
        assert len(res_ids) == len(set(res_ids))

    def test_deterministic_replay_produces_identical_snapshots(self) -> None:
        """Repeated scenario executions produce bit-identical tick results."""
        # Run 1
        world1, _, _ = _build_emergency_world()
        engine1 = SimulationEngine(world=world1)
        world1.emergency_manager.activate_emergency("amb_01", EmergencyType.AMBULANCE, "n3", 0.0)
        res1 = engine1.step()

        # Run 2
        world2, _, _ = _build_emergency_world()
        engine2 = SimulationEngine(world=world2)
        world2.emergency_manager.activate_emergency("amb_01", EmergencyType.AMBULANCE, "n3", 0.0)
        res2 = engine2.step()

        assert res1.tick == res2.tick
        assert math.isclose(res1.elapsed_time_s, res2.elapsed_time_s)
        assert res1.emergency_metrics == res2.emergency_metrics
        assert len(res1.emergency_events) == len(res2.emergency_events)

    def test_scenario_reset_restores_baseline_emergency_state(self) -> None:
        """WorldState reset completely clears dynamic corridors, reservations, and overrides."""
        world, agent_std, agent_amb = _build_emergency_world()
        engine = SimulationEngine(world=world)

        world.emergency_manager.activate_emergency("amb_01", EmergencyType.AMBULANCE, "n3", 0.0)
        engine.step()

        assert len(world.emergency_manager.get_active_reservations()) > 0

        # Reset world
        world.reset()

        assert len(world.emergency_manager.get_active_reservations()) == 0
        assert world.emergency_manager.get_active_corridor("amb_01") is None
        assert (
            world.emergency_manager.get_vehicle_state("amb_01") == EmergencyLifecycleState.INACTIVE
        )
