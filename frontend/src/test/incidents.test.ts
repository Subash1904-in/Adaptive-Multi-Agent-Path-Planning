import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createIncidentSubsystemSnapshot,
  type CreateIncidentPayload,
  type IncidentRecord,
} from "../types/incidents";
import { SimulationApiClient } from "../lib/api/client";
import { IncidentOverlayManager } from "../features/scene3d/incidentOverlay";
import { SimulationHistoryBuffer } from "../features/playback/historyBuffer";
import type { RoadNetworkGeometry } from "../types/graph";

describe("Incident Domain & Snapshot Helper", () => {
  it("creates an empty snapshot when no incidents are present", () => {
    const snap = createIncidentSubsystemSnapshot([]);
    expect(snap.active_incidents).toEqual([]);
    expect(snap.closed_edges).toEqual([]);
    expect(snap.congested_edges).toEqual({});
    expect(snap.hazard_edges).toEqual({});
    expect(snap.active_count).toBe(0);
  });

  it("categorizes active road closures, congestion, and obstacles correctly", () => {
    const incidents: IncidentRecord[] = [
      {
        id: "inc_1",
        incident_type: "road_closure",
        status: "active",
        severity: "critical",
        affected_edge_id: "edge_0_1",
        reported_timestamp_s: 1.0,
        reported_tick: 10,
      },
      {
        id: "inc_2",
        incident_type: "congestion",
        status: "active",
        severity: "high",
        affected_edge_id: "edge_1_2",
        congestion_factor: 3.5,
        reported_timestamp_s: 2.0,
        reported_tick: 20,
      },
      {
        id: "inc_3",
        incident_type: "obstacle",
        status: "active",
        severity: "medium",
        affected_edge_id: "edge_2_3",
        reported_timestamp_s: 3.0,
        reported_tick: 30,
      },
      {
        id: "inc_4",
        incident_type: "road_closure",
        status: "resolved",
        severity: "low",
        affected_edge_id: "edge_3_4",
        reported_timestamp_s: 0.5,
        reported_tick: 5,
        resolved_timestamp_s: 4.0,
        resolved_tick: 40,
      },
    ];

    const snap = createIncidentSubsystemSnapshot(incidents);
    expect(snap.active_count).toBe(3);
    expect(snap.closed_edges).toEqual(["edge_0_1"]);
    expect(snap.congested_edges).toEqual({ edge_1_2: 3.5 });
    expect(snap.hazard_edges).toEqual({ edge_2_3: 1.0 });
    expect(snap.active_incidents).toHaveLength(4);
  });
});

describe("SimulationApiClient Incidents API", () => {
  let client: SimulationApiClient;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    client = new SimulationApiClient({ baseUrl: "http://test-server/api/v1" });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("lists incidents for a simulation run", async () => {
    const mockResponse = {
      run_id: "run_inc_1",
      total_count: 1,
      active_count: 1,
      resolved_count: 0,
      incidents: [
        {
          id: "inc_test",
          incident_type: "road_closure",
          status: "active",
          severity: "high",
          affected_edge_id: "edge_a",
          reported_timestamp_s: 0.0,
          reported_tick: 0,
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResponse,
    } as Response);

    const result = await client.listIncidents("run_inc_1");
    expect(result.incidents).toHaveLength(1);
    expect(result.incidents[0].affected_edge_id).toBe("edge_a");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_inc_1/incidents/",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("creates an incident successfully", async () => {
    const payload: CreateIncidentPayload = {
      incident_type: "congestion",
      affected_edge_id: "edge_b",
      delay_multiplier: 2.5,
      severity: "medium",
    };

    const mockCreated = {
      id: "inc_cong_1",
      incident_type: "congestion",
      status: "active",
      severity: "medium",
      affected_edge_id: "edge_b",
      congestion_factor: 2.5,
      reported_timestamp_s: 1.0,
      reported_tick: 10,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockCreated,
    } as Response);

    const result = await client.createIncident("run_inc_1", payload);
    expect(result.id).toBe("inc_cong_1");
    expect(result.congestion_factor).toBe(2.5);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_inc_1/incidents/",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      })
    );
  });

  it("removes an incident successfully", async () => {
    const mockResolved = {
      id: "inc_cong_1",
      status: "resolved",
      resolved_timestamp_s: 5.0,
      resolved_tick: 50,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResolved,
    } as Response);

    const result = await client.removeIncident("run_inc_1", "inc_cong_1");
    expect(result.status).toBe("resolved");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_inc_1/incidents/inc_cong_1/",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("handles error response with RFC 7807 problem details", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        type: "about:blank",
        title: "Bad Request",
        status: 400,
        detail: "Edge does not exist in road network.",
      }),
    } as Response);

    await expect(
      client.createIncident("run_inc_1", {
        incident_type: "road_closure",
        affected_edge_id: "nonexistent_edge",
      })
    ).rejects.toThrow("Edge does not exist in road network.");
  });
});

describe("IncidentOverlayManager 3D Rendering", () => {
  let manager: IncidentOverlayManager;

  const mockGeometry: RoadNetworkGeometry = {
    nodes: [
      { id: "n0", x: 0, y: 0 },
      { id: "n1", x: 50, y: 0 },
      { id: "n2", x: 50, y: 50 },
    ],
    edges: [
      {
        id: "edge_0_1",
        start_node_id: "n0",
        end_node_id: "n1",
        speed_limit_mps: 15,
        lanes: 2,
        length_m: 50,
      },
      {
        id: "edge_1_2",
        start_node_id: "n1",
        end_node_id: "n2",
        speed_limit_mps: 15,
        lanes: 2,
        length_m: 50,
      },
    ],
  };

  beforeEach(() => {
    manager = new IncidentOverlayManager();
  });

  afterEach(() => {
    manager.dispose();
  });

  it("creates road closure visual overlay with barrier and red edge highlight", () => {
    const incidents: IncidentRecord[] = [
      {
        id: "inc_closure_1",
        incident_type: "road_closure",
        status: "active",
        severity: "critical",
        affected_edge_id: "edge_0_1",
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(incidents, mockGeometry);
    expect(manager.closuresGroup.children.length).toBe(1);
    expect(manager.closuresGroup.children[0].children.length).toBeGreaterThanOrEqual(2);
  });

  it("creates congestion glow visual overlay with amber line", () => {
    const incidents: IncidentRecord[] = [
      {
        id: "inc_cong_1",
        incident_type: "congestion",
        status: "active",
        severity: "high",
        affected_edge_id: "edge_1_2",
        congestion_factor: 3.0,
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(incidents, mockGeometry);
    expect(manager.congestionGroup.children.length).toBe(1);
  });

  it("creates obstacle warning sign visual overlay", () => {
    const incidents: IncidentRecord[] = [
      {
        id: "inc_obst_1",
        incident_type: "obstacle",
        status: "active",
        severity: "medium",
        affected_edge_id: "edge_0_1",
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(incidents, mockGeometry);
    expect(manager.obstaclesGroup.children.length).toBe(1);
  });

  it("creates traffic signal override halo visual overlay", () => {
    const incidents: IncidentRecord[] = [
      {
        id: "inc_sig_1",
        incident_type: "signal_override",
        status: "active",
        severity: "critical",
        affected_node_id: "n1",
        target_signal_phase: "red",
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(incidents, mockGeometry);
    expect(manager.signalOverridesGroup.children.length).toBe(1);
  });

  it("removes overlays when incidents are resolved or removed", () => {
    const activeIncidents: IncidentRecord[] = [
      {
        id: "inc_temp",
        incident_type: "road_closure",
        status: "active",
        severity: "high",
        affected_edge_id: "edge_0_1",
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(activeIncidents, mockGeometry);
    expect(manager.closuresGroup.children.length).toBe(1);

    // Update with empty list
    manager.update([], mockGeometry);
    expect(manager.closuresGroup.children.length).toBe(0);
  });

  it("disposes meshes and clears root group on dispose()", () => {
    const activeIncidents: IncidentRecord[] = [
      {
        id: "inc_disposable",
        incident_type: "road_closure",
        status: "active",
        severity: "high",
        affected_edge_id: "edge_0_1",
        reported_timestamp_s: 0,
        reported_tick: 0,
      },
    ];

    manager.update(activeIncidents, mockGeometry);
    expect(manager.closuresGroup.children.length).toBe(1);

    manager.dispose();
    expect(manager.closuresGroup.children.length).toBe(0);
    expect(manager.congestionGroup.children.length).toBe(0);
  });
});

describe("SimulationHistoryBuffer Incident Retention", () => {
  it("deep clones and preserves incident states across snapshots", () => {
    const buffer = new SimulationHistoryBuffer(10);

    const inc1: IncidentRecord = {
      id: "inc_1",
      incident_type: "road_closure",
      status: "active",
      severity: "high",
      affected_edge_id: "edge_x",
      reported_timestamp_s: 1.0,
      reported_tick: 10,
    };

    const snap1 = createIncidentSubsystemSnapshot([inc1]);

    buffer.addSnapshot({
      tick: 10,
      simulation_time_s: 1.0,
      timestamp_ms: 1000,
      vehicles: new Map(),
      pedestrians: new Map(),
      signals: new Map(),
      incidents: snap1,
    });

    // Mutate the original record to ensure immutability
    inc1.status = "resolved";

    const retrieved = buffer.getSnapshot(10);
    expect(retrieved).not.toBeNull();
    expect(retrieved?.incidents?.active_incidents[0].status).toBe("active");
    expect(retrieved?.incidents?.closed_edges).toEqual(["edge_x"]);
  });
});
