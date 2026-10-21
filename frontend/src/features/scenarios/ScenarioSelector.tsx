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
    <div className="panel scenario-control-panel">
      <div className="panel-header">
        <h2 className="panel-title">Scenario & Run Controls</h2>
      </div>

      <div className="panel-body">
        {/* Scenario Selection Dropdown */}
        <div className="control-group">
          <label htmlFor="scenario-select" className="control-label">
            Select Scenario
          </label>
          <select
            id="scenario-select"
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
            disabled={isLoading || isSubmitting}
            className="select-input"
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
          <div className="scenario-meta-box">
            <p className="scenario-desc">{selectedScn.description}</p>
            <div className="scenario-tags">
              <span className="meta-tag">Vehicles: {selectedScn.vehicle_count}</span>
              <span className="meta-tag">Network: {selectedScn.road_network_source}</span>
              <span className="meta-tag">dt: {selectedScn.time_step_s}s</span>
              {selectedScn.max_ticks && (
                <span className="meta-tag">Max Ticks: {selectedScn.max_ticks}</span>
              )}
            </div>
          </div>
        )}

        {/* Run Creation Form */}
        <div className="run-create-row">
          <div className="ticks-input-group">
            <label htmlFor="max-ticks-input" className="sub-label">
              Ticks Cap
            </label>
            <input
              id="max-ticks-input"
              type="number"
              min="1"
              max="2000"
              value={maxTicksInput}
              onChange={(e) => setMaxTicksInput(e.target.value)}
              disabled={isLoading || isSubmitting}
              className="text-input text-input-sm"
              placeholder="100"
            />
          </div>

          <button
            type="button"
            onClick={handleStartRun}
            disabled={!selectedScenarioId || isLoading || isSubmitting}
            className="btn btn-primary"
            aria-label="Create and initialize new simulation run"
          >
            {isSubmitting ? "Initializing..." : "Initialize Run"}
          </button>
        </div>

        {actionError && (
          <div className="alert alert-error" role="alert">
            {actionError}
          </div>
        )}

        {/* Current Run Active Status Box */}
        {currentRun && (
          <div className="current-run-card">
            <div className="current-run-header">
              <div>
                <span className="current-run-title">Run Status</span>
                <span className="current-run-id">#{currentRun.run_id}</span>
              </div>
              <span className={`lifecycle-badge lifecycle-${currentRun.lifecycle_state.toLowerCase()}`}>
                {currentRun.lifecycle_state}
              </span>
            </div>

            <div className="run-stats-grid">
              <div className="stat-card">
                <span className="stat-label">Tick</span>
                <span className="stat-value">{currentRun.current_tick}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Sim Time</span>
                <span className="stat-value">{currentRun.elapsed_time_s.toFixed(1)}s</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Arrived</span>
                <span className="stat-value">
                  {currentRun.arrived_count}/{currentRun.total_vehicles}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Active</span>
                <span className="stat-value">{currentRun.active_count}</span>
              </div>
            </div>

            {/* Stepping and Control Buttons */}
            <div className="run-controls-toolbar">
              <button
                type="button"
                onClick={() => handleStep(1)}
                disabled={isTerminal || isSubmitting}
                className="btn btn-secondary btn-sm"
                title="Advance simulation by 1 discrete tick"
              >
                Step +1
              </button>
              <button
                type="button"
                onClick={() => handleStep(10)}
                disabled={isTerminal || isSubmitting}
                className="btn btn-secondary btn-sm"
                title="Advance simulation by 10 discrete ticks"
              >
                Step +10
              </button>
              <button
                type="button"
                onClick={() => handleStep(0, true)}
                disabled={isTerminal || isSubmitting}
                className="btn btn-secondary btn-sm"
                title="Execute simulation run to completion"
              >
                Run to End
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={isTerminal || isSubmitting}
                className="btn btn-danger btn-sm"
                title="Cooperative cancellation of simulation run"
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
