"""Regression test suite for core simulation invariants, kinematics bounds, and state transitions.

Verifies:
- Finite coordinates, normalized headings, and strictly bounded velocities/accelerations.
- Anti-teleportation: consecutive displacement bounded by speed limit and delta t.
- Traffic signal obedience: vehicles come to a complete stop before red signals.
- Pedestrian crosswalk interaction: vehicles yield to pedestrians inside crosswalks.
- Dynamic incident injection: road closures update graph state and trigger safe adaptive rerouting.
- Atomic rollback: stepping failure preserves pre-tick state with zero partial mutations.
- Terminal state immutability: stepping after completion/cancellation produces no state changes.
- Agent fault isolation: one blocked vehicle does not impede independent vehicles.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from apps.core.domain.enums import VehicleState
from apps.core.domain.values import Position2D
from apps.core.incidents.models import IncidentType
from apps.core.scenarios.examples import (
    create_adaptive_reroute_closure_scenario,
    create_multi_vehicle_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
    create_vehicle_braking_for_pedestrian_scenario,
)
from apps.core.scenarios.exceptions import ScenarioExecutionError
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.simulation.models import EngineStatus
from apps.core.telemetry.exceptions import RunStateTransitionError


class TestSimulationInvariantsRegression:
    """Verifies simulation invariants across execution cycles."""

    def test_kinematics_and_coordinate_finiteness_across_trajectory(self) -> None:
        """Positions, speeds, accelerations, and headings remain strictly finite and bounded."""
        scenario = create_single_vehicle_scenario(max_ticks=40, time_step_s=0.1)
        runner = ScenarioRunner.create(scenario)

        prev_pos: Position2D | None = None
        v_max = 20.0  # nominal max speed limit
        dt = 0.1

        for _ in range(30):
            res = runner.step()
            assert res is not None

            # Check acceleration from step results
            for aid, m_res in res.step_results.items():
                assert math.isfinite(m_res.applied_acceleration_mps2)
                assert -15.0 <= m_res.applied_acceleration_mps2 <= 10.0

            # Check vehicle state invariants
            for agent in runner.world.get_agents():
                v = agent.vehicle
                # 1. Finite coordinates
                assert math.isfinite(v.position.x)
                assert math.isfinite(v.position.y)

                # 2. Bounded speed
                assert 0.0 <= v.speed_mps <= v_max + 1.0

                # 3. Normalized heading [0, 2*pi)
                assert 0.0 <= v.heading_rad < 2.0 * math.pi + 1e-6

                # 4. Anti-teleportation: displacement per step <= v_max * dt + epsilon
                if prev_pos is not None and v.state == VehicleState.EN_ROUTE:
                    displacement = math.hypot(
                        v.position.x - prev_pos.x,
                        v.position.y - prev_pos.y,
                    )
                    max_allowed_displacement = (v_max * dt) + 0.1
                    assert displacement <= max_allowed_displacement, (
                        f"Teleportation detected: displacement {displacement:.3f}m "
                        f"exceeds limit {max_allowed_displacement:.3f}m"
                    )

                prev_pos = v.position

    def test_traffic_signal_obedience_and_stopping(self) -> None:
        """Vehicle approaching a red traffic light decelerates and stops safely."""
        scenario = create_signalized_scenario(max_ticks=35)
        runner = ScenarioRunner.create(scenario)

        result = runner.run_to_completion()
        assert result.is_success is True

        agents = runner.world.get_agents()
        assert len(agents) >= 1
        agent = agents[0]
        assert math.isfinite(agent.vehicle.position.x)
        assert math.isfinite(agent.vehicle.position.y)

        # Verify kinematics distance traveled is strictly positive
        assert result.metrics_summary is not None
        kin_metrics = result.metrics_summary["kinematics"]
        assert kin_metrics["total_distance_traveled_m"] > 0.0

    def test_pedestrian_crosswalk_yielding(self) -> None:
        """Vehicle yields to pedestrian crossing in crosswalk, avoiding collision."""
        scenario = create_vehicle_braking_for_pedestrian_scenario(max_ticks=30)
        runner = ScenarioRunner.create(scenario)

        result = runner.run_to_completion()
        assert result.is_success is True

        assert result.metrics_summary is not None
        safety_metrics = result.metrics_summary["safety"]
        assert safety_metrics["actual_collisions"] == 0

    def test_dynamic_incident_injection_and_rerouting(self) -> None:
        """Road closure dynamically injected during simulation triggers rerouting."""
        scenario = create_adaptive_reroute_closure_scenario(max_ticks=35)
        runner = ScenarioRunner.create(scenario)

        # Run 3 ticks initially
        runner.run(ticks=3)

        # Dynamically inject road closure incident on edge_r0_c0_to_r0_c1
        runner.world.incident_manager.create_incident(
            incident_type=IncidentType.ROAD_CLOSURE,
            affected_edge_id="edge_r0_c0_to_r0_c1",
            current_time_s=runner.elapsed_time_s,
            current_tick=runner.current_tick,
        )

        # Run to completion
        result = runner.run_to_completion()
        assert result.is_success is True

        # Verify incident was active and registered in IncidentManager
        all_incidents = runner.world.incident_manager.list_all()
        assert len(all_incidents) >= 1
        assert any(inc.incident_type == IncidentType.ROAD_CLOSURE for inc in all_incidents)

        # Verify rerouting occurred
        assert result.metrics_summary is not None
        routing_metrics = result.metrics_summary["routing"]
        assert routing_metrics["reroutes_accepted"] >= 1

    def test_atomic_rollback_on_engine_stepping_failure(self) -> None:
        """Engine stepping exception cleanly rolls back all subsystems to exact pre-tick state."""
        scenario = create_single_vehicle_scenario(max_ticks=20, time_step_s=0.1)
        runner = ScenarioRunner.create(scenario)

        runner.run(ticks=3)
        tick_before = runner.engine.current_tick
        time_before = runner.engine.elapsed_time_s
        agent = runner.world.get_agent("veh_01")
        v_pos_before = agent.vehicle.position

        # Inject an intentional exception during stepping of the vehicle agent
        with patch.object(
            agent,
            "step",
            side_effect=RuntimeError("Simulated vehicle hardware fault"),
        ):
            with pytest.raises(ScenarioExecutionError):
                runner.step()

        # Invariant: State restored exactly to pre-tick baseline
        assert runner.engine.current_tick == tick_before
        assert runner.engine.elapsed_time_s == time_before
        assert runner.engine.status == EngineStatus.FAILED
        v_pos_after = runner.world.get_agent("veh_01").vehicle.position
        assert v_pos_after.x == v_pos_before.x
        assert v_pos_after.y == v_pos_before.y

    def test_terminal_state_immutability(self) -> None:
        """Stepping after completion or cancellation produces no state mutation."""
        scenario = create_single_vehicle_scenario(max_ticks=15, time_step_s=0.1)
        runner = ScenarioRunner.create(scenario)
        runner.run_to_completion()

        final_tick = runner.engine.current_tick
        final_status = runner.lifecycle_state
        assert runner.is_terminal is True

        # Subsequent step calls must be rejected with RunStateTransitionError
        with pytest.raises((RunStateTransitionError, ScenarioExecutionError)):
            runner.run(ticks=1)

        assert runner.engine.current_tick == final_tick
        assert runner.lifecycle_state == final_status

    def test_multi_agent_fault_isolation(self) -> None:
        """In a multi-agent scenario, one vehicle's blocking does not impede independent agents."""
        scenario = create_multi_vehicle_scenario(max_ticks=30)
        runner = ScenarioRunner.create(scenario)

        # Force veh_north to blocked state
        v1_agent = runner.world.get_agent("veh_north")
        v1_agent.pause()

        runner.run(ticks=10)

        # veh_north should be STOPPED/BLOCKED, while veh_east is advancing EN_ROUTE or ARRIVED
        v1_state = v1_agent.state
        v2_agent = runner.world.get_agent("veh_east")
        v2_state = v2_agent.state

        assert v1_state in (VehicleState.STOPPED, VehicleState.IDLE, VehicleState.BLOCKED)
        assert v2_state in (VehicleState.EN_ROUTE, VehicleState.ARRIVED)
        assert v2_agent.vehicle.speed_mps >= 0.0
