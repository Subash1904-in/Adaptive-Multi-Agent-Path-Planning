"""SimulationEngine orchestrating authoritative clock and vehicle-agent stepping.

Implements deterministic ordered tick sequencing, atomic tick rollback on failure,
pause/resume/single-step semantics, and point-in-time snapshot access.
"""

from typing import Optional

from apps.core.domain.values import Position2D
from apps.core.kinematics.models import MotionStepResult
from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.exceptions import EngineStateError, TickExecutionError
from apps.core.simulation.models import EngineStatus, TickResult, WorldSnapshot
from apps.core.simulation.world import WorldState


class SimulationEngine:
    """Simulation execution coordinator and authoritative tick sequencer.

    Orchestrates the SimulationClock and WorldState, ensuring that all eligible agents
    receive identical discrete time steps, deterministic iteration ordering, and
    atomic rollback guarantees if an unexpected error occurs during stepping.
    """

    def __init__(self, world: WorldState) -> None:
        """Initialize the simulation engine with a world state.

        Args:
            world: Authoritative WorldState container.

        Raises:
            TypeError: If world is not an instance of WorldState.
        """
        if not isinstance(world, WorldState):
            raise TypeError(f"Expected WorldState instance, got {type(world).__name__}.")

        self.world: WorldState = world
        self.status: EngineStatus = EngineStatus.INITIALIZED
        self.last_tick_result: Optional[TickResult] = None

    @property
    def clock(self) -> SimulationClock:
        """Authoritative SimulationClock belonging to the world state."""
        return self.world.clock

    @property
    def time_step_s(self) -> float:
        """Fixed discrete step size in seconds."""
        return self.clock.time_step_s

    @property
    def current_tick(self) -> int:
        """Current integer tick count."""
        return self.clock.tick_count

    @property
    def elapsed_time_s(self) -> float:
        """Current simulated elapsed time in seconds."""
        return self.clock.elapsed_time_s

    @property
    def is_paused(self) -> bool:
        """True if the engine or clock is paused."""
        return self.status == EngineStatus.PAUSED or self.clock.is_paused

    @property
    def is_running(self) -> bool:
        """True if the engine is running and unpaused."""
        return self.status == EngineStatus.RUNNING and self.clock.is_running

    def pause(self) -> None:
        """Pause simulation execution.

        Idempotent if already paused. Preserves agent positions and route progress.
        """
        self.status = EngineStatus.PAUSED
        self.world.clock.pause()

    def resume(self) -> None:
        """Resume simulation execution from a paused state.

        Raises:
            EngineStateError: If the engine is in a FAILED state.
        """
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot resume an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )
        self.status = EngineStatus.RUNNING
        self.world.clock.resume()

    def stop(self) -> None:
        """Stop simulation execution."""
        self.status = EngineStatus.STOPPED

    def reset(self) -> None:
        """Reset the simulation world and clock to initial baseline states.

        Restores all registered vehicles to their initial registration positions,
        speeds, headings, and states, and resets tick counter and elapsed time to 0.
        """
        self.world.reset()
        self.status = EngineStatus.INITIALIZED
        self.last_tick_result = None

    def step(self, target_accels: Optional[dict[str, float]] = None) -> TickResult:
        """Advance the entire simulation world by exactly one discrete time step dt.

        Execution ordering:
        1. Validates engine status.
        2. Determines eligible agents in stable identifier order.
        3. Captures lightweight rollback states of all agents.
        4. Advances each agent with identical dt.
           If any agent fails, rolls back all agents atomically and marks engine FAILED.
        5. Advances the authoritative clock exactly once.
        6. Constructs and returns the immutable TickResult.

        Args:
            target_accels: Optional mapping of vehicle_id to commanded acceleration in m/s^2.

        Returns:
            TickResult containing tick index, elapsed time, and per-agent motion results.

        Raises:
            EngineStateError: If the engine is in FAILED or STOPPED state.
            TickExecutionError: If any agent stepping fails (with atomic rollback applied).
        """
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot step an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )
        if self.status == EngineStatus.STOPPED:
            raise EngineStateError(
                "Cannot step an engine in STOPPED state.",
                current_state=self.status.value,
            )

        # Allow single-stepping while paused; otherwise ensure status is RUNNING
        is_single_step = self.is_paused
        if self.status == EngineStatus.INITIALIZED and not is_single_step:
            self.status = EngineStatus.RUNNING

        agents = self.world.get_agents()
        dt = self.clock.time_step_s

        # 1. Capture atomic rollback snapshots of all agents before stepping
        rollback_states: dict[str, tuple] = {}
        for agent in agents:
            v = agent.vehicle
            rollback_states[v.id] = (
                agent.state,
                Position2D(x=v.position.x, y=v.position.y),
                v.heading_rad,
                v.speed_mps,
                v.current_node_id,
                v.current_edge_id,
                agent.current_edge_index,
                agent.distance_along_segment_m,
            )

        # 2. Advance each agent by identical dt in deterministic order
        step_results: dict[str, MotionStepResult] = {}
        try:
            for agent in agents:
                vid = agent.vehicle.id
                accel = target_accels.get(vid) if target_accels else None
                step_res = agent.step(dt=dt, target_accel=accel)
                step_results[vid] = step_res
        except Exception as exc:
            # Atomic rollback: restore all agents to pre-tick snapshot
            for agent in agents:
                vid = agent.vehicle.id
                if vid in rollback_states:
                    (
                        r_state,
                        r_pos,
                        r_heading,
                        r_speed,
                        r_nid,
                        r_eid,
                        r_eidx,
                        r_dist,
                    ) = rollback_states[vid]
                    agent.vehicle.state = r_state
                    agent.vehicle.position = Position2D(x=r_pos.x, y=r_pos.y)
                    agent.vehicle.heading_rad = r_heading
                    agent.vehicle.speed_mps = r_speed
                    agent.vehicle.current_node_id = r_nid
                    agent.vehicle.current_edge_id = r_eid
                    agent.current_edge_index = r_eidx
                    agent.distance_along_segment_m = r_dist

            self.status = EngineStatus.FAILED
            raise TickExecutionError(
                f"Tick {self.clock.tick_count + 1} failed during agent execution: {exc}",
                tick=self.clock.tick_count + 1,
                cause=exc,
            ) from exc

        # 3. Advance authoritative clock exactly once
        new_tick = self.clock.tick(force=is_single_step)

        # 4. Construct typed tick result
        arrived_ids = [vid for vid, r in step_results.items() if r.arrived]
        active_ids = [vid for vid, r in step_results.items() if not r.arrived]

        tick_result = TickResult(
            tick=new_tick,
            elapsed_time_s=self.clock.elapsed_time_s,
            time_step_s=dt,
            agent_count=len(step_results),
            step_results=step_results,
            arrived_agent_ids=arrived_ids,
            active_agent_ids=active_ids,
        )

        self.last_tick_result = tick_result
        return tick_result

    def run(
        self,
        ticks: int,
        target_accels_by_tick: Optional[list[dict[str, float]]] = None,
    ) -> list[TickResult]:
        """Execute a sequence of discrete simulation ticks.

        Args:
            ticks: Number of ticks to advance (must be integer > 0).
            target_accels_by_tick: Optional list of per-tick acceleration mappings.

        Returns:
            List of TickResult objects for each executed tick.

        Raises:
            ValueError: If ticks is not a positive integer.
            EngineStateError: If the engine is paused, stopped, or failed.
        """
        if not isinstance(ticks, int) or ticks <= 0:
            raise ValueError(f"ticks must be a positive integer, got {ticks}.")
        if self.is_paused:
            raise EngineStateError(
                "Cannot run multiple ticks while engine is paused. Call resume() or step().",
                current_state=self.status.value,
            )
        if self.status == EngineStatus.FAILED:
            raise EngineStateError(
                "Cannot run an engine in FAILED state. Call reset() first.",
                current_state=self.status.value,
            )

        results: list[TickResult] = []
        for i in range(ticks):
            accels = (
                target_accels_by_tick[i]
                if target_accels_by_tick and i < len(target_accels_by_tick)
                else None
            )
            res = self.step(target_accels=accels)
            results.append(res)

        return results

    def get_snapshot(self) -> WorldSnapshot:
        """Expose an immutable snapshot of the current world and agent states."""
        return self.world.get_snapshot()
