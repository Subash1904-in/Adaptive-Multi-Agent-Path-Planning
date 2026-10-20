"""Tests for ScenarioDefinition validation rules and structural constraints."""

import pytest

from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.scenarios.exceptions import ScenarioValidationError
from apps.core.scenarios.models import (
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.scenarios.validation import (
    validate_graph_compatibility,
    validate_scenario,
)


@pytest.fixture
def base_scenario() -> ScenarioDefinition:
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=CityGridConfig(rows=2, cols=2),
    )
    v = VehicleScenarioDefinition(
        vehicle_id="v1",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c1",
    )
    return ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_scn", name="Test Scenario"),
        road_network=rn,
        vehicles=(v,),
        time_step_s=0.1,
        max_ticks=100,
    )


def test_valid_scenario_passes_validation(base_scenario):
    validate_scenario(base_scenario)


def test_invalid_type_raises():
    with pytest.raises(ScenarioValidationError, match="Expected ScenarioDefinition"):
        validate_scenario("not_a_scenario")  # type: ignore


def test_empty_metadata_id_raises(base_scenario):
    bad = ScenarioDefinition(
        metadata=ScenarioMetadata(id="", name="Valid Name"),
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
    )
    with pytest.raises(ScenarioValidationError, match="Scenario ID must not be empty"):
        validate_scenario(bad)


def test_empty_metadata_name_raises(base_scenario):
    bad = ScenarioDefinition(
        metadata=ScenarioMetadata(id="scn_01", name="  "),
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
    )
    with pytest.raises(ScenarioValidationError, match="Scenario name must not be empty"):
        validate_scenario(bad)


@pytest.mark.parametrize("dt", [0.0, -0.1, 15.0])
def test_invalid_time_step_raises(base_scenario, dt):
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        time_step_s=dt,
    )
    with pytest.raises(ScenarioValidationError, match="time_step_s"):
        validate_scenario(bad)


@pytest.mark.parametrize("ticks", [0, -10])
def test_invalid_max_ticks_raises(base_scenario, ticks):
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        max_ticks=ticks,
    )
    with pytest.raises(ScenarioValidationError, match="max_ticks must be strictly positive"):
        validate_scenario(bad)


@pytest.mark.parametrize("dur", [0.0, -5.0])
def test_invalid_max_duration_raises(base_scenario, dur):
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        max_duration_s=dur,
    )
    with pytest.raises(ScenarioValidationError, match="max_duration_s must be strictly positive"):
        validate_scenario(bad)


def test_effective_max_ticks_derivation(base_scenario):
    s1 = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        time_step_s=0.1,
        max_ticks=50,
    )
    assert s1.effective_max_ticks == 50

    s2 = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        time_step_s=0.1,
        max_duration_s=5.0,
    )
    assert s2.effective_max_ticks == 50

    # min of max_ticks (100) and duration (5.0s -> 50 ticks)
    s3 = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        time_step_s=0.1,
        max_ticks=100,
        max_duration_s=5.0,
    )
    assert s3.effective_max_ticks == 50

    # No limits
    s4 = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
    )
    assert s4.effective_max_ticks is None


def test_supplied_graph_none_raises(base_scenario):
    bad_rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SUPPLIED_GRAPH,
        supplied_graph=None,
    )
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=bad_rn,
        vehicles=base_scenario.vehicles,
    )
    with pytest.raises(ScenarioValidationError, match="supplied_graph is None"):
        validate_scenario(bad)


def test_osm_import_config_none_raises(base_scenario):
    bad_rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.OSM_IMPORT,
        osm_config=None,
    )
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=bad_rn,
        vehicles=base_scenario.vehicles,
    )
    with pytest.raises(ScenarioValidationError, match="osm_config is None"):
        validate_scenario(bad)


def test_duplicate_vehicle_id_raises(base_scenario):
    v1 = VehicleScenarioDefinition(vehicle_id="dup", start_node_id="a", destination_node_id="b")
    v2 = VehicleScenarioDefinition(vehicle_id="dup", start_node_id="b", destination_node_id="a")
    bad = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=(v1, v2),
    )
    with pytest.raises(ScenarioValidationError, match="Duplicate vehicle ID 'dup'"):
        validate_scenario(bad)


def test_empty_vehicle_fields_raise(base_scenario):
    bad_v1 = VehicleScenarioDefinition(vehicle_id="", start_node_id="a", destination_node_id="b")
    with pytest.raises(ScenarioValidationError, match="empty vehicle_id"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_v1,),
            )
        )

    bad_v2 = VehicleScenarioDefinition(vehicle_id="v", start_node_id="", destination_node_id="b")
    with pytest.raises(ScenarioValidationError, match="empty start_node_id"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_v2,),
            )
        )

    bad_v3 = VehicleScenarioDefinition(vehicle_id="v", start_node_id="a", destination_node_id="")
    with pytest.raises(ScenarioValidationError, match="empty destination_node_id"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_v3,),
            )
        )


def test_invalid_routing_parameters_raise(base_scenario):
    bad_algo = VehicleScenarioDefinition(
        vehicle_id="v", start_node_id="a", destination_node_id="b", algorithm="INVALID_ALGO"
    )
    with pytest.raises(ScenarioValidationError, match="invalid algorithm"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_algo,),
            )
        )

    bad_cost = VehicleScenarioDefinition(
        vehicle_id="v", start_node_id="a", destination_node_id="b", cost_mode="INVALID_COST"
    )
    with pytest.raises(ScenarioValidationError, match="invalid cost_mode"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_cost,),
            )
        )


def test_negative_initial_speed_raises(base_scenario):
    bad_speed = VehicleScenarioDefinition(
        vehicle_id="v", start_node_id="a", destination_node_id="b", initial_speed_mps=-1.0
    )
    with pytest.raises(ScenarioValidationError, match="initial_speed_mps must be non-negative"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_speed,),
            )
        )


def test_invalid_kinematics_type_raises(base_scenario):
    bad_kin = VehicleScenarioDefinition(
        vehicle_id="v", start_node_id="a", destination_node_id="b", kinematics="bad"  # type: ignore
    )
    with pytest.raises(ScenarioValidationError, match="kinematics must be KinematicsConfig"):
        validate_scenario(
            ScenarioDefinition(
                metadata=base_scenario.metadata,
                road_network=base_scenario.road_network,
                vehicles=(bad_kin,),
            )
        )


def test_signal_validation_rules(base_scenario):
    s1 = TrafficSignalScenarioDefinition(signal_id="sig_1", node_id="node_r0_c0")
    s2 = TrafficSignalScenarioDefinition(signal_id="sig_1", node_id="node_r0_c1")
    dup_id = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        signals=(s1, s2),
    )
    with pytest.raises(ScenarioValidationError, match="Duplicate signal ID 'sig_1'"):
        validate_scenario(dup_id)

    s3 = TrafficSignalScenarioDefinition(signal_id="sig_3", node_id="node_r0_c0")
    dup_node = ScenarioDefinition(
        metadata=base_scenario.metadata,
        road_network=base_scenario.road_network,
        vehicles=base_scenario.vehicles,
        signals=(s1, s3),
    )
    with pytest.raises(
        ScenarioValidationError,
        match="Multiple signals registered for intersection node 'node_r0_c0'",
    ):
        validate_scenario(dup_node)


def test_graph_compatibility_checks():
    graph = generate_synthetic_city_grid(config=CityGridConfig(rows=2, cols=2))
    rn_supplied = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SUPPLIED_GRAPH,
        supplied_graph=graph,
    )

    # Missing start node
    v_bad_start = VehicleScenarioDefinition(
        vehicle_id="v_bad", start_node_id="nonexistent_start", destination_node_id="node_r0_c1"
    )
    s_start = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s", name="s"),
        road_network=rn_supplied,
        vehicles=(v_bad_start,),
    )
    with pytest.raises(ScenarioValidationError, match="start node 'nonexistent_start'"):
        validate_graph_compatibility(s_start, graph)

    # Missing destination node
    v_bad_dest = VehicleScenarioDefinition(
        vehicle_id="v_bad", start_node_id="node_r0_c0", destination_node_id="nonexistent_dest"
    )
    s_dest = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s", name="s"),
        road_network=rn_supplied,
        vehicles=(v_bad_dest,),
    )
    with pytest.raises(ScenarioValidationError, match="destination node 'nonexistent_dest'"):
        validate_graph_compatibility(s_dest, graph)

    # Missing signal node
    sig_bad_node = TrafficSignalScenarioDefinition(signal_id="sig_x", node_id="nonexistent_node")
    s_sig_node = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s", name="s"),
        road_network=rn_supplied,
        vehicles=(),
        signals=(sig_bad_node,),
    )
    with pytest.raises(ScenarioValidationError, match="signal 'sig_x' node 'nonexistent_node'"):
        validate_graph_compatibility(s_sig_node, graph)

    # Missing incoming edge
    sig_bad_edge = TrafficSignalScenarioDefinition(
        signal_id="sig_x", node_id="node_r0_c0", incoming_edge_ids=("unknown_edge",)
    )
    s_sig_edge = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s", name="s"),
        road_network=rn_supplied,
        vehicles=(),
        signals=(sig_bad_edge,),
    )
    with pytest.raises(ScenarioValidationError, match="unknown incoming edge 'unknown_edge'"):
        validate_graph_compatibility(s_sig_edge, graph)


def test_serialization_to_dict(base_scenario):
    data = base_scenario.to_dict()
    assert data["metadata"]["id"] == "test_scn"
    assert data["time_step_s"] == 0.1
    assert data["max_ticks"] == 100
    assert len(data["vehicles"]) == 1
    assert data["vehicles"][0]["vehicle_id"] == "v1"
