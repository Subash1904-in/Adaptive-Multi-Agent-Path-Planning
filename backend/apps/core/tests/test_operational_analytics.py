"""Unit and integration tests for operational analytics aggregator and metrics endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.core.api.serializers import MetricsQuerySerializer
from apps.core.api.services import default_simulation_service
from apps.core.domain.enums import IncidentType
from apps.core.scenarios.examples import create_single_vehicle_scenario
from apps.core.simulation.models import TickResult
from apps.core.telemetry.analytics import (
    OperationalAnalyticsAggregator,
    _percentile,
)


class DummyWorld:
    def __init__(
        self,
        agents=None,
        road_graph=None,
        safety_manager=None,
        communication_network=None,
        incident_manager=None,
    ):
        self._agents = agents or []
        self.road_graph = road_graph
        self.safety_manager = safety_manager
        self.communication_network = communication_network
        self.incident_manager = incident_manager

    def get_agents(self):
        return self._agents


class DummyVehicleAgent:
    def __init__(self, agent_id: str, is_arrived: bool = False, current_edge_id: str | None = None):
        self.id = agent_id
        self.is_arrived = is_arrived
        self.current_edge_id = current_edge_id
        self.planned_path = None


class DummyStepResult:
    def __init__(
        self,
        current_edge_id: str,
        new_speed_mps: float = 10.0,
        distance_traveled_m: float = 5.0,
    ):
        self.current_edge_id = current_edge_id
        self.new_speed_mps = new_speed_mps
        self.distance_traveled_m = distance_traveled_m


class DummyEdge:
    def __init__(self, edge_id: str, start_node_id: str, end_node_id: str, length_m: float = 50.0):
        self.id = edge_id
        self.start_node_id = start_node_id
        self.end_node_id = end_node_id
        self.length_m = length_m


class DummyRoadGraph:
    def __init__(self):
        self.edges = {
            "e1": DummyEdge("e1", "n1", "n2"),
            "e2": DummyEdge("e2", "n2", "n3"),
            "e3": DummyEdge("e3", "n3", "n4"),
        }

    def has_edge(self, edge_id: str) -> bool:
        return edge_id in self.edges

    def get_edge(self, edge_id: str):
        return self.edges.get(edge_id)


class DummySafetyManager:
    def __init__(self, collisions: int = 0, near_misses: int = 0):
        self.metrics = {
            "actual_collisions": collisions,
            "near_misses": near_misses,
            "ttc_warnings": 1,
            "emergency_stops": 0,
            "min_observed_headway_m": 4.5,
            "min_observed_ttc_s": 1.8,
        }


class DummyCommNetwork:
    def __init__(self):
        self.metrics = {
            "messages_sent": 20,
            "messages_delivered": 18,
            "messages_lost": 2,
            "messages_expired": 0,
            "messages_lost_snr": 1,
            "messages_lost_hidden_terminal": 1,
            "messages_lost_buffer_overflow": 0,
            "messages_lost_out_of_range": 0,
            "packets_queued_latency": 3,
            "packets_delivered_latency": 18,
        }


class DummyIncident:
    def __init__(self, incident_type: IncidentType):
        self.incident_type = incident_type


class DummyIncidentManager:
    def __init__(self):
        self._incidents = [
            DummyIncident(incident_type=IncidentType.ROAD_CLOSURE),
            DummyIncident(incident_type=IncidentType.CONGESTION),
        ]

    def list_active(self):
        return self._incidents

    @property
    def resolved_count(self) -> int:
        return 1


def test_percentile_helper():
    """Verify linear interpolation percentile calculation and boundary conditions."""
    assert _percentile([], 50.0) is None
    assert _percentile([10.0], 50.0) == 10.0
    assert _percentile([10.0, 20.0, 30.0], 0.0) == 10.0
    assert _percentile([10.0, 20.0, 30.0], 100.0) == 30.0
    assert _percentile([10.0, 20.0, 30.0], 50.0) == 20.0
    assert _percentile([10.0, 20.0, 30.0, 40.0], 50.0) == 25.0


def test_empty_operational_analytics():
    """Verify operational analytics on an empty simulation state with zero division safeguards."""
    world = DummyWorld()
    result = OperationalAnalyticsAggregator.compute(
        tick_history=[],
        world=world,
        elapsed_time_s=0.0,
        time_step_s=0.1,
    )

    trips = result["trips"]
    assert trips["completed_trips"] == 0
    assert trips["total_trips"] == 0
    assert trips["active_trips"] == 0
    assert trips["completion_rate_pct"] is None  # Honesty: None when total_trips is 0
    assert trips["travel_time"]["mean_s"] is None
    assert trips["travel_time"]["median_s"] is None
    assert trips["travel_time"]["sample_count"] == 0
    assert trips["travel_time"]["bins"] == []

    throughput = result["throughput"]
    assert throughput["total_crossings"] == 0
    assert throughput["crossings_per_minute"] == 0.0
    assert throughput["top_intersections"] == []

    safety = result["safety"]
    assert safety["actual_collisions"] == 0
    assert safety["near_misses"] == 0
    assert safety["collision_rate_per_minute"] == 0.0

    comms = result["communication"]
    assert comms["messages_sent"] == 0
    assert comms["pdr"] is None
    assert comms["loss_rate"] is None
    assert comms["latency_ms_available"] is False

    routing = result["routing"]
    assert routing["reroutes_evaluated"] == 0
    assert routing["reroutes_accepted"] == 0
    assert routing["acceptance_rate_pct"] is None

    assert result["time_series"] == []


def test_operational_analytics_with_arrivals_and_travel_times():
    """Verify trip completion calculations and multi-sample travel-time distribution."""
    # Create 3 agents: 2 arrived, 1 in transit
    v1 = DummyVehicleAgent(agent_id="v1", is_arrived=True, current_edge_id="e2")
    v2 = DummyVehicleAgent(agent_id="v2", is_arrived=True, current_edge_id="e3")
    v3 = DummyVehicleAgent(agent_id="v3", is_arrived=False, current_edge_id="e1")

    world = DummyWorld(
        agents=[v1, v2, v3],
        road_graph=DummyRoadGraph(),
        safety_manager=DummySafetyManager(collisions=1, near_misses=2),
        communication_network=DummyCommNetwork(),
        incident_manager=DummyIncidentManager(),
    )

    # Build tick history with arrivals and edge transitions
    t1 = TickResult(
        tick=1,
        elapsed_time_s=10.0,
        time_step_s=10.0,
        agent_count=3,
        step_results={
            "v1": DummyStepResult("e1"),
            "v2": DummyStepResult("e2"),
            "v3": DummyStepResult("e1"),
        },
        arrived_agent_ids=[],
        active_agent_ids=["v1", "v2", "v3"],
        routing_metrics={"reroutes_evaluated": 2, "reroutes_accepted": 1},
    )
    t2 = TickResult(
        tick=2,
        elapsed_time_s=20.0,
        time_step_s=10.0,
        agent_count=2,
        step_results={
            "v1": DummyStepResult("e2"),
            "v2": DummyStepResult("e2"),
            "v3": DummyStepResult("e1"),
        },
        arrived_agent_ids=["v1"],
        active_agent_ids=["v2", "v3"],
        routing_metrics={"reroutes_evaluated": 1, "reroutes_accepted": 1},
    )
    t3 = TickResult(
        tick=3,
        elapsed_time_s=40.0,
        time_step_s=10.0,
        agent_count=1,
        step_results={
            "v1": DummyStepResult("e2"),
            "v2": DummyStepResult("e3"),
            "v3": DummyStepResult("e1"),
        },
        arrived_agent_ids=["v2"],
        active_agent_ids=["v3"],
        routing_metrics={"reroutes_evaluated": 0, "reroutes_accepted": 0},
    )

    result = OperationalAnalyticsAggregator.compute(
        tick_history=[t1, t2, t3],
        world=world,
        elapsed_time_s=40.0,
        time_step_s=10.0,
    )

    trips = result["trips"]
    assert trips["completed_trips"] == 2
    assert trips["total_trips"] == 3
    assert trips["active_trips"] == 1
    assert trips["completion_rate_pct"] == 66.67

    dist = trips["travel_time"]
    assert dist["sample_count"] == 2
    assert dist["min_s"] == 20.0
    assert dist["max_s"] == 40.0
    assert dist["mean_s"] == 30.0
    assert dist["median_s"] == 30.0
    assert len(dist["bins"]) >= 1

    throughput = result["throughput"]
    # 2 transitions: e1->e2 crossed n2, e2->e3 crossed n3
    assert throughput["total_crossings"] == 2
    # 2 crossings in 40s -> 3.0 crossings/min
    assert throughput["crossings_per_minute"] == 3.0
    top_map = {item["node_id"]: item["crossings"] for item in throughput["top_intersections"]}
    assert top_map.get("n2") == 1
    assert top_map.get("n3") == 1

    safety = result["safety"]
    assert safety["actual_collisions"] == 1
    assert safety["near_misses"] == 2
    assert safety["min_separation_observed_m"] == 4.5
    assert safety["min_ttc_observed_s"] == 1.8

    comms = result["communication"]
    assert comms["messages_sent"] == 20
    assert comms["messages_delivered"] == 18
    assert comms["pdr"] == 0.9
    assert comms["loss_rate"] == 0.1
    assert comms["loss_breakdown"]["snr_fading"] == 1
    assert comms["loss_breakdown"]["hidden_terminal"] == 1

    routing = result["routing"]
    assert routing["reroutes_evaluated"] == 3
    assert routing["reroutes_accepted"] == 2
    assert routing["acceptance_rate_pct"] == 66.67

    incidents = result["incidents"]
    assert incidents["total_active"] == 2
    assert incidents["active_by_type"].get("road_closure") == 1
    assert incidents["active_by_type"].get("congestion") == 1

    time_series = result["time_series"]
    assert len(time_series) == 3
    assert time_series[0]["timestamp_s"] == 10.0
    assert time_series[1]["timestamp_s"] == 20.0
    assert time_series[2]["timestamp_s"] == 40.0


def test_time_window_filtering():
    """Verify that time window parameters properly bound analytics calculation."""
    world = DummyWorld(road_graph=DummyRoadGraph())

    t1 = TickResult(
        tick=1,
        elapsed_time_s=10.0,
        time_step_s=10.0,
        agent_count=1,
        step_results={"v1": DummyStepResult("e1")},
        arrived_agent_ids=[],
        active_agent_ids=["v1"],
    )
    t2 = TickResult(
        tick=2,
        elapsed_time_s=30.0,
        time_step_s=10.0,
        agent_count=1,
        step_results={"v1": DummyStepResult("e2")},
        arrived_agent_ids=[],
        active_agent_ids=["v1"],
    )
    t3 = TickResult(
        tick=3,
        elapsed_time_s=60.0,
        time_step_s=10.0,
        agent_count=1,
        step_results={"v1": DummyStepResult("e2")},
        arrived_agent_ids=[],
        active_agent_ids=["v1"],
    )

    # Filter to window [20.0, 40.0] -> only t2 matches in the filtered ticks
    result = OperationalAnalyticsAggregator.compute(
        tick_history=[t1, t2, t3],
        world=world,
        elapsed_time_s=60.0,
        time_step_s=10.0,
        time_window_start_s=20.0,
        time_window_end_s=40.0,
    )

    assert len(result["time_series"]) == 1
    assert result["time_series"][0]["timestamp_s"] == 30.0


def test_metrics_query_serializer_validation():
    """Verify serializer parameter validation including invalid window range."""
    # Valid
    s1 = MetricsQuerySerializer(
        data={"time_window_start_s": 10.0, "time_window_end_s": 50.0, "limit_samples": 200}
    )
    assert s1.is_valid()
    assert s1.validated_data["time_window_start_s"] == 10.0
    assert s1.validated_data["limit_samples"] == 200

    # Invalid: start > end
    s2 = MetricsQuerySerializer(data={"time_window_start_s": 50.0, "time_window_end_s": 10.0})
    assert not s2.is_valid()
    assert "time_window_start_s" in s2.errors


@pytest.mark.django_db
def test_api_run_metrics_endpoint():
    """Integration test verifying GET /api/v1/runs/{run_id}/metrics/."""
    service = default_simulation_service
    scenario = create_single_vehicle_scenario()
    runner = service.create_run(scenario=scenario, max_ticks=5, time_step_s=0.1)
    runner.step()

    client = APIClient()
    response = client.get(f"/api/v1/runs/{runner.run_id}/metrics/")
    assert response.status_code == 200
    data = response.json()

    assert data["run_id"] == runner.run_id
    assert "metrics" in data
    assert "analytics" in data

    analytics = data["analytics"]
    assert "trips" in analytics
    assert "throughput" in analytics
    assert "safety" in analytics
    assert "communication" in analytics
    assert "routing" in analytics
    assert "incidents" in analytics
    assert "time_series" in analytics

    # Test with query params
    response_filtered = client.get(
        f"/api/v1/runs/{runner.run_id}/metrics/?time_window_start_s=0.0&limit_samples=50"
    )
    assert response_filtered.status_code == 200

    # Test with invalid query params
    response_invalid = client.get(
        f"/api/v1/runs/{runner.run_id}/metrics/?time_window_start_s=100.0&time_window_end_s=10.0"
    )
    assert response_invalid.status_code == 400
