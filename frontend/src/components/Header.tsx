import React from "react";
import type { WebSocketConnectionStatus } from "../types/websocket";

export interface HeaderProps {
  connectionStatus: WebSocketConnectionStatus;
  runId: string | null;
  onReconnect?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  connectionStatus,
  runId,
  onReconnect,
}) => {
  const getStatusBadge = () => {
    switch (connectionStatus) {
      case "CONNECTED":
        return {
          label: "CONNECTED",
          bg: "#065f46",
          color: "#34d399",
          dot: "#10b981",
        };
      case "CONNECTING":
        return {
          label: "CONNECTING",
          bg: "#78350f",
          color: "#fcd34d",
          dot: "#f59e0b",
        };
      case "RECONNECTING":
        return {
          label: "RECONNECTING",
          bg: "#1e3a8a",
          color: "#93c5fd",
          dot: "#3b82f6",
        };
      case "ERROR":
        return {
          label: "ERROR",
          bg: "#7f1d1d",
          color: "#fca5a5",
          dot: "#ef4444",
        };
      case "DISCONNECTED":
      default:
        return {
          label: "DISCONNECTED",
          bg: "#334155",
          color: "#cbd5e1",
          dot: "#94a3b8",
        };
    }
  };

  const badge = getStatusBadge();

  return (
    <header className="app-header">
      <div className="header-brand">
        <span className="brand-badge">AMAPP</span>
        <h1 className="header-title">Adaptive Multi-Agent Path Planning</h1>
        <span className="header-version">v1.0.0</span>
      </div>

      <div className="header-disclaimer" title="Academic and educational simulation platform">
        Research & Educational Simulation
      </div>

      <div className="header-status-area">
        {runId && (
          <div className="header-active-run">
            <span className="label">ACTIVE RUN:</span>
            <code className="run-id">{runId}</code>
          </div>
        )}

        <div
          className="connection-status-pill"
          style={{ backgroundColor: badge.bg, color: badge.color }}
          role="status"
          aria-live="polite"
        >
          <span
            className="status-dot"
            style={{ backgroundColor: badge.dot }}
            aria-hidden="true"
          />
          <span>{badge.label}</span>
        </div>

        {(connectionStatus === "DISCONNECTED" || connectionStatus === "ERROR") && onReconnect && runId && (
          <button
            type="button"
            onClick={onReconnect}
            className="btn btn-secondary btn-sm"
            aria-label="Reconnect to live simulation WebSocket"
          >
            Reconnect
          </button>
        )}
      </div>
    </header>
  );
};
