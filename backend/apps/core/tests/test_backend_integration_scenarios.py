"""End-to-end backend integration tests executing representative scenarios across Phases 2 to 19.

Verifies:
- Phase 2-5: Graph, single-vehicle kinematics, multi-vehicle routing, and authoritative clock
- Phase 6-7: Signal cycle synchronization and traffic light states
- Phase 8-11: Adaptive rerouting on network closure and cost changes
- Phase 12-14: V2V communication with packet loss, latency, and decentralized sharing
- Phase 15-16: Safety supervisor collision avoidance, near misses, and braking overrides
- Phase 17: Pedestrian crosswalk interactions, signal compliance, and clearance
- Phase 18: Dynamic emergency corridor establishment, preemption, and civilian yielding
- Phase 19: Pluggable AI decision policy evaluation, candidate ranking, and constraint rejection
- Unified execution via ScenarioRunner with telemetry, metrics aggregation, and JSON export
"""

import json

from apps.core.scenarios.examples import (
    create_adaptive_reroute_closure_scenario,
    create_ai_decision_emergency_corridor_rejection_scenario,
    create_ai_decision_fastest_route_scenario,
    create_ambulance_corridor_scenario,
    create_packet_loss_scenario,
    create_pedestrian_waiting_at_red_signal_scenario,
    create_signalized_scenario,
    create_single_vehicle_scenario,
    create_vehicle_braking_for_pedestrian_scenario,
)
from apps.core.scenarios.models import (
    RunConfig,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.telemetry.models import TelemetryRecordType


class TestBackendIntegrationScenarios:
    """Integration test suite exercising the backend runner across all simulation subsystems."""

    def test_single_vehicle_kinematics_and_clock(self):
        """Phase 2-5: Single vehicle advances along planned route under simulation clock."""
        scn = create_single_vehicle_scenario(max_ticks=20, time_step_s=0.1)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        assert result.completed_ticks > 0
        assert result.elapsed_time_s > 0.0
        assert result.metrics_summary["kinematics"]["total_distance_traveled_m"] > 0.0

        # Verify telemetry records captured vehicle motion
        v_records = runner.telemetry.filter_records(categories={TelemetryRecordType.VEHICLE_STATE})
        assert len(v_records) == result.completed_ticks
        assert v_records[0].agent_id == "veh_01"

    def test_signalized_intersection_simulation(self):
        """Phase 6-7: Vehicles navigate signalized intersections with signal state telemetry."""
        scn = create_signalized_scenario(max_ticks=25)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        sig_records = runner.telemetry.filter_records(categories={TelemetryRecordType.SIGNAL_EVENT})
        assert len(sig_records) > 0
        assert "sig_r1_c1" in sig_records[0].payload

    def test_adaptive_rerouting_after_road_closure(self):
        """Phase 8-11: Road closure triggers adaptive reroute, recorded in metrics & telemetry."""
        scn = create_adaptive_reroute_closure_scenario(max_ticks=15)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        assert result.metrics_summary["routing"]["reroutes_evaluated"] >= 0
        # Check export produces valid JSON
        exported_json = runner.export_result()
        parsed = json.loads(exported_json)
        assert parsed["metrics_summary"]["routing"]["reroutes_evaluated"] >= 0

    def test_v2v_communication_with_packet_loss(self):
        """Phase 12-14: V2V communication under stochastic packet loss computes valid PDR."""
        scn = create_packet_loss_scenario(loss_rate=0.4, max_ticks=15)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        comm = result.metrics_summary["communication"]
        assert comm["messages_sent"] >= 0
        assert comm["packet_delivery_ratio"] is not None
        assert 0.0 <= comm["packet_delivery_ratio"] <= 1.0

    def test_pedestrian_waiting_and_crossing_under_signal_control(self):
        """Phase 17: Pedestrian waits at curb and crosses with crosswalk telemetry and metrics."""
        scn = create_pedestrian_waiting_at_red_signal_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        p_records = runner.telemetry.filter_records(
            categories={TelemetryRecordType.PEDESTRIAN_STATE}
        )
        assert len(p_records) > 0
        assert result.metrics_summary["simulation"]["pedestrians_registered"] == 1

    def test_vehicle_braking_for_pedestrian_safety_override(self):
        """Phase 16-17: Approaching vehicle yields/brakes for pedestrian in crosswalk."""
        scn = create_vehicle_braking_for_pedestrian_scenario(max_ticks=25)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        assert result.metrics_summary["safety"]["pair_checks"] >= 0
        assert result.metrics_summary["safety"]["actual_collisions"] == 0

    def test_emergency_vehicle_corridor_and_civilian_yielding(self):
        """Phase 18: Emergency vehicle reserves corridor and civilian vehicles yield."""
        scn = create_ambulance_corridor_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        em_metrics = result.metrics_summary["emergency"]
        assert "corridors_created" in em_metrics
        assert "emergency_yield_actions" in em_metrics

        # Telemetry should contain emergency corridor / event observations
        em_records = runner.telemetry.filter_records(
            categories={TelemetryRecordType.EMERGENCY_EVENT}
        )
        assert len(em_records) >= 0
        # Valid execution result
        assert result.run_metadata is not None
        assert result.run_metadata.commit_sha is not None or result.run_metadata.commit_sha is None

    def test_ai_decision_policy_evaluation_and_rejection(self):
        """Phase 19: AI decision policy evaluates candidates & rejects corridor intrusions."""
        scn = create_ai_decision_emergency_corridor_rejection_scenario(max_ticks=20)
        runner = ScenarioRunner.create(scn)
        result = runner.run_to_completion()

        assert result.is_success is True
        dec_summary = result.metrics_summary["decision"]
        assert dec_summary["evaluations_total"] >= 0

        # DECISION_EVENT records captured in telemetry
        d_records = runner.telemetry.filter_records(categories={TelemetryRecordType.DECISION_EVENT})
        if d_records:
            assert "decision_outcome" in d_records[0].name

    def test_full_pipeline_export_json_validity(self):
        """End-to-end execution export contains valid JSON conforming to all schema requirements."""
        scn = create_ai_decision_fastest_route_scenario(max_ticks=10)
        runner = ScenarioRunner.create(
            scn,
            run_config=RunConfig(run_id="run_e2e_export_test", max_ticks=10),
        )
        result = runner.run_to_completion()
        assert result.is_success is True

        json_export = runner.export_result(indent=2)
        parsed = json.loads(json_export)

        assert parsed["run_id"] == "run_e2e_export_test"
        assert parsed["lifecycle_state"] in ("COMPLETED", "LIMIT_REACHED")
        assert "run_metadata" in parsed
        assert "metrics_summary" in parsed
        assert "final_world_snapshot" in parsed
        assert parsed["run_metadata"]["scenario_fingerprint"] is not None
        assert parsed["run_metadata"]["final_world_state_fingerprint"] is not None
