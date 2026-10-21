"""Unit and integration tests for Phase 18 emergency scenario definitions and builder.

Verifies:
- ScenarioDefinition schema extension for emergency vehicles and emergency configuration
- Scenario validation rules (valid vehicle ID references, graph node presence, priority bounds)
- ScenarioBuilder instantiation and auto-activation of emergency vehicles
- End-to-end execution of all 6 Phase 18 example scenario fixtures
- Backward compatibility with scenarios omitting emergency configurations
"""

import dataclasses

import pytest

from apps.core.emergency.models import (
    EmergencyLifecycleState,
    EmergencyType,
)
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_ambulance_corridor_scenario,
    create_competing_emergency_priority_scenario,
    create_fire_engine_multi_intersection_scenario,
    create_pedestrian_crosswalk_signal_priority_denial_scenario,
    create_police_activation_cancellation_scenario,
    create_single_vehicle_scenario,
    create_vehicle_yielding_to_emergency_scenario,
)
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.models import EmergencyVehicleScenarioDefinition
from apps.core.scenarios.validation import validate_scenario


class TestEmergencyScenarioValidation:
    """Tests for ScenarioDefinition validation of emergency vehicles and configurations."""

    def test_valid_ambulance_scenario_passes_validation(self) -> None:
        scn = create_ambulance_corridor_scenario()
        validate_scenario(scn)

    def test_unregistered_vehicle_id_raises_validation_error(self) -> None:
        scn = create_ambulance_corridor_scenario()
        bad_ev = EmergencyVehicleScenarioDefinition(
            vehicle_id="phantom_vehicle",
            emergency_type=EmergencyType.AMBULANCE,
            start_node_id="node_r0_c0",
            destination_node_id="node_r0_c2",
            priority_level=2,
        )
        invalid_scn = dataclasses.replace(scn, emergency_vehicles=(bad_ev,))
        with pytest.raises(ScenarioValidationError, match="not declared"):
            validate_scenario(invalid_scn)

    def test_invalid_destination_node_raises_validation_error(self) -> None:
        scn = create_ambulance_corridor_scenario()
        ctx = ScenarioBuilder(scn).build()
        bad_ev = EmergencyVehicleScenarioDefinition(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            start_node_id="node_r0_c0",
            destination_node_id="node_nonexistent",
            priority_level=2,
        )
        invalid_scn = dataclasses.replace(scn, emergency_vehicles=(bad_ev,))
        with pytest.raises(ScenarioValidationError, match="does not exist in graph"):
            validate_scenario(invalid_scn, graph=ctx.world.road_graph)

    def test_invalid_priority_level_raises_validation_error(self) -> None:
        scn = create_ambulance_corridor_scenario()
        bad_ev = EmergencyVehicleScenarioDefinition(
            vehicle_id="amb_01",
            emergency_type=EmergencyType.AMBULANCE,
            start_node_id="node_r0_c0",
            destination_node_id="node_r0_c2",
            priority_level=0,  # Below minimum (1)
        )
        invalid_scn = dataclasses.replace(scn, emergency_vehicles=(bad_ev,))
        with pytest.raises(ScenarioValidationError, match="priority_level"):
            validate_scenario(invalid_scn)

    def test_backward_compatibility_omitting_emergency_config(self) -> None:
        scn = create_single_vehicle_scenario()
        validate_scenario(scn)
        ctx = ScenarioBuilder(scn).build()
        assert ctx.world.emergency_manager is not None
        assert len(ctx.world.emergency_manager.get_registered_vehicles()) == 0
        res = ctx.engine.step()
        assert res.tick == 1
        assert res.emergency_metrics["active_emergency_vehicles"] == 0


class TestEmergencyScenarioBuilderAndExecution:
    """Tests for ScenarioBuilder and SimulationEngine execution across Phase 18 fixtures."""

    def test_ambulance_corridor_scenario_execution(self) -> None:
        scn = create_ambulance_corridor_scenario(time_step_s=0.5, max_ticks=10)
        ctx = ScenarioBuilder(scn).build()
        world = ctx.world
        engine = ctx.engine

        assert world.emergency_manager.is_emergency_vehicle("amb_01")
        assert world.emergency_manager.get_vehicle_state("amb_01") in (
            EmergencyLifecycleState.REQUESTING_PRIORITY,
            EmergencyLifecycleState.PRIORITY_ACTIVE,
        )

        res = engine.step()
        assert res.tick == 1
        assert res.emergency_metrics["active_emergency_vehicles"] >= 1
        assert len(world.emergency_manager.get_active_reservations()) > 0

    def test_fire_engine_multi_intersection_scenario_execution(self) -> None:
        scn = create_fire_engine_multi_intersection_scenario(time_step_s=0.5, max_ticks=10)
        ctx = ScenarioBuilder(scn).build()
        world = ctx.world
        engine = ctx.engine

        assert world.emergency_manager.is_emergency_vehicle("fire_01")
        res = engine.step()
        assert res.tick == 1
        assert res.emergency_metrics["active_corridors"] >= 1

    def test_police_activation_cancellation_scenario_execution(self) -> None:
        scn = create_police_activation_cancellation_scenario(time_step_s=0.5, max_ticks=10)
        ctx = ScenarioBuilder(scn).build()
        world = ctx.world
        engine = ctx.engine

        assert world.emergency_manager.is_emergency_vehicle("pol_01")
        assert (
            world.emergency_manager.get_vehicle_state("pol_01")
            == EmergencyLifecycleState.INACTIVE
        )

        # Activate priority manually
        world.emergency_manager.activate_emergency(
            vehicle_id="pol_01",
            emergency_type=EmergencyType.POLICE,
            destination_node_id="node_r2_c2",
            current_time_s=0.0,
            priority_level=1,
            start_node_id="node_r0_c0",
        )
        assert world.emergency_manager.get_vehicle_state("pol_01") in (
            EmergencyLifecycleState.REQUESTING_PRIORITY,
            EmergencyLifecycleState.PRIORITY_ACTIVE,
        )

        # Step 2 ticks with active emergency
        engine.step()
        engine.step()
        assert world.emergency_manager.get_active_corridor("pol_01") is not None

        world.emergency_manager.cancel_priority(
            "pol_01", current_time_s=1.0, reason="Incident resolved"
        )
        assert world.emergency_manager.get_active_corridor("pol_01") is None
        assert len(world.emergency_manager.get_active_reservations()) == 0

        # Further stepping continues normally
        res = engine.step()
        assert res.tick == 3

    def test_competing_emergency_priority_scenario_execution(self) -> None:
        scn = create_competing_emergency_priority_scenario(time_step_s=0.5, max_ticks=10)
        ctx = ScenarioBuilder(scn).build()
        world = ctx.world
        engine = ctx.engine

        assert world.emergency_manager.is_emergency_vehicle("amb_high")
        assert world.emergency_manager.is_emergency_vehicle("pol_low")

        # Step tick
        res = engine.step()
        assert res.tick == 1
        # Ambulance (priority level 1) has higher authority than police (priority level 3)
        st_amb = world.emergency_manager.get_vehicle_state("amb_high")
        assert st_amb == EmergencyLifecycleState.PRIORITY_ACTIVE

    def test_vehicle_yielding_scenario_execution(self) -> None:
        scn = create_vehicle_yielding_to_emergency_scenario(time_step_s=0.5, max_ticks=10)
        ctx = ScenarioBuilder(scn).build()
        engine = ctx.engine

        res = engine.step()
        assert res.tick == 1
        assert res.emergency_metrics is not None

    def test_pedestrian_crosswalk_signal_priority_denial_scenario_execution(self) -> None:
        scn = create_pedestrian_crosswalk_signal_priority_denial_scenario(
            time_step_s=0.5, max_ticks=10
        )
        ctx = ScenarioBuilder(scn).build()
        engine = ctx.engine

        res = engine.step()
        assert res.tick == 1
        # Crossing pedestrian protects signal clearance; priority denial must be recorded
        assert res.emergency_metrics["signal_priority_denials"] >= 1
