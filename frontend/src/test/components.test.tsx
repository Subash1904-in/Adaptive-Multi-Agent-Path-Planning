import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Header } from "../components/Header";
import { ScenarioSelector } from "../features/scenarios/ScenarioSelector";
import { TelemetryFeed } from "../features/telemetry/TelemetryFeed";
import { MetricsPanel } from "../features/telemetry/MetricsPanel";
import { EntityInspector } from "../features/simulation/EntityInspector";
import type { RunMetrics, RunStatus, ScenarioSummary, VehicleState } from "../types/simulation";
import type { WebSocketEventEnvelope } from "../types/websocket";

describe("Component Unit Tests", () => {
  describe("Header", () => {
    it("renders application title and research disclaimer", () => {
      render(<Header connectionStatus="DISCONNECTED" runId={null} />);
      expect(screen.getByText("Adaptive Multi-Agent Path Planning")).toBeInTheDocument();
      expect(screen.getByText("Research & Educational Simulation")).toBeInTheDocument();
      expect(screen.getByText("DISCONNECTED")).toBeInTheDocument();
    });

    it("displays active run ID and triggers onReconnect when in ERROR state", () => {
      const handleReconnect = vi.fn();
      render(
        <Header
          connectionStatus="ERROR"
          runId="run_demo_123"
          onReconnect={handleReconnect}
        />
      );

      expect(screen.getByText("run_demo_123")).toBeInTheDocument();
      expect(screen.getByText("ERROR")).toBeInTheDocument();

      const reconnectBtn = screen.getByRole("button", { name: /reconnect/i });
      fireEvent.click(reconnectBtn);
      expect(handleReconnect).toHaveBeenCalledTimes(1);
    });
  });

  describe("ScenarioSelector", () => {
    const mockScenarios: ScenarioSummary[] = [
      {
        id: "scn_01",
        name: "Grid 3x3",
        description: "Standard synthetic grid",
        version: "1.0.0",
        author: "Dev",
        vehicle_count: 5,
        road_network_source: "synthetic_grid",
        time_step_s: 0.1,
        max_ticks: 200,
        effective_max_ticks: 200,
      },
    ];

    it("renders scenario selector options and triggers selection change", async () => {
      const onSelect = vi.fn();
      const onCreate = vi.fn();

      render(
        <ScenarioSelector
          scenarios={mockScenarios}
          selectedScenarioId="scn_01"
          onSelectScenario={onSelect}
          onCreateRun={onCreate}
          currentRun={null}
          onStepRun={vi.fn()}
          onCancelRun={vi.fn()}
          isLoading={false}
          actionError={null}
        />
      );

      expect(screen.getByLabelText(/select scenario/i)).toHaveValue("scn_01");
      expect(screen.getByText("Standard synthetic grid")).toBeInTheDocument();
      expect(screen.getByText("Vehicles: 5")).toBeInTheDocument();

      const initBtn = screen.getByRole("button", { name: /create and initialize/i });
      fireEvent.click(initBtn);
      await waitFor(() => expect(initBtn).toBeEnabled());
      expect(onCreate).toHaveBeenCalledWith("scn_01", 100);
    });

    it("displays active run status and handles stepping controls", async () => {
      const mockRun: RunStatus = {
        run_id: "run_active_42",
        scenario_id: "scn_01",
        scenario_name: "Grid 3x3",
        lifecycle_state: "RUNNING",
        current_tick: 15,
        elapsed_time_s: 1.5,
        is_terminal: false,
        arrived_count: 1,
        active_count: 4,
        total_vehicles: 5,
        scenario_fingerprint: "abc",
        initial_world_state_fingerprint: "def",
        commit_sha: "123",
        disclaimer: "Academic only",
      };

      const onStep = vi.fn();
      const onCancel = vi.fn();

      render(
        <ScenarioSelector
          scenarios={mockScenarios}
          selectedScenarioId="scn_01"
          onSelectScenario={vi.fn()}
          onCreateRun={vi.fn()}
          currentRun={mockRun}
          onStepRun={onStep}
          onCancelRun={onCancel}
          isLoading={false}
          actionError="Temporary warning"
        />
      );

      expect(screen.getByText("#run_active_42")).toBeInTheDocument();
      expect(screen.getByText("15")).toBeInTheDocument(); // current tick
      expect(screen.getByText("1.5s")).toBeInTheDocument(); // elapsed time
      expect(screen.getByText("1/5")).toBeInTheDocument(); // arrived count
      expect(screen.getByRole("alert")).toHaveTextContent("Temporary warning");

      const step1Btn = screen.getByRole("button", { name: /step \+1$/i });
      fireEvent.click(step1Btn);
      await waitFor(() => expect(step1Btn).toBeEnabled());
      expect(onStep).toHaveBeenCalledWith(1, false);

      const step10Btn = screen.getByRole("button", { name: /step \+10/i });
      fireEvent.click(step10Btn);
      await waitFor(() => expect(step10Btn).toBeEnabled());
      expect(onStep).toHaveBeenCalledWith(10, false);

      const runEndBtn = screen.getByRole("button", { name: /run to end/i });
      fireEvent.click(runEndBtn);
      await waitFor(() => expect(runEndBtn).toBeEnabled());
      expect(onStep).toHaveBeenCalledWith(0, true);

      const cancelBtn = screen.getByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);
      await waitFor(() => expect(cancelBtn).toBeEnabled());
      expect(onCancel).toHaveBeenCalledTimes(1);
    });
  });

  describe("TelemetryFeed", () => {
    it("renders empty state message when no events exist", () => {
      render(<TelemetryFeed events={[]} latestGap={null} />);
      expect(
        screen.getByText(/no telemetry events received yet/i)
      ).toBeInTheDocument();
    });

    it("renders event list and telemetry gap banner", () => {
      const mockEvents: WebSocketEventEnvelope[] = [
        {
          event_type: "vehicle.state",
          run_id: "run_01",
          sequence: 1,
          tick: 0,
          timestamp_s: 0.0,
          schema_version: "1.0.0",
          payload: { vehicle_id: "veh_01", speed_mps: 8.5, lifecycle_state: "en_route" },
        },
        {
          event_type: "safety.event",
          run_id: "run_01",
          sequence: 2,
          tick: 1,
          timestamp_s: 0.1,
          schema_version: "1.0.0",
          payload: { vehicle_id: "veh_01", other_id: "veh_02", action: "braking" },
        },
      ];

      const onClearGap = vi.fn();
      render(
        <TelemetryFeed
          events={mockEvents}
          latestGap={{ reason: "buffer_overflow", dropped_count: 12 }}
          onClearGap={onClearGap}
        />
      );

      expect(screen.getByText(/telemetry gap detected/i)).toBeInTheDocument();
      expect(screen.getByText(/12 non-critical events dropped/i)).toBeInTheDocument();
      expect(screen.getByText(/Vehicle veh_01: speed=8.5m\/s/i)).toBeInTheDocument();
      expect(screen.getByText(/Safety conflict: veh_01 with veh_02/i)).toBeInTheDocument();

      const dismissBtn = screen.getByRole("button", { name: /dismiss telemetry gap/i });
      fireEvent.click(dismissBtn);
      expect(onClearGap).toHaveBeenCalledTimes(1);
    });
  });

  describe("MetricsPanel", () => {
    it("renders default 0 values when metrics is null without crashing", () => {
      render(<MetricsPanel metrics={null} />);
      expect(screen.getByText("Cross-Subsystem Metrics")).toBeInTheDocument();
      expect(screen.getByText("0.0 m")).toBeInTheDocument();
      expect(screen.getByText("100.0%")).toBeInTheDocument();
    });

    it("renders populated metrics values correctly", () => {
      const mockMetrics: RunMetrics = {
        run_id: "run_01",
        lifecycle_state: "RUNNING",
        current_tick: 50,
        disclaimer: "Academic only",
        metrics: {
          kinematics: {
            total_distance_traveled_m: 350.5,
            average_speed_mps: 7.2,
            max_speed_observed_mps: 12.0,
          },
          communication: {
            messages_sent: 45,
            messages_delivered: 44,
            packet_delivery_ratio: 0.978,
          },
          safety: {
            actual_collisions: 0,
            near_misses: 2,
          },
          routing: {
            reroutes_accepted: 3,
          },
          pedestrians: {
            crosswalk_crossings_completed: 4,
          },
          emergency: {
            corridors_created: 1,
          },
        },
      };

      render(<MetricsPanel metrics={mockMetrics} />);
      expect(screen.getByText("350.5 m")).toBeInTheDocument();
      expect(screen.getByText("7.2 m/s")).toBeInTheDocument();
      expect(screen.getByText("97.8%")).toBeInTheDocument();
      expect(screen.getByText("45")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  describe("EntityInspector", () => {
    it("returns null when entity is not selected", () => {
      const { container } = render(
        <EntityInspector
          entityId={null}
          entityType={null}
          onClose={vi.fn()}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it("renders vehicle details and calls onClose", () => {
      const mockVehicle: VehicleState = {
        vehicle_id: "veh_alpha",
        vehicle_type: "standard",
        position: { x: 45.0, y: 80.0 },
        heading_rad: 1.5708,
        speed_mps: 11.2,
        lifecycle_state: "en_route",
        route: ["node_r0_c0", "node_r0_c1", "node_r1_c1"],
      };

      const onClose = vi.fn();
      render(
        <EntityInspector
          entityId="veh_alpha"
          entityType="vehicle"
          vehicleState={mockVehicle}
          onClose={onClose}
        />
      );

      expect(screen.getByText("VEHICLE AGENT")).toBeInTheDocument();
      expect(screen.getByText("veh_alpha")).toBeInTheDocument();
      expect(screen.getByText(/11.20 m\/s/i)).toBeInTheDocument();
      expect(screen.getByText("(45.0, 80.0)")).toBeInTheDocument();
      expect(screen.getByText("node_r0_c0 → node_r0_c1 → node_r1_c1")).toBeInTheDocument();

      const closeBtn = screen.getByRole("button", { name: /close entity inspector/i });
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
