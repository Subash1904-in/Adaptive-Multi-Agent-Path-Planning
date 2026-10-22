"""Algorithm adapters and registry for the AMAPP benchmarking framework."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from apps.core.benchmarking.exceptions import UnsupportedAlgorithmError
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


class LearnedRoutingBenchmarkAdapter(BaseRoutingBenchmarkAdapter):
    """Extension point for future learned/reinforcement-learning routing policies (Phases 32-34)."""

    @property
    def algorithm_id(self) -> str:
        return "learned"

    @property
    def name(self) -> str:
        return "Learned RL Policy (Future Extension)"

    @property
    def version(self) -> str:
        return "0.0.0-placeholder"

    @property
    def description(self) -> str:
        return "Reinforcement learning policy extension point scheduled for Phases 32-34."

    @property
    def is_adaptive(self) -> bool:
        return True

    @property
    def is_implemented(self) -> bool:
        return False

    def plan_initial_route(
        self,
        road_graph: RoadGraph,
        start_node_id: str,
        destination_node_id: str,
        cost_mode: CostMode = CostMode.TRAVEL_TIME,
        closed_edge_ids: Optional[set[str]] = None,
    ) -> tuple[Optional[RoutingResult], float]:
        raise UnsupportedAlgorithmError(
            algorithm_id=self.algorithm_id,
            message=(
                "Learned reinforcement learning routing policy is not implemented in Phase 31 "
                "(scheduled for Phases 32-34)."
            ),
        )

    def configure_scenario(self, base_scenario: ScenarioDefinition) -> ScenarioDefinition:
        raise UnsupportedAlgorithmError(
            algorithm_id=self.algorithm_id,
            message=(
                "Learned reinforcement learning routing policy is not implemented in Phase 31 "
                "(scheduled for Phases 32-34)."
            ),
        )


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
