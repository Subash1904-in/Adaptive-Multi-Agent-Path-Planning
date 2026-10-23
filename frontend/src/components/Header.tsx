import React from "react";
import type { WebSocketConnectionStatus } from "../types/websocket";

export interface HeaderProps {
  connectionStatus: WebSocketConnectionStatus;
  runId: string | null;
  onReconnect?: () => void;
  isInspectorOpen?: boolean;
  onToggleInspector?: () => void;
  scenarioName?: string;
}

export const Header: React.FC<HeaderProps> = ({
  connectionStatus,
  runId,
  onReconnect,
  isInspectorOpen = true,
  onToggleInspector,
  scenarioName,
}) => {
  const getStatusColor = () => {
    switch (connectionStatus) {
      case "CONNECTED":
        return { dot: "#059669", text: "#059669", label: "Live WebSocket" };
      case "CONNECTING":
      case "RECONNECTING":
        return { dot: "#d97706", text: "#d97706", label: "Connecting..." };
      case "ERROR":
        return { dot: "#dc2626", text: "#dc2626", label: "Connection Error" };
      case "DISCONNECTED":
      default:
        return { dot: "#94a3b8", text: "#64748b", label: "Offline" };
    }
  };

  const status = getStatusColor();

  return (
    <header className="app-header">
      {/* Zone 1: Brand Wordmark */}
      <div className="header-brand">
        <span className="brand-badge">AMAPP</span>
        <span className="header-title">Adaptive Multi-Agent Path Planning</span>
        <span className="header-tagline">Research & Educational Simulation</span>
        {scenarioName && (
          <span className="header-tagline">· {scenarioName}</span>
        )}
      </div>

      {/* Zone 2: Status & Active Run */}
      <div className="header-right-zone">
        {runId && (
          <div className="header-run-tag" title="Authoritative active run identifier">
            <span>Run:</span>
            <code className="header-run-code">{runId}</code>
          </div>
        )}

        <div className="connection-indicator" role="status" aria-live="polite">
          <span
            className="connection-dot"
            style={{ backgroundColor: status.dot }}
            aria-hidden="true"
          />
          <span style={{ color: status.text }}>{connectionStatus}</span>
        </div>

        {(connectionStatus === "DISCONNECTED" || connectionStatus === "ERROR") && onReconnect && runId && (
          <button
            type="button"
            onClick={onReconnect}
            className="header-tool-btn"
            aria-label="Reconnect to live simulation WebSocket"
          >
            Reconnect
          </button>
        )}

        {onToggleInspector && (
          <button
            type="button"
            onClick={onToggleInspector}
            className={`btn-inspector-toggle ${isInspectorOpen ? "active" : ""}`}
            aria-expanded={isInspectorOpen}
            aria-label="Toggle Operations and Analytics Inspector Drawer"
            title="Toggle Inspector Drawer (Alt+I)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="15" y1="3" x2="15" y2="21" />
            </svg>
            <span>{isInspectorOpen ? "Hide Inspector" : "Show Inspector"}</span>
          </button>
        )}
      </div>
    </header>
  );
};
