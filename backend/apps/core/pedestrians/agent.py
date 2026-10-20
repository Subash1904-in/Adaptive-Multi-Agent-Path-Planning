import math
from typing import Any, Optional, Union

from apps.core.domain.models import Pedestrian
from apps.core.domain.values import Position2D
from apps.core.pedestrians.crosswalk import Crosswalk
from apps.core.pedestrians.exceptions import (
    InvalidPedestrianStateError,
    PedestrianKinematicsError,
)
from apps.core.pedestrians.models import (
    PedestrianConfig,
    PedestrianLifecycleState,
    PedestrianSignalState,
    PedestrianStepResult,
    validate_pedestrian_transition,
)


class PedestrianAgent:
    """Autonomous pedestrian agent navigating sidewalks, waiting areas, and crosswalks.

    Preserves simulation invariants:
        - Deterministic, bounded motion step-by-step.
        - Obeying pedestrian signal indications.
        - Safe clearance policy when signal changes during crossing.
        - Zero unmodeled teleportation or random movement.
    """

    def __init__(
        self,
        pedestrian: Optional[Pedestrian] = None,
        pedestrian_id: Optional[str] = None,
        initial_position: Optional[Union[Position2D, tuple[float, float]]] = None,
        position: Optional[Union[Position2D, tuple[float, float]]] = None,
        destination_point: Optional[Union[Position2D, tuple[float, float]]] = None,
        destination: Optional[Union[Position2D, tuple[float, float]]] = None,
        config: Optional[PedestrianConfig] = None,
        crosswalk_id: Optional[str] = None,
        current_crosswalk_id: Optional[str] = None,
        target_position: Optional[Union[Position2D, tuple[float, float]]] = None,
        initial_state: PedestrianLifecycleState = PedestrianLifecycleState.IDLE,
        state: Optional[PedestrianLifecycleState] = None,
        initial_heading_rad: float = 0.0,
        initial_speed_mps: float = 0.0,
        heading_rad: float = 0.0,
        desired_speed_mps: Optional[float] = None,
    ) -> None:
        """Initialize pedestrian agent with either a domain Pedestrian entity or direct parameters.

        Args:
            pedestrian: Optional domain entity representing identity and initial position.
            pedestrian_id: Identifier when constructing directly.
            initial_position: Initial coordinates (x, y) or Position2D.
            destination_point: Target destination coordinates (x, y) or Position2D.
            config: Optional PedestrianConfig for physical walking bounds.
            crosswalk_id: Optional ID of the crosswalk this pedestrian intends to use.
            target_position: Alias for destination_point.
            initial_state: Initial lifecycle state (defaults to IDLE).
            initial_heading_rad: Initial orientation in radians.
            initial_speed_mps: Initial walking speed in m/s.
            heading_rad: Alternative parameter name for initial_heading_rad.
        """
        effective_position = position if position is not None else initial_position
        effective_destination = (
            destination if destination is not None
            else (destination_point if destination_point is not None else target_position)
        )
        effective_crosswalk_id = (
            current_crosswalk_id if current_crosswalk_id is not None else crosswalk_id
        )
        effective_state = state if state is not None else initial_state
        effective_heading = heading_rad if heading_rad != 0.0 else initial_heading_rad
        if config is None and desired_speed_mps is not None:
            spd = float(desired_speed_mps)
            config = PedestrianConfig(
                walking_speed_mps=spd,
                max_speed_mps=max(2.0, spd * 1.5),
            )
        if pedestrian is not None:
            if not isinstance(pedestrian, Pedestrian):
                raise TypeError(f"Expected Pedestrian instance, got {type(pedestrian).__name__}.")
            self.pedestrian: Pedestrian = pedestrian
        else:
            if not pedestrian_id or not str(pedestrian_id).strip():
                raise InvalidPedestrianStateError("Pedestrian ID must not be empty.")

            init_pos = effective_position or (0.0, 0.0)
            if isinstance(init_pos, (tuple, list)):
                if not (math.isfinite(init_pos[0]) and math.isfinite(init_pos[1])):
                    raise PedestrianKinematicsError("Initial position coordinates must be finite.")
                pos_entity = Position2D(x=float(init_pos[0]), y=float(init_pos[1]))
            elif isinstance(init_pos, Position2D):
                pos_entity = init_pos
            else:
                raise PedestrianKinematicsError(
                    f"Invalid initial position type: {type(init_pos).__name__}"
                )

            dest = effective_destination
            if dest is not None:
                if isinstance(dest, (tuple, list)):
                    if not (math.isfinite(dest[0]) and math.isfinite(dest[1])):
                        raise PedestrianKinematicsError("Target coordinates must be finite.")
                    target_entity = Position2D(x=float(dest[0]), y=float(dest[1]))
                elif isinstance(dest, Position2D):
                    target_entity = dest
                else:
                    raise PedestrianKinematicsError(
                        f"Invalid destination type: {type(dest).__name__}"
                    )
            else:
                target_entity = None

            self.pedestrian = Pedestrian(
                id=str(pedestrian_id),
                position=pos_entity,
                speed_mps=initial_speed_mps,
                target_position=target_entity,
                crossing_node_id=effective_crosswalk_id,
            )

        self.config: PedestrianConfig = config or PedestrianConfig()
        self.crosswalk_id: Optional[str] = (
            effective_crosswalk_id or self.pedestrian.crossing_node_id
        )
        self.target_position: Optional[Position2D] = (
            self.pedestrian.target_position
        )
        self.state: PedestrianLifecycleState = effective_state
        self.heading_rad: float = effective_heading
        self.waiting_time_s: float = 0.0
        self.crossing_time_s: float = 0.0
        self.total_distance_m: float = 0.0

        # Sync domain entity
        self.pedestrian.speed_mps = 0.0

    @property
    def id(self) -> str:
        """Unique pedestrian identifier."""
        return self.pedestrian.id

    @property
    def pedestrian_id(self) -> str:
        """Unique pedestrian identifier alias."""
        return self.pedestrian.id

    @property
    def current_crosswalk_id(self) -> Optional[str]:
        """Crosswalk ID currently associated with this pedestrian."""
        return self.crosswalk_id

    @property
    def destination_point(self) -> Optional[tuple[float, float]]:
        """Destination point as an (x, y) tuple, if set."""
        if self.target_position:
            return (self.target_position.x, self.target_position.y)
        return None

    @property
    def position(self) -> Position2D:
        """Current 2D Cartesian position in meters."""
        return self.pedestrian.position

    @property
    def speed_mps(self) -> float:
        """Current walking speed in meters per second."""
        return self.pedestrian.speed_mps

    @property
    def is_active(self) -> bool:
        """True if pedestrian is active in the world (not IDLE or ARRIVED)."""
        return self.state not in (PedestrianLifecycleState.IDLE, PedestrianLifecycleState.ARRIVED)

    def start(self) -> None:
        """Activate pedestrian from IDLE to walking or approaching crosswalk."""
        if self.state == PedestrianLifecycleState.IDLE:
            if self.crosswalk_id:
                self.set_state(PedestrianLifecycleState.APPROACHING_CROSSWALK)
            else:
                self.set_state(PedestrianLifecycleState.WALKING)

    def set_state(self, new_state: PedestrianLifecycleState) -> None:
        """Transition agent to a new lifecycle state with invariant validation."""
        validate_pedestrian_transition(self.state, new_state, self.id)
        self.state = new_state

    def step(
        self,
        dt: float,
        signal_state: Optional[PedestrianSignalState] = None,
        crosswalk: Optional[Crosswalk] = None,
        safety_stop: bool = False,
    ) -> PedestrianStepResult:
        """Advance pedestrian kinematics and state deterministically over duration dt.

        Args:
            dt: Fixed simulation step duration in seconds (must be strictly positive).
            signal_state: Current pedestrian signal indication (WALK, CLEARANCE, DONT_WALK).
            crosswalk: Associated Crosswalk instance, if crosswalk_id is set.
            safety_stop: If True, halts movement for immediate physical danger.

        Returns:
            PedestrianStepResult containing updated position, speed, and state.
        """
        if not isinstance(dt, (int, float)) or isinstance(dt, bool):
            raise PedestrianKinematicsError(f"Step dt must be numeric, got {type(dt).__name__}.")
        if not math.isfinite(dt) or dt <= 0.0:
            raise PedestrianKinematicsError(f"Step dt must be strictly positive, got {dt}.")

        old_pos = Position2D(x=self.position.x, y=self.position.y)
        old_state = self.state

        # 1. State Machine Progression
        if self.state == PedestrianLifecycleState.IDLE:
            if crosswalk is not None:
                self.set_state(PedestrianLifecycleState.APPROACHING_CROSSWALK)
            elif self.target_position is not None:
                self.set_state(PedestrianLifecycleState.WALKING)

        if self.state == PedestrianLifecycleState.APPROACHING_CROSSWALK:
            dest = crosswalk.entry_point if crosswalk is not None else self.target_position
            if dest is None:
                self.set_state(PedestrianLifecycleState.BLOCKED)
            else:
                dist_to_curb = math.hypot(dest.x - self.position.x, dest.y - self.position.y)
                if dist_to_curb <= self.config.arrival_tolerance_m:
                    self.set_state(PedestrianLifecycleState.WAITING_TO_CROSS)
                    self.pedestrian.speed_mps = 0.0

        if self.state == PedestrianLifecycleState.WAITING_TO_CROSS:
            self.pedestrian.speed_mps = 0.0
            self.waiting_time_s += dt
            effective_signal = signal_state or PedestrianSignalState.WALK
            if effective_signal == PedestrianSignalState.WALK and not safety_stop:
                self.set_state(PedestrianLifecycleState.CROSSING)
                self.pedestrian.speed_mps = self.config.walking_speed_mps

        if self.state == PedestrianLifecycleState.CROSSING:
            self.crossing_time_s += dt
            exit_pt = crosswalk.exit_point if crosswalk is not None else self.target_position
            if exit_pt is None:
                self.set_state(PedestrianLifecycleState.BLOCKED)
            else:
                dist_to_exit = math.hypot(exit_pt.x - self.position.x, exit_pt.y - self.position.y)
                if dist_to_exit <= self.config.arrival_tolerance_m:
                    # Completed crossing! Snap to exit point and transition to ARRIVED or WALKING
                    self.pedestrian.position = Position2D(x=exit_pt.x, y=exit_pt.y)
                    self.pedestrian.speed_mps = 0.0
                    self.set_state(PedestrianLifecycleState.ARRIVED)

        # 2. Kinematic Movement Integration for Active States
        is_moving = self.state in (
            PedestrianLifecycleState.APPROACHING_CROSSWALK,
            PedestrianLifecycleState.CROSSING,
            PedestrianLifecycleState.WALKING,
        ) and not safety_stop

        if is_moving:
            # Determine active navigation target
            if self.state == PedestrianLifecycleState.CROSSING:
                target = crosswalk.exit_point if crosswalk else self.target_position
            elif self.state == PedestrianLifecycleState.APPROACHING_CROSSWALK:
                target = crosswalk.entry_point if crosswalk else self.target_position
            else:
                target = self.target_position

            if target is not None:
                dx = target.x - self.position.x
                dy = target.y - self.position.y
                distance_to_target = math.hypot(dx, dy)

                if distance_to_target > 1e-6:
                    self.heading_rad = math.atan2(dy, dx)
                    step_dist = min(self.config.walking_speed_mps * dt, distance_to_target)
                    ux = dx / distance_to_target
                    uy = dy / distance_to_target

                    new_x = self.position.x + ux * step_dist
                    new_y = self.position.y + uy * step_dist

                    if not (math.isfinite(new_x) and math.isfinite(new_y)):
                        raise PedestrianKinematicsError(
                            f"Non-finite position calculated: ({new_x}, {new_y})."
                        )

                    self.pedestrian.position = Position2D(x=new_x, y=new_y)
                    self.pedestrian.speed_mps = self.config.walking_speed_mps
                    self.total_distance_m += step_dist

                    rem_dist = math.hypot(target.x - new_x, target.y - new_y)
                    if rem_dist <= self.config.arrival_tolerance_m:
                        self.pedestrian.speed_mps = 0.0
                        if self.state in (
                            PedestrianLifecycleState.WALKING,
                            PedestrianLifecycleState.CROSSING,
                        ):
                            self.set_state(PedestrianLifecycleState.ARRIVED)
                else:
                    self.pedestrian.speed_mps = 0.0
                    if self.state in (
                        PedestrianLifecycleState.WALKING,
                        PedestrianLifecycleState.CROSSING,
                    ):
                        self.set_state(PedestrianLifecycleState.ARRIVED)
        else:
            self.pedestrian.speed_mps = 0.0

        return PedestrianStepResult(
            pedestrian_id=self.id,
            old_position=old_pos,
            new_position=Position2D(x=self.position.x, y=self.position.y),
            old_state=old_state,
            new_state=self.state,
            speed_mps=self.speed_mps,
            heading_rad=self.heading_rad,
            waiting_time_s=self.waiting_time_s,
            crosswalk_id=self.crosswalk_id,
            arrived=self.state == PedestrianLifecycleState.ARRIVED,
        )

    def capture_state(self) -> dict[str, Any]:
        """Capture atomic rollback snapshot of pedestrian state."""
        return {
            "position": Position2D(x=self.position.x, y=self.position.y),
            "speed_mps": self.speed_mps,
            "heading_rad": self.heading_rad,
            "state": self.state,
            "waiting_time_s": self.waiting_time_s,
            "crossing_time_s": self.crossing_time_s,
            "total_distance_m": self.total_distance_m,
            "crosswalk_id": self.crosswalk_id,
            "target_position": (
                Position2D(x=self.target_position.x, y=self.target_position.y)
                if self.target_position
                else None
            ),
        }

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        """Atomically restore pedestrian state from snapshot."""
        pos = snapshot["position"]
        if isinstance(pos, dict):
            self.pedestrian.position = Position2D(x=pos["x"], y=pos["y"])
        else:
            self.pedestrian.position = Position2D(x=pos.x, y=pos.y)
        self.pedestrian.speed_mps = snapshot["speed_mps"]
        self.heading_rad = snapshot["heading_rad"]
        st = snapshot["state"]
        self.state = (
            st if isinstance(st, PedestrianLifecycleState) else PedestrianLifecycleState(st)
        )
        self.waiting_time_s = snapshot["waiting_time_s"]
        self.crossing_time_s = snapshot.get("crossing_time_s", 0.0)
        self.total_distance_m = snapshot.get("total_distance_m", 0.0)
        self.crosswalk_id = snapshot.get("crosswalk_id")
        t_pos = snapshot.get("target_position")
        if t_pos is not None:
            if isinstance(t_pos, dict):
                self.target_position = Position2D(x=t_pos["x"], y=t_pos["y"])
            else:
                self.target_position = Position2D(x=t_pos.x, y=t_pos.y)
        else:
            self.target_position = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize pedestrian agent state to a plain dictionary."""
        return {
            "pedestrian_id": self.pedestrian_id,
            "position": self.position.to_dict(),
            "speed_mps": round(self.speed_mps, 4),
            "heading_rad": round(self.heading_rad, 4),
            "state": self.state.value,
            "waiting_time_s": round(self.waiting_time_s, 3),
            "crossing_time_s": round(self.crossing_time_s, 3),
            "total_distance_m": round(self.total_distance_m, 3),
            "crosswalk_id": self.crosswalk_id,
        }
