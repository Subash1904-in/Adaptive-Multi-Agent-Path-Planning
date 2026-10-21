import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiClientError, SimulationApiClient } from "../lib/api/client";

describe("SimulationApiClient", () => {
  let client: SimulationApiClient;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    client = new SimulationApiClient({ baseUrl: "http://test-server/api/v1" });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("constructs base URL correctly and strips trailing slashes", () => {
    const custom = new SimulationApiClient({ baseUrl: "http://example.com/api/v1///" });
    expect(custom.getBaseUrl()).toBe("http://example.com/api/v1");
  });

  it("lists scenarios successfully", async () => {
    const mockScenarios = [
      {
        id: "scn_01",
        name: "Test Scenario",
        description: "Test description",
        version: "1.0.0",
        author: "Tester",
        vehicle_count: 2,
        road_network_source: "synthetic_grid",
        time_step_s: 0.1,
        max_ticks: 100,
        effective_max_ticks: 100,
      },
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockScenarios,
    } as Response);

    const result = await client.listScenarios();
    expect(result).toEqual(mockScenarios);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/scenarios/",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("retrieves single scenario by ID", async () => {
    const mockScenario = {
      metadata: { id: "scn_single", name: "Single Vehicle" },
      road_network: { source_type: "synthetic_grid" },
      vehicles: [],
      time_step_s: 0.1,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockScenario,
    } as Response);

    const result = await client.getScenario("scn_single");
    expect(result).toEqual(mockScenario);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/scenarios/scn_single/",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("creates a simulation run successfully", async () => {
    const mockRunStatus = {
      run_id: "run_custom",
      scenario_id: "scn_01",
      scenario_name: "Test Scenario",
      lifecycle_state: "READY",
      current_tick: 0,
      elapsed_time_s: 0.0,
      is_terminal: false,
      arrived_count: 0,
      active_count: 1,
      total_vehicles: 1,
      scenario_fingerprint: "abc",
      initial_world_state_fingerprint: "def",
      commit_sha: "123",
      disclaimer: "Academic only",
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockRunStatus,
    } as Response);

    const result = await client.createRun({
      scenario_id: "scn_01",
      run_id: "run_custom",
      max_ticks: 50,
    });

    expect(result).toEqual(mockRunStatus);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          scenario_id: "scn_01",
          run_id: "run_custom",
          max_ticks: 50,
        }),
      })
    );
  });

  it("handles non-2xx RFC 7807 error responses gracefully", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({
        error_code: "RUN_NOT_FOUND",
        detail: "Run 'run_missing' was not found in registry.",
      }),
    } as Response);

    await expect(client.getRun("run_missing")).rejects.toThrow(ApiClientError);
    await expect(client.getRun("run_missing")).rejects.toMatchObject({
      statusCode: 404,
      errorCode: "RUN_NOT_FOUND",
      message: "Run 'run_missing' was not found in registry.",
    });
  });

  it("handles invalid JSON from server without crashing", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("SyntaxError: Unexpected token < in JSON");
      },
    } as unknown as Response);

    await expect(client.listScenarios()).rejects.toThrow(
      "Invalid JSON returned by server"
    );
  });

  it("handles network failure (fetch rejected)", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

    await expect(client.getHealth()).rejects.toThrow(
      "Request failed: Failed to fetch"
    );
  });

  it("steps run and cancels run with correct payloads", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "stepped" }),
    } as Response);

    await client.stepRun("run_01", { ticks: 5 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_01/step/",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ ticks: 5 }),
      })
    );

    await client.cancelRun("run_01", "Stop requested");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_01/cancel/",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "Stop requested" }),
      })
    );
  });

  it("fetches run metrics with optional time-window query parameters", async () => {
    const mockMetrics = {
      run_id: "run_metrics_01",
      lifecycle_state: "RUNNING",
      current_tick: 50,
      metrics: {},
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockMetrics,
    } as Response);

    // Call without query params
    const res1 = await client.getRunMetrics("run_metrics_01");
    expect(res1).toEqual(mockMetrics);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_metrics_01/metrics/",
      expect.objectContaining({ method: "GET" })
    );

    // Call with query params
    const res2 = await client.getRunMetrics("run_metrics_01", {
      tick_start: 10,
      tick_end: 40,
      time_window_start_s: 1.0,
      time_window_end_s: 4.0,
    });
    expect(res2).toEqual(mockMetrics);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://test-server/api/v1/runs/run_metrics_01/metrics/?tick_start=10&tick_end=40&time_window_start_s=1&time_window_end_s=4",
      expect.objectContaining({ method: "GET" })
    );
  });
});

