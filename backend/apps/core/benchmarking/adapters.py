"""Algorithm adapters and registry for the AMAPP benchmarking framework."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np

from apps.core.benchmarking.exceptions import UnsupportedAlgorithmError
from apps.core.benchmarking.models import BenchmarkStatus, BenchmarkTrialResult
from apps.core.benchmarking.scenarios import BenchmarkScenarioRegistry
from apps.core.graph.road_graph import RoadGraph
from apps.core.routing.astar import astar_search
from apps.core.routing.dijkstra import dijkstra_search
from apps.core.routing.exceptions import NoPathFoundError
from apps.core.routing.models import (
    AdaptiveRoutingConfig,
    CostMode,
    RoutingAlgorithm,
    RoutingResult,
)
from apps.core.scenarios.models import ScenarioDefinition, VehicleScenarioDefinition

if TYPE_CHECKING:
    from apps.core.rl.training.policy import RLModelPolicy


class BaseRoutingBenchmarkAdapter(ABC):
    """Abstract base adapter establishing common execution protocol for benchmarked algorithms."""

    @property
    @abstractmethod
    def algorithm_id(self) -> str:
        """Unique lowercase identifier for the algorithm."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Implementation version string."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief technical description."""
        pass

    @property
    @abstractmethod
    def is_adaptive(self) -> bool:
        """Whether the algorithm supports dynamic in-route adaptation."""
        pass

    @property
    @abstractmethod
    def is_implemented(self) -> bool:
        """Whether a genuine implementation exists in the current codebase."""
        pass

    @abstractmethod
    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        """Compute an initial route and return (RoutingResult or None, planning_duration_ms)."""
        pass

    @abstractmethod
    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Produce an equivalent ScenarioDefinition configured for this algorithm."""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Serialize adapter metadata."""
        return {
            "algorithm_id": self.algorithm_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "is_adaptive": self.is_adaptive,
            "is_implemented": self.is_implemented,
        }


class DijkstraBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Benchmark adapter for Dijkstra shortest-path baseline."""

    @property
    def algorithm_id(self) -> str:
        return "dijkstra"

    @property
    def name(self) -> str:
        return "Dijkstra Baseline"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Uniform-cost priority queue search computing optimal paths without heuristics."

    @property
    def is_adaptive(self) -> bool:
        return False

    @property
    def is_implemented(self) -> bool:
        return True

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        t0 = time.perf_counter()
        try:
            result = dijkstra_search(
                road_graph=road_graph,
                start_node_id=start_node_id,
                destination_node_id=destination_node_id,
                cost_mode=cost_mode,
                closed_edge_ids=closed_edge_ids,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return result, duration_ms
        except NoPathFoundError:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return None, duration_ms

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Configure all vehicles to use Dijkstra with static non-adaptive execution."""
        configured_vehicles = []
        for v in base_scenario.vehicles:
            configured_vehicles.append(
                VehicleScenarioDefinition(
                    vehicle_id=v.vehicle_id,
                    start_node_id=v.start_node_id,
                    destination_node_id=v.destination_node_id,
                    algorithm=RoutingAlgorithm.DIJKSTRA,
                    cost_mode=v.cost_mode,
                    kinematics=v.kinematics,
                    initial_speed_mps=v.initial_speed_mps,
                    closed_edge_ids=v.closed_edge_ids,
                    vehicle_type=v.vehicle_type,
                    metadata=dict(v.metadata),
                )
            )

        return ScenarioDefinition(
            metadata=base_scenario.metadata,
            road_network=base_scenario.road_network,
            vehicles=tuple(configured_vehicles),
            signals=base_scenario.signals,
            crosswalks=base_scenario.crosswalks,
            pedestrians=base_scenario.pedestrians,
            emergency_vehicles=base_scenario.emergency_vehicles,
            time_step_s=base_scenario.time_step_s,
            max_ticks=base_scenario.max_ticks,
            max_duration_s=base_scenario.max_duration_s,
            stop_on_all_arrived=base_scenario.stop_on_all_arrived,
            seed=base_scenario.seed,
            allow_unreachable_vehicles=base_scenario.allow_unreachable_vehicles,
            simulation_metadata=base_scenario.simulation_metadata,
            v2v_config=base_scenario.v2v_config,
            coordination_config=base_scenario.coordination_config,
            adaptive_routing_config=AdaptiveRoutingConfig(enabled=False),
            safety_config=base_scenario.safety_config,
            emergency_config=base_scenario.emergency_config,
            decision_config=base_scenario.decision_config,
        )


class AStarBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Benchmark adapter for A* heuristic search baseline."""

    @property
    def algorithm_id(self) -> str:
        return "astar"

    @property
    def name(self) -> str:
        return "A* Heuristic Baseline"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Heuristic-guided search utilizing Euclidean distance lower bounds."

    @property
    def is_adaptive(self) -> bool:
        return False

    @property
    def is_implemented(self) -> bool:
        return True

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        t0 = time.perf_counter()
        try:
            result = astar_search(
                road_graph=road_graph,
                start_node_id=start_node_id,
                destination_node_id=destination_node_id,
                cost_mode=cost_mode,
                closed_edge_ids=closed_edge_ids,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return result, duration_ms
        except NoPathFoundError:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return None, duration_ms

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Configure all vehicles to use A* with static non-adaptive execution."""
        configured_vehicles = []
        for v in base_scenario.vehicles:
            configured_vehicles.append(
                VehicleScenarioDefinition(
                    vehicle_id=v.vehicle_id,
                    start_node_id=v.start_node_id,
                    destination_node_id=v.destination_node_id,
                    algorithm=RoutingAlgorithm.ASTAR,
                    cost_mode=v.cost_mode,
                    kinematics=v.kinematics,
                    initial_speed_mps=v.initial_speed_mps,
                    closed_edge_ids=v.closed_edge_ids,
                    vehicle_type=v.vehicle_type,
                    metadata=dict(v.metadata),
                )
            )

        return ScenarioDefinition(
            metadata=base_scenario.metadata,
            road_network=base_scenario.road_network,
            vehicles=tuple(configured_vehicles),
            signals=base_scenario.signals,
            crosswalks=base_scenario.crosswalks,
            pedestrians=base_scenario.pedestrians,
            emergency_vehicles=base_scenario.emergency_vehicles,
            time_step_s=base_scenario.time_step_s,
            max_ticks=base_scenario.max_ticks,
            max_duration_s=base_scenario.max_duration_s,
            stop_on_all_arrived=base_scenario.stop_on_all_arrived,
            seed=base_scenario.seed,
            allow_unreachable_vehicles=base_scenario.allow_unreachable_vehicles,
            simulation_metadata=base_scenario.simulation_metadata,
            v2v_config=base_scenario.v2v_config,
            coordination_config=base_scenario.coordination_config,
            adaptive_routing_config=AdaptiveRoutingConfig(enabled=False),
            safety_config=base_scenario.safety_config,
            emergency_config=base_scenario.emergency_config,
            decision_config=base_scenario.decision_config,
        )


class StaticRoutingBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Benchmark adapter for static/fixed route baseline (unresponsive to incidents)."""

    @property
    def algorithm_id(self) -> str:
        return "static"

    @property
    def name(self) -> str:
        return "Static Fixed Route"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Fixed pre-planned routing following original trajectory without dynamic adaptation."

    @property
    def is_adaptive(self) -> bool:
        return False

    @property
    def is_implemented(self) -> bool:
        return True

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        t0 = time.perf_counter()
        try:
            result = astar_search(
                road_graph=road_graph,
                start_node_id=start_node_id,
                destination_node_id=destination_node_id,
                cost_mode=cost_mode,
                closed_edge_ids=closed_edge_ids,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return result, duration_ms
        except NoPathFoundError:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return None, duration_ms

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Configure scenario with static routing (adaptive routing disabled)."""
        configured_vehicles = []
        for v in base_scenario.vehicles:
            configured_vehicles.append(
                VehicleScenarioDefinition(
                    vehicle_id=v.vehicle_id,
                    start_node_id=v.start_node_id,
                    destination_node_id=v.destination_node_id,
                    algorithm=RoutingAlgorithm.ASTAR,
                    cost_mode=v.cost_mode,
                    kinematics=v.kinematics,
                    initial_speed_mps=v.initial_speed_mps,
                    closed_edge_ids=v.closed_edge_ids,
                    vehicle_type=v.vehicle_type,
                    metadata=dict(v.metadata),
                )
            )

        return ScenarioDefinition(
            metadata=base_scenario.metadata,
            road_network=base_scenario.road_network,
            vehicles=tuple(configured_vehicles),
            signals=base_scenario.signals,
            crosswalks=base_scenario.crosswalks,
            pedestrians=base_scenario.pedestrians,
            emergency_vehicles=base_scenario.emergency_vehicles,
            time_step_s=base_scenario.time_step_s,
            max_ticks=base_scenario.max_ticks,
            max_duration_s=base_scenario.max_duration_s,
            stop_on_all_arrived=base_scenario.stop_on_all_arrived,
            seed=base_scenario.seed,
            allow_unreachable_vehicles=base_scenario.allow_unreachable_vehicles,
            simulation_metadata=base_scenario.simulation_metadata,
            v2v_config=base_scenario.v2v_config,
            coordination_config=base_scenario.coordination_config,
            adaptive_routing_config=AdaptiveRoutingConfig(enabled=False),
            safety_config=base_scenario.safety_config,
            emergency_config=base_scenario.emergency_config,
            decision_config=base_scenario.decision_config,
        )


class AdaptiveRoutingBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Benchmark adapter for dynamic adaptive rerouting responding to traffic incidents."""

    @property
    def algorithm_id(self) -> str:
        return "adaptive"

    @property
    def name(self) -> str:
        return "Adaptive Dynamic Rerouting"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Decentralized adaptive route adjustment responding to closures, "
            "congestion, and hazards."
        )

    @property
    def is_adaptive(self) -> bool:
        return True

    @property
    def is_implemented(self) -> bool:
        return True

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        t0 = time.perf_counter()
        try:
            result = astar_search(
                road_graph=road_graph,
                start_node_id=start_node_id,
                destination_node_id=destination_node_id,
                cost_mode=cost_mode,
                closed_edge_ids=closed_edge_ids,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return result, duration_ms
        except NoPathFoundError:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return None, duration_ms

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Configure scenario with dynamic adaptive rerouting enabled."""
        configured_vehicles = []
        for v in base_scenario.vehicles:
            configured_vehicles.append(
                VehicleScenarioDefinition(
                    vehicle_id=v.vehicle_id,
                    start_node_id=v.start_node_id,
                    destination_node_id=v.destination_node_id,
                    algorithm=RoutingAlgorithm.ASTAR,
                    cost_mode=v.cost_mode,
                    kinematics=v.kinematics,
                    initial_speed_mps=v.initial_speed_mps,
                    closed_edge_ids=v.closed_edge_ids,
                    vehicle_type=v.vehicle_type,
                    metadata=dict(v.metadata),
                )
            )

        adaptive_cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=2.0,
            min_relative_benefit=0.05,
            reroute_cooldown_s=2.0,
            algorithm=RoutingAlgorithm.ASTAR,
            cost_mode=CostMode.TRAVEL_TIME,
        )

        return ScenarioDefinition(
            metadata=base_scenario.metadata,
            road_network=base_scenario.road_network,
            vehicles=tuple(configured_vehicles),
            signals=base_scenario.signals,
            crosswalks=base_scenario.crosswalks,
            pedestrians=base_scenario.pedestrians,
            emergency_vehicles=base_scenario.emergency_vehicles,
            time_step_s=base_scenario.time_step_s,
            max_ticks=base_scenario.max_ticks,
            max_duration_s=base_scenario.max_duration_s,
            stop_on_all_arrived=base_scenario.stop_on_all_arrived,
            seed=base_scenario.seed,
            allow_unreachable_vehicles=base_scenario.allow_unreachable_vehicles,
            simulation_metadata=base_scenario.simulation_metadata,
            v2v_config=base_scenario.v2v_config,
            coordination_config=base_scenario.coordination_config,
            adaptive_routing_config=adaptive_cfg,
            safety_config=base_scenario.safety_config,
            emergency_config=base_scenario.emergency_config,
            decision_config=base_scenario.decision_config,
        )


class SafeFallbackPolicyWrapper:
    """Policy wrapper enforcing strict action validation and multi-layer conventional fallback.

    Guarantees:
    1. Model availability check: If model missing/incompatible, invokes fallback planner.
    2. Model inference safety: Traps exceptions, timeouts, non-finite values, or malformed outputs.
    3. Action space safety: Validates 0 <= a <= K. If outside, triggers fallback.
    4. Action mask enforcement: Checks action_mask. If chosen action is masked out, falls back.
    5. Action 0 (Keep Route) fallback: Defaults to action 0; if blocked, reroutes via conventional.
    6. Diagnostics tracking: Records execution mode, fallback reasons, invalid actions, latencies.
    """

    def __init__(
        self,
        model_policy: Optional[RLModelPolicy] = None,
        fallback_policy: Optional[Callable[[np.ndarray, dict], int]] = None,
        timeout_s: Optional[float] = None,
        forced_fallback_reason: Optional[str] = None,
    ) -> None:
        self.model_policy = model_policy
        if fallback_policy is not None:
            self.fallback_policy = fallback_policy
        else:
            from apps.core.rl.adapter import GreedyProgressTestPolicy
            self.fallback_policy = GreedyProgressTestPolicy()
        self.timeout_s = timeout_s
        self.forced_fallback_reason = forced_fallback_reason

        # Diagnostic counters and latencies
        self.total_decisions: int = 0
        self.learned_decisions: int = 0
        self.fallback_decisions: int = 0
        self.fallback_reasons: dict[str, int] = {}
        self.invalid_actions_count: int = 0
        self.masked_actions_rejected: int = 0
        self.inference_latencies_ms: list[float] = []
        self.fallback_latencies_ms: list[float] = []

    def _record_fallback(self, reason: str, duration_ms: float) -> None:
        self.fallback_decisions += 1
        self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1
        self.fallback_latencies_ms.append(duration_ms)

    def __call__(self, obs: np.ndarray, info: dict) -> int:
        self.total_decisions += 1
        action_mask = info.get("action_mask")

        # Layer 1: Model availability check or forced fallback
        if self.forced_fallback_reason:
            t_fb = time.perf_counter()
            fb_action = self._execute_fallback(obs, info, reason=self.forced_fallback_reason)
            dur_ms = (time.perf_counter() - t_fb) * 1000.0
            self._record_fallback(self.forced_fallback_reason, dur_ms)
            return fb_action

        if self.model_policy is None:
            t_fb = time.perf_counter()
            fb_action = self._execute_fallback(obs, info, reason="model_unavailable")
            self._record_fallback("model_unavailable", (time.perf_counter() - t_fb) * 1000.0)
            return fb_action

        # Layer 2: Model inference with timing and error trapping
        t0 = time.perf_counter()
        try:
            raw_action = self.model_policy.predict(obs, info)
            inf_ms = (time.perf_counter() - t0) * 1000.0
            self.inference_latencies_ms.append(inf_ms)
            if self.timeout_s is not None and (inf_ms / 1000.0) > self.timeout_s:
                t_fb = time.perf_counter()
                reason = "inference_timeout"
                fb_action = self._execute_fallback(obs, info, reason=reason)
                self._record_fallback(reason, (time.perf_counter() - t_fb) * 1000.0)
                return fb_action
        except Exception as exc:
            inf_ms = (time.perf_counter() - t0) * 1000.0
            self.inference_latencies_ms.append(inf_ms)
            t_fb = time.perf_counter()
            reason = f"inference_exception:{type(exc).__name__}"
            fb_action = self._execute_fallback(obs, info, reason=reason)
            self._record_fallback(reason, (time.perf_counter() - t_fb) * 1000.0)
            return fb_action

        # Layer 3: Output sanity check (finite, int convertible)
        if raw_action is None or not np.isfinite(raw_action):
            t_fb = time.perf_counter()
            fb_action = self._execute_fallback(obs, info, reason="malformed_output")
            self._record_fallback("malformed_output", (time.perf_counter() - t_fb) * 1000.0)
            return fb_action

        try:
            action_int = int(raw_action)
        except (ValueError, TypeError):
            t_fb = time.perf_counter()
            fb_action = self._execute_fallback(obs, info, reason="non_integer_action")
            self._record_fallback("non_integer_action", (time.perf_counter() - t_fb) * 1000.0)
            return fb_action

        # Layer 4: Action bounds check [0, K] (where K = 8 for Discrete(9))
        max_action = (len(action_mask) - 1) if action_mask is not None else 8
        if action_int < 0 or action_int > max_action:
            self.invalid_actions_count += 1
            t_fb = time.perf_counter()
            fb_action = self._execute_fallback(obs, info, reason="out_of_bounds_action")
            self._record_fallback("out_of_bounds_action", (time.perf_counter() - t_fb) * 1000.0)
            return fb_action

        # Layer 5: Action mask legality check
        if action_mask is not None and len(action_mask) > action_int:
            if not action_mask[action_int]:
                self.invalid_actions_count += 1
                self.masked_actions_rejected += 1
                t_fb = time.perf_counter()
                fb_action = self._execute_fallback(obs, info, reason="masked_action_rejected")
                dur_ms = (time.perf_counter() - t_fb) * 1000.0
                self._record_fallback("masked_action_rejected", dur_ms)
                return fb_action

        # Valid learned decision accepted
        self.learned_decisions += 1
        return action_int

    def _execute_fallback(self, obs: np.ndarray, info: dict, reason: str) -> int:
        """Execute conventional fallback policy safely preserving legal actions."""
        action_mask = info.get("action_mask")
        # If action 0 (keep route) is legal, it is the safest default
        if action_mask is not None and len(action_mask) > 0 and action_mask[0]:
            return 0
        # If keep route is blocked (e.g. incident on current road), query fallback policy
        fb_action = self.fallback_policy(obs, info)
        if action_mask is not None and len(action_mask) > fb_action and action_mask[fb_action]:
            return fb_action
        # If fallback policy also suggested an illegal action, find first legal action
        if action_mask is not None:
            for idx, legal in enumerate(action_mask):
                if legal:
                    return idx
        return 0


class LearnedRoutingBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Adapter for learned RL routing policy (MaskablePPO) with safe conventional fallback."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        algorithm: Optional[Any] = None,
        fallback_algorithm: RoutingAlgorithm = RoutingAlgorithm.ASTAR,
        deterministic: bool = True,
        model_manager: Optional[Any] = None,
        inference_timeout_s: Optional[float] = 1.0,
    ) -> None:
        self.model_path = model_path
        if algorithm is not None:
            self.algorithm = algorithm
        else:
            from apps.core.rl.training.config import RLAlgorithm
            self.algorithm = RLAlgorithm.MASKABLE_PPO
        self.fallback_algorithm = fallback_algorithm
        self.deterministic = deterministic
        self.inference_timeout_s = inference_timeout_s
        if model_manager is not None:
            self.model_manager = model_manager
        else:
            from apps.core.rl.model_manager import RLModelManager
            self.model_manager = RLModelManager.get_instance()

    @property
    def algorithm_id(self) -> str:
        return "learned"

    @property
    def name(self) -> str:
        return "Learned RL Policy (MaskablePPO)"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Reinforcement learning policy (MaskablePPO) with safe conventional fallback."

    @property
    def is_adaptive(self) -> bool:
        return True

    @property
    def is_implemented(self) -> bool:
        return True

    def is_model_available(self) -> bool:
        """Check whether a verified, compatible model artifact is available."""
        return self.model_manager.is_model_available(
            model_path=self.model_path,
            algorithm=self.algorithm,
        )

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        """Compute initial route via conventional planner to seed simulation."""
        t0 = time.perf_counter()
        try:
            if self.fallback_algorithm == RoutingAlgorithm.DIJKSTRA:
                result = dijkstra_search(
                    road_graph=road_graph,
                    start_node_id=start_node_id,
                    destination_node_id=destination_node_id,
                    cost_mode=cost_mode,
                    closed_edge_ids=closed_edge_ids,
                )
            else:
                result = astar_search(
                    road_graph=road_graph,
                    start_node_id=start_node_id,
                    destination_node_id=destination_node_id,
                    cost_mode=cost_mode,
                    closed_edge_ids=closed_edge_ids,
                )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return result, duration_ms
        except NoPathFoundError:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return None, duration_ms

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Configure scenario with dynamic adaptive rerouting enabled."""
        configured_vehicles = []
        for v in base_scenario.vehicles:
            configured_vehicles.append(
                VehicleScenarioDefinition(
                    vehicle_id=v.vehicle_id,
                    start_node_id=v.start_node_id,
                    destination_node_id=v.destination_node_id,
                    algorithm=self.fallback_algorithm,
                    cost_mode=v.cost_mode,
                    kinematics=v.kinematics,
                    initial_speed_mps=v.initial_speed_mps,
                    closed_edge_ids=v.closed_edge_ids,
                    vehicle_type=v.vehicle_type,
                    metadata=dict(v.metadata),
                )
            )

        adaptive_cfg = AdaptiveRoutingConfig(
            enabled=True,
            min_absolute_benefit=2.0,
            min_relative_benefit=0.05,
            reroute_cooldown_s=2.0,
            algorithm=self.fallback_algorithm,
            cost_mode=CostMode.TRAVEL_TIME,
        )

        return ScenarioDefinition(
            metadata=base_scenario.metadata,
            road_network=base_scenario.road_network,
            vehicles=tuple(configured_vehicles),
            signals=base_scenario.signals,
            crosswalks=base_scenario.crosswalks,
            pedestrians=base_scenario.pedestrians,
            emergency_vehicles=base_scenario.emergency_vehicles,
            time_step_s=base_scenario.time_step_s,
            max_ticks=base_scenario.max_ticks,
            max_duration_s=base_scenario.max_duration_s,
            stop_on_all_arrived=base_scenario.stop_on_all_arrived,
            seed=base_scenario.seed,
            allow_unreachable_vehicles=base_scenario.allow_unreachable_vehicles,
            simulation_metadata=base_scenario.simulation_metadata,
            v2v_config=base_scenario.v2v_config,
            coordination_config=base_scenario.coordination_config,
            adaptive_routing_config=adaptive_cfg,
            safety_config=base_scenario.safety_config,
            emergency_config=base_scenario.emergency_config,
            decision_config=base_scenario.decision_config,
        )

    def execute_trial(
        self,
        scenario_id: str,
        trial_index: int = 0,
        seed: int = 42,
        benchmark_run_id: Optional[str] = None,
        max_ticks_override: Optional[int] = None,
        forced_fallback_reason: Optional[str] = None,
    ) -> BenchmarkTrialResult:
        """Execute scenario benchmark trial under learned routing policy with safe fallback."""
        run_id = benchmark_run_id or f"bench_learned_{int(time.time()):d}"
        started_at = datetime.now(timezone.utc).isoformat()

        scenario_registry = BenchmarkScenarioRegistry.get_default_registry()
        scenario_def = scenario_registry.get(scenario_id)

        # 1. Resolve model policy via RLModelManager
        policy_inst, val_result = self.model_manager.get_policy(
            model_path=self.model_path,
            algorithm=self.algorithm,
            deterministic=self.deterministic,
        )

        model_available = val_result.is_valid and policy_inst is not None

        # Determine effective fallback reason if model unavailable
        effective_forced_fallback = forced_fallback_reason
        if not model_available and not effective_forced_fallback:
            effective_forced_fallback = (
                f"model_incompatible:{val_result.error_message}"
                if val_result and val_result.error_message
                else "model_artifact_missing"
            )

        # 2. Build SafeFallbackPolicyWrapper
        wrapper = SafeFallbackPolicyWrapper(
            model_policy=policy_inst if model_available else None,
            timeout_s=self.inference_timeout_s,
            forced_fallback_reason=effective_forced_fallback,
        )

        base_scenario = scenario_def.create_scenario(seed=seed)
        configured_scenario = self.configure_scenario(base_scenario)

        # 3. Pre-evaluate initial routing feasibility for primary vehicle
        from apps.core.scenarios.builder import ScenarioBuilder
        road_graph = ScenarioBuilder(configured_scenario)._resolve_road_graph()
        initial_route_feasible = False
        init_plan_ms = 0.0

        if configured_scenario.vehicles:
            primary_vehicle = configured_scenario.vehicles[0]
            routing_res, init_plan_ms = self.plan_initial_route(
                road_graph=road_graph,
                start_node_id=primary_vehicle.start_node_id,
                destination_node_id=primary_vehicle.destination_node_id,
                cost_mode=primary_vehicle.cost_mode,
                closed_edge_ids=set(primary_vehicle.closed_edge_ids),
            )
            initial_route_feasible = routing_res is not None and routing_res.success
        else:
            initial_route_feasible = True

        if not initial_route_feasible:
            completed_at = datetime.now(timezone.utc).isoformat()
            return BenchmarkTrialResult(
                benchmark_run_id=run_id,
                scenario_id=scenario_id,
                scenario_version=scenario_def.version,
                algorithm_id=self.algorithm_id,
                algorithm_version=self.version,
                seed=seed,
                trial_index=trial_index,
                status=BenchmarkStatus.INFEASIBLE,
                route_feasible=False,
                route_cost=None,
                route_length_m=None,
                planning_duration_ms=float(init_plan_ms),
                simulation_duration_s=0.0,
                simulation_ticks=0,
                travel_time_s=None,
                completed_trips=0,
                total_trips=len(configured_scenario.vehicles),
                completion_rate_pct=0.0,
                collision_count=0,
                near_miss_count=0,
                intersection_crossings=0,
                reroutes_evaluated=0,
                reroutes_accepted=0,
                messages_sent=0,
                messages_delivered=0,
                pdr=None,
                incident_count=0,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason="No traversable path from origin to destination.",
                metadata={
                    "is_adaptive": self.is_adaptive,
                    "execution_mode": "fallback",
                    "model_available": model_available,
                    "model_path": val_result.model_path if val_result else None,
                    "algorithm": self.algorithm.value,
                    "total_decisions": 0,
                    "learned_decisions": 0,
                    "fallback_decisions": 0,
                    "fallback_reasons": {"initial_route_infeasible": 1},
                    "invalid_actions": 0,
                    "masked_actions_rejected": 0,
                    "mean_inference_latency_ms": 0.0,
                    "mean_fallback_latency_ms": 0.0,
                },
            )

        # 4. Configure and instantiate single-agent Gymnasium environment
        from apps.core.rl.config import SingleAgentRLConfig
        from apps.core.rl.env import AMAPPSingleAgentEnv

        effective_max_ticks = max_ticks_override or 250
        max_steps = max(50, effective_max_ticks // 5)

        cfg = SingleAgentRLConfig(
            scenario_id=scenario_id,
            decision_interval_ticks=5,
            max_steps=max_steps,
        )
        env = AMAPPSingleAgentEnv(config=cfg)

        plan_t0 = time.perf_counter()
        try:
            obs, info = env.reset(seed=seed)
            init_plan_ms = (time.perf_counter() - plan_t0) * 1000.0
        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            env.close()
            return BenchmarkTrialResult(
                benchmark_run_id=run_id,
                scenario_id=scenario_id,
                scenario_version=scenario_def.version,
                algorithm_id=self.algorithm_id,
                algorithm_version=self.version,
                seed=seed,
                trial_index=trial_index,
                status=BenchmarkStatus.FAILED,
                route_feasible=False,
                route_cost=None,
                route_length_m=None,
                planning_duration_ms=0.0,
                simulation_duration_s=0.0,
                simulation_ticks=0,
                travel_time_s=None,
                completed_trips=0,
                total_trips=1,
                completion_rate_pct=0.0,
                collision_count=0,
                near_miss_count=0,
                intersection_crossings=0,
                reroutes_evaluated=0,
                reroutes_accepted=0,
                messages_sent=0,
                messages_delivered=0,
                pdr=None,
                incident_count=0,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason=f"Environment reset error: {exc}",
                metadata={
                    "is_adaptive": self.is_adaptive,
                    "model_available": model_available,
                    "execution_mode": "fallback" if not model_available else "learned",
                },
            )

        # Check initial route feasibility
        primary_agent = env.agent
        initial_route_feasible = (
            primary_agent is not None
            and primary_agent.route is not None
            and len(primary_agent.route.node_ids) >= 2
        )

        terminated = False
        truncated = False
        total_collisions = 0
        total_near_misses = 0

        # Step loop
        while not (terminated or truncated):
            action = wrapper(obs, info)
            obs, reward, terminated, truncated, info = env.step(action)
            total_collisions += info.get("collisions", 0)
            total_near_misses += info.get("near_misses", 0)

        completed_at = datetime.now(timezone.utc).isoformat()
        agent = env.agent
        is_arrived = agent.is_arrived if agent else False

        # Status resolution
        if not initial_route_feasible:
            status = BenchmarkStatus.INFEASIBLE
            failure_reason = "No traversable path from origin to destination."
        elif is_arrived:
            status = BenchmarkStatus.SUCCESS
            failure_reason = None
        elif truncated:
            status = BenchmarkStatus.TIMEOUT
            failure_reason = f"Step limit ({max_steps}) reached before destination arrival."
        else:
            status = BenchmarkStatus.FAILED
            failure_reason = "Episode terminated before arrival."

        travel_time_s = float(env.engine.elapsed_time_s) if is_arrived and env.engine else None
        completed_trips = 1 if is_arrived else 0
        route_len = agent.total_route_distance_m if agent else 0.0

        pdr = None
        messages_sent = 0
        messages_delivered = 0
        if env.world and getattr(env.world, "communication_network", None):
            cm = env.world.communication_network.metrics
            messages_sent = cm.broadcasts_attempted + cm.unicasts_attempted
            messages_delivered = cm.successful_deliveries
            if cm.delivery_attempts > 0:
                pdr = float(round((cm.successful_deliveries / cm.delivery_attempts) * 100.0, 2))

        total_planning_ms = (
            init_plan_ms
            + sum(wrapper.inference_latencies_ms)
            + sum(wrapper.fallback_latencies_ms)
        )
        mean_inf_latency = (
            sum(wrapper.inference_latencies_ms) / len(wrapper.inference_latencies_ms)
            if wrapper.inference_latencies_ms
            else 0.0
        )
        mean_fb_latency = (
            sum(wrapper.fallback_latencies_ms) / len(wrapper.fallback_latencies_ms)
            if wrapper.fallback_latencies_ms
            else 0.0
        )

        execution_mode = "learned" if wrapper.learned_decisions > 0 else "fallback"

        result = BenchmarkTrialResult(
            benchmark_run_id=run_id,
            scenario_id=scenario_id,
            scenario_version=scenario_def.version,
            algorithm_id=self.algorithm_id,
            algorithm_version=self.version,
            seed=seed,
            trial_index=trial_index,
            status=status,
            route_feasible=initial_route_feasible,
            route_cost=travel_time_s,
            route_length_m=float(route_len) if is_arrived else None,
            planning_duration_ms=float(total_planning_ms),
            simulation_duration_s=float(env.engine.elapsed_time_s) if env.engine else 0.0,
            simulation_ticks=int(env.engine.current_tick) if env.engine else 0,
            travel_time_s=travel_time_s,
            completed_trips=completed_trips,
            total_trips=1,
            completion_rate_pct=100.0 if is_arrived else 0.0,
            collision_count=total_collisions,
            near_miss_count=total_near_misses,
            intersection_crossings=0,
            reroutes_evaluated=wrapper.total_decisions,
            reroutes_accepted=0,
            messages_sent=messages_sent,
            messages_delivered=messages_delivered,
            pdr=pdr,
            incident_count=0,
            started_at=started_at,
            completed_at=completed_at,
            failure_reason=failure_reason,
            metadata={
                "is_adaptive": self.is_adaptive,
                "execution_mode": execution_mode,
                "model_available": model_available,
                "model_path": val_result.model_path if val_result else None,
                "algorithm": self.algorithm.value,
                "total_decisions": wrapper.total_decisions,
                "learned_decisions": wrapper.learned_decisions,
                "fallback_decisions": wrapper.fallback_decisions,
                "fallback_reasons": dict(wrapper.fallback_reasons),
                "invalid_actions": wrapper.invalid_actions_count,
                "masked_actions_rejected": wrapper.masked_actions_rejected,
                "mean_inference_latency_ms": round(mean_inf_latency, 3),
                "mean_fallback_latency_ms": round(mean_fb_latency, 3),
                "accumulated_reward": info.get("accumulated_reward", 0.0),
            },
        )
        env.close()
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize adapter metadata including model availability."""
        d = super().to_dict()
        d["model_available"] = self.is_model_available()
        d["model_path"] = str(self.model_path) if self.model_path else "auto"
        return d


class AlgorithmRegistry:
    """Registry managing available benchmarking algorithm adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseRoutingBenchmarkAdapter] = {}

    def register(self, adapter: BaseRoutingBenchmarkAdapter) -> None:
        """Register an algorithm adapter."""
        self._adapters[adapter.algorithm_id.lower()] = adapter

    def get(self, algorithm_id: str) -> BaseRoutingBenchmarkAdapter:
        """Retrieve an algorithm adapter by ID or raise UnsupportedAlgorithmError."""
        key = algorithm_id.strip().lower()
        if key not in self._adapters:
            raise UnsupportedAlgorithmError(
                algorithm_id=algorithm_id,
                available_algorithms=sorted(self._adapters.keys()),
            )
        adapter = self._adapters[key]
        if not adapter.is_implemented:
            raise UnsupportedAlgorithmError(
                algorithm_id=algorithm_id,
                message=(
                    f"Algorithm '{algorithm_id}' is recognized as an extension point but has "
                    "not yet been implemented in the active codebase (scheduled for Phases 32-34)."
                ),
                available_algorithms=[aid for aid, a in self._adapters.items() if a.is_implemented],
            )
        return adapter

    def list_algorithms(self) -> list[dict[str, Any]]:
        """Return descriptors for all registered algorithms."""
        return [adapter.to_dict() for adapter in self._adapters.values()]

    @classmethod
    def get_default_registry(cls) -> "AlgorithmRegistry":
        """Instantiate a registry preloaded with all standard AMAPP algorithm adapters."""
        reg = cls()
        reg.register(DijkstraBenchmarkAdapter())
        reg.register(AStarBenchmarkAdapter())
        reg.register(StaticRoutingBenchmarkAdapter())
        reg.register(AdaptiveRoutingBenchmarkAdapter())
        reg.register(LearnedRoutingBenchmarkAdapter())
        return reg
