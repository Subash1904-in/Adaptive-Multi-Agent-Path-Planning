import React, { useEffect, useMemo, useRef, useState } from "react";
import { Header } from "../components/Header";
import { EntityInspector } from "../features/simulation/EntityInspector";
import { ScenarioSelector } from "../features/scenarios/ScenarioSelector";
import { SimulationViewer3D } from "../features/scene3d/SimulationViewer3D";
import { MetricsPanel } from "../features/telemetry/MetricsPanel";
import { TelemetryFeed } from "../features/telemetry/TelemetryFeed";
import { defaultApiClient } from "../lib/api/client";
import { SimulationWebSocketClient } from "../lib/websocket/client";
import type {
  PedestrianState,
  RunMetrics,
  RunStatus,
  ScenarioDefinition,
  ScenarioSummary,
  TrafficSignalState,
  VehicleState,
} from "../types/simulation";
import type {
  TelemetryGapPayload,
  WebSocketConnectionStatus,
  WebSocketEventEnvelope,
} from "../types/websocket";

export const App: React.FC = () => {
  // Scenario & Run State
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [selectedScenario, setSelectedScenario] = useState<ScenarioDefinition | null>(null);
  const [currentRun, setCurrentRun] = useState<RunStatus | null>(null);
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [isLoadingScenarios, setIsLoadingScenarios] = useState<boolean>(true);
  const [actionError, setActionError] = useState<string | null>(null);

  // Entities & Telemetry Stream State
  const [vehicles, setVehicles] = useState<Map<string, VehicleState>>(new Map());
  const [pedestrians, setPedestrians] = useState<Map<string, PedestrianState>>(new Map());
  const [signals, setSignals] = useState<Map<string, TrafficSignalState>>(new Map());
  const [telemetryEvents, setTelemetryEvents] = useState<WebSocketEventEnvelope[]>([]);
  const [latestGap, setLatestGap] = useState<TelemetryGapPayload | null>(null);

  // Selection
  const [selectedEntity, setSelectedEntity] = useState<{
    id: string;
    type: "vehicle" | "pedestrian";
  } | null>(null);

  // WebSocket Connection State
  const [wsStatus, setWsStatus] = useState<WebSocketConnectionStatus>("DISCONNECTED");
  const wsClientRef = useRef<SimulationWebSocketClient>(new SimulationWebSocketClient());

  // 1. Initial Load: Fetch Scenarios
  useEffect(() => {
    let isMounted = true;
    async function loadScenarios() {
      setIsLoadingScenarios(true);
      setActionError(null);
      try {
        const list = await defaultApiClient.listScenarios();
        if (!isMounted) return;
        setScenarios(list);
        if (list.length > 0) {
          setSelectedScenarioId(list[0].id);
        }
      } catch (err) {
        if (!isMounted) return;
        const msg = err instanceof Error ? err.message : "Failed to load scenarios";
        setActionError(`Backend connection failed: ${msg}`);
      } finally {
        if (isMounted) setIsLoadingScenarios(false);
      }
    }
    loadScenarios();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Fetch Selected Scenario Definition
  useEffect(() => {
    if (!selectedScenarioId) {
      setSelectedScenario(null);
      return;
    }
    let isMounted = true;
    async function loadScenarioDetail() {
      try {
        const scn = await defaultApiClient.getScenario(selectedScenarioId);
        if (!isMounted) return;
        setSelectedScenario(scn);

        // Prepopulate vehicle positions from scenario definition if no active run
        if (!currentRun || currentRun.scenario_id !== selectedScenarioId) {
          const initVehicles = new Map<string, VehicleState>();
          for (const v of scn.vehicles) {
            initVehicles.set(v.vehicle_id, {
              vehicle_id: v.vehicle_id,
              position: { x: 0, y: 0 },
              speed_mps: v.initial_speed_mps || 0,
              heading_rad: 0,
              lifecycle_state: "READY",
              vehicle_type: v.vehicle_type || "standard",
            });
          }
          setVehicles(initVehicles);

          const initSignals = new Map<string, TrafficSignalState>();
          if (scn.signals) {
            for (const sig of scn.signals) {
              initSignals.set(sig.signal_id, {
                signal_id: sig.signal_id,
                node_id: sig.node_id,
                state: "RED",
              });
            }
          }
          setSignals(initSignals);
        }
      } catch (err) {
        console.warn("Failed to load scenario details:", err);
      }
    }
    loadScenarioDetail();
    return () => {
      isMounted = false;
    };
  }, [selectedScenarioId, currentRun]);

  // 3. Setup WebSocket Client Listeners & Connection to Active Run
  useEffect(() => {
    const wsClient = wsClientRef.current;

    const unbindStatus = wsClient.onStatusChange((status) => {
      setWsStatus(status);
    });

    const unbindEvents = wsClient.onEvent((event) => {
      // 1. Append to telemetry events (max 100)
      setTelemetryEvents((prev) => [event, ...prev.slice(0, 99)]);

      const p = event.payload as Record<string, unknown>;
      if (!p) return;

      // 2. Process Domain Events
      switch (event.event_type) {
        case "telemetry.gap":
          setLatestGap(p as unknown as TelemetryGapPayload);
          break;

        case "vehicle.state": {
          const vId = String(p.vehicle_id);
          const pos = p.position as { x: number; y: number } | undefined;
          if (vId && pos) {
            setVehicles((prev) => {
              const next = new Map(prev);
              next.set(vId, {
                vehicle_id: vId,
                position: pos,
                speed_mps: Number(p.speed_mps || 0),
                heading_rad: Number(p.heading_rad || 0),
                lifecycle_state: String(p.lifecycle_state || "en_route"),
                vehicle_type: (p.vehicle_type as "standard" | "emergency") || "standard",
                route: p.route as string[] | undefined,
                current_edge_id: p.current_edge_id as string | undefined,
                is_emergency: vId.toLowerCase().startsWith("amb_") || p.vehicle_type === "emergency",
              });
              return next;
            });
          }
          break;
        }

        case "pedestrian.state": {
          const pId = String(p.pedestrian_id);
          const pos = p.position as { x: number; y: number } | undefined;
          if (pId && pos) {
            setPedestrians((prev) => {
              const next = new Map(prev);
              next.set(pId, {
                pedestrian_id: pId,
                position: pos,
                speed_mps: Number(p.speed_mps || 0),
                heading_rad: Number(p.heading_rad || 0),
                lifecycle_state: String(p.lifecycle_state || "walking"),
                crosswalk_id: p.crosswalk_id as string | undefined,
              });
              return next;
            });
          }
          break;
        }

        case "traffic_signals.update": {
          const sigId = String(p.signal_id);
          if (sigId) {
            setSignals((prev) => {
              const next = new Map(prev);
              next.set(sigId, {
                signal_id: sigId,
                node_id: String(p.node_id),
                state: (p.state as "RED" | "YELLOW" | "GREEN") || "RED",
                time_to_green_s: p.time_to_green_s as number | undefined,
                time_to_red_s: p.time_to_red_s as number | undefined,
              });
              return next;
            });
          }
          break;
        }

        case "run.step":
        case "run.state_change":
        case "run.completed":
        case "run.cancelled":
        case "run.failed": {
          setCurrentRun((prev) => {
            if (!prev) return null;
            return {
              ...prev,
              current_tick: event.tick,
              elapsed_time_s: event.timestamp_s,
              lifecycle_state:
                (p.to_state as RunStatus["lifecycle_state"]) ||
                (event.event_type === "run.completed" ? "COMPLETED" : prev.lifecycle_state),
              is_terminal:
                event.event_type === "run.completed" ||
                event.event_type === "run.cancelled" ||
                event.event_type === "run.failed",
            };
          });
          break;
        }

        case "metrics.summary": {
          setMetrics({
            run_id: event.run_id,
            lifecycle_state: "RUNNING",
            current_tick: event.tick,
            metrics: p as RunMetrics["metrics"],
            disclaimer: event.disclaimer || "",
          });
          break;
        }
      }
    });

    return () => {
      unbindStatus();
      unbindEvents();
      wsClient.disconnect();
    };
  }, []);

  // Connect WebSocket when currentRun changes
  useEffect(() => {
    if (currentRun?.run_id) {
      wsClientRef.current.connect(currentRun.run_id);
    } else {
      wsClientRef.current.disconnect();
    }
  }, [currentRun?.run_id]);

  // 4. Action Handlers
  const handleCreateRun = async (scenarioId: string, maxTicks?: number) => {
    setActionError(null);
    try {
      const run = await defaultApiClient.createRun({
        scenario_id: scenarioId,
        max_ticks: maxTicks || 100,
        stop_on_all_arrived: true,
      });
      setCurrentRun(run);
      setVehicles(new Map());
      setPedestrians(new Map());
      setTelemetryEvents([]);
      setLatestGap(null);
      setSelectedEntity(null);

      // Fetch initial metrics
      try {
        const m = await defaultApiClient.getRunMetrics(run.run_id);
        setMetrics(m);
      } catch {
        // Ignored initially
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Run initialization failed";
      setActionError(msg);
    }
  };

  const handleStepRun = async (ticks: number, runToCompletion = false) => {
    if (!currentRun) return;
    setActionError(null);
    try {
      await defaultApiClient.stepRun(currentRun.run_id, {
        ticks,
        run_to_completion: runToCompletion,
      });

      // Update metrics snapshot
      try {
        const m = await defaultApiClient.getRunMetrics(currentRun.run_id);
        setMetrics(m);
      } catch {
        // Ignored
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Simulation step failed";
      setActionError(msg);
    }
  };

  const handleCancelRun = async () => {
    if (!currentRun) return;
    setActionError(null);
    try {
      await defaultApiClient.cancelRun(currentRun.run_id, "Operator requested stop");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Cancellation failed";
      setActionError(msg);
    }
  };

  const handleReconnect = () => {
    if (currentRun?.run_id) {
      wsClientRef.current.connect(currentRun.run_id);
    }
  };

  // Find active route for selected vehicle
  const activeRoute = useMemo(() => {
    if (selectedEntity?.type === "vehicle" && selectedEntity.id) {
      const v = vehicles.get(selectedEntity.id);
      return v?.route;
    }
    return undefined;
  }, [selectedEntity, vehicles]);

  return (
    <div className="app-container">
      <Header
        connectionStatus={wsStatus}
        runId={currentRun?.run_id ?? null}
        onReconnect={handleReconnect}
      />

      <main className="dashboard-grid">
        {/* Left Sidebar: Controls & Inspector */}
        <section className="sidebar-col" aria-label="Controls and Details">
          <ScenarioSelector
            scenarios={scenarios}
            selectedScenarioId={selectedScenarioId}
            onSelectScenario={(id) => {
              setSelectedScenarioId(id);
              setCurrentRun(null);
            }}
            onCreateRun={handleCreateRun}
            currentRun={currentRun}
            onStepRun={handleStepRun}
            onCancelRun={handleCancelRun}
            isLoading={isLoadingScenarios}
            actionError={actionError}
          />

          {selectedEntity && (
            <EntityInspector
              entityId={selectedEntity.id}
              entityType={selectedEntity.type}
              vehicleState={selectedEntity.type === "vehicle" ? vehicles.get(selectedEntity.id) : null}
              pedestrianState={
                selectedEntity.type === "pedestrian" ? pedestrians.get(selectedEntity.id) : null
              }
              onClose={() => setSelectedEntity(null)}
            />
          )}

          <MetricsPanel metrics={metrics} />
        </section>

        {/* Center Main: 3D Simulation Viewport */}
        <section className="viewport-col" aria-label="3D Simulation Viewport">
          <div className="viewport-wrapper">
            <SimulationViewer3D
              scenario={selectedScenario}
              vehicles={vehicles}
              pedestrians={pedestrians}
              signals={signals}
              activeRoute={activeRoute}
              selectedEntityId={selectedEntity?.id}
              onSelectEntity={(id, type) => setSelectedEntity({ id, type })}
              isLoading={isLoadingScenarios}
            />
          </div>

          {/* Bottom Row inside Viewport Column: Telemetry Feed */}
          <div className="telemetry-wrapper">
            <TelemetryFeed
              events={telemetryEvents}
              latestGap={latestGap}
              onClearGap={() => setLatestGap(null)}
            />
          </div>
        </section>
      </main>
    </div>
  );
};
