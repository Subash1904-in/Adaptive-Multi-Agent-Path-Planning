import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { OperationalDashboard } from "../features/analytics/OperationalDashboard";
import type { RunMetrics, RunStatus } from "../types/simulation";
import type { OperationalAnalytics } from "../types/analytics";

describe("OperationalDashboard & Analytics Tests", () => {
  const mockRunStatus: RunStatus = {
    run_id: "run_operational_test",
    scenario_id: "scn_downtown_dense",
    scenario_name: "Downtown Dense Grid",
    lifecycle_state: "RUNNING",
    current_tick: 42,
    elapsed_time_s: 4.2,
    is_terminal: false,
    active_count: 5,
    arrived_count: 3,
    total_vehicles: 8,
    scenario_fingerprint: "fp_test_123",
    initial_world_state_fingerprint: "init_fp_123",
    commit_sha: "c764a52",
    disclaimer: "AMAPP Educational Simulation",
  };

  const sampleAnalytics: OperationalAnalytics = {
    trips: {
      total_trips: 8,
      completed_trips: 3,
      active_trips: 5,
      completion_rate_pct: 37.5,
      travel_time: {
        sample_count: 3,
        mean_s: 12.4,
        median_s: 11.8,
        p90_s: 14.5,
        p95_s: 14.8,
        min_s: 10.2,
        max_s: 15.1,
        bins: [
          { bin_start_s: 10.0, bin_end_s: 12.0, count: 2 },
          { bin_start_s: 12.0, bin_end_s: 14.0, count: 0 },
          { bin_start_s: 14.0, bin_end_s: 16.0, count: 1 },
        ],
      },
    },
    throughput: {
      total_crossings: 18,
      crossings_per_minute: 257.14,
      signalized_crossings: 12,
      unsignalized_crossings: 6,
      top_intersections: [
        { node_id: "node_center_cross", crossings: 12, is_signalized: true },
        { node_id: "node_north_junction", crossings: 6, is_signalized: false },
      ],
    },
    safety: {
      actual_collisions: 0,
      near_misses: 1,
      emergency_brakes: 1,
      control_overrides: 0,
      min_separation_observed_m: 1.8,
      min_ttc_observed_s: 1.2,
      collision_rate_per_minute: 0.0,
      near_miss_rate_per_minute: 14.28,
      near_miss_frequency_per_tick: 0.0238,
    },
    communication: {
      messages_sent: 50,
      messages_delivered: 48,
      messages_lost: 2,
      messages_expired: 0,
      packet_delivery_ratio: 0.96,
      packet_loss_rate: 0.04,
      loss_by_reason: {},
      latency_packets_queued: 0,
      latency_packets_delivered: 48,
      latency_continuous_ms: null,
      latency_ms_available: false,
      disclaimer: "Discrete model",
    },
    routing: {
      reroutes_evaluated: 4,
      reroutes_accepted: 3,
      reroutes_rejected: 1,
      acceptance_rate_pct: 75.0,
      active_rerouted_vehicles: 2,
    },
    incidents: {
      total_active_incidents: 1,
      active_by_type: {
        ROAD_CLOSURE: 1,
      },
      resolved_incidents: 1,
    },
    time_series: [
      {
        tick: 10,
        simulation_time_s: 1.0,
        completed_trips: 0,
        trips_completed: 0,
        active_vehicles: 8,
        total_distance_m: 50.0,
        avg_speed_mps: 5.0,
        intersection_crossings: 4,
        collisions: 0,
        near_misses: 0,
        v2v_pdr: 1.0,
        reroutes_accepted: 0,
        active_incidents: 0,
      },
      {
        tick: 20,
        simulation_time_s: 2.0,
        completed_trips: 1,
        trips_completed: 1,
        active_vehicles: 7,
        total_distance_m: 120.0,
        avg_speed_mps: 7.2,
        intersection_crossings: 9,
        collisions: 0,
        near_misses: 1,
        v2v_pdr: 0.95,
        reroutes_accepted: 1,
        active_incidents: 1,
      },
      {
        tick: 40,
        simulation_time_s: 4.0,
        completed_trips: 3,
        trips_completed: 3,
        active_vehicles: 5,
        total_distance_m: 245.5,
        avg_speed_mps: 8.5,
        intersection_crossings: 18,
        collisions: 0,
        near_misses: 1,
        v2v_pdr: 0.96,
        reroutes_accepted: 3,
        active_incidents: 1,
      },
    ],
  };

  const mockRunMetricsWithAnalytics: RunMetrics = {
    run_id: "run_operational_test",
    lifecycle_state: "RUNNING",
    current_tick: 42,
    disclaimer: "AMAPP Research & Educational Simulation",
    metrics: {
      kinematics: {
        total_distance_traveled_m: 245.5,
        average_speed_mps: 8.5,
        max_speed_observed_mps: 12.0,
      },
      communication: {
        messages_sent: 50,
        messages_delivered: 48,
        packet_delivery_ratio: 0.96,
      },
      safety: {
        actual_collisions: 0,
        near_misses: 1,
      },
      routing: {
        reroutes_accepted: 3,
      },
      pedestrians: {
        crosswalk_crossings_completed: 2,
      },
      emergency: {
        corridors_created: 0,
      },
    },
    analytics: sampleAnalytics,
  };

  it("renders summary KPI cards with authoritative values", () => {
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
      />
    );

    // Trips completed
    expect(screen.getByTestId("kpi-trips-completed")).toHaveTextContent("3 / 8");
    // Completion rate
    expect(screen.getByTestId("kpi-completion-rate")).toHaveTextContent("37.5%");
    // Travel time
    expect(screen.getByTestId("kpi-mean-travel-time")).toHaveTextContent("12.4 s");
    // Collisions
    expect(screen.getByTestId("kpi-collision-events")).toHaveTextContent("0");
    // Near misses
    expect(screen.getByTestId("kpi-near-miss-events")).toHaveTextContent("1");
    // V2V PDR
    expect(screen.getByTestId("kpi-v2v-pdr")).toHaveTextContent("96.0%");
    // Active incidents
    expect(screen.getByTestId("kpi-active-incidents")).toHaveTextContent("1");
    // Simulation tick & status
    expect(screen.getByTestId("kpi-sim-tick-status")).toHaveTextContent("Tick 42");
    expect(screen.getByTestId("kpi-sim-tick-status")).toHaveTextContent("RUNNING");
  });

  it("displays honest 'Unavailable' labels when metrics are null or unmeasured", () => {
    const emptyMetrics: RunMetrics = {
      run_id: "run_empty",
      lifecycle_state: "INITIALIZED",
      current_tick: 0,
      disclaimer: "Test disclaimer",
      metrics: {},
      analytics: {
        trips: {
          total_trips: 0,
          completed_trips: 0,
          active_trips: 0,
          completion_rate_pct: null,
          travel_time: {
            sample_count: 0,
            mean_s: null,
            median_s: null,
            p90_s: null,
            p95_s: null,
            min_s: null,
            max_s: null,
            bins: [],
          },
        },
        throughput: {
          total_crossings: 0,
          crossings_per_minute: 0.0,
          signalized_crossings: 0,
          unsignalized_crossings: 0,
          top_intersections: [],
        },
        safety: {
          actual_collisions: 0,
          near_misses: 0,
          emergency_brakes: 0,
          control_overrides: 0,
          min_separation_observed_m: null,
          min_ttc_observed_s: null,
          collision_rate_per_minute: 0.0,
          near_miss_rate_per_minute: 0.0,
          near_miss_frequency_per_tick: null,
        },
        communication: {
          messages_sent: 0,
          messages_delivered: 0,
          messages_lost: 0,
          messages_expired: 0,
          packet_delivery_ratio: null,
          packet_loss_rate: null,
          loss_by_reason: {},
          latency_packets_queued: 0,
          latency_packets_delivered: 0,
          latency_continuous_ms: null,
          latency_ms_available: false,
          disclaimer: "No messages",
        },
        routing: {
          reroutes_evaluated: 0,
          reroutes_accepted: 0,
          reroutes_rejected: 0,
          acceptance_rate_pct: null,
        },
        incidents: {
          total_active_incidents: 0,
          active_by_type: {},
          resolved_incidents: 0,
        },
        time_series: [],
      },
    };

    render(
      <OperationalDashboard
        metrics={emptyMetrics}
        currentRun={null}
      />
    );

    // Completion rate should display Unavailable rather than 0% or NaN
    expect(screen.getByTestId("kpi-completion-rate")).toHaveTextContent("Unavailable");
    // Travel time mean should display Unavailable
    expect(screen.getByTestId("kpi-mean-travel-time")).toHaveTextContent("Unavailable");
    // PDR should display Unavailable
    expect(screen.getByTestId("kpi-v2v-pdr")).toHaveTextContent("Unavailable");
    // Histogram empty state message
    expect(screen.getByText("No completed trips yet")).toBeInTheDocument();
  });

  it("switches category tabs and filters displayed metrics", () => {
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
      />
    );

    // Check default tab is active
    const allTab = screen.getByRole("tab", { name: /All KPIs/i });
    expect(allTab).toHaveAttribute("aria-selected", "true");

    // Switch to Safety & Hazards tab
    const safetyTab = screen.getByRole("tab", { name: /Safety & Hazards/i });
    fireEvent.click(safetyTab);
    expect(safetyTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("kpi-collision-events")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-near-miss-events")).toBeInTheDocument();

    // Switch to V2V Network tab
    const commsTab = screen.getByRole("tab", { name: /V2V Network/i });
    fireEvent.click(commsTab);
    expect(commsTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("kpi-v2v-pdr")).toBeInTheDocument();
  });

  it("renders SVG travel-time distribution histogram bars and legend", () => {
    const { container } = render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
      />
    );

    // Look for svg histogram rects
    const histogramRects = container.querySelectorAll(".histogram-svg rect");
    expect(histogramRects.length).toBeGreaterThanOrEqual(3);

    // Travel time stats bar
    expect(screen.getByText(/Median: 11\.8s/i)).toBeInTheDocument();
    expect(screen.getByText(/P90: 14\.5s/i)).toBeInTheDocument();
    expect(screen.getByText(/P95: 14\.8s/i)).toBeInTheDocument();
    expect(screen.getByText(/Min: 10\.2s/i)).toBeInTheDocument();
    expect(screen.getByText(/Max: 15\.1s/i)).toBeInTheDocument();
  });

  it("renders top intersection crossings and incident type breakdown", () => {
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
      />
    );

    expect(screen.getByText("node_center_cross")).toBeInTheDocument();
    expect(screen.getByText(/12 crossings/i)).toBeInTheDocument();
    expect(screen.getByText("node_north_junction")).toBeInTheDocument();
    expect(screen.getByText(/6 crossings/i)).toBeInTheDocument();

    expect(screen.getByText("ROAD CLOSURE")).toBeInTheDocument();
  });

  it("triggers onRefreshMetrics when applying time-window filters", () => {
    const handleRefresh = vi.fn();
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
        onRefreshMetrics={handleRefresh}
      />
    );

    const startInput = screen.getByLabelText(/Window Start \(s\)/i);
    const endInput = screen.getByLabelText(/Window End \(s\)/i);
    const applyBtn = screen.getByRole("button", { name: /^Apply$/i });

    fireEvent.change(startInput, { target: { value: "1.5" } });
    fireEvent.change(endInput, { target: { value: "3.5" } });
    fireEvent.click(applyBtn);

    expect(handleRefresh).toHaveBeenCalledWith({
      time_window_start_s: 1.5,
      time_window_end_s: 3.5,
    });
  });

  it("triggers onRefreshMetrics with empty params when resetting filters", () => {
    const handleRefresh = vi.fn();
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
        onRefreshMetrics={handleRefresh}
      />
    );

    const startInput = screen.getByLabelText(/Window Start \(s\)/i);
    fireEvent.change(startInput, { target: { value: "1.0" } });

    const resetBtn = screen.getByRole("button", { name: /^Reset$/i });
    fireEvent.click(resetBtn);

    expect(startInput).toHaveValue(null);
    expect(handleRefresh).toHaveBeenCalledWith({});
  });

  it("displays historical review banner when reviewing past ticks", () => {
    const handleReturn = vi.fn();
    render(
      <OperationalDashboard
        metrics={mockRunMetricsWithAnalytics}
        currentRun={mockRunStatus}
        isReviewing={true}
        reviewTick={20}
        onReturnToLive={handleReturn}
      />
    );

    expect(
      screen.getByText(/Historical Review Mode:/i)
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/Tick #20/i).length
    ).toBeGreaterThanOrEqual(1);

    const returnBtn = screen.getAllByRole("button", { name: /Return to Live/i })[0];
    fireEvent.click(returnBtn);
    expect(handleReturn).toHaveBeenCalledTimes(1);
  });
});
