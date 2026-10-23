import { useCallback, useEffect, useRef, useState } from "react";
import { Simulation as TwinSimulation } from "./simulation.js";
import { World as TwinWorld } from "./world.js";
import { defaultApiClient } from "../lib/api/client";
import type { RunMetrics, RunStatus, ScenarioSummary } from "../types/simulation";

type TwinSimulationRuntime = {
  running: boolean;
  rate: number;
  time: number;
  agents: Array<{
    id: string;
    type: string;
    speed: number;
    destination: { name: string };
    status: string;
    arrived: boolean;
  }>;
  event: string;
  eventDetail: string;
  metrics: {
    active: number;
    arrived: number;
    mean: number;
    reroutes: number;
    distanceTravelledKm: number;
    sentHops: number;
    receivedHops: number;
    meanLatencyMs: number | null;
    conflictPredictions: number;
  };
  messages: Array<{ sender: string; receiver: string; type: string; hop: number; decision: string }>;
  tick(deltaSeconds: number): void;
  reset(): void;
  triggerBlockage(): void;
  triggerEmergency(): void;
  triggerConflict(): void;
  triggerTraffic(durationSeconds?: number): void;
  startPresentationSequence(options?: { quick?: boolean }): void;
  position(agent: unknown): { x: number; y: number; z: number; heading: number } | null;
};

type TwinWorldRuntime = {
  update(simulation: TwinSimulationRuntime, selected: unknown): void;
  updateCameraTransition(deltaSeconds: number): void;
  render(): void;
  setCamera(mode: string, position?: unknown): void;
};

const formatTime = (seconds: number) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export function DigitalTwinApp() {
  const viewportRef = useRef<HTMLDivElement>(null);
  const simulationRef = useRef<TwinSimulationRuntime | null>(null);
  const worldRef = useRef<TwinWorldRuntime | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [backendRun, setBackendRun] = useState<RunStatus | null>(null);
  const [backendMetrics, setBackendMetrics] = useState<RunMetrics | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [selectedVehicle, setSelectedVehicle] = useState("V1");
  const [, redraw] = useState(0);
  const selectedVehicleRef = useRef(selectedVehicle);

  useEffect(() => {
    selectedVehicleRef.current = selectedVehicle;
  }, [selectedVehicle]);

  useEffect(() => {
    const simulation = new TwinSimulation() as TwinSimulationRuntime;
    simulation.running = true;
    simulationRef.current = simulation;
    if (!viewportRef.current) return;
    const world = new TwinWorld(viewportRef.current) as TwinWorldRuntime;
    worldRef.current = world;
    let previous = performance.now();
    let frame = 0;
    const animate = (timestamp: number) => {
      const delta = Math.min((timestamp - previous) / 1000, 0.1);
      previous = timestamp;
      simulation.tick(delta);
      const agent = simulation.agents.find((item) => item.id === selectedVehicleRef.current);
      world.update(simulation, agent);
      world.updateCameraTransition(delta);
      world.render();
      if (timestamp - frame > 160) {
        frame = timestamp;
        redraw((value) => value + 1);
      }
      requestAnimationFrame(animate);
    };
    const animation = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animation);
      worldRef.current = null;
      simulationRef.current = null;
      if (viewportRef.current) {
        viewportRef.current.replaceChildren();
      }
    };
  }, []);

  useEffect(() => {
    let active = true;
    defaultApiClient.listScenarios().then((items) => {
      if (!active) return;
      setScenarios(items);
      setSelectedScenario(items[0]?.id ?? "");
    }).catch((error: unknown) => {
      if (active) setBackendError(error instanceof Error ? error.message : "Unable to load backend scenarios");
    });
    return () => { active = false; };
  }, []);

  const runBackend = useCallback(async (action: "create" | "step" | "metrics") => {
    setBackendError(null);
    try {
      if (action === "create") {
        const run = await defaultApiClient.createRun({ scenario_id: selectedScenario });
        setBackendRun(run);
        return;
      }
      if (!backendRun) return;
      if (action === "step") {
        const result = await defaultApiClient.stepRun(backendRun.run_id, { ticks: 1 });
        setBackendRun((current) => current ? { ...current, ...result } as RunStatus : current);
      } else {
        setBackendMetrics(await defaultApiClient.getRunMetrics(backendRun.run_id));
      }
    } catch (error: unknown) {
      setBackendError(error instanceof Error ? error.message : "Backend request failed");
    }
  }, [backendRun, selectedScenario]);

  const simulation = simulationRef.current;
  const metrics = simulation?.metrics;
  const selected = simulation?.agents.find((agent) => agent.id === selectedVehicle);

  return (
    <main className="twin-shell">
      <div ref={viewportRef} className="twin-viewport" />
      <header className="twin-brand">
        <span className="twin-mark">V2V</span>
        <div><strong>URBAN MOBILITY LAB</strong><small>ADAPTIVE MULTI-AGENT DIGITAL TWIN</small></div>
        <span className="twin-live"><i /> LOCAL SIMULATION</span>
      </header>
      <section className="twin-panel twin-controls">
        <div className="twin-panel-title"><span>COMMAND CENTER</span><b>{backendRun?.lifecycle_state ?? "STANDBY"}</b></div>
        <button className="twin-primary" onClick={() => simulation?.startPresentationSequence({ quick: true })}>Start quick mission</button>
        <div className="twin-button-grid">
          <button onClick={() => { if (simulation) simulation.running = !simulation.running; }}>{simulation?.running ? "Pause" : "Resume"}</button>
          <button onClick={() => { simulation?.reset(); simulation && (simulation.running = true); }}>Reset twin</button>
        </div>
        <label>Backend scenario<select value={selectedScenario} onChange={(event) => setSelectedScenario(event.target.value)}>
          {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
        </select></label>
        <div className="twin-button-grid">
          <button onClick={() => void runBackend("create")}>Create backend run</button>
          <button disabled={!backendRun} onClick={() => void runBackend("step")}>Step backend</button>
        </div>
        <div className="twin-event"><b>{simulation?.event ?? "Initializing digital twin"}</b><span>{simulation?.eventDetail ?? "Connecting to the simulation runtime."}</span></div>
        <div className="twin-button-grid">
          <button onClick={() => simulation?.triggerEmergency()}>Emergency</button>
          <button onClick={() => simulation?.triggerBlockage()}>Blockage</button>
          <button onClick={() => simulation?.triggerConflict()}>Conflict</button>
        </div>
        <label>Simulation rate <strong>{simulation?.rate.toFixed(1)}x</strong><input type="range" min="0.25" max="4" step="0.25" value={simulation?.rate ?? 1} onChange={(event) => { if (simulation) simulation.rate = Number(event.target.value); }} /></label>
      </section>
      <aside className="twin-panel twin-telemetry">
        <div className="twin-panel-title"><span>LIVE TELEMETRY</span><b>{formatTime(simulation?.time ?? 0)}</b></div>
        <div className="twin-kpis">
          <div><strong>{metrics?.active ?? 0}</strong><span>ACTIVE VEHICLES</span></div>
          <div><strong>{metrics?.arrived ?? 0}</strong><span>ARRIVED</span></div>
          <div><strong>{Math.round(metrics?.mean ?? 0)}</strong><span>MEAN KM/H</span></div>
          <div><strong>{metrics?.reroutes ?? 0}</strong><span>REROUTES</span></div>
          <div><strong>{metrics?.distanceTravelledKm.toFixed(1) ?? "0.0"}</strong><span>DISTANCE KM</span></div>
          <div><strong>{metrics?.receivedHops ?? 0}</strong><span>V2V HOPS</span></div>
        </div>
        <label>Inspect vehicle<select value={selectedVehicle} onChange={(event) => setSelectedVehicle(event.target.value)}>
          {(simulation?.agents ?? []).map((agent) => <option key={agent.id} value={agent.id}>{agent.id} · {agent.type}</option>)}
        </select></label>
        <div className="twin-vehicle-card"><b>{selected?.id ?? "—"} · {selected?.status ?? "Awaiting telemetry"}</b><span>{selected?.destination.name ?? "No destination loaded"}</span><strong>{Math.round(selected?.speed ?? 0)} <small>km/h</small></strong></div>
        <div className="twin-section-title">V2V MESSAGE TRACE</div>
        <div className="twin-message-list">{(simulation?.messages.slice(0, 5) ?? []).map((message, index) => <div key={`${message.sender}-${message.receiver}-${index}`}><b>{message.sender} → {message.receiver}</b><span>{message.type} · hop {message.hop}</span></div>)}</div>
        <button className="twin-secondary" disabled={!backendRun} onClick={() => void runBackend("metrics")}>Refresh backend analytics</button>
        {backendMetrics && <div className="twin-backend-status">Backend tick {backendMetrics.current_tick} · {backendMetrics.lifecycle_state}</div>}
        {backendError && <div className="twin-error">{backendError}</div>}
      </aside>
      <footer className="twin-footer"><span>{simulation?.eventDetail ?? "Digital twin ready"}</span><b>DRAG TO ORBIT · SCROLL TO ZOOM</b></footer>
    </main>
  );
}
