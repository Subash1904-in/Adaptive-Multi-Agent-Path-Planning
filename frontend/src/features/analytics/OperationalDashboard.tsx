import React, { useState, useMemo } from "react";
import type { RunMetrics, RunStatus } from "../../types/simulation";
import type {
  AnalyticsCategoryFilter,
  HistogramBin,
  MetricsQueryParams,
  OperationalAnalytics,
  TimeSeriesPoint,
  TravelTimeDistribution,
} from "../../types/analytics";

export interface OperationalDashboardProps {
  metrics: RunMetrics | null;
  currentRun?: RunStatus | null;
  isReviewing?: boolean;
  reviewTick?: number | null;
  isLoading?: boolean;
  onRefresh?: (query?: MetricsQueryParams) => void;
  onRefreshMetrics?: (query?: MetricsQueryParams) => void;
  onReturnToLive?: () => void;
}

export const OperationalDashboard: React.FC<OperationalDashboardProps> = ({
  metrics,
  currentRun,
  isReviewing = false,
  reviewTick = null,
  isLoading = false,
  onRefresh,
  onRefreshMetrics,
  onReturnToLive,
}) => {
  const refreshFn = onRefreshMetrics || onRefresh;
  const [selectedCategory, setSelectedCategory] = useState<AnalyticsCategoryFilter>("all");
  const [timeSeriesMetric, setTimeSeriesMetric] = useState<
    "completed_trips" | "crossings" | "speed" | "safety" | "incidents"
  >("completed_trips");

  // Time-window filter states
  const [windowStart, setWindowStart] = useState<string>("");
  const [windowEnd, setWindowEnd] = useState<string>("");
  const [windowError, setWindowError] = useState<string | null>(null);

  const analytics: OperationalAnalytics | undefined = metrics?.analytics;
  const legacyMetrics = metrics?.metrics;

  // Extract or synthesize trip metrics
  const tripData = useMemo(() => {
    const rawTrips = analytics?.trips;
    const registered = rawTrips?.total_trips ?? legacyMetrics?.simulation?.vehicles_registered ?? 0;
    const arrived = rawTrips?.completed_trips ?? legacyMetrics?.simulation?.vehicles_arrived ?? 0;
    const active = rawTrips?.active_trips ?? legacyMetrics?.simulation?.vehicles_active ?? 0;
    const rate = rawTrips?.completion_rate_pct ?? (registered > 0 ? (arrived / registered) * 100 : null);
    const rawTravelTime = rawTrips?.travel_time ?? (analytics as unknown as { travel_time?: TravelTimeDistribution })?.travel_time;

    return {
      total_trips: registered,
      completed_trips: arrived,
      active_trips: active,
      completion_rate_pct: rate,
      travel_time: rawTravelTime ?? {
        sample_count: 0,
        mean_s: null,
        median_s: null,
        p90_s: null,
        p95_s: null,
        min_s: null,
        max_s: null,
        bins: [],
      },
    };
  }, [analytics, legacyMetrics?.simulation]);

  // Extract throughput metrics
  const throughputData = useMemo(() => {
    const rawThroughput = analytics?.throughput;
    const nodeCrossings = (rawThroughput as unknown as { node_crossings?: Array<{ node_id: string; crossing_count: number; is_signalized?: boolean }> })?.node_crossings;
    const topIntersections = rawThroughput?.top_intersections ?? (nodeCrossings ? nodeCrossings.map((n) => ({
      node_id: n.node_id,
      crossings: n.crossing_count,
      is_signalized: n.is_signalized ?? false,
    })) : []);

    return {
      total_crossings: rawThroughput?.total_crossings ?? 0,
      crossings_per_minute: rawThroughput?.crossings_per_minute ?? 0,
      signalized_crossings: rawThroughput?.signalized_crossings ?? 0,
      unsignalized_crossings: rawThroughput?.unsignalized_crossings ?? 0,
      top_intersections: topIntersections,
    };
  }, [analytics?.throughput]);

  // Extract safety metrics
  const safetyData = useMemo(() => {
    const rawSafety = analytics?.safety;
    const col = rawSafety?.actual_collisions ?? legacyMetrics?.safety?.actual_collisions ?? 0;
    const nm = rawSafety?.near_misses ?? legacyMetrics?.safety?.near_misses ?? 0;
    return {
      actual_collisions: col,
      near_misses: nm,
      emergency_brakes: rawSafety?.emergency_brakes ?? 0,
      control_overrides: rawSafety?.control_overrides ?? 0,
      min_separation_observed_m: rawSafety?.min_separation_observed_m ?? null,
      min_ttc_observed_s: rawSafety?.min_ttc_observed_s ?? null,
      collision_rate_per_minute: rawSafety?.collision_rate_per_minute ?? 0,
      near_miss_rate_per_minute: rawSafety?.near_miss_rate_per_minute ?? 0,
    };
  }, [analytics?.safety, legacyMetrics?.safety]);

  // Extract communication metrics
  const commData = useMemo(() => {
    if (analytics?.communication) {
      return analytics.communication;
    }
    const sent = legacyMetrics?.communication?.messages_sent ?? 0;
    const delivered = legacyMetrics?.communication?.messages_delivered ?? 0;
    const pdr = legacyMetrics?.communication?.packet_delivery_ratio ?? null;
    return {
      messages_sent: sent,
      messages_delivered: delivered,
      messages_lost: Math.max(0, sent - delivered),
      messages_expired: 0,
      packet_delivery_ratio: pdr,
      packet_loss_rate: sent > 0 ? Math.max(0, 1.0 - (delivered / sent)) : null,
      loss_by_reason: {},
      loss_breakdown: {},
      latency_packets_queued: 0,
      latency_packets_delivered: delivered,
      latency_continuous_ms: null,
      latency_ms_available: false,
      disclaimer: "Continuous latency in milliseconds is not tracked by the discrete channel model.",
    };
  }, [analytics?.communication, legacyMetrics?.communication]);

  // Extract routing metrics
  const routingData = useMemo(() => {
    const rawRouting = analytics?.routing;
    const evalTotal = rawRouting?.reroutes_evaluated ?? (rawRouting as unknown as { reroutes_attempted?: number })?.reroutes_attempted ?? legacyMetrics?.routing?.reroutes_evaluated ?? 0;
    const accepted = rawRouting?.reroutes_accepted ?? legacyMetrics?.routing?.reroutes_accepted ?? 0;
    const rate = rawRouting?.acceptance_rate_pct ?? (rawRouting as unknown as { reroute_acceptance_rate_pct?: number })?.reroute_acceptance_rate_pct ?? (evalTotal > 0 ? (accepted / evalTotal) * 100 : null);
    return {
      reroutes_evaluated: evalTotal,
      reroutes_accepted: accepted,
      reroutes_rejected: Math.max(0, evalTotal - accepted),
      acceptance_rate_pct: rate,
    };
  }, [analytics?.routing, legacyMetrics?.routing]);

  // Extract incident metrics
  const incidentData = useMemo(() => {
    const rawIncidents = analytics?.incidents;
    const totalActive = rawIncidents?.total_active_incidents ?? rawIncidents?.total_active ?? (rawIncidents as unknown as { active_count?: number })?.active_count ?? 0;
    return {
      total_active_incidents: totalActive,
      total_active: totalActive,
      active_by_type: rawIncidents?.active_by_type ?? {},
      resolved_incidents: rawIncidents?.resolved_incidents ?? (rawIncidents as unknown as { cumulative_count?: number })?.cumulative_count ?? 0,
    };
  }, [analytics?.incidents]);

  // Time-series points
  const timeSeries: TimeSeriesPoint[] = useMemo(() => {
    return analytics?.time_series ?? [];
  }, [analytics?.time_series]);

  // Filter application handler
  const handleApplyWindow = () => {
    setWindowError(null);
    const startVal = windowStart.trim() !== "" ? parseFloat(windowStart) : undefined;
    const endVal = windowEnd.trim() !== "" ? parseFloat(windowEnd) : undefined;

    if (startVal !== undefined && isNaN(startVal)) {
      setWindowError("Window start must be a valid number");
      return;
    }
    if (endVal !== undefined && isNaN(endVal)) {
      setWindowError("Window end must be a valid number");
      return;
    }
    if (startVal !== undefined && startVal < 0) {
      setWindowError("Window start cannot be negative");
      return;
    }
    if (startVal !== undefined && endVal !== undefined && startVal > endVal) {
      setWindowError("Window start cannot be greater than window end");
      return;
    }

    if (refreshFn) {
      refreshFn({
        time_window_start_s: startVal,
        time_window_end_s: endVal,
      });
    }
  };

  const handleResetWindow = () => {
    setWindowStart("");
    setWindowEnd("");
    setWindowError(null);
    if (refreshFn) {
      refreshFn({});
    }
  };

  return (
    <div className="panel operational-dashboard-panel" aria-label="Operational Metrics Dashboard">
      {/* Header and Controls */}
      <div className="panel-header dashboard-header">
        <div className="dashboard-title-group">
          <h2 className="panel-title">Operational Metrics & Analytics</h2>
          <span className="live-status-pill">
            {isReviewing ? (
              <span className="review-badge">Historical Tick #{reviewTick}</span>
            ) : currentRun?.lifecycle_state ? (
              <span className={`status-badge status-${currentRun.lifecycle_state}`}>
                {currentRun.lifecycle_state.toUpperCase()}
              </span>
            ) : (
              <span className="status-badge status-idle">STANDBY</span>
            )}
          </span>
        </div>

        <div className="dashboard-actions">
          {isReviewing && onReturnToLive && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onReturnToLive}
              title="Return to live simulation telemetry"
            >
              Return to Live
            </button>
          )}
          {refreshFn && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => handleApplyWindow()}
              disabled={isLoading}
              title="Reconcile and refresh metrics"
            >
              {isLoading ? "Refreshing..." : "Refresh"}
            </button>
          )}
        </div>
      </div>

      {/* Historical Review Mode Banner */}
      {isReviewing && (
        <div className="historical-review-banner" role="status" aria-live="polite">
          <span className="banner-icon">⏮</span>
          <span className="banner-text">
            <strong>Historical Review Mode:</strong> Showing recorded metrics at Tick #{reviewTick}.
            Live execution is paused and simulation mutations are disabled.
          </span>
          {onReturnToLive && (
            <button
              type="button"
              className="btn-return-live-link"
              onClick={onReturnToLive}
            >
              Resume Live Stream →
            </button>
          )}
        </div>
      )}

      {/* Category Tabs */}
      <nav className="dashboard-category-tabs" role="tablist" aria-label="Analytics Categories">
        {(
          [
            ["all", "All KPIs"],
            ["trips", "Trips & Travel Times"],
            ["throughput", "Intersection Flow"],
            ["safety", "Safety & Hazards"],
            ["communication", "V2V Network"],
            ["routing", "Adaptive Routing"],
            ["incidents", "Active Incidents"],
          ] as [AnalyticsCategoryFilter, string][]
        ).map(([cat, label]) => (
          <button
            key={cat}
            type="button"
            role="tab"
            className={`tab-btn ${selectedCategory === cat ? "active" : ""}`}
            onClick={() => setSelectedCategory(cat)}
            aria-selected={selectedCategory === cat}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Time Window Boundary Filter */}
      <div className="window-filter-bar">
        <div className="filter-inputs">
          <label className="filter-label">
            Window Start (s):
            <input
              type="number"
              min="0"
              step="1"
              className="filter-input"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              placeholder="e.g. 0.0"
            />
          </label>
          <label className="filter-label">
            Window End (s):
            <input
              type="number"
              min="0"
              step="1"
              className="filter-input"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              placeholder="e.g. 60.0"
            />
          </label>
          <button
            type="button"
            className="btn btn-secondary btn-xs"
            onClick={handleApplyWindow}
            disabled={isLoading}
          >
            Apply
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={handleResetWindow}
            disabled={isLoading}
          >
            Reset
          </button>
        </div>
        {windowError && <span className="filter-error-msg">{windowError}</span>}
      </div>

      <div className="panel-body dashboard-content">
        {/* KPI Cards Grid */}
        <div className="kpi-grid">
          {/* Trip Completion */}
          {(selectedCategory === "all" || selectedCategory === "trips") && (
            <>
              <div className="kpi-card" data-testid="kpi-trips-completed">
                <div className="kpi-label">Completed Trips</div>
                <div className="kpi-value">
                  {tripData.completed_trips}
                  <span className="kpi-subtext"> / {tripData.total_trips} total</span>
                </div>
                <div className="kpi-footer" data-testid="kpi-completion-rate">
                  Completion Rate:{" "}
                  {tripData.completion_rate_pct !== null ? (
                    <strong>{tripData.completion_rate_pct.toFixed(1)}%</strong>
                  ) : (
                    <span className="text-muted">Unavailable</span>
                  )}
                </div>
              </div>

              <div className="kpi-card" data-testid="kpi-mean-travel-time">
                <div className="kpi-label">Mean Travel Time</div>
                <div className="kpi-value">
                  {tripData.travel_time.mean_s !== null ? (
                    <>{tripData.travel_time.mean_s.toFixed(1)} s</>
                  ) : (
                    <span className="text-muted">Unavailable</span>
                  )}
                </div>
                <div className="kpi-footer">
                  Median:{" "}
                  {tripData.travel_time.median_s !== null
                    ? `${tripData.travel_time.median_s.toFixed(1)} s`
                    : "Unavailable"}{" "}
                  | p90:{" "}
                  {tripData.travel_time.p90_s !== null
                    ? `${tripData.travel_time.p90_s.toFixed(1)} s`
                    : "Unavailable"}
                </div>
              </div>
            </>
          )}

          {/* Intersection Throughput */}
          {(selectedCategory === "all" || selectedCategory === "throughput") && (
            <>
              <div className="kpi-card" data-testid="kpi-throughput-total">
                <div className="kpi-label">Intersection Crossings</div>
                <div className="kpi-value">{throughputData.total_crossings}</div>
                <div className="kpi-footer">
                  Rate: <strong>{throughputData.crossings_per_minute.toFixed(1)}/min</strong> |
                  Signalized: {throughputData.signalized_crossings}
                </div>
              </div>
            </>
          )}

          {/* Safety & Collisions */}
          {(selectedCategory === "all" || selectedCategory === "safety") && (
            <>
              <div
                className={`kpi-card ${safetyData.actual_collisions > 0 ? "kpi-card-danger" : ""}`}
                data-testid="kpi-collision-events"
              >
                <div className="kpi-label">Collisions & Near-Misses</div>
                <div className="kpi-value">
                  <span className={safetyData.actual_collisions > 0 ? "text-danger" : ""}>
                    {safetyData.actual_collisions}
                  </span>
                  <span className="kpi-subtext" data-testid="kpi-near-miss-events">
                    {" "}col / {safetyData.near_misses} near-miss
                  </span>
                </div>
                <div className="kpi-footer">
                  Collision Rate: {safetyData.collision_rate_per_minute.toFixed(2)}/min | Near-miss
                  Rate: {safetyData.near_miss_rate_per_minute.toFixed(2)}/min
                </div>
              </div>

              <div className="kpi-card" data-testid="kpi-safety-extrema">
                <div className="kpi-label">Minimum Observed TTC / Headway</div>
                <div className="kpi-value">
                  {safetyData.min_ttc_observed_s !== null ? (
                    <>{safetyData.min_ttc_observed_s.toFixed(2)} s</>
                  ) : (
                    <span className="text-muted">Unavailable</span>
                  )}
                </div>
                <div className="kpi-footer">
                  Min Separation:{" "}
                  {safetyData.min_separation_observed_m !== null
                    ? `${safetyData.min_separation_observed_m.toFixed(1)} m`
                    : "Unavailable"}
                </div>
              </div>
            </>
          )}

          {/* V2V Communication */}
          {(selectedCategory === "all" || selectedCategory === "communication") && (
            <>
              <div className="kpi-card" data-testid="kpi-v2v-pdr">
                <div className="kpi-label">V2V Packet Delivery Ratio (PDR)</div>
                <div className="kpi-value">
                  {commData.packet_delivery_ratio !== null ? (
                    <>{(commData.packet_delivery_ratio * 100).toFixed(1)}%</>
                  ) : (
                    <span className="text-muted">Unavailable</span>
                  )}
                </div>
                <div className="kpi-footer">
                  Sent: {commData.messages_sent} | Delivered: {commData.messages_delivered} | Loss
                  Rate:{" "}
                  {commData.packet_loss_rate !== null
                    ? `${(commData.packet_loss_rate * 100).toFixed(1)}%`
                    : "Unavailable"}
                </div>
              </div>

              <div className="kpi-card" data-testid="kpi-v2v-latency">
                <div className="kpi-label">V2V Latency Queue Status</div>
                <div className="kpi-value">
                  {commData.latency_packets_queued}
                  <span className="kpi-subtext"> queued</span>
                </div>
                <div className="kpi-footer" title={commData.disclaimer}>
                  Continuous Latency: <span className="text-muted">Unavailable (Discrete)</span>
                </div>
              </div>
            </>
          )}

          {/* Adaptive Routing */}
          {(selectedCategory === "all" || selectedCategory === "routing") && (
            <>
              <div className="kpi-card" data-testid="kpi-rerouting">
                <div className="kpi-label">Adaptive Rerouting Activity</div>
                <div className="kpi-value">
                  {routingData.reroutes_accepted}
                  <span className="kpi-subtext"> / {routingData.reroutes_evaluated} evaluated</span>
                </div>
                <div className="kpi-footer">
                  Acceptance Rate:{" "}
                  {routingData.acceptance_rate_pct !== null ? (
                    <strong>{routingData.acceptance_rate_pct.toFixed(1)}%</strong>
                  ) : (
                    <span className="text-muted">Unavailable</span>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Active Incidents */}
          {(selectedCategory === "all" || selectedCategory === "incidents") && (
            <>
              <div className="kpi-card" data-testid="kpi-active-incidents">
                <div className="kpi-label">Active Roadway Incidents</div>
                <div className="kpi-value">
                  {incidentData.total_active_incidents}
                  <span className="kpi-subtext"> active</span>
                </div>
                <div className="kpi-footer">
                  Resolved: {incidentData.resolved_incidents} total
                </div>
              </div>
            </>
          )}

          {/* Simulation Progress & Status */}
          <div className="kpi-card" data-testid="kpi-sim-tick-status">
            <div className="kpi-label">Simulation Progress</div>
            <div className="kpi-value">
              Tick {currentRun?.current_tick ?? 0}
              <span className="kpi-subtext">
                {" "}({(currentRun?.elapsed_time_s ?? 0).toFixed(1)}s)
              </span>
            </div>
            <div className="kpi-footer">
              Status: <strong>{currentRun?.lifecycle_state ?? "STANDBY"}</strong>
            </div>
          </div>
        </div>

        {/* Charts Section */}
        <div className="charts-section">
          {/* Chart 1: Travel-Time Distribution Histogram */}
          {(selectedCategory === "all" || selectedCategory === "trips") && (
            <div className="chart-box" data-testid="chart-travel-time-histogram">
              <div className="chart-header">
                <h3 className="chart-title">Travel-Time Distribution (Completed Trips)</h3>
                <span className="chart-subtitle">
                  {tripData.travel_time.sample_count > 0 ? (
                    <>
                      {tripData.travel_time.sample_count} samples recorded
                      {tripData.travel_time.median_s !== null && ` | Median: ${tripData.travel_time.median_s.toFixed(1)}s`}
                      {tripData.travel_time.p90_s !== null && ` | P90: ${tripData.travel_time.p90_s.toFixed(1)}s`}
                      {tripData.travel_time.p95_s !== null && ` | P95: ${tripData.travel_time.p95_s.toFixed(1)}s`}
                      {tripData.travel_time.min_s !== null && ` | Min: ${tripData.travel_time.min_s.toFixed(1)}s`}
                      {tripData.travel_time.max_s !== null && ` | Max: ${tripData.travel_time.max_s.toFixed(1)}s`}
                    </>
                  ) : (
                    "No completed trip samples"
                  )}
                </span>
              </div>

              {tripData.travel_time.bins.length > 0 ? (
                <div className="svg-chart-container">
                  <TravelTimeHistogramSvg bins={tripData.travel_time.bins} />
                </div>
              ) : (
                <div className="chart-empty-state">
                  <span className="empty-icon">📊</span>
                  <p>No completed trips yet</p>
                  <span className="empty-subtext">
                    Travel times and histograms populate deterministically as vehicles arrive at
                    destinations.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Chart 2: Top Intersection Crossings */}
          {(selectedCategory === "all" || selectedCategory === "throughput") && (
            <div className="chart-box" data-testid="chart-top-intersections">
              <div className="chart-header">
                <h3 className="chart-title">Intersection Crossing Volume by Node</h3>
                <span className="chart-subtitle">Authoritative edge transition transitions</span>
              </div>

              {throughputData.top_intersections.length > 0 ? (
                <div className="intersection-bars-container">
                  {throughputData.top_intersections.map((node) => {
                    const maxVal = Math.max(
                      1,
                      ...throughputData.top_intersections.map((n) => n.crossings)
                    );
                    const pct = (node.crossings / maxVal) * 100;
                    return (
                      <div key={node.node_id} className="intersection-bar-row">
                        <div className="node-info">
                          <span className="node-id">{node.node_id}</span>
                          {node.is_signalized && (
                            <span className="signal-badge" title="Controlled by Traffic Signal">
                              SIGNAL
                            </span>
                          )}
                        </div>
                        <div className="bar-track">
                          <div
                            className="bar-fill"
                            style={{ width: `${pct}%` }}
                            role="progressbar"
                            aria-valuenow={node.crossings}
                            aria-valuemin={0}
                            aria-valuemax={maxVal}
                          />
                        </div>
                        <span className="crossing-count">{node.crossings} crossings</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="chart-empty-state">
                  <span className="empty-icon">🚦</span>
                  <p>No confirmed intersection crossings recorded yet.</p>
                  <span className="empty-subtext">
                    Crossings are registered when vehicle agents move across connected edge boundaries.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Chart 3: Active Incident Breakdown */}
          {(selectedCategory === "all" || selectedCategory === "incidents") && (
            <div className="chart-box" data-testid="chart-incidents-breakdown">
              <div className="chart-header">
                <h3 className="chart-title">Active Incidents by Classification</h3>
                <span className="chart-subtitle">
                  {incidentData.total_active_incidents} active hazards & roadway disruptions
                </span>
              </div>

              {Object.keys(incidentData.active_by_type).length > 0 ? (
                <div className="incident-types-grid">
                  {Object.entries(incidentData.active_by_type).map(([type, count]) => (
                    <div key={type} className="incident-type-badge-card">
                      <span className="inc-type-label">{type.replace("_", " ").toUpperCase()}</span>
                      <span className="inc-type-count">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="chart-empty-state">
                  <span className="empty-icon">🛡️</span>
                  <p>No active incidents on the road network.</p>
                  <span className="empty-subtext">
                    Use the Roadway Incident Injection panel to simulate lane closures, congestion,
                    or signal overrides.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Chart 4: Time-Series Trend */}
          <div className="chart-box chart-box-wide" data-testid="chart-time-series">
            <div className="chart-header chart-header-with-controls">
              <div>
                <h3 className="chart-title">Discrete Time-Series Trends</h3>
                <span className="chart-subtitle">
                  Authoritative progression across discrete simulation ticks
                </span>
              </div>

              <div className="chart-metric-selector">
                <label className="metric-sel-label">Series: </label>
                <select
                  className="metric-select"
                  value={timeSeriesMetric}
                  onChange={(e) =>
                    setTimeSeriesMetric(
                      e.target.value as "completed_trips" | "crossings" | "speed" | "safety" | "incidents"
                    )
                  }
                >
                  <option value="completed_trips">Completed Trips</option>
                  <option value="crossings">Intersection Crossings</option>
                  <option value="speed">Average Speed (m/s)</option>
                  <option value="safety">Collisions & Near-Misses</option>
                  <option value="incidents">Active Incidents</option>
                </select>
              </div>
            </div>

            {timeSeries.length > 0 ? (
              <div className="svg-chart-container">
                <TimeSeriesStepChartSvg points={timeSeries} metric={timeSeriesMetric} />
              </div>
            ) : (
              <div className="chart-empty-state">
                <span className="empty-icon">📈</span>
                <p>No time-series data points available.</p>
                <span className="empty-subtext">
                  Step or play the simulation run to collect bounded telemetry progression samples.
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Pure SVG Histogram for travel-time distribution.
 */
interface HistogramProps {
  bins: HistogramBin[];
}

const TravelTimeHistogramSvg: React.FC<HistogramProps> = ({ bins }) => {
  const width = 480;
  const height = 180;
  const padding = { top: 20, right: 20, bottom: 35, left: 40 };

  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const barWidth = Math.max(6, innerWidth / Math.max(1, bins.length) - 4);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="metrics-svg-chart histogram-svg"
      role="img"
      aria-label="Travel time distribution histogram"
    >
      {/* Horizontal guide lines */}
      {[0, 0.5, 1].map((ratio) => {
        const y = padding.top + innerHeight * (1 - ratio);
        const val = Math.round(maxCount * ratio);
        return (
          <g key={ratio}>
            <line
              x1={padding.left}
              y1={y}
              x2={width - padding.right}
              y2={y}
              stroke="var(--border-subtle, #334155)"
              strokeDasharray="3 3"
              strokeWidth="1"
            />
            <text
              x={padding.left - 6}
              y={y + 3}
              fontSize="10"
              fill="var(--text-muted, #94a3b8)"
              textAnchor="end"
            >
              {val}
            </text>
          </g>
        );
      })}

      {/* Bars */}
      {bins.map((b, i) => {
        const barHeight = (b.count / maxCount) * innerHeight;
        const x = padding.left + i * (innerWidth / bins.length) + 2;
        const y = padding.top + innerHeight - barHeight;
        return (
          <g key={i} className="histogram-bar-group">
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={Math.max(1, barHeight)}
              fill="var(--accent-primary, #0ea5e9)"
              rx="2"
            >
              <title>{`${b.bin_start_s.toFixed(1)}s - ${b.bin_end_s.toFixed(1)}s: ${b.count} samples`}</title>
            </rect>
            {b.count > 0 && (
              <text
                x={x + barWidth / 2}
                y={y - 4}
                fontSize="9"
                fill="var(--text-primary, #f8fafc)"
                textAnchor="middle"
              >
                {b.count}
              </text>
            )}
            <text
              x={x + barWidth / 2}
              y={height - padding.bottom + 14}
              fontSize="9"
              fill="var(--text-muted, #94a3b8)"
              textAnchor="middle"
            >
              {b.bin_start_s.toFixed(0)}s
            </text>
          </g>
        );
      })}

      {/* Axis title */}
      <text
        x={width / 2}
        y={height - 4}
        fontSize="10"
        fill="var(--text-muted, #94a3b8)"
        textAnchor="middle"
      >
        Travel Time (seconds)
      </text>
    </svg>
  );
};

/**
 * Pure SVG Step/Discrete line chart for time-series metrics.
 */
interface TimeSeriesProps {
  points: TimeSeriesPoint[];
  metric: "completed_trips" | "crossings" | "speed" | "safety" | "incidents";
}

const TimeSeriesStepChartSvg: React.FC<TimeSeriesProps> = ({ points, metric }) => {
  const width = 640;
  const height = 180;
  const padding = { top: 20, right: 25, bottom: 35, left: 45 };

  const getTime = (p: TimeSeriesPoint): number => {
    if (typeof p.timestamp_s === "number") return p.timestamp_s;
    if (typeof p.simulation_time_s === "number") return p.simulation_time_s;
    return Number(p.tick || 0) * 0.1;
  };

  const getMetricValue = (p: TimeSeriesPoint): number => {
    switch (metric) {
      case "completed_trips":
        return p.completed_trips ?? p.trips_completed ?? 0;
      case "crossings":
        return p.intersection_crossings ?? 0;
      case "speed":
        return p.avg_speed_mps ?? 0;
      case "safety":
        return (p.collisions ?? 0) + (p.near_misses ?? 0);
      case "incidents":
        return p.active_incidents ?? 0;
    }
  };

  const getMetricLabel = (): string => {
    switch (metric) {
      case "completed_trips":
        return "Trips Completed";
      case "crossings":
        return "Intersection Crossings";
      case "speed":
        return "Speed (m/s)";
      case "safety":
        return "Collisions & Near-Misses";
      case "incidents":
        return "Active Incidents";
    }
  };

  const values = points.map(getMetricValue);
  const minVal = 0;
  const maxVal = Math.max(1, ...values);
  const minTime = getTime(points[0]);
  const maxTime = Math.max(minTime + 0.1, getTime(points[points.length - 1]));

  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const getX = (t: number) => padding.left + ((t - minTime) / (maxTime - minTime)) * innerWidth;
  const getY = (v: number) => padding.top + innerHeight - ((v - minVal) / (maxVal - minVal)) * innerHeight;

  // Build discrete step-path string
  let pathD = "";
  points.forEach((p, i) => {
    const t = getTime(p);
    const x = getX(t);
    const y = getY(getMetricValue(p));
    if (i === 0) {
      pathD += `M ${x} ${y}`;
    } else {
      const prevY = getY(getMetricValue(points[i - 1]));
      // Discrete step line: horizontal to current x, then vertical to current y
      pathD += ` L ${x} ${prevY} L ${x} ${y}`;
    }
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="metrics-svg-chart"
      role="img"
      aria-label={`${getMetricLabel()} time-series chart`}
    >
      {/* Horizontal guide lines */}
      {[0, 0.5, 1].map((ratio) => {
        const y = padding.top + innerHeight * (1 - ratio);
        const val = minVal + (maxVal - minVal) * ratio;
        return (
          <g key={ratio}>
            <line
              x1={padding.left}
              y1={y}
              x2={width - padding.right}
              y2={y}
              stroke="var(--border-subtle, #334155)"
              strokeDasharray="3 3"
              strokeWidth="1"
            />
            <text
              x={padding.left - 6}
              y={y + 3}
              fontSize="10"
              fill="var(--text-muted, #94a3b8)"
              textAnchor="end"
            >
              {val < 10 ? val.toFixed(1) : Math.round(val)}
            </text>
          </g>
        );
      })}

      {/* Discrete Step Path */}
      <path
        d={pathD}
        fill="none"
        stroke="var(--accent-primary, #38bdf8)"
        strokeWidth="2"
      />

      {/* Discrete Point Markers */}
      {points.map((p, i) => {
        const t = getTime(p);
        const x = getX(t);
        const y = getY(getMetricValue(p));
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="3"
            fill="var(--accent-primary, #38bdf8)"
            stroke="var(--bg-surface, #0f172a)"
            strokeWidth="1.5"
          >
            <title>{`Tick ${p.tick} (${t.toFixed(1)}s): ${getMetricValue(p)}`}</title>
          </circle>
        );
      })}

      {/* X-axis labels */}
      <text
        x={padding.left}
        y={height - padding.bottom + 15}
        fontSize="9"
        fill="var(--text-muted, #94a3b8)"
      >
        {minTime.toFixed(1)}s
      </text>
      <text
        x={width - padding.right}
        y={height - padding.bottom + 15}
        fontSize="9"
        fill="var(--text-muted, #94a3b8)"
        textAnchor="end"
      >
        {maxTime.toFixed(1)}s
      </text>
      <text
        x={width / 2}
        y={height - 4}
        fontSize="10"
        fill="var(--text-muted, #94a3b8)"
        textAnchor="middle"
      >
        Simulation Time (seconds)
      </text>
    </svg>
  );
};
