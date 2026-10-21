import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Header } from "../components/Header";
import { EntityInspector } from "../features/simulation/EntityInspector";
import { ScenarioSelector } from "../features/scenarios/ScenarioSelector";
import { SimulationViewer3D } from "../features/scene3d/SimulationViewer3D";
import { PlaybackBar } from "../features/playback/PlaybackBar";
import { PlaybackScheduler } from "../features/playback/playbackScheduler";
import { SimulationHistoryBuffer } from "../features/playback/historyBuffer";
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
  PlaybackSpeed,
  PlaybackState,
  TimelineRange,
} from "../types/playback";
import type {
  TelemetryGapPayload,
  WebSocketConnectionStatus,
  WebSocketEventEnvelope,
} from "../types/websocket";
import type { V2VSubsystemSnapshot } from "../types/v2v";
import {
  createV2VSubsystemSnapshot,
  extractV2VNetworkState,
} from "../features/scene3d/v2vAdapter";

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
  const [liveV2VSnapshot, setLiveV2VSnapshot] = useState<V2VSubsystemSnapshot | null>(null);

  // Playback & Historical Review State
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [playbackSpeed, setPlaybackSpeed] = useState<PlaybackSpeed>(1);
  const [activeReviewTick, setActiveReviewTick] = useState<number | null>(null);
  const [historyVersion, setHistoryVersion] = useState<number>(0);

  const historyBufferRef = useRef<SimulationHistoryBuffer>(new SimulationHistoryBuffer(500));
  const schedulerRef = useRef<PlaybackScheduler | null>(null);
  const selectedScenarioRef = useRef<ScenarioDefinition | null>(selectedScenario);

  useEffect(() => {
    selectedScenarioRef.current = selectedScenario;
  }, [selectedScenario]);

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

        case "world.snapshot": {
          const commRaw = p.communication as Record<string, unknown> | undefined;
          if (commRaw) {
            setVehicles((currentVehicles) => {
              const vPositions = new Map<string, { x: number; y: number }>();
              for (const [vId, vState] of currentVehicles.entries()) {
                vPositions.set(vId, vState.position);
              }
              const snap = createV2VSubsystemSnapshot({
                tick: event.tick,
                timestampS: event.timestamp_s,
                commSnapshot: commRaw,
                scenario: selectedScenarioRef.current,
                vehiclePositions: vPositions,
              });
              setLiveV2VSnapshot(snap);
              return currentVehicles;
            });
          }
          break;
        }

        case "communication.event": {
          setLiveV2VSnapshot((prev) => {
            if (!prev) {
              return createV2VSubsystemSnapshot({
                tick: event.tick,
                timestampS: event.timestamp_s,
                commMetrics: p,
                scenario: selectedScenarioRef.current,
              });
            }
            const nextState = extractV2VNetworkState(undefined, p, selectedScenarioRef.current);
            return {
              ...prev,
              tick: event.tick,
              timestampS: event.timestamp_s,
              networkState: {
                ...prev.networkState,
                totalBroadcasts: nextState.totalBroadcasts || prev.networkState.totalBroadcasts,
                totalDelivered: nextState.totalDelivered || prev.networkState.totalDelivered,
                totalDropped: nextState.totalDropped || prev.networkState.totalDropped,
                packetDeliveryRatio: nextState.packetDeliveryRatio ?? prev.networkState.packetDeliveryRatio,
                recentDrops: nextState.recentDrops,
              },
            };
          });
          break;
        }

        case "vehicle.state": {
          const vId = String(p.vehicle_id);
          const pos = p.position as { x: number; y: number } | undefined;
          if (vId && pos) {
            setVehicles((prev) => {
              const next = new Map(prev);
              const prevV = prev.get(vId);
              next.set(vId, {
                vehicle_id: vId,
                position: pos,
                speed_mps: Number(p.speed_mps ?? prevV?.speed_mps ?? 0),
                heading_rad: Number(p.heading_rad ?? prevV?.heading_rad ?? 0),
                lifecycle_state: String(p.lifecycle_state || prevV?.lifecycle_state || "en_route"),
                vehicle_type: (p.vehicle_type as "standard" | "emergency") || prevV?.vehicle_type || "standard",
                route: (p.route as string[] | undefined) ?? prevV?.route,
                current_edge_id: (p.current_edge_id as string | undefined) ?? prevV?.current_edge_id,
                is_emergency:
                  vId.toLowerCase().startsWith("amb_") ||
                  vId.toLowerCase().startsWith("fire_") ||
                  p.vehicle_type === "emergency" ||
                  p.emergency_type !== undefined ||
                  prevV?.is_emergency,
                emergency_type: (p.emergency_type as "ambulance" | "fire_engine" | "police" | undefined) ?? prevV?.emergency_type,
                priority_level: (p.priority_level as number | undefined) ?? prevV?.priority_level,
                tick: event.tick,
                simulation_time_s: event.timestamp_s,
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
              const prevP = prev.get(pId);
              next.set(pId, {
                pedestrian_id: pId,
                position: pos,
                speed_mps: Number(p.speed_mps ?? prevP?.speed_mps ?? 0),
                heading_rad: Number(p.heading_rad ?? prevP?.heading_rad ?? 0),
                lifecycle_state: String(p.lifecycle_state || prevP?.lifecycle_state || "walking"),
                crosswalk_id: (p.crosswalk_id as string | undefined) ?? prevP?.crosswalk_id,
                tick: event.tick,
                simulation_time_s: event.timestamp_s,
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
          const isCompleted = event.event_type === "run.completed";
          const isCancelled = event.event_type === "run.cancelled";
          const isFailed = event.event_type === "run.failed";
          const isTerm = isCompleted || isCancelled || isFailed;

          if (isTerm) {
            schedulerRef.current?.stop();
            if (isCompleted) setPlaybackState("completed");
            else if (isCancelled) setPlaybackState("cancelled");
            else setPlaybackState("failed");
          }

          setCurrentRun((prev) => {
            if (!prev) return null;
            return {
              ...prev,
              current_tick: event.tick,
              elapsed_time_s: event.timestamp_s,
              lifecycle_state:
                (p.to_state as RunStatus["lifecycle_state"]) ||
                (isCompleted ? "COMPLETED" : isCancelled ? "CANCELLED" : isFailed ? "FAILED" : prev.lifecycle_state),
              is_terminal: isTerm || prev.is_terminal,
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

  // 4. Session History Recording (Deduplicated snapshot capture)
  useEffect(() => {
    if (currentRun && currentRun.current_tick !== undefined) {
      historyBufferRef.current.addSnapshot({
        tick: currentRun.current_tick,
        simulation_time_s: currentRun.elapsed_time_s,
        timestamp_ms: Date.now(),
        vehicles,
        pedestrians,
        signals,
        metrics,
        communication: liveV2VSnapshot,
      });
      setHistoryVersion((v) => v + 1);
    }
  }, [currentRun, vehicles, pedestrians, signals, metrics, liveV2VSnapshot]);

  // 5. Playback Stepping Core Callback
  const executeStep = useCallback(
    async (ticks: number): Promise<boolean> => {
      if (!currentRun || currentRun.is_terminal) {
        return false;
      }
      setActionError(null);
      try {
        const res = await defaultApiClient.stepRun(currentRun.run_id, { ticks });
        const nextTick = Number(res.current_tick ?? (currentRun.current_tick + ticks));
        const nextSimTime = Number(
          res.elapsed_time_s ??
            currentRun.elapsed_time_s + ticks * (selectedScenarioRef.current?.time_step_s ?? 0.1)
        );
        const nextLifecycle = String(res.lifecycle_state || "RUNNING") as RunStatus["lifecycle_state"];
        const isTerm = Boolean(
          res.is_terminal ||
            ["COMPLETED", "CANCELLED", "FAILED", "LIMIT_REACHED"].includes(nextLifecycle)
        );

        setCurrentRun((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            current_tick: nextTick,
            elapsed_time_s: nextSimTime,
            lifecycle_state: nextLifecycle,
            is_terminal: isTerm,
            arrived_count:
              res.arrived_count !== undefined ? Number(res.arrived_count) : prev.arrived_count,
            active_count:
              res.active_count !== undefined ? Number(res.active_count) : prev.active_count,
          };
        });

        // Ingest communication metrics from tick_result if present
        const tickRes = (res.tick_result || res.last_tick_result) as Record<string, unknown> | undefined;
        if (tickRes?.communication_metrics) {
          setVehicles((currVehicles) => {
            const vPositions = new Map<string, { x: number; y: number }>();
            for (const [vId, vState] of currVehicles.entries()) {
              vPositions.set(vId, vState.position);
            }
            setLiveV2VSnapshot((prev) =>
              createV2VSubsystemSnapshot({
                tick: nextTick,
                timestampS: nextSimTime,
                commMetrics: tickRes.communication_metrics,
                scenario: selectedScenarioRef.current,
                vehiclePositions: vPositions,
                commSnapshot: prev?.networkState ? { ...prev.networkState } : undefined,
              })
            );
            return currVehicles;
          });
        }

        if (isTerm) {
          if (nextLifecycle === "COMPLETED" || nextLifecycle === "LIMIT_REACHED") {
            setPlaybackState("completed");
          } else if (nextLifecycle === "CANCELLED") {
            setPlaybackState("cancelled");
          } else {
            setPlaybackState("failed");
          }
          return false;
        }

        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Simulation step failed";
        setActionError(msg);
        return false;
      }
    },
    [currentRun]
  );

  // 6. Playback Scheduler Lifecycle Management
  useEffect(() => {
    schedulerRef.current = new PlaybackScheduler(
      {
        onStep: executeStep,
        onStateChange: (st) => setPlaybackState(st),
        onError: (err) => setActionError(err),
      },
      {
        speed: playbackSpeed,
        timeStepS: selectedScenario?.time_step_s ?? 0.1,
      }
    );

    return () => {
      schedulerRef.current?.dispose();
      schedulerRef.current = null;
    };
  }, [executeStep, playbackSpeed, selectedScenario?.time_step_s]);

  // 7. Action Handlers
  const handleCreateRun = async (scenarioId: string, maxTicks?: number) => {
    setActionError(null);
    schedulerRef.current?.stop();
    historyBufferRef.current.clear();
    setActiveReviewTick(null);
    setPlaybackState("ready");

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
      setLiveV2VSnapshot(null);

      // Record tick 0 baseline snapshot
      historyBufferRef.current.addSnapshot({
        tick: run.current_tick,
        simulation_time_s: run.elapsed_time_s,
        timestamp_ms: Date.now(),
        vehicles: new Map(),
        pedestrians: new Map(),
        signals: new Map(),
        metrics: null,
        communication: null,
      });
      setHistoryVersion((v) => v + 1);

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
      setPlaybackState("idle");
    }
  };

  const handleStepRun = async (ticks: number, runToCompletion = false) => {
    if (!currentRun || currentRun.is_terminal) return;
    if (activeReviewTick !== null) {
      setActiveReviewTick(null);
    }
    await schedulerRef.current?.executeManualStep(ticks || 1);

    if (runToCompletion) {
      setActionError(null);
      try {
        await defaultApiClient.stepRun(currentRun.run_id, { run_to_completion: true });
        const finalRun = await defaultApiClient.getRun(currentRun.run_id);
        setCurrentRun(finalRun);
        setPlaybackState("completed");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Run to completion failed";
        setActionError(msg);
      }
    }
  };

  const handleCancelRun = async () => {
    if (!currentRun) return;
    setActionError(null);
    schedulerRef.current?.stop();
    try {
      await defaultApiClient.cancelRun(currentRun.run_id, "Operator requested stop");
      setPlaybackState("cancelled");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Cancellation failed";
      setActionError(msg);
    }
  };

  const handlePlay = () => {
    if (activeReviewTick !== null) {
      setActiveReviewTick(null);
    }
    schedulerRef.current?.play();
  };

  const handlePause = () => {
    schedulerRef.current?.pause();
  };

  const handleResume = () => {
    if (activeReviewTick !== null) {
      setActiveReviewTick(null);
    }
    schedulerRef.current?.resume();
  };

  const handleSetSpeed = (nextSpeed: PlaybackSpeed) => {
    setPlaybackSpeed(nextSpeed);
    schedulerRef.current?.setSpeed(nextSpeed);
  };

  const handleSeekTick = (targetTick: number) => {
    schedulerRef.current?.pause();
    setActiveReviewTick(targetTick);
    setPlaybackState("reviewing");
  };

  const handleReturnToLive = () => {
    setActiveReviewTick(null);
    setPlaybackState("paused");
  };

  const handleReconnect = () => {
    if (currentRun?.run_id) {
      wsClientRef.current.connect(currentRun.run_id);
    }
  };

  // 8. Determine Entities to Render (Historical Review vs. Live)
  const renderedVehicles = useMemo(() => {
    if (activeReviewTick !== null) {
      const snap = historyBufferRef.current.getSnapshot(activeReviewTick);
      if (snap) return snap.vehicles;
    }
    return vehicles;
  }, [activeReviewTick, vehicles]);

  const renderedPedestrians = useMemo(() => {
    if (activeReviewTick !== null) {
      const snap = historyBufferRef.current.getSnapshot(activeReviewTick);
      if (snap) return snap.pedestrians;
    }
    return pedestrians;
  }, [activeReviewTick, pedestrians]);

  const renderedSignals = useMemo(() => {
    if (activeReviewTick !== null) {
      const snap = historyBufferRef.current.getSnapshot(activeReviewTick);
      if (snap) return snap.signals;
    }
    return signals;
  }, [activeReviewTick, signals]);

  // Determine V2V Subsystem Snapshot (Historical Review vs. Live)
  const renderedV2VSnapshot = useMemo(() => {
    if (activeReviewTick !== null) {
      const snap = historyBufferRef.current.getSnapshot(activeReviewTick);
      if (snap) return snap.communication ?? null;
    }
    return liveV2VSnapshot;
  }, [activeReviewTick, liveV2VSnapshot]);

  // Find active route for selected vehicle
  const activeRoute = useMemo(() => {
    if (selectedEntity?.type === "vehicle" && selectedEntity.id) {
      const v = renderedVehicles.get(selectedEntity.id);
      return v?.route;
    }
    return undefined;
  }, [selectedEntity, renderedVehicles]);

  // Compute Timeline Metadata
  const timelineRange: TimelineRange = useMemo(() => {
    const earliest = historyBufferRef.current.getEarliestTick() ?? 0;
    const latest = historyBufferRef.current.getLatestTick() ?? (currentRun?.current_tick ?? 0);
    return {
      earliestTick: earliest,
      latestTick: Math.max(earliest, latest),
      currentTick: currentRun?.current_tick ?? 0,
      simulationTimeS: currentRun?.elapsed_time_s ?? 0,
      maxTicks: selectedScenario?.max_ticks,
      isLive: activeReviewTick === null,
      activeReviewTick,
      bufferedCount: historyBufferRef.current.size(),
    };
    // historyVersion dependency forces recalculation when buffer changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    currentRun?.current_tick,
    currentRun?.elapsed_time_s,
    selectedScenario?.max_ticks,
    activeReviewTick,
    historyVersion,
  ]);

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
              setPlaybackState("idle");
              historyBufferRef.current.clear();
              setActiveReviewTick(null);
              setLiveV2VSnapshot(null);
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
              vehicleState={
                selectedEntity.type === "vehicle"
                  ? renderedVehicles.get(selectedEntity.id)
                  : null
              }
              pedestrianState={
                selectedEntity.type === "pedestrian"
                  ? renderedPedestrians.get(selectedEntity.id)
                  : null
              }
              onClose={() => setSelectedEntity(null)}
            />
          )}

          <MetricsPanel metrics={metrics} />
        </section>

        {/* Center Main: 3D Simulation Viewport & Playback Bar */}
        <section className="viewport-col" aria-label="3D Simulation Viewport">
          <div className="viewport-wrapper">
            <SimulationViewer3D
              scenario={selectedScenario}
              vehicles={renderedVehicles}
              pedestrians={renderedPedestrians}
              signals={renderedSignals}
              activeRoute={activeRoute}
              selectedEntityId={selectedEntity?.id}
              onSelectEntity={(id, type) => setSelectedEntity({ id, type })}
              isLoading={isLoadingScenarios}
              isReviewing={activeReviewTick !== null}
              reviewTick={activeReviewTick}
              onReturnToLive={handleReturnToLive}
              communicationSnapshot={renderedV2VSnapshot}
              playbackSpeed={playbackSpeed}
              isPaused={playbackState === "paused" || playbackState === "reviewing"}
            />
          </div>

          {/* Interactive Playback Bar & Timeline Scrubber */}
          <div className="playback-bar-wrapper" style={{ marginTop: "12px", marginBottom: "12px" }}>
            <PlaybackBar
              playbackState={playbackState}
              speed={playbackSpeed}
              timeline={timelineRange}
              isTerminal={currentRun?.is_terminal ?? false}
              canPlay={Boolean(currentRun && !currentRun.is_terminal)}
              canStep={Boolean(currentRun && !currentRun.is_terminal)}
              onPlay={handlePlay}
              onPause={handlePause}
              onResume={handleResume}
              onStep={(ticks) => handleStepRun(ticks)}
              onSetSpeed={handleSetSpeed}
              onSeekTick={handleSeekTick}
              onReturnToLive={handleReturnToLive}
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
