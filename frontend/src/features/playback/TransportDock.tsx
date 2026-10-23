import React from "react";
import type { PlaybackSpeed, PlaybackState, TimelineRange } from "../../types/playback";
import type { ScenarioSummary, RunStatus } from "../../types/simulation";

export interface TransportDockProps {
  scenarios: ScenarioSummary[];
  selectedScenarioId: string;
  onSelectScenario: (scenarioId: string) => void;
  currentRun: RunStatus | null;
  playbackState: PlaybackState;
  speed: PlaybackSpeed;
  timeline: TimelineRange;
  isTerminal: boolean;
  canPlay: boolean;
  canStep: boolean;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStep: (ticks: number) => void;
  onSetSpeed: (speed: PlaybackSpeed) => void;
  onSeekTick: (tick: number) => void;
  onReturnToLive: () => void;
  onOpenIncidentModal: () => void;
  onInitializeRun: () => void;
  isLoading?: boolean;
}

export const TransportDock: React.FC<TransportDockProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  currentRun,
  playbackState,
  speed,
  timeline,
  isTerminal,
  canPlay,
  canStep,
  onPlay,
  onPause,
  onResume,
  onStep,
  onSetSpeed,
  onSeekTick,
  onReturnToLive,
  onOpenIncidentModal,
  onInitializeRun,
  isLoading = false,
}) => {
  const isPlaying = playbackState === "playing";
  const isReviewing = !timeline.isLive && timeline.activeReviewTick !== null;
  const currentTick = isReviewing ? timeline.activeReviewTick! : timeline.currentTick;
  const speedOptions: PlaybackSpeed[] = [0.5, 1, 2, 5];

  const handlePlayToggle = () => {
    if (isPlaying) {
      onPause();
    } else if (playbackState === "paused" || isReviewing) {
      onResume();
    } else {
      onPlay();
    }
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val)) {
      onSeekTick(val);
    }
  };

  return (
    <div className="transport-dock-wrapper" role="region" aria-label="Simulation Playback Transport Dock">
      <div className="transport-dock-card">
        {/* Scenario Quick Selector */}
        <div className="transport-scenario-pill">
          <select
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
            disabled={isLoading || isPlaying}
            className="scenario-select-minimal"
            title="Switch simulation scenario"
            aria-label="Select simulation scenario"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.vehicle_count} veh)
              </option>
            ))}
          </select>

          {(!currentRun || isTerminal) && (
            <button
              type="button"
              onClick={onInitializeRun}
              className="btn-transport-step"
              style={{ padding: "0 8px", height: "30px", fontSize: "0.75rem" }}
              title="Initialize simulation run"
            >
              Start
            </button>
          )}
        </div>

        {/* Transport Playback Buttons */}
        <div className="transport-actions-cluster">
          <button
            type="button"
            className={`btn-transport-play ${isPlaying ? "is-playing" : ""}`}
            onClick={handlePlayToggle}
            disabled={!canPlay && !isPlaying}
            aria-label={isPlaying ? "Pause simulation" : "Play simulation"}
            title={isPlaying ? "Pause playback" : "Start continuous playback"}
          >
            {isPlaying ? (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16" rx="1" />
                  <rect x="14" y="4" width="4" height="16" rx="1" />
                </svg>
                <span>Pause</span>
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                <span>{playbackState === "paused" ? "Resume" : "Play"}</span>
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-transport-step"
            onClick={() => onStep(1)}
            disabled={!canStep || isPlaying || isTerminal}
            aria-label="Advance 1 simulation tick"
            title="Step forward 1 tick (+1)"
          >
            +1 tick
          </button>

          <button
            type="button"
            className="btn-transport-step"
            onClick={() => onStep(10)}
            disabled={!canStep || isPlaying || isTerminal}
            aria-label="Advance 10 simulation ticks"
            title="Step forward 10 ticks (+10)"
          >
            +10
          </button>
        </div>

        {/* Playback Cadence Speeds */}
        <div className="speed-segmented-control" role="group" aria-label="Playback Speed">
          {speedOptions.map((opt) => (
            <button
              key={opt}
              type="button"
              className={`speed-segment-btn ${speed === opt ? "active" : ""}`}
              onClick={() => onSetSpeed(opt)}
              aria-pressed={speed === opt}
              title={`${opt}x playback speed`}
            >
              {opt}×
            </button>
          ))}
        </div>

        {/* Timeline Slider and Readout */}
        <div className="transport-scrubber-cluster">
          <input
            type="range"
            min={timeline.earliestTick}
            max={Math.max(timeline.latestTick, 1)}
            value={currentTick}
            onChange={handleSliderChange}
            disabled={timeline.latestTick <= timeline.earliestTick}
            className="transport-slider"
            title={`Scrub timeline (Tick ${currentTick}/${timeline.latestTick})`}
            aria-label="Scrub simulation timeline"
          />

          <div className="transport-tick-meta">
            <span className="tick-highlight">t={currentTick}</span>
            <span> / {timeline.latestTick}</span>
            {isReviewing && (
              <button
                type="button"
                onClick={onReturnToLive}
                style={{
                  marginLeft: "8px",
                  padding: "2px 6px",
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  backgroundColor: "#fef3c7",
                  color: "#b45309",
                  border: "1px solid #fde68a",
                  borderRadius: "4px",
                  cursor: "pointer",
                }}
                title="Return to real-time live head"
              >
                Live ➔
              </button>
            )}
          </div>
        </div>

        {/* Quick Incident Button */}
        <button
          type="button"
          onClick={onOpenIncidentModal}
          className="btn-quick-incident"
          title="Inject road closure, congestion, or obstacle"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>Incident</span>
        </button>
      </div>
    </div>
  );
};
