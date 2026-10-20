"""Simulation core subsystem for the AMAPP platform.

Provides authoritative discrete simulation clock, world-state management,
deterministic multi-vehicle stepping, and atomic tick rollback guarantees.
"""

from apps.core.simulation.clock import SimulationClock
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import (
    AgentNotFoundError,
    ClockStateError,
    DuplicateAgentIdError,
    EngineStateError,
    IncompatibleAgentGraphError,
    InvalidTimeStepError,
    SimulationError,
    TickExecutionError,
)
from apps.core.simulation.models import (
    EngineStatus,
    TickResult,
    VehicleSnapshot,
    WorldSnapshot,
)
from apps.core.simulation.world import WorldState

__all__ = [
    "AgentNotFoundError",
    "ClockStateError",
    "DuplicateAgentIdError",
    "EngineStateError",
    "EngineStatus",
    "IncompatibleAgentGraphError",
    "InvalidTimeStepError",
    "SimulationClock",
    "SimulationEngine",
    "SimulationError",
    "TickExecutionError",
    "TickResult",
    "VehicleSnapshot",
    "WorldSnapshot",
    "WorldState",
]
