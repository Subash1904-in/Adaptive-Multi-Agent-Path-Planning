"""Deterministic traffic signal controller and intersection approach manager.

Governs phase transitions (RED -> GREEN -> YELLOW -> RED) synchronized with the simulation clock,
associates signals with controlled intersection nodes and road approaches, and provides
instantaneous phase and time-to-transition queries.
"""

from typing import Optional

from apps.core.domain.enums import TrafficSignalState
from apps.core.domain.models import TrafficSignal
from apps.core.graph.road_graph import RoadGraph
from apps.core.signals.exceptions import (
    InvalidIntersectionAssociationError,
)
from apps.core.signals.models import (
    SignalCycleConfig,
    SignalQueryResult,
    SignalSnapshot,
)


class TrafficSignalController:
    """Controller executing deterministic phase transitions for an intersection traffic signal.

    Strictly adheres to the sequence:
        RED -> GREEN -> YELLOW -> RED
    Synchronizes state deterministically with the authoritative simulation time.
    """

    TOLERANCE_S: float = 1e-7

    def __init__(
        self,
        signal: TrafficSignal,
        config: Optional[SignalCycleConfig] = None,
        road_graph: Optional[RoadGraph] = None,
        incoming_edge_ids: Optional[list[str]] = None,
    ) -> None:
        """Initialize the traffic signal controller.

        Args:
            signal: Domain TrafficSignal entity.
            config: Optional SignalCycleConfig (defaults to 30s Green, 5s Yellow, 30s Red).
            road_graph: Optional RoadGraph to validate intersection node and approach edges.
            incoming_edge_ids: Optional list of incoming road edge IDs governed by this signal.
                               If omitted and road_graph is provided, auto-discovered.

        Raises:
            TypeError: If signal is not an instance of TrafficSignal.
            InvalidIntersectionAssociationError: If node_id or incoming edges are invalid.
        """
        if not isinstance(signal, TrafficSignal):
            raise TypeError(f"Expected TrafficSignal instance, got {type(signal).__name__}.")

        self.signal: TrafficSignal = signal
        self.config: SignalCycleConfig = config or SignalCycleConfig()
        self.road_graph: Optional[RoadGraph] = road_graph

        # Validate intersection association if road_graph is provided
        resolved_incoming: list[str] = []
        if self.road_graph is not None:
            if not self.road_graph.has_node(signal.node_id):
                raise InvalidIntersectionAssociationError(
                    f"Traffic signal '{signal.id}' references "
                    f"non-existent node '{signal.node_id}'.",
                    node_id=signal.node_id,
                )

            if incoming_edge_ids is not None:
                for eid in incoming_edge_ids:
                    if not self.road_graph.has_edge(eid):
                        raise InvalidIntersectionAssociationError(
                            f"Traffic signal '{signal.id}' references non-existent edge '{eid}'.",
                            node_id=signal.node_id,
                        )
                    edge = self.road_graph.get_edge(eid)
                    if edge.end_node_id != signal.node_id:
                        raise InvalidIntersectionAssociationError(
                            f"Edge '{eid}' terminates at '{edge.end_node_id}', "
                            f"not controlled intersection node '{signal.node_id}'.",
                            node_id=signal.node_id,
                        )
                    resolved_incoming.append(eid)
            else:
                # Auto-discover all incoming edges terminating at signal.node_id
                resolved_incoming = [
                    edge.id for edge in self.road_graph.get_incoming_edges(signal.node_id)
                ]
        elif incoming_edge_ids is not None:
            resolved_incoming = list(incoming_edge_ids)

        self.incoming_edge_ids: list[str] = sorted(resolved_incoming)
        self.signal.cycle_duration_s = self.config.total_cycle_duration_s

        # Precompute internal phase schedule intervals
        self._schedule: list[tuple[TrafficSignalState, float, float]] = self._build_phase_schedule(
            self.config
        )

        # Initialize domain entity state to t=0
        self.update(0.0)

    @staticmethod
    def _build_phase_schedule(
        config: SignalCycleConfig,
    ) -> list[tuple[TrafficSignalState, float, float]]:
        """Construct the ordered intervals [start_time, end_time) for a single cycle period.

        Sequence is strictly:
            RED -> GREEN -> YELLOW -> RED
        """
        d_red = config.red_duration_s
        d_green = config.green_duration_s
        d_yellow = config.yellow_duration_s

        if config.initial_phase == TrafficSignalState.RED:
            # RED -> GREEN -> YELLOW
            phases = [
                (TrafficSignalState.RED, 0.0, d_red),
                (TrafficSignalState.GREEN, d_red, d_red + d_green),
                (TrafficSignalState.YELLOW, d_red + d_green, d_red + d_green + d_yellow),
            ]
        elif config.initial_phase == TrafficSignalState.GREEN:
            # GREEN -> YELLOW -> RED
            phases = [
                (TrafficSignalState.GREEN, 0.0, d_green),
                (TrafficSignalState.YELLOW, d_green, d_green + d_yellow),
                (TrafficSignalState.RED, d_green + d_yellow, d_green + d_yellow + d_red),
            ]
        else:  # YELLOW
            # YELLOW -> RED -> GREEN
            phases = [
                (TrafficSignalState.YELLOW, 0.0, d_yellow),
                (TrafficSignalState.RED, d_yellow, d_yellow + d_red),
                (TrafficSignalState.GREEN, d_yellow + d_red, d_yellow + d_red + d_green),
            ]
        return phases

    @property
    def id(self) -> str:
        """Unique traffic signal identifier."""
        return self.signal.id

    @property
    def node_id(self) -> str:
        """Controlled intersection node identifier."""
        return self.signal.node_id

    @property
    def state(self) -> TrafficSignalState:
        """Current phase state (RED, YELLOW, GREEN)."""
        return self.signal.state

    @property
    def remaining_phase_s(self) -> float:
        """Seconds remaining in current phase."""
        return self.signal.remaining_phase_s

    def controls_edge(self, edge_id: str) -> bool:
        """Check whether this signal governs the specified incoming road edge."""
        return edge_id in self.incoming_edge_ids

    def evaluate(self, sim_time_s: float) -> tuple[TrafficSignalState, float, float]:
        """Compute signal state, elapsed time in phase, and remaining phase time at sim_time_s.

        Args:
            sim_time_s: Current simulated elapsed time in seconds (must be non-negative).

        Returns:
            Tuple of (current_state, elapsed_in_phase_s, remaining_phase_s).

        Raises:
            ValueError: If sim_time_s is negative.
        """
        if sim_time_s < -self.TOLERANCE_S:
            raise ValueError(f"sim_time_s must be non-negative, got {sim_time_s}.")

        sim_time_s = max(0.0, sim_time_s)
        total_cycle = self.config.total_cycle_duration_s

        # Map to position in cycle period accounting for phase offset
        tau = (sim_time_s + self.config.phase_offset_s) % total_cycle

        for phase_state, start_t, end_t in self._schedule:
            # Interval [start_t, end_t)
            if start_t - self.TOLERANCE_S <= tau < end_t - self.TOLERANCE_S:
                elapsed_in_phase = max(0.0, tau - start_t)
                remaining_in_phase = max(0.0, end_t - tau)
                return phase_state, elapsed_in_phase, remaining_in_phase

        # Fallback to last phase if tau reaches boundary exactly
        last_phase, last_start, last_end = self._schedule[-1]
        elapsed = max(0.0, tau - last_start)
        remaining = max(0.0, last_end - tau)
        return last_phase, elapsed, remaining

    def update(self, sim_time_s: float) -> None:
        """Evaluate and synchronize internal TrafficSignal domain entity at sim_time_s."""
        state, _, remaining = self.evaluate(sim_time_s)
        self.signal.state = state
        self.signal.remaining_phase_s = remaining

    def reset(self) -> None:
        """Reset signal state to initial time t=0.0."""
        self.update(0.0)

    def query(self, sim_time_s: Optional[float] = None) -> SignalQueryResult:
        """Query signal phase and transition times.

        Args:
            sim_time_s: Optional timestamp to evaluate. If omitted, uses current signal state.

        Returns:
            SignalQueryResult containing current state, remaining phase, and time to next green/red.
        """
        if sim_time_s is not None:
            cur_state, _, remaining = self.evaluate(sim_time_s)
        else:
            cur_state = self.signal.state
            remaining = self.signal.remaining_phase_s

        d_yellow = self.config.yellow_duration_s
        d_red = self.config.red_duration_s

        # Compute time to green and time to red from current phase
        if cur_state == TrafficSignalState.GREEN:
            time_to_green = 0.0
            time_to_red = remaining + d_yellow
        elif cur_state == TrafficSignalState.YELLOW:
            time_to_red = remaining
            time_to_green = remaining + d_red
        else:  # RED
            time_to_green = remaining
            time_to_red = 0.0

        return SignalQueryResult(
            signal_id=self.signal.id,
            node_id=self.signal.node_id,
            state=cur_state,
            remaining_phase_s=remaining,
            time_to_green_s=time_to_green,
            time_to_red_s=time_to_red,
            incoming_edge_ids=list(self.incoming_edge_ids),
        )

    def get_snapshot(self, sim_time_s: Optional[float] = None) -> SignalSnapshot:
        """Generate an immutable point-in-time snapshot of the traffic signal state."""
        if sim_time_s is not None:
            cur_state, elapsed, remaining = self.evaluate(sim_time_s)
        else:
            cur_state = self.signal.state
            remaining = self.signal.remaining_phase_s
            # Approximate elapsed from remaining
            durations = {
                TrafficSignalState.RED: self.config.red_duration_s,
                TrafficSignalState.GREEN: self.config.green_duration_s,
                TrafficSignalState.YELLOW: self.config.yellow_duration_s,
            }
            elapsed = max(0.0, durations.get(cur_state, 30.0) - remaining)

        return SignalSnapshot(
            signal_id=self.signal.id,
            node_id=self.signal.node_id,
            state=cur_state,
            remaining_phase_s=remaining,
            elapsed_in_phase_s=elapsed,
            cycle_duration_s=self.config.total_cycle_duration_s,
            incoming_edge_ids=list(self.incoming_edge_ids),
        )
