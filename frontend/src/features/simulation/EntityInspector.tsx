import React from "react";
import type { PedestrianState, VehicleState } from "../../types/simulation";
import { determineVehicleModelType } from "../scene3d/models";

export interface EntityInspectorProps {
  entityId: string | null;
  entityType: "vehicle" | "pedestrian" | null;
  vehicleState?: VehicleState | null;
  pedestrianState?: PedestrianState | null;
  onClose: () => void;
  isStale?: boolean;
}

export const EntityInspector: React.FC<EntityInspectorProps> = ({
  entityId,
  entityType,
  vehicleState,
  pedestrianState,
  onClose,
  isStale: propIsStale,
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
                backgroundColor: isStale ? "#7f1d1d" : "#064e3b",
                color: isStale ? "#fca5a5" : "#6ee7b7",
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

          {/* Remaining Route for Vehicles */}
          {isVehicle && vehicleState?.route && vehicleState.route.length > 0 && (
            <div className="inspector-route-box">
              <span className="field-label">Remaining Route:</span>
              <span className="route-nodes">{vehicleState.route.join(" → ")}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="inspector-empty">Waiting for telemetry update...</div>
      )}
    </div>
  );
};
