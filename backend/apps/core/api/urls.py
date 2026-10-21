"""URL routing configuration for the AMAPP simulation REST API."""

from django.urls import path

from .views import (
    RunCancelView,
    RunDetailView,
    RunExportView,
    RunIncidentDetailView,
    RunIncidentListCreateView,
    RunListCreateView,
    RunMetricsView,
    RunResultView,
    RunStepView,
    RunTelemetryView,
    ScenarioDetailView,
    ScenarioListCreateView,
    ScenarioValidateView,
)

urlpatterns = [
    # Scenarios
    path("scenarios/", ScenarioListCreateView.as_view(), name="api_scenario_list"),
    path("scenarios/validate/", ScenarioValidateView.as_view(), name="api_scenario_validate"),
    path(
        "scenarios/<str:scenario_id>/",
        ScenarioDetailView.as_view(),
        name="api_scenario_detail",
    ),
    # Simulation Runs
    path("runs/", RunListCreateView.as_view(), name="api_run_list"),
    path("runs/<str:run_id>/", RunDetailView.as_view(), name="api_run_detail"),
    path("runs/<str:run_id>/step/", RunStepView.as_view(), name="api_run_step"),
    path("runs/<str:run_id>/cancel/", RunCancelView.as_view(), name="api_run_cancel"),
    path("runs/<str:run_id>/result/", RunResultView.as_view(), name="api_run_result"),
    path("runs/<str:run_id>/metrics/", RunMetricsView.as_view(), name="api_run_metrics"),
    path("runs/<str:run_id>/telemetry/", RunTelemetryView.as_view(), name="api_run_telemetry"),
    path("runs/<str:run_id>/export/", RunExportView.as_view(), name="api_run_export"),
    # Incidents
    path(
        "runs/<str:run_id>/incidents/",
        RunIncidentListCreateView.as_view(),
        name="api_run_incidents",
    ),
    path(
        "runs/<str:run_id>/incidents/<str:incident_id>/",
        RunIncidentDetailView.as_view(),
        name="api_run_incident_detail",
    ),
]
