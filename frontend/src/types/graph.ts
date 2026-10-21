/**
 * Graph geometry models for 3D road network and urban environment visualization.
 */

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

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

export type LaneMarkingType = "solid" | "dashed" | "edge_border" | "centerline";

export interface LaneMarkingSegment {
  id: string;
  type: LaneMarkingType;
  colorHex: number;
  start: Point3D;
  end: Point3D;
  width: number;
}

export interface ZebraStripeGeometry {
  id: string;
  position: Point3D;
  width: number;
  length: number;
  rotationY: number;
}

export interface SidewalkSegmentGeometry {
  id: string;
  edgeId: string;
  side: "left" | "right";
  start: Point3D;
  end: Point3D;
  width: number;
  curbHeight: number;
}

export interface ProceduralBuilding {
  id: string;
  position: Point3D;
  width: number;
  depth: number;
  height: number;
  rotationY: number;
  colorHex: number;
}

export interface BuildingGeneratorOptions {
  seed?: number;
  density?: number;
  minHeight?: number;
  maxHeight?: number;
  minFootprint?: number;
  maxFootprint?: number;
  roadClearanceM?: number;
}

export type CameraProjectionMode = "perspective" | "orthographic";
export type LightingMode = "day" | "night";
