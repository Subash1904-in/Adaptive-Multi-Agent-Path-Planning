"""Gymnasium-compatible Single-Agent Reinforcement Learning Environment for AMAPP.

Provides an authoritative, deterministic Gymnasium environment (`AMAPPSingleAgentEnv`)
wrapping the simulation engine and road network without bypassing safety constraints,
traffic rules, or incident closures.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from apps.core.benchmarking.scenarios import BenchmarkScenarioRegistry
from apps.core.domain.enums import VehicleState
from apps.core.domain.models import Route
from apps.core.domain.values import Position2D
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.rl.config import SingleAgentRLConfig
from apps.core.rl.exceptions import (
    AgentNotFoundError,
    InvalidActionError,
    ScenarioResetError,
)
from apps.core.rl.features import (
    _get_graph_bounds,
    extract_agent_observation,
)
from apps.core.rl.rewards import RewardCalculator
from apps.core.routing.models import CostMode
from apps.core.routing.planner import RoutePlanner
from apps.core.scenarios.builder import ScenarioBuilder
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.models import EngineStatus
from apps.core.simulation.world import WorldState


class AMAPPSingleAgentEnv(gym.Env):
    """Deterministic, Gymnasium-compatible single-agent autonomous vehicle routing environment.

    Action Space:
        spaces.Discrete(K + 1) where K = max_outgoing_actions (default 8).
        - Action 0: Keep current planned route (follow active route without rerouting).
        - Action a in [1, K]: Branch along the (a - 1)-th outgoing edge from the upcoming
          anchor junction/node and calculate an optimal A* path to the destination.
          If the branch does not exist or is closed/infeasible, the action is penalized
          and the vehicle safely continues on its previous route or stops.

    Observation Space:
        spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)
        Continuous normalized feature vector capturing position, speed, heading,
        relative destination direction, route progress, edge state, signal phase,
        nearest neighbor vehicle, active incidents, and step counters.
    """

    metadata = {"render_modes": ["ansi"], "render_fps": 10}

    def __init__(
        self,
        config: Optional[SingleAgentRLConfig] = None,
        render_mode: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.config: SingleAgentRLConfig = config or SingleAgentRLConfig()
        self.render_mode: Optional[str] = render_mode

        # Define Gymnasium action and observation spaces
        self.action_space = spaces.Discrete(self.config.max_outgoing_actions + 1)
        self.observation_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(self.config.observation_dim,),
            dtype=np.float32,
        )

        # Simulation and reward components
        self.world: Optional[WorldState] = None
        self.engine: Optional[SimulationEngine] = None
        self.agent: Optional[VehicleAgent] = None
        self.reward_calculator = RewardCalculator(self.config.reward_config)

        # Episode state variables
        self._current_seed: Optional[int] = None
        self._step_count: int = 0
        self._accumulated_reward: float = 0.0
        self._arrival_rewarded: bool = False
        self._consecutive_invalid: int = 0
        self._prev_distance_m: float = 0.0
        self._diag_span: float = 200.0
        self._is_terminated: bool = False
        self._is_truncated: bool = False

    def _get_destination_pos(self) -> Position2D:
        """Resolve physical destination coordinate for the controlled vehicle."""
        if self.agent and self.agent.vehicle.target_node_id and self.world:
            if self.world.road_graph.has_node(self.agent.vehicle.target_node_id):
                return self.world.road_graph.get_node(self.agent.vehicle.target_node_id).position
        if self.agent:
            return self.agent.vehicle.position
        return Position2D(x=0.0, y=0.0)

    def action_masks(self) -> np.ndarray:
        """Derive boolean mask of legally traversable routing actions from current state.

        Returns:
            np.ndarray of shape (max_outgoing_actions + 1,) where True indicates legal.
        """
        mask = np.zeros(self.config.max_outgoing_actions + 1, dtype=bool)
        mask[0] = True  # Action 0 (Keep Route) is always structurally permissible

        if self.agent is not None and not self.agent.is_arrived and self.world is not None:
            curr_edge = self.agent.current_edge
            anchor_node = curr_edge.end_node_id if curr_edge else self.agent.vehicle.current_node_id
            if anchor_node and self.world.road_graph.has_node(anchor_node):
                outgoing = sorted(
                    self.world.road_graph.get_outgoing_edges(anchor_node),
                    key=lambda e: e.id,
                )
                for i, edge in enumerate(outgoing[: self.config.max_outgoing_actions]):
                    is_closed = False
                    if hasattr(self.world, "incident_manager") and self.world.incident_manager:
                        is_closed = self.world.incident_manager.is_edge_closed(edge.id)
                    if not is_closed:
                        mask[i + 1] = True
        return mask

    get_action_mask = action_masks

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Reset the environment to a clean scenario state using deterministic seed.

        Args:
            seed: Deterministic integer seed.
            options: Optional configuration dictionary.

        Returns:
            tuple of (initial_observation, info_dictionary).
        """
        super().reset(seed=seed)
        effective_seed = seed if seed is not None else 42
        self._current_seed = effective_seed

        # 1. Resolve and create isolated ScenarioDefinition
        try:
            scenario_registry = BenchmarkScenarioRegistry.get_default_registry()
            scenario_def = scenario_registry.get(self.config.scenario_id)
            scenario = scenario_def.create_scenario(seed=effective_seed)
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to instantiate scenario '{self.config.scenario_id}': {exc}",
                scenario_id=self.config.scenario_id,
                seed=effective_seed,
                cause=exc,
            ) from exc

        # 2. Build isolated WorldState and SimulationEngine
        try:
            context = ScenarioBuilder(scenario).build()
            self.world = context.world
            self.engine = context.engine
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to build simulation world for scenario '{self.config.scenario_id}': {exc}",
                scenario_id=self.config.scenario_id,
                seed=effective_seed,
                cause=exc,
            ) from exc

        # 3. Locate controlled vehicle agent
        agent_id = self.config.agent_id
        if agent_id is None:
            if scenario.vehicles:
                agent_id = scenario.vehicles[0].vehicle_id
            else:
                raise AgentNotFoundError(
                    f"Scenario '{self.config.scenario_id}' contains no vehicles to control.",
                    agent_id="<none>",
                )

        if not self.world.has_agent(agent_id):
            available = [a.vehicle.id for a in self.world.get_agents()]
            raise AgentNotFoundError(
                f"Controlled agent '{agent_id}' not found in simulation world.",
                agent_id=agent_id,
                available_agents=available,
            )

        self.agent = self.world.get_agent(agent_id)

        # 4. Reset episode tracking counters
        self._step_count = 0
        self._accumulated_reward = 0.0
        self._arrival_rewarded = False
        self._consecutive_invalid = 0
        self._is_terminated = False
        self._is_truncated = False

        _, _, _, _, self._diag_span = _get_graph_bounds(self.world)
        dest_pos = self._get_destination_pos()
        self._prev_distance_m = math.hypot(
            dest_pos.x - self.agent.vehicle.position.x,
            dest_pos.y - self.agent.vehicle.position.y,
        )

        obs = extract_agent_observation(
            agent=self.agent,
            world=self.world,
            max_outgoing_actions=self.config.max_outgoing_actions,
            consecutive_invalid_actions=0,
            step_count=0,
            max_steps=self.config.max_steps,
        )

        info = {
            "step_count": 0,
            "tick": self.engine.current_tick,
            "agent_id": agent_id,
            "scenario_id": self.config.scenario_id,
            "seed": effective_seed,
            "initial_distance_m": float(self._prev_distance_m),
            "action_mask": self.action_masks(),
        }
        return obs, info

    def step(
        self, action: int | np.integer
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """Advance the environment by one routing decision step.

        Execution pipeline:
        1. Validates action against action space.
        2. Applies routing action if vehicle is active.
        3. Advances authoritative simulation by decision_interval_ticks.
        4. Calculates objective reward, termination, and truncation.
        5. Computes and returns next observation.
        """
        action_int = int(action)
        if not self.action_space.contains(action_int):
            raise InvalidActionError(
                f"Action {action_int} is outside valid action space {self.action_space}.",
                action=action_int,
                agent_id=self.agent.vehicle.id if self.agent else None,
            )

        # Handle post-terminal steps per Gymnasium conventions
        if self._is_terminated or self._is_truncated:
            obs = extract_agent_observation(
                agent=self.agent,
                world=self.world,
                max_outgoing_actions=self.config.max_outgoing_actions,
                consecutive_invalid_actions=self._consecutive_invalid,
                step_count=self._step_count,
                max_steps=self.config.max_steps,
            )
            return (
                obs,
                0.0,
                self._is_terminated,
                self._is_truncated,
                {"warning": "step called after episode terminated or truncated."},
            )

        self._step_count += 1
        is_invalid_action = False
        is_rerouted = False

        # Apply routing action
        if self.agent.state == VehicleState.ARRIVED:
            # Vehicle already arrived; action is a no-op
            is_invalid_action = False
        elif action_int == 0:
            # Action 0: Keep current route (follow planned trajectory)
            is_invalid_action = False
            self._consecutive_invalid = 0
        else:
            # Action a in [1, K]: Branch along the (a - 1)-th outgoing edge
            branch_idx = action_int - 1
            curr_edge = self.agent.current_edge
            anchor_node = curr_edge.end_node_id if curr_edge else self.agent.vehicle.current_node_id

            if anchor_node and self.world.road_graph.has_node(anchor_node):
                outgoing = sorted(
                    self.world.road_graph.get_outgoing_edges(anchor_node),
                    key=lambda e: e.id,
                )
                if branch_idx < len(outgoing):
                    target_edge = outgoing[branch_idx]
                    is_closed = False
                    if hasattr(self.world, "incident_manager") and self.world.incident_manager:
                        is_closed = self.world.incident_manager.is_edge_closed(target_edge.id)

                    if not is_closed:
                        dest_node_id = self.agent.vehicle.target_node_id
                        try:
                            planner = RoutePlanner(self.world.road_graph)
                            res = planner.find_route(
                                start_node_id=target_edge.end_node_id,
                                destination_node_id=dest_node_id,
                                cost_mode=CostMode.TRAVEL_TIME,
                            )
                            if res.success and len(res.node_ids) >= 1:
                                candidate_nodes = [anchor_node] + list(res.node_ids)
                                candidate_route = Route(
                                    id=f"rl_reroute_{self._step_count}",
                                    node_ids=candidate_nodes,
                                    edge_ids=None,
                                )
                                self.agent.replace_remaining_route(
                                    candidate_route=candidate_route,
                                    resume_node_id=anchor_node,
                                )
                                is_rerouted = True
                                is_invalid_action = False
                                self._consecutive_invalid = 0
                            else:
                                is_invalid_action = True
                                self._consecutive_invalid += 1
                        except Exception:
                            is_invalid_action = True
                            self._consecutive_invalid += 1
                    else:
                        is_invalid_action = True
                        self._consecutive_invalid += 1
                else:
                    is_invalid_action = True
                    self._consecutive_invalid += 1
            else:
                is_invalid_action = True
                self._consecutive_invalid += 1

        # Advance authoritative simulation engine by decision_interval_ticks
        step_collisions = 0
        step_near_misses = 0

        safety_mgr = getattr(self.world, "safety_manager", None)
        events_start_idx = len(safety_mgr.events) if safety_mgr else 0

        for _ in range(self.config.decision_interval_ticks):
            if self.engine.status in (EngineStatus.STOPPED, EngineStatus.FAILED):
                break
            self.engine.step()

            if self.agent.state == VehicleState.ARRIVED:
                break

        if safety_mgr:
            vid = self.agent.vehicle.id
            for event in safety_mgr.events[events_start_idx:]:
                if vid in event.vehicle_ids:
                    if getattr(event, "is_overlap", False) or "COLLISION" in getattr(
                        event.event_type, "name", ""
                    ):
                        step_collisions += 1
                    elif "NEAR_MISS" in getattr(event.event_type, "name", ""):
                        step_near_misses += 1

        # Compute current distance to destination
        dest_pos = self._get_destination_pos()
        curr_dist = math.hypot(
            dest_pos.x - self.agent.vehicle.position.x,
            dest_pos.y - self.agent.vehicle.position.y,
        )

        # Determine termination and truncation
        is_arrived = self.agent.state == VehicleState.ARRIVED
        terminated = bool(is_arrived)
        truncated = bool(
            self._step_count >= self.config.max_steps
            or self.engine.status in (EngineStatus.STOPPED, EngineStatus.FAILED)
        )

        self._is_terminated = terminated
        self._is_truncated = truncated

        # Compute step reward
        breakdown = self.reward_calculator.calculate_reward(
            prev_distance_m=self._prev_distance_m,
            curr_distance_m=curr_dist,
            is_arrived=is_arrived,
            arrival_already_rewarded=self._arrival_rewarded,
            new_collisions=step_collisions,
            new_near_misses=step_near_misses,
            is_invalid_action=is_invalid_action,
            is_truncated=truncated and not is_arrived,
            is_rerouted=is_rerouted,
            diag_span_m=self._diag_span,
        )

        if is_arrived:
            self._arrival_rewarded = True
        self._prev_distance_m = curr_dist
        step_reward = float(breakdown.total_reward)
        self._accumulated_reward += step_reward

        # Compute observation
        obs = extract_agent_observation(
            agent=self.agent,
            world=self.world,
            max_outgoing_actions=self.config.max_outgoing_actions,
            consecutive_invalid_actions=self._consecutive_invalid,
            step_count=self._step_count,
            max_steps=self.config.max_steps,
        )

        info = {
            "step_count": self._step_count,
            "tick": self.engine.current_tick,
            "elapsed_time_s": float(self.engine.elapsed_time_s),
            "is_arrived": bool(is_arrived),
            "is_en_route": bool(self.agent.state == VehicleState.EN_ROUTE),
            "remaining_distance_m": float(self.agent.remaining_route_distance_m),
            "current_speed_mps": float(self.agent.vehicle.speed_mps),
            "action_valid": bool(not is_invalid_action),
            "action_mask": self.action_masks(),
            "reward_components": breakdown.to_dict(),
            "reward_breakdown": breakdown.to_dict(),
            "consecutive_invalid": int(self._consecutive_invalid),
            "distance_to_dest": float(curr_dist),
            "accumulated_reward": float(self._accumulated_reward),
            "collisions": int(step_collisions),
            "near_misses": int(step_near_misses),
        }

        return obs, step_reward, terminated, truncated, info

    def render(self) -> Optional[str]:
        """Render ANSI text summary of environment state."""
        if self.agent is None or self.world is None:
            return "AMAPPSingleAgentEnv(Uninitialized)"
        v = self.agent.vehicle
        edge_str = v.current_edge_id or "junction"
        s = (
            f"Step {self._step_count:3d} | Tick {self.engine.current_tick:4d} | "
            f"Vehicle '{v.id}' at ({v.position.x:.1f}, {v.position.y:.1f}) on {edge_str} | "
            f"Speed: {v.speed_mps:.1f} m/s | State: {v.state.value} | "
            f"Reward: {self._accumulated_reward:+.2f}"
        )
        if self.render_mode == "ansi":
            return s
        return None

    def close(self) -> None:
        """Release environment and simulation resources."""
        self.world = None
        self.engine = None
        self.agent = None
