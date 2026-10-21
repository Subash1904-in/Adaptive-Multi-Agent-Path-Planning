import { describe, it, expect } from "vitest";
import {
  simToWorldCoordinates,
  generateSyntheticGridGeometry,
  extractRoadNetworkFromScenario,
  computeNetworkBounds,
} from "../features/scene3d/geometry";
import type { ScenarioDefinition } from "../types/simulation";

describe("Geometry and Coordinate Transforms", () => {
  describe("simToWorldCoordinates", () => {
    it("maps planar coordinates to Three.js space correctly", () => {
      const p1 = simToWorldCoordinates(10, 25);
      expect(p1).toEqual({ x: 10, y: 0, z: -25 });

      const p2 = simToWorldCoordinates(-50, 100, 1.5);
      expect(p2).toEqual({ x: -50, y: 1.5, z: -100 });
    });

    it("handles invalid or non-finite coordinates gracefully without throwing", () => {
      const pNan = simToWorldCoordinates(NaN, 10);
      expect(pNan).toEqual({ x: 0, y: 0, z: 0 });

      const pInf = simToWorldCoordinates(10, Infinity, 2);
      expect(pInf).toEqual({ x: 0, y: 2, z: 0 });
    });
  });

  describe("generateSyntheticGridGeometry", () => {
    it("generates correct default 3x3 grid with bidirectional edges", () => {
      const grid = generateSyntheticGridGeometry();
      // 3x3 = 9 nodes
      expect(grid.nodes.length).toBe(9);
      expect(grid.nodes[0]).toEqual({
        id: "node_r0_c0",
        x: 0,
        y: 0,
        attributes: { row: 0, col: 0, is_boundary: true },
      });
      expect(grid.nodes[4]).toEqual({
        id: "node_r1_c1",
        x: 100,
        y: 100,
        attributes: { row: 1, col: 1, is_boundary: false },
      });

      // Horizontal: 3 rows * 2 cols = 6 segments * 2 directions = 12 edges
      // Vertical: 2 rows * 3 cols = 6 segments * 2 directions = 12 edges
      // Total = 24 edges
      expect(grid.edges.length).toBe(24);
    });

    it("supports unidirectional grid when configured", () => {
      const grid = generateSyntheticGridGeometry({
        rows: 2,
        cols: 2,
        spacing_m: 50,
        bidirectional: false,
      });

      expect(grid.nodes.length).toBe(4);
      // Horizontal: 2 rows * 1 col = 2 edges
      // Vertical: 1 row * 2 cols = 2 edges
      // Total = 4 edges
      expect(grid.edges.length).toBe(4);
    });

    it("clamps rows and cols to minimum of 2", () => {
      const grid = generateSyntheticGridGeometry({
        rows: 0,
        cols: -5,
        spacing_m: 0,
      });

      expect(grid.nodes.length).toBe(4); // 2x2
    });
  });

  describe("extractRoadNetworkFromScenario", () => {
    it("returns default grid for null scenario", () => {
      const grid = extractRoadNetworkFromScenario(null);
      expect(grid.nodes.length).toBe(9);
    });

    it("extracts grid_config from synthetic_grid scenario", () => {
      const scenario: ScenarioDefinition = {
        metadata: {
          id: "custom_grid",
          name: "Custom 4x4",
          description: "Test",
          version: "1.0.0",
          author: "Test",
        },
        road_network: {
          source_type: "synthetic_grid",
          grid_config: { rows: 4, cols: 4, spacing_m: 80 },
        },
        signals: [],
        vehicles: [],
        pedestrians: [],
        time_step_s: 0.1,
      };

      const grid = extractRoadNetworkFromScenario(scenario);
      expect(grid.nodes.length).toBe(16);
      expect(grid.nodes[15]).toEqual({
        id: "node_r3_c3",
        x: 240,
        y: 240,
        attributes: { row: 3, col: 3, is_boundary: true },
      });
    });
  });

  describe("computeNetworkBounds", () => {
    it("computes center and dimensions correctly", () => {
      const grid = generateSyntheticGridGeometry({
        rows: 3,
        cols: 3,
        spacing_m: 100,
      });

      const bounds = computeNetworkBounds(grid);
      // minX=0, maxX=200 -> center X = 100
      // minY=0, maxY=200 -> center Y in sim = 100 -> world Z = -100
      expect(bounds.center).toEqual({ x: 100, y: 0, z: -100 });
      expect(bounds.size.width).toBe(200);
      expect(bounds.size.depth).toBe(200);
    });

    it("handles empty geometry gracefully", () => {
      const bounds = computeNetworkBounds({ nodes: [], edges: [] });
      expect(bounds.center).toEqual({ x: 0, y: 0, z: 0 });
      expect(bounds.size.width).toBe(100);
    });
  });
});
