import React from "react";
import type { PedestrianState, VehicleState } from "../../types/simulation";

export interface EntityInspectorProps {
  entityId: string | null;
  entityType: "vehicle" | "pedestrian" | null;
  vehicleState?: VehicleState | null;
  pedestrianState?: PedestrianState | null;
  onClose: () => void;
}

export const EntityInspector: React.FC<EntityInspectorProps> = ({
  entityId,
  entityType,
  vehicleState,
  pedestrianState,
  onClose,
}) => {
  if (!entityId || !entityType) return null;

  const isVehicle = entityType === "vehicle";
  const state = isVehicle ? vehicleState : pedestrianState;

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
          <div className="inspector-row">
            <span className="field-label">Status:</span>
            <span className="field-value status-tag">{state.lifecycle_state}</span>
          </div>
          <div className="inspector-row">
            <span className="field-label">Speed:</span>
            <span className="field-value">{state.speed_mps.toFixed(2)} m/s ({(state.speed_mps * 3.6).toFixed(1)} km/h)</span>
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
          {isVehicle && vehicleState?.vehicle_type && (
            <div className="inspector-row">
              <span className="field-label">Type:</span>
              <span className="field-value">{vehicleState.vehicle_type}</span>
            </div>
          )}
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
