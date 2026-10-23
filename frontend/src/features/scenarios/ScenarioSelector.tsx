import React, { useState } from "react";
import type { RunStatus, ScenarioSummary } from "../../types/simulation";

export interface ScenarioSelectorProps {
  scenarios: ScenarioSummary[];
  selectedScenarioId: string;
  onSelectScenario: (scenarioId: string) => void;
  onCreateRun: (scenarioId: string, maxTicks?: number) => Promise<void>;
  currentRun: RunStatus | null;
  onStepRun: (ticks: number, runToCompletion?: boolean) => Promise<void>;
  onCancelRun: () => Promise<void>;
  isLoading: boolean;
  actionError: string | null;
}

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  onCreateRun,
  currentRun,
  onStepRun,
  onCancelRun,
  isLoading,
  actionError,
}) => {
  const [maxTicksInput, setMaxTicksInput] = useState<string>("100");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedScn = scenarios.find((s) => s.id === selectedScenarioId);

  const handleStartRun = async () => {
    if (!selectedScenarioId) return;
    setIsSubmitting(true);
    try {
      const ticks = maxTicksInput ? parseInt(maxTicksInput, 10) : undefined;
      await onCreateRun(selectedScenarioId, Number.isFinite(ticks) ? ticks : undefined);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStep = async (ticks: number, runToCompletion = false) => {
    if (!currentRun) return;
    setIsSubmitting(true);
    try {
      await onStepRun(ticks, runToCompletion);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!currentRun) return;
    setIsSubmitting(true);
    try {
      await onCancelRun();
    } finally {
      setIsSubmitting(false);
    }
  };

  const isTerminal = currentRun?.is_terminal || false;

  return (
    <div className="swiss-card" role="region" aria-label="Scenario and Run Controls">
      <div className="swiss-card-header">
        <div>
          <h3 className="swiss-card-title">Scenario & Workstation</h3>
          <span className="swiss-card-kicker">Metropolitan road network & multi-agent parameters</span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {/* Scenario Selection Dropdown */}
        <div className="form-field" style={{ marginBottom: 0 }}>
          <label htmlFor="scenario-select" className="form-label">
            Select Scenario
          </label>
          <select
            id="scenario-select"
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
            disabled={isLoading || isSubmitting}
            className="form-select"
          >
            {scenarios.length === 0 ? (
              <option value="">No scenarios available</option>
            ) : (
              scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.vehicle_count} veh, {s.road_network_source})
                </option>
              ))
            )}
          </select>
        </div>

        {selectedScn && (
          <div style={{ backgroundColor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "10px" }}>
            <p style={{ fontSize: "0.78rem", color: "#475569", marginBottom: "8px" }}>
              {selectedScn.description}
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", fontSize: "0.72rem", color: "#64748b" }}>
              <span>Vehicles: {selectedScn.vehicle_count}</span>
              <span>·</span>
              <span>Network: {selectedScn.road_network_source}</span>
              <span>·</span>
              <span>dt: {selectedScn.time_step_s}s</span>
            </div>
          </div>
        )}

        {/* Run Creation Form */}
        <div style={{ display: "flex", gap: "8px", alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="max-ticks-input" className="form-label">
              Ticks Limit
            </label>
            <input
              id="max-ticks-input"
              type="number"
              min="1"
              max="5000"
              value={maxTicksInput}
              onChange={(e) => setMaxTicksInput(e.target.value)}
              disabled={isLoading || isSubmitting}
              className="form-input"
              placeholder="200"
            />
          </div>

          <button
            type="button"
            onClick={handleStartRun}
            disabled={!selectedScenarioId || isLoading || isSubmitting}
            className="form-btn-primary"
            style={{ width: "auto", height: "36px", padding: "0 16px" }}
            aria-label="Create and initialize new simulation run"
          >
            {isSubmitting ? "Starting..." : "Initialize Run"}
          </button>
        </div>

        {actionError && (
          <div style={{ backgroundColor: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca", padding: "8px 10px", borderRadius: "6px", fontSize: "0.78rem" }} role="alert">
            {actionError}
          </div>
        )}

        {/* Current Run Active Status Box */}
        {currentRun && (
          <div style={{ backgroundColor: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px", marginTop: "4px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
              <div>
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a" }}>Run Status </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.72rem", color: "#0284c7" }}>
                  #{currentRun.run_id}
                </span>
              </div>
              <span style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "0.68rem",
                fontWeight: 700,
                padding: "2px 6px",
                borderRadius: "4px",
                backgroundColor: currentRun.lifecycle_state === "RUNNING" ? "#ecfdf5" : "#f1f5f9",
                color: currentRun.lifecycle_state === "RUNNING" ? "#059669" : "#475569",
                border: "1px solid #e2e8f0",
              }}>
                {currentRun.lifecycle_state}
              </span>
            </div>

            <div className="kpi-row-grid" style={{ marginBottom: "12px" }}>
              <div className="kpi-cell">
                <span className="kpi-cell-label">Current Tick</span>
                <span className="kpi-cell-value">{currentRun.current_tick}</span>
              </div>
              <div className="kpi-cell">
                <span className="kpi-cell-label">Sim Time</span>
                <span className="kpi-cell-value">{currentRun.elapsed_time_s.toFixed(1)}s</span>
              </div>
              <div className="kpi-cell">
                <span className="kpi-cell-label">Arrived</span>
                <span className="kpi-cell-value">
                  {currentRun.arrived_count}/{currentRun.total_vehicles}
                </span>
              </div>
              <div className="kpi-cell">
                <span className="kpi-cell-label">Active</span>
                <span className="kpi-cell-value">{currentRun.active_count}</span>
              </div>
            </div>

            {/* Stepping and Control Buttons */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "6px" }}>
              <button
                type="button"
                onClick={() => handleStep(1)}
                disabled={isTerminal || isSubmitting}
                className="btn-transport-step"
                style={{ height: "30px", fontSize: "0.75rem", padding: 0 }}
                aria-label="Step +1"
                title="Advance simulation by 1 discrete tick"
              >
                +1 tick
              </button>
              <button
                type="button"
                onClick={() => handleStep(10)}
                disabled={isTerminal || isSubmitting}
                className="btn-transport-step"
                style={{ height: "30px", fontSize: "0.75rem", padding: 0 }}
                aria-label="Step +10"
                title="Advance simulation by 10 discrete ticks"
              >
                +10 ticks
              </button>
              <button
                type="button"
                onClick={() => handleStep(0, true)}
                disabled={isTerminal || isSubmitting}
                className="btn-transport-step"
                style={{ height: "30px", fontSize: "0.75rem", padding: 0 }}
                aria-label="Run to End"
                title="Execute simulation run to completion"
              >
                End
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={isTerminal || isSubmitting}
                className="btn-transport-step"
                style={{ height: "30px", fontSize: "0.75rem", padding: 0, color: "#dc2626", borderColor: "#fecdd3", backgroundColor: "#fff1f2" }}
                aria-label="Cancel Run"
                title="Cancel simulation run"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
