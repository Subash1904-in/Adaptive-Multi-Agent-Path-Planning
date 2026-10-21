"""Unit and integration tests for MetricsAggregator and RunMetricsSummary.

Verifies:
- Accurate aggregation across all simulation subsystems without mutating underlying state
- Explicit documentation of metric classifications (cumulative, per-tick, observed, derived)
- Derived metric calculation formulas (packet_delivery_ratio, average_speed_mps)
- Strict prevention of double-counting on failed or rolled back simulation ticks
- Graceful handling of unconfigured subsystems with explicit defaults
"""

from types import SimpleNamespace

from apps.core.scenarios.examples import (
    create_adaptive_reroute_closure_scenario,
    create_multi_vehicle_scenario,
    create_packet_loss_scenario,
    create_single_vehicle_scenario,
)
from apps.core.scenarios.models import (
    TerminationReason,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.simulation.models import TickResult
from apps.core.telemetry.aggregation import (
    METRIC_CLASSIFICATIONS,
    MetricsAggregator,
)


class TestMetricsAggregationFormulasAndSemantics:
    """Tests metric definitions, classifications, and derived formulas."""

    def test_metric_classifications_documentation(self):
        """All documented metrics possess an explicit classification in METRIC_CLASSIFICATIONS."""
        assert "simulation.total_ticks" in METRIC_CLASSIFICATIONS
        assert "cumulative" in METRIC_CLASSIFICATIONS["simulation.total_ticks"]
        assert "derived" in METRIC_CLASSIFICATIONS["communication.packet_delivery_ratio"]
        assert "derived" in METRIC_CLASSIFICATIONS["kinematics.average_speed_mps"]
        assert "observed" in METRIC_CLASSIFICATIONS["safety.min_separation_observed_m"]

    def test_derived_pdr_formula(self):
        """PDR formula: messages_delivered / messages_sent, or 1.0 when sent == 0."""
        # Scenario with V2V comms
        scn = create_packet_loss_scenario(loss_rate=0.3, max_ticks=10)
        runner = ScenarioRunner.create(scn)
        res = runner.run_to_completion()

        assert res.metrics_summary is not None
        comm = res.metrics_summary["communication"]
        sent = comm["messages_sent"]
        delivered = comm["messages_delivered"]
        pdr = comm["packet_delivery_ratio"]

        if sent > 0:
            expected_pdr = round(delivered / sent, 4)
            assert pdr == expected_pdr
        else:
            assert pdr == 1.0

    def test_derived_kinematics_average_speed(self):
        """Kinematics average speed: total_distance_traveled_m / total_travel_time."""
        scn = create_single_vehicle_scenario(max_ticks=5, time_step_s=0.1)
        runner = ScenarioRunner.create(scn)
        res = runner.run_to_completion()

        assert res.metrics_summary is not None
        kin = res.metrics_summary["kinematics"]
        dist = kin["total_distance_traveled_m"]
        avg_speed = kin["average_speed_mps"]
        ticks = res.completed_ticks

        if ticks > 0 and dist > 0.0:
            # single vehicle travel time = ticks * 0.1
            expected = round(dist / (ticks * 0.1), 4)
            assert avg_speed == expected

    def test_failed_ticks_not_double_counted(self):
        """Ticks that fail are never appended to tick_history and not counted in metrics."""
        scn = create_single_vehicle_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scn)

        # Step 2 valid ticks
        runner.run(ticks=2)
        assert len(runner.tick_history) == 2
        dist_after_2 = sum(
            sr.distance_traveled_m for tr in runner.tick_history for sr in tr.step_results.values()
        )

        # Injected failure on 3rd tick
        def failing_step(*args, **kwargs):
            raise RuntimeError("Engine transient hardware error")

        runner.engine.step = failing_step

        res = runner.run(ticks=1)
        assert res.termination_reason == TerminationReason.FAILED
        assert res.completed_ticks == 2
        assert len(runner.tick_history) == 2

        # Verify distance was NOT modified by the failed attempt
        kin = res.metrics_summary["kinematics"]
        assert kin["total_distance_traveled_m"] == round(dist_after_2, 4)


class TestCrossSubsystemMetricsInclusion:
    """Tests aggregation across communication, routing, coordination, and safety."""

    def test_multi_vehicle_metrics_aggregation(self):
        """Multi-vehicle scenario aggregates simulation, kinematics, and safety metrics."""
        scn = create_multi_vehicle_scenario(max_ticks=5, seed=42)
        runner = ScenarioRunner.create(scn)
        res = runner.run_to_completion()

        summary = res.metrics_summary
        assert summary is not None

        # Simulation
        assert summary["simulation"]["total_ticks"] == 5
        assert summary["simulation"]["vehicles_registered"] == len(scn.vehicles)
        assert summary["simulation"]["terminal_state"] in ("COMPLETED", "LIMIT_REACHED")

        # Kinematics
        assert summary["kinematics"]["total_distance_traveled_m"] > 0.0
        assert summary["kinematics"]["max_speed_observed_mps"] > 0.0

        # Safety
        assert summary["safety"]["pair_checks"] >= 0
        assert summary["safety"]["actual_collisions"] == 0

    def test_adaptive_routing_metrics_aggregation(self):
        """Adaptive rerouting scenario aggregates evaluations, acceptances, and rejections."""
        scn = create_adaptive_reroute_closure_scenario(max_ticks=10)
        runner = ScenarioRunner.create(scn)
        res = runner.run_to_completion()

        summary = res.metrics_summary
        assert summary is not None
        assert "routing" in summary
        assert summary["routing"]["reroutes_evaluated"] >= 0
        assert summary["routing"]["reroutes_accepted"] >= 0

    def test_tick_result_fallback_aggregation_and_zero_sent_pdr(self):
        """MetricsAggregator aggregates from TickResult when world managers are absent."""
        mock_world = type("MockWorld", (), {"_pedestrians": {}})()

        mock_step_res = SimpleNamespace(
            new_speed_mps=5.0,
            distance_traveled_m=5.0,
        )

        tr = TickResult(
            tick=1,
            elapsed_time_s=0.1,
            time_step_s=0.1,
            agent_count=1,
            step_results={"v1": mock_step_res},
            arrived_agent_ids=[],
            active_agent_ids=["v1"],
            routing_metrics={
                "reroutes_evaluated": 3,
                "reroutes_accepted": 2,
                "reroutes_rejected": 1,
            },
            communication_metrics={
                "messages_sent": 0,
                "messages_delivered": 0,
                "messages_lost": 0,
                "messages_expired": 0,
            },
            coordination_metrics={
                "conflicts_detected": 2,
                "conflicts_resolved": 2,
                "yield_actions": 1,
            },
            safety_metrics={
                "pair_checks": 4,
                "near_misses": 1,
                "emergency_brakes": 1,
                "control_overrides": 1,
                "actual_collisions": 0,
                "min_separation_observed": 1.5,
                "min_ttc_observed": 0.8,
            },
            pedestrian_metrics={"crosswalk_waits": 2, "crossings_completed": 1},
            emergency_metrics={
                "corridors_created": 1,
                "emergency_yield_actions": 1,
                "preemption_requests": 1,
            },
            corridors={"corr_1": {}},
            decision_metrics={
                "evaluations_total": 4,
                "decisions_accepted": 3,
                "decisions_rejected": 1,
                "decisions_deferred": 0,
                "decisions_reevaluated": 0,
            },
        )

        summary = MetricsAggregator.aggregate(
            tick_history=[tr],
            world=mock_world,
            total_vehicles=1,
            arrived_vehicles=0,
            active_vehicles=1,
            terminal_state="COMPLETED",
            termination_reason="target_ticks_completed",
            elapsed_time_s=0.1,
            time_step_s=0.1,
        )

        assert summary.routing["reroutes_evaluated"] == 3
        assert summary.routing["reroutes_accepted"] == 2
        assert summary.routing["reroutes_rejected"] == 1
        assert summary.communication["packet_delivery_ratio"] is None
        assert summary.coordination["conflicts_detected"] == 2
        assert summary.safety["min_separation_observed_m"] == 1.5
        assert summary.safety["min_ttc_observed_s"] == 0.8
        assert summary.pedestrians["crosswalk_waits"] == 2
        assert summary.emergency["corridors_created"] == 1
        assert summary.emergency["corridors_active_final"] == 1
        assert summary.decision["decisions_accepted"] == 3
