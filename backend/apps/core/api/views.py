"""REST API views for scenario management, simulation execution, and telemetry.

Implements thin, validated HTTP endpoints delegating simulation behaviors
directly to domain services without mutating SimulationEngine or WorldState.
"""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import (
    BenchmarkConfiguration,
    BenchmarkTrial,
    ExperimentMetric,
    SimulationRun,
)
from apps.core.scenarios.models import ScenarioDefinition
from apps.core.telemetry.models import TelemetryConfig

from .exceptions import RunNotFoundError
from .pagination import AMAPPHistoryPagination
from .permissions import SimulationApiPermission
from .serializers import (
    BenchmarkConfigurationSerializer,
    BenchmarkTrialSerializer,
    CreateIncidentRequestSerializer,
    ExperimentMetricSerializer,
    ExportQuerySerializer,
    IncidentListResponseSerializer,
    MetricsQuerySerializer,
    PersistentSimulationRunSerializer,
    RunCancelRequestSerializer,
    RunCreateRequestSerializer,
    RunStatusResponseSerializer,
    RunStepRequestSerializer,
    ScenarioDefinitionSerializer,
    ScenarioSummarySerializer,
    TelemetryQuerySerializer,
    scenario_definition_from_dict,
)
from .services import SimulationService, default_simulation_service


class BaseSimulationView(APIView):
    """Base API view configuring default permissions and service dependency."""

    permission_classes = [SimulationApiPermission]
    service: SimulationService = default_simulation_service


# ==============================================================================
# Scenario Management Endpoints
# ==============================================================================


class ScenarioListCreateView(BaseSimulationView):
    """GET: List all registered scenarios.

    POST: Register a new validated ScenarioDefinition.
    """

    def get(self, request: Request) -> Response:
        """List all registered scenario definitions."""
        scenarios = self.service.list_scenarios()
        serializer = ScenarioSummarySerializer(scenarios, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        """Validate and register a new ScenarioDefinition."""
        serializer = ScenarioDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scenario: ScenarioDefinition = serializer.validated_data
        registered = self.service.register_scenario(scenario)
        response_serializer = ScenarioDefinitionSerializer(registered)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ScenarioDetailView(BaseSimulationView):
    """GET: Retrieve a single ScenarioDefinition by its unique ID."""

    def get(self, request: Request, scenario_id: str) -> Response:
        """Retrieve scenario details by ID."""
        scenario = self.service.get_scenario(scenario_id)
        serializer = ScenarioDefinitionSerializer(scenario)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ScenarioValidateView(BaseSimulationView):
    """POST: Validate a ScenarioDefinition payload without registering it."""

    def post(self, request: Request) -> Response:
        """Validate a scenario definition payload."""
        serializer = ScenarioDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scenario: ScenarioDefinition = serializer.validated_data
        result = self.service.validate_scenario_definition(scenario)
        return Response(result, status=status.HTTP_200_OK)


# ==============================================================================
# Simulation Run Lifecycle and Execution Endpoints
# ==============================================================================


class RunListCreateView(BaseSimulationView):
    """GET: List all active or past simulation runs.

    POST: Create and initialize a new simulation run in READY state.
    """

    def get(self, request: Request) -> Response:
        """List all active or past simulation runs with optional pagination and filtering."""
        history_params = {
            "limit",
            "offset",
            "page",
            "status",
            "scenario_id",
            "from_date",
            "to_date",
            "historical",
        }
        if any(p in request.query_params for p in history_params):
            qs = SimulationRun.objects.all().order_by("-created_at", "-id")
            if "status" in request.query_params:
                qs = qs.filter(status=request.query_params["status"])
            if "scenario_id" in request.query_params:
                qs = qs.filter(scenario_id=request.query_params["scenario_id"])
            if "from_date" in request.query_params:
                qs = qs.filter(created_at__gte=request.query_params["from_date"])
            if "to_date" in request.query_params:
                qs = qs.filter(created_at__lte=request.query_params["to_date"])

            paginator = AMAPPHistoryPagination()
            page = paginator.paginate_queryset(qs, request)
            if page is not None:
                serializer = PersistentSimulationRunSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)

            serializer = PersistentSimulationRunSerializer(qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Default unpaginated in-memory runners list for backward-compatibility
        runners = self.service.list_runs()
        serializer = RunStatusResponseSerializer(runners, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        """Initialize a new simulation run."""
        req_serializer = RunCreateRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        data = req_serializer.validated_data

        target_scenario: ScenarioDefinition | None = None
        if data.get("scenario"):
            target_scenario = scenario_definition_from_dict(data["scenario"])

        t_cfg: TelemetryConfig | None = None
        if data.get("telemetry_capacity") is not None or data.get("strict_retention") is not None:
            t_cfg = TelemetryConfig(
                buffer_capacity=data.get("telemetry_capacity", 5000),
                strict_retention=bool(data.get("strict_retention", False)),
            )

        runner = self.service.create_run(
            scenario_id=data.get("scenario_id"),
            scenario=target_scenario,
            run_id=data.get("run_id"),
            max_ticks=data.get("max_ticks"),
            max_duration_s=data.get("max_duration_s"),
            stop_on_all_arrived=data.get("stop_on_all_arrived"),
            time_step_s=data.get("time_step_s"),
            seed=data.get("seed"),
            telemetry_config=t_cfg,
        )

        res_serializer = RunStatusResponseSerializer(runner)
        return Response(res_serializer.data, status=status.HTTP_201_CREATED)


class RunDetailView(BaseSimulationView):
    """GET: Retrieve point-in-time lifecycle status of a simulation run."""

    def get(self, request: Request, run_id: str) -> Response:
        """Retrieve run status from active runner or persistent history."""
        if self.service.run_registry.exists(run_id):
            runner = self.service.get_run(run_id)
            serializer = RunStatusResponseSerializer(runner)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Fallback to persisted database record
        db_run = SimulationRun.objects.filter(run_id=run_id).first()
        if db_run is not None:
            serializer = PersistentSimulationRunSerializer(db_run)
            return Response(serializer.data, status=status.HTTP_200_OK)

        raise RunNotFoundError(run_id)


class RunStepView(BaseSimulationView):
    """POST: Advance a simulation run by discrete ticks or to completion."""

    def post(self, request: Request, run_id: str) -> Response:
        """Step or run simulation to completion."""
        serializer = RunStepRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = self.service.step_run(
            run_id=run_id,
            ticks=data.get("ticks", 1),
            target_accels=data.get("target_accels"),
            run_to_completion=data.get("run_to_completion", False),
        )
        return Response(result, status=status.HTTP_200_OK)


class RunCancelView(BaseSimulationView):
    """POST: Request cooperative cancellation of an active simulation run."""

    def post(self, request: Request, run_id: str) -> Response:
        """Cancel a running simulation."""
        serializer = RunCancelRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "User requested cancellation")

        result = self.service.cancel_run(run_id=run_id, reason=reason)
        return Response(result, status=status.HTTP_200_OK)


# ==============================================================================
# Simulation Results, Metrics, Telemetry, and Export Endpoints
# ==============================================================================


class RunResultView(BaseSimulationView):
    """GET: Retrieve execution result and final summary of a simulation run."""

    def get(self, request: Request, run_id: str) -> Response:
        """Retrieve run execution results."""
        result = self.service.get_run_result(run_id)
        return Response(result, status=status.HTTP_200_OK)


class RunMetricsView(BaseSimulationView):
    """GET: Retrieve aggregated metrics and operational analytics for a simulation run."""

    def get(self, request: Request, run_id: str) -> Response:
        """Retrieve aggregated metrics with optional window filtering or persistent metrics."""
        # If in-memory runner exists and not querying persisted history explicitly
        if self.service.run_registry.exists(run_id) and not request.query_params.get("persisted"):
            serializer = MetricsQuerySerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            metrics = self.service.get_run_metrics(
                run_id=run_id,
                time_window_start_s=data.get("time_window_start_s"),
                time_window_end_s=data.get("time_window_end_s"),
                limit_samples=data.get("limit_samples", 500),
            )
            return Response(metrics, status=status.HTTP_200_OK)

        # Fallback to persistent metrics
        run = SimulationRun.objects.filter(run_id=run_id).first()
        if not run and not self.service.run_registry.exists(run_id):
            raise RunNotFoundError(run_id)

        qs = ExperimentMetric.objects.filter(simulation_run__run_id=run_id).order_by(
            "-created_at", "-id"
        )
        metric_name = request.query_params.get("metric_name")
        if metric_name:
            qs = qs.filter(metric_name=metric_name)

        paginator = AMAPPHistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = ExperimentMetricSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = ExperimentMetricSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RunTelemetryView(BaseSimulationView):
    """GET: Query bounded telemetry stream records for a simulation run."""

    def get(self, request: Request, run_id: str) -> Response:
        """Query telemetry records."""
        serializer = TelemetryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = self.service.query_run_telemetry(
            run_id=run_id,
            record_type=data.get("record_type"),
            name=data.get("name"),
            tick_start=data.get("tick_start"),
            tick_end=data.get("tick_end"),
            limit=data.get("limit"),
        )
        return Response(result, status=status.HTTP_200_OK)


class RunExportView(BaseSimulationView):
    """GET: Export full simulation execution result and telemetry as JSON."""

    def get(self, request: Request, run_id: str) -> HttpResponse:
        """Export serialized result payload."""
        serializer = ExportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        json_str = self.service.export_run(
            run_id=run_id,
            max_bytes=data.get("max_bytes", 10_000_000),
            indent=data.get("indent"),
            max_telemetry_records=data.get("max_telemetry_records"),
        )
        return HttpResponse(json_str, content_type="application/json")


# ==============================================================================
# Simulation Incident Injection and Management Endpoints
# ==============================================================================


class RunIncidentListCreateView(BaseSimulationView):
    """GET: List all active or resolved incidents for a simulation run.

    POST: Inject a dynamic roadway incident (closure, congestion, obstacle, signal override).
    """

    def get(self, request: Request, run_id: str) -> Response:
        """List incidents for a simulation run with optional status filter."""
        status_filter = request.query_params.get("status")
        result = self.service.list_incidents(run_id, status_filter=status_filter)
        serializer = IncidentListResponseSerializer(result)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request, run_id: str) -> Response:
        """Validate and inject a roadway incident into an active simulation run."""
        serializer = CreateIncidentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self.service.create_incident(run_id, serializer.validated_data)
        return Response(result, status=status.HTTP_201_CREATED)


class RunIncidentDetailView(BaseSimulationView):
    """GET: Retrieve single incident details.

    DELETE: Resolve and remove an active incident, restoring baseline road and signal conditions.
    """

    def get(self, request: Request, run_id: str, incident_id: str) -> Response:
        """Retrieve details of an incident."""
        result = self.service.get_incident(run_id, incident_id)
        return Response(result, status=status.HTTP_200_OK)

    def delete(self, request: Request, run_id: str, incident_id: str) -> Response:
        """Resolve and remove an active incident."""
        result = self.service.remove_incident(run_id, incident_id)
        return Response(result, status=status.HTTP_200_OK)


# ==============================================================================
# Historical Benchmark Configuration and Trial Endpoints
# ==============================================================================


class BenchmarkConfigurationListView(BaseSimulationView):
    """GET: List persisted reproducible BenchmarkConfigurations."""

    def get(self, request: Request) -> Response:
        """List benchmark configurations with pagination and filtering."""
        qs = BenchmarkConfiguration.objects.all().order_by("-created_at", "-id")
        name = request.query_params.get("name")
        if name:
            qs = qs.filter(name__icontains=name)

        paginator = AMAPPHistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = BenchmarkConfigurationSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = BenchmarkConfigurationSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BenchmarkConfigurationDetailView(BaseSimulationView):
    """GET: Retrieve details of a specific BenchmarkConfiguration."""

    def get(self, request: Request, configuration_id: str) -> Response:
        """Retrieve single benchmark configuration."""
        cfg = BenchmarkConfiguration.objects.filter(configuration_id=configuration_id).first()
        if not cfg:
            raise NotFound(f"Benchmark configuration '{configuration_id}' not found.")
        serializer = BenchmarkConfigurationSerializer(cfg)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BenchmarkTrialListView(BaseSimulationView):
    """GET: Query historical benchmark trial execution outcomes."""

    def get(self, request: Request) -> Response:
        """List benchmark trials with bounded filtering and pagination."""
        qs = (
            BenchmarkTrial.objects.select_related("benchmark_config", "simulation_run")
            .all()
            .order_by("-created_at", "-id")
        )
        if "benchmark_run_id" in request.query_params:
            qs = qs.filter(benchmark_run_id=request.query_params["benchmark_run_id"])
        if "scenario_id" in request.query_params:
            qs = qs.filter(scenario_id=request.query_params["scenario_id"])
        if "algorithm_id" in request.query_params:
            qs = qs.filter(algorithm_id=request.query_params["algorithm_id"])
        if "status" in request.query_params:
            qs = qs.filter(status=request.query_params["status"])

        paginator = AMAPPHistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = BenchmarkTrialSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = BenchmarkTrialSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BenchmarkTrialDetailView(BaseSimulationView):
    """GET: Retrieve single benchmark trial details."""

    def get(self, request: Request, trial_id: int) -> Response:
        """Retrieve single trial by numeric ID."""
        trial = (
            BenchmarkTrial.objects.select_related("benchmark_config", "simulation_run")
            .filter(id=trial_id)
            .first()
        )
        if not trial:
            raise NotFound(f"Benchmark trial with ID '{trial_id}' not found.")
        serializer = BenchmarkTrialSerializer(trial)
        return Response(serializer.data, status=status.HTTP_200_OK)
