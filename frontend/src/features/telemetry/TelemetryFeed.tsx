import React, { useState, useMemo } from "react";
import type { TelemetryGapPayload, WebSocketEventEnvelope } from "../../types/websocket";

export interface TelemetryFeedProps {
  events: WebSocketEventEnvelope[];
  latestGap: TelemetryGapPayload | null;
  onClearGap?: () => void;
}

export const TelemetryFeed: React.FC<TelemetryFeedProps> = ({
  events,
  latestGap,
  onClearGap,
}) => {
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const filteredEvents = useMemo(() => {
    return events.filter((evt) => {
      if (filterType !== "all" && !evt.event_type.startsWith(filterType)) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const payloadStr = JSON.stringify(evt.payload || "").toLowerCase();
        return evt.event_type.toLowerCase().includes(q) || payloadStr.includes(q);
      }
      return true;
    });
  }, [events, filterType, searchQuery]);

  const handleExportJson = () => {
    const jsonStr = JSON.stringify(events, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `amapp-telemetry-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatPayloadSummary = (event: WebSocketEventEnvelope): string => {
    const p = event.payload as Record<string, unknown> | undefined;
    if (!p || typeof p !== "object") return "";

    switch (event.event_type) {
      case "run.state_change":
        return `State transitioned from ${p.from_state || "?"} ➔ ${p.to_state || "?"}`;
      case "run.step":
        return `Advanced tick ${event.tick} (sim time ${event.timestamp_s.toFixed(1)}s)`;
      case "run.completed":
        return `Run completed in ${p.completed_ticks || event.tick} ticks (${p.reason || "all arrived"})`;
      case "run.cancelled":
        return `Run cancelled at tick ${event.tick}: ${p.reason || "operator request"}`;
      case "run.failed":
        return `Run failed: ${p.error_message || "unknown failure"}`;
      case "vehicle.state":
        return `Vehicle ${p.vehicle_id}: speed=${Number(p.speed_mps || 0).toFixed(1)}m/s state=${p.lifecycle_state || "en_route"}`;
      case "pedestrian.state":
        return `Pedestrian ${p.pedestrian_id}: state=${p.lifecycle_state || "crossing"}`;
      case "traffic_signals.update":
        return `Signal ${p.signal_id} on node ${p.node_id}: phase=${p.state}`;
      case "safety.event":
        return `Safety conflict: ${p.vehicle_id} with ${p.other_id || "?"} (action=${p.action || "braking"})`;
      case "routing.reroute":
        return `Reroute for ${p.vehicle_id}: decision=${p.decision || "accepted"} (reason=${p.reason || "congestion"})`;
      case "communication.event":
        return `V2V message packet broadcast/delivery`;
      case "incident.created":
        return `Incident created: ${p.incident_type} on edge ${p.affected_edge_id || p.edge_id}`;
      case "incident.removed":
        return `Incident cleared: ${p.incident_id || p.id}`;
      default:
        return JSON.stringify(p).slice(0, 90);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {/* Header Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
          Streaming <strong style={{ color: "#0f172a" }}>{filteredEvents.length}</strong> of {events.length} events
        </div>
        <button
          type="button"
          onClick={handleExportJson}
          disabled={events.length === 0}
          style={{
            backgroundColor: "#ffffff",
            color: "#0f172a",
            border: "1px solid #e2e8f0",
            borderRadius: "6px",
            padding: "4px 10px",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
          title="Export events as JSON file"
        >
          Export JSON
        </button>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: "4px", overflowX: "auto", paddingBottom: "2px" }}>
        {[
          { key: "all", label: "All Events" },
          { key: "run.", label: "Lifecycle" },
          { key: "vehicle.", label: "Vehicles" },
          { key: "routing.", label: "Routing" },
          { key: "safety.", label: "Safety" },
          { key: "incident.", label: "Incidents" },
        ].map((cat) => (
          <button
            key={cat.key}
            type="button"
            onClick={() => setFilterType(cat.key)}
            style={{
              padding: "4px 8px",
              borderRadius: "4px",
              border: filterType === cat.key ? "1px solid #0f172a" : "1px solid #e2e8f0",
              backgroundColor: filterType === cat.key ? "#0f172a" : "#ffffff",
              color: filterType === cat.key ? "#ffffff" : "#475569",
              fontSize: "0.72rem",
              fontWeight: 600,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Search Input */}
      <input
        type="text"
        placeholder="Search event logs..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="form-input"
        style={{ fontSize: "0.78rem", padding: "5px 8px" }}
      />

      {latestGap && (
        <div style={{ backgroundColor: "#fffbeb", border: "1px solid #fde68a", padding: "8px 10px", borderRadius: "6px", fontSize: "0.75rem", color: "#92400e", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Telemetry Gap Detected: {latestGap.dropped_count || "Some"} non-critical events dropped.</span>
          {onClearGap && (
            <button type="button" onClick={onClearGap} aria-label="Dismiss telemetry gap notice" style={{ background: "none", border: "none", cursor: "pointer", fontWeight: "bold" }}>
              ✕
            </button>
          )}
        </div>
      )}

      {/* Events Table */}
      <div className="telemetry-table-wrapper">
        {filteredEvents.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center", color: "#94a3b8", fontSize: "0.8rem" }}>
            No telemetry events received yet. Start or step a simulation run to begin streaming.
          </div>
        ) : (
          <table className="telemetry-table">
            <thead>
              <tr>
                <th style={{ width: "40px" }}>Tick</th>
                <th style={{ width: "110px" }}>Type</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((evt) => (
                <tr key={`${evt.sequence}-${evt.tick}-${evt.event_type}`}>
                  <td style={{ fontFamily: "JetBrains Mono, monospace", color: "#0284c7", fontWeight: 600 }}>
                    {evt.tick}
                  </td>
                  <td style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.68rem", color: "#64748b" }}>
                    {evt.event_type}
                  </td>
                  <td>
                    {formatPayloadSummary(evt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
