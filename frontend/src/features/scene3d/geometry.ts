/**
 * Coordinate transformations and road network geometry construction.
 * Maps simulation planar coordinates (meters) to Three.js 3D world space (X=East, Y=Up, Z=South).
 */

import type { RoadEdgeGeometry, RoadNetworkGeometry, RoadNodeGeometry } from "../../types/graph";
import type { GridConfig, ScenarioDefinition } from "../../types/simulation";

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

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
    return { x: 0, y: elevation, z: 0 };
  }
  return {
    x: Number(simX),
    y: Number(elevation),
    z: -Number(simY),
  };
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
        attributes: { direction: "east", row: r },
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
          attributes: { direction: "west", row: r },
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
        attributes: { direction: "north", col: c },
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
          attributes: { direction: "south", col: c },
        });
      }
    }
  }

  return { nodes, edges };
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
