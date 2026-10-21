import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SimulationWebSocketClient } from "../lib/websocket/client";
import type { WebSocketConnectionStatus, WebSocketEventEnvelope } from "../types/websocket";

// Mock WebSocket implementation for Vitest
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
    // Simulate async connection open
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

  // Test helper to simulate receiving a message
  receiveMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === "string" ? data : JSON.stringify(data) });
    }
  }

  // Test helper to simulate socket error & close
  simulateClose(code = 1006, reason = "Abnormal closure") {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onerror) this.onerror(new Error(reason));
    if (this.onclose) this.onclose({ code, reason });
  }
}

describe("SimulationWebSocketClient", () => {
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
    // @ts-expect-error Mocking WebSocket
    globalThis.WebSocket = MockWebSocket;
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    globalThis.WebSocket = originalWebSocket;
  });

  it("initializes with DISCONNECTED status and connects to correct endpoint", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    expect(client.getStatus()).toBe("DISCONNECTED");

    client.connect("run_01");
    expect(client.getStatus()).toBe("CONNECTING");

    expect(MockWebSocket.instances.length).toBe(1);
    expect(MockWebSocket.instances[0].url).toBe("ws://test-server/ws/v1/runs/run_01/");
  });

  it("transitions to CONNECTED and sends subscribe command on open", () => {
    const client = new SimulationWebSocketClient({
      wsBaseUrl: "ws://test-server/ws/v1",
      autoSubscribe: true,
      fromSequence: 10,
    });

    const statusUpdates: WebSocketConnectionStatus[] = [];
    client.onStatusChange((s) => statusUpdates.push(s));

    client.connect("run_01");
    expect(statusUpdates).toContain("CONNECTING");

    // Advance fake timer to trigger onopen
    vi.advanceTimersByTime(20);

    expect(client.getStatus()).toBe("CONNECTED");
    expect(statusUpdates).toContain("CONNECTED");

    const socket = MockWebSocket.instances[0];
    expect(socket.sentMessages.length).toBe(1);
    const sentCmd = JSON.parse(socket.sentMessages[0]);
    expect(sentCmd).toEqual({
      type: "subscribe",
      from_sequence: 10,
      from_tick: undefined,
    });
  });

  it("parses valid envelope and invokes registered event listeners", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    const receivedEvents: WebSocketEventEnvelope[] = [];
    client.onEvent((evt) => receivedEvents.push(evt));

    client.connect("run_01");
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];
    const mockEnvelope: WebSocketEventEnvelope = {
      event_type: "vehicle.state",
      run_id: "run_01",
      sequence: 1,
      tick: 0,
      timestamp_s: 0.0,
      schema_version: "1.0.0",
      payload: { vehicle_id: "veh_01", speed_mps: 5.0 },
    };

    socket.receiveMessage(JSON.stringify(mockEnvelope));

    expect(receivedEvents.length).toBe(1);
    expect(receivedEvents[0]).toEqual(mockEnvelope);
  });

  it("handles malformed JSON and binary frames defensively without throwing", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    const receivedEvents: WebSocketEventEnvelope[] = [];
    client.onEvent((evt) => receivedEvents.push(evt));

    client.connect("run_01");
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];

    // Malformed JSON text
    socket.receiveMessage("{ invalid json");
    // Binary frame (not a string)
    socket.receiveMessage(new ArrayBuffer(8));
    // Missing required fields
    socket.receiveMessage(JSON.stringify({ not_an_envelope: true }));

    expect(receivedEvents.length).toBe(0);
    expect(client.getStatus()).toBe("CONNECTED");
  });

  it("responds to server heartbeat ping with client heartbeat", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    client.connect("run_01");
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];
    socket.receiveMessage(
      JSON.stringify({
        event_type: "heartbeat",
        run_id: "run_01",
        sequence: 5,
        tick: 1,
        timestamp_s: 0.1,
        schema_version: "1.0.0",
        payload: { server_time_s: 100 },
      })
    );

    // Initial subscribe + heartbeat reply
    expect(socket.sentMessages.length).toBe(2);
    expect(JSON.parse(socket.sentMessages[1])).toEqual({ type: "heartbeat" });
  });

  it("stops reconnecting immediately on 4404 Run Not Found", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    client.connect("missing_run");
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];
    socket.simulateClose(4404, "Run Not Found");

    expect(client.getStatus()).toBe("ERROR");
    // Verify no new socket instance was created
    expect(MockWebSocket.instances.length).toBe(1);
  });

  it("reconnects with backoff up to max attempts on transient disconnection", () => {
    const client = new SimulationWebSocketClient({
      wsBaseUrl: "ws://test-server/ws/v1",
      maxReconnectAttempts: 2,
      initialReconnectDelayMs: 100,
    });

    client.connect("run_01");
    vi.advanceTimersByTime(20);
    expect(client.getStatus()).toBe("CONNECTED");

    // 1st disconnect
    MockWebSocket.instances[0].simulateClose(1006);
    expect(client.getStatus()).toBe("RECONNECTING");

    // Advance 100ms for 1st retry
    vi.advanceTimersByTime(110);
    expect(MockWebSocket.instances.length).toBe(2);

    // 2nd disconnect
    MockWebSocket.instances[1].simulateClose(1006);
    expect(client.getStatus()).toBe("RECONNECTING");

    // Advance 150ms for 2nd retry
    vi.advanceTimersByTime(160);
    expect(MockWebSocket.instances.length).toBe(3);

    // 3rd disconnect exceeds maxReconnectAttempts (2)
    MockWebSocket.instances[2].simulateClose(1006);
    expect(client.getStatus()).toBe("ERROR");
  });

  it("cleans up connection and timers on disconnect()", () => {
    const client = new SimulationWebSocketClient({ wsBaseUrl: "ws://test-server/ws/v1" });
    client.connect("run_01");
    vi.advanceTimersByTime(20);

    client.disconnect();
    expect(client.getStatus()).toBe("DISCONNECTED");

    // Ensure no new reconnect occurs
    vi.advanceTimersByTime(5000);
    expect(MockWebSocket.instances.length).toBe(1);
  });
});
