"""Serializers for AMAPP REST API endpoints.

Handles serialization and deserialization of ScenarioDefinitions, RunConfigs,
simulation step requests, query parameters, and execution telemetry payloads.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

from rest_framework import serializers

from apps.core.communication.models import (
    CommunicationConfig,
    DeliveryPolicy,
    StaleNeighborPolicy,
)
from apps.core.coordination.models import CoordinationConfig
from apps.core.decision.config import DecisionConfig
from apps.core.domain.enums import TrafficSignalState, VehicleType
from apps.core.emergency.models import EmergencyConfig, EmergencyType, ReservationConflictPolicy
from apps.core.graph.generator import CityGridConfig
from apps.core.graph.osm_models import OSMImportConfig
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
from apps.core.safety.models import SafetyConfig
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.models import (
    CrosswalkScenarioDefinition,
    EmergencyVehicleScenarioDefinition,
    PedestrianScenarioDefinition,
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.scenarios.runner import ScenarioRunner
from apps.core.signals.models import SignalCycleConfig

from .services import EDUCATIONAL_DISCLAIMER


def scenario_definition_from_dict(data: dict[str, Any]) -> ScenarioDefinition:
    """Deserialize a dictionary payload into an authoritative ScenarioDefinition."""
    if not isinstance(data, dict):
        raise ScenarioValidationError(
            f"Scenario data must be a JSON object, got {type(data).__name__}.",
            field="scenario",
        )

    # 1. Metadata
    meta_raw = data.get("metadata")
    if not isinstance(meta_raw, dict):
        raise ScenarioValidationError("Field 'metadata' must be a JSON object.", field="metadata")
    metadata = ScenarioMetadata(
        id=str(meta_raw.get("id", "")).strip(),
        name=str(meta_raw.get("name", "")).strip(),
        description=str(meta_raw.get("description", "")),
        version=str(meta_raw.get("version", "1.0.0")),
        author=str(meta_raw.get("author", "")),
    )

    # 2. Road Network
    rn_raw = data.get("road_network")
    if not isinstance(rn_raw, dict):
        raise ScenarioValidationError(
            "Field 'road_network' must be a JSON object.", field="road_network"
        )

    source_type_str = rn_raw.get("source_type", RoadNetworkSourceType.SYNTHETIC_GRID.value)
    try:
        source_type = RoadNetworkSourceType(source_type_str)
    except ValueError as exc:
        raise ScenarioValidationError(
            f"Invalid road network source_type '{source_type_str}'.",
            field="road_network.source_type",
        ) from exc

    grid_cfg: Optional[CityGridConfig] = None
    if rn_raw.get("grid_config"):
        gc = rn_raw["grid_config"]
        grid_cfg = CityGridConfig(
            rows=gc.get("rows", 3),
            cols=gc.get("cols", 3),
            spacing_m=float(gc.get("spacing_m", 100.0)),
            speed_limit_mps=float(gc.get("speed_limit_mps", 13.89)),
            lanes=gc.get("lanes", 1),
            bidirectional=gc.get("bidirectional", True),
            seed=gc.get("seed", 42),
        )

    osm_cfg: Optional[OSMImportConfig] = None
    if rn_raw.get("osm_config"):
        oc = rn_raw["osm_config"]
        osm_cfg = OSMImportConfig(
            osm_file_path=oc.get("osm_file_path"),
            place_name=oc.get("place_name"),
            network_type=oc.get("network_type", "drive"),
            simplify_geometry=oc.get("simplify_geometry", True),
        )

    road_network = RoadNetworkDefinition(
        source_type=source_type,
        grid_config=grid_cfg,
        osm_config=osm_cfg,
        allow_osm_fallback=rn_raw.get("allow_osm_fallback", True),
    )

    # 3. Vehicles
    vehicles_raw = data.get("vehicles", [])
    if not isinstance(vehicles_raw, (list, tuple)):
        raise ScenarioValidationError(
            "Field 'vehicles' must be an array of vehicle definitions.", field="vehicles"
        )

    parsed_vehicles: list[VehicleScenarioDefinition] = []
    for idx, v in enumerate(vehicles_raw):
        if not isinstance(v, dict):
            raise ScenarioValidationError(
                f"Vehicle entry at index {idx} must be an object.", field=f"vehicles[{idx}]"
            )

        algo_str = v.get("algorithm", RoutingAlgorithm.ASTAR.value)
        try:
            algo = RoutingAlgorithm(algo_str) if isinstance(algo_str, str) else algo_str
        except ValueError:
            algo = RoutingAlgorithm.ASTAR

        cost_str = v.get("cost_mode", CostMode.TRAVEL_TIME.value)
        try:
            cost = CostMode(cost_str) if isinstance(cost_str, str) else cost_str
        except ValueError:
            cost = CostMode.TRAVEL_TIME

        v_type_str = v.get("vehicle_type", VehicleType.STANDARD.value)
        try:
            v_type = VehicleType(v_type_str) if isinstance(v_type_str, str) else v_type_str
        except ValueError:
            v_type = VehicleType.STANDARD

        kin_cfg: Optional[KinematicsConfig] = None
        if v.get("kinematics") and isinstance(v["kinematics"], dict):
            k_raw = v["kinematics"]
            kin_cfg = KinematicsConfig(
                max_speed_mps=float(k_raw.get("max_speed_mps", 13.89)),
                max_acceleration_mps2=float(k_raw.get("max_acceleration_mps2", 3.0)),
                max_deceleration_mps2=float(k_raw.get("max_deceleration_mps2", 5.0)),
                min_speed_mps=float(k_raw.get("min_speed_mps", 0.0)),
                enforce_road_speed_limits=bool(k_raw.get("enforce_road_speed_limits", True)),
            )

        parsed_vehicles.append(
            VehicleScenarioDefinition(
                vehicle_id=str(v.get("vehicle_id", "")).strip(),
                start_node_id=str(v.get("start_node_id", "")).strip(),
                destination_node_id=str(v.get("destination_node_id", "")).strip(),
                algorithm=algo,
                cost_mode=cost,
                closed_edge_ids=tuple(v.get("closed_edge_ids", ())),
                kinematics=kin_cfg,
                initial_speed_mps=float(v.get("initial_speed_mps", 0.0)),
                vehicle_type=v_type,
                metadata=dict(v.get("metadata", {})),
            )
        )

    # 4. Signals
    parsed_signals: list[TrafficSignalScenarioDefinition] = []
    for s in data.get("signals", []):
        if isinstance(s, dict):
            cfg_raw = s.get("config", {})
            sig_cfg = SignalCycleConfig(
                green_duration_s=float(cfg_raw.get("green_duration_s", 30.0)),
                yellow_duration_s=float(cfg_raw.get("yellow_duration_s", 5.0)),
                red_duration_s=float(cfg_raw.get("red_duration_s", 30.0)),
                initial_phase=TrafficSignalState(
                    cfg_raw.get("initial_phase", TrafficSignalState.RED.value)
                ),
                phase_offset_s=float(cfg_raw.get("phase_offset_s", 0.0)),
            )
            parsed_signals.append(
                TrafficSignalScenarioDefinition(
                    signal_id=str(s.get("signal_id", "")),
                    node_id=str(s.get("node_id", "")),
                    config=sig_cfg,
                    incoming_edge_ids=tuple(s.get("incoming_edge_ids", ())),
                )
            )

    # 5. Pedestrians
    parsed_pedestrians: list[PedestrianScenarioDefinition] = []
    for p in data.get("pedestrians", []):
        if isinstance(p, dict):
            init_pos = tuple(float(x) for x in p.get("initial_position", (0.0, 0.0)))
            dest_pos = tuple(float(x) for x in p.get("destination_point", (0.0, 0.0)))
            parsed_pedestrians.append(
                PedestrianScenarioDefinition(
                    pedestrian_id=str(p.get("pedestrian_id", "")),
                    initial_position=(init_pos[0], init_pos[1]),
                    destination_point=(dest_pos[0], dest_pos[1]),
                    crosswalk_id=p.get("crosswalk_id"),
                    initial_heading_rad=float(p.get("initial_heading_rad", 0.0)),
                    initial_speed_mps=float(p.get("initial_speed_mps", 0.0)),
                    walking_speed_mps=float(p.get("walking_speed_mps", 1.4)),
                    max_speed_mps=float(p.get("max_speed_mps", 2.0)),
                )
            )

    # 6. Crosswalks
    parsed_crosswalks: list[CrosswalkScenarioDefinition] = []
    for c in data.get("crosswalks", []):
        if isinstance(c, dict):
            entry_pt = tuple(float(x) for x in c.get("entry_point", (0.0, 0.0)))
            exit_pt = tuple(float(x) for x in c.get("exit_point", (0.0, 0.0)))
            parsed_crosswalks.append(
                CrosswalkScenarioDefinition(
                    crosswalk_id=str(c.get("crosswalk_id", "")),
                    entry_point=(entry_pt[0], entry_pt[1]),
                    exit_point=(exit_pt[0], exit_pt[1]),
                    width_m=float(c.get("width_m", 3.0)),
                    associated_intersection_id=c.get("associated_intersection_id"),
                    signal_controller_id=c.get("signal_controller_id"),
                )
            )

    # 7. Emergency Vehicles
    parsed_emergencies: list[EmergencyVehicleScenarioDefinition] = []
    for ev in data.get("emergency_vehicles", []):
        if isinstance(ev, dict):
            etype_str = ev.get("emergency_type", EmergencyType.AMBULANCE.value)
            try:
                etype = EmergencyType(etype_str)
            except ValueError:
                etype = EmergencyType.AMBULANCE
            parsed_emergencies.append(
                EmergencyVehicleScenarioDefinition(
                    vehicle_id=str(ev.get("vehicle_id", "")),
                    emergency_type=etype,
                    start_node_id=str(ev.get("start_node_id", "")),
                    destination_node_id=str(ev.get("destination_node_id", "")),
                    priority_level=ev.get("priority_level"),
                    activate_at_time_s=float(ev.get("activate_at_time_s", 0.0)),
                    ttl_s=float(ev.get("ttl_s", 60.0)),
                    auto_activate=bool(ev.get("auto_activate", True)),
                )
            )

    # 8. Optional Subsystem Configs
    v2v_cfg: Optional[CommunicationConfig] = None
    if data.get("v2v_config") and isinstance(data["v2v_config"], dict):
        vc = dict(data["v2v_config"])
        if isinstance(vc.get("delivery_policy"), str):
            vc["delivery_policy"] = DeliveryPolicy(vc["delivery_policy"])
        if isinstance(vc.get("stale_policy"), str):
            vc["stale_policy"] = StaleNeighborPolicy(vc["stale_policy"])
        v2v_cfg = CommunicationConfig(**vc)

    coord_cfg = (
        CoordinationConfig(**data["coordination_config"])
        if data.get("coordination_config") and isinstance(data["coordination_config"], dict)
        else None
    )

    adapt_cfg: Optional[AdaptiveRoutingConfig] = None
    if data.get("adaptive_routing_config") and isinstance(data["adaptive_routing_config"], dict):
        ac = dict(data["adaptive_routing_config"])
        if isinstance(ac.get("algorithm"), str):
            ac["algorithm"] = RoutingAlgorithm(ac["algorithm"])
        if isinstance(ac.get("cost_mode"), str):
            ac["cost_mode"] = CostMode(ac["cost_mode"])
        adapt_cfg = AdaptiveRoutingConfig(**ac)

    safety_cfg = (
        SafetyConfig(**data["safety_config"])
        if data.get("safety_config") and isinstance(data["safety_config"], dict)
        else None
    )

    emerg_cfg: Optional[EmergencyConfig] = None
    if data.get("emergency_config") and isinstance(data["emergency_config"], dict):
        ec = dict(data["emergency_config"])
        if isinstance(ec.get("conflict_policy"), str):
            ec["conflict_policy"] = ReservationConflictPolicy(ec["conflict_policy"])
        emerg_cfg = EmergencyConfig(**ec)

    decis_cfg = (
        DecisionConfig(**data["decision_config"])
        if data.get("decision_config") and isinstance(data["decision_config"], dict)
        else None
    )

    return ScenarioDefinition(
        metadata=metadata,
        road_network=road_network,
        vehicles=tuple(parsed_vehicles),
        signals=tuple(parsed_signals),
        pedestrians=tuple(parsed_pedestrians),
        crosswalks=tuple(parsed_crosswalks),
        emergency_vehicles=tuple(parsed_emergencies),
        time_step_s=float(data.get("time_step_s", 0.1)),
        max_ticks=data.get("max_ticks"),
        max_duration_s=float(data["max_duration_s"]) if data.get("max_duration_s") else None,
        stop_on_all_arrived=bool(data.get("stop_on_all_arrived", True)),
        seed=data.get("seed"),
        allow_unreachable_vehicles=bool(data.get("allow_unreachable_vehicles", False)),
        simulation_metadata=dict(data.get("simulation_metadata", {})),
        v2v_config=v2v_cfg,
        coordination_config=coord_cfg,
        adaptive_routing_config=adapt_cfg,
        safety_config=safety_cfg,
        emergency_config=emerg_cfg,
        decision_config=decis_cfg,
    )


class ScenarioSummarySerializer(serializers.Serializer):
    """Compact summary serializer for scenario list endpoints."""

    id = serializers.CharField(source="metadata.id")
    name = serializers.CharField(source="metadata.name")
    description = serializers.CharField(source="metadata.description")
    version = serializers.CharField(source="metadata.version")
    author = serializers.CharField(source="metadata.author")
    vehicle_count = serializers.SerializerMethodField()
    road_network_source = serializers.CharField(source="road_network.source_type.value")
    time_step_s = serializers.FloatField()
    max_ticks = serializers.IntegerField(allow_null=True)
    effective_max_ticks = serializers.IntegerField(allow_null=True)

    def get_vehicle_count(self, obj: ScenarioDefinition) -> int:
        return len(obj.vehicles)


class ScenarioDefinitionSerializer(serializers.Serializer):
    """Full serializer and deserializer for ScenarioDefinition."""

    def to_internal_value(self, data: Any) -> ScenarioDefinition:
        if not isinstance(data, dict):
            raise serializers.ValidationError("Scenario definition must be a JSON object.")
        return scenario_definition_from_dict(data)

    def to_representation(self, instance: ScenarioDefinition) -> dict[str, Any]:
        payload = instance.to_dict()
        payload["disclaimer"] = EDUCATIONAL_DISCLAIMER
        return payload


class RunCreateRequestSerializer(serializers.Serializer):
    """Validates the request payload to initiate a new simulation run."""

    scenario_id = serializers.CharField(required=False, allow_blank=True, default=None)
    scenario = serializers.DictField(required=False, default=None)
    run_id = serializers.CharField(required=False, allow_blank=True, default=None)
    max_ticks = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    max_duration_s = serializers.FloatField(required=False, min_value=0.001, allow_null=True)
    stop_on_all_arrived = serializers.BooleanField(required=False, allow_null=True)
    time_step_s = serializers.FloatField(
        required=False, min_value=0.001, max_value=10.0, allow_null=True
    )
    seed = serializers.IntegerField(required=False, allow_null=True)
    telemetry_capacity = serializers.IntegerField(required=False, min_value=10, allow_null=True)
    strict_retention = serializers.BooleanField(required=False, allow_null=True)

    def validate_run_id(self, value: Optional[str]) -> Optional[str]:
        if value is not None:
            cleaned = value.strip()
            if not cleaned or not re.match(r"^[a-zA-Z0-9_\-\.]{1,128}$", cleaned):
                raise serializers.ValidationError(
                    "run_id must contain only alphanumeric characters, underscores, "
                    "hyphens, and dots (max 128 characters)."
                )
            return cleaned
        return None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        scn_id = attrs.get("scenario_id")
        scn_data = attrs.get("scenario")
        if not scn_id and not scn_data:
            raise serializers.ValidationError(
                "Must provide either 'scenario_id' or 'scenario' definition."
            )
        return attrs


class RunStatusResponseSerializer(serializers.Serializer):
    """Serializes the point-in-time status of an active or terminal simulation run."""

    run_id = serializers.CharField()
    scenario_id = serializers.CharField(source="scenario.metadata.id")
    scenario_name = serializers.CharField(source="scenario.metadata.name")
    lifecycle_state = serializers.CharField(source="lifecycle_state.value")
    current_tick = serializers.IntegerField()
    elapsed_time_s = serializers.FloatField()
    is_terminal = serializers.BooleanField()
    arrived_count = serializers.SerializerMethodField()
    active_count = serializers.SerializerMethodField()
    total_vehicles = serializers.SerializerMethodField()
    scenario_fingerprint = serializers.CharField()
    initial_world_state_fingerprint = serializers.CharField()
    commit_sha = serializers.CharField(allow_null=True)
    disclaimer = serializers.CharField(default=EDUCATIONAL_DISCLAIMER)

    def get_arrived_count(self, obj: ScenarioRunner) -> int:
        return sum(1 for a in obj.world.get_agents() if a.is_arrived)

    def get_active_count(self, obj: ScenarioRunner) -> int:
        return sum(1 for a in obj.world.get_agents() if not a.is_arrived)

    def get_total_vehicles(self, obj: ScenarioRunner) -> int:
        return len(obj.world.get_agents())


class RunStepRequestSerializer(serializers.Serializer):
    """Validates parameters for advancing a simulation run."""

    ticks = serializers.IntegerField(required=False, default=1, min_value=1, max_value=10000)
    run_to_completion = serializers.BooleanField(required=False, default=False)
    target_accels = serializers.DictField(
        required=False,
        child=serializers.FloatField(),
        default=None,
    )

    def validate_target_accels(self, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        cleaned = {}
        for k, v in value.items():
            if not isinstance(k, str) or not k.strip():
                raise serializers.ValidationError("Vehicle ID keys must be non-empty strings.")
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise serializers.ValidationError(
                    f"Target acceleration for '{k}' must be a finite number."
                )
            if abs(v) > 50.0:
                raise serializers.ValidationError(
                    f"Target acceleration for '{k}' exceeds physical limits (+/- 50 m/s^2)."
                )
            cleaned[k.strip()] = float(v)
        return cleaned


class RunCancelRequestSerializer(serializers.Serializer):
    """Validates cooperative cancellation request parameters."""

    reason = serializers.CharField(
        required=False,
        default="User requested cancellation",
        max_length=256,
    )


class TelemetryQuerySerializer(serializers.Serializer):
    """Validates query parameters for filtering telemetry records."""

    record_type = serializers.CharField(required=False, allow_blank=True, default=None)
    name = serializers.CharField(required=False, allow_blank=True, default=None)
    tick_start = serializers.IntegerField(required=False, min_value=0, default=None)
    tick_end = serializers.IntegerField(required=False, min_value=0, default=None)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50000, default=None)


class MetricsQuerySerializer(serializers.Serializer):
    """Validates query parameters for filtering run metrics and analytics."""

    tick_start = serializers.IntegerField(required=False, min_value=0, default=None)
    tick_end = serializers.IntegerField(required=False, min_value=0, default=None)
    time_window_start_s = serializers.FloatField(required=False, min_value=0.0, default=None)
    time_window_end_s = serializers.FloatField(required=False, min_value=0.0, default=None)
    limit_samples = serializers.IntegerField(
        required=False, min_value=1, max_value=500, default=100
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate range bounds and finite values."""
        tick_start = attrs.get("tick_start")
        tick_end = attrs.get("tick_end")
        if tick_start is not None and tick_end is not None and tick_start > tick_end:
            raise serializers.ValidationError(
                {"tick_start": "tick_start cannot be greater than tick_end."}
            )

        start_s = attrs.get("time_window_start_s")
        end_s = attrs.get("time_window_end_s")
        if start_s is not None and not math.isfinite(start_s):
            raise serializers.ValidationError({"time_window_start_s": "Must be a finite number."})
        if end_s is not None and not math.isfinite(end_s):
            raise serializers.ValidationError({"time_window_end_s": "Must be a finite number."})
        if start_s is not None and end_s is not None and start_s > end_s:
            raise serializers.ValidationError(
                {
                    "time_window_start_s": (
                        "time_window_start_s cannot be greater than time_window_end_s."
                    )
                }
            )
        return attrs


class ExportQuerySerializer(serializers.Serializer):
    """Validates query parameters for simulation result export."""

    max_bytes = serializers.IntegerField(
        required=False, default=10_000_000, min_value=100, max_value=100_000_000
    )
    indent = serializers.IntegerField(required=False, min_value=0, max_value=8, default=None)
    max_telemetry_records = serializers.IntegerField(
        required=False, min_value=1, max_value=100_000, default=None
    )


class CreateIncidentRequestSerializer(serializers.Serializer):
    """Validates parameters for dynamic roadway incident injection."""

    incident_type = serializers.CharField(required=True)
    affected_edge_id = serializers.CharField(required=False, allow_null=True, default=None)
    affected_node_id = serializers.CharField(required=False, allow_null=True, default=None)
    severity = serializers.CharField(required=False, default="medium")
    duration_s = serializers.FloatField(
        required=False, allow_null=True, default=None, min_value=0.01
    )
    description = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None, max_length=512
    )
    congestion_factor = serializers.FloatField(
        required=False, allow_null=True, default=None, min_value=1.0
    )
    target_signal_phase = serializers.CharField(required=False, allow_null=True, default=None)
    obstacle_type = serializers.CharField(required=False, allow_null=True, default=None)
    incident_id = serializers.CharField(
        required=False, allow_null=True, default=None, max_length=64
    )
    metadata = serializers.DictField(required=False, default=dict)

    def validate_congestion_factor(self, value: Optional[float]) -> Optional[float]:
        if value is not None:
            if not math.isfinite(value) or value < 1.0 or value > 1000.0:
                raise serializers.ValidationError(
                    "congestion_factor must be a finite float between 1.0 and 1000.0."
                )
        return value

    def validate_duration_s(self, value: Optional[float]) -> Optional[float]:
        if value is not None:
            if not math.isfinite(value) or value <= 0.0 or value > 86400.0:
                raise serializers.ValidationError(
                    "duration_s must be a finite positive float up to 86400.0."
                )
        return value


class IncidentSerializer(serializers.Serializer):
    """Serializes an IncidentRecord domain model."""

    id = serializers.CharField()
    incident_type = serializers.CharField()
    severity = serializers.CharField()
    status = serializers.CharField()
    affected_edge_id = serializers.CharField(allow_null=True)
    affected_node_id = serializers.CharField(allow_null=True)
    position = serializers.DictField()
    reported_timestamp_s = serializers.FloatField()
    duration_s = serializers.FloatField(allow_null=True)
    description = serializers.CharField(allow_null=True)
    congestion_factor = serializers.FloatField(allow_null=True)
    target_signal_phase = serializers.CharField(allow_null=True)
    obstacle_type = serializers.CharField(allow_null=True)
    resolved_timestamp_s = serializers.FloatField(allow_null=True)
    created_tick = serializers.IntegerField()
    resolved_tick = serializers.IntegerField(allow_null=True)
    metadata = serializers.DictField()


class IncidentListResponseSerializer(serializers.Serializer):
    """Serializes the response for enumerating incidents on a run."""

    run_id = serializers.CharField()
    total_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    resolved_count = serializers.IntegerField()
    incidents = IncidentSerializer(many=True)
    disclaimer = serializers.CharField(default=EDUCATIONAL_DISCLAIMER)


# ==============================================================================
# Historical Persistence Models Serializers
# ==============================================================================


class PersistentSimulationRunSerializer(serializers.ModelSerializer):
    """Serializes a persistent SimulationRun ORM record."""

    is_terminal = serializers.BooleanField(read_only=True)
    disclaimer = serializers.CharField(default=EDUCATIONAL_DISCLAIMER, read_only=True)

    class Meta:
        from apps.core.models import SimulationRun

        model = SimulationRun
        fields = [
            "id",
            "run_id",
            "scenario_id",
            "scenario_version",
            "status",
            "start_time",
            "completion_time",
            "simulation_duration_s",
            "completed_ticks",
            "configuration_snapshot",
            "configuration_fingerprint",
            "seed",
            "seed_policy",
            "routing_strategy",
            "git_commit_sha",
            "schema_version",
            "error_category",
            "error_summary",
            "created_at",
            "updated_at",
            "is_terminal",
            "disclaimer",
        ]
        read_only_fields = fields


class BenchmarkConfigurationSerializer(serializers.ModelSerializer):
    """Serializes a reproducible BenchmarkConfiguration ORM record."""

    disclaimer = serializers.CharField(default=EDUCATIONAL_DISCLAIMER, read_only=True)

    class Meta:
        from apps.core.models import BenchmarkConfiguration

        model = BenchmarkConfiguration
        fields = [
            "id",
            "configuration_id",
            "name",
            "description",
            "scenario_ids",
            "algorithm_ids",
            "trial_count",
            "base_seed",
            "seed_policy",
            "parameters",
            "configuration_fingerprint",
            "created_at",
            "disclaimer",
        ]
        read_only_fields = fields


class BenchmarkTrialSerializer(serializers.ModelSerializer):
    """Serializes a single BenchmarkTrial ORM record."""

    benchmark_config_id = serializers.CharField(
        source="benchmark_config.configuration_id", read_only=True, allow_null=True
    )
    simulation_run_id = serializers.CharField(
        source="simulation_run.run_id", read_only=True, allow_null=True
    )
    disclaimer = serializers.CharField(default=EDUCATIONAL_DISCLAIMER, read_only=True)

    class Meta:
        from apps.core.models import BenchmarkTrial

        model = BenchmarkTrial
        fields = [
            "id",
            "benchmark_run_id",
            "benchmark_config_id",
            "simulation_run_id",
            "scenario_id",
            "scenario_version",
            "algorithm_id",
            "algorithm_version",
            "trial_index",
            "seed",
            "status",
            "route_feasible",
            "route_cost",
            "route_length_m",
            "planning_duration_ms",
            "simulation_duration_s",
            "simulation_ticks",
            "travel_time_s",
            "completed_trips",
            "total_trips",
            "completion_rate_pct",
            "collision_count",
            "near_miss_count",
            "intersection_crossings",
            "reroutes_evaluated",
            "reroutes_accepted",
            "messages_sent",
            "messages_delivered",
            "pdr",
            "incident_count",
            "fallback_count",
            "started_at",
            "completed_at",
            "failure_reason",
            "diagnostic_summary",
            "created_at",
            "disclaimer",
        ]
        read_only_fields = fields


class ExperimentMetricSerializer(serializers.ModelSerializer):
    """Serializes structured experiment metric data."""

    simulation_run_id = serializers.CharField(
        source="simulation_run.run_id", read_only=True, allow_null=True
    )
    benchmark_trial_id = serializers.IntegerField(
        source="benchmark_trial.id", read_only=True, allow_null=True
    )

    class Meta:
        from apps.core.models import ExperimentMetric

        model = ExperimentMetric
        fields = [
            "id",
            "simulation_run_id",
            "benchmark_trial_id",
            "metric_name",
            "metric_type",
            "numeric_value",
            "unit",
            "sample_tick",
            "sample_timestamp_s",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
