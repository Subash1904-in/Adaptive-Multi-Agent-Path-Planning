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
  StreetlampProp,
  UrbanTreeProp,
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

export interface MetropolitanNetworkOptions {
  cityRadiusM?: number;
  spacingM?: number;
}

/**
 * Hand-authored SIHSimulation-inspired circulation layout.
 *
 * This is intentionally a new procedural layout rather than an import of the
 * supplied project's map or UI. The rounded perimeter, two inner loops, and
 * radial connectors provide smooth continuous circulation for dense traffic.
 */
export function buildSIHSimulationLayout(): RoadNetworkGeometry {
  const nodes: RoadNodeGeometry[] = [];
  const edges: RoadEdgeGeometry[] = [];
  const addNode = (id: string, x: number, y: number, zone: string) =>
    nodes.push({ id, x, y, attributes: { layout: "sih-simulation", zone } });
  const addBidirectional = (id: string, a: string, b: string, lanes = 2) => {
    const start = nodes.find((node) => node.id === a);
    const end = nodes.find((node) => node.id === b);
    if (!start || !end) return;
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    edges.push(
      {
        id,
        start_node_id: a,
        end_node_id: b,
        length_m: length,
        speed_limit_mps: 12.5,
        lanes,
        attributes: { layout: "sih-simulation", one_way: false, width_m: lanes * 3.75 },
      },
      {
        id: `${id}_rev`,
        start_node_id: b,
        end_node_id: a,
        length_m: length,
        speed_limit_mps: 12.5,
        lanes,
        attributes: { layout: "sih-simulation", one_way: false, width_m: lanes * 3.75 },
      }
    );
  };

  const outerCount = 20;
  for (let index = 0; index < outerCount; index += 1) {
    const angle = (index / outerCount) * Math.PI * 2;
    addNode(`sih_outer_${index}`, Math.cos(angle) * 270, Math.sin(angle) * 185, "outer-loop");
  }
  for (let index = 0; index < outerCount; index += 1) {
    addBidirectional(
      `sih_outer_edge_${index}`,
      `sih_outer_${index}`,
      `sih_outer_${(index + 1) % outerCount}`,
      3
    );
  }

  const innerCount = 12;
  for (let index = 0; index < innerCount; index += 1) {
    const angle = (index / innerCount) * Math.PI * 2 + Math.PI / 12;
    addNode(`sih_inner_${index}`, Math.cos(angle) * 125, Math.sin(angle) * 85, "inner-loop");
  }
  for (let index = 0; index < innerCount; index += 1) {
    addBidirectional(
      `sih_inner_edge_${index}`,
      `sih_inner_${index}`,
      `sih_inner_${(index + 1) % innerCount}`,
      2
    );
  }

  for (let index = 0; index < 12; index += 1) {
    const outerIndex = Math.round((index / innerCount) * outerCount) % outerCount;
    addBidirectional(
      `sih_connector_${index}`,
      `sih_inner_${index}`,
      `sih_outer_${outerIndex}`,
      2
    );
  }

  return { nodes, edges };
}

/**
 * Expands or constructs an extensive, realistic metropolitan road network.
 * Preserves all scenario nodes and edges so simulation paths remain 100% valid,
 * while generating:
 * 1. Broad multi-lane arterial boulevards (Grand East-West & North-South axes)
 * 2. Angled diagonal avenues (e.g. Broadway & Parkway diagonals) breaking the square grid
 * 3. A sweeping curved perimeter ring expressway (24-segment circular ring road)
 * 4. Secondary urban cross streets with realistic varied block proportions
 * 5. Radial highway connectors tying the ring road into the metropolitan core
 */
export function buildRealisticMetropolitanNetwork(
  baseGeometry?: RoadNetworkGeometry | null,
  options?: MetropolitanNetworkOptions
): RoadNetworkGeometry {
  const cityRadius = options?.cityRadiusM ?? 380;
  const nodes: RoadNodeGeometry[] = [];
  const edges: RoadEdgeGeometry[] = [];
  const nodeMap = new Map<string, RoadNodeGeometry>();
  const edgeSet = new Set<string>();

  const addNode = (node: RoadNodeGeometry) => {
    if (!nodeMap.has(node.id)) {
      nodeMap.set(node.id, node);
      nodes.push(node);
    }
  };

  const addEdge = (edge: RoadEdgeGeometry) => {
    if (!edgeSet.has(edge.id)) {
      edgeSet.add(edge.id);
      edges.push(edge);
    }
  };

  const addBiEdge = (
    id1: string,
    uId: string,
    vId: string,
    lanes = 2,
    speedLimit = 13.89,
    widthM?: number
  ) => {
    const u = nodeMap.get(uId);
    const v = nodeMap.get(vId);
    if (!u || !v || uId === vId) return;
    const len = Math.hypot(v.x - u.x, v.y - u.y);
    if (len < 0.5) return;

    addEdge({
      id: id1,
      start_node_id: uId,
      end_node_id: vId,
      length_m: Math.round(len * 10) / 10,
      speed_limit_mps: speedLimit,
      lanes,
      attributes: { width_m: widthM, one_way: false },
    });

    addEdge({
      id: `${id1}_rev`,
      start_node_id: vId,
      end_node_id: uId,
      length_m: Math.round(len * 10) / 10,
      speed_limit_mps: speedLimit,
      lanes,
      attributes: { width_m: widthM, one_way: false },
    });
  };

  // 1. Ingest base scenario nodes and edges (if any)
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  if (baseGeometry && baseGeometry.nodes.length > 0) {
    for (const n of baseGeometry.nodes) {
      addNode(n);
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y);
      maxY = Math.max(maxY, n.y);
    }
    for (const e of baseGeometry.edges) {
      addEdge(e);
    }
  }

  // Determine metropolitan center
  const cx = Number.isFinite(minX) && Number.isFinite(maxX) ? (minX + maxX) / 2 : 100;
  const cy = Number.isFinite(minY) && Number.isFinite(maxY) ? (minY + maxY) / 2 : 100;

  // 2. Outer Curved Perimeter Ring Expressway (24-segment circular ring road)
  const N_RING = 24;
  const ringNodeIds: string[] = [];
  for (let i = 0; i < N_RING; i++) {
    const ang = (i / N_RING) * 2 * Math.PI;
    const rx = Math.round(cx + cityRadius * Math.cos(ang));
    const ry = Math.round(cy + cityRadius * Math.sin(ang));
    const id = `ring_n${i}`;
    ringNodeIds.push(id);
    addNode({
      id,
      x: rx,
      y: ry,
      attributes: { type: "ring_expressway", angle_rad: ang },
    });
  }

  // Connect ring segments
  for (let i = 0; i < N_RING; i++) {
    const nextIdx = (i + 1) % N_RING;
    addBiEdge(
      `edge_ring_${i}_to_${nextIdx}`,
      ringNodeIds[i],
      ringNodeIds[nextIdx],
      4,
      22.2,
      16.0
    );
  }

  // 3. Grand Arterial Boulevards (4-lane divided avenues crossing the entire city)
  // 3A. East-West Grand Boulevard
  const ewSteps = [-320, -240, -160, -80, 0, 80, 160, 240, 320];
  const ewNodeIds: string[] = [];
  for (let i = 0; i < ewSteps.length; i++) {
    const offset = ewSteps[i];
    const nx = cx + offset;
    const ny = cy;

    let existingId: string | null = null;
    for (const [id, n] of nodeMap) {
      if (Math.hypot(n.x - nx, n.y - ny) < 18) {
        existingId = id;
        break;
      }
    }

    const id = existingId || `art_ew_${i}`;
    if (!existingId) {
      addNode({
        id,
        x: nx,
        y: ny,
        attributes: { type: "arterial_ew" },
      });
    }
    ewNodeIds.push(id);
  }

  for (let i = 0; i < ewNodeIds.length - 1; i++) {
    if (ewNodeIds[i] !== ewNodeIds[i + 1]) {
      addBiEdge(`edge_art_ew_${i}`, ewNodeIds[i], ewNodeIds[i + 1], 4, 18.0, 16.0);
    }
  }
  // Connect East-West ends to ring road: West to ring_n12 (180 deg), East to ring_n0 (0 deg)
  addBiEdge("edge_art_ew_to_ring_w", ewNodeIds[0], "ring_n12", 4, 20.0, 16.0);
  addBiEdge("edge_art_ew_to_ring_e", ewNodeIds[ewNodeIds.length - 1], "ring_n0", 4, 20.0, 16.0);

  // 3B. North-South Grand Boulevard
  const nsSteps = [-320, -240, -160, -80, 0, 80, 160, 240, 320];
  const nsNodeIds: string[] = [];
  for (let i = 0; i < nsSteps.length; i++) {
    const offset = nsSteps[i];
    const nx = cx;
    const ny = cy + offset;

    let existingId: string | null = null;
    for (const [id, n] of nodeMap) {
      if (Math.hypot(n.x - nx, n.y - ny) < 18) {
        existingId = id;
        break;
      }
    }

    const id = existingId || `art_ns_${i}`;
    if (!existingId) {
      addNode({
        id,
        x: nx,
        y: ny,
        attributes: { type: "arterial_ns" },
      });
    }
    nsNodeIds.push(id);
  }

  for (let i = 0; i < nsNodeIds.length - 1; i++) {
    if (nsNodeIds[i] !== nsNodeIds[i + 1]) {
      addBiEdge(`edge_art_ns_${i}`, nsNodeIds[i], nsNodeIds[i + 1], 4, 18.0, 16.0);
    }
  }
  // Connect North-South ends to ring road: South to ring_n18 (270 deg), North to ring_n6 (90 deg)
  addBiEdge("edge_art_ns_to_ring_s", nsNodeIds[0], "ring_n18", 4, 20.0, 16.0);
  addBiEdge("edge_art_ns_to_ring_n", nsNodeIds[nsNodeIds.length - 1], "ring_n6", 4, 20.0, 16.0);

  // 4. Diagonal Avenues (Broadway & Parkway Diagonals breaking the square grid)
  // Diagonal 1: Southwest to Northeast (45-degree angle)
  const diag1Steps = [-280, -210, -140, -70, 0, 70, 140, 210, 280];
  const diag1NodeIds: string[] = [];
  for (let i = 0; i < diag1Steps.length; i++) {
    const offset = diag1Steps[i];
    const nx = Math.round(cx + offset);
    const ny = Math.round(cy + offset);

    let existingId: string | null = null;
    for (const [id, n] of nodeMap) {
      if (Math.hypot(n.x - nx, n.y - ny) < 22) {
        existingId = id;
        break;
      }
    }

    const id = existingId || `diag1_n${i}`;
    if (!existingId) {
      addNode({
        id,
        x: nx,
        y: ny,
        attributes: { type: "diagonal_avenue_broadway" },
      });
    }
    diag1NodeIds.push(id);
  }

  for (let i = 0; i < diag1NodeIds.length - 1; i++) {
    if (diag1NodeIds[i] !== diag1NodeIds[i + 1]) {
      addBiEdge(`edge_diag1_${i}`, diag1NodeIds[i], diag1NodeIds[i + 1], 3, 16.0, 12.0);
    }
  }
  // Connect Diagonal 1 ends to ring road: SW to ring_n15 (225 deg), NE to ring_n3 (45 deg)
  addBiEdge("edge_diag1_to_ring_sw", diag1NodeIds[0], "ring_n15", 3, 16.0, 12.0);
  addBiEdge("edge_diag1_to_ring_ne", diag1NodeIds[diag1NodeIds.length - 1], "ring_n3", 3, 16.0, 12.0);

  // Diagonal 2: Northwest to Southeast (135-degree angle)
  const diag2Steps = [-280, -210, -140, -70, 0, 70, 140, 210, 280];
  const diag2NodeIds: string[] = [];
  for (let i = 0; i < diag2Steps.length; i++) {
    const offset = diag2Steps[i];
    const nx = Math.round(cx - offset);
    const ny = Math.round(cy + offset);

    let existingId: string | null = null;
    for (const [id, n] of nodeMap) {
      if (Math.hypot(n.x - nx, n.y - ny) < 22) {
        existingId = id;
        break;
      }
    }

    const id = existingId || `diag2_n${i}`;
    if (!existingId) {
      addNode({
        id,
        x: nx,
        y: ny,
        attributes: { type: "diagonal_avenue_parkway" },
      });
    }
    diag2NodeIds.push(id);
  }

  for (let i = 0; i < diag2NodeIds.length - 1; i++) {
    if (diag2NodeIds[i] !== diag2NodeIds[i + 1]) {
      addBiEdge(`edge_diag2_${i}`, diag2NodeIds[i], diag2NodeIds[i + 1], 3, 16.0, 12.0);
    }
  }
  // Connect Diagonal 2 ends to ring road: NW to ring_n9 (135 deg), SE to ring_n21 (315 deg)
  addBiEdge("edge_diag2_to_ring_nw", diag2NodeIds[0], "ring_n9", 3, 16.0, 12.0);
  addBiEdge("edge_diag2_to_ring_se", diag2NodeIds[diag2NodeIds.length - 1], "ring_n21", 3, 16.0, 12.0);

  // 5. Secondary Urban District Connectors (Varied non-square grid blocks)
  const quadOffsetsX = [-210, -110, 110, 210];
  const quadOffsetsY = [-210, -110, 110, 210];

  for (const qx of quadOffsetsX) {
    for (const qy of quadOffsetsY) {
      const nx = cx + qx;
      const ny = cy + qy;

      let existingId: string | null = null;
      for (const [id, n] of nodeMap) {
        if (Math.hypot(n.x - nx, n.y - ny) < 24) {
          existingId = id;
          break;
        }
      }

      if (!existingId) {
        const id = `dist_x${qx}_y${qy}`;
        addNode({
          id,
          x: nx,
          y: ny,
          attributes: { type: "district_connector" },
        });

        // Connect to nearest nodes within 90m
        for (const [otherId, otherNode] of nodeMap) {
          if (otherId === id) continue;
          const d = Math.hypot(otherNode.x - nx, otherNode.y - ny);
          if (d > 20 && d <= 95) {
            const angleDeg = (Math.abs(Math.atan2(otherNode.y - ny, otherNode.x - nx)) * 180) / Math.PI;
            const isCardinal = angleDeg < 18 || angleDeg > 162 || Math.abs(angleDeg - 90) < 18;
            const isDiagonal = Math.abs(angleDeg - 45) < 18 || Math.abs(angleDeg - 135) < 18;
            if (isCardinal || isDiagonal) {
              addBiEdge(`edge_conn_${id}_to_${otherId}`, id, otherId, 2, 13.89, 8.5);
            }
          }
        }
      }
    }
  }

  // 6. Guarantee full metropolitan graph connectivity:
  // Ensure every node in the metropolitan network is reachable and connected to the arterial grid
  const nodeDegrees = new Map<string, number>();
  for (const n of nodes) nodeDegrees.set(n.id, 0);
  for (const e of edges) {
    nodeDegrees.set(e.start_node_id, (nodeDegrees.get(e.start_node_id) || 0) + 1);
    nodeDegrees.set(e.end_node_id, (nodeDegrees.get(e.end_node_id) || 0) + 1);
  }

  for (const n of nodes) {
    const deg = nodeDegrees.get(n.id) || 0;
    if (deg <= 2) {
      // Find nearest arterial/diagonal or district neighbors to ensure seamless network traversal
      const candidates = nodes
        .filter((other) => other.id !== n.id)
        .map((other) => ({ other, dist: Math.hypot(other.x - n.x, other.y - n.y) }))
        .filter(({ dist }) => dist >= 15 && dist <= 120)
        .sort((a, b) => a.dist - b.dist);

      for (const { other } of candidates.slice(0, 3)) {
        addBiEdge(`edge_bridge_${n.id}_${other.id}`, n.id, other.id, 2, 13.89, 8.5);
        nodeDegrees.set(n.id, (nodeDegrees.get(n.id) || 0) + 1);
        nodeDegrees.set(other.id, (nodeDegrees.get(other.id) || 0) + 1);
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
 * Authoritative single source of truth for the complete metropolitan road network.
 * Produces an extensive, realistic road network with arterial boulevards, diagonal avenues,
 * perimeter ring expressway, and district connectors, while preserving all scenario nodes.
 */
export function getUnifiedMetropolitanRoadNetwork(
  scenario: ScenarioDefinition | null
): RoadNetworkGeometry {
  const base = extractRoadNetworkFromScenario(scenario);
  const sihLayout = buildSIHSimulationLayout();
  return buildRealisticMetropolitanNetwork({
    nodes: [...sihLayout.nodes, ...base.nodes],
    edges: [...sihLayout.edges, ...base.edges],
  });
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

  const minH = options?.minHeight ?? 22;
  const maxH = options?.maxHeight ?? 110;
  const minFP = options?.minFootprint ?? 14;
  const maxFP = options?.maxFootprint ?? 28;
  const roadClearance = options?.roadClearanceM ?? 3.5;
  const sidewalkAllowance = 2.5;

  // Architectural modern metropolitan color palettes (Swiss porcelain, limestone, soft tinted glass)
  const glassPalette = [
    0xf8fafc, // Porcelain Chalk White
    0xf1f5f9, // Architectural Limestone
    0xe2e8f0, // Soft Platinum Slate
    0xe0f2fe, // Light Sky Tinted Glass
    0xf3f4f6, // Matte Alabaster
    0xe0e7ff, // Soft Azure Tint
    0xede9fe, // Soft Quartz
  ];

  const buildings: ProceduralBuilding[] = [];
  const placedFootprints: { cx: number; cz: number; radius: number }[] = [];

  // Step across the metropolitan footprint
  const step = 25;
  let idCounter = 0;

  for (let x = minX; x <= maxX; x += step) {
    for (let z = minZ; z <= maxZ; z += step) {
      // Natural urban lot jitter
      const jitterX = (random() - 0.5) * 6;
      const jitterZ = (random() - 0.5) * 6;
      const candX = x + jitterX;
      const candZ = z + jitterZ;

      // Central Park District exclusion (Metropolitan Central Park)
      const isParkZone =
        candX >= bounds.center.x - 120 &&
        candX <= bounds.center.x - 25 &&
        candZ >= bounds.center.z + 25 &&
        candZ <= bounds.center.z + 125;
      if (isParkZone) continue;

      const bWidth = minFP + random() * (maxFP - minFP);
      const bDepth = minFP + random() * (maxFP - minFP);
      const bRadius = Math.hypot(bWidth, bDepth) / 2;

      // 1. Exclusion check against road segments
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

      // 2. Exclusion check against junctions
      let collidesWithJunction = false;
      for (const node of geometry.nodes) {
        const np = simToWorldCoordinates(node.x, node.y);
        const distToJunction = Math.hypot(candX - np.x, candZ - np.z);
        if (distToJunction < 11.0 + bRadius) {
          collidesWithJunction = true;
          break;
        }
      }
      if (collidesWithJunction) continue;

      // 3. Exclusion check against placed buildings
      let overlapsBuilding = false;
      for (const b of placedFootprints) {
        const dist = Math.hypot(candX - b.cx, candZ - b.cz);
        if (dist < b.radius + bRadius + 1.5) {
          overlapsBuilding = true;
          break;
        }
      }
      if (overlapsBuilding) continue;

      // Accepted Building Lot!
      // Downtown center proximity multiplier: towering skyscrapers in CBD, mid-rises in outer districts
      const distFromCenter = Math.hypot(candX - bounds.center.x, candZ - bounds.center.z);
      const centerFactor = Math.max(
        0.2,
        1.0 - distFromCenter / (Math.max(bounds.size.width, bounds.size.depth) * 0.65)
      );
      const height = (minH + random() * (maxH - minH)) * (0.45 + centerFactor * 0.7);
      const colorHex = glassPalette[Math.floor(random() * glassPalette.length)];

      // Flatiron wedge alignment if near diagonal avenues
      const isNearDiagonal =
        Math.abs(Math.abs(candX - bounds.center.x) - Math.abs(candZ - bounds.center.z)) < 24;
      const rotationY = isNearDiagonal
        ? ((candX - bounds.center.x) * (candZ - bounds.center.z) > 0 ? Math.PI / 4 : -Math.PI / 4) +
          (random() - 0.5) * 0.05
        : (random() - 0.5) * 0.08;

      placedFootprints.push({ cx: candX, cz: candZ, radius: bRadius });

      // Multi-tier skyscraper architecture
      const tiers: {
        width: number;
        depth: number;
        height: number;
        offsetY: number;
        style: "podium" | "glass_tower" | "stepped" | "penthouse";
      }[] = [];
      const hasPodium = height > 28;
      const podiumHeight = hasPodium ? Math.min(8.0, height * 0.18) : 0;

      if (hasPodium) {
        tiers.push({
          width: bWidth,
          depth: bDepth,
          height: podiumHeight,
          offsetY: podiumHeight / 2,
          style: "podium",
        });
      }

      const towerHeight = height - podiumHeight;
      const towerInset = hasPodium ? 1.2 : 0;
      const towerWidth = Math.max(8.0, bWidth - towerInset * 2);
      const towerDepth = Math.max(8.0, bDepth - towerInset * 2);

      tiers.push({
        width: towerWidth,
        depth: towerDepth,
        height: towerHeight,
        offsetY: podiumHeight + towerHeight / 2,
        style: "glass_tower",
      });

      // Rooftop crowns for prominent skyscrapers
      const hasSpire = height > 55 && random() > 0.4;
      const hasHelipad = height > 45 && !hasSpire && random() > 0.55;
      const hasPenthouse = height > 38 && random() > 0.3;

      if (hasPenthouse) {
        const phH = 4.5;
        const phW = towerWidth * 0.55;
        const phD = towerDepth * 0.55;
        tiers.push({
          width: phW,
          depth: phD,
          height: phH,
          offsetY: height + phH / 2,
          style: "penthouse",
        });
      }

      const hasPlaza = random() > 0.65;

      buildings.push({
        id: `bld_${++idCounter}`,
        position: { x: candX, y: 0, z: candZ },
        width: Math.round(bWidth * 10) / 10,
        depth: Math.round(bDepth * 10) / 10,
        height: Math.round(height * 10) / 10,
        rotationY,
        colorHex,
        tiers,
        hasSpire,
        hasHelipad,
        hasPlaza,
        windowGlowColorHex: random() > 0.5 ? 0xfef08a : 0xfde047,
      });
    }
  }

  return buildings;
}

/**
 * Builds a hand-authored suburban district around the metropolitan network.
 * The offsets are intentionally fixed so the visual map is stable across runs
 * and can be adjusted like a simple map layout rather than a random city fill.
 */
export function generateManualSuburbanBuildings(
  geometry: RoadNetworkGeometry
): ProceduralBuilding[] {
  if (geometry.nodes.length === 0) return [];

  const bounds = computeNetworkBounds(geometry);
  const lots: Array<[number, number, number, number, number]> = [
    [-175, -105, 18, 14, 9],
    [-125, -105, 14, 18, 12],
    [-75, -105, 20, 14, 10],
    [-15, -105, 16, 16, 14],
    [45, -105, 22, 14, 11],
    [105, -105, 15, 20, 15],
    [165, -105, 20, 15, 10],
    [-175, -45, 15, 18, 12],
    [-120, -45, 22, 14, 10],
    [-65, -45, 16, 18, 13],
    [5, -45, 20, 15, 9],
    [65, -45, 14, 20, 16],
    [125, -45, 22, 14, 11],
    [180, -45, 16, 18, 13],
    [-175, 35, 20, 15, 11],
    [-115, 35, 15, 20, 15],
    [-55, 35, 22, 14, 10],
    [15, 35, 16, 18, 12],
    [75, 35, 20, 15, 14],
    [135, 35, 15, 20, 10],
    [-165, 100, 18, 14, 9],
    [-105, 100, 14, 18, 13],
    [-45, 100, 20, 15, 11],
    [20, 100, 16, 20, 15],
    [80, 100, 22, 14, 10],
    [145, 100, 15, 18, 12],
  ];
  const facadePalette = [0xf08a62, 0xe97855, 0xf2a36f, 0xd9684c, 0xec946d];
  const roofPalette = [0x3f6fb6, 0x4d83c7, 0x64748b, 0x2f5d9b];

  const nodeMap = new Map(geometry.nodes.map((node) => [node.id, node]));
  const segments = geometry.edges.flatMap((edge) => {
    const start = nodeMap.get(edge.start_node_id);
    const end = nodeMap.get(edge.end_node_id);
    if (!start || !end) return [];
    const a = simToWorldCoordinates(start.x, start.y);
    const b = simToWorldCoordinates(end.x, end.y);
    return [{ ax: a.x, az: a.z, bx: b.x, bz: b.z, halfWidth: computeRoadEdgeWidth(edge) / 2 }];
  });
  const placed: Array<{ x: number; z: number; radius: number }> = [];
  const buildings: ProceduralBuilding[] = [];

  for (let index = 0; index < lots.length; index += 1) {
    const [offsetX, offsetZ, width, depth, height] = lots[index];
    const x = bounds.center.x + offsetX;
    const z = bounds.center.z + offsetZ;
    const radius = Math.hypot(width, depth) / 2;
    const nearRoad = segments.some((segment) => {
      const distance = pointToSegmentDistance(x, z, segment.ax, segment.az, segment.bx, segment.bz);
      return distance < segment.halfWidth + 5.5 + radius;
    });
    const nearJunction = geometry.nodes.some((node) => {
      const position = simToWorldCoordinates(node.x, node.y);
      return Math.hypot(x - position.x, z - position.z) < radius + 11;
    });
    const overlaps = placed.some((building) =>
      Math.hypot(x - building.x, z - building.z) < radius + building.radius + 2
    );
    if (nearRoad || nearJunction || overlaps) continue;

    placed.push({ x, z, radius });
    const floorHeight = Math.max(4.5, height - 4);
    buildings.push({
      id: `manual_suburban_${index + 1}`,
      position: { x, y: 0, z },
      width,
      depth,
      height,
      rotationY: index % 3 === 0 ? Math.PI / 2 : 0,
      colorHex: facadePalette[index % facadePalette.length],
      tiers: [
        { width, depth, height: floorHeight, offsetY: floorHeight / 2, style: "podium" },
        {
          width: width * 0.92,
          depth: depth * 0.92,
          height: height - floorHeight,
          offsetY: floorHeight + (height - floorHeight) / 2,
          style: "stepped",
        },
      ],
      hasPlaza: false,
      hasSpire: false,
      hasHelipad: false,
      windowGlowColorHex: roofPalette[index % roofPalette.length],
    });
  }

  return buildings;
}

/**
 * Generates instanced urban environmental props: street trees, modern LED streetlamps,
 * decorative plaza greenery, and central park groves, positioned strictly outside roadway boundaries.
 */
export function generateUrbanProps(
  geometry: RoadNetworkGeometry,
  buildings: ProceduralBuilding[],
  seed = 42
): {
  trees: UrbanTreeProp[];
  streetlamps: StreetlampProp[];
} {
  const random = createMulberry32(seed);
  const trees: UrbanTreeProp[] = [];
  const streetlamps: StreetlampProp[] = [];

  const nodeMap = new Map<string, RoadNodeGeometry>();
  for (const n of geometry.nodes) {
    nodeMap.set(n.id, n);
  }

  const foliagePalette = [
    0x2d6a4f, // Lush Emerald Pine
    0x40916c, // Fresh Park Green
    0x1b4332, // Deep Forest Green
    0x52b788, // Lime Meadow Green
    0x2d5a27, // Urban Maple
  ];

  let treeCounter = 0;
  let lampCounter = 0;

  // 1. Street-Side Trees & Streetlamps along Road Sidewalks
  for (const edge of geometry.edges) {
    const u = nodeMap.get(edge.start_node_id);
    const v = nodeMap.get(edge.end_node_id);
    if (!u || !v) continue;

    const p1 = simToWorldCoordinates(u.x, u.y);
    const p2 = simToWorldCoordinates(v.x, v.y);

    const dx = p2.x - p1.x;
    const dz = p2.z - p1.z;
    const len = Math.hypot(dx, dz);
    if (len < 18) continue;

    const ux = dx / len;
    const uz = dz / len;
    const nx = -uz;
    const nz = ux;

    const roadWidth = computeRoadEdgeWidth(edge);
    const halfWidth = roadWidth / 2;

    // Sidewalk offset for trees: 2.2m beyond road edge
    const treeOffsetDist = halfWidth + 2.2;
    // Sidewalk offset for lamps: 1.4m beyond road edge (curb line)
    const lampOffsetDist = halfWidth + 1.4;

    const startDist = 8.0;
    const endDist = len - 8.0;

    // Distribute Street Trees every ~14m
    for (let d = startDist; d <= endDist; d += 14.0) {
      const px = p1.x + ux * d;
      const pz = p1.z + uz * d;

      // Left side tree
      const tHeightL = 4.2 + random() * 1.8;
      const tColorL = foliagePalette[Math.floor(random() * foliagePalette.length)];
      trees.push({
        id: `tree_${++treeCounter}`,
        position: { x: px + nx * treeOffsetDist, y: 0, z: pz + nz * treeOffsetDist },
        height: Math.round(tHeightL * 10) / 10,
        canopyRadius: 1.6 + random() * 0.6,
        canopyColorHex: tColorL,
      });

      // Right side tree
      const tHeightR = 4.2 + random() * 1.8;
      const tColorR = foliagePalette[Math.floor(random() * foliagePalette.length)];
      trees.push({
        id: `tree_${++treeCounter}`,
        position: { x: px - nx * treeOffsetDist, y: 0, z: pz - nz * treeOffsetDist },
        height: Math.round(tHeightR * 10) / 10,
        canopyRadius: 1.6 + random() * 0.6,
        canopyColorHex: tColorR,
      });
    }

    // Distribute Streetlamps every ~28m
    for (let d = startDist + 6.0; d <= endDist; d += 28.0) {
      const px = p1.x + ux * d;
      const pz = p1.z + uz * d;
      const rotY = Math.atan2(dx, dz);

      // Left lamp
      streetlamps.push({
        id: `lamp_${++lampCounter}`,
        position: { x: px + nx * lampOffsetDist, y: 0, z: pz + nz * lampOffsetDist },
        rotationY: rotY + Math.PI / 2,
        height: 5.5,
      });

      // Right lamp
      streetlamps.push({
        id: `lamp_${++lampCounter}`,
        position: { x: px - nx * lampOffsetDist, y: 0, z: pz - nz * lampOffsetDist },
        rotationY: rotY - Math.PI / 2,
        height: 5.5,
      });
    }
  }

  // 2. Plaza Trees in Building Courtyards
  for (const b of buildings) {
    if (b.hasPlaza) {
      const plazaTrees = 2 + Math.floor(random() * 3);
      for (let i = 0; i < plazaTrees; i++) {
        const angle = random() * Math.PI * 2;
        const radius = Math.max(b.width, b.depth) * 0.6 + 2.0 + random() * 4.0;
        const tx = b.position.x + Math.cos(angle) * radius;
        const tz = b.position.z + Math.sin(angle) * radius;
        const tHeight = 3.6 + random() * 2.2;
        const tColor = foliagePalette[Math.floor(random() * foliagePalette.length)];

        trees.push({
          id: `tree_${++treeCounter}`,
          position: { x: tx, y: 0, z: tz },
          height: Math.round(tHeight * 10) / 10,
          canopyRadius: 1.5 + random() * 0.8,
          canopyColorHex: tColor,
        });
      }
    }
  }

  // 3. Central Park Woodland Canopy Grove
  const bounds = computeNetworkBounds(geometry);
  const parkMinX = bounds.center.x - 110;
  const parkMaxX = bounds.center.x - 30;
  const parkMinZ = bounds.center.z + 30;
  const parkMaxZ = bounds.center.z + 120;
  const parkCenterX = (parkMinX + parkMaxX) / 2;
  const parkCenterZ = (parkMinZ + parkMaxZ) / 2;

  for (let px = parkMinX + 10; px <= parkMaxX - 10; px += 16) {
    for (let pz = parkMinZ + 10; pz <= parkMaxZ - 10; pz += 16) {
      const distToFountain = Math.hypot(px - parkCenterX, pz - parkCenterZ);
      if (distToFountain < 16) continue;

      const jx = px + (random() - 0.5) * 6;
      const jz = pz + (random() - 0.5) * 6;
      const tHeight = 4.8 + random() * 2.5;
      const tColor = foliagePalette[Math.floor(random() * foliagePalette.length)];

      trees.push({
        id: `tree_park_${++treeCounter}`,
        position: { x: jx, y: 0, z: jz },
        height: Math.round(tHeight * 10) / 10,
        canopyRadius: 2.0 + random() * 0.9,
        canopyColorHex: tColor,
      });
    }
  }

  return { trees, streetlamps };
}
