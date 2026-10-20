"""Tests for ScenarioBuilder object assembly, signal/agent registration, and error handling."""

import networkx as nx
import pytest

from apps.core.domain.enums import VehicleState
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.osm_models import BoundingBox, OSMImportConfig
from apps.core.routing.models import RoutingAlgorithm
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.scenarios.exceptions import (
    ScenarioBuilderError,
    UnreachableDestinationError,
)
from apps.core.scenarios.models import (
    RoadNetworkDefinition,
    RoadNetworkSourceType,
    ScenarioDefinition,
    ScenarioMetadata,
    TrafficSignalScenarioDefinition,
    VehicleScenarioDefinition,
)
from apps.core.signals.models import SignalCycleConfig


def test_build_synthetic_grid_scenario():
    grid_cfg = CityGridConfig(rows=3, cols=3, spacing_m=100.0)
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=grid_cfg,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="v1",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        algorithm=RoutingAlgorithm.ASTAR,
    )
    v2 = VehicleScenarioDefinition(
        vehicle_id="v2",
        start_node_id="node_r0_c1",
        destination_node_id="node_r2_c1",
        algorithm=RoutingAlgorithm.DIJKSTRA,
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_syn", name="Synthetic Test"),
        road_network=rn,
        vehicles=(v1, v2),
        time_step_s=0.1,
    )

    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()

    assert context.world is not None
    assert context.engine is not None
    assert context.planner is not None
    assert context.world.agent_count == 2
    assert context.world.agent_ids == ["v1", "v2"]
    assert context.initial_snapshot.tick == 0
    assert context.initial_snapshot.agent_count == 2
    # Ensure agents were started and are EN_ROUTE
    for aid in ["v1", "v2"]:
        agent = context.world.get_agent(aid)
        assert agent.state == VehicleState.EN_ROUTE


def test_build_supplied_graph_scenario():
    graph = generate_synthetic_city_grid(config=CityGridConfig(rows=2, cols=2))
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SUPPLIED_GRAPH,
        supplied_graph=graph,
    )
    v1 = VehicleScenarioDefinition(
        vehicle_id="v1",
        start_node_id="node_r0_c0",
        destination_node_id="node_r1_c1",
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_sup", name="Supplied Test"),
        road_network=rn,
        vehicles=(v1,),
    )

    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()

    assert context.world.road_graph is graph


def test_build_with_traffic_signals():
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=CityGridConfig(rows=3, cols=3, signalized_intersections=[]),
    )
    sig = TrafficSignalScenarioDefinition(
        signal_id="sig_center",
        node_id="node_r1_c1",
        config=SignalCycleConfig(green_duration_s=8.0, yellow_duration_s=2.0, red_duration_s=8.0),
    )
    v = VehicleScenarioDefinition(
        vehicle_id="v1",
        start_node_id="node_r1_c0",
        destination_node_id="node_r1_c2",
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_sig", name="Signal Test"),
        road_network=rn,
        vehicles=(v,),
        signals=(sig,),
    )

    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()

    assert context.world.has_signal("sig_center")
    ctrl = context.world.get_signal("sig_center")
    assert ctrl.node_id == "node_r1_c1"


def test_build_unreachable_destination_raises():
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=CityGridConfig(rows=3, cols=3),
    )
    # Block outgoing edges from node_r0_c0
    v = VehicleScenarioDefinition(
        vehicle_id="v_trapped",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        closed_edge_ids=("edge_r0_c0_to_r0_c1", "edge_r0_c0_to_r1_c0"),
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_unreach", name="Unreachable"),
        road_network=rn,
        vehicles=(v,),
        allow_unreachable_vehicles=False,
    )

    builder = ScenarioBuilder(scenario=scenario)
    with pytest.raises(UnreachableDestinationError) as exc_info:
        builder.build()
    assert exc_info.value.vehicle_id == "v_trapped"


def test_build_unreachable_destination_excluded_when_allowed():
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
        grid_config=CityGridConfig(rows=3, cols=3),
    )
    v_trapped = VehicleScenarioDefinition(
        vehicle_id="v_trapped",
        start_node_id="node_r0_c0",
        destination_node_id="node_r2_c2",
        closed_edge_ids=("edge_r0_c0_to_r0_c1", "edge_r0_c0_to_r1_c0"),
    )
    v_ok = VehicleScenarioDefinition(
        vehicle_id="v_ok",
        start_node_id="node_r1_c1",
        destination_node_id="node_r1_c2",
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_unreach_allow", name="Allowed Unreachable"),
        road_network=rn,
        vehicles=(v_trapped, v_ok),
        allow_unreachable_vehicles=True,
    )

    builder = ScenarioBuilder(scenario=scenario)
    context = builder.build()

    assert context.excluded_vehicle_ids == ("v_trapped",)
    assert context.world.agent_count == 1
    assert context.world.has_agent("v_ok")
    assert not context.world.has_agent("v_trapped")


def test_build_osm_mock_acquisition():
    def mock_acq(cfg: OSMImportConfig) -> nx.MultiDiGraph:
        G = nx.MultiDiGraph(crs="EPSG:4326")
        G.add_node(1, x=-122.4194, y=37.7749)
        G.add_node(2, x=-122.4184, y=37.7749)
        G.add_edge(1, 2, 0, length=80.0, maxspeed="30", highway="residential")
        G.add_edge(2, 1, 0, length=80.0, maxspeed="30", highway="residential")
        return G

    osm_cfg = OSMImportConfig(
        bounds=BoundingBox(north=37.8, south=37.7, east=-122.4, west=-122.5),
        allow_fallback=False,
    )
    rn = RoadNetworkDefinition(
        source_type=RoadNetworkSourceType.OSM_IMPORT,
        osm_config=osm_cfg,
    )
    v = VehicleScenarioDefinition(
        vehicle_id="v_osm",
        start_node_id="osm_node_1",
        destination_node_id="osm_node_2",
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="test_osm", name="OSM Scenario"),
        road_network=rn,
        vehicles=(v,),
    )

    builder = ScenarioBuilder(scenario=scenario, acquisition_fn=mock_acq)
    context = builder.build()

    assert context.world.agent_count == 1
    assert context.world.has_agent("v_osm")


def test_builder_fails_cleanly_on_unexpected_error(monkeypatch):
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s_err", name="Error"),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=CityGridConfig(rows=2, cols=2),
        ),
        vehicles=(),
    )
    builder = ScenarioBuilder(scenario=scenario)

    # Simulate unexpected failure during WorldState instantiation
    def bad_init(*args, **kwargs):
        raise RuntimeError("Disk corrupted")

    monkeypatch.setattr("apps.core.scenarios.builder.WorldState", bad_init)
    with pytest.raises(ScenarioBuilderError, match="Failed to initialize WorldState"):
        builder.build()


def test_builder_fails_on_route_planner_error(monkeypatch):
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s_err_rp", name="Error RP"),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=CityGridConfig(rows=2, cols=2),
        ),
        vehicles=(),
    )
    builder = ScenarioBuilder(scenario=scenario)

    def bad_planner(*args, **kwargs):
        raise RuntimeError("Planner init failed")

    monkeypatch.setattr("apps.core.scenarios.builder.RoutePlanner", bad_planner)
    with pytest.raises(ScenarioBuilderError, match="Failed to initialize RoutePlanner"):
        builder.build()


def test_builder_fails_on_agent_creation_error(monkeypatch):
    v = VehicleScenarioDefinition(
        vehicle_id="v_fail",
        start_node_id="node_r0_c0",
        destination_node_id="node_r0_c1",
    )
    scenario = ScenarioDefinition(
        metadata=ScenarioMetadata(id="s_err_agent", name="Error Agent"),
        road_network=RoadNetworkDefinition(
            source_type=RoadNetworkSourceType.SYNTHETIC_GRID,
            grid_config=CityGridConfig(rows=2, cols=2),
        ),
        vehicles=(v,),
    )
    builder = ScenarioBuilder(scenario=scenario)

    def bad_agent(*args, **kwargs):
        raise RuntimeError("Agent instantiation failure")

    monkeypatch.setattr("apps.core.scenarios.builder.VehicleAgent", bad_agent)
    with pytest.raises(ScenarioBuilderError, match="Failed to instantiate agent"):
        builder.build()
