import React, { useMemo, useState } from "react";
import type { ScenarioDefinition, RunStatus, TrafficSignalScenarioDefinition } from "../../types/simulation";
import type {
  CreateIncidentPayload,
  IncidentRecord,
  IncidentSeverity,
  IncidentType,
  ObstacleType,
} from "../../types/incidents";
import { extractRoadNetworkFromScenario } from "../scene3d/geometry";
import type { RoadEdgeGeometry } from "../../types/graph";

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
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [incidentType, setIncidentType] = useState<IncidentType>("road_closure");
  const [targetEdgeId, setTargetEdgeId] = useState<string>("");
  const [targetNodeId, setTargetNodeId] = useState<string>("");
  const [severity, setSeverity] = useState<IncidentSeverity>("high");
  const [delayMultiplier, setDelayMultiplier] = useState<number>(2.5);
  const [obstacleType, setObstacleType] = useState<ObstacleType>("construction");
  const [signalPhase, setSignalPhase] = useState<"RED" | "YELLOW" | "GREEN">("RED");
  const [durationS, setDurationS] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const geometry = useMemo(() => (scenario ? extractRoadNetworkFromScenario(scenario) : null), [scenario]);
  const availableEdges = geometry?.edges || [];
  const availableSignals = scenario?.signals || [];

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

    const payload: CreateIncidentPayload = {
      incident_type: incidentType,
      severity,
      description: description.trim() || undefined,
    };

    if (incidentType === "road_closure") {
      const edge = targetEdgeId || (availableEdges[0]?.id ?? "");
      if (!edge) {
        setErrorMessage("Please select a target edge for road closure.");
        return;
      }
      payload.edge_id = edge;
      payload.affected_edge_id = edge;
    } else if (incidentType === "congestion") {
      const edge = targetEdgeId || (availableEdges[0]?.id ?? "");
      if (!edge) {
        setErrorMessage("Please select a target edge for congestion.");
        return;
      }
      payload.edge_id = edge;
      payload.affected_edge_id = edge;
      payload.delay_multiplier = delayMultiplier;
      payload.congestion_factor = delayMultiplier;
    } else if (incidentType === "obstacle") {
      const edge = targetEdgeId || (availableEdges[0]?.id ?? "");
      if (!edge) {
        setErrorMessage("Please select a target edge for obstacle injection.");
        return;
      }
      payload.edge_id = edge;
      payload.affected_edge_id = edge;
      payload.obstacle_type = obstacleType;
    } else if (incidentType === "signal_override") {
      const sig = targetNodeId || (availableSignals[0]?.signal_id ?? availableSignals[0]?.node_id ?? "");
      if (!sig) {
        setErrorMessage("Please specify or select a target signal / intersection.");
        return;
      }
      payload.signal_id = sig;
      payload.affected_node_id = sig;
      payload.override_phase = signalPhase;
      payload.target_signal_phase = signalPhase.toLowerCase() as "red" | "yellow" | "green";
      if (durationS && Number(durationS) > 0) {
        payload.duration_s = Number(durationS);
      }
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
    <div
      className="incident-control-panel-card"
      role="region"
      aria-label="Traffic Incident Injection and Scenario Controls"
      style={{
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        backdropFilter: "blur(6px)",
        border: "1px solid #334155",
        borderRadius: "8px",
        padding: "14px 16px",
        marginTop: "12px",
        color: "#f8fafc",
        fontFamily: "Space Grotesk, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "1.1rem" }}>⚠️</span>
          <h3
            style={{
              margin: 0,
              fontSize: "0.95rem",
              fontWeight: 700,
              letterSpacing: "0.02em",
              textTransform: "uppercase",
              color: "#38bdf8",
            }}
          >
            Incident Controls
          </h3>
          {activeIncidents.length > 0 && (
            <span
              style={{
                backgroundColor: "#ef4444",
                color: "#ffffff",
                borderRadius: "12px",
                padding: "1px 7px",
                fontSize: "0.72rem",
                fontWeight: 700,
              }}
            >
              {activeIncidents.length}
            </span>
          )}
        </div>
        <button
          type="button"
          aria-expanded={isExpanded}
          aria-label={isExpanded ? "Collapse Incident Panel" : "Expand Incident Panel"}
          style={{
            background: "none",
            border: "none",
            color: "#94a3b8",
            fontSize: "1rem",
            cursor: "pointer",
          }}
        >
          {isExpanded ? "▲" : "▼"}
        </button>
      </div>

      {isExpanded && (
        <div style={{ marginTop: "12px" }}>
          {errorMessage && (
            <div
              role="alert"
              style={{
                backgroundColor: "rgba(239, 68, 68, 0.15)",
                border: "1px solid #ef4444",
                borderRadius: "6px",
                padding: "8px 10px",
                marginBottom: "12px",
                fontSize: "0.78rem",
                color: "#fca5a5",
              }}
            >
              {errorMessage}
            </div>
          )}

          {/* Incident Injection Form */}
          <form onSubmit={handleInject} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label htmlFor="incident-type-select" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                Incident Type
              </label>
              <select
                id="incident-type-select"
                value={incidentType}
                onChange={(e) => setIncidentType(e.target.value as IncidentType)}
                disabled={!hasActiveRun || isSubmitting}
                style={{
                  backgroundColor: "#1e293b",
                  border: "1px solid #475569",
                  borderRadius: "6px",
                  padding: "6px 8px",
                  color: "#f8fafc",
                  fontSize: "0.82rem",
                  cursor: hasActiveRun ? "pointer" : "not-allowed",
                }}
              >
                <option value="road_closure">🛑 Road Closure (Impassable Edge)</option>
                <option value="congestion">🚗 Localized Congestion (Delay Multiplier)</option>
                <option value="obstacle">🚧 Obstacle / Work Zone</option>
                <option value="signal_override">🚦 Signal Phase Override</option>
              </select>
            </div>

            {/* Target Selector: Edge or Signal Node */}
            {incidentType !== "signal_override" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="incident-edge-select" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Target Edge
                </label>
                {availableEdges.length > 0 ? (
                  <select
                    id="incident-edge-select"
                    value={targetEdgeId || (availableEdges[0]?.id ?? "")}
                    onChange={(e) => setTargetEdgeId(e.target.value)}
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                      cursor: hasActiveRun ? "pointer" : "not-allowed",
                    }}
                  >
                    {availableEdges.map((e: RoadEdgeGeometry) => (
                      <option key={e.id} value={e.id}>
                        {e.id} ({e.start_node_id} → {e.end_node_id})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="incident-edge-input"
                    type="text"
                    value={targetEdgeId}
                    onChange={(e) => setTargetEdgeId(e.target.value)}
                    placeholder="e.g. edge_n0_n1"
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                    }}
                  />
                )}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="incident-signal-select" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Target Signal / Intersection
                </label>
                {availableSignals.length > 0 ? (
                  <select
                    id="incident-signal-select"
                    value={targetNodeId || (availableSignals[0]?.signal_id ?? availableSignals[0]?.node_id ?? "")}
                    onChange={(e) => setTargetNodeId(e.target.value)}
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                      cursor: hasActiveRun ? "pointer" : "not-allowed",
                    }}
                  >
                    {availableSignals.map((s: TrafficSignalScenarioDefinition) => (
                      <option key={s.signal_id} value={s.signal_id}>
                        {s.signal_id} ({s.node_id})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="incident-signal-input"
                    type="text"
                    value={targetNodeId}
                    onChange={(e) => setTargetNodeId(e.target.value)}
                    placeholder="e.g. sig_intersection_1"
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                    }}
                  />
                )}
              </div>
            )}

            {/* Type-Specific Options */}
            {incidentType === "congestion" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="congestion-multiplier" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Delay Multiplier ({delayMultiplier}x)
                </label>
                <input
                  id="congestion-multiplier"
                  type="range"
                  min="1.2"
                  max="6.0"
                  step="0.1"
                  value={delayMultiplier}
                  onChange={(e) => setDelayMultiplier(Number(e.target.value))}
                  disabled={!hasActiveRun || isSubmitting}
                  style={{ width: "100%", accentColor: "#f97316" }}
                />
              </div>
            )}

            {incidentType === "obstacle" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="obstacle-type-select" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Obstacle Hazard Type
                </label>
                <select
                  id="obstacle-type-select"
                  value={obstacleType}
                  onChange={(e) => setObstacleType(e.target.value as ObstacleType)}
                  disabled={!hasActiveRun || isSubmitting}
                  style={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #475569",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    color: "#f8fafc",
                    fontSize: "0.82rem",
                  }}
                >
                  <option value="construction">Construction Barrier</option>
                  <option value="debris">Debris / Road Spill</option>
                  <option value="stalled_vehicle">Stalled / Disabled Vehicle</option>
                  <option value="static_barrier">Static Structural Barrier</option>
                </select>
              </div>
            )}

            {incidentType === "signal_override" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <label htmlFor="signal-override-phase" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                    Override Phase
                  </label>
                  <select
                    id="signal-override-phase"
                    value={signalPhase}
                    onChange={(e) => setSignalPhase(e.target.value as "RED" | "YELLOW" | "GREEN")}
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                    }}
                  >
                    <option value="RED">🔴 RED (Hold All)</option>
                    <option value="GREEN">🟢 GREEN (Priority Pass)</option>
                    <option value="YELLOW">🟡 YELLOW (Caution)</option>
                  </select>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <label htmlFor="signal-override-duration" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                    Duration (s, opt)
                  </label>
                  <input
                    id="signal-override-duration"
                    type="number"
                    min="1"
                    max="300"
                    placeholder="Indefinite"
                    value={durationS}
                    onChange={(e) => setDurationS(e.target.value)}
                    disabled={!hasActiveRun || isSubmitting}
                    style={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "6px",
                      padding: "6px 8px",
                      color: "#f8fafc",
                      fontSize: "0.82rem",
                    }}
                  />
                </div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="incident-severity-select" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Severity
                </label>
                <select
                  id="incident-severity-select"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value as IncidentSeverity)}
                  disabled={!hasActiveRun || isSubmitting}
                  style={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #475569",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    color: "#f8fafc",
                    fontSize: "0.82rem",
                  }}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label htmlFor="incident-desc-input" style={{ fontSize: "0.76rem", color: "#94a3b8", fontWeight: 600 }}>
                  Notes (opt)
                </label>
                <input
                  id="incident-desc-input"
                  type="text"
                  placeholder="e.g. Flooded water main"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={!hasActiveRun || isSubmitting}
                  style={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #475569",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    color: "#f8fafc",
                    fontSize: "0.82rem",
                  }}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={!hasActiveRun || isSubmitting || isLoading}
              style={{
                backgroundColor: hasActiveRun ? "#dc2626" : "#475569",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                padding: "8px 12px",
                fontSize: "0.85rem",
                fontWeight: 700,
                cursor: hasActiveRun ? "pointer" : "not-allowed",
                marginTop: "4px",
                boxShadow: hasActiveRun ? "0 2px 6px rgba(220, 38, 38, 0.4)" : "none",
                transition: "background-color 0.2s",
              }}
            >
              {isSubmitting ? "Injecting..." : "⚡ Inject Incident"}
            </button>
          </form>

          {/* Active Incidents List */}
          <div style={{ marginTop: "16px", borderTop: "1px solid #334155", paddingTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>
                Active Incidents ({activeIncidents.length})
              </span>
            </div>

            {activeIncidents.length === 0 ? (
              <p style={{ margin: 0, fontSize: "0.78rem", color: "#64748b", fontStyle: "italic" }}>
                No active traffic incidents injected.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {activeIncidents.map((inc) => {
                  const targetLabel = inc.affected_edge_id
                    ? `Edge: ${inc.affected_edge_id}`
                    : inc.affected_node_id
                    ? `Node: ${inc.affected_node_id}`
                    : "Scenario Wide";

                  const badgeColor =
                    inc.incident_type === "road_closure"
                      ? "#ef4444"
                      : inc.incident_type === "congestion"
                      ? "#f97316"
                      : inc.incident_type === "obstacle"
                      ? "#f59e0b"
                      : "#38bdf8";

                  return (
                    <div
                      key={inc.id}
                      style={{
                        backgroundColor: "#1e293b",
                        border: `1px solid ${badgeColor}`,
                        borderRadius: "6px",
                        padding: "8px 10px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "0.78rem",
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span
                            style={{
                              backgroundColor: badgeColor,
                              color: "#ffffff",
                              borderRadius: "4px",
                              padding: "1px 5px",
                              fontSize: "0.68rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                            }}
                          >
                            {inc.incident_type.replace("_", " ")}
                          </span>
                          <span style={{ fontWeight: 600, color: "#f8fafc" }}>{targetLabel}</span>
                        </div>
                        {inc.description && (
                          <span style={{ fontSize: "0.72rem", color: "#94a3b8" }}>{inc.description}</span>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleRemove(inc.id)}
                        disabled={!hasActiveRun || removingId === inc.id}
                        aria-label={`Remove incident ${inc.id}`}
                        style={{
                          backgroundColor: "#334155",
                          border: "1px solid #64748b",
                          borderRadius: "4px",
                          color: "#f8fafc",
                          padding: "4px 8px",
                          fontSize: "0.72rem",
                          fontWeight: 600,
                          cursor: hasActiveRun ? "pointer" : "not-allowed",
                        }}
                      >
                        {removingId === inc.id ? "..." : "Remove"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
