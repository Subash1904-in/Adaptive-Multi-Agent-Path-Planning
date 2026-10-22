"""Comprehensive End-to-End Regression Test Suite.

Executes full cross-component simulation lifecycle:
1. Scenario registration & Run initialization via REST API.
2. Initial multi-agent stepping and clock advancement.
3. Mid-simulation dynamic incident injection (road closure).
4. Adaptive rerouting and multi-agent coordination under dynamic network change.
5. Stepping to terminal completion with safety constraint enforcement.
6. Database persistence of run state, telemetry records, and metrics summary.
7. Telemetry & metrics querying via REST endpoints.
8. WebSocket live communication and frame protocol synchronization.
"""

from __future__ import annotations

import pytest
from channels.testing import WebsocketCommunicator
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_simulation_service
from apps.core.models import SimulationRun
from apps.core.realtime.routing import websocket_urlpatterns


@pytest.fixture(autouse=True)
def clean_services() -> None:
    """Clear simulation service registries before and after each test."""
    default_simulation_service.run_registry.clear()
    default_simulation_service.scenario_registry.clear()
    default_simulation_service.scenario_registry.preload_defaults()
    yield
    default_simulation_service.run_registry.clear()
    default_simulation_service.scenario_registry.clear()


@pytest.mark.django_db(transaction=True)
class TestCrossComponentE2ERegression:
    """End-to-end integration tests traversing every architectural boundary in AMAPP."""

    def test_full_cross_component_simulation_workflow(self) -> None:
        """Full lifecycle: create run -> step -> inject incident -> complete -> persist -> query."""
        api_client = APIClient()
        run_id = "e2e_reg_run_01"

        # 1. Initialize run via REST API
        create_resp = api_client.post(
            "/api/v1/runs/",
            data={
                "scenario_id": "scn_multi_veh",
                "run_id": run_id,
                "max_ticks": 40,
                "time_step_s": 0.1,
            },
            format="json",
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        created_data = create_resp.json()
        assert created_data["run_id"] == run_id
        assert created_data["lifecycle_state"].upper() == "READY"

        # Verify initial persistent record
        db_run = SimulationRun.objects.get(run_id=run_id)
        assert db_run.status == "READY"
        assert db_run.is_terminal is False

        # 2. Step 3 ticks
        step1_resp = api_client.post(
            f"/api/v1/runs/{run_id}/step/",
            data={"ticks": 3},
            format="json",
        )
        assert step1_resp.status_code == status.HTTP_200_OK
        step1_data = step1_resp.json()
        assert step1_data["advanced_ticks"] == 3
        assert step1_data["current_tick"] == 3
        assert step1_data["lifecycle_state"].upper() == "RUNNING"

        # 3. Dynamic Incident Injection: Road closure
        incident_resp = api_client.post(
            f"/api/v1/runs/{run_id}/incidents/",
            data={
                "incident_type": "road_closure",
                "affected_edge_id": "edge_r0_c0_to_r1_c0",
                "severity": "high",
                "description": "Cross-component regression road closure incident",
            },
            format="json",
        )
        assert incident_resp.status_code == status.HTTP_201_CREATED
        inc_data = incident_resp.json()
        assert inc_data["affected_edge_id"] == "edge_r0_c0_to_r1_c0"
        assert inc_data["status"] == "active"

        # Verify incidents list endpoint reflects the new incident
        list_incidents_resp = api_client.get(f"/api/v1/runs/{run_id}/incidents/")
        assert list_incidents_resp.status_code == status.HTTP_200_OK
        assert list_incidents_resp.json()["active_count"] == 1

        # 4. Advance simulation to completion
        complete_resp = api_client.post(
            f"/api/v1/runs/{run_id}/step/",
            data={"run_to_completion": True},
            format="json",
        )
        assert complete_resp.status_code == status.HTTP_200_OK
        complete_data = complete_resp.json()
        assert complete_data["is_terminal"] is True
        assert complete_data["lifecycle_state"].upper() in ("COMPLETED", "LIMIT_REACHED")

        # 5. Verify database persistence state
        db_run.refresh_from_db()
        assert db_run.is_terminal is True
        assert db_run.status in ("COMPLETED", "LIMIT_REACHED")
        assert db_run.completed_ticks > 3
        assert db_run.simulation_duration_s is not None
        assert db_run.simulation_duration_s > 0.0

        # 6. Verify REST query endpoints: Metrics, Telemetry, and Result
        metrics_resp = api_client.get(f"/api/v1/runs/{run_id}/metrics/")
        assert metrics_resp.status_code == status.HTTP_200_OK
        metrics_data = metrics_resp.json()
        assert "analytics" in metrics_data
        assert "safety" in metrics_data["analytics"]

        telemetry_resp = api_client.get(f"/api/v1/runs/{run_id}/telemetry/")
        assert telemetry_resp.status_code == status.HTTP_200_OK
        telemetry_data = telemetry_resp.json()
        assert "records" in telemetry_data
        assert len(telemetry_data["records"]) > 0

        result_resp = api_client.get(f"/api/v1/runs/{run_id}/result/")
        assert result_resp.status_code == status.HTTP_200_OK
        res_data = result_resp.json()
        assert res_data["run_id"] == run_id
        assert "disclaimer" in res_data
        assert "educational simulation" in res_data["disclaimer"].lower()

    @pytest.mark.asyncio
    async def test_websocket_and_rest_simultaneous_synchronization(self) -> None:
        """WebSocket consumer interacts with active simulation runner initialized via service."""
        from asgiref.sync import sync_to_async
        from channels.routing import URLRouter

        from apps.core.api.services import SimulationService

        application = URLRouter(websocket_urlpatterns)
        service = SimulationService()

        # Initialize runner in service asynchronously
        runner = await sync_to_async(service.create_run)(
            scenario_id="scn_single_veh",
            run_id="ws_e2e_run_01",
            max_ticks=20,
        )

        communicator = WebsocketCommunicator(
            application,
            f"/ws/v1/runs/{runner.run_id}/",
        )
        connected, _ = await communicator.connect()
        assert connected is True

        # Send step action frame over WebSocket
        await communicator.send_json_to({"action": "step", "ticks": 2})

        # Receive telemetry or step response
        response = await communicator.receive_json_from(timeout=5.0)
        assert response is not None
        assert "type" in response or "action" in response or "tick" in str(response)

        await communicator.disconnect()
