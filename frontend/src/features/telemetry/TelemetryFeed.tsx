import React from "react";
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
  const formatPayloadSummary = (event: WebSocketEventEnvelope): string => {
    const p = event.payload;
    if (!p || typeof p !== "object") return "";

    switch (event.event_type) {
      case "run.state_change":
        return `State transitioned from ${p.from_state || "?"} -> ${p.to_state || "?"}`;
      case "run.step":
        return `Completed tick ${event.tick} (sim time ${event.timestamp_s.toFixed(1)}s)`;
      case "run.completed":
        return `Run completed in ${p.completed_ticks || event.tick} ticks (${p.reason || "all vehicles arrived"})`;
      case "run.cancelled":
        return `Run cancelled at tick ${event.tick}: ${p.reason || "operator request"}`;
      case "run.failed":
        return `Run failed: ${p.error_message || "unknown failure"}`;
      case "vehicle.state":
        return `Vehicle ${p.vehicle_id}: speed=${Number(p.speed_mps || 0).toFixed(1)}m/s state=${p.lifecycle_state || "en_route"}`;
      case "pedestrian.state":
        return `Pedestrian ${p.pedestrian_id}: state=${p.lifecycle_state || "crossing"}`;
      case "traffic_signals.update":
        return `Signal ${p.signal_id} on node ${p.node_id}: state=${p.state}`;
      case "safety.event":
        return `Safety conflict: ${p.vehicle_id} with ${p.other_id || "?"} (action=${p.action || "braking"})`;
      case "routing.reroute":
        return `Reroute for ${p.vehicle_id}: ${p.decision || "accepted"} (reason=${p.reason || "dynamic"})`;
      case "communication.message":
        return `V2V message from ${p.sender_id} (${p.message_type || "heartbeat"})`;
      case "emergency.event":
        return `Emergency priority: ${p.vehicle_id} (${p.emergency_type || "ambulance"})`;
      case "decision.evaluated":
        return `Decision evaluation for ${p.vehicle_id}: selected candidate ${p.selected_candidate_id || "route"}`;
      case "connection.ack":
        return `Connected to run ${p.run_id} (initial tick ${p.initial_tick || 0})`;
      case "heartbeat":
        return "Server keepalive heartbeat received";
      case "telemetry.gap":
        return `Data gap: ${p.dropped_count || "some"} records dropped (${p.reason || "buffer overflow"})`;
      default:
        return JSON.stringify(p).slice(0, 80);
    }
  };

  const getEventBadgeClass = (eventType: string): string => {
    if (eventType.startsWith("run.")) return "tag-lifecycle";
    if (eventType.startsWith("vehicle.")) return "tag-vehicle";
    if (eventType.startsWith("pedestrian.")) return "tag-pedestrian";
    if (eventType.startsWith("safety.")) return "tag-safety";
    if (eventType.startsWith("emergency.")) return "tag-emergency";
    if (eventType.startsWith("routing.")) return "tag-routing";
    if (eventType.startsWith("traffic_signals.")) return "tag-signal";
    if (eventType === "telemetry.gap") return "tag-gap";
    return "tag-default";
  };

  return (
    <div className="panel telemetry-panel">
      <div className="panel-header">
        <h2 className="panel-title">Telemetry & Event Feed</h2>
        <span className="badge badge-neutral">{events.length} events</span>
      </div>

      {latestGap && (
        <div className="alert alert-warning gap-alert" role="alert">
          <div className="gap-alert-content">
            <span className="gap-alert-title">Telemetry Gap Detected:</span>
            <span>
              {latestGap.reason === "buffer_overflow"
                ? `Outbound buffer saturated. ${latestGap.dropped_count ?? "?"} non-critical events dropped.`
                : `Requested historical sequence range expired from memory buffer.`}
            </span>
          </div>
          {onClearGap && (
            <button
              type="button"
              onClick={onClearGap}
              className="btn-dismiss"
              aria-label="Dismiss telemetry gap notice"
            >
              &times;
            </button>
          )}
        </div>
      )}

      <div className="telemetry-feed-scroll" tabIndex={0} aria-label="Event feed stream">
        {events.length === 0 ? (
          <div className="feed-empty-state">
            No telemetry events received yet. Start or step a simulation run to begin streaming.
          </div>
        ) : (
          <div className="event-list">
            {events.map((evt) => (
              <div key={`${evt.sequence}-${evt.tick}-${evt.event_type}`} className="event-row">
                <div className="event-meta">
                  <span className="event-seq">#{evt.sequence}</span>
                  <span className="event-tick">T:{evt.tick}</span>
                  <span className="event-time">{evt.timestamp_s.toFixed(1)}s</span>
                  <span className={`event-tag ${getEventBadgeClass(evt.event_type)}`}>
                    {evt.event_type}
                  </span>
                </div>
                <div className="event-desc">{formatPayloadSummary(evt)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
