"""Multi-agent extension boundary and environment for AMAPP.

Coordinates simultaneous decentralized routing actions across multiple vehicle agents
operating over a shared deterministic simulation world.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
from gymnasium import spaces

from apps.core.benchmarking.scenarios import BenchmarkScenarioRegistry
from apps.core.domain.enums import VehicleState
from apps.core.domain.models import Route
from apps.core.domain.values import Position2D
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.rl.config import MultiAgentRLConfig
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


class AMAPPMultiAgentEnv:
    """Multi-Agent decentralized routing environment for AMAPP.

    Provides a clean, modular multi-agent interface where multiple autonomous vehicles
    independently and simultaneously choose routing branches at intersections while
    sharing decentralized V2V communication and road space.
    """

    metadata = {"render_modes": ["ansi"], "render_fps": 10}

    def __init__(
        self,
        config: Optional[MultiAgentRLConfig] = None,
        render_mode: Optional[str] = None,
    ) -> None:
        self.config: MultiAgentRLConfig = config or MultiAgentRLConfig()
        self.render_mode: Optional[str] = render_mode

        self.world: Optional[WorldState] = None
        self.engine: Optional[SimulationEngine] = None
        self.controlled_agents: dict[str, VehicleAgent] = {}

        self.possible_agents: list[str] = []
        self.agents: list[str] = []

        self.observation_spaces: dict[str, spaces.Box] = {}
        self.action_spaces: dict[str, spaces.Discrete] = {}

        # Pre-populate agent spaces from scenario definition
        try:
            scenario_registry = BenchmarkScenarioRegistry.get_default_registry()
            scenario_def = scenario_registry.get(self.config.scenario_id)
            sc = scenario_def.create_scenario(seed=42)
            if self.config.agent_ids:
                self.possible_agents = list(self.config.agent_ids)
            else:
                self.possible_agents = [v.vehicle_id for v in sc.vehicles]
            self.agents = list(self.possible_agents)
            for aid in self.possible_agents:
                self.observation_spaces[aid] = spaces.Box(
                    low=-1.0, high=1.0, shape=(self.config.observation_dim,), dtype=np.float32
                )
                self.action_spaces[aid] = spaces.Discrete(self.config.max_outgoing_actions + 1)
        except Exception:
            self.possible_agents = []
            self.agents = []

        self.reward_calculator = RewardCalculator(self.config.reward_config)

        self._current_seed: Optional[int] = None
        self._step_count: int = 0
        self._accumulated_rewards: dict[str, float] = {}
        self._arrival_rewarded: dict[str, bool] = {}
        self._consecutive_invalid: dict[str, int] = {}
        self._prev_distances_m: dict[str, float] = {}
        self._diag_span: float = 200.0

    def _get_agent_dest_pos(self, agent: VehicleAgent) -> Position2D:
        """Resolve destination coordinate for a specific vehicle agent."""
        if agent.vehicle.target_node_id and self.world:
            if self.world.road_graph.has_node(agent.vehicle.target_node_id):
                return self.world.road_graph.get_node(agent.vehicle.target_node_id).position
        return agent.vehicle.position

    def action_masks(self, agent_id: str) -> np.ndarray:
        """Derive legal action mask for a specific vehicle agent."""
        mask = np.zeros(self.config.max_outgoing_actions + 1, dtype=bool)
        mask[0] = True

        if agent_id in self.controlled_agents and self.world is not None:
            agent = self.controlled_agents[agent_id]
            if not agent.is_arrived:
                curr_edge = agent.current_edge
                anchor = curr_edge.end_node_id if curr_edge else agent.vehicle.current_node_id
                if anchor and self.world.road_graph.has_node(anchor):
                    outgoing = sorted(
                        self.world.road_graph.get_outgoing_edges(anchor),
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
    ) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]]]:
        """Reset the multi-agent environment to a clean scenario state.

        Returns:
            tuple of (obs_dict, info_dict) keyed by agent_id.
        """
        effective_seed = seed if seed is not None else 42
        self._current_seed = effective_seed

        # 1. Build isolated scenario and world
        try:
            scenario_registry = BenchmarkScenarioRegistry.get_default_registry()
            scenario_def = scenario_registry.get(self.config.scenario_id)
            scenario = scenario_def.create_scenario(seed=effective_seed)
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to instantiate multi-agent scenario '{self.config.scenario_id}': {exc}",
                scenario_id=self.config.scenario_id,
                seed=effective_seed,
                cause=exc,
            ) from exc

        try:
            context = ScenarioBuilder(scenario).build()
            self.world = context.world
            self.engine = context.engine
        except Exception as exc:
            raise ScenarioResetError(
                f"Failed to build simulation world for multi-agent scenario: {exc}",
                scenario_id=self.config.scenario_id,
                seed=effective_seed,
                cause=exc,
            ) from exc

        # 2. Configure controlled agents
        all_agent_ids = [a.vehicle.id for a in self.world.get_agents()]
        if self.config.agent_ids:
            for aid in self.config.agent_ids:
                if aid not in all_agent_ids:
                    raise AgentNotFoundError(
                        f"Specified controlled agent '{aid}' not found in scenario.",
                        agent_id=aid,
                        available_agents=all_agent_ids,
                    )
            target_ids = list(self.config.agent_ids)
        else:
            target_ids = all_agent_ids

        self.possible_agents = list(target_ids)
        self.agents = list(target_ids)
        self.controlled_agents = {aid: self.world.get_agent(aid) for aid in target_ids}

        # 3. Setup per-agent spaces and tracking
        self.observation_spaces = {
            aid: spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(self.config.observation_dim,),
                dtype=np.float32,
            )
            for aid in target_ids
        }
        self.action_spaces = {
            aid: spaces.Discrete(self.config.max_outgoing_actions + 1) for aid in target_ids
        }

        self._step_count = 0
        self._accumulated_rewards = {aid: 0.0 for aid in target_ids}
        self._arrival_rewarded = {aid: False for aid in target_ids}
        self._consecutive_invalid = {aid: 0 for aid in target_ids}

        _, _, _, _, self._diag_span = _get_graph_bounds(self.world)
        self._prev_distances_m = {}
        for aid, agent in self.controlled_agents.items():
            dest = self._get_agent_dest_pos(agent)
            self._prev_distances_m[aid] = math.hypot(
                dest.x - agent.vehicle.position.x,
                dest.y - agent.vehicle.position.y,
            )

        obs_dict = {}
        info_dict = {}
        for aid, agent in self.controlled_agents.items():
            obs_dict[aid] = extract_agent_observation(
                agent=agent,
                world=self.world,
                max_outgoing_actions=self.config.max_outgoing_actions,
                consecutive_invalid_actions=0,
                step_count=0,
                max_steps=self.config.max_steps,
            )
            info_dict[aid] = {
                "step_count": 0,
                "agent_id": aid,
                "seed": effective_seed,
                "initial_distance_m": float(self._prev_distances_m[aid]),
                "action_mask": self.action_masks(aid),
            }

        return obs_dict, info_dict

    def step(
        self,
        actions: dict[str, int],
    ) -> tuple[
        dict[str, np.ndarray],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, dict[str, Any]],
    ]:
        """Execute simultaneous actions for all active agents.

        Args:
            actions: Dict mapping agent_id -> action index.

        Returns:
            (observations, rewards, terminations, truncations, infos) dicts.
        """
        self._step_count += 1
        is_invalid_dict = {}
        is_rerouted_dict = {}

        # 1. Apply actions for each active agent
        for aid in list(self.agents):
            agent = self.controlled_agents[aid]
            act = int(actions.get(aid, 0))

            if not self.action_spaces[aid].contains(act):
                raise InvalidActionError(
                    f"Action {act} out of range for agent '{aid}'.",
                    action=act,
                    agent_id=aid,
                )

            is_invalid = False
            is_rerouted = False

            if agent.is_arrived:
                is_invalid = False
            elif act == 0:
                is_invalid = False
                self._consecutive_invalid[aid] = 0
            else:
                branch_idx = act - 1
                curr_edge = agent.current_edge
                anchor = curr_edge.end_node_id if curr_edge else agent.vehicle.current_node_id

                if anchor and self.world.road_graph.has_node(anchor):
                    outgoing = sorted(
                        self.world.road_graph.get_outgoing_edges(anchor),
                        key=lambda e: e.id,
                    )
                    if branch_idx < len(outgoing):
                        target_edge = outgoing[branch_idx]
                        is_closed = False
                        if hasattr(self.world, "incident_manager") and self.world.incident_manager:
                            is_closed = self.world.incident_manager.is_edge_closed(target_edge.id)
                        if not is_closed:
                            try:
                                planner = RoutePlanner(self.world.road_graph)
                                res = planner.find_route(
                                    start_node_id=target_edge.end_node_id,
                                    destination_node_id=agent.vehicle.target_node_id,
                                    cost_mode=CostMode.TRAVEL_TIME,
                                )
                                if res.success and len(res.node_ids) >= 1:
                                    cand_route = Route(
                                        id=f"ma_reroute_{aid}_{self._step_count}",
                                        node_ids=[anchor] + list(res.node_ids),
                                        edge_ids=None,
                                    )
                                    agent.replace_remaining_route(cand_route, resume_node_id=anchor)
                                    is_rerouted = True
                                    self._consecutive_invalid[aid] = 0
                                else:
                                    is_invalid = True
                                    self._consecutive_invalid[aid] += 1
                            except Exception:
                                is_invalid = True
                                self._consecutive_invalid[aid] += 1
                        else:
                            is_invalid = True
                            self._consecutive_invalid[aid] += 1
                    else:
                        is_invalid = True
                        self._consecutive_invalid[aid] += 1
                else:
                    is_invalid = True
                    self._consecutive_invalid[aid] += 1

            is_invalid_dict[aid] = is_invalid
            is_rerouted_dict[aid] = is_rerouted

        # 2. Advance shared simulation engine
        step_collisions = {aid: 0 for aid in self.agents}
        step_near_misses = {aid: 0 for aid in self.agents}

        safety_mgr = getattr(self.world, "safety_manager", None)
        events_start_idx = len(safety_mgr.events) if safety_mgr else 0

        for _ in range(self.config.decision_interval_ticks):
            if self.engine.status in (EngineStatus.STOPPED, EngineStatus.FAILED):
                break
            self.engine.step()

        if safety_mgr:
            for event in safety_mgr.events[events_start_idx:]:
                is_col = getattr(event, "is_overlap", False) or "COLLISION" in getattr(
                    event.event_type, "name", ""
                )
                is_nm = "NEAR_MISS" in getattr(event.event_type, "name", "")
                for aid in self.agents:
                    v_id = self.controlled_agents[aid].vehicle.id
                    if v_id in event.vehicle_ids:
                        if is_col:
                            step_collisions[aid] += 1
                        elif is_nm:
                            step_near_misses[aid] += 1

        # 3. Compute per-agent outputs
        obs_dict = {}
        rew_dict = {}
        term_dict = {}
        trunc_dict = {}
        info_dict = {}

        global_truncated = bool(
            self._step_count >= self.config.max_steps
            or self.engine.status in (EngineStatus.STOPPED, EngineStatus.FAILED)
        )

        for aid in list(self.agents):
            agent = self.controlled_agents[aid]
            dest = self._get_agent_dest_pos(agent)
            curr_dist = math.hypot(
                dest.x - agent.vehicle.position.x,
                dest.y - agent.vehicle.position.y,
            )

            is_arrived = agent.state == VehicleState.ARRIVED
            terminated = bool(is_arrived)
            truncated = global_truncated

            breakdown = self.reward_calculator.calculate_reward(
                prev_distance_m=self._prev_distances_m[aid],
                curr_distance_m=curr_dist,
                is_arrived=is_arrived,
                arrival_already_rewarded=self._arrival_rewarded[aid],
                new_collisions=step_collisions[aid],
                new_near_misses=step_near_misses[aid],
                is_invalid_action=is_invalid_dict[aid],
                is_truncated=truncated and not is_arrived,
                is_rerouted=is_rerouted_dict[aid],
                diag_span_m=self._diag_span,
            )

            if is_arrived:
                self._arrival_rewarded[aid] = True
            self._prev_distances_m[aid] = curr_dist

            step_reward = float(breakdown.total_reward)
            self._accumulated_rewards[aid] += step_reward

            obs = extract_agent_observation(
                agent=agent,
                world=self.world,
                max_outgoing_actions=self.config.max_outgoing_actions,
                consecutive_invalid_actions=self._consecutive_invalid[aid],
                step_count=self._step_count,
                max_steps=self.config.max_steps,
            )

            obs_dict[aid] = obs
            rew_dict[aid] = step_reward
            term_dict[aid] = terminated
            trunc_dict[aid] = truncated
            info_dict[aid] = {
                "step_count": self._step_count,
                "agent_id": aid,
                "is_arrived": is_arrived,
                "action_valid": not is_invalid_dict[aid],
                "reward_components": breakdown.to_dict(),
                "accumulated_reward": float(self._accumulated_rewards[aid]),
                "action_mask": self.action_masks(aid),
            }

            # Remove arrived agents from active stepping list
            if terminated:
                self.agents.remove(aid)

        return obs_dict, rew_dict, term_dict, trunc_dict, info_dict

    def close(self) -> None:
        """Release multi-agent environment resources."""
        self.world = None
        self.engine = None
        self.controlled_agents.clear()
        self.agents.clear()
