/**
 * Coordinate transformations, road network geometry construction,
 * multi-lane markings, crosswalks, sidewalks/curbs, and deterministic procedural urban buildings.
 * Maps simulation planar coordinates (meters) to Three.js 3D world space (X=East, Y=Up, Z=South).
 */

import type {
  BuildingGeneratorOptions,
  LaneMarkingSegment,
  Point3D,
  ProceduralBuilding,
  RoadEdgeGeometry,
  RoadNetworkGeometry,
  RoadNodeGeometry,
  SidewalkSegmentGeometry,
  ZebraStripeGeometry,
} from "../../types/graph";
import type { GridConfig, ScenarioDefinition } from "../../types/simulation";

export type { Point3D };

/**
 * Standard 3D coordinate mapping for AMAPP:
 * Planar simulation space (x, y in meters) maps to Three.js world space:
 * - 3D X = sim x (East/West)
 * - 3D Y = elevation (Up, default 0 for ground)
 * - 3D Z = -sim y (North/South inverted for standard screen-space forward)
 */
export function simToWorldCoordinates(
  simX: number,
  simY: number,
  elevation = 0
): Point3D {
  if (!Number.isFinite(simX) || !Number.isFinite(simY)) {
    return { x: 0, y: Number.isFinite(elevation) ? Number(elevation) : 0, z: 0 };
  }
  return {
    x: Number(simX),
    y: Number.isFinite(elevation) ? Number(elevation) : 0,
    z: -Number(simY),
  };
}

/**
 * Computes road surface width in meters from edge attributes or lane count.
 * Fallback to standard 8.0m for two-lane equivalent.
 */
export function computeRoadEdgeWidth(
  edge: RoadEdgeGeometry,
  laneWidthM = 3.75,
  defaultWidthM = 8.0
): number {
  if (edge.attributes && typeof edge.attributes.width_m === "number" && edge.attributes.width_m > 0) {
    return Math.max(3.0, edge.attributes.width_m);
  }
  const lanes = Math.max(1, edge.lanes || 1);
  if (lanes > 1) {
    return Math.max(defaultWidthM, lanes * laneWidthM);
  }
  return defaultWidthM;
}

/**
 * Generates deterministic road network geometry from synthetic grid config.
 * Produces identical node IDs and positions as backend apps.core.graph.generator.generate_city_grid.
 */
export function generateSyntheticGridGeometry(
  config?: GridConfig | null
): RoadNetworkGeometry {
  const rows = Math.max(2, config?.rows ?? 3);
  const cols = Math.max(2, config?.cols ?? 3);
  const spacingM = Math.max(10, config?.spacing_m ?? 100);
  const speedLimit = config?.speed_limit_mps ?? 13.89;
  const lanes = Math.max(1, config?.lanes ?? 1);
  const bidirectional = config?.bidirectional ?? true;

  const nodes: RoadNodeGeometry[] = [];
  const edges: RoadEdgeGeometry[] = [];

  // 1. Nodes
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      nodes.push({
        id: `node_r${r}_c${c}`,
        x: c * spacingM,
        y: r * spacingM,
        attributes: {
          row: r,
          col: c,
          is_boundary: r === 0 || r === rows - 1 || c === 0 || c === cols - 1,
        },
      });
    }
  }

  // 2. Horizontal Edges (East/West)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const eastId = `edge_r${r}_c${c}_to_r${r}_c${c + 1}`;
      edges.push({
        id: eastId,
        start_node_id: `node_r${r}_c${c}`,
        end_node_id: `node_r${r}_c${c + 1}`,
        length_m: spacingM,
        speed_limit_mps: speedLimit,
        lanes,
        attributes: { direction: "east", row: r, one_way: !bidirectional },
      });

      if (bidirectional) {
        const westId = `edge_r${r}_c${c + 1}_to_r${r}_c${c}`;
        edges.push({
          id: westId,
          start_node_id: `node_r${r}_c${c + 1}`,
          end_node_id: `node_r${r}_c${c}`,
          length_m: spacingM,
          speed_limit_mps: speedLimit,
          lanes,
          attributes: { direction: "west", row: r, one_way: false },
        });
      }
    }
  }

  // 3. Vertical Edges (North/South)
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols; c++) {
      const northId = `edge_r${r}_c${c}_to_r${r + 1}_c${c}`;
      edges.push({
        id: northId,
        start_node_id: `node_r${r}_c${c}`,
        end_node_id: `node_r${r + 1}_c${c}`,
        length_m: spacingM,
        speed_limit_mps: speedLimit,
        lanes,
        attributes: { direction: "north", col: c, one_way: !bidirectional },
      });

      if (bidirectional) {
        const southId = `edge_r${r + 1}_c${c}_to_r${r}_c${c}`;
        edges.push({
          id: southId,
          start_node_id: `node_r${r + 1}_c${c}`,
          end_node_id: `node_r${r}_c${c}`,
          length_m: spacingM,
          speed_limit_mps: speedLimit,
          lanes,
          attributes: { direction: "south", col: c, one_way: false },
        });
      }
    }
  }

  return { nodes, edges };
}

/**
 * Deterministic Equirectangular geographic to local Cartesian projection.
 * Projects (longitude, latitude) degrees into metric planar (X, Y) relative to origin.
 */
export function projectGeoCoordinatesToLocalMeters(
  coords: { id: string; lon: number; lat: number }[]
): Map<string, { x: number; y: number }> {
  const result = new Map<string, { x: number; y: number }>();
  if (coords.length === 0) return result;

  const validCoords = coords.filter(
    (c) => Number.isFinite(c.lon) && Number.isFinite(c.lat)
  );
  if (validCoords.length === 0) return result;

  let sumLon = 0;
  let sumLat = 0;
  for (const c of validCoords) {
    sumLon += c.lon;
    sumLat += c.lat;
  }
  const originLon = sumLon / validCoords.length;
  const originLat = sumLat / validCoords.length;

  const R = 6371000; // Earth radius in meters
  const latRad = (originLat * Math.PI) / 180;
  const cosLat = Math.cos(latRad);

  for (const c of coords) {
    if (!Number.isFinite(c.lon) || !Number.isFinite(c.lat)) {
      result.set(c.id, { x: 0, y: 0 });
      continue;
    }
    const dLonRad = ((c.lon - originLon) * Math.PI) / 180;
    const dLatRad = ((c.lat - originLat) * Math.PI) / 180;
    const x = dLonRad * R * cosLat;
    const y = dLatRad * R;
    result.set(c.id, { x, y });
  }

  return result;
}

/**
 * Data adapter for OSM / GeoJSON road network payloads.
 * Supports converting raw OSM graph extracts or supplied graphs into renderable RoadNetworkGeometry.
 */
export function adaptOsmRoadNetwork(
  rawOsmData: Record<string, unknown> | null | undefined
): RoadNetworkGeometry {
  if (!rawOsmData || typeof rawOsmData !== "object") {
    return generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
  }

  const nodes: RoadNodeGeometry[] = [];
  const edges: RoadEdgeGeometry[] = [];

  // Check for explicit node list
  const rawNodes = Array.isArray(rawOsmData.nodes) ? rawOsmData.nodes : [];
  const rawEdges = Array.isArray(rawOsmData.edges) ? rawOsmData.edges : [];

  if (rawNodes.length > 0 && rawEdges.length > 0) {
    // Check if nodes use lat/lon degrees vs planar x/y meters
    const isGeo = rawNodes.some(
      (n: Record<string, unknown>) =>
        typeof n.lat === "number" &&
        typeof n.lon === "number" &&
        Math.abs(n.lat) <= 90 &&
        Math.abs(n.lon) <= 180
    );

    if (isGeo) {
      const geoCoords = rawNodes.map((n: Record<string, unknown>, idx: number) => ({
        id: String(n.id || `osm_node_${idx}`),
        lon: Number(n.lon ?? 0),
        lat: Number(n.lat ?? 0),
      }));
      const projMap = projectGeoCoordinatesToLocalMeters(geoCoords);

      for (const n of rawNodes as Record<string, unknown>[]) {
        const id = String(n.id);
        const pt = projMap.get(id) || { x: 0, y: 0 };
        nodes.push({
          id,
          x: pt.x,
          y: pt.y,
          attributes: { ...n },
        });
      }
    } else {
      for (const n of rawNodes as Record<string, unknown>[]) {
        nodes.push({
          id: String(n.id),
          x: Number(n.x ?? 0),
          y: Number(n.y ?? 0),
          attributes: { ...n },
        });
      }
    }

    for (const e of rawEdges as Record<string, unknown>[]) {
      const startId = String(e.start_node_id || e.u || "");
      const endId = String(e.end_node_id || e.v || "");
      if (!startId || !endId) continue;

      const lanes = Math.max(1, Number(e.lanes || 1));
      const speedLimit = Number(e.speed_limit_mps || 13.89);
      const length = Number(e.length_m || 50);

      edges.push({
        id: String(e.id || `${startId}_to_${endId}`),
        start_node_id: startId,
        end_node_id: endId,
        length_m: length,
        speed_limit_mps: speedLimit,
        lanes,
        attributes: {
          one_way: Boolean(e.one_way || e.oneway),
          width_m: e.width_m ? Number(e.width_m) : undefined,
          ...e,
        },
      });
    }

    if (nodes.length > 0 && edges.length > 0) {
      return { nodes, edges };
    }
  }

  // Graceful fallback to default grid if OSM payload does not contain renderable graph
  return generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
}

/**
 * Extracts or builds road network geometry from a ScenarioDefinition.
 */
export function extractRoadNetworkFromScenario(
  scenario: ScenarioDefinition | null
): RoadNetworkGeometry {
  if (!scenario) {
    return generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
  }

  const rn = scenario.road_network;
  if (rn.source_type === "synthetic_grid" && rn.grid_config) {
    return generateSyntheticGridGeometry(rn.grid_config);
  }

  if (rn.source_type === "osm_import") {
    // If scenario embeds an OSM graph data structure, adapt it
    const rawData = (rn as unknown as Record<string, unknown>).graph_data ||
      (rn as unknown as Record<string, unknown>).osm_geometry;
    if (rawData && typeof rawData === "object") {
      return adaptOsmRoadNetwork(rawData as Record<string, unknown>);
    }
    // Documented fallback when OSM graph geometry is not exposed in public REST payload
    return generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
  }

  // Fallback default grid
  return generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
}

/**
 * Computes bounding box and center point of a road network for camera positioning.
 */
export function computeNetworkBounds(geometry: RoadNetworkGeometry): {
  center: Point3D;
  size: { width: number; depth: number };
} {
  if (geometry.nodes.length === 0) {
    return {
      center: { x: 0, y: 0, z: 0 },
      size: { width: 100, depth: 100 },
    };
  }

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const node of geometry.nodes) {
    if (node.x < minX) minX = node.x;
    if (node.x > maxX) maxX = node.x;
    if (node.y < minY) minY = node.y;
    if (node.y > maxY) maxY = node.y;
  }

  const width = Math.max(10, maxX - minX);
  const depth = Math.max(10, maxY - minY);
  const centerWorld = simToWorldCoordinates((minX + maxX) / 2, (minY + maxY) / 2);

  return {
    center: centerWorld,
    size: { width, depth },
  };
}

/**
 * Generates multi-lane road markings (dashed white lane dividers, solid double/single yellow centerlines,
 * and solid white edge borders). Markings are offset in world space with elevation Y=0.035.
 */
export function generateMultiLaneMarkings(
  edge: RoadEdgeGeometry,
  u: RoadNodeGeometry,
  v: RoadNodeGeometry,
  isBidirectional = true
): LaneMarkingSegment[] {
  const p1 = simToWorldCoordinates(u.x, u.y, 0.035);
  const p2 = simToWorldCoordinates(v.x, v.y, 0.035);

  const dx = p2.x - p1.x;
  const dz = p2.z - p1.z;
  const len = Math.hypot(dx, dz);
  if (len < 0.5) return [];

  const ux = dx / len;
  const uz = dz / len;
  // Perpendicular unit vector in XZ plane (left normal)
  const nx = -uz;
  const nz = ux;

  const totalWidth = computeRoadEdgeWidth(edge);
  const halfWidth = totalWidth / 2;
  const markings: LaneMarkingSegment[] = [];

  // 1. Road edge boundary markings (Solid white lines on left and right borders)
  const borderInset = 0.25;
  const leftBorderOffset = halfWidth - borderInset;
  const rightBorderOffset = -(halfWidth - borderInset);

  markings.push({
    id: `${edge.id}_border_left`,
    type: "edge_border",
    colorHex: 0xffffff,
    width: 0.15,
    start: { x: p1.x + nx * leftBorderOffset, y: 0.035, z: p1.z + nz * leftBorderOffset },
    end: { x: p2.x + nx * leftBorderOffset, y: 0.035, z: p2.z + nz * leftBorderOffset },
  });

  markings.push({
    id: `${edge.id}_border_right`,
    type: "edge_border",
    colorHex: 0xffffff,
    width: 0.15,
    start: { x: p1.x + nx * rightBorderOffset, y: 0.035, z: p1.z + nz * rightBorderOffset },
    end: { x: p2.x + nx * rightBorderOffset, y: 0.035, z: p2.z + nz * rightBorderOffset },
  });

  // 2. Centerline and Lane Dividers
  const lanes = Math.max(1, edge.lanes || 1);

  if (isBidirectional) {
    // Two-way road: Centerline dividing oncoming traffic (Solid yellow)
    markings.push({
      id: `${edge.id}_centerline`,
      type: "centerline",
      colorHex: 0xfacc15,
      width: 0.2,
      start: { x: p1.x, y: 0.035, z: p1.z },
      end: { x: p2.x, y: 0.035, z: p2.z },
    });

    // If multi-lane in each direction (lanes >= 2 per side)
    if (lanes >= 2) {
      const halfLanes = Math.max(1, Math.floor(lanes / 2));
      const laneWidth = halfWidth / halfLanes;

      for (let i = 1; i < halfLanes; i++) {
        const offsetLeft = i * laneWidth;
        markings.push({
          id: `${edge.id}_lane_div_l${i}`,
          type: "dashed",
          colorHex: 0xffffff,
          width: 0.15,
          start: { x: p1.x + nx * offsetLeft, y: 0.035, z: p1.z + nz * offsetLeft },
          end: { x: p2.x + nx * offsetLeft, y: 0.035, z: p2.z + nz * offsetLeft },
        });

        const offsetRight = -i * laneWidth;
        markings.push({
          id: `${edge.id}_lane_div_r${i}`,
          type: "dashed",
          colorHex: 0xffffff,
          width: 0.15,
          start: { x: p1.x + nx * offsetRight, y: 0.035, z: p1.z + nz * offsetRight },
          end: { x: p2.x + nx * offsetRight, y: 0.035, z: p2.z + nz * offsetRight },
        });
      }
    }
  } else {
    // One-way road: dashed white lane separators between each lane
    if (lanes > 1) {
      const laneWidth = totalWidth / lanes;
      for (let i = 1; i < lanes; i++) {
        const offset = -halfWidth + i * laneWidth;
        markings.push({
          id: `${edge.id}_lane_div_${i}`,
          type: "dashed",
          colorHex: 0xffffff,
          width: 0.15,
          start: { x: p1.x + nx * offset, y: 0.035, z: p1.z + nz * offset },
          end: { x: p2.x + nx * offset, y: 0.035, z: p2.z + nz * offset },
        });
      }
    }
  }

  return markings;
}

/**
 * Generates zebra-style crosswalk stripes from explicit entry/exit points across a roadway.
 * Stripes are white rectangular pads placed at Y=0.04.
 */
export function generateZebraStripes(
  entryPoint: [number, number],
  exitPoint: [number, number],
  widthM = 3.0,
  stripeWidthM = 0.5,
  stripeGapM = 0.5
): ZebraStripeGeometry[] {
  const p1 = simToWorldCoordinates(entryPoint[0], entryPoint[1], 0.04);
  const p2 = simToWorldCoordinates(exitPoint[0], exitPoint[1], 0.04);

  const dx = p2.x - p1.x;
  const dz = p2.z - p1.z;
  const pathLen = Math.hypot(dx, dz);
  if (pathLen < 0.5) return [];

  const ux = dx / pathLen;
  const uz = dz / pathLen;
  const angleY = Math.atan2(dx, dz);

  const stripes: ZebraStripeGeometry[] = [];
  const pitch = stripeWidthM + stripeGapM;
  const numStripes = Math.max(1, Math.floor(pathLen / pitch));

  for (let i = 0; i < numStripes; i++) {
    const d = (i + 0.5) * pitch;
    if (d > pathLen - stripeWidthM * 0.5) break;

    stripes.push({
      id: `stripe_${i}`,
      position: {
        x: p1.x + ux * d,
        y: 0.04,
        z: p1.z + uz * d,
      },
      width: widthM,
      length: stripeWidthM,
      rotationY: angleY,
    });
  }

  return stripes;
}

/**
 * Generates inferred crosswalks at intersection approaches where explicit crosswalk metadata is absent.
 * Clearly identified as visual inference to preserve simulation semantics.
 */
export function generateInferredCrosswalks(
  geometry: RoadNetworkGeometry,
  crosswalkWidthM = 3.0,
  setbackM = 7.0
): ZebraStripeGeometry[] {
  const stripes: ZebraStripeGeometry[] = [];
  const nodeMap = new Map<string, RoadNodeGeometry>();
  for (const n of geometry.nodes) {
    nodeMap.set(n.id, n);
  }

  // Count degree of each node
  const nodeEdgeMap = new Map<string, RoadEdgeGeometry[]>();
  for (const edge of geometry.edges) {
    const list = nodeEdgeMap.get(edge.start_node_id) || [];
    list.push(edge);
    nodeEdgeMap.set(edge.start_node_id, list);
  }

  // For nodes with at least 2 connections, place crosswalks on outgoing approaches
  const processedApproaches = new Set<string>();

  for (const [nodeId, edges] of nodeEdgeMap.entries()) {
    if (edges.length < 2) continue;
    const node = nodeMap.get(nodeId);
    if (!node) continue;

    for (const edge of edges) {
      const otherNode = nodeMap.get(edge.end_node_id);
      if (!otherNode) continue;

      const key = [nodeId, otherNode.id].sort().join("<->");
      if (processedApproaches.has(key)) continue;
      processedApproaches.add(key);

      const pNode = simToWorldCoordinates(node.x, node.y, 0.04);
      const pOther = simToWorldCoordinates(otherNode.x, otherNode.y, 0.04);

      const dx = pOther.x - pNode.x;
      const dz = pOther.z - pNode.z;
      const len = Math.hypot(dx, dz);
      if (len <= setbackM + 5) continue;

      const ux = dx / len;
      const uz = dz / len;
      // Perpendicular unit vector in XZ plane
      const nx = -uz;
      const nz = ux;

      const roadWidth = computeRoadEdgeWidth(edge);
      const halfW = roadWidth / 2;

      // Crossing line across the road at setbackM from node center
      const centerCrossX = pNode.x + ux * setbackM;
      const centerCrossZ = pNode.z + uz * setbackM;

      const entryPt: [number, number] = [
        centerCrossX + nx * halfW,
        -(centerCrossZ + nz * halfW), // map world to sim (simY = -worldZ)
      ];
      const exitPt: [number, number] = [
        centerCrossX - nx * halfW,
        -(centerCrossZ - nz * halfW),
      ];

      const edgeStripes = generateZebraStripes(entryPt, exitPt, crosswalkWidthM, 0.5, 0.5);
      stripes.push(...edgeStripes);
    }
  }

  return stripes;
}

/**
 * Generates curbs and sidewalks alongside road edges.
 * Elevated slightly above road level (Y=0.08) and set back from intersection pads so roads are never blocked.
 */
export function generateCurbsAndSidewalks(
  edge: RoadEdgeGeometry,
  u: RoadNodeGeometry,
  v: RoadNodeGeometry,
  sidewalkWidthM = 2.0,
  curbHeightM = 0.12,
  junctionClearanceM = 5.0
): SidewalkSegmentGeometry[] {
  const p1 = simToWorldCoordinates(u.x, u.y, 0.08);
  const p2 = simToWorldCoordinates(v.x, v.y, 0.08);

  const dx = p2.x - p1.x;
  const dz = p2.z - p1.z;
  const len = Math.hypot(dx, dz);
  if (len <= junctionClearanceM * 2 + 2) return [];

  const ux = dx / len;
  const uz = dz / len;
  // Perpendicular unit vector in XZ plane
  const nx = -uz;
  const nz = ux;

  const roadWidth = computeRoadEdgeWidth(edge);
  const halfRoadWidth = roadWidth / 2;
  const offsetDistance = halfRoadWidth + sidewalkWidthM / 2;

  // Trim start and end by junction clearance to avoid intersecting junction circles
  const startX = p1.x + ux * junctionClearanceM;
  const startZ = p1.z + uz * junctionClearanceM;
  const endX = p2.x - ux * junctionClearanceM;
  const endZ = p2.z - uz * junctionClearanceM;

  const leftSidewalk: SidewalkSegmentGeometry = {
    id: `${edge.id}_sidewalk_left`,
    edgeId: edge.id,
    side: "left",
    width: sidewalkWidthM,
    curbHeight: curbHeightM,
    start: { x: startX + nx * offsetDistance, y: 0.08, z: startZ + nz * offsetDistance },
    end: { x: endX + nx * offsetDistance, y: 0.08, z: endZ + nz * offsetDistance },
  };

  const rightSidewalk: SidewalkSegmentGeometry = {
    id: `${edge.id}_sidewalk_right`,
    edgeId: edge.id,
    side: "right",
    width: sidewalkWidthM,
    curbHeight: curbHeightM,
    start: { x: startX - nx * offsetDistance, y: 0.08, z: startZ - nz * offsetDistance },
    end: { x: endX - nx * offsetDistance, y: 0.08, z: endZ - nz * offsetDistance },
  };

  return [leftSidewalk, rightSidewalk];
}

/**
 * Fast deterministic PRNG (Mulberry32).
 * Returns uniform random float in [0, 1) given a 32-bit unsigned integer seed.
 */
export function createMulberry32(seed: number): () => number {
  let a = (seed ^ 0x12345678) >>> 0;
  return function next(): number {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Calculates Euclidean distance from a 2D point (px, pz) to a line segment (ax, az)-(bx, bz).
 */
export function pointToSegmentDistance(
  px: number,
  pz: number,
  ax: number,
  az: number,
  bx: number,
  bz: number
): number {
  const dx = bx - ax;
  const dz = bz - az;
  const lenSq = dx * dx + dz * dz;
  if (lenSq === 0) {
    return Math.hypot(px - ax, pz - az);
  }
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / lenSq));
  const projX = ax + t * dx;
  const projZ = az + t * dz;
  return Math.hypot(px - projX, pz - projZ);
}

/**
 * Generates deterministic procedural urban buildings around the road network.
 * Respects strict exclusion zones: buildings are guaranteed never to intersect road surfaces,
 * intersections, crosswalks, or sidewalks.
 */
export function generateProceduralBuildings(
  geometry: RoadNetworkGeometry,
  options?: BuildingGeneratorOptions
): ProceduralBuilding[] {
  if (geometry.nodes.length === 0) return [];

  const seed = options?.seed ?? 42;
  const random = createMulberry32(seed);

  const nodeMap = new Map<string, RoadNodeGeometry>();
  for (const n of geometry.nodes) {
    nodeMap.set(n.id, n);
  }

  // Precompute world segments and max half-width for exclusion check
  const segments: { ax: number; az: number; bx: number; bz: number; roadHalfWidth: number }[] = [];
  for (const edge of geometry.edges) {
    const u = nodeMap.get(edge.start_node_id);
    const v = nodeMap.get(edge.end_node_id);
    if (!u || !v) continue;
    const p1 = simToWorldCoordinates(u.x, u.y);
    const p2 = simToWorldCoordinates(v.x, v.y);
    const width = computeRoadEdgeWidth(edge);
    segments.push({
      ax: p1.x,
      az: p1.z,
      bx: p2.x,
      bz: p2.z,
      roadHalfWidth: width / 2,
    });
  }

  const bounds = computeNetworkBounds(geometry);
  const minX = bounds.center.x - bounds.size.width / 2 - 40;
  const maxX = bounds.center.x + bounds.size.width / 2 + 40;
  const minZ = bounds.center.z - bounds.size.depth / 2 - 40;
  const maxZ = bounds.center.z + bounds.size.depth / 2 + 40;

  const minH = options?.minHeight ?? 14;
  const maxH = options?.maxHeight ?? 65;
  const minFP = options?.minFootprint ?? 12;
  const maxFP = options?.maxFootprint ?? 24;
  const roadClearance = options?.roadClearanceM ?? 4.0;
  const sidewalkAllowance = 3.0; // clearance for curbs & sidewalks

  // Building color palette (modern sleek urban slate/cool blue/charcoal)
  const palette = [
    0x1e293b, 0x334155, 0x475569, 0x1e3a5f, 0x243c5a, 0x0f2744, 0x374151,
  ];

  const buildings: ProceduralBuilding[] = [];
  const placedFootprints: { cx: number; cz: number; radius: number }[] = [];

  // Generate candidate grid points with jitter
  const step = 28; // spacing between candidate building lots
  let idCounter = 0;

  for (let x = minX; x <= maxX; x += step) {
    for (let z = minZ; z <= maxZ; z += step) {
      // Small deterministic jitter to make urban layout natural
      const jitterX = (random() - 0.5) * 8;
      const jitterZ = (random() - 0.5) * 8;
      const candX = x + jitterX;
      const candZ = z + jitterZ;

      const bWidth = minFP + random() * (maxFP - minFP);
      const bDepth = minFP + random() * (maxFP - minFP);
      const bRadius = Math.hypot(bWidth, bDepth) / 2;

      // 1. Exclusion check against all road segments
      let collidesWithRoad = false;
      for (const seg of segments) {
        const dist = pointToSegmentDistance(candX, candZ, seg.ax, seg.az, seg.bx, seg.bz);
        const minSafeDist = seg.roadHalfWidth + sidewalkAllowance + roadClearance + bRadius;
        if (dist < minSafeDist) {
          collidesWithRoad = true;
          break;
        }
      }
      if (collidesWithRoad) continue;

      // 2. Exclusion check against intersection nodes
      let collidesWithJunction = false;
      for (const node of geometry.nodes) {
        const np = simToWorldCoordinates(node.x, node.y);
        const distToJunction = Math.hypot(candX - np.x, candZ - np.z);
        if (distToJunction < 12.0 + bRadius) {
          collidesWithJunction = true;
          break;
        }
      }
      if (collidesWithJunction) continue;

      // 3. Exclusion check against other placed buildings
      let overlapsBuilding = false;
      for (const b of placedFootprints) {
        const dist = Math.hypot(candX - b.cx, candZ - b.cz);
        if (dist < b.radius + bRadius + 2.0) {
          overlapsBuilding = true;
          break;
        }
      }
      if (overlapsBuilding) continue;

      // Accepted!
      const height = minH + random() * (maxH - minH);
      const colorHex = palette[Math.floor(random() * palette.length)];
      const rotationY = (random() - 0.5) * 0.1; // subtle orientation alignment

      placedFootprints.push({ cx: candX, cz: candZ, radius: bRadius });
      buildings.push({
        id: `bld_${++idCounter}`,
        position: { x: candX, y: height / 2, z: candZ },
        width: Math.round(bWidth * 10) / 10,
        depth: Math.round(bDepth * 10) / 10,
        height: Math.round(height * 10) / 10,
        rotationY,
        colorHex,
      });
    }
  }

  return buildings;
}
