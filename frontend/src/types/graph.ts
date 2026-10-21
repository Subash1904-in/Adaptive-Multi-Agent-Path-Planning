/**
 * Graph geometry models for 3D road network visualization.
 */

export interface RoadNodeGeometry {
  id: string;
  x: number;
  y: number;
  attributes?: Record<string, unknown>;
}

export interface RoadEdgeGeometry {
  id: string;
  start_node_id: string;
  end_node_id: string;
  length_m: number;
  speed_limit_mps: number;
  lanes: number;
  attributes?: Record<string, unknown>;
}

export interface RoadNetworkGeometry {
  nodes: RoadNodeGeometry[];
  edges: RoadEdgeGeometry[];
}
