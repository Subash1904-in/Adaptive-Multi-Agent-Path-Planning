"""WorldState container managing RoadGraph, VehicleAgents, and authoritative clock.

Maintains deterministic vehicle collections, agent-graph compatibility checks,
immutable state snapshots, and baseline state capture for reproducible resets.
"""

from typing import Any, Optional, Union

from apps.core.communication.models import CommunicationConfig
from apps.core.communication.neighbors import NeighborTable
from apps.core.communication.network import SimulatedCommunicationNetwork
from apps.core.communication.scheduler import BroadcastScheduler
from apps.core.coordination.knowledge import VehicleKnowledgeStore
from apps.core.coordination.manager import CoordinationManager
from apps.core.coordination.models import CoordinationConfig
from apps.core.decision.config import DecisionConfig
from apps.core.decision.manager import DecisionManager
from apps.core.domain.models import SimulationConfig, TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.emergency.models import (
    EmergencyConfig,
    EmergencyCorridor,
    EmergencyLifecycleState,
    PriorityRequest,
)
from apps.core.emergency.priority_manager import EmergencyPriorityManager
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.pedestrians.agent import PedestrianAgent
from apps.core.pedestrians.crosswalk import Crosswalk
from apps.core.pedestrians.exceptions import (
    CrosswalkNotFoundError,
    DuplicatePedestrianError,
    InvalidCrosswalkError,
    PedestrianNotFoundError,
)
from apps.core.pedestrians.metrics import PedestrianMetrics
from apps.core.routing.adapter import DynamicRouteAdapter
from apps.core.routing.models import AdaptiveRoutingConfig
from apps.core.safety.manager import SafetyManager
from apps.core.safety.models import SafetyConfig
from apps.core.signals.controller import TrafficSignalController
from apps.core.signals.exceptions import (
    DuplicateSignalError,
    InvalidIntersectionAssociationError,
    SignalNotFoundError,
)
from apps.core.signals.models import SignalCycleConfig, SignalQueryResult
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.exceptions import (
    AgentNotFoundError,
    DuplicateAgentIdError,
    IncompatibleAgentGraphError,
)
from apps.core.simulation.models import VehicleSnapshot, WorldSnapshot


class WorldState:
    """Authoritative container managing the simulation road network and vehicle agents.

    Provides stable deterministic agent ordering, graph consistency enforcement,
    and point-in-time snapshot generation.
    """

    def __init__(
        self,
        road_graph: RoadGraph,
        config: Optional[SimulationConfig] = None,
        clock: Optional[SimulationClock] = None,
        metadata: Optional[dict[str, Any]] = None,
        communication_config: Optional[CommunicationConfig] = None,
        coordination_config: Optional[CoordinationConfig] = None,
        adaptive_routing_config: Optional[AdaptiveRoutingConfig] = None,
        safety_config: Optional[SafetyConfig] = None,
        emergency_config: Optional[EmergencyConfig] = None,
        decision_config: Optional[DecisionConfig] = None,
    ) -> None:
        """Initialize the world state container.

        Args:
            road_graph: Authoritative RoadGraph representing topological connectivity.
            config: Optional SimulationConfig defining time steps and parameters.
            clock: Optional authoritative SimulationClock. If omitted, initialized with config dt.
            metadata: Optional user-defined dictionary for simulation context.
            communication_config: Optional CommunicationConfig governing V2V parameters.
            coordination_config: Optional CoordinationConfig governing knowledge sharing.
            adaptive_routing_config: Optional AdaptiveRoutingConfig governing dynamic rerouting.
            safety_config: Optional SafetyConfig governing collision detection and avoidance.
            emergency_config: Optional EmergencyConfig governing emergency priority and corridors.
            decision_config: Optional DecisionConfig governing AI decision policy evaluation.

        Raises:
            TypeError: If road_graph is not an instance of RoadGraph.
        """
        if not isinstance(road_graph, RoadGraph):
            raise TypeError(f"Expected RoadGraph instance, got {type(road_graph).__name__}.")

        self.road_graph: RoadGraph = road_graph
        self.config: SimulationConfig = config or SimulationConfig()
        self.clock: SimulationClock = clock or SimulationClock(time_step_s=self.config.time_step_s)
        self.metadata: dict[str, Any] = dict(metadata or {})

        self._agents: dict[str, VehicleAgent] = {}
        self._agent_baselines: dict[str, dict[str, Any]] = {}

        self._signals: dict[str, TrafficSignalController] = {}
        self._signal_node_map: dict[str, str] = {}
        self._signal_edge_map: dict[str, str] = {}

        # Initialize V2V communication subsystem
        if communication_config is not None:
            self.communication_config: CommunicationConfig = communication_config
        else:
            self.communication_config = CommunicationConfig(
                enabled=self.config.enable_v2v,
                range_m=self.config.communication_radius_m,
            )
        self.communication_network: SimulatedCommunicationNetwork = SimulatedCommunicationNetwork(
            config=self.communication_config
        )
        self.broadcast_scheduler: BroadcastScheduler = BroadcastScheduler(
            broadcast_interval_s=self.communication_config.broadcast_interval_s,
            message_ttl_s=self.communication_config.message_ttl_s,
        )
        self._comm_baseline: Optional[dict[str, Any]] = None
        self._sched_baseline: Optional[dict[str, Any]] = None

        # Initialize Decentralized V2V Coordination subsystem
        if coordination_config is not None:
            self.coordination_config: CoordinationConfig = coordination_config
        else:
            self.coordination_config = CoordinationConfig(enabled=self.communication_config.enabled)
        self.coordination_manager: CoordinationManager = CoordinationManager(
            config=self.coordination_config,
            road_graph=self.road_graph,
        )
        self._coord_baseline: Optional[dict[str, Any]] = None

        # Initialize Adaptive Dynamic Routing subsystem
        if adaptive_routing_config is not None:
            self.adaptive_routing_config: AdaptiveRoutingConfig = adaptive_routing_config
        else:
            self.adaptive_routing_config = AdaptiveRoutingConfig(enabled=False)
        self.adaptive_routing_adapter: DynamicRouteAdapter = DynamicRouteAdapter(
            road_graph=self.road_graph,
            config=self.adaptive_routing_config,
        )
        self._routing_baseline: Optional[dict[str, Any]] = None

        # Initialize Safety and Collision Avoidance subsystem
        if safety_config is not None:
            self.safety_config: SafetyConfig = safety_config
        else:
            self.safety_config = SafetyConfig(enabled=False)
        self.safety_manager: SafetyManager = SafetyManager(config=self.safety_config)
        self._safety_baseline: Optional[dict[str, Any]] = None

        # Initialize Pedestrian and Crosswalk subsystem
        self._pedestrians: dict[str, PedestrianAgent] = {}
        self._pedestrian_baselines: dict[str, dict[str, Any]] = {}
        self._crosswalks: dict[str, Crosswalk] = {}
        self.pedestrian_metrics: PedestrianMetrics = PedestrianMetrics()
        self._pedestrian_metrics_baseline: Optional[dict[str, Any]] = None

        # Initialize Emergency Priority and Corridors subsystem
        if emergency_config is not None:
            self.emergency_config: EmergencyConfig = emergency_config
        else:
            self.emergency_config = EmergencyConfig()
        self.emergency_manager: EmergencyPriorityManager = EmergencyPriorityManager(
            road_graph=self.road_graph,
            config=self.emergency_config,
        )
        self._emergency_baseline: Optional[dict[str, Any]] = None

        # Initialize Decision Policy subsystem
        if decision_config is not None:
            self.decision_config: DecisionConfig = decision_config
        else:
            self.decision_config = DecisionConfig(enabled=False)
        self.decision_manager: DecisionManager = DecisionManager(config=self.decision_config)
        self._decision_baseline: Optional[dict[str, Any]] = None

        # Link decision and emergency managers to adaptive routing adapter
        self.adaptive_routing_adapter.decision_manager = self.decision_manager
        self.adaptive_routing_adapter.emergency_manager = self.emergency_manager

        # Auto-register signals defined in the road_graph
        for sig in self.road_graph.get_traffic_signals().values():
            if sig.id not in self._signals:
                controller = TrafficSignalController(
                    signal=sig,
                    road_graph=self.road_graph,
                )
                self._register_controller(controller)

    def _register_controller(self, controller: TrafficSignalController) -> None:
        """Register an initialized TrafficSignalController into internal lookup maps."""
        self._signals[controller.id] = controller
        self._signal_node_map[controller.node_id] = controller.id
        for edge_id in controller.incoming_edge_ids:
            self._signal_edge_map[edge_id] = controller.id

    @property
    def signal_count(self) -> int:
        """Total number of registered traffic signals in the world."""
        return len(self._signals)

    @property
    def signal_ids(self) -> list[str]:
        """List of all registered signal identifiers in deterministic sorted order."""
        return sorted(self._signals.keys())

    def get_signals(self) -> list[TrafficSignalController]:
        """Enumerate all registered traffic signal controllers in deterministic sorted order."""
        return [self._signals[sid] for sid in sorted(self._signals.keys())]

    def has_signal(self, signal_id: str) -> bool:
        """Check whether a traffic signal is registered in the world."""
        return signal_id in self._signals

    def get_signal(self, signal_id: str) -> TrafficSignalController:
        """Retrieve a registered traffic signal controller by signal ID."""
        if signal_id not in self._signals:
            raise SignalNotFoundError(signal_id)
        return self._signals[signal_id]

    def get_signal_at_node(self, node_id: str) -> Optional[TrafficSignalController]:
        """Retrieve the traffic signal governing an intersection node, or None."""
        sig_id = self._signal_node_map.get(node_id)
        if sig_id is None:
            return None
        return self._signals.get(sig_id)

    def get_signal_for_edge(self, edge_id: str) -> Optional[TrafficSignalController]:
        """Retrieve the traffic signal governing an incoming road edge approach, or None."""
        sig_id = self._signal_edge_map.get(edge_id)
        if sig_id is None:
            return None
        return self._signals.get(sig_id)

    def add_traffic_signal(
        self,
        signal_or_controller: Union[TrafficSignal, TrafficSignalController],
        config: Optional[SignalCycleConfig] = None,
        incoming_edge_ids: Optional[list[str]] = None,
    ) -> TrafficSignalController:
        """Register a traffic signal or controller in the world state.

        Args:
            signal_or_controller: Domain TrafficSignal or pre-configured TrafficSignalController.
            config: Optional SignalCycleConfig (used when passing TrafficSignal).
            incoming_edge_ids: Optional list of incoming road edge IDs.

        Returns:
            The registered TrafficSignalController.

        Raises:
            TypeError: If input is not a TrafficSignal or TrafficSignalController.
            DuplicateSignalError: If signal ID or intersection node already has a signal.
            InvalidIntersectionAssociationError: If node or edge associations are invalid.
        """
        if isinstance(signal_or_controller, TrafficSignal):
            controller = TrafficSignalController(
                signal=signal_or_controller,
                config=config,
                road_graph=self.road_graph,
                incoming_edge_ids=incoming_edge_ids,
            )
        elif isinstance(signal_or_controller, TrafficSignalController):
            controller = signal_or_controller
            if controller.road_graph is not None and controller.road_graph is not self.road_graph:
                raise InvalidIntersectionAssociationError(
                    f"TrafficSignalController '{controller.id}' is bound to a different RoadGraph.",
                    node_id=controller.node_id,
                )
            if not self.road_graph.has_node(controller.node_id):
                raise InvalidIntersectionAssociationError(
                    f"Traffic signal '{controller.id}' references "
                    f"non-existent node '{controller.node_id}'.",
                    node_id=controller.node_id,
                )
            for eid in controller.incoming_edge_ids:
                if not self.road_graph.has_edge(eid):
                    raise InvalidIntersectionAssociationError(
                        f"Traffic signal '{controller.id}' references non-existent edge '{eid}'.",
                        node_id=controller.node_id,
                    )
                edge = self.road_graph.get_edge(eid)
                if edge.end_node_id != controller.node_id:
                    raise InvalidIntersectionAssociationError(
                        f"Edge '{eid}' terminates at '{edge.end_node_id}', "
                        f"not '{controller.node_id}'.",
                        node_id=controller.node_id,
                    )
            # If controller had no road_graph or incoming edges, link it and discover
            if controller.road_graph is None:
                controller.road_graph = self.road_graph
                if not controller.incoming_edge_ids:
                    controller.incoming_edge_ids = sorted(
                        [edge.id for edge in self.road_graph.get_incoming_edges(controller.node_id)]
                    )
        else:
            raise TypeError(
                f"Expected TrafficSignal or TrafficSignalController, "
                f"got {type(signal_or_controller).__name__}."
            )

        if controller.id in self._signals:
            raise DuplicateSignalError(controller.id)
        if controller.node_id in self._signal_node_map:
            raise DuplicateSignalError(
                f"Intersection node '{controller.node_id}' already has a signal registered."
            )

        # Synchronize controller to road graph's signal registry if not present
        if self.road_graph.get_traffic_signal(controller.node_id) is None:
            self.road_graph._signals[controller.node_id] = controller.signal

        # Synchronize to current simulation time
        controller.update(self.clock.elapsed_time_s)

        self._register_controller(controller)
        return controller

    def remove_signal(self, signal_id: str) -> TrafficSignalController:
        """Remove and return a registered traffic signal controller."""
        if signal_id not in self._signals:
            raise SignalNotFoundError(signal_id)
        ctrl = self._signals.pop(signal_id)
        self._signal_node_map.pop(ctrl.node_id, None)
        for eid in ctrl.incoming_edge_ids:
            if self._signal_edge_map.get(eid) == signal_id:
                self._signal_edge_map.pop(eid, None)
        self.road_graph._signals.pop(ctrl.node_id, None)
        return ctrl

    def update_signals(self, sim_time_s: float) -> None:
        """Update all traffic signal controllers to the specified simulation time."""
        for ctrl in self._signals.values():
            ctrl.update(sim_time_s)

    def query_signal(self, signal_id: str, sim_time_s: Optional[float] = None) -> SignalQueryResult:
        """Query state and phase timing for a specific traffic signal."""
        if signal_id not in self._signals:
            raise SignalNotFoundError(signal_id)
        t = sim_time_s if sim_time_s is not None else self.clock.elapsed_time_s
        return self._signals[signal_id].query(sim_time_s=t)

    def query_signal_for_edge(
        self, edge_id: str, sim_time_s: Optional[float] = None
    ) -> Optional[SignalQueryResult]:
        """Query state and phase timing for a signal governing an edge approach, or None."""
        sig_id = self._signal_edge_map.get(edge_id)
        if sig_id is None:
            return None
        t = sim_time_s if sim_time_s is not None else self.clock.elapsed_time_s
        return self._signals[sig_id].query(sim_time_s=t)

    @property
    def agent_count(self) -> int:
        """Total number of registered vehicle agents in the world."""
        return len(self._agents)

    @property
    def agent_ids(self) -> list[str]:
        """List of all registered agent identifiers in deterministic sorted order."""
        return sorted(self._agents.keys())

    def get_agents(self) -> list[VehicleAgent]:
        """Enumerate all registered vehicle agents in deterministic sorted identifier order."""
        return [self._agents[aid] for aid in sorted(self._agents.keys())]

    def add_agent(self, agent: VehicleAgent) -> None:
        """Register a vehicle agent in the world state.

        Args:
            agent: VehicleAgent to register.

        Raises:
            TypeError: If agent is not an instance of VehicleAgent.
            DuplicateAgentIdError: If an agent with the same vehicle ID already exists.
            IncompatibleAgentGraphError: If the agent is bound to a different road graph.
        """
        if not isinstance(agent, VehicleAgent):
            raise TypeError(f"Expected VehicleAgent instance, got {type(agent).__name__}.")

        agent_id = agent.vehicle.id
        if agent_id in self._agents:
            raise DuplicateAgentIdError(agent_id)

        # Graph compatibility check: agent must be bound to the exact same RoadGraph instance
        if agent.road_graph is not self.road_graph:
            raise IncompatibleAgentGraphError(
                f"Agent '{agent_id}' is bound to a different RoadGraph instance "
                "than the WorldState.",
                agent_id=agent_id,
            )

        self._agents[agent_id] = agent
        self._agent_baselines[agent_id] = self._capture_agent_state(agent)
        if (
            self.communication_network.config.enabled
            and not self.communication_network.is_participant_registered(agent_id)
        ):
            self.communication_network.register_participant(agent_id)
        if self.coordination_manager.config.enabled and not self.coordination_manager.has_vehicle(
            agent_id
        ):
            self.coordination_manager.register_vehicle(agent_id)

    def get_agent(self, agent_id: str) -> VehicleAgent:
        """Retrieve a registered vehicle agent by identifier.

        Args:
            agent_id: Unique vehicle identifier.

        Returns:
            The registered VehicleAgent.

        Raises:
            AgentNotFoundError: If agent_id is not registered in the world.
        """
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        return self._agents[agent_id]

    def has_agent(self, agent_id: str) -> bool:
        """Check whether an agent identifier is registered in the world."""
        return agent_id in self._agents

    def remove_agent(self, agent_id: str) -> VehicleAgent:
        """Remove and return a registered vehicle agent.

        Args:
            agent_id: Unique vehicle identifier to remove.

        Returns:
            The removed VehicleAgent.

        Raises:
            AgentNotFoundError: If agent_id is not registered in the world.
        """
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        agent = self._agents.pop(agent_id)
        self._agent_baselines.pop(agent_id, None)
        if self.communication_network.config.enabled:
            self.communication_network.unregister_participant(agent_id)
        return agent

    @property
    def pedestrian_count(self) -> int:
        """Total number of registered pedestrian agents in the world."""
        return len(self._pedestrians)

    @property
    def pedestrian_ids(self) -> list[str]:
        """List of all registered pedestrian identifiers in deterministic sorted order."""
        return sorted(self._pedestrians.keys())

    def get_pedestrians(self) -> list[PedestrianAgent]:
        """Enumerate all registered pedestrian agents in deterministic sorted order."""
        return [self._pedestrians[pid] for pid in sorted(self._pedestrians.keys())]

    def add_pedestrian(self, pedestrian: PedestrianAgent) -> None:
        """Register a pedestrian agent in the world state.

        Args:
            pedestrian: PedestrianAgent to register.

        Raises:
            TypeError: If pedestrian is not an instance of PedestrianAgent.
            DuplicatePedestrianError: If a pedestrian with the same ID already exists.
        """
        if not isinstance(pedestrian, PedestrianAgent):
            raise TypeError(f"Expected PedestrianAgent instance, got {type(pedestrian).__name__}.")
        pid = pedestrian.pedestrian_id
        if pid in self._pedestrians:
            raise DuplicatePedestrianError(f"Pedestrian '{pid}' already registered.")
        self._pedestrians[pid] = pedestrian
        self._pedestrian_baselines[pid] = pedestrian.capture_state()

    def register_pedestrian(self, pedestrian: PedestrianAgent) -> None:
        """Alias for add_pedestrian."""
        self.add_pedestrian(pedestrian)

    def get_pedestrian(self, pedestrian_id: str) -> PedestrianAgent:
        """Retrieve a registered pedestrian agent by ID."""
        if pedestrian_id not in self._pedestrians:
            raise PedestrianNotFoundError(f"Pedestrian '{pedestrian_id}' not found.")
        return self._pedestrians[pedestrian_id]

    def has_pedestrian(self, pedestrian_id: str) -> bool:
        """Check whether a pedestrian identifier is registered in the world."""
        return pedestrian_id in self._pedestrians

    def remove_pedestrian(self, pedestrian_id: str) -> PedestrianAgent:
        """Remove and return a registered pedestrian agent."""
        if pedestrian_id not in self._pedestrians:
            raise PedestrianNotFoundError(f"Pedestrian '{pedestrian_id}' not found.")
        ped = self._pedestrians.pop(pedestrian_id)
        self._pedestrian_baselines.pop(pedestrian_id, None)
        return ped

    @property
    def crosswalk_count(self) -> int:
        """Total number of registered crosswalks in the world."""
        return len(self._crosswalks)

    @property
    def crosswalk_ids(self) -> list[str]:
        """List of all registered crosswalk identifiers in deterministic sorted order."""
        return sorted(self._crosswalks.keys())

    def get_crosswalks(self) -> list[Crosswalk]:
        """Enumerate all registered crosswalks in deterministic sorted order."""
        return [self._crosswalks[cid] for cid in sorted(self._crosswalks.keys())]

    def add_crosswalk(self, crosswalk: Crosswalk) -> None:
        """Register a crosswalk in the world state.

        Args:
            crosswalk: Crosswalk to register.

        Raises:
            TypeError: If crosswalk is not an instance of Crosswalk.
            InvalidCrosswalkError: If crosswalk ID exists or referenced nodes/edges do not exist.
        """
        if not isinstance(crosswalk, Crosswalk):
            raise TypeError(f"Expected Crosswalk instance, got {type(crosswalk).__name__}.")
        cid = crosswalk.crosswalk_id
        if cid in self._crosswalks:
            raise InvalidCrosswalkError(f"Crosswalk '{cid}' already registered.")

        if crosswalk.associated_intersection_id:
            if not self.road_graph.has_node(crosswalk.associated_intersection_id):
                raise InvalidCrosswalkError(
                    f"Crosswalk '{cid}' references non-existent intersection "
                    f"'{crosswalk.associated_intersection_id}'."
                )
        for eid in crosswalk.associated_road_segment_ids:
            if not self.road_graph.has_edge(eid):
                raise InvalidCrosswalkError(
                    f"Crosswalk '{cid}' references non-existent road segment '{eid}'."
                )

        self._crosswalks[cid] = crosswalk

    def register_crosswalk(self, crosswalk: Crosswalk) -> None:
        """Alias for add_crosswalk."""
        self.add_crosswalk(crosswalk)

    def get_crosswalk(self, crosswalk_id: str) -> Crosswalk:
        """Retrieve a registered crosswalk by ID."""
        if crosswalk_id not in self._crosswalks:
            raise CrosswalkNotFoundError(f"Crosswalk '{crosswalk_id}' not found.")
        return self._crosswalks[crosswalk_id]

    def has_crosswalk(self, crosswalk_id: str) -> bool:
        """Check whether a crosswalk identifier is registered in the world."""
        return crosswalk_id in self._crosswalks

    def remove_crosswalk(self, crosswalk_id: str) -> Crosswalk:
        """Remove and return a registered crosswalk."""
        if crosswalk_id not in self._crosswalks:
            raise CrosswalkNotFoundError(f"Crosswalk '{crosswalk_id}' not found.")
        return self._crosswalks.pop(crosswalk_id)

    def get_neighbor_table(self, vehicle_id: str) -> Optional[NeighborTable]:
        """Retrieve the neighbor table for a registered vehicle agent, or None."""
        return self.communication_network.get_neighbor_table(vehicle_id)

    @staticmethod
    def _capture_agent_state(agent: VehicleAgent) -> dict[str, Any]:
        """Capture a lightweight internal state dictionary of an agent for reset purposes."""
        return {
            "state": agent.state,
            "position": Position2D(x=agent.vehicle.position.x, y=agent.vehicle.position.y),
            "heading_rad": agent.vehicle.heading_rad,
            "speed_mps": agent.vehicle.speed_mps,
            "current_node_id": agent.vehicle.current_node_id,
            "current_edge_id": agent.vehicle.current_edge_id,
            "current_edge_index": agent.current_edge_index,
            "distance_along_segment_m": agent.distance_along_segment_m,
            "route_id": agent.vehicle.route_id,
            "target_node_id": agent.vehicle.target_node_id,
            "route": agent.route,
        }

    @staticmethod
    def _apply_agent_state(agent: VehicleAgent, state_dict: dict[str, Any]) -> None:
        """Restore an agent's internal and domain entity state from a captured dictionary."""
        agent.vehicle.state = state_dict["state"]
        pos = state_dict["position"]
        agent.vehicle.position = Position2D(x=pos.x, y=pos.y)
        agent.vehicle.heading_rad = state_dict["heading_rad"]
        agent.vehicle.speed_mps = state_dict["speed_mps"]
        agent.vehicle.current_node_id = state_dict["current_node_id"]
        agent.vehicle.current_edge_id = state_dict["current_edge_id"]
        agent.current_edge_index = state_dict["current_edge_index"]
        agent.distance_along_segment_m = state_dict["distance_along_segment_m"]
        agent.vehicle.route_id = state_dict["route_id"]
        agent.vehicle.target_node_id = state_dict["target_node_id"]
        if state_dict.get("route") is not None and agent.route is not state_dict["route"]:
            agent.assign_route(state_dict["route"])

    def save_baseline(self) -> None:
        """Capture the current state of all registered agents and subsystems for reset."""
        for agent_id, agent in self._agents.items():
            self._agent_baselines[agent_id] = self._capture_agent_state(agent)
        for ped_id, ped in self._pedestrians.items():
            self._pedestrian_baselines[ped_id] = ped.capture_state()
        self._pedestrian_metrics_baseline = self.pedestrian_metrics.capture_state()
        self._comm_baseline = self.communication_network.capture_state()
        self._sched_baseline = self.broadcast_scheduler.capture_state()
        self._coord_baseline = self.coordination_manager.capture_state()
        self._routing_baseline = self.adaptive_routing_adapter.capture_state()
        self._safety_baseline = self.safety_manager.capture_state()
        self._emergency_baseline = self.emergency_manager.capture_state()
        self._decision_baseline = self.decision_manager.capture_state()

    def restore_baseline(self) -> None:
        """Restore all registered agents and subsystems to their recorded baseline states."""
        for agent_id, baseline in self._agent_baselines.items():
            if agent_id in self._agents:
                self._apply_agent_state(self._agents[agent_id], baseline)
        for ped_id, baseline in self._pedestrian_baselines.items():
            if ped_id in self._pedestrians:
                self._pedestrians[ped_id].restore_state(baseline)
        if self._pedestrian_metrics_baseline is not None:
            self.pedestrian_metrics.restore_state(self._pedestrian_metrics_baseline)
        if self._comm_baseline is not None:
            self.communication_network.restore_state(self._comm_baseline)
        if self._sched_baseline is not None:
            self.broadcast_scheduler.restore_state(self._sched_baseline)
        if self._coord_baseline is not None:
            self.coordination_manager.restore_state(self._coord_baseline)
        if self._routing_baseline is not None:
            self.adaptive_routing_adapter.restore_state(self._routing_baseline)
        if self._safety_baseline is not None:
            self.safety_manager.restore_state(self._safety_baseline)
        if self._emergency_baseline is not None:
            self.emergency_manager.restore_state(self._emergency_baseline)
        if self._decision_baseline is not None:
            self.decision_manager.restore_state(self._decision_baseline)

    def reset(self) -> None:
        """Reset simulation clock to tick 0 and restore all agents, signals, comms, and safety."""
        self.clock.reset(initial_tick=0)
        self.restore_baseline()
        for ctrl in self._signals.values():
            ctrl.reset()
        self.pedestrian_metrics.reset()
        self.communication_network.reset()
        self.broadcast_scheduler.reset()
        self.coordination_manager.reset()
        self.adaptive_routing_adapter.reset()
        self.safety_manager.reset()
        self.emergency_manager.reset()
        self.decision_manager.reset()
        if self.communication_network.config.enabled:
            for aid in self._agents:
                if not self.communication_network.is_participant_registered(aid):
                    self.communication_network.register_participant(aid)
        if self.coordination_manager.config.enabled:
            for aid in self._agents:
                if not self.coordination_manager.has_vehicle(aid):
                    self.coordination_manager.register_vehicle(aid)

    def register_emergency_vehicle(
        self,
        vehicle_id: str,
        initial_state: EmergencyLifecycleState = EmergencyLifecycleState.INACTIVE,
    ) -> None:
        """Register a vehicle identifier as an emergency vehicle in the world."""
        self.emergency_manager.register_emergency_vehicle(
            vehicle_id=vehicle_id, initial_state=initial_state
        )

    def is_emergency_vehicle(self, vehicle_id: str) -> bool:
        """Check whether a vehicle is registered as an emergency vehicle."""
        return self.emergency_manager.is_emergency_vehicle(vehicle_id)

    def get_emergency_corridors(self) -> dict[str, EmergencyCorridor]:
        """Return active emergency corridors."""
        return {cid: c for cid, c in self.emergency_manager.corridors.items() if c.is_active}

    def get_emergency_requests(self) -> dict[str, PriorityRequest]:
        """Return active priority requests."""
        return dict(self.emergency_manager.active_requests)

    def get_snapshot(self) -> WorldSnapshot:
        """Generate an immutable point-in-time snapshot of world, agents, signals, and comms.

        Returns:
            WorldSnapshot containing clock status, vehicle snapshots, signals, and comms.
        """
        vehicle_snaps: dict[str, VehicleSnapshot] = {}
        for agent in self.get_agents():
            v = agent.vehicle
            vehicle_snaps[v.id] = VehicleSnapshot(
                vehicle_id=v.id,
                state=agent.state,
                position=Position2D(x=v.position.x, y=v.position.y),
                heading_rad=v.heading_rad,
                speed_mps=v.speed_mps,
                current_edge_id=v.current_edge_id,
                current_node_id=v.current_node_id,
                distance_along_segment_m=agent.distance_along_segment_m,
                remaining_route_distance_m=agent.remaining_route_distance_m,
                route_id=v.route_id,
                target_node_id=v.target_node_id,
            )

        signal_snaps = {c.id: c.get_snapshot(self.clock.elapsed_time_s) for c in self.get_signals()}

        comm_snap = None
        if self.communication_network.config.enabled:
            comm_snap = self.communication_network.get_snapshot(self.clock.elapsed_time_s).to_dict()

        coord_snap = None
        if self.coordination_manager.config.enabled:
            coord_snap = self.coordination_manager.get_snapshot(self.clock.elapsed_time_s).to_dict()

        routing_snap = None
        if self.adaptive_routing_adapter.config.enabled:
            routing_snap = self.adaptive_routing_adapter.metrics.to_dict()

        safety_snap = None
        if self.safety_manager.config.enabled:
            safety_snap = self.safety_manager.metrics.to_dict()

        ped_snaps = {p.pedestrian_id: p.capture_state() for p in self.get_pedestrians()}
        cw_snaps = {c.crosswalk_id: c.to_dict() for c in self.get_crosswalks()}
        ped_metrics_snap = (
            self.pedestrian_metrics.to_dict() if (self._pedestrians or self._crosswalks) else None
        )

        emergency_snap = {
            vid: self.emergency_manager.get_vehicle_state(vid).value
            for vid in self.emergency_manager.get_all_emergency_vehicles()
        }
        corridor_snaps = {
            cid: c.to_dict() for cid, c in self.emergency_manager.corridors.items() if c.is_active
        }
        emergency_metrics_snap = (
            self.emergency_manager.metrics.to_dict()
            if self.emergency_manager.get_all_emergency_vehicles()
            else None
        )

        return WorldSnapshot(
            tick=self.clock.tick_count,
            elapsed_time_s=self.clock.elapsed_time_s,
            time_step_s=self.clock.time_step_s,
            is_paused=self.clock.is_paused,
            agent_count=len(vehicle_snaps),
            vehicles=vehicle_snaps,
            signals=signal_snaps,
            communication=comm_snap,
            coordination=coord_snap,
            routing=routing_snap,
            safety=safety_snap,
            pedestrians=ped_snaps,
            crosswalks=cw_snaps,
            pedestrian_metrics=ped_metrics_snap,
            emergency=emergency_snap,
            corridors=corridor_snaps,
            emergency_metrics=emergency_metrics_snap,
            decision_metrics=(
                self.decision_manager.metrics.to_dict()
                if self.decision_manager.config.enabled
                else None
            ),
            decision_records=(
                [r.to_dict() for r in self.decision_manager._records]
                if self.decision_manager.config.enabled
                else None
            ),
            metadata=dict(self.metadata),
        )

    def get_knowledge_store(self, vehicle_id: str) -> VehicleKnowledgeStore:
        """Retrieve private knowledge store for a specific registered vehicle."""
        return self.coordination_manager.get_store(vehicle_id)
