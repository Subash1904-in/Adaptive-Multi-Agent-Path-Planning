import { describe, it, expect } from "vitest";
import {
  simToWorldCoordinates,
  computeRoadEdgeWidth,
  generateSyntheticGridGeometry,
  extractRoadNetworkFromScenario,
  computeNetworkBounds,
  generateMultiLaneMarkings,
  generateZebraStripes,
  generateInferredCrosswalks,
  generateCurbsAndSidewalks,
  createMulberry32,
  pointToSegmentDistance,
  generateProceduralBuildings,
  adaptOsmRoadNetwork,
  projectGeoCoordinatesToLocalMeters,
} from "../features/scene3d/geometry";
import type { RoadEdgeGeometry, RoadNodeGeometry } from "../types/graph";
import type { ScenarioDefinition } from "../types/simulation";

describe("Geometry, Urban Environment and Coordinate Transforms", () => {
  describe("simToWorldCoordinates", () => {
    it("maps planar coordinates to Three.js space correctly (X=East, Y=Up, Z=-North)", () => {
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

      const pBothNan = simToWorldCoordinates(NaN, NaN, NaN);
      expect(pBothNan).toEqual({ x: 0, y: 0, z: 0 });
    });
  });

  describe("computeRoadEdgeWidth", () => {
    it("uses explicit width_m attribute when specified and valid", () => {
      const edge: RoadEdgeGeometry = {
        id: "edge_custom",
        start_node_id: "n1",
        end_node_id: "n2",
        length_m: 50,
        speed_limit_mps: 13.89,
        lanes: 2,
        attributes: { width_m: 12.5 },
      };
      expect(computeRoadEdgeWidth(edge)).toBe(12.5);
    });

    it("derives width from lane count when lanes > 1", () => {
      const edge: RoadEdgeGeometry = {
        id: "edge_4lanes",
        start_node_id: "n1",
        end_node_id: "n2",
        length_m: 50,
        speed_limit_mps: 13.89,
        lanes: 4,
      };
      // 4 lanes * 3.75m = 15.0m
      expect(computeRoadEdgeWidth(edge)).toBe(15.0);
    });

    it("falls back to default width when lanes <= 1 and no explicit width", () => {
      const edge: RoadEdgeGeometry = {
        id: "edge_1lane",
        start_node_id: "n1",
        end_node_id: "n2",
        length_m: 50,
        speed_limit_mps: 13.89,
        lanes: 1,
      };
      expect(computeRoadEdgeWidth(edge)).toBe(8.0);
    });
  });

  describe("generateSyntheticGridGeometry", () => {
    it("generates correct default 3x3 grid with bidirectional edges", () => {
      const grid = generateSyntheticGridGeometry();
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
      // 12 horizontal + 12 vertical = 24 bidirectional edges
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
      expect(grid.edges.length).toBe(4);
    });

    it("clamps rows and cols to minimum of 2", () => {
      const grid = generateSyntheticGridGeometry({
        rows: 0,
        cols: -5,
        spacing_m: 0,
      });

      expect(grid.nodes.length).toBe(4);
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

    it("falls back gracefully when scenario is osm_import without embedded graph data", () => {
      const scenario: ScenarioDefinition = {
        metadata: {
          id: "osm_scenario",
          name: "OSM Scenario",
          description: "Test",
          version: "1.0.0",
          author: "Test",
        },
        road_network: {
          source_type: "osm_import",
          osm_config: {
            place_name: "Downtown",
            network_type: "drive",
          },
        },
        signals: [],
        vehicles: [],
        pedestrians: [],
        time_step_s: 0.1,
      };

      const grid = extractRoadNetworkFromScenario(scenario);
      expect(grid.nodes.length).toBe(9);
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

  describe("generateMultiLaneMarkings", () => {
    const nodeA: RoadNodeGeometry = { id: "na", x: 0, y: 0 };
    const nodeB: RoadNodeGeometry = { id: "nb", x: 100, y: 0 };

    it("generates edge borders and solid yellow centerline for bidirectional road", () => {
      const edge: RoadEdgeGeometry = {
        id: "e1",
        start_node_id: "na",
        end_node_id: "nb",
        length_m: 100,
        speed_limit_mps: 13.89,
        lanes: 2,
      };

      const markings = generateMultiLaneMarkings(edge, nodeA, nodeB, true);
      expect(markings.length).toBeGreaterThanOrEqual(3);

      const centerline = markings.find((m) => m.type === "centerline");
      expect(centerline).toBeDefined();
      expect(centerline?.colorHex).toBe(0xfacc15); // Yellow
      expect(centerline?.start.y).toBe(0.035);

      const borders = markings.filter((m) => m.type === "edge_border");
      expect(borders.length).toBe(2);
      expect(borders[0].colorHex).toBe(0xffffff);
    });

    it("generates dashed white lane dividers for multi-lane road", () => {
      const edge: RoadEdgeGeometry = {
        id: "e_multi",
        start_node_id: "na",
        end_node_id: "nb",
        length_m: 100,
        speed_limit_mps: 13.89,
        lanes: 4,
      };

      const markings = generateMultiLaneMarkings(edge, nodeA, nodeB, true);
      const dashed = markings.filter((m) => m.type === "dashed");
      expect(dashed.length).toBeGreaterThan(0);
      expect(dashed[0].colorHex).toBe(0xffffff);
    });

    it("handles degenerate or zero-length edges safely", () => {
      const edge: RoadEdgeGeometry = {
        id: "e_zero",
        start_node_id: "na",
        end_node_id: "na",
        length_m: 0,
        speed_limit_mps: 13.89,
        lanes: 2,
      };

      const markings = generateMultiLaneMarkings(edge, nodeA, nodeA, true);
      expect(markings).toEqual([]);
    });
  });

  describe("generateZebraStripes", () => {
    it("generates parallel white stripes between entry and exit points", () => {
      const entry: [number, number] = [0, 0];
      const exit: [number, number] = [10, 0];

      const stripes = generateZebraStripes(entry, exit, 3.0, 0.5, 0.5);
      expect(stripes.length).toBeGreaterThan(0);
      expect(stripes[0].position.y).toBe(0.04);
      expect(stripes[0].width).toBe(3.0);
      expect(stripes[0].length).toBe(0.5);
    });

    it("returns empty array for zero-length crosswalk", () => {
      const entry: [number, number] = [5, 5];
      const exit: [number, number] = [5, 5];

      const stripes = generateZebraStripes(entry, exit);
      expect(stripes).toEqual([]);
    });
  });

  describe("generateInferredCrosswalks", () => {
    it("generates inferred crosswalks at intersection nodes with multiple connections", () => {
      const grid = generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
      const inferred = generateInferredCrosswalks(grid, 3.0, 7.0);

      expect(inferred.length).toBeGreaterThan(0);
      expect(inferred[0].position.y).toBe(0.04);
    });
  });

  describe("generateCurbsAndSidewalks", () => {
    const nodeA: RoadNodeGeometry = { id: "na", x: 0, y: 0 };
    const nodeB: RoadNodeGeometry = { id: "nb", x: 100, y: 0 };

    it("generates left and right sidewalks running parallel to the road", () => {
      const edge: RoadEdgeGeometry = {
        id: "e_walk",
        start_node_id: "na",
        end_node_id: "nb",
        length_m: 100,
        speed_limit_mps: 13.89,
        lanes: 2,
      };

      const sidewalks = generateCurbsAndSidewalks(edge, nodeA, nodeB, 2.0, 0.12, 5.0);
      expect(sidewalks.length).toBe(2);
      expect(sidewalks[0].side).toBe("left");
      expect(sidewalks[1].side).toBe("right");
      expect(sidewalks[0].width).toBe(2.0);
      expect(sidewalks[0].curbHeight).toBe(0.12);
      expect(sidewalks[0].start.y).toBe(0.08);
    });

    it("returns empty array for short segments less than clearance distance", () => {
      const shortNodeB: RoadNodeGeometry = { id: "nb_short", x: 6, y: 0 };
      const edge: RoadEdgeGeometry = {
        id: "e_short",
        start_node_id: "na",
        end_node_id: "nb_short",
        length_m: 6,
        speed_limit_mps: 13.89,
        lanes: 2,
      };

      const sidewalks = generateCurbsAndSidewalks(edge, nodeA, shortNodeB, 2.0, 0.12, 5.0);
      expect(sidewalks).toEqual([]);
    });
  });

  describe("createMulberry32 PRNG", () => {
    it("generates bit-for-bit identical sequences given the same seed", () => {
      const rng1 = createMulberry32(12345);
      const rng2 = createMulberry32(12345);

      const seq1 = Array.from({ length: 10 }, () => rng1());
      const seq2 = Array.from({ length: 10 }, () => rng2());

      expect(seq1).toEqual(seq2);
    });

    it("generates different sequences for different seeds", () => {
      const rng1 = createMulberry32(100);
      const rng2 = createMulberry32(200);

      const v1 = rng1();
      const v2 = rng2();
      expect(v1).not.toBe(v2);
    });
  });

  describe("pointToSegmentDistance", () => {
    it("computes perpendicular distance when projection falls within segment", () => {
      // Segment (0,0) to (10,0), point at (5, 4) -> distance = 4
      const dist = pointToSegmentDistance(5, 4, 0, 0, 10, 0);
      expect(dist).toBeCloseTo(4, 5);
    });

    it("computes distance to closest endpoint when projection falls outside", () => {
      // Segment (0,0) to (10,0), point at (-3, 4) -> dist to (0,0) = 5
      const dist = pointToSegmentDistance(-3, 4, 0, 0, 10, 0);
      expect(dist).toBeCloseTo(5, 5);
    });

    it("handles zero-length segment safely", () => {
      const dist = pointToSegmentDistance(3, 4, 0, 0, 0, 0);
      expect(dist).toBeCloseTo(5, 5);
    });
  });

  describe("generateProceduralBuildings", () => {
    it("generates deterministic building layout identical for the same seed", () => {
      const grid = generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });

      const b1 = generateProceduralBuildings(grid, { seed: 99 });
      const b2 = generateProceduralBuildings(grid, { seed: 99 });

      expect(b1.length).toBeGreaterThan(0);
      expect(b1).toEqual(b2);
    });

    it("guarantees all buildings strictly avoid road surfaces and junctions", () => {
      const grid = generateSyntheticGridGeometry({ rows: 3, cols: 3, spacing_m: 100 });
      const buildings = generateProceduralBuildings(grid, { seed: 42, roadClearanceM: 4.0 });

      for (const b of buildings) {
        // Must have positive height and realistic dimensions
        expect(b.height).toBeGreaterThan(10);
        expect(b.width).toBeGreaterThan(10);
        expect(b.depth).toBeGreaterThan(10);

        // Check distance to all grid nodes: must be outside junction clearance
        for (const node of grid.nodes) {
          const np = simToWorldCoordinates(node.x, node.y);
          const dist = Math.hypot(b.position.x - np.x, b.position.z - np.z);
          // Building center must not be within 10m of any intersection node center
          expect(dist).toBeGreaterThan(12);
        }
      }
    });

    it("returns empty array for empty road network", () => {
      const empty = generateProceduralBuildings({ nodes: [], edges: [] });
      expect(empty).toEqual([]);
    });
  });

  describe("projectGeoCoordinatesToLocalMeters", () => {
    it("projects geographic (lon, lat) degrees to local Cartesian meters centered at origin", () => {
      const coords = [
        { id: "n1", lon: -122.4194, lat: 37.7749 },
        { id: "n2", lon: -122.4184, lat: 37.7759 },
      ];

      const proj = projectGeoCoordinatesToLocalMeters(coords);
      expect(proj.size).toBe(2);

      const p1 = proj.get("n1");
      const p2 = proj.get("n2");
      expect(p1).toBeDefined();
      expect(p2).toBeDefined();

      // Origin is midpoint, so sum of x and y should be ~0
      expect((p1?.x ?? 0) + (p2?.x ?? 0)).toBeCloseTo(0, 2);
      expect((p1?.y ?? 0) + (p2?.y ?? 0)).toBeCloseTo(0, 2);
    });

    it("handles empty or invalid inputs gracefully", () => {
      const empty = projectGeoCoordinatesToLocalMeters([]);
      expect(empty.size).toBe(0);

      const invalid = projectGeoCoordinatesToLocalMeters([
        { id: "bad", lon: NaN, lat: Infinity },
      ]);
      expect(invalid.size).toBe(0);
    });
  });

  describe("adaptOsmRoadNetwork", () => {
    it("adapts planar OSM node and edge payload into RoadNetworkGeometry", () => {
      const rawOsm = {
        nodes: [
          { id: "osm_1", x: 10, y: 20 },
          { id: "osm_2", x: 60, y: 20 },
        ],
        edges: [
          {
            id: "osm_e1",
            start_node_id: "osm_1",
            end_node_id: "osm_2",
            lanes: 2,
            speed_limit_mps: 15.0,
            length_m: 50.0,
          },
        ],
      };

      const result = adaptOsmRoadNetwork(rawOsm);
      expect(result.nodes.length).toBe(2);
      expect(result.edges.length).toBe(1);
      expect(result.nodes[0].x).toBe(10);
      expect(result.edges[0].lanes).toBe(2);
    });

    it("adapts geographic (lon, lat) OSM payload into planar metric coordinates", () => {
      const rawGeoOsm = {
        nodes: [
          { id: "g1", lon: -122.4194, lat: 37.7749 },
          { id: "g2", lon: -122.4184, lat: 37.7759 },
        ],
        edges: [
          {
            id: "ge1",
            start_node_id: "g1",
            end_node_id: "g2",
            lanes: 2,
          },
        ],
      };

      const result = adaptOsmRoadNetwork(rawGeoOsm);
      expect(result.nodes.length).toBe(2);
      expect(result.edges.length).toBe(1);
      expect(Number.isFinite(result.nodes[0].x)).toBe(true);
      expect(Number.isFinite(result.nodes[0].y)).toBe(true);
    });

    it("falls back cleanly to default synthetic grid on null or invalid payload", () => {
      const fallbackNull = adaptOsmRoadNetwork(null);
      expect(fallbackNull.nodes.length).toBe(9);

      const fallbackEmpty = adaptOsmRoadNetwork({});
      expect(fallbackEmpty.nodes.length).toBe(9);
    });
  });
});
