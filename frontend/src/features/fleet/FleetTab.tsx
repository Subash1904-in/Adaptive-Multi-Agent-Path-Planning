import React, { useState, useMemo } from "react";
import type { VehicleState } from "../../types/simulation";

export interface FleetTabProps {
  vehicles: Map<string, VehicleState>;
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
}

export const FleetTab: React.FC<FleetTabProps> = ({
  vehicles,
  selectedVehicleId,
  onSelectVehicle,
}) => {
  const [searchQuery, setSearchQuery] = useState("");

  const vehicleList = useMemo(() => {
    const list = Array.from(vehicles.values());
    if (!searchQuery.trim()) return list;
    const q = searchQuery.toLowerCase();
    return list.filter(
      (v) =>
        v.vehicle_id.toLowerCase().includes(q) ||
        (v.current_edge_id && v.current_edge_id.toLowerCase().includes(q))
    );
  }, [vehicles, searchQuery]);

  const arrivedCount = useMemo(() => {
    return Array.from(vehicles.values()).filter(
      (v) => v.lifecycle_state === "arrived" || v.lifecycle_state === "COMPLETED"
    ).length;
  }, [vehicles]);

  const activeCount = vehicles.size - arrivedCount;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Fleet KPI Summary */}
      <div className="kpi-row-grid">
        <div className="kpi-cell">
          <span className="kpi-cell-label">Active Cruising</span>
          <span className="kpi-cell-value">{activeCount}</span>
          <span className="kpi-cell-subtext">Vehicles on road</span>
        </div>
        <div className="kpi-cell">
          <span className="kpi-cell-label">Arrived</span>
          <span className="kpi-cell-value">{arrivedCount}</span>
          <span className="kpi-cell-subtext">Completed trips</span>
        </div>
      </div>

      {/* Search Filter */}
      <div style={{ position: "relative" }}>
        <input
          type="text"
          placeholder="Filter vehicles by ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="form-input"
          style={{ fontSize: "0.8rem", padding: "6px 10px" }}
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            style={{
              position: "absolute",
              right: "8px",
              top: "50%",
              transform: "translateY(-50%)",
              background: "none",
              border: "none",
              color: "#94a3b8",
              cursor: "pointer",
              fontSize: "0.8rem",
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Vehicle List */}
      <div className="fleet-list-container">
        {vehicleList.length === 0 ? (
          <div style={{ textAlign: "center", padding: "24px", color: "#94a3b8", fontSize: "0.8rem" }}>
            No matching vehicles found.
          </div>
        ) : (
          vehicleList.map((v) => {
            const isSelected = selectedVehicleId === v.vehicle_id;
            const speedKmh = (v.speed_mps * 3.6).toFixed(1);

            return (
              <div
                key={v.vehicle_id}
                className={`fleet-vehicle-row ${isSelected ? "selected" : ""}`}
                onClick={() => onSelectVehicle(v.vehicle_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onSelectVehicle(v.vehicle_id);
                }}
              >
                <div className="vehicle-meta-main">
                  <span
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      backgroundColor: v.is_emergency
                        ? "#dc2626"
                        : isSelected
                        ? "#0284c7"
                        : "#059669",
                      display: "inline-block",
                    }}
                  />
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span className="vehicle-id-badge">{v.vehicle_id}</span>
                      {v.is_emergency && (
                        <span style={{ fontSize: "0.65rem", fontWeight: 700, color: "#dc2626" }}>
                          EMERGENCY
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "#64748b" }}>
                      {v.current_edge_id ? `Edge: ${v.current_edge_id}` : "Navigating"}
                    </div>
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="vehicle-speed-display">{speedKmh} km/h</div>
                  <div className="vehicle-status-tag">{v.lifecycle_state}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
