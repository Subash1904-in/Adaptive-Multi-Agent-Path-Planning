"""Scenario configuration validation logic for AMAPP.

Validates structural, semantic, and graph-compatibility constraints
on ScenarioDefinition before construction and execution.
"""

from typing import Optional

from apps.core.communication.models import CommunicationConfig
from apps.core.coordination.models import CoordinationConfig
from apps.core.decision.config import DecisionConfig
from apps.core.emergency.models import EmergencyConfig, EmergencyType
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.models import KinematicsConfig
from apps.core.routing.models import AdaptiveRoutingConfig, CostMode, RoutingAlgorithm
from apps.core.safety.models import SafetyConfig
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.models import (
    CrosswalkScenarioDefinition,
    EmergencyVehicleScenarioDefinition,
    PedestrianScenarioDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    VehicleScenarioDefinition,
)


def validate_scenario(
    scenario: ScenarioDefinition,
    graph: Optional[RoadGraph] = None,
) -> None:
    """Validate a scenario definition for structural and semantic correctness.

    Args:
        scenario: The ScenarioDefinition to validate.
        graph: Optional RoadGraph to validate node and edge references against.

    Raises:
        ScenarioValidationError: If any configuration or semantic constraint is violated.
    """
    if not isinstance(scenario, ScenarioDefinition):
        raise ScenarioValidationError(
            f"Expected ScenarioDefinition, got {type(scenario).__name__}.",
            field="scenario",
        )

    # 1. Metadata validation
    if not scenario.metadata.id or not scenario.metadata.id.strip():
        raise ScenarioValidationError("Scenario ID must not be empty.", field="metadata.id")
    if not scenario.metadata.name or not scenario.metadata.name.strip():
        raise ScenarioValidationError("Scenario name must not be empty.", field="metadata.name")

    # 2. Simulation time configuration
    if scenario.time_step_s <= 0.0 or scenario.time_step_s > 10.0:
        raise ScenarioValidationError(
            f"Simulation time_step_s must be in range (0.0, 10.0], got {scenario.time_step_s}.",
            field="time_step_s",
        )
    if scenario.max_ticks is not None and scenario.max_ticks <= 0:
        raise ScenarioValidationError(
            f"max_ticks must be strictly positive, got {scenario.max_ticks}.",
            field="max_ticks",
        )
    if scenario.max_duration_s is not None and scenario.max_duration_s <= 0.0:
        raise ScenarioValidationError(
            f"max_duration_s must be strictly positive, got {scenario.max_duration_s}.",
            field="max_duration_s",
        )

    # 3. Road network specification
    rn = scenario.road_network
    if not isinstance(rn.source_type, RoadNetworkSourceType):
        try:
            RoadNetworkSourceType(rn.source_type)
        except ValueError:
            raise ScenarioValidationError(
                f"Unknown road network source_type '{rn.source_type}'.",
                field="road_network.source_type",
            )

    if rn.source_type == RoadNetworkSourceType.SUPPLIED_GRAPH:
        if rn.supplied_graph is None and graph is None:
            raise ScenarioValidationError(
                "Road network source_type is SUPPLIED_GRAPH but supplied_graph is None.",
                field="road_network.supplied_graph",
            )
    elif rn.source_type == RoadNetworkSourceType.OSM_IMPORT:
        if rn.osm_config is None:
            raise ScenarioValidationError(
                "Road network source_type is OSM_IMPORT but osm_config is None.",
                field="road_network.osm_config",
            )

    # 4. Vehicle definitions
    seen_vehicle_ids: set[str] = set()
    for idx, v in enumerate(scenario.vehicles):
        if not isinstance(v, VehicleScenarioDefinition):
            raise ScenarioValidationError(
                f"Vehicle definition at index {idx} must be a VehicleScenarioDefinition instance.",
                field=f"vehicles[{idx}]",
            )
        if not v.vehicle_id or not v.vehicle_id.strip():
            raise ScenarioValidationError(
                f"Vehicle at index {idx} has empty vehicle_id.",
                field=f"vehicles[{idx}].vehicle_id",
            )
        if v.vehicle_id in seen_vehicle_ids:
            raise ScenarioValidationError(
                f"Duplicate vehicle ID '{v.vehicle_id}' found in scenario.",
                field="vehicles",
                details={"vehicle_id": v.vehicle_id},
            )
        seen_vehicle_ids.add(v.vehicle_id)

        if not v.start_node_id or not v.start_node_id.strip():
            raise ScenarioValidationError(
                f"Vehicle '{v.vehicle_id}' has empty start_node_id.",
                field=f"vehicles[{idx}].start_node_id",
            )
        if not v.destination_node_id or not v.destination_node_id.strip():
            raise ScenarioValidationError(
                f"Vehicle '{v.vehicle_id}' has empty destination_node_id.",
                field=f"vehicles[{idx}].destination_node_id",
            )

        # Algorithm validation
        if isinstance(v.algorithm, str):
            try:
                RoutingAlgorithm(v.algorithm)
            except ValueError:
                raise ScenarioValidationError(
                    f"Vehicle '{v.vehicle_id}' specifies invalid algorithm '{v.algorithm}'.",
                    field=f"vehicles[{idx}].algorithm",
                )

        # Cost mode validation
        if isinstance(v.cost_mode, str):
            try:
                CostMode(v.cost_mode)
            except ValueError:
                raise ScenarioValidationError(
                    f"Vehicle '{v.vehicle_id}' specifies invalid cost_mode '{v.cost_mode}'.",
                    field=f"vehicles[{idx}].cost_mode",
                )

        if v.initial_speed_mps < 0.0:
            msg = (
                f"Vehicle '{v.vehicle_id}' initial_speed_mps must be non-negative, "
                f"got {v.initial_speed_mps}."
            )
            raise ScenarioValidationError(msg, field=f"vehicles[{idx}].initial_speed_mps")

        if v.kinematics is not None and not isinstance(v.kinematics, KinematicsConfig):
            raise ScenarioValidationError(
                f"Vehicle '{v.vehicle_id}' kinematics must be KinematicsConfig or None.",
                field=f"vehicles[{idx}].kinematics",
            )

    # 5. Traffic signal definitions
    seen_signal_ids: set[str] = set()
    seen_signal_nodes: set[str] = set()
    for idx, s in enumerate(scenario.signals):
        if not s.signal_id or not s.signal_id.strip():
            raise ScenarioValidationError(
                f"Signal at index {idx} has empty signal_id.",
                field=f"signals[{idx}].signal_id",
            )
        if s.signal_id in seen_signal_ids:
            raise ScenarioValidationError(
                f"Duplicate signal ID '{s.signal_id}' found in scenario.",
                field="signals",
                details={"signal_id": s.signal_id},
            )
        seen_signal_ids.add(s.signal_id)

        if not s.node_id or not s.node_id.strip():
            raise ScenarioValidationError(
                f"Signal '{s.signal_id}' has empty node_id.",
                field=f"signals[{idx}].node_id",
            )
        if s.node_id in seen_signal_nodes:
            raise ScenarioValidationError(
                f"Multiple signals registered for intersection node '{s.node_id}'.",
                field="signals",
                details={"node_id": s.node_id},
            )
        seen_signal_nodes.add(s.node_id)

    # 6. Communication configuration validation
    if scenario.v2v_config is not None and not isinstance(scenario.v2v_config, CommunicationConfig):
        raise ScenarioValidationError(
            "v2v_config must be an instance of CommunicationConfig.",
            field="v2v_config",
        )

    # 7. Coordination configuration validation
    if scenario.coordination_config is not None and not isinstance(
        scenario.coordination_config, CoordinationConfig
    ):
        raise ScenarioValidationError(
            "coordination_config must be an instance of CoordinationConfig.",
            field="coordination_config",
        )

    # 8. Adaptive routing configuration validation
    if scenario.adaptive_routing_config is not None and not isinstance(
        scenario.adaptive_routing_config, AdaptiveRoutingConfig
    ):
        raise ScenarioValidationError(
            "adaptive_routing_config must be an instance of AdaptiveRoutingConfig.",
            field="adaptive_routing_config",
        )

    # 8.5. Safety configuration validation
    if scenario.safety_config is not None and not isinstance(
        scenario.safety_config, SafetyConfig
    ):
        raise ScenarioValidationError(
            "safety_config must be an instance of SafetyConfig.",
            field="safety_config",
        )

    # 8.7. Crosswalk validation
    seen_crosswalk_ids: set[str] = set()
    for idx, cw in enumerate(scenario.crosswalks):
        if not isinstance(cw, CrosswalkScenarioDefinition):
            raise ScenarioValidationError(
                f"Crosswalk at index {idx} must be a CrosswalkScenarioDefinition instance.",
                field=f"crosswalks[{idx}]",
            )
        if not cw.crosswalk_id or not cw.crosswalk_id.strip():
            raise ScenarioValidationError(
                f"Crosswalk at index {idx} has empty crosswalk_id.",
                field=f"crosswalks[{idx}].crosswalk_id",
            )
        if cw.crosswalk_id in seen_crosswalk_ids:
            raise ScenarioValidationError(
                f"Duplicate crosswalk ID '{cw.crosswalk_id}' found in scenario.",
                field="crosswalks",
                details={"crosswalk_id": cw.crosswalk_id},
            )
        seen_crosswalk_ids.add(cw.crosswalk_id)

        if cw.width_m <= 0.0:
            raise ScenarioValidationError(
                f"Crosswalk '{cw.crosswalk_id}' width_m must be strictly positive.",
                field=f"crosswalks[{idx}].width_m",
            )
        if cw.entry_point == cw.exit_point:
            raise ScenarioValidationError(
                f"Crosswalk '{cw.crosswalk_id}' entry and exit points cannot be identical.",
                field=f"crosswalks[{idx}].entry_point",
            )

    # 8.8. Pedestrian validation
    seen_pedestrian_ids: set[str] = set()
    for idx, ped in enumerate(scenario.pedestrians):
        if not isinstance(ped, PedestrianScenarioDefinition):
            raise ScenarioValidationError(
                f"Pedestrian at index {idx} must be a PedestrianScenarioDefinition instance.",
                field=f"pedestrians[{idx}]",
            )
        if not ped.pedestrian_id or not ped.pedestrian_id.strip():
            raise ScenarioValidationError(
                f"Pedestrian at index {idx} has empty pedestrian_id.",
                field=f"pedestrians[{idx}].pedestrian_id",
            )
        if ped.pedestrian_id in seen_pedestrian_ids:
            raise ScenarioValidationError(
                f"Duplicate pedestrian ID '{ped.pedestrian_id}' found in scenario.",
                field="pedestrians",
                details={"pedestrian_id": ped.pedestrian_id},
            )
        seen_pedestrian_ids.add(ped.pedestrian_id)

        if ped.walking_speed_mps <= 0.0:
            raise ScenarioValidationError(
                f"Pedestrian '{ped.pedestrian_id}' walking_speed_mps must be strictly positive.",
                field=f"pedestrians[{idx}].walking_speed_mps",
            )
        if ped.max_speed_mps < ped.walking_speed_mps:
            raise ScenarioValidationError(
                f"Pedestrian '{ped.pedestrian_id}' max_speed_mps "
                "cannot be less than walking speed.",
                field=f"pedestrians[{idx}].max_speed_mps",
            )
        if ped.crosswalk_id and ped.crosswalk_id not in seen_crosswalk_ids:
            raise ScenarioValidationError(
                f"Pedestrian '{ped.pedestrian_id}' references unknown "
                f"crosswalk '{ped.crosswalk_id}'.",
                field=f"pedestrians[{idx}].crosswalk_id",
            )

    # 8.9. Emergency vehicles validation
    seen_emergency_ids: set[str] = set()
    for idx, ev in enumerate(scenario.emergency_vehicles):
        if not isinstance(ev, EmergencyVehicleScenarioDefinition):
            raise ScenarioValidationError(
                f"Emergency vehicle at index {idx} must be an "
                "EmergencyVehicleScenarioDefinition instance.",
                field=f"emergency_vehicles[{idx}]",
            )
        if not ev.vehicle_id or not ev.vehicle_id.strip():
            raise ScenarioValidationError(
                f"Emergency vehicle at index {idx} has empty vehicle_id.",
                field=f"emergency_vehicles[{idx}].vehicle_id",
            )
        if ev.vehicle_id in seen_emergency_ids:
            raise ScenarioValidationError(
                f"Duplicate emergency vehicle ID '{ev.vehicle_id}' found in scenario.",
                field="emergency_vehicles",
                details={"vehicle_id": ev.vehicle_id},
            )
        seen_emergency_ids.add(ev.vehicle_id)

        if ev.vehicle_id not in seen_vehicle_ids:
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' is not declared in scenario vehicles.",
                field=f"emergency_vehicles[{idx}].vehicle_id",
                details={"vehicle_id": ev.vehicle_id},
            )

        if isinstance(ev.emergency_type, str):
            try:
                EmergencyType(ev.emergency_type)
            except ValueError:
                raise ScenarioValidationError(
                    f"Emergency vehicle '{ev.vehicle_id}' specifies invalid "
                    f"emergency_type '{ev.emergency_type}'.",
                    field=f"emergency_vehicles[{idx}].emergency_type",
                )
        elif not isinstance(ev.emergency_type, EmergencyType):
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' emergency_type must be "
                "an EmergencyType enum.",
                field=f"emergency_vehicles[{idx}].emergency_type",
            )

        if ev.priority_level is not None and (
            not isinstance(ev.priority_level, int) or ev.priority_level < 1
        ):
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' priority_level must be an integer >= 1.",
                field=f"emergency_vehicles[{idx}].priority_level",
            )
        if ev.ttl_s <= 0.0:
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' ttl_s must be strictly positive.",
                field=f"emergency_vehicles[{idx}].ttl_s",
            )
        if ev.activate_at_time_s < 0.0:
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' activate_at_time_s must be non-negative.",
                field=f"emergency_vehicles[{idx}].activate_at_time_s",
            )

    if scenario.emergency_config is not None and not isinstance(
        scenario.emergency_config, EmergencyConfig
    ):
        raise ScenarioValidationError(
            "emergency_config must be an EmergencyConfig instance.",
            field="emergency_config",
        )

    if scenario.decision_config is not None:
        if not isinstance(scenario.decision_config, DecisionConfig):
            raise ScenarioValidationError(
                "decision_config must be a DecisionConfig instance.",
                field="decision_config",
            )
        try:
            scenario.decision_config.validate()
        except Exception as exc:
            raise ScenarioValidationError(
                f"Invalid decision_config: {exc}",
                field="decision_config",
            ) from exc

    # 9. Graph compatibility validation if graph is provided
    target_graph = graph or scenario.road_network.supplied_graph
    if target_graph is not None:
        validate_graph_compatibility(scenario, target_graph)


def validate_graph_compatibility(scenario: ScenarioDefinition, graph: RoadGraph) -> None:
    """Validate that scenario references (nodes, edges) exist within the provided road graph.

    Args:
        scenario: ScenarioDefinition referencing graph elements.
        graph: RoadGraph to check against.

    Raises:
        ScenarioValidationError: If any node or required element is not in the graph.
    """
    for v in scenario.vehicles:
        if not graph.has_node(v.start_node_id):
            raise ScenarioValidationError(
                f"Vehicle '{v.vehicle_id}' start node '{v.start_node_id}' does not exist in graph.",
                field="start_node_id",
                details={"vehicle_id": v.vehicle_id, "start_node_id": v.start_node_id},
            )
        if not graph.has_node(v.destination_node_id):
            msg = (
                f"Vehicle '{v.vehicle_id}' destination node '{v.destination_node_id}' "
                "does not exist in graph."
            )
            raise ScenarioValidationError(
                msg,
                field="destination_node_id",
                details={"vehicle_id": v.vehicle_id, "destination_node_id": v.destination_node_id},
            )

    for s in scenario.signals:
        if not graph.has_node(s.node_id):
            raise ScenarioValidationError(
                f"Traffic signal '{s.signal_id}' node '{s.node_id}' does not exist in graph.",
                field="signals.node_id",
                details={"signal_id": s.signal_id, "node_id": s.node_id},
            )
        for edge_id in s.incoming_edge_ids:
            if not graph.has_edge(edge_id):
                raise ScenarioValidationError(
                    f"Traffic signal '{s.signal_id}' references unknown incoming edge '{edge_id}'.",
                    field="signals.incoming_edge_ids",
                    details={"signal_id": s.signal_id, "edge_id": edge_id},
                )

    for cw in scenario.crosswalks:
        if cw.associated_intersection_id and not graph.has_node(cw.associated_intersection_id):
            raise ScenarioValidationError(
                f"Crosswalk '{cw.crosswalk_id}' references unknown intersection "
                f"'{cw.associated_intersection_id}'.",
                field="crosswalks.associated_intersection_id",
                details={
                    "crosswalk_id": cw.crosswalk_id,
                    "node_id": cw.associated_intersection_id,
                },
            )
        for edge_id in cw.associated_road_segment_ids:
            if not graph.has_edge(edge_id):
                raise ScenarioValidationError(
                    f"Crosswalk '{cw.crosswalk_id}' references unknown road segment '{edge_id}'.",
                    field="crosswalks.associated_road_segment_ids",
                    details={"crosswalk_id": cw.crosswalk_id, "edge_id": edge_id},
                )

    for ev in scenario.emergency_vehicles:
        if ev.start_node_id and not graph.has_node(ev.start_node_id):
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' start node "
                f"'{ev.start_node_id}' does not exist in graph.",
                field="emergency_vehicles.start_node_id",
                details={"vehicle_id": ev.vehicle_id, "start_node_id": ev.start_node_id},
            )
        if ev.destination_node_id and not graph.has_node(ev.destination_node_id):
            raise ScenarioValidationError(
                f"Emergency vehicle '{ev.vehicle_id}' destination node "
                f"'{ev.destination_node_id}' does not exist in graph.",
                field="emergency_vehicles.destination_node_id",
                details={
                    "vehicle_id": ev.vehicle_id,
                    "destination_node_id": ev.destination_node_id,
                },
            )

