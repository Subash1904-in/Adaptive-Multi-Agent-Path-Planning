import React from "react";
import type { PlaybackSpeed, PlaybackState, TimelineRange } from "../../types/playback";

export interface PlaybackBarProps {
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
}

export const PlaybackBar: React.FC<PlaybackBarProps> = ({
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
}) => {
  const isPlaying = playbackState === "playing";
  const isStepping = playbackState === "stepping";
  const isReviewing = !timeline.isLive && timeline.activeReviewTick !== null;
  const displayTick = isReviewing ? timeline.activeReviewTick! : timeline.currentTick;
  const displaySimTime = (displayTick * (timeline.simulationTimeS / Math.max(1, timeline.currentTick || 1))).toFixed(1);

  const handlePlayToggle = () => {
    if (isPlaying) {
      onPause();
    } else if (playbackState === "paused" || isReviewing) {
      onResume();
    } else {
      onPlay();
    }
  };

  const handleScrubberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const tick = parseInt(e.target.value, 10);
    if (Number.isFinite(tick)) {
      onSeekTick(tick);
    }
  };

  const speedOptions: PlaybackSpeed[] = [0.5, 1, 2, 5];

  return (
    <div
      className="playback-bar-container"
      role="region"
      aria-label="Simulation Playback and Timeline Controls"
    >
      {/* Top Row: Playback Buttons, Speed Selector, State Badges */}
      <div className="playback-controls-row">
        {/* Play / Pause / Step Cluster */}
        <div className="playback-btn-group" role="group" aria-label="Playback Transport Controls">
          <button
            type="button"
            className={`btn-playback-toggle ${isPlaying ? "playing" : ""}`}
            onClick={handlePlayToggle}
            disabled={!canPlay && !isPlaying}
            aria-label={isPlaying ? "Pause simulation playback" : "Play simulation playback"}
            title={
              isPlaying
                ? "Pause client-driven simulation stepping"
                : "Play (Client-driven periodic stepping)"
            }
          >
            {isPlaying ? (
              <>
                <span className="btn-icon">⏸</span>
                <span className="btn-text">Pause</span>
              </>
            ) : (
              <>
                <span className="btn-icon">▶</span>
                <span className="btn-text">{playbackState === "paused" ? "Resume" : "Play"}</span>
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-playback-step"
            onClick={() => onStep(1)}
            disabled={!canStep || isPlaying || isStepping || isTerminal}
            aria-label="Advance simulation by 1 tick"
            title="Advance authoritative simulation by 1 discrete tick (+1)"
          >
            <span className="btn-icon">⏭</span>
            <span className="btn-text">+1</span>
          </button>

          <button
            type="button"
            className="btn-playback-step"
            onClick={() => onStep(10)}
            disabled={!canStep || isPlaying || isStepping || isTerminal}
            aria-label="Advance simulation by 10 ticks"
            title="Advance authoritative simulation by 10 discrete ticks (+10)"
          >
            <span className="btn-icon">⏩</span>
            <span className="btn-text">+10</span>
          </button>
        </div>

        {/* Speed Multiplier Cluster */}
        <div className="speed-selector-group" role="group" aria-label="Playback Speed Cadence">
          <span className="speed-label" id="speed-selector-label">Speed:</span>
          <div className="speed-btn-cluster" aria-labelledby="speed-selector-label">
            {speedOptions.map((opt) => (
              <button
                key={opt}
                type="button"
                className={`btn-speed ${speed === opt ? "active" : ""}`}
                onClick={() => onSetSpeed(opt)}
                aria-pressed={speed === opt}
                aria-label={`${opt}x playback speed`}
                title={`Set playback cadence to ${opt}x (tick physics unchanged)`}
              >
                {opt}×
              </button>
            ))}
          </div>
        </div>

        {/* Status Indicators & Live/Review Switcher */}
        <div className="playback-status-group">
          {timeline.isLive ? (
            <span className="mode-badge mode-live" aria-live="polite">
              <span className="live-dot" aria-hidden="true" />
              LIVE STREAM
            </span>
          ) : (
            <div className="review-mode-indicator">
              <span className="mode-badge mode-review" aria-live="polite">
                🕒 REVIEW (Tick {displayTick})
              </span>
              <button
                type="button"
                className="btn-return-live"
                onClick={onReturnToLive}
                aria-label="Return to live simulation view"
                title="Exit historical review and return to live simulation view"
              >
                Return to Live ➔
              </button>
            </div>
          )}

          <span className={`playback-state-tag state-${playbackState}`}>
            {playbackState.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Bottom Row: Timeline Scrubber, Tick Readout, Buffer Capacity Info */}
      <div className="timeline-scrubber-row">
        <div className="timeline-meta-left">
          <span className="timeline-tick-label">
            {timeline.bufferedCount > 0 ? `Tick ${timeline.earliestTick}` : "Tick 0"}
          </span>
        </div>

        <div className="timeline-slider-track">
          <label htmlFor="timeline-scrubber-input" className="sr-only">
            Timeline position scrubber
          </label>
          <input
            id="timeline-scrubber-input"
            type="range"
            min={timeline.earliestTick}
            max={Math.max(timeline.earliestTick, timeline.latestTick)}
            value={displayTick}
            onChange={handleScrubberChange}
            disabled={timeline.bufferedCount === 0}
            className="timeline-range-input"
            aria-valuemin={timeline.earliestTick}
            aria-valuemax={Math.max(timeline.earliestTick, timeline.latestTick)}
            aria-valuenow={displayTick}
            aria-valuetext={`Tick ${displayTick}, Simulation time ${displaySimTime} seconds`}
          />
        </div>

        <div className="timeline-meta-right">
          <span className="timeline-tick-label">
            {timeline.bufferedCount > 0 ? `Tick ${timeline.latestTick}` : "Tick 0"}
          </span>
        </div>

        <div className="timeline-readout">
          <span className="readout-primary">
            Tick <strong className="readout-tick">{displayTick}</strong>
            {timeline.maxTicks !== null && timeline.maxTicks !== undefined && (
              <span className="readout-total"> / {timeline.maxTicks}</span>
            )}
            {" "}({displaySimTime}s)
          </span>
          <span className="readout-buffer">
            [{timeline.bufferedCount} frames in memory]
          </span>
        </div>
      </div>
    </div>
  );
};
