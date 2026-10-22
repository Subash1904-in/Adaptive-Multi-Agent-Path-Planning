import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SimulationApiClient } from "../lib/api/client";
import { SimulationWebSocketClient } from "../lib/websocket/client";
import type {
  RunStatus,
  ScenarioDefinition,
  ScenarioSummary,
} from "../types/simulation";
import type { WebSocketEventEnvelope } from "../types/websocket";
import type { IncidentRecord } from "../types/incidents";

// Mock WebSocket implementation for end-to-end integration tests
class MockWebSocket {
  public static instances: MockWebSocket[] = [];
  public static readonly OPEN = 1;
  public static readonly CLOSED = 3;

  public url: string;
  public readyState = 0; // CONNECTING
  public sentMessages: string[] = [];
  public onopen: (() => void) | null = null;
  public onmessage: ((event: { data: unknown }) => void) | null = null;
  public onerror: ((error: unknown) => void) | null = null;
  public onclose: ((event: { code: number; reason: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) this.onopen();
    }, 10);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = "") {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose({ code, reason });
  }

  receiveMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === "string" ? data : JSON.stringify(data) });
    }
  }
}

describe("Frontend E2E Simulation Workflow Integration", () => {
  let apiClient: SimulationApiClient;
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
    // @ts-expect-error Mocking WebSocket
    globalThis.WebSocket = MockWebSocket;
    apiClient = new SimulationApiClient({ baseUrl: "http://localhost:8000/api/v1" });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("completes full scenario selection, run creation, and lifecycle execution", async () => {
    // 1. Scenario selection & loading
    const mockScenarios: ScenarioSummary[] = [
      {
        id: "scn_multi_veh",
        name: "Multi-Vehicle Deployment",
        description: "Three vehicles traversing 4x4 grid",
        version: "1.0.0",
        author: "AMAPP Test",
        vehicle_count: 3,
        road_network_source: "synthetic_grid",
        time_step_s: 0.1,
        max_ticks: 100,
        effective_max_ticks: 100,
      },
    ];

    const mockDetail: ScenarioDefinition = {
      metadata: {
        id: "scn_multi_veh",
        name: "Multi-Vehicle Deployment",
        description: "Three vehicles traversing 4x4 grid",
        version: "1.0.0",
        author: "AMAPP Test",
      },
      road_network: {
        source_type: "synthetic_grid",
        grid_config: { rows: 4, cols: 4, spacing_m: 50 },
      },
      vehicles: [
        {
          vehicle_id: "veh_01",
          start_node_id: "node_0",
          destination_node_id: "node_3",
          algorithm: "astar",
          cost_mode: "travel_time",
          vehicle_type: "standard",
          initial_speed_mps: 0.0,
        },
      ],
      time_step_s: 0.1,
      max_ticks: 100,
      stop_on_all_arrived: true,
      seed: 42,
    };

    const mockRunStatus: RunStatus = {
      run_id: "run_e2e_frontend_01",
      scenario_id: "scn_multi_veh",
      scenario_name: "Multi-Vehicle Deployment",
      lifecycle_state: "READY",
      current_tick: 0,
      elapsed_time_s: 0.0,
      is_terminal: false,
      arrived_count: 0,
      active_count: 3,
      total_vehicles: 3,
      scenario_fingerprint: "a".repeat(64),
      initial_world_state_fingerprint: "b".repeat(64),
      commit_sha: null,
      disclaimer: "Educational simulation",
    };

    globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.endsWith("/scenarios/") && (!init || init.method === "GET")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScenarios,
        } as Response);
      }
      if (urlStr.includes("/scenarios/scn_multi_veh/")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockDetail,
        } as Response);
      }
      if (urlStr.endsWith("/runs/") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => mockRunStatus,
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response);
    });

    // Step A: List and select scenario
    const scenarios = await apiClient.listScenarios();
    expect(scenarios).toHaveLength(1);
    expect(scenarios[0].id).toBe("scn_multi_veh");

    const scenario = await apiClient.getScenario("scn_multi_veh");
    expect(scenario.metadata.name).toBe("Multi-Vehicle Deployment");
    expect(scenario.vehicles).toHaveLength(1);

    // Step B: Create simulation run
    const run = await apiClient.createRun({
      scenario_id: "scn_multi_veh",
      run_id: "run_e2e_frontend_01",
    });
    expect(run.run_id).toBe("run_e2e_frontend_01");
    expect(run.lifecycle_state).toBe("READY");

    // 2. Real-time WebSocket connection and telemetry streaming
    const wsClient = new SimulationWebSocketClient({
      wsBaseUrl: "ws://localhost:8000/ws/v1",
      autoSubscribe: true,
    });

    const receivedEvents: WebSocketEventEnvelope[] = [];
    wsClient.onEvent((event) => receivedEvents.push(event));

    wsClient.connect(run.run_id);
    expect(wsClient.getStatus()).toBe("CONNECTING");

    // Advance clock to allow MockWebSocket onopen
    vi.advanceTimersByTime(20);
    expect(wsClient.getStatus()).toBe("CONNECTED");
    const activeWs = MockWebSocket.instances[0];
    expect(activeWs).toBeDefined();

    // 3. Receive telemetry event
    const telemetryEvent: WebSocketEventEnvelope = {
      run_id: run.run_id,
      event_type: "vehicle.state",
      tick: 1,
      timestamp_s: 0.1,
      sequence: 1,
      schema_version: "1.0.0",
      payload: {
        vehicles: [
          {
            id: "veh_01",
            position: { x: 10.5, y: 20.0 },
            speed_mps: 8.5,
            heading_rad: 0.0,
            current_edge_id: "edge_r0_c0_to_r0_c1",
            state: "IN_TRANSIT",
          },
        ],
        active_count: 1,
        arrived_count: 0,
      },
      disclaimer: "Educational simulation",
    };

    activeWs.receiveMessage(telemetryEvent);
    expect(receivedEvents).toHaveLength(1);
    expect(receivedEvents[0].event_type).toBe("vehicle.state");
    const vehicle = (receivedEvents[0].payload as { vehicles: Array<{ id: string; speed_mps: number }> }).vehicles[0];
    expect(vehicle.id).toBe("veh_01");
    expect(vehicle.speed_mps).toBe(8.5);

    // 4. Dynamic incident injection
    const mockIncidentRecord: IncidentRecord = {
      id: "inc_001",
      incident_type: "road_closure",
      affected_edge_id: "edge_r0_c0_to_r0_c1",
      affected_node_id: null,
      severity: "high",
      duration_s: 30.0,
      status: "active",
      reported_tick: 5,
      reported_timestamp_s: 0.5,
      resolved_tick: null,
      resolved_timestamp_s: null,
      description: "Emergency road closure",
      congestion_factor: null,
      target_signal_phase: null,
      metadata: {},
    };

    globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes("/incidents/") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => mockIncidentRecord,
        } as Response);
      }
      if (urlStr.includes("/step/") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            run_id: run.run_id,
            lifecycle_state: "RUNNING",
            current_tick: 5,
            advanced_ticks: 5,
          }),
        } as Response);
      }
      if (urlStr.includes("/cancel/") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            run_id: run.run_id,
            lifecycle_state: "CANCELLED",
            current_tick: 5,
          }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response);
    });

    const incident = await apiClient.createIncident(run.run_id, {
      incident_type: "road_closure",
      affected_edge_id: "edge_r0_c0_to_r0_c1",
      severity: "high",
      description: "Emergency road closure",
    });
    expect(incident.id).toBe("inc_001");
    expect(incident.status).toBe("active");

    // 5. Discrete step execution
    const stepResult = await apiClient.stepRun(run.run_id, { ticks: 5 });
    expect(stepResult.advanced_ticks).toBe(5);

    // 6. Cooperative cancellation & WebSocket closure
    const cancelResult = await apiClient.cancelRun(run.run_id, "Operator test termination");
    expect(cancelResult.lifecycle_state).toBe("CANCELLED");

    wsClient.disconnect();
    expect(wsClient.getStatus()).toBe("DISCONNECTED");
  });
});
