import React, { useState } from "react";
import type { ScenarioDefinition, RunStatus } from "../../types/simulation";
import type {
  CreateIncidentPayload,
  IncidentSeverity,
  IncidentType,
  ObstacleType,
} from "../../types/incidents";
import { getUnifiedMetropolitanRoadNetwork } from "../scene3d/geometry";

export interface IncidentModalProps {
  isOpen: boolean;
  onClose: () => void;
  scenario: ScenarioDefinition | null;
  currentRun: RunStatus | null;
  onInject: (payload: CreateIncidentPayload) => Promise<void>;
  isLoading?: boolean;
}

export const IncidentModal: React.FC<IncidentModalProps> = ({
  isOpen,
  onClose,
  scenario,
  currentRun,
  onInject,
  isLoading = false,
}) => {
  const [incidentType, setIncidentType] = useState<IncidentType>("road_closure");
  const [selectedEdgeId, setSelectedEdgeId] = useState<string>("");
  const [severity, setSeverity] = useState<IncidentSeverity>("high");
  const [delayMultiplier, setDelayMultiplier] = useState<number>(2.5);
  const [obstacleType, setObstacleType] = useState<ObstacleType>("construction");
  const [description, setDescription] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const metroGeometry = getUnifiedMetropolitanRoadNetwork(scenario);
  const availableEdges = metroGeometry.edges;
  const targetEdge = selectedEdgeId || (availableEdges[0]?.id ?? "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!currentRun) {
      setErrorMsg("Please start a simulation run before injecting incidents.");
      return;
    }

    if (!targetEdge && incidentType !== "signal_override") {
      setErrorMsg("Please select an affected road segment.");
      return;
    }

    const payload: CreateIncidentPayload = {
      incident_type: incidentType,
      severity,
      description: description.trim() || undefined,
      edge_id: targetEdge,
      affected_edge_id: targetEdge,
    };

    if (incidentType === "congestion") {
      payload.delay_multiplier = delayMultiplier;
      payload.congestion_factor = delayMultiplier;
    } else if (incidentType === "obstacle") {
      payload.obstacle_type = obstacleType;
    }

    try {
      await onInject(payload);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to inject incident";
      setErrorMsg(msg);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-incident-title">
      <div className="modal-dialog-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header-row">
          <h3 id="modal-incident-title" className="modal-title">Inject Roadway Incident</h3>
          <button type="button" onClick={onClose} className="btn-close-modal" aria-label="Close dialog">
            ✕
          </button>
        </div>

        {errorMsg && (
          <div style={{ backgroundColor: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca", padding: "8px 12px", borderRadius: "6px", fontSize: "0.8rem" }}>
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Incident Type */}
          <div className="form-field">
            <label className="form-label" htmlFor="inc-type">Incident Type</label>
            <select
              id="inc-type"
              className="form-select"
              value={incidentType}
              onChange={(e) => setIncidentType(e.target.value as IncidentType)}
            >
              <option value="road_closure">Road Closure (Block Path)</option>
              <option value="congestion">Traffic Jam / Congestion</option>
              <option value="obstacle">Physical Obstacle / Debris</option>
            </select>
          </div>

          {/* Road Segment */}
          <div className="form-field">
            <label className="form-label" htmlFor="inc-edge">Affected Road Segment</label>
            <select
              id="inc-edge"
              className="form-select"
              value={targetEdge}
              onChange={(e) => setSelectedEdgeId(e.target.value)}
            >
              {availableEdges.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id} ({e.lanes || 2} lanes, max {e.speed_limit_mps || 15} m/s)
                </option>
              ))}
            </select>
          </div>

          {/* Severity */}
          <div className="form-field">
            <label className="form-label">Severity Level</label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "6px" }}>
              {(["low", "medium", "high", "critical"] as IncidentSeverity[]).map((sev) => (
                <button
                  key={sev}
                  type="button"
                  onClick={() => setSeverity(sev)}
                  style={{
                    padding: "6px 4px",
                    borderRadius: "6px",
                    border: severity === sev ? "1px solid #0f172a" : "1px solid #e2e8f0",
                    backgroundColor: severity === sev ? "#0f172a" : "#ffffff",
                    color: severity === sev ? "#ffffff" : "#475569",
                    fontFamily: "Space Grotesk, sans-serif",
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    textTransform: "capitalize",
                    cursor: "pointer",
                  }}
                >
                  {sev}
                </button>
              ))}
            </div>
          </div>

          {/* Type specific attributes */}
          {incidentType === "congestion" && (
            <div className="form-field">
              <label className="form-label" htmlFor="inc-delay">Delay Multiplier: {delayMultiplier}×</label>
              <input
                id="inc-delay"
                type="range"
                min="1.5"
                max="8.0"
                step="0.5"
                value={delayMultiplier}
                onChange={(e) => setDelayMultiplier(parseFloat(e.target.value))}
                style={{ width: "100%", accentColor: "#0f172a" }}
              />
            </div>
          )}

          {incidentType === "obstacle" && (
            <div className="form-field">
              <label className="form-label" htmlFor="inc-obstacle">Obstacle Type</label>
              <select
                id="inc-obstacle"
                className="form-select"
                value={obstacleType}
                onChange={(e) => setObstacleType(e.target.value as ObstacleType)}
              >
                <option value="construction">Construction Barricade</option>
                <option value="debris">Fallen Debris / Cargo</option>
                <option value="stalled_vehicle">Disabled Vehicle</option>
                <option value="static_barrier">Concrete Jersey Barrier</option>
              </select>
            </div>
          )}

          {/* Description */}
          <div className="form-field">
            <label className="form-label" htmlFor="inc-desc">Notes / Description (Optional)</label>
            <input
              id="inc-desc"
              type="text"
              placeholder="e.g. Utility line maintenance"
              className="form-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
            <button
              type="button"
              onClick={onClose}
              className="form-btn-primary"
              style={{ backgroundColor: "#ffffff", color: "#475569", border: "1px solid #e2e8f0" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !currentRun}
              className="form-btn-primary"
            >
              {isLoading ? "Injecting..." : "Inject Incident"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
