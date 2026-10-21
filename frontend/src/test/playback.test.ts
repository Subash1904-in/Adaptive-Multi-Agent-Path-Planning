import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SimulationHistoryBuffer } from "../features/playback/historyBuffer";
import { PlaybackScheduler } from "../features/playback/playbackScheduler";
import type { SimulationFrameSnapshot } from "../types/playback";
import type { VehicleState, PedestrianState, TrafficSignalState } from "../types/simulation";

describe("SimulationHistoryBuffer", () => {
  let buffer: SimulationHistoryBuffer;

  const createDummySnapshot = (tick: number, timeS: number): SimulationFrameSnapshot => {
    const vehicles = new Map<string, VehicleState>();
    vehicles.set(`v_${tick}`, {
      vehicle_id: `v_${tick}`,
      position: { x: tick * 10, y: 0 },
      speed_mps: 12.5,
      heading_rad: 0,
      lifecycle_state: "en_route",
      vehicle_type: "standard",
    });

    const pedestrians = new Map<string, PedestrianState>();
    pedestrians.set(`p_${tick}`, {
      pedestrian_id: `p_${tick}`,
      position: { x: 5, y: tick * 2 },
      speed_mps: 1.4,
      heading_rad: 1.57,
      lifecycle_state: "walking",
    });

    const signals = new Map<string, TrafficSignalState>();
    signals.set(`sig_1`, {
      signal_id: "sig_1",
      node_id: "node_1",
      state: tick % 2 === 0 ? "GREEN" : "RED",
    });

    return {
      tick,
      simulation_time_s: timeS,
      timestamp_ms: 1000 + tick * 100,
      vehicles,
      pedestrians,
      signals,
    };
  };

  beforeEach(() => {
    buffer = new SimulationHistoryBuffer(5); // small capacity for testing eviction
  });

  it("initializes with empty state and reports zero size", () => {
    expect(buffer.size()).toBe(0);
    expect(buffer.getCapacity()).toBe(5);
    expect(buffer.getEarliestTick()).toBeNull();
    expect(buffer.getLatestTick()).toBeNull();
    expect(buffer.getAllTicks()).toEqual([]);
  });

  it("inserts snapshots and maintains sorted tick order", () => {
    buffer.addSnapshot(createDummySnapshot(2, 0.2));
    buffer.addSnapshot(createDummySnapshot(0, 0.0));
    buffer.addSnapshot(createDummySnapshot(1, 0.1));

    expect(buffer.size()).toBe(3);
    expect(buffer.getAllTicks()).toEqual([0, 1, 2]);
    expect(buffer.getEarliestTick()).toBe(0);
    expect(buffer.getLatestTick()).toBe(2);
  });

  it("deep-clones entity maps to prevent mutation leakage", () => {
    const original = createDummySnapshot(5, 0.5);
    buffer.addSnapshot(original);

    // Mutate original maps
    original.vehicles.get("v_5")!.position.x = 9999;
    original.vehicles.set("new_veh", {
      vehicle_id: "new_veh",
      position: { x: 1, y: 1 },
      speed_mps: 0,
      heading_rad: 0,
      lifecycle_state: "ready",
      vehicle_type: "standard",
    });

    const stored = buffer.getSnapshot(5);
    expect(stored).toBeDefined();
    expect(stored!.vehicles.get("v_5")?.position.x).toBe(50); // unchanged
    expect(stored!.vehicles.has("new_veh")).toBe(false); // unpolluted
  });

  it("deduplicates snapshots at the same tick", () => {
    const snap1 = createDummySnapshot(4, 0.4);
    buffer.addSnapshot(snap1);
    expect(buffer.size()).toBe(1);

    // Update with duplicate tick
    const snap2 = createDummySnapshot(4, 0.4);
    snap2.simulation_time_s = 0.405;
    buffer.addSnapshot(snap2);

    expect(buffer.size()).toBe(1);
    expect(buffer.getAllTicks()).toEqual([4]);
    expect(buffer.getSnapshot(4)?.simulation_time_s).toBe(0.405);
  });

  it("enforces FIFO eviction when capacity is exceeded", () => {
    for (let t = 0; t < 8; t++) {
      buffer.addSnapshot(createDummySnapshot(t, t * 0.1));
    }

    expect(buffer.size()).toBe(5);
    expect(buffer.getAllTicks()).toEqual([3, 4, 5, 6, 7]);
    expect(buffer.getEarliestTick()).toBe(3);
    expect(buffer.getLatestTick()).toBe(7);
    expect(buffer.has(0)).toBe(false);
    expect(buffer.has(1)).toBe(false);
    expect(buffer.has(2)).toBe(false);
    expect(buffer.has(3)).toBe(true);
  });

  it("ignores non-finite and negative tick values defensively", () => {
    buffer.addSnapshot(createDummySnapshot(-1, -0.1));
    buffer.addSnapshot(createDummySnapshot(NaN, 0));
    expect(buffer.size()).toBe(0);
  });

  it("clears buffer cleanly", () => {
    buffer.addSnapshot(createDummySnapshot(1, 0.1));
    buffer.addSnapshot(createDummySnapshot(2, 0.2));
    expect(buffer.size()).toBe(2);

    buffer.clear();
    expect(buffer.size()).toBe(0);
    expect(buffer.getEarliestTick()).toBeNull();
    expect(buffer.getLatestTick()).toBeNull();
  });
});

describe("PlaybackScheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("initializes with default state, 1x speed, and 100ms interval", () => {
    const onStep = vi.fn().mockResolvedValue(true);
    const onStateChange = vi.fn();

    const scheduler = new PlaybackScheduler({ onStep, onStateChange });
    expect(scheduler.getState()).toBe("idle");
    expect(scheduler.getSpeed()).toBe(1);
    expect(scheduler.getTimeStepS()).toBe(0.1);
    expect(scheduler.getIntervalMs()).toBe(100);
    scheduler.dispose();
  });

  it("dynamically computes intervalMs based on speed and timeStepS", () => {
    const scheduler = new PlaybackScheduler({ onStep: vi.fn(), onStateChange: vi.fn() });

    scheduler.setTimeStepS(0.1);
    scheduler.setSpeed(1);
    expect(scheduler.getIntervalMs()).toBe(100);

    scheduler.setSpeed(0.5);
    expect(scheduler.getIntervalMs()).toBe(200);

    scheduler.setSpeed(2);
    expect(scheduler.getIntervalMs()).toBe(50);

    scheduler.setSpeed(5);
    expect(scheduler.getIntervalMs()).toBe(20);

    // Clamps to minIntervalMs
    scheduler.setTimeStepS(0.01);
    expect(scheduler.getIntervalMs()).toBe(20);
    scheduler.dispose();
  });

  it("periodically triggers onStep when playing using fake timers", async () => {
    const onStep = vi.fn().mockResolvedValue(true);
    const onStateChange = vi.fn();

    const scheduler = new PlaybackScheduler({ onStep, onStateChange }, { speed: 1, timeStepS: 0.1 });
    scheduler.play();

    expect(onStateChange).toHaveBeenCalledWith("playing");
    expect(scheduler.getState()).toBe("playing");

    // Advance 0ms -> initial tick scheduled
    await vi.advanceTimersByTimeAsync(1);
    expect(onStep).toHaveBeenCalledTimes(1);
    expect(onStep).toHaveBeenCalledWith(1);

    // Advance 100ms -> 2nd tick
    await vi.advanceTimersByTimeAsync(100);
    expect(onStep).toHaveBeenCalledTimes(2);

    // Advance 200ms -> 3rd and 4th ticks
    await vi.advanceTimersByTimeAsync(200);
    expect(onStep).toHaveBeenCalledTimes(4);

    scheduler.pause();
    expect(onStateChange).toHaveBeenCalledWith("paused");
    expect(scheduler.getState()).toBe("paused");

    // Advance while paused -> no further calls
    await vi.advanceTimersByTimeAsync(500);
    expect(onStep).toHaveBeenCalledTimes(4);

    scheduler.dispose();
  });

  it("prevents overlapping step requests during playback", async () => {
    let resolveStep: (val: boolean) => void = () => {};
    const slowStep = vi.fn().mockImplementation(() => {
      return new Promise<boolean>((resolve) => {
        resolveStep = resolve;
      });
    });

    const scheduler = new PlaybackScheduler(
      { onStep: slowStep, onStateChange: vi.fn() },
      { speed: 1, timeStepS: 0.1 }
    );

    scheduler.play();
    await vi.advanceTimersByTimeAsync(1);
    expect(slowStep).toHaveBeenCalledTimes(1);

    // Advance timer while request is still pending
    await vi.advanceTimersByTimeAsync(200);
    expect(slowStep).toHaveBeenCalledTimes(1); // not called again!

    // Resolve the slow step
    resolveStep(true);
    await vi.advanceTimersByTimeAsync(100);
    expect(slowStep).toHaveBeenCalledTimes(2); // resumed safely

    scheduler.dispose();
  });

  it("stops playback when onStep returns false (terminal run)", async () => {
    const onStep = vi
      .fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false); // becomes terminal on 2nd tick

    const onStateChange = vi.fn();
    const scheduler = new PlaybackScheduler({ onStep, onStateChange }, { speed: 1, timeStepS: 0.1 });

    scheduler.play();
    await vi.advanceTimersByTimeAsync(1);
    expect(onStep).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(100);
    expect(onStep).toHaveBeenCalledTimes(2);

    // Timers advanced further, but run stopped
    await vi.advanceTimersByTimeAsync(500);
    expect(onStep).toHaveBeenCalledTimes(2);

    scheduler.dispose();
  });

  it("handles manual stepping via executeManualStep", async () => {
    const onStep = vi.fn().mockResolvedValue(true);
    const onStateChange = vi.fn();
    const scheduler = new PlaybackScheduler({ onStep, onStateChange });

    const ok1 = await scheduler.executeManualStep(1);
    expect(ok1).toBe(true);
    expect(onStep).toHaveBeenCalledWith(1);
    expect(onStateChange).toHaveBeenCalledWith("stepping");
    expect(onStateChange).toHaveBeenCalledWith("paused");

    const ok10 = await scheduler.executeManualStep(10);
    expect(ok10).toBe(true);
    expect(onStep).toHaveBeenCalledWith(10);

    scheduler.dispose();
  });

  it("notifies onError when step throws an exception", async () => {
    const onStep = vi.fn().mockRejectedValue(new Error("Network timeout"));
    const onError = vi.fn();
    const scheduler = new PlaybackScheduler({ onStep, onStateChange: vi.fn(), onError });

    const ok = await scheduler.executeManualStep(1);
    expect(ok).toBe(false);
    expect(onError).toHaveBeenCalledWith("Network timeout");

    scheduler.dispose();
  });
});
