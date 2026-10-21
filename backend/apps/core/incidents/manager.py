"""Authoritative incident management subsystem coordinator.

Governs lifecycle validation, active incident registration, graph edge cost / closure
mutations, traffic signal phase overrides, automatic duration expiry, and baseline restoration.
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any, Optional

from apps.core.coordination.manager import CoordinationManager
from apps.core.coordination.models import (
    CongestionLevel,
    CongestionReport,
    HazardReport,
    HazardSeverity,
    HazardType,
    ReportType,
    RoadClosureReport,
    RoadClosureStatus,
)
from apps.core.domain.enums import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    ObstacleType,
    TrafficSignalState,
)
from apps.core.domain.values import Position2D
from apps.core.graph.road_graph import RoadGraph
from apps.core.incidents.exceptions import (
    DuplicateIncidentIdError,
    IncidentNotFoundError,
    IncidentValidationError,
    InvalidIncidentTargetError,
)
from apps.core.incidents.models import IncidentRecord, IncidentSubsystemSnapshot
from apps.core.signals.controller import TrafficSignalController

logger = logging.getLogger("amapp.incidents")

SUPPORTED_INCIDENT_TYPES = frozenset(
    {
        IncidentType.ROAD_CLOSURE,
        IncidentType.CONGESTION,
        IncidentType.OBSTACLE,
        IncidentType.SIGNAL_OVERRIDE,
        IncidentType.HAZARD,
        IncidentType.ACCIDENT,
    }
)

SEVERITY_CONGESTION_FACTORS: dict[IncidentSeverity, float] = {
    IncidentSeverity.LOW: 1.5,
    IncidentSeverity.MEDIUM: 2.0,
    IncidentSeverity.HIGH: 3.0,
    IncidentSeverity.CRITICAL: 5.0,
}

SEVERITY_HAZARD_PENALTIES: dict[IncidentSeverity, float] = {
    IncidentSeverity.LOW: 15.0,
    IncidentSeverity.MEDIUM: 35.0,
    IncidentSeverity.HIGH: 70.0,
    IncidentSeverity.CRITICAL: 150.0,
}


class IncidentManager:
    """Authoritative coordinator managing roadway incidents and simulation disruptions.

    Applies deterministic mutations to graph traversal costs, closure sets, and signal
    overrides, and synchronizes decentralized vehicle knowledge stores when coordination is enabled.
    """

    def __init__(
        self,
        road_graph: RoadGraph,
        signals: Optional[dict[str, TrafficSignalController]] = None,
        coordination_manager: Optional[CoordinationManager] = None,
    ) -> None:
        """Initialize the incident manager.

        Args:
            road_graph: Authoritative RoadGraph representing topological connectivity.
            signals: Optional mapping of signal_id to TrafficSignalController.
            coordination_manager: Optional CoordinationManager for vehicle belief synchronization.
        """
        self._road_graph: RoadGraph = road_graph
        self._signals: dict[str, TrafficSignalController] = signals or {}
        self._coordination_manager: Optional[CoordinationManager] = coordination_manager

        # Map intersection node_id -> signal controller for easy lookup
        self._node_signal_map: dict[str, TrafficSignalController] = {
            ctrl.node_id: ctrl for ctrl in self._signals.values()
        }

        # Subsystem operational registries
        self._active_incidents: dict[str, IncidentRecord] = {}
        self._resolved_incidents: dict[str, IncidentRecord] = {}
        self._edge_closures: set[str] = set()
        self._edge_congestion: dict[str, float] = {}
        self._edge_hazards: dict[str, float] = {}
        self._signal_overrides: dict[str, tuple[str, TrafficSignalState]] = {}
        self._audit_log: list[dict[str, Any]] = []

    @property
    def active_count(self) -> int:
        """Total number of currently active incidents."""
        return len(self._active_incidents)

    @property
    def resolved_count(self) -> int:
        """Total number of resolved incidents."""
        return len(self._resolved_incidents)

    def _resolve_signal_controller(
        self, signal_id: Optional[str], node_id: Optional[str]
    ) -> Optional[TrafficSignalController]:
        """Lookup signal controller by signal_id or controlled intersection node_id."""
        if signal_id and signal_id in self._signals:
            return self._signals[signal_id]
        if node_id and node_id in self._node_signal_map:
            return self._node_signal_map[node_id]
        return None

    def _calculate_incident_position(
        self,
        edge_id: Optional[str],
        node_id: Optional[str],
        custom_position: Optional[Position2D] = None,
    ) -> Position2D:
        """Derive spatial coordinate for an incident from graph topology if not provided."""
        if custom_position is not None:
            return custom_position

        if edge_id and self._road_graph.has_edge(edge_id):
            edge = self._road_graph.get_edge(edge_id)
            start_node = self._road_graph.get_node(edge.start_node_id)
            end_node = self._road_graph.get_node(edge.end_node_id)
            mid_x = (start_node.position.x + end_node.position.x) / 2.0
            mid_y = (start_node.position.y + end_node.position.y) / 2.0
            return Position2D(x=round(mid_x, 4), y=round(mid_y, 4))

        if node_id and self._road_graph.has_node(node_id):
            node = self._road_graph.get_node(node_id)
            return Position2D(x=round(node.position.x, 4), y=round(node.position.y, 4))

        return Position2D(x=0.0, y=0.0)

    def create_incident(
        self,
        incident_type: IncidentType | str,
        affected_edge_id: Optional[str] = None,
        affected_node_id: Optional[str] = None,
        severity: IncidentSeverity | str = IncidentSeverity.MEDIUM,
        duration_s: Optional[float] = None,
        description: Optional[str] = None,
        congestion_factor: Optional[float] = None,
        target_signal_phase: Optional[TrafficSignalState | str] = None,
        obstacle_type: Optional[ObstacleType | str] = None,
        custom_position: Optional[Position2D] = None,
        incident_id: Optional[str] = None,
        current_time_s: float = 0.0,
        current_tick: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> IncidentRecord:
        """Create, validate, and activate a dynamic roadway incident.

        Args:
            incident_type: Supported category (ROAD_CLOSURE, CONGESTION, OBSTACLE,
                SIGNAL_OVERRIDE, etc.).
            affected_edge_id: RoadEdge identifier for edge-bound incidents.
            affected_node_id: RoadNode identifier for intersection or signal-bound incidents.
            severity: Impact severity level (LOW, MEDIUM, HIGH, CRITICAL).
            duration_s: Optional finite active duration in seconds (> 0.0).
            description: Optional textual explanation.
            congestion_factor: Multiplicative travel delay factor for congestion (>= 1.0).
            target_signal_phase: Target held phase (RED, YELLOW, GREEN) for signal overrides.
            obstacle_type: Physical obstacle classification for obstacle incidents.
            custom_position: Optional custom spatial coordinate.
            incident_id: Optional custom identifier. If omitted, a UUID is generated.
            current_time_s: Current simulation clock seconds.
            current_tick: Current simulation clock tick.
            metadata: Optional additional key-value metadata.

        Returns:
            The newly created and activated IncidentRecord.

        Raises:
            IncidentValidationError: If inputs are invalid or unsupported.
            InvalidIncidentTargetError: If target edge or signal node does not exist.
            DuplicateIncidentIdError: If incident_id already exists.
        """
        # 1. Parse and validate incident_type
        if isinstance(incident_type, str):
            try:
                resolved_type = IncidentType(incident_type.lower())
            except ValueError as exc:
                raise IncidentValidationError(
                    f"Unsupported incident type '{incident_type}'. Supported types: "
                    f"{sorted(t.value for t in SUPPORTED_INCIDENT_TYPES)}.",
                    field="incident_type",
                ) from exc
        else:
            resolved_type = incident_type

        if resolved_type not in SUPPORTED_INCIDENT_TYPES:
            raise IncidentValidationError(
                f"Incident type '{resolved_type.value}' is not supported.",
                field="incident_type",
            )

        # 2. Parse and validate severity
        if isinstance(severity, str):
            try:
                resolved_severity = IncidentSeverity(severity.lower())
            except ValueError as exc:
                raise IncidentValidationError(
                    f"Invalid incident severity '{severity}'.",
                    field="severity",
                ) from exc
        else:
            resolved_severity = severity

        # 3. Validate duration
        if duration_s is not None:
            if not isinstance(duration_s, (int, float)) or duration_s <= 0.0:
                raise IncidentValidationError(
                    f"duration_s must be a positive number, got {duration_s}.",
                    field="duration_s",
                )
            duration_s = float(duration_s)

        # 4. Validate identifier uniqueness
        inc_id = incident_id or f"inc_{uuid.uuid4().hex[:8]}"
        if inc_id in self._active_incidents or inc_id in self._resolved_incidents:
            raise DuplicateIncidentIdError(inc_id)

        # 5. Type-specific validation and target resolution
        resolved_signal_ctrl: Optional[TrafficSignalController] = None
        resolved_signal_phase: Optional[TrafficSignalState] = None
        resolved_obs_type: Optional[ObstacleType] = None
        resolved_cong_factor: Optional[float] = None

        if resolved_type in (
            IncidentType.ROAD_CLOSURE,
            IncidentType.CONGESTION,
            IncidentType.OBSTACLE,
            IncidentType.HAZARD,
            IncidentType.ACCIDENT,
        ):
            if not affected_edge_id:
                raise InvalidIncidentTargetError(
                    f"Incident of type '{resolved_type.value}' requires an affected_edge_id.",
                    target_type="edge",
                )
            if not self._road_graph.has_edge(affected_edge_id):
                raise InvalidIncidentTargetError(
                    f"Road edge '{affected_edge_id}' does not exist in the road graph.",
                    target_id=affected_edge_id,
                    target_type="edge",
                )

        if resolved_type == IncidentType.CONGESTION:
            if congestion_factor is not None:
                if not isinstance(congestion_factor, (int, float)) or congestion_factor < 1.0:
                    raise IncidentValidationError(
                        f"congestion_factor must be >= 1.0, got {congestion_factor}.",
                        field="congestion_factor",
                    )
                resolved_cong_factor = float(congestion_factor)
            else:
                resolved_cong_factor = SEVERITY_CONGESTION_FACTORS.get(resolved_severity, 2.0)

        elif resolved_type == IncidentType.OBSTACLE:
            if obstacle_type is not None:
                if isinstance(obstacle_type, str):
                    try:
                        resolved_obs_type = ObstacleType(obstacle_type.lower())
                    except ValueError as exc:
                        raise IncidentValidationError(
                            f"Invalid obstacle_type '{obstacle_type}'.",
                            field="obstacle_type",
                        ) from exc
                else:
                    resolved_obs_type = obstacle_type
            else:
                resolved_obs_type = ObstacleType.STATIC_BARRIER

        elif resolved_type == IncidentType.SIGNAL_OVERRIDE:
            resolved_signal_ctrl = self._resolve_signal_controller(
                signal_id=metadata.get("signal_id") if metadata else None,
                node_id=affected_node_id,
            )
            if resolved_signal_ctrl is None:
                raise InvalidIncidentTargetError(
                    f"No traffic signal found for intersection node '{affected_node_id}'.",
                    target_id=affected_node_id,
                    target_type="node",
                )
            if not target_signal_phase:
                raise IncidentValidationError(
                    "Signal override requires a target_signal_phase (red, yellow, green).",
                    field="target_signal_phase",
                )
            if isinstance(target_signal_phase, str):
                try:
                    resolved_signal_phase = TrafficSignalState(target_signal_phase.lower())
                except ValueError as exc:
                    raise IncidentValidationError(
                        f"Invalid target_signal_phase '{target_signal_phase}'. "
                        "Must be red, yellow, or green.",
                        field="target_signal_phase",
                    ) from exc
            else:
                resolved_signal_phase = target_signal_phase

        # 6. Compute spatial position
        position = self._calculate_incident_position(
            edge_id=affected_edge_id,
            node_id=affected_node_id,
            custom_position=custom_position,
        )

        # 7. Construct IncidentRecord
        record = IncidentRecord(
            id=inc_id,
            incident_type=resolved_type,
            position=position,
            severity=resolved_severity,
            status=IncidentStatus.ACTIVE,
            affected_edge_id=affected_edge_id,
            affected_node_id=affected_node_id,
            reported_timestamp_s=current_time_s,
            duration_s=duration_s,
            description=description,
            congestion_factor=resolved_cong_factor,
            target_signal_phase=resolved_signal_phase,
            obstacle_type=resolved_obs_type,
            created_tick=current_tick,
            metadata=dict(metadata or {}),
        )

        # 8. Apply operational effects to simulation state
        self._apply_incident_effects(record, current_time_s, resolved_signal_ctrl)

        # 9. Register in active map
        self._active_incidents[inc_id] = record
        self._audit_log.append(
            {
                "action": "create",
                "incident_id": inc_id,
                "incident_type": resolved_type.value,
                "timestamp_s": current_time_s,
                "tick": current_tick,
            }
        )

        logger.info(
            "Activated incident '%s' [%s] on edge=%s node=%s (duration=%ss).",
            inc_id,
            resolved_type.value,
            affected_edge_id,
            affected_node_id,
            duration_s,
        )
        return record

    def _apply_incident_effects(
        self,
        record: IncidentRecord,
        current_time_s: float,
        signal_ctrl: Optional[TrafficSignalController] = None,
    ) -> None:
        """Apply operational effects to road graph, signals, and coordination beliefs."""
        # A. Road Closure
        if record.incident_type == IncidentType.ROAD_CLOSURE and record.affected_edge_id:
            self._edge_closures.add(record.affected_edge_id)
            if self._coordination_manager and self._coordination_manager.config.enabled:
                report = RoadClosureReport(
                    report_id=f"rep_{record.id}",
                    report_type=ReportType.ROAD_CLOSURE,
                    reporting_vehicle_id="infrastructure_incident_system",
                    timestamp_s=current_time_s,
                    expiry_timestamp_s=(
                        current_time_s + record.duration_s
                        if record.duration_s is not None
                        else None
                    ),
                    edge_id=record.affected_edge_id,
                    closure_status=RoadClosureStatus.CLOSED,
                    reason=record.description or "Authoritative incident closure",
                )
                self._coordination_manager.ingest_report(report, current_time_s=current_time_s)

        # B. Localized Congestion
        elif record.incident_type == IncidentType.CONGESTION and record.affected_edge_id:
            factor = record.congestion_factor or 2.0
            self._edge_congestion[record.affected_edge_id] = factor
            if self._coordination_manager and self._coordination_manager.config.enabled:
                level_map = {
                    IncidentSeverity.LOW: CongestionLevel.LOW,
                    IncidentSeverity.MEDIUM: CongestionLevel.MODERATE,
                    IncidentSeverity.HIGH: CongestionLevel.HIGH,
                    IncidentSeverity.CRITICAL: CongestionLevel.SEVERE,
                }
                c_level = level_map.get(record.severity, CongestionLevel.MODERATE)
                report = CongestionReport(
                    report_id=f"rep_{record.id}",
                    report_type=ReportType.CONGESTION,
                    reporting_vehicle_id="infrastructure_incident_system",
                    timestamp_s=current_time_s,
                    expiry_timestamp_s=(
                        current_time_s + record.duration_s
                        if record.duration_s is not None
                        else None
                    ),
                    edge_id=record.affected_edge_id,
                    congestion_level=c_level,
                    travel_time_factor=factor,
                )
                self._coordination_manager.ingest_report(report, current_time_s=current_time_s)

        # C. Obstacle / Hazard / Accident
        elif (
            record.incident_type
            in (IncidentType.OBSTACLE, IncidentType.HAZARD, IncidentType.ACCIDENT)
            and record.affected_edge_id
        ):
            penalty = SEVERITY_HAZARD_PENALTIES.get(record.severity, 35.0)
            self._edge_hazards[record.affected_edge_id] = penalty
            if self._coordination_manager and self._coordination_manager.config.enabled:
                h_type = (
                    HazardType.OBSTACLE
                    if record.incident_type == IncidentType.OBSTACLE
                    else HazardType.ACCIDENT
                )
                h_sev_map = {
                    IncidentSeverity.LOW: HazardSeverity.LOW,
                    IncidentSeverity.MEDIUM: HazardSeverity.MEDIUM,
                    IncidentSeverity.HIGH: HazardSeverity.HIGH,
                    IncidentSeverity.CRITICAL: HazardSeverity.CRITICAL,
                }
                report = HazardReport(
                    report_id=f"rep_{record.id}",
                    report_type=ReportType.HAZARD,
                    reporting_vehicle_id="infrastructure_incident_system",
                    timestamp_s=current_time_s,
                    expiry_timestamp_s=(
                        current_time_s + record.duration_s
                        if record.duration_s is not None
                        else None
                    ),
                    hazard_type=h_type,
                    severity=h_sev_map.get(record.severity, HazardSeverity.MEDIUM),
                    edge_id=record.affected_edge_id,
                    position=record.position,
                    description=record.description,
                )
                self._coordination_manager.ingest_report(report, current_time_s=current_time_s)

        # D. Signal Override
        elif (
            record.incident_type == IncidentType.SIGNAL_OVERRIDE
            and record.target_signal_phase is not None
        ):
            ctrl = signal_ctrl or self._resolve_signal_controller(
                signal_id=None, node_id=record.affected_node_id
            )
            if ctrl is not None:
                duration = record.duration_s if record.duration_s is not None else 86400.0
                ctrl.apply_priority_override(
                    state=record.target_signal_phase,
                    duration_s=duration,
                    current_time_s=current_time_s,
                    request_id=f"incident_{record.id}",
                )
                self._signal_overrides[ctrl.id] = (record.id, record.target_signal_phase)

    def remove_incident(
        self,
        incident_id: str,
        current_time_s: float = 0.0,
        current_tick: int = 0,
    ) -> IncidentRecord:
        """Deactivate and remove an active incident, restoring baseline road and signal state.

        Args:
            incident_id: Identifier of the active incident to resolve.
            current_time_s: Current simulation clock seconds.
            current_tick: Current simulation clock tick.

        Returns:
            The resolved IncidentRecord.

        Raises:
            IncidentNotFoundError: If the incident is not registered or already resolved.
        """
        if incident_id not in self._active_incidents:
            raise IncidentNotFoundError(incident_id)

        record = self._active_incidents.pop(incident_id)
        record.status = IncidentStatus.RESOLVED
        record.resolved_timestamp_s = current_time_s
        record.resolved_tick = current_tick

        # Revert operational effects
        self._revert_incident_effects(record, current_time_s)

        # Store in resolved registry
        self._resolved_incidents[incident_id] = record
        self._audit_log.append(
            {
                "action": "remove",
                "incident_id": incident_id,
                "incident_type": record.incident_type.value,
                "timestamp_s": current_time_s,
                "tick": current_tick,
            }
        )

        logger.info(
            "Resolved and reverted incident '%s' [%s].", incident_id, record.incident_type.value
        )
        return record

    def _revert_incident_effects(self, record: IncidentRecord, current_time_s: float) -> None:
        """Restore baseline traversability, edge costs, or signal cycle program."""
        # A. Road Closure Reopening
        if record.incident_type == IncidentType.ROAD_CLOSURE and record.affected_edge_id:
            # Check if any OTHER active incident also closes this edge
            other_active_closure = any(
                inc.affected_edge_id == record.affected_edge_id
                for inc in self._active_incidents.values()
                if inc.incident_type == IncidentType.ROAD_CLOSURE
            )
            if not other_active_closure:
                self._edge_closures.discard(record.affected_edge_id)
                if self._coordination_manager and self._coordination_manager.config.enabled:
                    report = RoadClosureReport(
                        report_id=f"reopen_{record.id}",
                        report_type=ReportType.ROAD_CLOSURE,
                        reporting_vehicle_id="infrastructure_incident_system",
                        timestamp_s=current_time_s,
                        edge_id=record.affected_edge_id,
                        closure_status=RoadClosureStatus.REOPENED,
                        reason="Incident resolved; roadway reopened",
                    )
                    self._coordination_manager.ingest_report(report, current_time_s=current_time_s)

        # B. Localized Congestion Clearance
        elif record.incident_type == IncidentType.CONGESTION and record.affected_edge_id:
            # Recalculate max congestion factor from any other active incidents on this edge
            active_factors = [
                inc.congestion_factor or 2.0
                for inc in self._active_incidents.values()
                if inc.incident_type == IncidentType.CONGESTION
                and inc.affected_edge_id == record.affected_edge_id
            ]
            if active_factors:
                self._edge_congestion[record.affected_edge_id] = max(active_factors)
            else:
                self._edge_congestion.pop(record.affected_edge_id, None)

        # C. Obstacle / Hazard Clearance
        elif (
            record.incident_type
            in (IncidentType.OBSTACLE, IncidentType.HAZARD, IncidentType.ACCIDENT)
            and record.affected_edge_id
        ):
            other_hazards = [
                SEVERITY_HAZARD_PENALTIES.get(inc.severity, 35.0)
                for inc in self._active_incidents.values()
                if inc.incident_type
                in (IncidentType.OBSTACLE, IncidentType.HAZARD, IncidentType.ACCIDENT)
                and inc.affected_edge_id == record.affected_edge_id
            ]
            if other_hazards:
                self._edge_hazards[record.affected_edge_id] = max(other_hazards)
            else:
                self._edge_hazards.pop(record.affected_edge_id, None)

        # D. Signal Override Restoration
        elif record.incident_type == IncidentType.SIGNAL_OVERRIDE:
            ctrl = self._resolve_signal_controller(signal_id=None, node_id=record.affected_node_id)
            if ctrl is not None:
                ctrl.clear_priority_override()
                self._signal_overrides.pop(ctrl.id, None)

    def step(self, current_time_s: float, current_tick: int = 0) -> list[IncidentRecord]:
        """Evaluate duration expirations and automatically resolve expired incidents.

        Args:
            current_time_s: Current simulation clock seconds.
            current_tick: Current simulation clock tick.

        Returns:
            List of IncidentRecords that expired and were automatically resolved on this step.
        """
        expired: list[IncidentRecord] = []
        for inc_id, record in list(self._active_incidents.items()):
            if record.is_expired(current_time_s):
                resolved_record = self.remove_incident(
                    incident_id=inc_id,
                    current_time_s=current_time_s,
                    current_tick=current_tick,
                )
                expired.append(resolved_record)
        return expired

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        """Retrieve an incident by ID (active or resolved)."""
        if incident_id in self._active_incidents:
            return self._active_incidents[incident_id]
        if incident_id in self._resolved_incidents:
            return self._resolved_incidents[incident_id]
        return None

    def list_active(self) -> list[IncidentRecord]:
        """Enumerate all currently active incidents sorted deterministically by ID."""
        return [self._active_incidents[k] for k in sorted(self._active_incidents.keys())]

    def list_resolved(self) -> list[IncidentRecord]:
        """Enumerate all resolved incidents sorted deterministically by ID."""
        return [self._resolved_incidents[k] for k in sorted(self._resolved_incidents.keys())]

    def list_all(self) -> list[IncidentRecord]:
        """Enumerate all active and resolved incidents sorted deterministically by ID."""
        all_incidents = {**self._active_incidents, **self._resolved_incidents}
        return [all_incidents[k] for k in sorted(all_incidents.keys())]

    def is_edge_closed(self, edge_id: str, current_time_s: float = 0.0) -> bool:
        """Check whether a road edge is impassable under authoritative active closures."""
        return edge_id in self._edge_closures

    def get_closed_edges(self, current_time_s: float = 0.0) -> set[str]:
        """Return the authoritative set of closed road edge IDs."""
        return set(self._edge_closures)

    def get_congestion_multiplier(self, edge_id: str, current_time_s: float = 0.0) -> float:
        """Return the authoritative congestion multiplier for an edge (>= 1.0)."""
        return self._edge_congestion.get(edge_id, 1.0)

    def get_hazard_penalty(self, edge_id: str, current_time_s: float = 0.0) -> float:
        """Return the additive hazard penalty for an edge (>= 0.0)."""
        return self._edge_hazards.get(edge_id, 0.0)

    def has_signal_override(self, signal_id: str) -> bool:
        """Check whether a traffic signal has an active incident override."""
        return signal_id in self._signal_overrides

    def capture_state(self) -> dict[str, Any]:
        """Deep-clone internal state for atomic rollback and baseline restoration."""
        return {
            "active_incidents": copy.deepcopy(self._active_incidents),
            "resolved_incidents": copy.deepcopy(self._resolved_incidents),
            "edge_closures": set(self._edge_closures),
            "edge_congestion": dict(self._edge_congestion),
            "edge_hazards": dict(self._edge_hazards),
            "signal_overrides": dict(self._signal_overrides),
            "audit_log": list(self._audit_log),
        }

    def restore_state(self, state_dict: dict[str, Any]) -> None:
        """Restore internal state from a captured dictionary."""
        self._active_incidents = copy.deepcopy(state_dict.get("active_incidents", {}))
        self._resolved_incidents = copy.deepcopy(state_dict.get("resolved_incidents", {}))
        self._edge_closures = set(state_dict.get("edge_closures", set()))
        self._edge_congestion = dict(state_dict.get("edge_congestion", {}))
        self._edge_hazards = dict(state_dict.get("edge_hazards", {}))
        self._signal_overrides = dict(state_dict.get("signal_overrides", {}))
        self._audit_log = list(state_dict.get("audit_log", []))

    def reset(self) -> None:
        """Reset incident manager to pristine initial state without any active incidents."""
        # Clear signal overrides on physical controllers
        for sig_id in list(self._signal_overrides.keys()):
            if sig_id in self._signals:
                self._signals[sig_id].clear_priority_override()

        self._active_incidents.clear()
        self._resolved_incidents.clear()
        self._edge_closures.clear()
        self._edge_congestion.clear()
        self._edge_hazards.clear()
        self._signal_overrides.clear()
        self._audit_log.clear()

    def get_snapshot(self) -> IncidentSubsystemSnapshot:
        """Generate an immutable point-in-time snapshot of the incident subsystem."""
        active_snaps = [inc.to_dict() for inc in self.list_active()]
        resolved_snaps = [inc.to_dict() for inc in self.list_resolved()]

        return IncidentSubsystemSnapshot(
            active_incidents=active_snaps,
            resolved_incidents=resolved_snaps,
            closed_edge_ids=sorted(self._edge_closures),
            congestion_modifiers=dict(self._edge_congestion),
            active_signal_overrides={
                sid: state.value for sid, (_, state) in self._signal_overrides.items()
            },
            total_created=len(active_snaps) + len(resolved_snaps),
            total_resolved=len(resolved_snaps),
            total_active=len(active_snaps),
        )
