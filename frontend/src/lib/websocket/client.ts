/**
 * Robust, typed WebSocket client for AMAPP simulation live streaming.
 * Integrates with ws://host/ws/v1/runs/{run_id}/ adhering to Protocol Schema 1.0.0.
 */

import type {
  ClientCommand,
  WebSocketConnectionStatus,
  WebSocketEventEnvelope,
} from "../../types/websocket";

export type EventHandler = (event: WebSocketEventEnvelope) => void;
export type StatusHandler = (status: WebSocketConnectionStatus, error?: string) => void;

export interface WebSocketClientOptions {
  wsBaseUrl?: string;
  autoSubscribe?: boolean;
  fromSequence?: number;
  fromTick?: number;
  maxReconnectAttempts?: number;
  initialReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
}

export class SimulationWebSocketClient {
  private readonly baseUrl: string;
  private readonly autoSubscribe: boolean;
  private readonly fromSequence?: number;
  private readonly fromTick?: number;
  private readonly maxReconnectAttempts: number;
  private readonly initialReconnectDelayMs: number;
  private readonly maxReconnectDelayMs: number;

  private socket: WebSocket | null = null;
  private runId: string | null = null;
  private status: WebSocketConnectionStatus = "DISCONNECTED";
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyClosed = false;

  private readonly eventListeners: Set<EventHandler> = new Set();
  private readonly statusListeners: Set<StatusHandler> = new Set();

  constructor(options?: WebSocketClientOptions) {
    this.autoSubscribe = options?.autoSubscribe ?? true;
    this.fromSequence = options?.fromSequence ?? 0;
    this.fromTick = options?.fromTick;
    this.maxReconnectAttempts = options?.maxReconnectAttempts ?? 5;
    this.initialReconnectDelayMs = options?.initialReconnectDelayMs ?? 1000;
    this.maxReconnectDelayMs = options?.maxReconnectDelayMs ?? 10000;

    if (options?.wsBaseUrl) {
      this.baseUrl = options.wsBaseUrl.replace(/\/+$/, "");
    } else if (typeof window !== "undefined") {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      this.baseUrl = `${proto}//${window.location.host}/ws/v1`;
    } else {
      this.baseUrl = "ws://127.0.0.1:8000/ws/v1";
    }
  }

  public getStatus(): WebSocketConnectionStatus {
    return this.status;
  }

  public getRunId(): string | null {
    return this.runId;
  }

  public onEvent(handler: EventHandler): () => void {
    this.eventListeners.add(handler);
    return () => {
      this.eventListeners.delete(handler);
    };
  }

  public onStatusChange(handler: StatusHandler): () => void {
    this.statusListeners.add(handler);
    handler(this.status);
    return () => {
      this.statusListeners.delete(handler);
    };
  }

  private setStatus(status: WebSocketConnectionStatus, error?: string): void {
    if (this.status !== status) {
      this.status = status;
      for (const listener of this.statusListeners) {
        try {
          listener(status, error);
        } catch (e) {
          console.error("Error in status listener:", e);
        }
      }
    }
  }

  public connect(runId: string): void {
    if (!runId || typeof runId !== "string" || !runId.trim()) {
      throw new Error("Invalid runId provided for WebSocket connection");
    }

    const cleanRunId = runId.trim();

    // If already connected to this run, do nothing
    if (this.socket && this.runId === cleanRunId && (this.status === "CONNECTED" || this.status === "CONNECTING")) {
      return;
    }

    this.disconnect();
    this.runId = cleanRunId;
    this.manuallyClosed = false;
    this.reconnectAttempts = 0;

    this.establishConnection();
  }

  private establishConnection(): void {
    if (!this.runId) return;

    this.clearReconnectTimer();
    this.setStatus(this.reconnectAttempts > 0 ? "RECONNECTING" : "CONNECTING");

    const endpoint = `${this.baseUrl}/runs/${encodeURIComponent(this.runId)}/`;

    try {
      this.socket = new WebSocket(endpoint);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to construct WebSocket";
      this.setStatus("ERROR", msg);
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.setStatus("CONNECTED");
      // Reset reconnect attempts after a short stable period to prevent infinite flapping loops
      setTimeout(() => {
        if (this.status === "CONNECTED") {
          this.reconnectAttempts = 0;
        }
      }, 5000);

      if (this.autoSubscribe) {
        this.sendCommand({
          type: "subscribe",
          from_sequence: this.fromSequence,
          from_tick: this.fromTick,
        });
      }
    };

    this.socket.onmessage = (messageEvent: MessageEvent) => {
      this.handleIncomingMessage(messageEvent.data);
    };

    this.socket.onerror = () => {
      this.setStatus("ERROR", "WebSocket connection error");
    };

    this.socket.onclose = (event: CloseEvent) => {
      this.socket = null;
      if (this.manuallyClosed) {
        this.setStatus("DISCONNECTED");
        return;
      }

      if (event.code === 4404) {
        this.setStatus("ERROR", `Simulation run '${this.runId}' not found (4404)`);
        return;
      }

      if (event.code === 4401) {
        this.setStatus("ERROR", "Unauthorized WebSocket origin (4401)");
        return;
      }

      this.scheduleReconnect();
    };
  }

  private handleIncomingMessage(rawData: unknown): void {
    if (typeof rawData !== "string") {
      // Discard binary frames
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      console.warn("Received malformed JSON over WebSocket, discarding.");
      return;
    }

    if (!parsed || typeof parsed !== "object") {
      return;
    }

    const envelope = parsed as Partial<WebSocketEventEnvelope>;

    // Validate standard envelope fields
    if (
      typeof envelope.event_type !== "string" ||
      typeof envelope.sequence !== "number" ||
      typeof envelope.tick !== "number"
    ) {
      return;
    }

    // Ping/Heartbeat auto-reply
    if (envelope.event_type === "heartbeat") {
      this.sendCommand({ type: "heartbeat" });
    }
    const rawObj = parsed as Record<string, unknown>;
    const simTime =
      typeof rawObj.simulation_time_s === "number"
        ? rawObj.simulation_time_s
        : typeof rawObj.timestamp_s === "number"
        ? rawObj.timestamp_s
        : 0;

    const fullEnvelope: WebSocketEventEnvelope = {
      ...(rawObj as Record<string, unknown>),
      event_type: envelope.event_type,
      run_id: String(rawObj.run_id || ""),
      sequence: envelope.sequence,
      tick: envelope.tick,
      timestamp_s: simTime,
      schema_version: String(rawObj.schema_version || "1.0.0"),
      payload: (rawObj.payload as Record<string, unknown>) || {},
    };
    for (const listener of this.eventListeners) {
      try {
        listener(fullEnvelope);
      } catch (err) {
        console.error("Error in WebSocket event listener:", err);
      }
    }
  }

  public sendCommand(cmd: ClientCommand): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    try {
      this.socket.send(JSON.stringify(cmd));
      return true;
    } catch (err) {
      console.error("Failed to send command over WebSocket:", err);
      return false;
    }
  }

  private scheduleReconnect(): void {
    if (this.manuallyClosed) return;

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.setStatus("ERROR", `Failed to reconnect after ${this.maxReconnectAttempts} attempts`);
      return;
    }

    this.reconnectAttempts += 1;
    this.setStatus("RECONNECTING");

    const delay = Math.min(
      this.initialReconnectDelayMs * Math.pow(1.5, this.reconnectAttempts - 1),
      this.maxReconnectDelayMs
    );

    this.clearReconnectTimer();
    this.reconnectTimer = setTimeout(() => {
      this.establishConnection();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  public disconnect(): void {
    this.manuallyClosed = true;
    this.clearReconnectTimer();
    this.reconnectAttempts = 0;

    if (this.socket) {
      try {
        this.socket.close(1000, "Client initiated disconnect");
      } catch {
        // Ignored
      }
      this.socket = null;
    }

    this.setStatus("DISCONNECTED");
  }

  public clearListeners(): void {
    this.eventListeners.clear();
    this.statusListeners.clear();
  }
}
