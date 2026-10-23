import React, { useMemo, useState } from "react";
import type { ScenarioDefinition, RunStatus } from "../../types/simulation";
import type {
  CreateIncidentPayload,
  IncidentRecord,
  IncidentSeverity,
  IncidentType,
  ObstacleType,
} from "../../types/incidents";
import { getUnifiedMetropolitanRoadNetwork } from "../scene3d/geometry";

export interface IncidentControlPanelProps {
  currentRun: RunStatus | null;
  scenario: ScenarioDefinition | null;
  activeIncidents: IncidentRecord[];
  onInjectIncident: (payload: CreateIncidentPayload) => Promise<void>;
  onRemoveIncident: (incidentId: string) => Promise<void>;
  isLoading?: boolean;
}

export const IncidentControlPanel: React.FC<IncidentControlPanelProps> = ({
  currentRun,
  scenario,
  activeIncidents,
  onInjectIncident,
  onRemoveIncident,
  isLoading = false,
}) => {
  const [incidentType, setIncidentType] = useState<IncidentType>("road_closure");
  const [targetEdgeId, setTargetEdgeId] = useState<string>("");
  const [severity, setSeverity] = useState<IncidentSeverity>("high");
  const [delayMultiplier, setDelayMultiplier] = useState<number>(2.5);
  const [obstacleType, setObstacleType] = useState<ObstacleType>("construction");
  const [description, setDescription] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

  const metroGeometry = useMemo(() => getUnifiedMetropolitanRoadNetwork(scenario), [scenario]);
  const availableEdges = metroGeometry.edges;

  const isTerminal = currentRun?.is_terminal ?? false;
  const hasActiveRun = Boolean(currentRun && !isTerminal);

  const handleInject = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!currentRun) {
      setErrorMessage("No active simulation run to inject incidents into.");
      return;
    }
    if (isTerminal) {
      setErrorMessage("Cannot mutate a completed, cancelled, or failed run.");
      return;
    }

    const edge = targetEdgeId || (availableEdges[0]?.id ?? "");
    if (!edge) {
      setErrorMessage("Please select a target edge.");
      return;
    }

    const payload: CreateIncidentPayload = {
      incident_type: incidentType,
      severity,
      description: description.trim() || undefined,
      edge_id: edge,
      affected_edge_id: edge,
    };

    if (incidentType === "congestion") {
      payload.delay_multiplier = delayMultiplier;
      payload.congestion_factor = delayMultiplier;
    } else if (incidentType === "obstacle") {
      payload.obstacle_type = obstacleType;
    }

    try {
      setIsSubmitting(true);
      await onInjectIncident(payload);
      setDescription("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to inject incident.";
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemove = async (incidentId: string) => {
    try {
      setRemovingId(incidentId);
      await onRemoveIncident(incidentId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to remove incident.";
      setErrorMessage(msg);
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="swiss-card" role="region" aria-label="Incident Management and Controls">
      <div className="swiss-card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h3 className="swiss-card-title">Incident Controls</h3>
          <span className="swiss-card-kicker">Road closures, jams, and obstacle injection</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className="badge badge-neutral" style={{ fontSize: "0.75rem", fontWeight: 700, padding: "2px 8px", backgroundColor: "#f1f5f9", borderRadius: "10px", color: "#475569" }}>
            {activeIncidents.length}
          </span>
          <button
            type="button"
            className="btn-collapse"
            onClick={() => setIsCollapsed(!isCollapsed)}
            aria-label={isCollapsed ? "Expand incident panel" : "Collapse incident panel"}
            style={{
              background: "none",
              border: "1px solid #e2e8f0",
              borderRadius: "4px",
              padding: "2px 8px",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: 700,
              color: "#64748b",
            }}
          >
            {isCollapsed ? "+" : "−"}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <>
          {errorMessage && (
            <div style={{ backgroundColor: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca", padding: "8px 10px", borderRadius: "6px", fontSize: "0.78rem", marginBottom: "12px" }}>
              {errorMessage}
            </div>
          )}

          {/* Active Incidents List */}
          {activeIncidents.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
                Active Roadway Incidents
              </div>
              {activeIncidents.map((inc) => (
                <div
                  key={inc.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 10px",
                    backgroundColor: "#fff1f2",
                    border: "1px solid #fecdd3",
                    borderRadius: "6px",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, fontSize: "0.75rem", color: "#e11d48" }}>
                        {inc.incident_type.replace("_", " ").toUpperCase()}
                      </span>
                      <span style={{ fontSize: "0.68rem", color: "#9f1239" }}>
                        ({inc.affected_edge_id || "Global"})
                      </span>
                    </div>
                    {inc.description && (
                      <div style={{ fontSize: "0.7rem", color: "#881337", marginTop: "2px" }}>
                        {inc.description}
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRemove(inc.id)}
                    disabled={removingId === inc.id}
                    aria-label={`Remove incident ${inc.id}`}
                    style={{
                      backgroundColor: "#ffffff",
                      color: "#e11d48",
                      border: "1px solid #fecdd3",
                      borderRadius: "4px",
                      padding: "3px 8px",
                      fontSize: "0.72rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                    title={`Remove incident ${inc.id}`}
                  >
                    {removingId === inc.id ? "Clearing..." : "Clear"}
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Inject Incident Form */}
          <form onSubmit={handleInject} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div className="form-field">
          <label htmlFor="panel-inc-type" className="form-label">
            Incident Type
          </label>
          <select
            id="panel-inc-type"
            value={incidentType}
            onChange={(e) => setIncidentType(e.target.value as IncidentType)}
            disabled={!hasActiveRun || isSubmitting}
            className="form-select"
          >
            <option value="road_closure">Road Closure (Block Path)</option>
            <option value="congestion">Traffic Congestion (Delay)</option>
            <option value="obstacle">Physical Obstacle / Debris</option>
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="panel-inc-edge" className="form-label">
            Target Edge
          </label>
          <select
            id="panel-inc-edge"
            value={targetEdgeId}
            onChange={(e) => setTargetEdgeId(e.target.value)}
            disabled={!hasActiveRun || isSubmitting}
            className="form-select"
          >
            {availableEdges.map((e) => (
              <option key={e.id} value={e.id}>
                {e.id} ({e.lanes || 2} lanes)
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label className="form-label">Severity</label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "4px" }}>
            {(["low", "medium", "high", "critical"] as IncidentSeverity[]).map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setSeverity(sev)}
                style={{
                  padding: "5px 2px",
                  borderRadius: "5px",
                  border: severity === sev ? "1px solid #0f172a" : "1px solid #e2e8f0",
                  backgroundColor: severity === sev ? "#0f172a" : "#ffffff",
                  color: severity === sev ? "#ffffff" : "#475569",
                  fontFamily: "Space Grotesk, sans-serif",
                  fontSize: "0.72rem",
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

        {incidentType === "congestion" && (
          <div className="form-field">
            <label className="form-label">Delay Multiplier: {delayMultiplier}×</label>
            <input
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
            <label htmlFor="panel-inc-obstacle" className="form-label">Obstacle Type</label>
            <select
              id="panel-inc-obstacle"
              value={obstacleType}
              onChange={(e) => setObstacleType(e.target.value as ObstacleType)}
              className="form-select"
            >
              <option value="construction">Construction Barricade</option>
              <option value="debris">Debris / Fallen Cargo</option>
              <option value="stalled_vehicle">Disabled Vehicle</option>
              <option value="static_barrier">Jersey Barrier</option>
            </select>
          </div>
        )}

        <div className="form-field">
          <label htmlFor="panel-inc-desc" className="form-label">Description (Optional)</label>
          <input
            id="panel-inc-desc"
            type="text"
            placeholder="e.g. Broken water main"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="form-input"
          />
        </div>

        <button
          type="submit"
          disabled={!hasActiveRun || isSubmitting || isLoading}
          className="form-btn-primary"
          aria-label="Inject Incident"
          style={{ marginTop: "4px" }}
        >
          {isSubmitting ? "Injecting..." : "⚡ Inject Incident"}
        </button>
      </form>
        </>
      )}
    </div>
  );
};
