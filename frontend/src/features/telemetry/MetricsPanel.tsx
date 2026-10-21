import React from "react";
import type { RunMetrics } from "../../types/simulation";

export interface MetricsPanelProps {
  metrics: RunMetrics | null;
  isLoading?: boolean;
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({ metrics, isLoading }) => {
  const m = metrics?.metrics;

  const distM = Number(m?.kinematics?.total_distance_traveled_m || 0);
  const avgSpeed = Number(m?.kinematics?.average_speed_mps || 0);
  const maxSpeed = Number(m?.kinematics?.max_speed_observed_mps || 0);
  const pdr = Number(m?.communication?.packet_delivery_ratio ?? 1.0);
  const msgsSent = Number(m?.communication?.messages_sent || 0);
  const collisions = Number(m?.safety?.actual_collisions || 0);
  const nearMisses = Number(m?.safety?.near_misses || 0);
  const reroutesAccepted = Number(m?.routing?.reroutes_accepted || 0);
  const pedCrossings = Number(m?.pedestrians?.crosswalk_crossings_completed || 0);
  const corridors = Number(m?.emergency?.corridors_created || 0);

  return (
    <div className="panel metrics-panel">
      <div className="panel-header">
        <h2 className="panel-title">Cross-Subsystem Metrics</h2>
        {isLoading && <span className="sub-tag">Updating...</span>}
      </div>

      <div className="panel-body">
        <div className="metrics-grid">
          {/* Kinematics */}
          <div className="metric-cell">
            <span className="metric-label">Total Distance</span>
            <span className="metric-value">{distM.toFixed(1)} m</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Avg Speed</span>
            <span className="metric-value">{avgSpeed.toFixed(1)} m/s</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Max Speed</span>
            <span className="metric-value">{maxSpeed.toFixed(1)} m/s</span>
          </div>

          {/* V2V Communication */}
          <div className="metric-cell">
            <span className="metric-label">V2V Messages</span>
            <span className="metric-value">{msgsSent}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Packet Delivery Ratio</span>
            <span className="metric-value">{(pdr * 100).toFixed(1)}%</span>
          </div>

          {/* Safety & Collisions */}
          <div className={`metric-cell ${collisions > 0 ? "metric-alert" : ""}`}>
            <span className="metric-label">Collisions</span>
            <span className="metric-value">{collisions}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Near-Miss Interventions</span>
            <span className="metric-value">{nearMisses}</span>
          </div>

          {/* Routing & Mobility */}
          <div className="metric-cell">
            <span className="metric-label">Reroutes Accepted</span>
            <span className="metric-value">{reroutesAccepted}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Pedestrian Crossings</span>
            <span className="metric-value">{pedCrossings}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">Emergency Corridors</span>
            <span className="metric-value">{corridors}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
