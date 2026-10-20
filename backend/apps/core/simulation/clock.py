"""Authoritative discrete simulation clock.

Maintains simulated time independently of wall-clock time using an integer tick counter
and a fixed time-step duration. Eliminates floating-point accumulation drift by deriving
elapsed time directly from tick counts.
"""

import math

from apps.core.simulation.exceptions import ClockStateError, InvalidTimeStepError


class SimulationClock:
    """Authoritative fixed-step simulation clock.

    Tracks simulated time as a function of integer tick count and fixed discrete step duration dt.
    Completely decoupled from wall-clock time, ensuring 100% deterministic reproducibility.
    """

    MIN_DT_S: float = 0.0001
    MAX_DT_S: float = 10.0
    DECIMAL_PRECISION: int = 9

    def __init__(self, time_step_s: float = 0.1, initial_tick: int = 0) -> None:
        """Initialize the simulation clock.

        Args:
            time_step_s: Discrete time step duration in seconds
                (must be finite and in [0.0001, 10.0]).
            initial_tick: Starting tick counter value (default 0, must be non-negative).

        Raises:
            InvalidTimeStepError: If time_step_s is non-finite, negative, or out of bounds.
            ValueError: If initial_tick is negative.
        """
        self._time_step_s = self._validate_time_step(time_step_s)
        if not isinstance(initial_tick, int) or initial_tick < 0:
            raise ValueError(f"initial_tick must be a non-negative integer, got {initial_tick}.")

        self._tick: int = initial_tick
        self._is_paused: bool = False

    @classmethod
    def _validate_time_step(cls, dt: float) -> float:
        """Validate that the discrete time step is a positive finite float within allowed limits."""
        if not isinstance(dt, (int, float)) or isinstance(dt, bool):
            raise InvalidTimeStepError(
                f"time_step_s must be a numeric float, got {type(dt).__name__}."
            )
        if not math.isfinite(dt):
            raise InvalidTimeStepError(f"time_step_s must be finite, got {dt}.", dt_s=dt)
        if dt <= 0.0:
            raise InvalidTimeStepError(
                f"time_step_s must be strictly positive, got {dt}.", dt_s=dt
            )
        if not (cls.MIN_DT_S <= dt <= cls.MAX_DT_S):
            raise InvalidTimeStepError(
                f"time_step_s {dt}s is outside allowable bounds [{cls.MIN_DT_S}, {cls.MAX_DT_S}].",
                dt_s=dt,
            )
        return float(dt)

    @property
    def time_step_s(self) -> float:
        """Fixed discrete step duration in seconds."""
        return self._time_step_s

    @property
    def tick_count(self) -> int:
        """Authoritative integer tick counter."""
        return self._tick

    @property
    def current_tick(self) -> int:
        """Alias for tick_count."""
        return self._tick

    @property
    def elapsed_time_s(self) -> float:
        """Total simulated elapsed time in seconds.

        Derived directly as round(tick * dt, 9) to eliminate IEEE 754 floating-point drift.
        """
        return round(self._tick * self._time_step_s, self.DECIMAL_PRECISION)

    @property
    def is_paused(self) -> bool:
        """True if the clock is currently paused."""
        return self._is_paused

    @property
    def is_running(self) -> bool:
        """True if the clock is running and eligible to tick."""
        return not self._is_paused

    def tick(self, force: bool = False) -> int:
        """Advance the simulation clock by one discrete tick.

        Args:
            force: If True, allows advancing a paused clock for explicit single-step operations.

        Returns:
            The new tick index after advancing.

        Raises:
            ClockStateError: If the clock is paused and force is False.
        """
        if self._is_paused and not force:
            raise ClockStateError(
                "Cannot advance a paused simulation clock without explicit force/single-step.",
                current_state="paused",
            )
        self._tick += 1
        return self._tick

    def pause(self) -> None:
        """Pause the clock. Idempotent if already paused."""
        self._is_paused = True

    def resume(self) -> None:
        """Resume the clock. Idempotent if already running."""
        self._is_paused = False

    def reset(self, initial_tick: int = 0) -> None:
        """Reset the clock to the initial tick and unpaused state.

        Args:
            initial_tick: Non-negative starting tick (default 0).

        Raises:
            ValueError: If initial_tick is negative.
        """
        if not isinstance(initial_tick, int) or initial_tick < 0:
            raise ValueError(f"initial_tick must be a non-negative integer, got {initial_tick}.")
        self._tick = initial_tick
        self._is_paused = False

    def __repr__(self) -> str:
        state = "paused" if self._is_paused else "running"
        return (
            f"SimulationClock(tick={self._tick}, "
            f"elapsed={self.elapsed_time_s:.4f}s, "
            f"dt={self._time_step_s}s, state='{state}')"
        )
