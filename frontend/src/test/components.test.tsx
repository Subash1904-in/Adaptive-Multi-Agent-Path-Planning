import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Header } from "../components/Header";
import { ScenarioSelector } from "../features/scenarios/ScenarioSelector";
import { TelemetryFeed } from "../features/telemetry/TelemetryFeed";
import { MetricsPanel } from "../features/telemetry/MetricsPanel";
import { EntityInspector } from "../features/simulation/EntityInspector";
import { SimulationViewer3D } from "../features/scene3d/SimulationViewer3D";
import { PlaybackBar } from "../features/playback/PlaybackBar";
import type { RunMetrics, RunStatus, ScenarioSummary, VehicleState } from "../types/simulation";
import type { WebSocketEventEnvelope } from "../types/websocket";
import type { TimelineRange } from "../types/playback";
import type { RouteSubsystemSnapshot } from "../types/routing";

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
      expect(screen.getByText(/LIVE \(Interpolated\)/i)).toBeInTheDocument();
      expect(screen.getByText("Sedan")).toBeInTheDocument();

      const closeBtn = screen.getByRole("button", { name: /close entity inspector/i });
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("renders emergency vehicle details, priority, and stale indication", () => {
      const mockEmergency: VehicleState = {
        vehicle_id: "amb_01",
        vehicle_type: "emergency",
        emergency_type: "ambulance",
        is_emergency: true,
        priority_level: 2,
        position: { x: 120.0, y: 40.0 },
        heading_rad: 0,
        speed_mps: 18.0,
        lifecycle_state: "en_route",
        tick: 42,
        simulation_time_s: 4.2,
        is_stale: true,
      };

      render(
        <EntityInspector
          entityId="amb_01"
          entityType="vehicle"
          vehicleState={mockEmergency}
          onClose={vi.fn()}
        />
      );

      expect(screen.getByText("Ambulance")).toBeInTheDocument();
      expect(screen.getByText(/ACTIVE \(ambulance\)/i)).toBeInTheDocument();
      expect(screen.getByText("Level 2")).toBeInTheDocument();
      expect(screen.getByText("Tick #42 • 4.20s")).toBeInTheDocument();
      expect(screen.getByText(/STALE \(Last Known State\)/i)).toBeInTheDocument();
    });

    it("renders pedestrian agent details and crosswalk information", () => {
      const mockPedestrian = {
        pedestrian_id: "ped_cross_01",
        position: { x: 50.0, y: 52.0 },
        heading_rad: 3.1415,
        speed_mps: 1.4,
        lifecycle_state: "crossing",
        crosswalk_id: "cw_node_r1_c1_north",
        tick: 15,
        simulation_time_s: 1.5,
      };

      render(
        <EntityInspector
          entityId="ped_cross_01"
          entityType="pedestrian"
          pedestrianState={mockPedestrian}
          onClose={vi.fn()}
        />
      );

      expect(screen.getByText("PEDESTRIAN AGENT")).toBeInTheDocument();
      expect(screen.getByText("ped_cross_01")).toBeInTheDocument();
      expect(screen.getByText("crossing")).toBeInTheDocument();
      expect(screen.getByText("cw_node_r1_c1_north")).toBeInTheDocument();
      expect(screen.getByText("Tick #15 • 1.50s")).toBeInTheDocument();
    });

    it("renders vehicle route telemetry, remaining distance, reroute reason, and candidate paths", () => {
      const mockVehicle: VehicleState = {
        vehicle_id: "veh_route_1",
        vehicle_type: "standard",
        position: { x: 10.0, y: 20.0 },
        heading_rad: 0,
        speed_mps: 12.0,
        lifecycle_state: "en_route",
        route_id: "route_alpha",
        route: ["node_0", "node_1", "node_2"],
        remaining_route_distance_m: 48.0,
      };

      const mockRouteSnapshot: RouteSubsystemSnapshot = {
        tick: 15,
        timestampS: 1.5,
        activeRoutes: new Map([
          [
            "veh_route_1",
            {
              vehicleId: "veh_route_1",
              routeId: "route_alpha",
              nodeIds: ["node_0", "node_1", "node_2"],
              edgeIds: ["edge_0_1", "edge_1_2"],
              worldPoints: [
                { x: 0, y: 0.12, z: 0 },
                { x: 50, y: 0.12, z: 0 },
                { x: 100, y: 0.12, z: 0 },
              ],
              totalDistanceM: 120.0,
              remainingDistanceM: 48.0,
              currentEdgeId: "edge_0_1",
              currentNodeId: "node_0",
              isRerouted: true,
            },
          ],
        ]),
        plannedRoutes: new Map(),
        candidateRoutes: new Map([
          [
            "veh_route_1",
            [
              {
                id: "cand_alt_1",
                vehicleId: "veh_route_1",
                nodeIds: ["node_0", "node_detour", "node_2"],
                edgeIds: ["edge_0_detour", "edge_detour_2"],
                worldPoints: [
                  { x: 0, y: 0.12, z: 0 },
                  { x: 50, y: 0.12, z: 50 },
                  { x: 100, y: 0.12, z: 0 },
                ],
                objectiveCost: 95.0,
                costImprovement: 25.0,
                isAccepted: true,
                evaluationTick: 15,
              },
            ],
          ],
        ]),
        rerouteEvents: [
          {
            id: "reroute_veh_route_1_15_1",
            vehicleId: "veh_route_1",
            tick: 15,
            simulationTimeS: 1.5,
            decisionType: "reroute_accepted",
            isAccepted: true,
            oldRouteId: "route_orig",
            newRouteId: "route_alpha",
            reason: "High traffic congestion detected on edge E1",
            hasExplicitReason: true,
            currentCost: 120.0,
            candidateCost: 95.0,
            costImprovement: 25.0,
            candidateNodeIds: ["node_0", "node_detour", "node_2"],
            candidateEdgeIds: ["edge_0_detour", "edge_detour_2"],
            markerPosition: { x: 10.0, y: 0.5, z: 20.0 },
          },
        ],
      };

      const onSelectCandidate = vi.fn();
      render(
        <EntityInspector
          entityId="veh_route_1"
          entityType="vehicle"
          vehicleState={mockVehicle}
          routeSnapshot={mockRouteSnapshot}
          onClose={vi.fn()}
          onSelectCandidate={onSelectCandidate}
        />
      );

      // Routing Header & Provenance
      expect(screen.getByText("Routing & Path Telemetry")).toBeInTheDocument();
      expect(screen.getByText("Authoritative Telemetry")).toBeInTheDocument();

      // Route ID and Distances
      expect(screen.getByText("route_alpha")).toBeInTheDocument();
      expect(screen.getByText("120 m")).toBeInTheDocument();
      expect(screen.getByText("48 m")).toBeInTheDocument();

      // Progress Bar: (1 - 48 / 120) * 100 = 60%
      expect(screen.getByText("60%")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");

      // ETA disclaimer
      expect(screen.getByText("Estimated Arrival:")).toBeInTheDocument();

      // Path nodes
      expect(screen.getByText("node_0 → node_1 → node_2")).toBeInTheDocument();

      // Reroute Evaluation Card
      expect(screen.getByText("Last Reroute Evaluation")).toBeInTheDocument();
      expect(screen.getByText("reroute_accepted")).toBeInTheDocument();
      expect(screen.getByText("Tick #15 (1.50s)")).toBeInTheDocument();
      expect(screen.getByText("route_orig → route_alpha")).toBeInTheDocument();
      expect(screen.getByText("High traffic congestion detected on edge E1")).toBeInTheDocument();
      expect(screen.getByText("Authoritative Backend Decision Reason")).toBeInTheDocument();
      expect(screen.getByText("120")).toBeInTheDocument();
      expect(screen.getByText("95")).toBeInTheDocument();
      expect(screen.getByText("25")).toBeInTheDocument();

      // Candidate Paths
      expect(screen.getByText("Evaluated Candidate Paths (1)")).toBeInTheDocument();
      expect(screen.getByText("cand_alt_1")).toBeInTheDocument();
      expect(screen.getByText("node_0 → node_detour → node_2")).toBeInTheDocument();

      // Inspect Candidate Button
      const inspectBtn = screen.getByRole("button", { name: /inspect candidate path cand_alt_1/i });
      fireEvent.click(inspectBtn);
      expect(onSelectCandidate).toHaveBeenCalledWith("cand_alt_1");
    });

    it("displays honest unprovided fallbacks when route distance telemetry is absent", () => {
      const mockVehicle: VehicleState = {
        vehicle_id: "veh_no_telemetry",
        vehicle_type: "standard",
        position: { x: 0, y: 0 },
        heading_rad: 0,
        speed_mps: 5.0,
        lifecycle_state: "en_route",
      };

      render(
        <EntityInspector
          entityId="veh_no_telemetry"
          entityType="vehicle"
          vehicleState={mockVehicle}
          routeSnapshot={null}
          onClose={vi.fn()}
        />
      );

      expect(screen.getByText("Routing & Path Telemetry")).toBeInTheDocument();
      expect(screen.getByText("Unavailable")).toBeInTheDocument();
      expect(screen.getAllByText("Not provided by backend")).toHaveLength(2);
    });
  });

  describe("SimulationViewer3D", () => {
    it("renders viewport with HUD controls and toggles lighting mode, camera projection, and buildings", () => {
      render(
        <SimulationViewer3D
          scenario={null}
          vehicles={new Map()}
          pedestrians={new Map()}
          signals={new Map()}
        />
      );

      // Verify viewport container is present
      expect(screen.getByLabelText("3D Simulation Viewport")).toBeInTheDocument();

      // Verify HUD Buttons
      const dayNightBtn = screen.getByRole("button", { name: /switch to night mode/i });
      expect(dayNightBtn).toHaveTextContent("☀️ Day");

      const projBtn = screen.getByRole("button", { name: /switch to orthographic projection/i });
      expect(projBtn).toHaveTextContent("📷 3D Persp");

      const bldBtn = screen.getByRole("button", { name: /hide procedural buildings/i });
      expect(bldBtn).toHaveTextContent("🏢 Buildings ON");

      const resetBtn = screen.getByRole("button", { name: /reset camera view/i });
      expect(resetBtn).toBeInTheDocument();

      // Test Day / Night Toggle
      fireEvent.click(dayNightBtn);
      expect(screen.getByRole("button", { name: /switch to day mode/i })).toHaveTextContent("🌙 Night");

      // Test Camera Projection Toggle
      fireEvent.click(projBtn);
      expect(screen.getByRole("button", { name: /switch to perspective projection/i })).toHaveTextContent("📐 2D Ortho");

      // Test Buildings Toggle
      fireEvent.click(bldBtn);
      expect(screen.getByRole("button", { name: /show procedural buildings/i })).toHaveTextContent("🏢 Buildings OFF");

      // Test Reset View Click
      fireEvent.click(resetBtn);

      // Verify Scene Legend
      expect(screen.getByText("Vehicle")).toBeInTheDocument();
      expect(screen.getByText("Emergency")).toBeInTheDocument();
      expect(screen.getByText("Pedestrian")).toBeInTheDocument();
      expect(screen.getByText("Signal")).toBeInTheDocument();
      expect(screen.getByText("Lane Marking")).toBeInTheDocument();
    });

    it("displays loading state overlay when isLoading is true", () => {
      render(
        <SimulationViewer3D
          scenario={null}
          vehicles={new Map()}
          pedestrians={new Map()}
          signals={new Map()}
          isLoading={true}
        />
      );

      expect(screen.getByText("Loading 3D Simulation Environment...")).toBeInTheDocument();
    });

    it("displays historical review banner when isReviewing is true and triggers onReturnToLive", () => {
      const handleReturnToLive = vi.fn();
      render(
        <SimulationViewer3D
          scenario={null}
          vehicles={new Map()}
          pedestrians={new Map()}
          signals={new Map()}
          isReviewing={true}
          reviewTick={14}
          onReturnToLive={handleReturnToLive}
        />
      );

      expect(screen.getByText("🕒 HISTORICAL REVIEW — TICK 14")).toBeInTheDocument();
      const returnBtn = screen.getByRole("button", { name: /return to live/i });
      fireEvent.click(returnBtn);
      expect(handleReturnToLive).toHaveBeenCalledTimes(1);
    });

    it("renders V2V HUD overlay toggles and opens collapsible V2V legend with actual metrics", () => {
      const mockCommSnap = {
        tick: 20,
        timestampS: 2.0,
        rangeM: 50.0,
        links: [
          { id: "v1<->v2", vehicleA: "v1", vehicleB: "v2", status: "active" as const },
        ],
        networkState: {
          enabled: true,
          rangeM: 50.0,
          channelState: "good" as const,
          activePartitions: [["v1", "v2"]],
          totalBroadcasts: 20,
          totalDelivered: 19,
          totalDropped: 1,
          inTransitCount: 0,
          packetDeliveryRatio: 0.95,
          recentDrops: {
            outOfRange: 0,
            packetLoss: 1,
            burstLoss: 0,
            linkOutage: 0,
            partition: 0,
            unavailable: 0,
            expired: 0,
            duplicate: 0,
            invalid: 0,
          },
        },
      };

      render(
        <SimulationViewer3D
          scenario={null}
          vehicles={new Map()}
          pedestrians={new Map()}
          signals={new Map()}
          communicationSnapshot={mockCommSnap}
        />
      );

      // Verify V2V Controls Toolbar
      expect(screen.getByRole("toolbar", { name: "V2V Overlay Controls" })).toBeInTheDocument();

      // Test Links toggle
      const linksBtn = screen.getByRole("button", { name: /hide v2v links/i });
      expect(linksBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(linksBtn);
      expect(screen.getByRole("button", { name: /show v2v links/i })).toHaveAttribute("aria-pressed", "false");

      // Test Range toggle
      const rangeBtn = screen.getByRole("button", { name: /hide range ring/i });
      expect(rangeBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(rangeBtn);
      expect(screen.getByRole("button", { name: /show range ring/i })).toHaveAttribute("aria-pressed", "false");

      // Test Reset V2V Defaults button
      const resetV2vBtn = screen.getByRole("button", { name: /reset v2v overlays to defaults/i });
      fireEvent.click(resetV2vBtn);
      expect(screen.getByRole("button", { name: /hide v2v links/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /hide range ring/i })).toHaveAttribute("aria-pressed", "true");

      // Test V2V Legend Toggle
      const legendToggleBtn = screen.getByRole("button", { name: /open v2v legend/i });
      expect(screen.queryByLabelText("V2V Visual Legend and Network State")).not.toBeInTheDocument();

      fireEvent.click(legendToggleBtn);
      expect(screen.getByLabelText("V2V Visual Legend and Network State")).toBeInTheDocument();
      expect(screen.getByText("Active Neighbor Link (Confirmed)")).toBeInTheDocument();
      expect(screen.getByText("Stale / Degraded Link (Timeout)")).toBeInTheDocument();
      expect(screen.getByText("Radio Range: 50.0 m")).toBeInTheDocument();
      expect(screen.getByText("GOOD")).toBeInTheDocument();
      expect(screen.getByText("95.0%")).toBeInTheDocument();

      // Close legend via X button
      const closeLegendBtn = screen.getByRole("button", { name: /dismiss v2v legend panel/i });
      fireEvent.click(closeLegendBtn);
      expect(screen.queryByLabelText("V2V Visual Legend and Network State")).not.toBeInTheDocument();
    });

    it("renders Route overlay HUD toggles and opens collapsible Route Legend", () => {
      render(
        <SimulationViewer3D
          scenario={null}
          vehicles={new Map()}
          pedestrians={new Map()}
          signals={new Map()}
        />
      );

      // Verify Route Controls Toolbar
      expect(screen.getByRole("toolbar", { name: "Route Overlay Controls" })).toBeInTheDocument();

      // Active Route toggle
      const activeBtn = screen.getByRole("button", { name: /hide active route$/i });
      expect(activeBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(activeBtn);
      expect(screen.getByRole("button", { name: /show active route$/i })).toHaveAttribute("aria-pressed", "false");

      // Planned Route toggle
      const plannedBtn = screen.getByRole("button", { name: /hide planned route$/i });
      expect(plannedBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(plannedBtn);
      expect(screen.getByRole("button", { name: /show planned route$/i })).toHaveAttribute("aria-pressed", "false");

      // Candidate Paths toggle
      const candBtn = screen.getByRole("button", { name: /hide candidate paths/i });
      expect(candBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(candBtn);
      expect(screen.getByRole("button", { name: /show candidate paths/i })).toHaveAttribute("aria-pressed", "false");

      // Reroute Markers toggle
      const markersBtn = screen.getByRole("button", { name: /hide reroute markers/i });
      expect(markersBtn).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(markersBtn);
      expect(screen.getByRole("button", { name: /show reroute markers/i })).toHaveAttribute("aria-pressed", "false");

      // Reset Routes Defaults button
      const resetRoutesBtn = screen.getByRole("button", { name: /reset route overlays to defaults/i });
      fireEvent.click(resetRoutesBtn);
      expect(screen.getByRole("button", { name: /hide active route$/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /hide planned route$/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /hide candidate paths/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /hide reroute markers/i })).toHaveAttribute("aria-pressed", "true");

      // Route Legend Toggle
      const legendBtn = screen.getByRole("button", { name: /open route legend/i });
      expect(screen.queryByLabelText("Route Visual Legend and Alternative Paths")).not.toBeInTheDocument();

      fireEvent.click(legendBtn);
      expect(screen.getByLabelText("Route Visual Legend and Alternative Paths")).toBeInTheDocument();
      expect(screen.getByText("Active Route (Authoritative Path)")).toBeInTheDocument();
      expect(screen.getByText("Planned Route (Baseline Comparison)")).toBeInTheDocument();
      expect(screen.getByText("Alternative Candidate (Evaluated)")).toBeInTheDocument();
      expect(screen.getByText("Inspected Candidate Path")).toBeInTheDocument();
      expect(screen.getByText("Accepted Reroute Decision")).toBeInTheDocument();
      expect(screen.getByText("Rejected / Insufficient Benefit")).toBeInTheDocument();

      // Dismiss route legend
      const dismissBtn = screen.getByRole("button", { name: /dismiss route legend panel/i });
      fireEvent.click(dismissBtn);
      expect(screen.queryByLabelText("Route Visual Legend and Alternative Paths")).not.toBeInTheDocument();
    });
  });

  describe("PlaybackBar", () => {
    const defaultTimeline: TimelineRange = {
      earliestTick: 0,
      latestTick: 50,
      currentTick: 25,
      simulationTimeS: 2.5,
      maxTicks: 100,
      isLive: true,
      activeReviewTick: null,
      bufferedCount: 26,
    };

    it("renders controls, timeline range, speed options, and mode badge", () => {
      render(
        <PlaybackBar
          playbackState="ready"
          speed={1}
          timeline={defaultTimeline}
          isTerminal={false}
          canPlay={true}
          canStep={true}
          onPlay={vi.fn()}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onStep={vi.fn()}
          onSetSpeed={vi.fn()}
          onSeekTick={vi.fn()}
          onReturnToLive={vi.fn()}
        />
      );

      expect(screen.getByRole("button", { name: /play simulation playback/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /advance simulation by 1 tick/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /advance simulation by 10 ticks/i })).toBeInTheDocument();
      expect(screen.getByText("LIVE STREAM")).toBeInTheDocument();
      expect(screen.getByText("READY")).toBeInTheDocument();
      expect(screen.getByText(/26 frames in memory/i)).toBeInTheDocument();
      expect(screen.getByRole("slider", { name: /timeline position scrubber/i })).toHaveValue("25");
    });

    it("handles transport clicks (play, pause, step +1, step +10, speed, seek)", () => {
      const onPlay = vi.fn();
      const onPause = vi.fn();
      const onResume = vi.fn();
      const onStep = vi.fn();
      const onSetSpeed = vi.fn();
      const onSeekTick = vi.fn();

      const { rerender } = render(
        <PlaybackBar
          playbackState="ready"
          speed={1}
          timeline={defaultTimeline}
          isTerminal={false}
          canPlay={true}
          canStep={true}
          onPlay={onPlay}
          onPause={onPause}
          onResume={onResume}
          onStep={onStep}
          onSetSpeed={onSetSpeed}
          onSeekTick={onSeekTick}
          onReturnToLive={vi.fn()}
        />
      );

      // Click Play
      fireEvent.click(screen.getByRole("button", { name: /play simulation playback/i }));
      expect(onPlay).toHaveBeenCalledTimes(1);

      // Re-render as playing
      rerender(
        <PlaybackBar
          playbackState="playing"
          speed={1}
          timeline={defaultTimeline}
          isTerminal={false}
          canPlay={true}
          canStep={false}
          onPlay={onPlay}
          onPause={onPause}
          onResume={onResume}
          onStep={onStep}
          onSetSpeed={onSetSpeed}
          onSeekTick={onSeekTick}
          onReturnToLive={vi.fn()}
        />
      );

      // Click Pause
      fireEvent.click(screen.getByRole("button", { name: /pause simulation playback/i }));
      expect(onPause).toHaveBeenCalledTimes(1);

      // Re-render as paused
      rerender(
        <PlaybackBar
          playbackState="paused"
          speed={1}
          timeline={defaultTimeline}
          isTerminal={false}
          canPlay={true}
          canStep={true}
          onPlay={onPlay}
          onPause={onPause}
          onResume={onResume}
          onStep={onStep}
          onSetSpeed={onSetSpeed}
          onSeekTick={onSeekTick}
          onReturnToLive={vi.fn()}
        />
      );

      // Click Step +1 and +10
      fireEvent.click(screen.getByRole("button", { name: /advance simulation by 1 tick/i }));
      expect(onStep).toHaveBeenCalledWith(1);

      fireEvent.click(screen.getByRole("button", { name: /advance simulation by 10 ticks/i }));
      expect(onStep).toHaveBeenCalledWith(10);

      // Click speed
      fireEvent.click(screen.getByRole("button", { name: /2x playback speed/i }));
      expect(onSetSpeed).toHaveBeenCalledWith(2);

      // Scrub timeline
      const slider = screen.getByRole("slider", { name: /timeline position scrubber/i });
      fireEvent.change(slider, { target: { value: "10" } });
      expect(onSeekTick).toHaveBeenCalledWith(10);
    });

    it("displays historical review badge and return to live button when reviewing", () => {
      const onReturnToLive = vi.fn();
      render(
        <PlaybackBar
          playbackState="reviewing"
          speed={1}
          timeline={{
            ...defaultTimeline,
            isLive: false,
            activeReviewTick: 12,
          }}
          isTerminal={false}
          canPlay={true}
          canStep={true}
          onPlay={vi.fn()}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onStep={vi.fn()}
          onSetSpeed={vi.fn()}
          onSeekTick={vi.fn()}
          onReturnToLive={onReturnToLive}
        />
      );

      expect(screen.getByText("🕒 REVIEW (Tick 12)")).toBeInTheDocument();
      const returnBtn = screen.getByRole("button", { name: /return to live simulation view/i });
      fireEvent.click(returnBtn);
      expect(onReturnToLive).toHaveBeenCalledTimes(1);
    });

    it("disables transport and step controls when run is terminal", () => {
      render(
        <PlaybackBar
          playbackState="completed"
          speed={1}
          timeline={defaultTimeline}
          isTerminal={true}
          canPlay={false}
          canStep={false}
          onPlay={vi.fn()}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onStep={vi.fn()}
          onSetSpeed={vi.fn()}
          onSeekTick={vi.fn()}
          onReturnToLive={vi.fn()}
        />
      );

      expect(screen.getByRole("button", { name: /play simulation playback/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /advance simulation by 1 tick/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /advance simulation by 10 ticks/i })).toBeDisabled();
      expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    });
  });
});

