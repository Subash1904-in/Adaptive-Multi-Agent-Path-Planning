"""WorldState container managing RoadGraph, VehicleAgents, and authoritative clock.

Maintains deterministic vehicle collections, agent-graph compatibility checks,
immutable state snapshots, and baseline state capture for reproducible resets.
"""

from typing import Any, Optional

from apps.core.domain.models import SimulationConfig
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.kinematics.vehicle_agent import VehicleAgent
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
        """Reset the simulation clock to tick 0 and restore all agents to baseline states."""
        self.clock.reset(initial_tick=0)
        self.restore_baseline()

    def get_snapshot(self) -> WorldSnapshot:
        """Generate an immutable point-in-time snapshot of the world and all agents.

        Returns:
            WorldSnapshot containing clock status and all vehicle snapshots in sorted order.
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

        return WorldSnapshot(
            tick=self.clock.tick_count,
            elapsed_time_s=self.clock.elapsed_time_s,
            time_step_s=self.clock.time_step_s,
            is_paused=self.clock.is_paused,
            agent_count=len(vehicle_snaps),
            vehicles=vehicle_snaps,
            metadata=dict(self.metadata),
        )
