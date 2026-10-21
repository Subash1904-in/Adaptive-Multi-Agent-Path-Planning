/**
 * Typed REST API client for AMAPP simulation backend.
 * Integrates with endpoints defined in backend/apps/core/api/urls.py and docs/API.md.
 */

import type {
  RunCreateRequest,
  RunMetrics,
  RunStatus,
  ScenarioDefinition,
  ScenarioSummary,
} from "../../types/simulation";
import type {
  CreateIncidentPayload,
  IncidentListResponse,
  IncidentRecord,
} from "../../types/incidents";

export class ApiClientError extends Error {
  public readonly statusCode: number;
  public readonly errorCode?: string;
  public readonly details?: unknown;

  constructor(
    message: string,
    statusCode: number,
    errorCode?: string,
    details?: unknown
  ) {
    super(message);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.errorCode = errorCode;
    this.details = details;
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
}

export class SimulationApiClient {
  private readonly baseUrl: string;

  constructor(config?: ApiClientConfig) {
    const raw = config?.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
    // Strip all trailing slashes if present
    this.baseUrl = raw.replace(/\/+$/, "");
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    const url = `${this.baseUrl}${cleanEndpoint}`;

    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string> | undefined),
    };

    if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    let response: Response;
    try {
      response = await fetch(url, { ...options, headers });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Network error";
      throw new ApiClientError(`Request failed: ${msg}`, 0);
    }

    if (!response.ok) {
      let errorBody: Record<string, unknown> | null = null;
      try {
        errorBody = await response.json();
      } catch {
        // Response was not JSON
      }

      const message =
        (errorBody?.detail as string) ||
        (errorBody?.message as string) ||
        (errorBody?.title as string) ||
        `HTTP ${response.status} ${response.statusText}`;

      const errorCode = (errorBody?.error_code as string) || undefined;
      throw new ApiClientError(message, response.status, errorCode, errorBody);
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiClientError("Invalid JSON returned by server", response.status);
    }
  }

  /**
   * Health check probe.
   */
  public async getHealth(signal?: AbortSignal): Promise<{ status: string; service: string; version: string }> {
    return this.request("/health/", { method: "GET", signal });
  }

  /**
   * List all registered scenarios with compact summaries.
   */
  public async listScenarios(signal?: AbortSignal): Promise<ScenarioSummary[]> {
    return this.request<ScenarioSummary[]>("/scenarios/", { method: "GET", signal });
  }

  /**
   * Retrieve full definition of a scenario by ID.
   */
  public async getScenario(
    scenarioId: string,
    signal?: AbortSignal
  ): Promise<ScenarioDefinition> {
    return this.request<ScenarioDefinition>(
      `/scenarios/${encodeURIComponent(scenarioId)}/`,
      { method: "GET", signal }
    );
  }

  /**
   * Validate a scenario payload without registering it.
   */
  public async validateScenario(
    scenario: Partial<ScenarioDefinition>,
    signal?: AbortSignal
  ): Promise<{ valid: boolean; scenario_id?: string; scenario_name?: string }> {
    return this.request("/scenarios/validate/", {
      method: "POST",
      body: JSON.stringify(scenario),
      signal,
    });
  }

  /**
   * Create and initialize a new simulation run in READY state.
   */
  public async createRun(
    request: RunCreateRequest,
    signal?: AbortSignal
  ): Promise<RunStatus> {
    return this.request<RunStatus>("/runs/", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    });
  }

  /**
   * Retrieve point-in-time status of a simulation run.
   */
  public async getRun(runId: string, signal?: AbortSignal): Promise<RunStatus> {
    return this.request<RunStatus>(`/runs/${encodeURIComponent(runId)}/`, {
      method: "GET",
      signal,
    });
  }

  /**
   * Step a simulation run forward by N discrete ticks or execute to completion.
   */
  public async stepRun(
    runId: string,
    params?: { ticks?: number; run_to_completion?: boolean; target_accels?: Record<string, number> },
    signal?: AbortSignal
  ): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      `/runs/${encodeURIComponent(runId)}/step/`,
      {
        method: "POST",
        body: JSON.stringify(params || {}),
        signal,
      }
    );
  }

  /**
   * Request cooperative cancellation of an active run.
   */
  public async cancelRun(
    runId: string,
    reason?: string,
    signal?: AbortSignal
  ): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      `/runs/${encodeURIComponent(runId)}/cancel/`,
      {
        method: "POST",
        body: JSON.stringify({ reason: reason || "User requested cancellation" }),
        signal,
      }
    );
  }

  /**
   * Retrieve intermediate or completed execution results for a run.
   */
  public async getRunResult(
    runId: string,
    signal?: AbortSignal
  ): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      `/runs/${encodeURIComponent(runId)}/result/`,
      { method: "GET", signal }
    );
  }

  /**
   * Retrieve cross-subsystem aggregated metrics for a run.
   */
  public async getRunMetrics(
    runId: string,
    signal?: AbortSignal
  ): Promise<RunMetrics> {
    return this.request<RunMetrics>(
      `/runs/${encodeURIComponent(runId)}/metrics/`,
      { method: "GET", signal }
    );
  }

  /**
   * Query bounded telemetry stream records for a run.
   */
  public async getRunTelemetry(
    runId: string,
    query?: {
      record_type?: string;
      name?: string;
      tick_start?: number;
      tick_end?: number;
      limit?: number;
    },
    signal?: AbortSignal
  ): Promise<{
    run_id: string;
    total_records_buffered: number;
    query_returned_count: number;
    drop_stats: Record<string, unknown>;
    records: Array<Record<string, unknown>>;
  }> {
    const params = new URLSearchParams();
    if (query?.record_type) params.set("record_type", query.record_type);
    if (query?.name) params.set("name", query.name);
    if (query?.tick_start !== undefined) params.set("tick_start", String(query.tick_start));
    if (query?.tick_end !== undefined) params.set("tick_end", String(query.tick_end));
    if (query?.limit !== undefined) params.set("limit", String(query.limit));

    const qs = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/runs/${encodeURIComponent(runId)}/telemetry/${qs}`, {
      method: "GET",
      signal,
    });
  }

  /**
   * Enumerate incidents registered on a simulation run.
   */
  public async listIncidents(
    runId: string,
    statusFilter?: "active" | "resolved",
    signal?: AbortSignal
  ): Promise<IncidentListResponse> {
    const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
    return this.request<IncidentListResponse>(
      `/runs/${encodeURIComponent(runId)}/incidents/${qs}`,
      { method: "GET", signal }
    );
  }

  /**
   * Inject a new dynamic roadway incident into an active simulation run.
   */
  public async createIncident(
    runId: string,
    payload: CreateIncidentPayload,
    signal?: AbortSignal
  ): Promise<IncidentRecord> {
    return this.request<IncidentRecord>(
      `/runs/${encodeURIComponent(runId)}/incidents/`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        signal,
      }
    );
  }

  /**
   * Deactivate and remove an active incident, restoring baseline traversability.
   */
  public async removeIncident(
    runId: string,
    incidentId: string,
    signal?: AbortSignal
  ): Promise<IncidentRecord> {
    return this.request<IncidentRecord>(
      `/runs/${encodeURIComponent(runId)}/incidents/${encodeURIComponent(incidentId)}/`,
      { method: "DELETE", signal }
    );
  }
}

export const defaultApiClient = new SimulationApiClient();
