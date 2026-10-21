import { describe, expect, it } from "vitest";
import {
  EntityInterpolationBuffer,
  interpolateHeading,
  interpolatePosition,
  normalizeAngle2Pi,
  normalizeAnglePi,
  simHeadingToWorldRotationY,
} from "../features/scene3d/interpolation";

describe("Temporal Interpolation & Coordinate Utilities", () => {
  describe("normalizeAngle2Pi", () => {
    it("normalizes negative angles to [0, 2*PI)", () => {
      expect(normalizeAngle2Pi(-Math.PI / 2)).toBeCloseTo(1.5 * Math.PI, 5);
      expect(normalizeAngle2Pi(-2 * Math.PI)).toBeCloseTo(0, 5);
    });

    it("normalizes angles greater than 2*PI", () => {
      expect(normalizeAngle2Pi(2.5 * Math.PI)).toBeCloseTo(0.5 * Math.PI, 5);
    });

    it("handles non-finite values safely", () => {
      expect(normalizeAngle2Pi(NaN)).toBe(0);
      expect(normalizeAngle2Pi(Infinity)).toBe(0);
    });
  });

  describe("normalizeAnglePi", () => {
    it("normalizes angles to (-PI, PI]", () => {
      expect(normalizeAnglePi(1.5 * Math.PI)).toBeCloseTo(-0.5 * Math.PI, 5);
      expect(normalizeAnglePi(Math.PI)).toBeCloseTo(Math.PI, 5);
      expect(normalizeAnglePi(0)).toBeCloseTo(0, 5);
    });
  });

  describe("interpolateHeading", () => {
    it("interpolates monotonically within the standard quadrant", () => {
      const h0 = 0.2;
      const h1 = 0.8;
      expect(interpolateHeading(h0, h1, 0.0)).toBeCloseTo(0.2, 5);
      expect(interpolateHeading(h0, h1, 0.5)).toBeCloseTo(0.5, 5);
      expect(interpolateHeading(h0, h1, 1.0)).toBeCloseTo(0.8, 5);
    });

    it("chooses the shortest angular path across the 0 <-> 2*PI boundary (no 360 spin)", () => {
      // 0.1 rad to 6.2 rad (near 2*PI - 0.08)
      // The shortest path crosses 0.0, going counter-clockwise (or clockwise in Euclidean)
      const h0 = 0.1;
      const h1 = 2 * Math.PI - 0.1; // ~6.183 rad

      // Midway should be approximately 0.0 (or 2*PI)
      const midway = interpolateHeading(h0, h1, 0.5);
      expect(midway).toBeCloseTo(0.0, 3);

      // A quarter way from h0 towards h1 through 0: should be 0.05
      const quarter = interpolateHeading(h0, h1, 0.25);
      expect(quarter).toBeCloseTo(0.05, 3);
    });

    it("handles reverse wraparound from near 2*PI to small positive angle", () => {
      const h0 = 2 * Math.PI - 0.1;
      const h1 = 0.1;

      const midway = interpolateHeading(h0, h1, 0.5);
      expect(midway).toBeCloseTo(0.0, 3);
    });

    it("clamps alpha strictly to [0, 1]", () => {
      const h0 = 1.0;
      const h1 = 2.0;
      expect(interpolateHeading(h0, h1, -0.5)).toBeCloseTo(1.0, 5);
      expect(interpolateHeading(h0, h1, 1.5)).toBeCloseTo(2.0, 5);
    });
  });

  describe("interpolatePosition", () => {
    it("linearly interpolates 2D planar positions", () => {
      const p0 = { x: 10, y: 20 };
      const p1 = { x: 30, y: 40 };

      expect(interpolatePosition(p0, p1, 0.0)).toEqual({ x: 10, y: 20 });
      expect(interpolatePosition(p0, p1, 0.5)).toEqual({ x: 20, y: 30 });
      expect(interpolatePosition(p0, p1, 1.0)).toEqual({ x: 30, y: 40 });
    });

    it("clamps alpha to [0, 1]", () => {
      const p0 = { x: 0, y: 0 };
      const p1 = { x: 100, y: 100 };

      expect(interpolatePosition(p0, p1, -1.0)).toEqual({ x: 0, y: 0 });
      expect(interpolatePosition(p0, p1, 2.0)).toEqual({ x: 100, y: 100 });
    });
  });

  describe("simHeadingToWorldRotationY", () => {
    it("aligns cardinal simulation directions with Three.js world axes", () => {
      // Heading 0: moving East along +X_sim -> +X_world -> rotationY = PI/2
      expect(simHeadingToWorldRotationY(0)).toBeCloseTo(Math.PI / 2, 5);

      // Heading PI/2: moving North along +Y_sim -> -Z_world -> rotationY = PI
      expect(Math.abs(simHeadingToWorldRotationY(Math.PI / 2))).toBeCloseTo(Math.PI, 5);

      // Heading PI: moving West along -X_sim -> -X_world -> rotationY = -PI/2
      expect(simHeadingToWorldRotationY(Math.PI)).toBeCloseTo(-Math.PI / 2, 5);

      // Heading 3*PI/2: moving South along -Y_sim -> +Z_world -> rotationY = 0
      expect(simHeadingToWorldRotationY(1.5 * Math.PI)).toBeCloseTo(0, 5);
    });

    it("handles non-finite headings gracefully", () => {
      expect(simHeadingToWorldRotationY(NaN)).toBe(0);
    });
  });
});

describe("EntityInterpolationBuffer", () => {
  it("stores samples and rejects malformed coordinates", () => {
    const buffer = new EntityInterpolationBuffer({ maxSamples: 5 });

    const accepted = buffer.pushSample("veh_1", {
      position: { x: 10, y: 20 },
      tick: 0,
      timestamp_s: 0.0,
      speed_mps: 5.0,
      heading_rad: 1.2,
    });
    expect(accepted).toBe(true);
    expect(buffer.getSampleCount("veh_1")).toBe(1);

    // Malformed coordinates rejected
    const rejectedNan = buffer.pushSample("veh_1", {
      position: { x: NaN, y: 20 },
      tick: 1,
      timestamp_s: 0.1,
    });
    expect(rejectedNan).toBe(false);

    const rejectedNull = buffer.pushSample("veh_1", {
      position: null as unknown as { x: number; y: number },
      tick: 1,
      timestamp_s: 0.1,
    });
    expect(rejectedNull).toBe(false);
    expect(buffer.getSampleCount("veh_1")).toBe(1);
  });

  it("derives heading from displacement when heading is not provided", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", {
      position: { x: 0, y: 0 },
      tick: 0,
      timestamp_s: 0.0,
    });

    // Move North along +Y: dy = 10, dx = 0 -> heading should be PI/2
    buffer.pushSample("veh_1", {
      position: { x: 0, y: 10 },
      tick: 1,
      timestamp_s: 0.1,
    });

    const latest = buffer.getLatestSample("veh_1");
    expect(latest?.heading_rad).toBeCloseTo(Math.PI / 2, 4);
  });

  it("preserves previous heading on zero displacement when heading is omitted", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", {
      position: { x: 10, y: 10 },
      tick: 0,
      timestamp_s: 0.0,
      heading_rad: 2.5,
    });

    // Zero displacement
    buffer.pushSample("veh_1", {
      position: { x: 10, y: 10 },
      tick: 1,
      timestamp_s: 0.1,
    });

    const latest = buffer.getLatestSample("veh_1");
    expect(latest?.heading_rad).toBeCloseTo(2.5, 4);
  });

  it("handles duplicate timestamps and ticks by updating in-place", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", {
      position: { x: 10, y: 20 },
      tick: 5,
      timestamp_s: 0.5,
      speed_mps: 4.0,
    });
    expect(buffer.getSampleCount("veh_1")).toBe(1);

    // Duplicate event
    buffer.pushSample("veh_1", {
      position: { x: 10, y: 20 },
      tick: 5,
      timestamp_s: 0.5,
      speed_mps: 4.5,
      lifecycle_state: "en_route",
    });
    expect(buffer.getSampleCount("veh_1")).toBe(1);

    const latest = buffer.getLatestSample("veh_1");
    expect(latest?.speed_mps).toBe(4.5);
    expect(latest?.lifecycle_state).toBe("en_route");
  });

  it("maintains sorted order for out-of-order events within the window", () => {
    const buffer = new EntityInterpolationBuffer({ maxSamples: 10 });

    buffer.pushSample("veh_1", { position: { x: 0, y: 0 }, tick: 0, timestamp_s: 0.0 });
    buffer.pushSample("veh_1", { position: { x: 20, y: 0 }, tick: 2, timestamp_s: 0.2 });

    // Out-of-order sample at 0.1
    buffer.pushSample("veh_1", { position: { x: 10, y: 0 }, tick: 1, timestamp_s: 0.1 });
    expect(buffer.getSampleCount("veh_1")).toBe(3);

    const state = buffer.getInterpolatedState("veh_1", 0.1);
    expect(state?.position.x).toBeCloseTo(10, 4);
  });

  it("discards expired out-of-order samples when buffer is full", () => {
    const buffer = new EntityInterpolationBuffer({ maxSamples: 3 });

    buffer.pushSample("veh_1", { position: { x: 1, y: 0 }, tick: 1, timestamp_s: 0.1 });
    buffer.pushSample("veh_1", { position: { x: 2, y: 0 }, tick: 2, timestamp_s: 0.2 });
    buffer.pushSample("veh_1", { position: { x: 3, y: 0 }, tick: 3, timestamp_s: 0.3 });
    expect(buffer.getSampleCount("veh_1")).toBe(3);

    // Sample older than oldest retained history (0.1) when full
    const accepted = buffer.pushSample("veh_1", { position: { x: 0, y: 0 }, tick: 0, timestamp_s: 0.05 });
    expect(accepted).toBe(false);
    expect(buffer.getSampleCount("veh_1")).toBe(3);
  });

  it("enforces bounded history size without memory leaks", () => {
    const buffer = new EntityInterpolationBuffer({ maxSamples: 4 });

    for (let i = 0; i < 15; i++) {
      buffer.pushSample("veh_1", {
        position: { x: i * 10, y: 0 },
        tick: i,
        timestamp_s: i * 0.1,
      });
    }

    expect(buffer.getSampleCount("veh_1")).toBe(4);
    // Oldest sample should be tick 11
    const oldest = buffer.getInterpolatedState("veh_1", 0.0);
    expect(oldest?.latest_tick).toBe(14);
    expect(oldest?.position.x).toBeCloseTo(110, 1); // clamped to earliest retained
  });

  it("interpolates accurately between sample boundaries", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", {
      position: { x: 0, y: 0 },
      tick: 0,
      timestamp_s: 0.0,
      heading_rad: 0.0,
      speed_mps: 10.0,
    });

    buffer.pushSample("veh_1", {
      position: { x: 100, y: 50 },
      tick: 1,
      timestamp_s: 1.0,
      heading_rad: 1.0,
      speed_mps: 20.0,
    });

    // Exact at t = 0.0
    const s0 = buffer.getInterpolatedState("veh_1", 0.0);
    expect(s0?.position).toEqual({ x: 0, y: 0 });
    expect(s0?.speed_mps).toBe(10.0);

    // Exact at t = 1.0
    const s1 = buffer.getInterpolatedState("veh_1", 1.0);
    expect(s1?.position).toEqual({ x: 100, y: 50 });
    expect(s1?.speed_mps).toBe(20.0);

    // Midway at t = 0.5
    const mid = buffer.getInterpolatedState("veh_1", 0.5);
    expect(mid?.position.x).toBeCloseTo(50, 4);
    expect(mid?.position.y).toBeCloseTo(25, 4);
    expect(mid?.speed_mps).toBeCloseTo(15.0, 4);
    expect(mid?.heading_rad).toBeCloseTo(0.5, 4);
  });

  it("clamps and bounds extrapolation when updates pause", () => {
    const buffer = new EntityInterpolationBuffer({ maxExtrapolationS: 0.15 });

    buffer.pushSample("veh_1", {
      position: { x: 0, y: 0 },
      tick: 0,
      timestamp_s: 0.0,
      heading_rad: 0.0, // Moving East (+X)
      speed_mps: 10.0,
    });
    buffer.pushSample("veh_1", {
      position: { x: 10, y: 0 },
      tick: 1,
      timestamp_s: 1.0,
      heading_rad: 0.0,
      speed_mps: 10.0,
    });

    // 0.1s past latest sample: extrapolates 0.1s * 10 m/s = 1.0m
    const ext1 = buffer.getInterpolatedState("veh_1", 1.1);
    expect(ext1?.position.x).toBeCloseTo(11.0, 2);

    // 1.0s past latest sample: extrapolation is bounded to maxExtrapolationS (0.15s) -> max 1.5m
    const extLong = buffer.getInterpolatedState("veh_1", 2.0);
    expect(extLong?.position.x).toBeCloseTo(11.5, 2);
    // Extrapolation NEVER grows indefinitely!
    const extVeryLong = buffer.getInterpolatedState("veh_1", 100.0);
    expect(extVeryLong?.position.x).toBeCloseTo(11.5, 2);
  });

  it("detects stale entity data based on configurable threshold", () => {
    const buffer = new EntityInterpolationBuffer({ staleThresholdS: 2.0 });

    buffer.pushSample("veh_1", {
      position: { x: 0, y: 0 },
      tick: 1,
      timestamp_s: 1.0,
    });

    // Render time 2.5s (1.5s delta < 2.0s threshold) -> not stale
    const fresh = buffer.getInterpolatedState("veh_1", 2.5);
    expect(fresh?.is_stale).toBe(false);

    // Render time 3.5s (2.5s delta > 2.0s threshold) -> stale
    const stale = buffer.getInterpolatedState("veh_1", 3.5);
    expect(stale?.is_stale).toBe(true);
  });

  it("supports getInterpolatedStateAtAlpha for tick-interval rendering", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", { position: { x: 10, y: 0 }, tick: 1, timestamp_s: 0.1 });
    buffer.pushSample("veh_1", { position: { x: 20, y: 0 }, tick: 2, timestamp_s: 0.2 });

    const state = buffer.getInterpolatedStateAtAlpha("veh_1", 0.7);
    expect(state?.position.x).toBeCloseTo(17.0, 4);
  });

  it("resets cleanly on clear and entity removal", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_1", { position: { x: 10, y: 0 }, tick: 1, timestamp_s: 0.1 });
    buffer.pushSample("veh_2", { position: { x: 20, y: 0 }, tick: 1, timestamp_s: 0.1 });

    expect(buffer.getActiveEntityIds()).toEqual(["veh_1", "veh_2"]);

    buffer.removeEntity("veh_1");
    expect(buffer.hasEntity("veh_1")).toBe(false);
    expect(buffer.hasEntity("veh_2")).toBe(true);

    buffer.clear();
    expect(buffer.getActiveEntityIds()).toEqual([]);
    expect(buffer.getInterpolatedState("veh_2", 0.1)).toBeNull();
  });

  it("cleans up stale entities older than maxAgeS", () => {
    const buffer = new EntityInterpolationBuffer();

    buffer.pushSample("veh_old", { position: { x: 0, y: 0 }, tick: 1, timestamp_s: 1.0 });
    buffer.pushSample("veh_new", { position: { x: 0, y: 0 }, tick: 10, timestamp_s: 10.0 });

    const removed = buffer.cleanupStaleEntities(12.0, 5.0);
    expect(removed).toEqual(["veh_old"]);
    expect(buffer.hasEntity("veh_old")).toBe(false);
    expect(buffer.hasEntity("veh_new")).toBe(true);
  });
});
