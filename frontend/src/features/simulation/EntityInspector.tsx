import React from "react";
import type { RouteSubsystemSnapshot } from "../../types/routing";
import type { PedestrianState, VehicleState } from "../../types/simulation";
import { determineVehicleModelType } from "../scene3d/models";

export interface EntityInspectorProps {
  entityId: string | null;
  entityType: "vehicle" | "pedestrian" | null;
  vehicleState?: VehicleState | null;
  pedestrianState?: PedestrianState | null;
  onClose: () => void;
  isStale?: boolean;
  routeSnapshot?: RouteSubsystemSnapshot | null;
  selectedCandidateId?: string | null;
  onSelectCandidate?: (candidateId: string | null) => void;
}

export const EntityInspector: React.FC<EntityInspectorProps> = ({
  entityId,
  entityType,
  vehicleState,
  pedestrianState,
  onClose,
  isStale: propIsStale,
  routeSnapshot,
  selectedCandidateId,
  onSelectCandidate,
}) => {
  if (!entityId || !entityType) return null;

  const isVehicle = entityType === "vehicle";
  const state = isVehicle ? vehicleState : pedestrianState;
  const isStale = propIsStale ?? state?.is_stale ?? false;

  const resolvedModelType = isVehicle && vehicleState
    ? determineVehicleModelType(
        vehicleState.vehicle_id,
        vehicleState.vehicle_type,
        vehicleState.emergency_type,
        vehicleState.model_type
      )
    : null;

  const formattedModelName = resolvedModelType
    ? resolvedModelType.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  return (
    <div className="entity-inspector-card" role="region" aria-label="Entity Details Inspector">
      <div className="inspector-header">
        <div>
          <span className="inspector-type">{isVehicle ? "VEHICLE AGENT" : "PEDESTRIAN AGENT"}</span>
          <h3 className="inspector-id">{entityId}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="btn-dismiss"
          aria-label="Close entity inspector"
        >
          &times;
        </button>
      </div>

      {state ? (
        <div className="inspector-body">
          {/* Data Freshness Indicator */}
          <div className="inspector-row">
            <span className="field-label">Data Freshness:</span>
            <span
              className={`field-value status-tag ${isStale ? "stale-tag" : "fresh-tag"}`}
              style={{
                backgroundColor: isStale ? "#fef2f2" : "#ecfdf5",
                color: isStale ? "#dc2626" : "#059669",
                border: isStale ? "1px solid #fecaca" : "1px solid #a7f3d0",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.75rem",
                fontWeight: 600,
              }}
            >
              {isStale ? "STALE (Last Known State)" : "LIVE (Interpolated)"}
            </span>
          </div>

          <div className="inspector-row">
            <span className="field-label">Status:</span>
            <span className="field-value status-tag">{state.lifecycle_state}</span>
          </div>

          <div className="inspector-row">
            <span className="field-label">Speed:</span>
            <span className="field-value">
              {state.speed_mps.toFixed(2)} m/s ({(state.speed_mps * 3.6).toFixed(1)} km/h)
            </span>
          </div>

          <div className="inspector-row">
            <span className="field-label">Heading:</span>
            <span className="field-value">
              {state.heading_rad.toFixed(2)} rad ({((state.heading_rad * 180) / Math.PI).toFixed(0)}°)
            </span>
          </div>

          <div className="inspector-row">
            <span className="field-label">Coordinates:</span>
            <span className="field-value">
              ({state.position.x.toFixed(1)}, {state.position.y.toFixed(1)})
            </span>
          </div>

          {/* Vehicle Category & Emergency Details */}
          {isVehicle && vehicleState && (
            <>
              {formattedModelName && (
                <div className="inspector-row">
                  <span className="field-label">Model Class:</span>
                  <span className="field-value">
                    {formattedModelName}
                  </span>
                </div>
              )}
              {vehicleState.vehicle_type && (
                <div className="inspector-row">
                  <span className="field-label">Type:</span>
                  <span className="field-value">{vehicleState.vehicle_type}</span>
                </div>
              )}
              {vehicleState.is_emergency && (
                <div className="inspector-row">
                  <span className="field-label">Emergency:</span>
                  <span
                    className="field-value"
                    style={{
                      color: "#ef4444",
                      fontWeight: 600,
                    }}
                  >
                    ACTIVE {vehicleState.emergency_type ? `(${vehicleState.emergency_type})` : ""}
                  </span>
                </div>
              )}
              {Number.isFinite(vehicleState.priority_level) && (
                <div className="inspector-row">
                  <span className="field-label">Priority:</span>
                  <span className="field-value">Level {vehicleState.priority_level}</span>
                </div>
              )}
            </>
          )}

          {/* Pedestrian Crosswalk Details */}
          {!isVehicle && pedestrianState?.crosswalk_id && (
            <div className="inspector-row">
              <span className="field-label">Crosswalk:</span>
              <span className="field-value">{pedestrianState.crosswalk_id}</span>
            </div>
          )}

          {/* Telemetry Clock / Tick */}
          {(Number.isFinite(state.tick) || Number.isFinite(state.simulation_time_s)) && (
            <div className="inspector-row">
              <span className="field-label">Telemetry:</span>
              <span className="field-value">
                {Number.isFinite(state.tick) ? `Tick #${state.tick}` : ""}
                {Number.isFinite(state.tick) && Number.isFinite(state.simulation_time_s) ? " • " : ""}
                {Number.isFinite(state.simulation_time_s) ? `${state.simulation_time_s?.toFixed(2)}s` : ""}
              </span>
            </div>
          )}

          {/* Route Progress, Alternatives, and Rerouting Explanations */}
          {isVehicle && (
            (() => {
              const activeRoute = routeSnapshot?.activeRoutes.get(entityId);
              const candidates = routeSnapshot?.candidateRoutes.get(entityId) || [];
              const vehicleReroutes = (routeSnapshot?.rerouteEvents || []).filter(
                (e) => e.vehicleId === entityId
              );
              const latestReroute = vehicleReroutes[vehicleReroutes.length - 1];

              const totalDist = activeRoute?.totalDistanceM ?? null;
              const rawRem =
                activeRoute?.remainingDistanceM ??
                vehicleState?.remaining_route_distance_m ??
                null;
              const remainingDist =
                rawRem != null && Number.isFinite(rawRem) ? Number(rawRem.toFixed(1)) : null;

              const progressRatio =
                totalDist != null && remainingDist != null && totalDist > 0
                  ? Math.max(0, Math.min(100, Math.round((1 - remainingDist / totalDist) * 100)))
                  : null;

              const routeNodes = activeRoute?.nodeIds || vehicleState?.route || [];
              const routeId = activeRoute?.routeId || vehicleState?.route_id || "Unassigned";

              return (
                <div className="inspector-routing-section">
                  <div className="inspector-section-header">
                    <h4>Routing & Path Telemetry</h4>
                    <span className="provenance-tag">Authoritative Telemetry</span>
                  </div>

                  <div className="inspector-row">
                    <span className="field-label">Active Route ID:</span>
                    <span className="field-value font-mono">{routeId}</span>
                  </div>

                  {/* Route Distances */}
                  <div className="inspector-row">
                    <span className="field-label">Total Distance:</span>
                    <span className="field-value">
                      {totalDist != null ? `${totalDist} m` : "Unavailable"}
                    </span>
                  </div>

                  <div className="inspector-row">
                    <span className="field-label">Remaining Distance:</span>
                    <span className="field-value highlight-cyan">
                      {remainingDist != null ? `${remainingDist} m` : "Not provided by backend"}
                    </span>
                  </div>

                  {/* Progress Ratio Bar */}
                  {progressRatio != null && (
                    <div className="inspector-progress-block">
                      <div className="inspector-progress-labels">
                        <span>Route Progress:</span>
                        <span>{progressRatio}%</span>
                      </div>
                      <div className="inspector-progress-track" role="progressbar" aria-valuenow={progressRatio} aria-valuemin={0} aria-valuemax={100}>
                        <div
                          className="inspector-progress-fill"
                          style={{ width: `${progressRatio}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* ETA Notice (Strict data provenance: AMAPP does not synthesize speculative ETAs) */}
                  <div className="inspector-row">
                    <span className="field-label">Estimated Arrival:</span>
                    <span className="field-value text-muted italic">Not provided by backend</span>
                  </div>

                  {/* Route Nodes Sequence */}
                  {routeNodes.length > 0 && (
                    <div className="inspector-route-box">
                      <span className="field-label">Active Path Nodes ({routeNodes.length}):</span>
                      <span className="route-nodes font-mono">{routeNodes.join(" → ")}</span>
                    </div>
                  )}

                  {/* Rerouting Decision & Explanation */}
                  {latestReroute && (
                    <div className="inspector-reroute-card">
                      <div className="reroute-card-header">
                        <span className="reroute-title">Last Reroute Evaluation</span>
                        <span
                          className={`reroute-badge ${
                            latestReroute.isAccepted ? "badge-accepted" : "badge-rejected"
                          }`}
                        >
                          {latestReroute.decisionType}
                        </span>
                      </div>

                      <div className="inspector-row text-xs">
                        <span className="field-label">Decision Tick:</span>
                        <span className="field-value">
                          Tick #{latestReroute.tick} ({latestReroute.simulationTimeS.toFixed(2)}s)
                        </span>
                      </div>

                      {latestReroute.oldRouteId && latestReroute.newRouteId && (
                        <div className="inspector-row text-xs">
                          <span className="field-label">Route Transition:</span>
                          <span className="field-value font-mono">
                            {latestReroute.oldRouteId} → {latestReroute.newRouteId}
                          </span>
                        </div>
                      )}

                      {/* Recorded Reason */}
                      <div className="reroute-reason-box">
                        <span className="reason-label">Recorded Reason:</span>
                        <p className="reason-text">{latestReroute.reason}</p>
                        <span className="provenance-subtext">
                          {latestReroute.hasExplicitReason
                            ? "Authoritative Backend Decision Reason"
                            : "System Neutral Telemetry Record"}
                        </span>
                      </div>

                      {/* Cost Comparison (where supplied by backend) */}
                      {latestReroute.currentCost != null && latestReroute.candidateCost != null && (
                        <div className="cost-comparison-grid">
                          <div className="cost-col">
                            <span className="cost-label">Current Cost:</span>
                            <span className="cost-val">{latestReroute.currentCost}</span>
                          </div>
                          <div className="cost-col">
                            <span className="cost-label">Candidate Cost:</span>
                            <span className="cost-val">{latestReroute.candidateCost}</span>
                          </div>
                          {latestReroute.costImprovement != null && (
                            <div className="cost-col">
                              <span className="cost-label">Improvement:</span>
                              <span className="cost-val highlight-green">
                                {latestReroute.costImprovement}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Evaluated Alternative Candidates (Only when supplied by backend) */}
                  {candidates.length > 0 && (
                    <div className="inspector-candidates-card">
                      <div className="candidates-header">
                        <h5>Evaluated Candidate Paths ({candidates.length})</h5>
                      </div>
                      {candidates.map((cand) => {
                        const isSelected = selectedCandidateId === cand.id;
                        return (
                          <div key={cand.id} className={`candidate-item ${isSelected ? "selected" : ""}`}>
                            <div className="candidate-item-row">
                              <span className="candidate-id font-mono">{cand.id}</span>
                              <button
                                type="button"
                                className={`btn-inspect-cand ${isSelected ? "active" : ""}`}
                                onClick={() => onSelectCandidate?.(isSelected ? null : cand.id)}
                                aria-label={`${isSelected ? "Deselect" : "Inspect"} candidate path ${cand.id}`}
                              >
                                {isSelected ? "Inspecting" : "Inspect 3D"}
                              </button>
                            </div>
                            <div className="candidate-nodes font-mono text-xs">
                              {cand.nodeIds.join(" → ")}
                            </div>
                            {cand.objectiveCost != null && (
                              <div className="candidate-cost-text text-xs">
                                Evaluated Cost: {cand.objectiveCost}
                                {cand.costImprovement != null ? ` (Diff: ${cand.costImprovement})` : ""}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })()
          )}
        </div>
      ) : (
        <div className="inspector-empty">Waiting for telemetry update...</div>
      )}
    </div>
  );
};
