/**
 * Client-driven playback scheduler for AMAPP simulation.
 *
 * Periodically issues bounded simulation step requests to the authoritative backend,
 * strictly enforces non-overlapping request execution, avoids browser-tab throttling bursts,
 * and dynamically adjusts request cadence based on playback speed multiplier.
 */

import type { PlaybackSchedulerConfig, PlaybackSpeed, PlaybackState } from "../../types/playback";

export interface PlaybackSchedulerCallbacks {
  onStep: (ticks: number) => Promise<boolean>;
  onStateChange: (state: PlaybackState) => void;
  onError?: (error: string) => void;
}

export class PlaybackScheduler {
  private state: PlaybackState = "idle";
  private speed: PlaybackSpeed = 1;
  private timeStepS: number = 0.1;
  private minIntervalMs: number = 20;

  private isStepInProgress: boolean = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private isDisposed: boolean = false;

  private readonly callbacks: PlaybackSchedulerCallbacks;

  constructor(callbacks: PlaybackSchedulerCallbacks, config?: PlaybackSchedulerConfig) {
    this.callbacks = callbacks;
    if (config?.speed !== undefined) this.speed = config.speed;
    if (config?.timeStepS !== undefined) this.timeStepS = Math.max(0.01, config.timeStepS);
    if (config?.minIntervalMs !== undefined) this.minIntervalMs = config.minIntervalMs;
  }

  public getState(): PlaybackState {
    return this.state;
  }

  public getSpeed(): PlaybackSpeed {
    return this.speed;
  }

  public getTimeStepS(): number {
    return this.timeStepS;
  }

  public setState(nextState: PlaybackState): void {
    if (this.state !== nextState) {
      this.state = nextState;
      this.callbacks.onStateChange(nextState);
    }
  }

  public setSpeed(nextSpeed: PlaybackSpeed): void {
    this.speed = nextSpeed;
  }

  public setTimeStepS(dt: number): void {
    this.timeStepS = Math.max(0.01, dt);
  }

  public getIntervalMs(): number {
    const rawInterval = (this.timeStepS * 1000) / this.speed;
    return Math.max(this.minIntervalMs, Math.round(rawInterval));
  }

  public play(): void {
    if (this.isDisposed) return;
    if (this.state === "completed" || this.state === "cancelled" || this.state === "failed") {
      return;
    }
    this.setState("playing");
    this.scheduleNextTick(0);
  }

  public pause(): void {
    if (this.isDisposed) return;
    this.clearTimer();
    if (this.state === "playing" || this.state === "stepping") {
      this.setState("paused");
    }
  }

  public resume(): void {
    if (this.state === "paused" || this.state === "ready" || this.state === "reviewing") {
      this.play();
    }
  }

  public stop(): void {
    this.clearTimer();
    this.isStepInProgress = false;
  }

  /**
   * Execute a discrete single or multi-tick step manually.
   */
  public async executeManualStep(ticks: number): Promise<boolean> {
    if (this.isDisposed || this.isStepInProgress) return false;
    this.clearTimer();
    this.setState("stepping");
    this.isStepInProgress = true;

    try {
      const shouldContinue = await this.callbacks.onStep(ticks);
      if (!this.isDisposed) {
        if (!shouldContinue) {
          // Run became terminal during step
          return false;
        }
        this.setState("paused");
      }
      return shouldContinue;
    } catch (err) {
      if (!this.isDisposed) {
        this.setState("paused");
        const msg = err instanceof Error ? err.message : "Step execution failed";
        this.callbacks.onError?.(msg);
      }
      return false;
    } finally {
      this.isStepInProgress = false;
    }
  }

  private scheduleNextTick(delayMs?: number): void {
    this.clearTimer();
    if (this.isDisposed || this.state !== "playing") return;

    const delay = delayMs !== undefined ? delayMs : this.getIntervalMs();
    this.timer = setTimeout(async () => {
      await this.handleTick();
    }, delay);
  }

  private async handleTick(): Promise<void> {
    if (this.isDisposed || this.state !== "playing") return;

    // Safety guard: never issue overlapping requests
    if (this.isStepInProgress) {
      this.scheduleNextTick(15);
      return;
    }

    this.isStepInProgress = true;
    try {
      const shouldContinue = await this.callbacks.onStep(1);
      if (this.isDisposed) return;

      if (!shouldContinue) {
        // Run has arrived, reached limit, or completed
        this.clearTimer();
        return;
      }

      if (this.state === "playing") {
        this.scheduleNextTick();
      }
    } catch (err) {
      if (!this.isDisposed) {
        this.pause();
        const msg = err instanceof Error ? err.message : "Periodic playback step error";
        this.callbacks.onError?.(msg);
      }
    } finally {
      this.isStepInProgress = false;
    }
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  public dispose(): void {
    this.isDisposed = true;
    this.clearTimer();
    this.isStepInProgress = false;
  }
}
