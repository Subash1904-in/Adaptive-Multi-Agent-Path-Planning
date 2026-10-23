/**
 * Standard scenario definitions for AMAPP.
 * Ports definitions from backend/apps/core/scenarios/examples.py to TypeScript.
 */

import type { ScenarioDefinition, ScenarioSummary } from "../../types/simulation";

export const SCENARIO_DEFINITIONS: Record<string, ScenarioDefinition> = {
  scn_single_veh: {
    metadata: {
      id: "scn_single_veh",
      name: "Single Vehicle Straight Run",
      description: "Single vehicle navigating from (0,0) to (0,2) on a 3x3 grid.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 3,
        cols: 3,
        spacing_m: 50.0,
        speed_limit_mps: 10.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    vehicles: [
      {
        vehicle_id: "veh_01",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r0_c2",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        initial_speed_mps: 0.0,
        vehicle_type: "standard",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 200,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_multi_veh: {
    metadata: {
      id: "scn_multi_veh",
      name: "Multi-Vehicle Grid Deployment",
      description: "Three vehicles traversing a 4x4 grid along distinct routes.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 4,
        cols: 4,
        spacing_m: 50.0,
        speed_limit_mps: 12.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    vehicles: [
      {
        vehicle_id: "veh_north",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r3_c0",
        algorithm: "ASTAR",
        cost_mode: "TRAVEL_TIME",
        initial_speed_mps: 0.0,
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_east",
        start_node_id: "node_r0_c1",
        destination_node_id: "node_r0_c3",
        algorithm: "DIJKSTRA",
        cost_mode: "DISTANCE",
        initial_speed_mps: 0.0,
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_diagonal",
        start_node_id: "node_r1_c0",
        destination_node_id: "node_r2_c3",
        algorithm: "ASTAR",
        cost_mode: "TRAVEL_TIME",
        initial_speed_mps: 0.0,
        vehicle_type: "standard",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 150,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_signalized: {
    metadata: {
      id: "scn_signalized",
      name: "Signalized Center Intersection",
      description: "Vehicle traversing an intersection governed by a traffic signal.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 3,
        cols: 3,
        spacing_m: 60.0,
        speed_limit_mps: 10.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    signals: [
      {
        signal_id: "sig_center",
        node_id: "node_r1_c1",
        config: {
          green_duration_s: 6.0,
          yellow_duration_s: 2.0,
          red_duration_s: 6.0,
        },
      },
    ],
    vehicles: [
      {
        vehicle_id: "veh_crossing_h",
        start_node_id: "node_r1_c0",
        destination_node_id: "node_r1_c2",
        algorithm: "ASTAR",
        vehicle_type: "standard",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 150,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_congestion: {
    metadata: {
      id: "scn_congestion",
      name: "V2V Congestion Knowledge Sharing",
      description: "Two vehicles in range sharing decentralized edge congestion observations.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 3,
        cols: 3,
        spacing_m: 80.0,
        speed_limit_mps: 12.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    vehicles: [
      {
        vehicle_id: "veh_leader",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r2_c2",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
      },
      {
        vehicle_id: "veh_follower",
        start_node_id: "node_r0_c1",
        destination_node_id: "node_r2_c2",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 100,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_ambulance: {
    metadata: {
      id: "scn_ambulance",
      name: "Emergency Vehicle Corridor Reservation",
      description: "Ambulance reserving dynamic green corridor with civilian vehicles yielding.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 4,
        cols: 4,
        spacing_m: 60.0,
        speed_limit_mps: 14.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    signals: [
      {
        signal_id: "sig_r1_c1",
        node_id: "node_r1_c1",
        config: { green_duration_s: 5.0, yellow_duration_s: 2.0, red_duration_s: 5.0 },
      },
      {
        signal_id: "sig_r2_c1",
        node_id: "node_r2_c1",
        config: { green_duration_s: 5.0, yellow_duration_s: 2.0, red_duration_s: 5.0 },
      },
    ],
    vehicles: [
      {
        vehicle_id: "amb_01",
        start_node_id: "node_r0_c1",
        destination_node_id: "node_r3_c1",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "emergency",
      },
      {
        vehicle_id: "veh_civilian_1",
        start_node_id: "node_r1_c0",
        destination_node_id: "node_r1_c2",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_civilian_2",
        start_node_id: "node_r2_c2",
        destination_node_id: "node_r2_c0",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
    ],
    emergency_vehicles: [
      {
        vehicle_id: "amb_01",
        emergency_type: "ambulance",
        start_node_id: "node_r0_c1",
        destination_node_id: "node_r3_c1",
        priority_level: 10,
        activate_at_time_s: 0.0,
      },
    ],
    time_step_s: 0.1,
    max_ticks: 150,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_pedestrian: {
    metadata: {
      id: "scn_pedestrian",
      name: "Pedestrian Crosswalk & Safety Traversal",
      description: "Pedestrian crossing at designated crosswalk with approaching vehicle yielding.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 3,
        cols: 3,
        spacing_m: 60.0,
        speed_limit_mps: 10.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    crosswalks: [
      {
        crosswalk_id: "cw_01",
        entry_point: [30.0, 56.0],
        exit_point: [30.0, 64.0],
        width_m: 4.0,
        associated_intersection_id: "node_r1_c1",
      },
    ],
    pedestrians: [
      {
        pedestrian_id: "ped_01",
        initial_position: [30.0, 56.0],
        destination_point: [30.0, 64.0],
        crosswalk_id: "cw_01",
        initial_speed_mps: 1.2,
        walking_speed_mps: 1.2,
      },
    ],
    vehicles: [
      {
        vehicle_id: "veh_crossing",
        start_node_id: "node_r1_c0",
        destination_node_id: "node_r1_c2",
        algorithm: "ASTAR",
        vehicle_type: "standard",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 150,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_unreachable: {
    metadata: {
      id: "scn_unreachable",
      name: "Unreachable Destination Scenario",
      description: "Vehicle whose path is completely blocked by closed edges.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 3,
        cols: 3,
        spacing_m: 50.0,
        speed_limit_mps: 10.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    vehicles: [
      {
        vehicle_id: "veh_trapped",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r2_c2",
        closed_edge_ids: ["edge_r0_c0_to_r0_c1", "edge_r0_c0_to_r1_c0"],
      },
      {
        vehicle_id: "veh_valid",
        start_node_id: "node_r1_c1",
        destination_node_id: "node_r1_c2",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 50,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_tick_limited: {
    metadata: {
      id: "scn_tick_limited",
      name: "Tick-Limited Incomplete Run",
      description: "Scenario configured with a small tick limit that terminates early.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 5,
        cols: 5,
        spacing_m: 100.0,
        speed_limit_mps: 10.0,
        lanes: 1,
        bidirectional: true,
        seed: 42,
      },
    },
    vehicles: [
      {
        vehicle_id: "veh_long_distance",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r4_c4",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 10,
    stop_on_all_arrived: true,
    seed: 42,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_metropolis_downtown: {
    metadata: {
      id: "scn_metropolis_downtown",
      name: "Metropolis Downtown Rush Hour (Dense Multi-Vehicle)",
      description: "High-density multi-agent routing across a sprawling metropolitan downtown with 5 autonomous vehicles, multi-lane avenues, and diagonal cross-thoroughfares.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 5,
        cols: 5,
        spacing_m: 70.0,
        speed_limit_mps: 16.0,
        lanes: 2,
        bidirectional: true,
        seed: 101,
      },
    },
    signals: [
      {
        signal_id: "sig_metro_core",
        node_id: "node_r2_c2",
        config: { green_duration_s: 7.0, yellow_duration_s: 2.0, red_duration_s: 7.0 },
      },
      {
        signal_id: "sig_metro_east",
        node_id: "node_r2_c3",
        config: { green_duration_s: 5.0, yellow_duration_s: 2.0, red_duration_s: 5.0 },
      },
    ],
    vehicles: [
      {
        vehicle_id: "veh_metro_1",
        start_node_id: "node_r0_c0",
        destination_node_id: "node_r4_c4",
        algorithm: "ASTAR",
        cost_mode: "TRAVEL_TIME",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_metro_2",
        start_node_id: "node_r4_c0",
        destination_node_id: "node_r0_c4",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_bus_express",
        start_node_id: "node_r2_c0",
        destination_node_id: "node_r2_c4",
        algorithm: "DIJKSTRA",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_delivery_truck",
        start_node_id: "node_r0_c2",
        destination_node_id: "node_r4_c2",
        algorithm: "ASTAR",
        cost_mode: "TRAVEL_TIME",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_metro_3",
        start_node_id: "node_r3_c4",
        destination_node_id: "node_r1_c0",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
    ],
    crosswalks: [
      {
        crosswalk_id: "cw_metro_1",
        entry_point: [130.0, 140.0],
        exit_point: [150.0, 140.0],
        width_m: 4.0,
        associated_intersection_id: "node_r2_c2",
      },
    ],
    pedestrians: [
      {
        pedestrian_id: "ped_metro_1",
        initial_position: [130.0, 140.0],
        destination_point: [150.0, 140.0],
        walking_speed_mps: 1.35,
        crosswalk_id: "cw_metro_1",
      },
    ],
    time_step_s: 0.1,
    max_ticks: 350,
    stop_on_all_arrived: true,
    seed: 101,
    disclaimer: "AMAPP educational simulation framework.",
  },

  scn_metropolis_emergency: {
    metadata: {
      id: "scn_metropolis_emergency",
      name: "Metropolis Emergency Corridor & Fire Response",
      description: "Ambulance and Fire Engine navigating high-speed arterial boulevards with civilian traffic yielding across city intersections.",
      version: "1.0.0",
      author: "AMAPP Team",
    },
    road_network: {
      source_type: "synthetic_grid",
      grid_config: {
        rows: 5,
        cols: 5,
        spacing_m: 75.0,
        speed_limit_mps: 18.0,
        lanes: 3,
        bidirectional: true,
        seed: 202,
      },
    },
    signals: [
      {
        signal_id: "sig_emerg_1",
        node_id: "node_r1_c2",
        config: { green_duration_s: 6.0, yellow_duration_s: 2.0, red_duration_s: 6.0 },
      },
      {
        signal_id: "sig_emerg_2",
        node_id: "node_r2_c2",
        config: { green_duration_s: 6.0, yellow_duration_s: 2.0, red_duration_s: 6.0 },
      },
      {
        signal_id: "sig_emerg_3",
        node_id: "node_r3_c2",
        config: { green_duration_s: 6.0, yellow_duration_s: 2.0, red_duration_s: 6.0 },
      },
    ],
    vehicles: [
      {
        vehicle_id: "amb_metro_01",
        start_node_id: "node_r0_c2",
        destination_node_id: "node_r4_c2",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "emergency",
      },
      {
        vehicle_id: "fire_metro_01",
        start_node_id: "node_r2_c0",
        destination_node_id: "node_r2_c4",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "emergency",
      },
      {
        vehicle_id: "veh_civilian_w",
        start_node_id: "node_r1_c0",
        destination_node_id: "node_r1_c4",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
      {
        vehicle_id: "veh_civilian_e",
        start_node_id: "node_r3_c4",
        destination_node_id: "node_r3_c0",
        algorithm: "ASTAR",
        cost_mode: "DISTANCE",
        vehicle_type: "standard",
      },
    ],
    emergency_vehicles: [
      {
        vehicle_id: "amb_metro_01",
        emergency_type: "ambulance",
        start_node_id: "node_r0_c2",
        destination_node_id: "node_r4_c2",
        priority_level: 10,
        activate_at_time_s: 0.0,
      },
      {
        vehicle_id: "fire_metro_01",
        emergency_type: "fire_engine",
        start_node_id: "node_r2_c0",
        destination_node_id: "node_r2_c4",
        priority_level: 9,
        activate_at_time_s: 0.0,
      },
    ],
    time_step_s: 0.1,
    max_ticks: 350,
    stop_on_all_arrived: true,
    seed: 202,
    disclaimer: "AMAPP educational simulation framework.",
  },
};

export function getScenarioSummaries(): ScenarioSummary[] {
  return Object.values(SCENARIO_DEFINITIONS).map((scn) => ({
    id: scn.metadata.id,
    name: scn.metadata.name,
    description: scn.metadata.description,
    version: scn.metadata.version,
    author: scn.metadata.author,
    vehicle_count: scn.vehicles.length,
    road_network_source: scn.road_network.source_type,
    time_step_s: scn.time_step_s,
    max_ticks: scn.max_ticks ?? null,
    effective_max_ticks: scn.max_ticks ?? null,
  }));
}
