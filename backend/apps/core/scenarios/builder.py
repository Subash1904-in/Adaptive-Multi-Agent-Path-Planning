"""Scenario builder assembling RoadGraph, signals, agents, and SimulationEngine.

Constructs an authoritative, fully validated, and reproducible simulation environment
from a ScenarioDefinition without exposing partially initialized states.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import networkx as nx

from apps.core.domain.models import TrafficSignal, Vehicle
from apps.core.domain.values import Position2D
from apps.core.emergency.models import EmergencyLifecycleState
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.graph.osm_models import OSMImportConfig
from apps.core.graph.osm_service import import_osm_road_network
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.crosswalk import Crosswalk
from apps.core.pedestrians.models import PedestrianConfig, PedestrianLifecycleState
from apps.core.routing.exceptions import NoPathFoundError
from apps.core.routing.planner import RoutePlanner
from apps.core.scenarios.exceptions import (
    ScenarioBuilderError,
    ScenarioValidationError,
    UnreachableDestinationError,
)
from apps.core.scenarios.models import (
    RoadNetworkSourceType,
    ScenarioDefinition,
)
from apps.core.scenarios.validation import validate_graph_compatibility, validate_scenario
from apps.core.signals.controller import TrafficSignalController
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.models import WorldSnapshot
from apps.core.simulation.world import WorldState


@dataclass(frozen=True)
class ScenarioRunContext:
    """Encapsulates runtime objects assembled for scenario execution."""

    scenario: ScenarioDefinition
    world: WorldState
    engine: SimulationEngine
    planner: RoutePlanner
    initial_snapshot: WorldSnapshot
    excluded_vehicle_ids: tuple[str, ...] = ()


class ScenarioBuilder:
    """Builder that transforms an immutable ScenarioDefinition into runnable simulation objects."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        acquisition_fn: Optional[Callable[[OSMImportConfig], nx.MultiDiGraph]] = None,
    ) -> None:
        """Initialize builder with a ScenarioDefinition.

        Args:
            scenario: The authoritative ScenarioDefinition.
            acquisition_fn: Optional override for OSM acquisition (testing/mocking).
        """
        self.scenario = scenario
        self.acquisition_fn = acquisition_fn

    def build(self) -> ScenarioRunContext:
        """Assemble all runtime simulation objects and return the ScenarioRunContext.

        Returns:
            ScenarioRunContext containing world, engine, planner, and initial baseline snapshot.

        Raises:
            ScenarioValidationError: If configuration fails validation.
            UnreachableDestinationError: If an unreachable vehicle cannot be routed.
            ScenarioBuilderError: If network generation or component assembly fails.
        """
        # 1. Structural and semantic validation
        validate_scenario(self.scenario)

        # 2. RoadGraph resolution
        graph = self._resolve_road_graph()

        # 3. Graph compatibility check
        validate_graph_compatibility(self.scenario, graph)

        # 4. Route planner construction
        try:
            planner = RoutePlanner(road_graph=graph)
        except Exception as exc:
            msg = (
                f"Failed to initialize RoutePlanner for scenario "
                f"'{self.scenario.metadata.id}': {exc}"
            )
            raise ScenarioBuilderError(
                msg,
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

        # 5. WorldState & SimulationClock construction
        try:
            clock = SimulationClock(time_step_s=self.scenario.time_step_s)
            world = WorldState(
                road_graph=graph,
                clock=clock,
                metadata=dict(self.scenario.simulation_metadata),
                communication_config=self.scenario.v2v_config,
                coordination_config=self.scenario.coordination_config,
                adaptive_routing_config=self.scenario.adaptive_routing_config,
                safety_config=self.scenario.safety_config,
                emergency_config=self.scenario.emergency_config,
                decision_config=self.scenario.decision_config,
            )
        except Exception as exc:
            msg = (
                f"Failed to initialize WorldState for scenario "
                f"'{self.scenario.metadata.id}': {exc}"
            )
            raise ScenarioBuilderError(
                msg,
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

        # 6. Explicit traffic signal registration
        self._register_signals(world, graph)

        # 6.5. Explicit crosswalk registration
        self._register_crosswalks(world)

        # 6.7. Pedestrian agent registration
        self._register_pedestrians(world)

        # 7. Route planning and vehicle agent registration
        excluded_vehicles: list[str] = []
        # Sort vehicles by ID for deterministic registration order
        sorted_vehicle_defs = sorted(self.scenario.vehicles, key=lambda v: v.vehicle_id)

        for vdef in sorted_vehicle_defs:
            closed_edges = set(vdef.closed_edge_ids) if vdef.closed_edge_ids else None
            try:
                routing_res = planner.find_route(
                    start_node_id=vdef.start_node_id,
                    destination_node_id=vdef.destination_node_id,
                    algorithm=vdef.algorithm,
                    cost_mode=vdef.cost_mode,
                    closed_edge_ids=closed_edges,
                )
                route = routing_res.route
            except NoPathFoundError as exc:
                if not self.scenario.allow_unreachable_vehicles:
                    raise UnreachableDestinationError(
                        vehicle_id=vdef.vehicle_id,
                        start_node_id=vdef.start_node_id,
                        destination_node_id=vdef.destination_node_id,
                    ) from exc
                excluded_vehicles.append(vdef.vehicle_id)
                continue
            except Exception as exc:
                if isinstance(exc, ScenarioValidationError):
                    raise
                raise ScenarioBuilderError(
                    f"Unexpected routing failure for vehicle '{vdef.vehicle_id}': {exc}",
                    scenario_id=self.scenario.metadata.id,
                    cause=exc,
                ) from exc

            # Instantiate vehicle entity and agent
            try:
                start_node = graph.get_node(vdef.start_node_id)
                max_spd = (
                    vdef.kinematics.max_speed_mps
                    if vdef.kinematics
                    else max(13.89, vdef.initial_speed_mps)
                )
                vehicle_entity = Vehicle(
                    id=vdef.vehicle_id,
                    vehicle_type=vdef.vehicle_type,
                    position=Position2D(x=start_node.position.x, y=start_node.position.y),
                    speed_mps=vdef.initial_speed_mps,
                    max_speed_mps=max(max_spd, vdef.initial_speed_mps),
                )
                agent = VehicleAgent(
                    vehicle=vehicle_entity,
                    road_graph=graph,
                    route=route,
                    config=vdef.kinematics,
                )
                agent.start()
                world.add_agent(agent)
            except Exception as exc:
                raise ScenarioBuilderError(
                    f"Failed to instantiate agent for vehicle '{vdef.vehicle_id}': {exc}",
                    scenario_id=self.scenario.metadata.id,
                    cause=exc,
                ) from exc

        # 7.5. Emergency vehicle registration and auto-activation
        for ev in self.scenario.emergency_vehicles:
            world.register_emergency_vehicle(
                vehicle_id=ev.vehicle_id,
                initial_state=EmergencyLifecycleState.INACTIVE,
            )
            if ev.auto_activate and ev.destination_node_id:
                try:
                    world.emergency_manager.activate_emergency(
                        vehicle_id=ev.vehicle_id,
                        emergency_type=ev.emergency_type,
                        destination_node_id=ev.destination_node_id,
                        current_time_s=clock.elapsed_time_s,
                        priority_level=ev.priority_level,
                        ttl_s=ev.ttl_s,
                        start_node_id=ev.start_node_id or None,
                    )
                except Exception:
                    pass

        # 8. Save baseline for deterministic resets
        world.save_baseline()

        # 9. Construct SimulationEngine
        try:
            engine = SimulationEngine(world=world)
        except Exception as exc:
            raise ScenarioBuilderError(
                f"Failed to instantiate SimulationEngine: {exc}",
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

        # 10. Capture initial baseline snapshot
        initial_snapshot = world.get_snapshot()

        return ScenarioRunContext(
            scenario=self.scenario,
            world=world,
            engine=engine,
            planner=planner,
            initial_snapshot=initial_snapshot,
            excluded_vehicle_ids=tuple(excluded_vehicles),
        )

    def _resolve_road_graph(self) -> RoadGraph:
        """Resolve or generate the RoadGraph according to road_network configuration."""
        rn = self.scenario.road_network
        src = rn.source_type

        try:
            if src == RoadNetworkSourceType.SYNTHETIC_GRID:
                if rn.grid_config is not None:
                    grid_cfg = rn.grid_config
                else:
                    seed = self.scenario.seed if self.scenario.seed is not None else 42
                    grid_cfg = CityGridConfig(seed=seed)
                return generate_synthetic_city_grid(config=grid_cfg)

            elif src == RoadNetworkSourceType.SUPPLIED_GRAPH:
                if rn.supplied_graph is None:
                    raise ScenarioValidationError(
                        "Supplied RoadGraph is None.",
                        field="road_network.supplied_graph",
                    )
                return rn.supplied_graph

            elif src == RoadNetworkSourceType.OSM_IMPORT:
                if rn.osm_config is None:
                    raise ScenarioValidationError(
                        "OSMImportConfig is None.",
                        field="road_network.osm_config",
                    )
                res = import_osm_road_network(
                    config=rn.osm_config,
                    acquisition_fn=self.acquisition_fn,
                )
                return res.graph

            else:
                raise ScenarioValidationError(
                    f"Unsupported road network source type '{src}'.",
                    field="road_network.source_type",
                )
        except ScenarioValidationError:
            raise
        except Exception as exc:
            raise ScenarioBuilderError(
                f"Failed to resolve road graph for scenario '{self.scenario.metadata.id}': {exc}",
                scenario_id=self.scenario.metadata.id,
                cause=exc,
            ) from exc

    def _register_signals(self, world: WorldState, graph: RoadGraph) -> None:
        """Register explicit scenario traffic signals into WorldState."""
        for sig_def in self.scenario.signals:
            if world.has_signal(sig_def.signal_id):
                continue
            if world.get_signal_at_node(sig_def.node_id) is not None:
                continue

            try:
                sig_entity = TrafficSignal(
                    id=sig_def.signal_id,
                    node_id=sig_def.node_id,
                )
                incoming = list(sig_def.incoming_edge_ids) if sig_def.incoming_edge_ids else None
                controller = TrafficSignalController(
                    signal=sig_entity,
                    config=sig_def.config,
                    road_graph=graph,
                    incoming_edge_ids=incoming,
                )
                world.add_traffic_signal(controller)
            except Exception as exc:
                raise ScenarioBuilderError(
                    f"Failed to register signal '{sig_def.signal_id}': {exc}",
                    scenario_id=self.scenario.metadata.id,
                    cause=exc,
                ) from exc

    def _register_crosswalks(self, world: WorldState) -> None:
        """Register crosswalks defined in the scenario definition."""
        sorted_crosswalks = sorted(self.scenario.crosswalks, key=lambda c: c.crosswalk_id)
        for cw_def in sorted_crosswalks:
            try:
                crosswalk = Crosswalk(
                    crosswalk_id=cw_def.crosswalk_id,
                    entry_point=cw_def.entry_point,
                    exit_point=cw_def.exit_point,
                    width_m=cw_def.width_m,
                    associated_intersection_id=cw_def.associated_intersection_id,
                    associated_road_segment_ids=cw_def.associated_road_segment_ids,
                    signal_controller_id=cw_def.signal_controller_id,
                    walk_signal_phase=cw_def.walk_signal_phase,
                    clearance_signal_phase=cw_def.clearance_signal_phase,
                    metadata=cw_def.metadata,
                )
                world.register_crosswalk(crosswalk)
            except Exception as exc:
                raise ScenarioBuilderError(
                    f"Failed to register crosswalk '{cw_def.crosswalk_id}': {exc}",
                    scenario_id=self.scenario.metadata.id,
                    cause=exc,
                ) from exc

    def _register_pedestrians(self, world: WorldState) -> None:
        """Register pedestrian agents defined in the scenario definition."""
        sorted_pedestrians = sorted(self.scenario.pedestrians, key=lambda p: p.pedestrian_id)
        for ped_def in sorted_pedestrians:
            try:
                config = PedestrianConfig(
                    walking_speed_mps=ped_def.walking_speed_mps,
                    max_speed_mps=ped_def.max_speed_mps,
                    length_m=ped_def.length_m,
                    width_m=ped_def.width_m,
                    arrival_tolerance_m=ped_def.arrival_tolerance_m,
                    waiting_distance_m=ped_def.waiting_distance_m,
                )
                init_state = ped_def.metadata.get("initial_state", PedestrianLifecycleState.IDLE)
                ped_agent = PedestrianAgent(
                    pedestrian_id=ped_def.pedestrian_id,
                    initial_position=ped_def.initial_position,
                    destination_point=ped_def.destination_point,
                    crosswalk_id=ped_def.crosswalk_id,
                    config=config,
                    initial_heading_rad=ped_def.initial_heading_rad,
                    initial_speed_mps=ped_def.initial_speed_mps,
                    initial_state=init_state,
                )
                if init_state == PedestrianLifecycleState.IDLE:
                    ped_agent.start()
                world.register_pedestrian(ped_agent)
            except Exception as exc:
                raise ScenarioBuilderError(
                    f"Failed to register pedestrian '{ped_def.pedestrian_id}': {exc}",
                    scenario_id=self.scenario.metadata.id,
                    cause=exc,
                ) from exc
