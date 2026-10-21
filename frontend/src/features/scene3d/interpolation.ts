/**
 * Temporal Interpolation Engine for AMAPP Simulation Viewer.
 *
 * Provides deterministic, bounded temporal state buffering, linear planar position interpolation,
 * shortest-path angular heading interpolation, duplicate/out-of-order rejection,
 * and stale-entity detection. Decoupled from Three.js and React rendering for testability.
 */

import { simToWorldCoordinates } from "./geometry";

export interface Position2D {
  x: number;
  y: number;
}

export interface EntitySample {
  timestamp_s: number;
  tick: number;
  position: Position2D;
  heading_rad: number;
  speed_mps: number;
  lifecycle_state?: string;
  is_emergency?: boolean;
  vehicle_type?: string;
  route?: string[];
  current_edge_id?: string;
}

export interface InterpolatedEntityState {
  entity_id: string;
  position: Position2D;
  world_position: { x: number; y: number; z: number };
  heading_rad: number;
  rotation_y: number;
  speed_mps: number;
  lifecycle_state: string;
  is_emergency: boolean;
  vehicle_type?: string;
  route?: string[];
  is_stale: boolean;
  latest_tick: number;
  latest_timestamp_s: number;
  sample_count: number;
}

/**
 * Normalizes an angle in radians to the [0, 2*PI) interval.
 */
export function normalizeAngle2Pi(angleRad: number): number {
  if (!Number.isFinite(angleRad)) return 0;
  const twoPi = 2 * Math.PI;
  return ((angleRad % twoPi) + twoPi) % twoPi;
}

/**
 * Normalizes an angle in radians to the (-PI, PI] interval.
 */
export function normalizeAnglePi(angleRad: number): number {
  if (!Number.isFinite(angleRad)) return 0;
  let a = (angleRad + Math.PI) % (2 * Math.PI);
  if (a < 0) a += 2 * Math.PI;
  const res = a - Math.PI;
  if (Math.abs(res + Math.PI) < 1e-12) return Math.PI;
  return res;
}

/**
 * Interpolates heading angle using the shortest angular path to prevent full 360-degree rotations.
 * Handles wraparound smoothly across the 0 <-> 2*PI boundary.
 *
 * @param h0 Starting heading in radians
 * @param h1 Target heading in radians
 * @param alpha Interpolation fraction [0, 1]
 * @returns Shortest-path interpolated angle in [0, 2*PI)
 */
export function interpolateHeading(h0: number, h1: number, alpha: number): number {
  const clampedAlpha = Math.max(0, Math.min(1, alpha));
  const twoPi = 2 * Math.PI;
  // Calculate shortest angular difference in (-PI, PI]
  const diff = ((h1 - h0 + Math.PI) % twoPi + twoPi) % twoPi - Math.PI;
  const interpolated = h0 + clampedAlpha * diff;
  return normalizeAngle2Pi(interpolated);
}

/**
 * Linearly interpolates a 2D planar position between two samples.
 */
export function interpolatePosition(
  p0: Position2D,
  p1: Position2D,
  alpha: number
): Position2D {
  const clampedAlpha = Math.max(0, Math.min(1, alpha));
  return {
    x: p0.x + clampedAlpha * (p1.x - p0.x),
    y: p0.y + clampedAlpha * (p1.y - p0.y),
  };
}

/**
 * Converts a simulation heading (radians [0, 2*PI), where 0 is East along +X and PI/2 is North along +Y)
 * to Three.js world rotation around the Y axis (where Three.js world has X=East, Y=Up, Z=-Y_sim=South).
 * Forward orientation aligns with the vehicle's movement vector.
 */
export function simHeadingToWorldRotationY(headingRad: number): number {
  if (!Number.isFinite(headingRad)) return 0;
  const dx = Math.cos(headingRad);
  const dz = -Math.sin(headingRad);
  return Math.atan2(dx, dz);
}

export interface EntityInterpolationBufferOptions {
  maxSamples?: number;
  defaultTimeStepS?: number;
  staleThresholdS?: number;
  maxExtrapolationS?: number;
}

/**
 * Manages bounded historical telemetry samples for dynamic simulation entities (vehicles and pedestrians)
 * and evaluates deterministic temporal interpolation for smooth presentation rendering.
 */
export class EntityInterpolationBuffer {
  private readonly maxSamples: number;
  private readonly defaultTimeStepS: number;
  private readonly staleThresholdS: number;
  private readonly maxExtrapolationS: number;
  private readonly sampleBuffers = new Map<string, EntitySample[]>();

  constructor(options: EntityInterpolationBufferOptions = {}) {
    this.maxSamples = Math.max(2, options.maxSamples ?? 10);
    this.defaultTimeStepS = options.defaultTimeStepS ?? 0.1;
    this.staleThresholdS = options.staleThresholdS ?? 5.0;
    this.maxExtrapolationS = options.maxExtrapolationS ?? 0.15;
  }

  /**
   * Pushes a new sample for the specified entity.
   * Validates coordinates, handles duplicates, maintains sorted order, and bounds buffer size.
   *
   * @returns true if the sample was accepted, false if rejected as malformed or expired.
   */
  public pushSample(
    entityId: string,
    sample: {
      position: Position2D;
      timestamp_s?: number;
      tick?: number;
      heading_rad?: number;
      speed_mps?: number;
      lifecycle_state?: string;
      is_emergency?: boolean;
      vehicle_type?: string;
      route?: string[];
      current_edge_id?: string;
    }
  ): boolean {
    if (!entityId || typeof entityId !== "string") return false;
    if (
      !sample.position ||
      !Number.isFinite(sample.position.x) ||
      !Number.isFinite(sample.position.y)
    ) {
      return false; // Malformed coordinates rejected
    }

    let buffer = this.sampleBuffers.get(entityId);
    if (!buffer) {
      buffer = [];
      this.sampleBuffers.set(entityId, buffer);
    }

    const prevSample = buffer.length > 0 ? buffer[buffer.length - 1] : null;

    // Determine tick and timestamp
    const tick = Number.isFinite(sample.tick) ? Number(sample.tick) : (prevSample ? prevSample.tick + 1 : 0);
    let timestamp_s: number;
    if (Number.isFinite(sample.timestamp_s)) {
      timestamp_s = Number(sample.timestamp_s);
    } else if (Number.isFinite(sample.tick)) {
      timestamp_s = Number(sample.tick) * this.defaultTimeStepS;
    } else if (prevSample) {
      timestamp_s = prevSample.timestamp_s + this.defaultTimeStepS;
    } else {
      timestamp_s = 0.0;
    }

    // Determine heading: use provided heading, or derive from displacement if meaningful
    let heading_rad: number;
    if (Number.isFinite(sample.heading_rad)) {
      heading_rad = normalizeAngle2Pi(Number(sample.heading_rad));
    } else if (prevSample) {
      const dx = sample.position.x - prevSample.position.x;
      const dy = sample.position.y - prevSample.position.y;
      if (Math.hypot(dx, dy) > 1e-4) {
        heading_rad = normalizeAngle2Pi(Math.atan2(dy, dx));
      } else {
        heading_rad = prevSample.heading_rad;
      }
    } else {
      heading_rad = 0;
    }

    const speed_mps = Number.isFinite(sample.speed_mps) && Number(sample.speed_mps) >= 0
      ? Number(sample.speed_mps)
      : (prevSample ? prevSample.speed_mps : 0);

    const validSample: EntitySample = {
      timestamp_s,
      tick,
      position: { x: sample.position.x, y: sample.position.y },
      heading_rad,
      speed_mps,
      lifecycle_state: sample.lifecycle_state ?? prevSample?.lifecycle_state,
      is_emergency: sample.is_emergency ?? prevSample?.is_emergency,
      vehicle_type: sample.vehicle_type ?? prevSample?.vehicle_type,
      route: sample.route ?? prevSample?.route,
      current_edge_id: sample.current_edge_id ?? prevSample?.current_edge_id,
    };

    // 1. Check for duplicate sample with same timestamp or tick
    const exactMatchIndex = buffer.findIndex(
      (s) => Math.abs(s.timestamp_s - timestamp_s) < 1e-6 || s.tick === tick
    );
    if (exactMatchIndex >= 0) {
      // Duplicate: update in-place with fresher metadata without creating duplicate entries
      buffer[exactMatchIndex] = {
        ...buffer[exactMatchIndex],
        ...validSample,
      };
      return true;
    }

    // 2. Check out-of-order sample
    if (buffer.length > 0 && timestamp_s < buffer[0].timestamp_s) {
      if (buffer.length >= this.maxSamples) {
        // Sample is older than the oldest retained history and buffer is full; discard
        return false;
      }
      // Insert in sorted order
      buffer.unshift(validSample);
      return true;
    }

    // Find insertion index to maintain strictly ascending timestamp order
    let insertIdx = buffer.length;
    for (let i = buffer.length - 1; i >= 0; i--) {
      if (timestamp_s > buffer[i].timestamp_s) {
        insertIdx = i + 1;
        break;
      } else {
        insertIdx = i;
      }
    }

    buffer.splice(insertIdx, 0, validSample);

    // 3. Enforce bounded history size
    while (buffer.length > this.maxSamples) {
      buffer.shift();
    }

    return true;
  }

  /**
   * Retrieves the interpolated state for an entity at the specified render time in seconds.
   * If renderTime_s is before the first sample, clamps to the first sample.
   * If renderTime_s is between two samples, linearly interpolates position and speed, and shortest-path lerps heading.
   * If renderTime_s is past the latest sample, applies bounded visual extrapolation up to maxExtrapolationS, then clamps.
   */
  public getInterpolatedState(
    entityId: string,
    renderTimeS: number,
    elevation = 0.5
  ): InterpolatedEntityState | null {
    const buffer = this.sampleBuffers.get(entityId);
    if (!buffer || buffer.length === 0) return null;

    const latest = buffer[buffer.length - 1];
    const isStale = (renderTimeS - latest.timestamp_s) > this.staleThresholdS;

    if (buffer.length === 1) {
      const worldPos = simToWorldCoordinates(latest.position.x, latest.position.y, elevation);
      return {
        entity_id: entityId,
        position: { ...latest.position },
        world_position: worldPos,
        heading_rad: latest.heading_rad,
        rotation_y: simHeadingToWorldRotationY(latest.heading_rad),
        speed_mps: latest.speed_mps,
        lifecycle_state: latest.lifecycle_state ?? "en_route",
        is_emergency: !!latest.is_emergency,
        vehicle_type: latest.vehicle_type,
        route: latest.route,
        is_stale: isStale,
        latest_tick: latest.tick,
        latest_timestamp_s: latest.timestamp_s,
        sample_count: 1,
      };
    }

    // Boundary: before first sample
    if (renderTimeS <= buffer[0].timestamp_s) {
      const first = buffer[0];
      const worldPos = simToWorldCoordinates(first.position.x, first.position.y, elevation);
      return {
        entity_id: entityId,
        position: { ...first.position },
        world_position: worldPos,
        heading_rad: first.heading_rad,
        rotation_y: simHeadingToWorldRotationY(first.heading_rad),
        speed_mps: first.speed_mps,
        lifecycle_state: first.lifecycle_state ?? "en_route",
        is_emergency: !!first.is_emergency,
        vehicle_type: first.vehicle_type,
        route: first.route,
        is_stale: isStale,
        latest_tick: latest.tick,
        latest_timestamp_s: latest.timestamp_s,
        sample_count: buffer.length,
      };
    }

    // Boundary: past latest sample (hold or short bounded extrapolation)
    if (renderTimeS >= latest.timestamp_s) {
      const dtAhead = Math.min(this.maxExtrapolationS, renderTimeS - latest.timestamp_s);
      let posX = latest.position.x;
      let posY = latest.position.y;
      if (dtAhead > 0 && latest.speed_mps > 0.01) {
        posX += Math.cos(latest.heading_rad) * latest.speed_mps * dtAhead;
        posY += Math.sin(latest.heading_rad) * latest.speed_mps * dtAhead;
      }
      const worldPos = simToWorldCoordinates(posX, posY, elevation);
      return {
        entity_id: entityId,
        position: { x: posX, y: posY },
        world_position: worldPos,
        heading_rad: latest.heading_rad,
        rotation_y: simHeadingToWorldRotationY(latest.heading_rad),
        speed_mps: latest.speed_mps,
        lifecycle_state: latest.lifecycle_state ?? "en_route",
        is_emergency: !!latest.is_emergency,
        vehicle_type: latest.vehicle_type,
        route: latest.route,
        is_stale: isStale,
        latest_tick: latest.tick,
        latest_timestamp_s: latest.timestamp_s,
        sample_count: buffer.length,
      };
    }

    // Find bounding pair
    let s0 = buffer[0];
    let s1 = buffer[1];
    for (let i = 0; i < buffer.length - 1; i++) {
      if (buffer[i].timestamp_s <= renderTimeS && renderTimeS <= buffer[i + 1].timestamp_s) {
        s0 = buffer[i];
        s1 = buffer[i + 1];
        break;
      }
    }

    const dt = s1.timestamp_s - s0.timestamp_s;
    const alpha = dt > 1e-6 ? (renderTimeS - s0.timestamp_s) / dt : 1.0;

    const interpolatedPos = interpolatePosition(s0.position, s1.position, alpha);
    const interpolatedHeading = interpolateHeading(s0.heading_rad, s1.heading_rad, alpha);
    const interpolatedSpeed = s0.speed_mps + alpha * (s1.speed_mps - s0.speed_mps);
    const worldPos = simToWorldCoordinates(interpolatedPos.x, interpolatedPos.y, elevation);

    return {
      entity_id: entityId,
      position: interpolatedPos,
      world_position: worldPos,
      heading_rad: interpolatedHeading,
      rotation_y: simHeadingToWorldRotationY(interpolatedHeading),
      speed_mps: interpolatedSpeed,
      lifecycle_state: s1.lifecycle_state ?? s0.lifecycle_state ?? "en_route",
      is_emergency: !!(s1.is_emergency ?? s0.is_emergency),
      vehicle_type: s1.vehicle_type ?? s0.vehicle_type,
      route: s1.route ?? s0.route,
      is_stale: isStale,
      latest_tick: latest.tick,
      latest_timestamp_s: latest.timestamp_s,
      sample_count: buffer.length,
    };
  }

  /**
   * Interpolates an entity between its penultimate and latest samples by an explicit fraction [0, 1].
   * Useful when rendering frames synchronized to tick progress intervals.
   */
  public getInterpolatedStateAtAlpha(
    entityId: string,
    alpha: number,
    elevation = 0.5
  ): InterpolatedEntityState | null {
    const buffer = this.sampleBuffers.get(entityId);
    if (!buffer || buffer.length === 0) return null;

    const latest = buffer[buffer.length - 1];
    if (buffer.length === 1) {
      return this.getInterpolatedState(entityId, latest.timestamp_s, elevation);
    }

    const prev = buffer[buffer.length - 2];
    const clampedAlpha = Math.max(0, Math.min(1, alpha));
    const targetTime = prev.timestamp_s + clampedAlpha * (latest.timestamp_s - prev.timestamp_s);
    return this.getInterpolatedState(entityId, targetTime, elevation);
  }

  public getLatestSample(entityId: string): EntitySample | null {
    const buffer = this.sampleBuffers.get(entityId);
    if (!buffer || buffer.length === 0) return null;
    return buffer[buffer.length - 1];
  }

  public getSampleCount(entityId: string): number {
    return this.sampleBuffers.get(entityId)?.length ?? 0;
  }

  public hasEntity(entityId: string): boolean {
    return this.sampleBuffers.has(entityId);
  }

  public removeEntity(entityId: string): void {
    this.sampleBuffers.delete(entityId);
  }

  public getActiveEntityIds(): string[] {
    return Array.from(this.sampleBuffers.keys());
  }

  /**
   * Cleans up entities that have not received an update in more than maxAgeS relative to currentTimeS.
   * Returns array of removed entity IDs.
   */
  public cleanupStaleEntities(currentTimeS: number, maxAgeS = 10.0): string[] {
    const removed: string[] = [];
    for (const [id, buffer] of this.sampleBuffers.entries()) {
      if (buffer.length > 0) {
        const latest = buffer[buffer.length - 1];
        if (currentTimeS - latest.timestamp_s > maxAgeS) {
          this.sampleBuffers.delete(id);
          removed.push(id);
        }
      } else {
        this.sampleBuffers.delete(id);
        removed.push(id);
      }
    }
    return removed;
  }

  /**
   * Resets all entity histories. Must be invoked when switching runs or scenarios.
   */
  public clear(): void {
    this.sampleBuffers.clear();
  }
}
