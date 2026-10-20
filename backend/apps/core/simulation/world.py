"""WorldState container managing RoadGraph, VehicleAgents, and authoritative clock.

Maintains deterministic vehicle collections, agent-graph compatibility checks,
immutable state snapshots, and baseline state capture for reproducible resets.
"""

from typing import Any, Optional, Union

from apps.core.domain.models import SimulationConfig, TrafficSignal
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
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
    ) -> None:
        """Initialize the world state container.

        Args:
            road_graph: Authoritative RoadGraph representing topological connectivity.
            config: Optional SimulationConfig defining time steps and parameters.
            clock: Optional authoritative SimulationClock. If omitted, initialized with config dt.
            metadata: Optional user-defined dictionary for simulation context.

        Raises:
            TypeError: If road_graph is not an instance of RoadGraph.
        """
        if not isinstance(road_graph, RoadGraph):
            raise TypeError(f"Expected RoadGraph instance, got {type(road_graph).__name__}.")

        self.road_graph: RoadGraph = road_graph
        self.config: SimulationConfig = config or SimulationConfig()
        self.clock: SimulationClock = clock or SimulationClock(
            time_step_s=self.config.time_step_s
        )
        self.metadata: dict[str, Any] = dict(metadata or {})

        self._agents: dict[str, VehicleAgent] = {}
        self._agent_baselines: dict[str, dict[str, Any]] = {}

        self._signals: dict[str, TrafficSignalController] = {}
        self._signal_node_map: dict[str, str] = {}
        self._signal_edge_map: dict[str, str] = {}

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
        return agent

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
        """Capture the current state of all registered agents as the baseline for reset."""
        for agent_id, agent in self._agents.items():
            self._agent_baselines[agent_id] = self._capture_agent_state(agent)

    def restore_baseline(self) -> None:
        """Restore all registered agents to their recorded baseline states."""
        for agent_id, baseline in self._agent_baselines.items():
            if agent_id in self._agents:
                self._apply_agent_state(self._agents[agent_id], baseline)

    def reset(self) -> None:
        """Reset the simulation clock to tick 0 and restore all agents and signals to baseline."""
        self.clock.reset(initial_tick=0)
        self.restore_baseline()
        for ctrl in self._signals.values():
            ctrl.reset()

    def get_snapshot(self) -> WorldSnapshot:
        """Generate an immutable point-in-time snapshot of the world, agents, and signals.

        Returns:
            WorldSnapshot containing clock status, vehicle snapshots, and signal snapshots.
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

        signal_snaps = {
            c.id: c.get_snapshot(self.clock.elapsed_time_s) for c in self.get_signals()
        }

        return WorldSnapshot(
            tick=self.clock.tick_count,
            elapsed_time_s=self.clock.elapsed_time_s,
            time_step_s=self.clock.time_step_s,
            is_paused=self.clock.is_paused,
            agent_count=len(vehicle_snaps),
            vehicles=vehicle_snaps,
            signals=signal_snaps,
            metadata=dict(self.metadata),
        )
