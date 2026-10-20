"""Tests for Phase 17 scenario creation, validation, building, and running."""


from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.examples import (
    create_pedestrian_crossing_permitted_scenario,
    create_pedestrian_waiting_at_red_signal_scenario,
    create_unavoidable_vehicle_pedestrian_collision_scenario,
    create_vehicle_braking_for_pedestrian_scenario,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.scenarios.validation import validate_scenario


class TestPedestrianScenarios:
    """Verifies Phase 17 pedestrian and crosswalk scenario definition and execution."""

    def test_pedestrian_waiting_at_red_signal_scenario(self) -> None:
        """Validate and run scenario where pedestrian waits for red vehicle signal
        (walk indication)."""
        defn = create_pedestrian_waiting_at_red_signal_scenario(max_ticks=20)
        validate_scenario(defn)

        builder = ScenarioBuilder(defn)
        context = builder.build()
        engine = context.engine

        assert engine.world.crosswalk_count == 1
        assert engine.world.pedestrian_count == 1
        ped = engine.world.get_pedestrian("ped_01")
        assert ped.pedestrian_id == "ped_01"

        runner = ScenarioRunner(context=context)
        report = runner.run()

        assert report.completed_ticks > 0
        assert ped.waiting_time_s >= 0.0

    def test_pedestrian_crossing_permitted_scenario(self) -> None:
        """Validate and run scenario where pedestrian crosses under permitted walk indication."""
        defn = create_pedestrian_crossing_permitted_scenario(max_ticks=50)
        validate_scenario(defn)

        builder = ScenarioBuilder(defn)
        context = builder.build()

        ped = context.world.get_pedestrian("ped_walker")
        runner = ScenarioRunner(context=context)
        report = runner.run()

        assert report.completed_ticks > 0
        assert ped.total_distance_m > 0.0

    def test_vehicle_braking_for_pedestrian_scenario(self) -> None:
        """Validate and run scenario where approaching vehicle brakes for crossing pedestrian."""
        defn = create_vehicle_braking_for_pedestrian_scenario(max_ticks=30)
        validate_scenario(defn)

        builder = ScenarioBuilder(defn)
        context = builder.build()

        assert context.world.agent_count == 1
        assert context.world.pedestrian_count == 1
        assert context.world.safety_manager is not None

        runner = ScenarioRunner(context=context)
        report = runner.run()

        assert report.completed_ticks > 0
        assert report.final_world_snapshot.pedestrians is not None
        assert context.world.safety_manager.metrics is not None

    def test_unavoidable_vehicle_pedestrian_collision_scenario(self) -> None:
        """Validate and run scenario where vehicle collides with pedestrian due to
        speed/distance."""
        defn = create_unavoidable_vehicle_pedestrian_collision_scenario(max_ticks=20)
        validate_scenario(defn)

        builder = ScenarioBuilder(defn)
        context = builder.build()

        runner = ScenarioRunner(context=context)
        report = runner.run()

        assert report.completed_ticks > 0
        assert report.final_world_snapshot.pedestrians is not None
        assert context.world.safety_manager.metrics is not None
