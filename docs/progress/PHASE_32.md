# Phase 32 — Gymnasium-Compatible Single-Agent and Multi-Agent RL Environment

## 1. Objective & Acceptance Checklist

The objective of Phase 32 is to implement a deterministic, Gymnasium-compatible reinforcement-learning environment that enables learning agents to interact with the existing autonomous-vehicle path-planning simulation. The environment models routing choices at intersections, exposes bounded observations and discrete actions, calculates objective-driven rewards from authoritative simulation events, and provides clean bridges for reproducible benchmarking and future multi-agent extensions.

### Acceptance Checklist
- [x] **Gymnasium Dependency Integration:** Added `gymnasium>=1.0.0,<1.1.0` to `requirements.txt`. Verified dependency resolution and compatibility with Python 3.11.9 and NumPy 2.4.6 without dependency conflicts (`pip check` verified clean).
- [x] **Simulation Ownership & Isolation:** Each environment instance directly creates and owns an isolated `WorldState` and `SimulationEngine` instance via standard scenario factories (`ScenarioBuilder`). Resets release all mutable graph states, vehicle kinematics, and incident registries without cross-episode or cross-instance leakage.
- [x] **Gymnasium API Compliance & Checker Verification:** Implemented `AMAPPSingleAgentEnv` subclassing `gymnasium.Env`. Fully passes `gymnasium.utils.env_checker.check_env` without exceptions.
- [x] **Bounded Continuous Observation Space:** Designed and implemented a 32-dimensional observation vector in `spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)` representing local planar coordinates, kinematics, heading trigonometry, destination delta, route progress, edge features (closure/congestion), upcoming junction branch density, traffic signal state, neighbor proximity, active incidents, and emergency vehicle alerts. No future state or destination outcome is leaked.
- [x] **Discrete Action Space & Action Masking:** Formulated `spaces.Discrete(K + 1)` branch selection actions at junctions (Action 0 keeps current route; Actions $1 \le a \le K$ select legal outgoing road edges). Implemented `action_masks() -> np.ndarray[bool]` accurately filtering unavailable branch indices and active road closures. Invalid actions are rejected without state corruption and penalized cleanly.
- [x] **Objective-Driven Reward Function:** Designed `RewardCalculator` and `RewardBreakdown` computing progress reward, step duration cost, arrival bonus (+100.0 credited strictly once upon arrival), collision (-20.0) and near-miss (-2.0) penalties, invalid action penalty (-1.0), and truncation penalty (-10.0) without future leakage or double-counting.
- [x] **Deterministic Seeded Resets & Lifecycle:** Implemented standard `reset(seed=..., options=...)` and `step(action) -> (obs, reward, terminated, truncated, info)` lifecycles. Distinguishes arrival termination (`terminated=True`) from step-limit truncation (`truncated=True`).
- [x] **Decentralized Multi-Agent Environment Extension:** Implemented `AMAPPMultiAgentEnv` coordinating simultaneous routing decisions across multiple vehicles with per-agent spaces, simultaneous step execution, and per-agent action masking without duplicating simulation clocks.
- [x] **Phase 31 Benchmark Integration Bridge:** Implemented `evaluate_rl_environment_episode` and deterministic test policies (`GreedyProgressTestPolicy`, `RandomTestPolicy`) producing authoritative `BenchmarkTrialResult` records conforming to the Phase 31 contract.
- [x] **Comprehensive Automated Testing:** Implemented 26 tests in `apps/core/tests/test_rl_environment.py` covering Gymnasium contracts, `check_env`, seed determinism, state isolation, observation bounds, action masking, reward math, multi-agent stepping, and benchmark evaluation. Full backend suite passes at 1,170 tests with 95.12% line coverage.
- [x] **CI Pipeline Evolution:** Updated `.github/workflows/ci.yml` adding `PHASE_32.md` to repository hygiene checks, verifying `gymnasium` in environment dependencies, and adding an automated `check_env` smoke verification step to the backend test job.
- [x] **Strict Scope Discipline:** Strictly avoided model training, policy optimization, or false learned-policy claims. Training is deferred to Phase 33.

---

## 2. Starting Repository & Environment State

- **Starting Branch:** `main`
- **Base Commit SHA:** `b9c754fb4c8b0f0e8daf8bb7a47dd64642927c99` (Phase 31 documentation commit following implementation commit `bfc00f6`)
- **Working Tree State:** Clean
- **Python Version:** 3.11.9
- **NumPy Version:** 2.4.6
- **Gymnasium Version:** 1.0.0
- **Existing Subsystems Reused:**
  - `apps.core.simulation.world.WorldState` & `SimulationEngine`: Authoritative discrete stepping and clock coordination.
  - `apps.core.graph.road_graph.RoadGraph`: Authoritative directed topological road network queries.
  - `apps.core.kinematics.vehicle_agent.VehicleAgent`: Bounded physical motion, acceleration, and route tracking.
  - `apps.core.routing.planner.RoutePlanner`: A* route finding and branch suffix replacement.
  - `apps.core.safety.manager.SafetyManager`: Authoritative collision detection and near-miss event logs.
  - `apps.core.incidents.manager.IncidentManager`: Authoritative road closure and congestion queries (`is_edge_closed`, `get_congestion_multiplier`).
  - `apps.core.emergency.priority_manager.EmergencyPriorityManager`: Emergency vehicle awareness and priority queries.
  - `apps.core.signals.controller.TrafficSignalController`: Authoritative intersection signal phase queries.
  - `apps.core.benchmarking.scenarios.BenchmarkScenarioRegistry`: Standardized benchmark scenario suites.

---

## 3. Package Architecture & Module Structure

The reinforcement-learning environment is implemented as an isolated package under `backend/apps/core/rl/`:

```
backend/apps/core/rl/
├── __init__.py           # Public exports (AMAPPSingleAgentEnv, AMAPPMultiAgentEnv, configs, policies, bridge)
├── config.py             # RewardConfig, SingleAgentRLConfig, MultiAgentRLConfig dataclasses
├── exceptions.py         # Structured RL exception taxonomy (RLEnvironmentError, InvalidActionError, etc.)
├── features.py           # 32-dimensional bounded observation extraction (extract_agent_observation)
├── rewards.py            # RewardBreakdown dataclass and RewardCalculator step reward formulation
├── env.py                # Single-agent Gymnasium environment (AMAPPSingleAgentEnv)
├── multi_agent.py        # Decentralized multi-agent environment extension (AMAPPMultiAgentEnv)
└── adapter.py            # Phase 31 benchmark bridge (evaluate_rl_environment_episode, test policies)
```

---

## 4. Observation Space Specification

The observation space is a continuous vector space `spaces.Box(low=-1.0, high=1.0, shape=(32,), dtype=np.float32)` representing local, non-privileged information observable by the vehicle:

| Index | Feature Name | Range / Bounds | Normalization & Physical Units | Description |
| :---: | :--- | :---: | :--- | :--- |
| **0** | `norm_x` | $[-1.0, 1.0]$ | $2 \cdot (x - x_{\min}) / \Delta x - 1$ | Vehicle planar X position scaled across graph extent. |
| **1** | `norm_y` | $[-1.0, 1.0]$ | $2 \cdot (y - y_{\min}) / \Delta y - 1$ | Vehicle planar Y position scaled across graph extent. |
| **2** | `speed_norm` | $[0.0, 1.0]$ | $v / v_{\max}$ ($v_{\max} = 30.0\text{ m/s}$) | Current vehicle forward speed. |
| **3** | `heading_sin` | $[-1.0, 1.0]$ | $\sin(\theta)$ | Sine of vehicle heading orientation. |
| **4** | `heading_cos` | $[-1.0, 1.0]$ | $\cos(\theta)$ | Cosine of vehicle heading orientation. |
| **5** | `dest_norm_x` | $[-1.0, 1.0]$ | $2 \cdot (x_{\text{dest}} - x_{\min}) / \Delta x - 1$ | Destination node planar X position. |
| **6** | `dest_norm_y` | $[-1.0, 1.0]$ | $2 \cdot (y_{\text{dest}} - y_{\min}) / \Delta y - 1$ | Destination node planar Y position. |
| **7** | `rel_dx` | $[-1.0, 1.0]$ | $\Delta x / D_{\text{span}}$ | Relative X vector to destination scaled by network span. |
| **8** | `rel_dy` | $[-1.0, 1.0]$ | $\Delta y / D_{\text{span}}$ | Relative Y vector to destination scaled by network span. |
| **9** | `euc_dist_norm`| $[0.0, 1.0]$ | $\|\Delta \mathbf{p}\| / D_{\text{span}}$ | Euclidean direct distance to destination. |
| **10** | `rem_dist_norm`| $[0.0, 1.0]$ | $d_{\text{rem}} / d_{\text{total}}$ | Fraction of remaining route distance along planned path. |
| **11** | `progress_ratio`| $[0.0, 1.0]$ | $1.0 - d_{\text{rem}} / d_{\text{total}}$ | Cumulative journey completion ratio. |
| **12** | `is_en_route` | $\{0.0, 1.0\}$ | Binary indicator | $1.0$ if vehicle lifecycle state is `EN_ROUTE`. |
| **13** | `is_blocked` | $\{0.0, 1.0\}$ | Binary indicator | $1.0$ if vehicle lifecycle state is `BLOCKED` or `STOPPED`. |
| **14** | `is_arrived` | $\{0.0, 1.0\}$ | Binary indicator | $1.0$ if vehicle lifecycle state is `ARRIVED`. |
| **15** | `speed_limit_norm`| $[0.0, 1.0]$ | $v_{\text{limit}} / v_{\max}$ | Speed limit of current road edge. |
| **16** | `edge_len_norm`| $[0.0, 1.0]$ | $L_{\text{edge}} / 500.0\text{ m}$ | Length of current road edge. |
| **17** | `edge_congestion`| $[0.0, 1.0]$ | $\text{clip}((M_{\text{cong}} - 1) / 4.0, 0, 1)$ | Congestion factor on current road edge. |
| **18** | `edge_closed` | $\{0.0, 1.0\}$ | Binary indicator | $1.0$ if current road edge is closed by active incident. |
| **19** | `outgoing_norm`| $[0.0, 1.0]$ | $K_{\text{out}} / K_{\max}$ ($K_{\max} = 8$) | Branch density of upcoming intersection node. |
| **20** | `signal_state` | $[0.0, 1.0]$ | $\{0.0: \text{None}, 0.33: \text{Green}, 0.66: \text{Yellow}, 1.0: \text{Red}\}$ | Approaching traffic signal phase. |
| **21** | `signal_dist` | $[0.0, 1.0]$ | $d_{\text{signal}} / 100.0\text{ m}$ | Distance to upcoming signalized intersection. |
| **22** | `nearest_v_dist`| $[0.0, 1.0]$ | $d_{\text{neighbor}} / 100.0\text{ m}$ | Distance to nearest other vehicle within 100m. |
| **23** | `nearest_v_rel_speed`| $[-1.0, 1.0]$ | $(v_{\text{other}} - v) / v_{\max}$ | Relative speed of nearest other vehicle. |
| **24** | `nearest_v_sin` | $[-1.0, 1.0]$ | $\sin(\theta_{\text{rel}})$ | Sine of relative bearing to nearest vehicle. |
| **25** | `nearest_v_cos` | $[-1.0, 1.0]$ | $\cos(\theta_{\text{rel}})$ | Cosine of relative bearing to nearest vehicle. |
| **26** | `incident_count`| $[0.0, 1.0]$ | $N_{\text{active}} / 10.0$ | Number of active incidents in the network. |
| **27** | `closure_dist` | $[0.0, 1.0]$ | $d_{\text{closure}} / 200.0\text{ m}$ | Distance to nearest closed road edge. |
| **28** | `emergency_nearby`| $\{0.0, 1.0\}$ | Binary indicator | $1.0$ if an active emergency vehicle is within awareness range. |
| **29** | `invalid_norm` | $[0.0, 1.0]$ | $N_{\text{invalid}} / 10.0$ | Consecutive invalid action count fraction. |
| **30** | `step_frac` | $[0.0, 1.0]$ | $t_{\text{step}} / T_{\max}$ | Episode step limit progression fraction. |
| **31** | `reserved` | $[0.0, 0.0]$ | Constant $0.0$ | Reserved alignment slot for future sensor embeddings. |

---

## 5. Action Space & Action Masking

- **Action Space:** `spaces.Discrete(K + 1)` where $K = \text{max\_outgoing\_actions}$ (default 8, size 9).
  - **Action 0 (`Keep Route`):** Maintains the vehicle's currently active planned route.
  - **Actions $1 \le a \le K$ (`Branch Selection`):** Selects outgoing edge index $(a-1)$ from the upcoming junction node, re-routing via A* from that edge to the destination node.
- **Action Masking Contract:**
  - `action_masks() -> np.ndarray[bool]` of length $K + 1$:
    - `mask[0] = True`: Keep Route is always structurally permissible.
    - `mask[i + 1] = True` iff outgoing edge $i$ exists from the upcoming anchor node and is **not closed** under active road closures in `IncidentManager`.
- **Invalid Action Handling:**
  - If the agent emits an unmasked or non-existent branch index, the simulation state is **not corrupted**.
  - The invalid action is logged, the vehicle maintains its current trajectory, consecutive invalid counter is incremented, and an invalid action penalty is assessed in the reward.

---

## 6. Objective-Driven Reward Formulation

The step reward balances destination progress against travel time and safety:

$$R = R_{\text{progress}} + R_{\text{step\_penalty}} + R_{\text{arrival}} + R_{\text{collision}} + R_{\text{near\_miss}} + R_{\text{invalid}} + R_{\text{truncation}} + R_{\text{reroute}}$$

| Component | Default Weight / Cost | Mathematical Formula | Purpose & Contract |
| :--- | :---: | :--- | :--- |
| **Progress** | $w_{\text{prog}} = 1.0$ | $w_{\text{prog}} \cdot \frac{d_{t-1} - d_t}{D_{\text{span}}}$ | Rewards moving closer to destination; penalizes moving away. |
| **Step Penalty** | $c_{\text{step}} = 0.05$ | $-c_{\text{step}}$ | Constant per-step penalty encouraging prompt route completion. |
| **Arrival Bonus** | $A = +100.0$ | $+A \cdot \mathbb{I}(\text{arrived} \land \neg \text{rewarded})$ | Credited **strictly once** when the vehicle reaches destination. |
| **Collision Penalty** | $c_{\text{col}} = 20.0$ | $-c_{\text{col}} \cdot N_{\text{new\_collisions}}$ | Severe penalty for physical vehicle overlap collisions. |
| **Near-Miss Penalty**| $c_{\text{nm}} = 2.0$ | $-c_{\text{nm}} \cdot N_{\text{new\_near\_misses}}$ | Penalty for safety buffer separation violations. |
| **Invalid Action** | $c_{\text{inv}} = 1.0$ | $-c_{\text{inv}} \cdot \mathbb{I}(\text{is\_invalid})$ | Penalizes choosing closed or out-of-bounds branches. |
| **Truncation Penalty**| $c_{\text{trunc}} = 10.0$ | $-c_{\text{trunc}} \cdot \mathbb{I}(\text{is\_truncated})$ | Assessed upon reaching step limit without completing trip. |
| **Reroute Cost** | $c_{\text{reroute}} = 0.1$ | $-c_{\text{reroute}} \cdot \mathbb{I}(\text{is\_rerouted})$ | Small hysteresis cost preventing route chattering. |

Reward diagnostics are exposed transparently in `info["reward_components"]` using `RewardBreakdown.to_dict()`.

---

## 7. Determinism, Seed Policy & State Isolation

1. **Seeded Reset Invariant:** `env.reset(seed=S)` deterministically seeds Python's `random`, `numpy.random`, and scenario construction PRNGs. Identical seeds produce bit-identical initial observations, graph topology, vehicle spawn positions, and action masks.
2. **Deterministic Trajectory Invariant:** Stepping an identical deterministic action sequence from identical initial seeds produces bit-identical observation trajectories and rewards.
3. **Complete State Isolation Invariant:** Separate environment instances maintain independent simulation worlds. Stepping or mutating one environment has zero effect on other instances. Repeated resets clear all accumulators, incident registries, and vehicle kinematic states.

---

## 8. Multi-Agent Decentralized Environment (`AMAPPMultiAgentEnv`)

`AMAPPMultiAgentEnv` extends the single-agent environment to coordinate multiple autonomous vehicles simultaneously:
- **Agents:** `env.agents: list[str]` enumerating active controlled vehicle identifiers.
- **Spaces:** `env.observation_spaces[agent_id]` and `env.action_spaces[agent_id]`.
- **Reset:** `reset(seed=...) -> (obs_dict, info_dict)` returning per-agent observations and metadata.
- **Step:** `step(actions: dict[str, int]) -> (obs_dict, rew_dict, term_dict, trunc_dict, info_dict)`.
- **Action Masking:** `action_masks(agent_id: str) -> np.ndarray[bool]` isolates legal branch choices per vehicle without cross-agent contamination.
- **Shared World Physics:** Vehicles move in a common road graph, observe each other through neighbor tables, and share V2V communication without duplicating simulation clocks.

---

## 9. Phase 31 Benchmark Integration Bridge

- **Function:** `evaluate_rl_environment_episode(scenario_id, policy, seed, max_steps)`
- **Benchmark Compatibility:** Bridges Gymnasium environment execution into the Phase 31 reproducible benchmarking framework, returning authoritative `BenchmarkTrialResult` records.
- **Test Policies:**
  - `GreedyProgressTestPolicy`: Deterministic baseline selecting branch actions that minimize Euclidean distance to destination.
  - `RandomTestPolicy`: Stress test policy sampling uniformly from legal action mask branches.
- **Metrics Integrity:** True simulation ticks, travel times, collision counts, near-misses, and V2V PDR are captured directly from the simulation engine.

---

## 10. Verification & Test Evidence

### Backend Quality Suite
- **Pytest Results:** **1,170 passed, 0 failed** in 44.61s.
- **Backend Line Coverage:** **95.12%** (well above the 80% threshold).
- **RL Environment Tests (`test_rl_environment.py`):** **26 passed, 0 failed** covering:
  - `check_env` validation on `AMAPPSingleAgentEnv`.
  - Observation space bounds, dtype, shape, and normalization.
  - Reset and step return tuple contracts.
  - Post-termination step warning handling.
  - Seed determinism and multi-instance state isolation.
  - Outgoing branch action masking and closed edge filtering.
  - Invalid action rejection without state corruption.
  - Reward calculation, arrival bonus single-credit, and component breakdown.
  - Multi-agent environment (`AMAPPMultiAgentEnv`) reset, step, and per-agent masking.
  - Benchmark evaluation bridge execution (`evaluate_rl_environment_episode`).
- **Reproducible Benchmark Smoke Check:** `python backend/manage.py run_benchmark --smoke` passed with 0 errors.
- **RL Environment Smoke Check:** `python -c "from apps.core.rl.env import AMAPPSingleAgentEnv; from gymnasium.utils.env_checker import check_env; check_env(AMAPPSingleAgentEnv())"` passed with 0 errors.
- **Ruff Linting:** All backend code passed clean (0 errors).
- **Django System Checks:** `python backend/manage.py check` identified no issues (0 silenced).

### Frontend Quality Suite
- **Vitest Unit & Component Tests:** **192 passed across 11 test suites** in 6.05s.
- **TypeScript Typechecking:** `npm run typecheck` passed with 0 errors.
- **ESLint Linting:** `npm run lint` passed with 0 errors.
- **Production Build:** `npm run build` succeeded creating optimized production bundle in `dist/`.

---

## 11. CI Workflow Evolution & Verification Evidence

### Modifications to `.github/workflows/ci.yml`
1. Added `"docs/progress/PHASE_32.md"` to mandatory files in `repo-hygiene`.
2. Added `gymnasium` to the runtime environment dependency verification step in `backend-quality`.
3. Added an automated `Run Gymnasium RL Environment Smoke Verification` step executing `check_env(AMAPPSingleAgentEnv())`.

### GitHub Actions CI Verification Gate (Rule 1 Non-Negotiable)
- **Workflow Run URL:** `https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/runs/39714625371`
- **Implementation Commit SHA:** `aa7d759`
- **Required Job Outcomes:**
  - `Repository Hygiene & Documentation Integrity`: **PASSED** (ID: 119613674920, 6s)
  - `Backend Lint, Test & Coverage`: **PASSED** (ID: 119613674860, 1m6s, 1,170 tests passed, 95.12% line coverage, RL env smoke passed)
  - `Frontend Lint, Typecheck, Test & Production Build`: **PASSED** (ID: 119613674702, 7m30s, 192 tests passed, build succeeded)


---

## 12. Requirements Traceability Impact

| Requirement | Description | Phase 32 Status | Notes |
| :--- | :--- | :---: | :--- |
| **FR-13** | AI Model Training Using Reinforcement Learning | **IN PROGRESS** | Single-agent and multi-agent Gymnasium environments implemented, verified with `check_env`, and bridged to benchmark framework. Policy training, PPO baselines, and convergence evaluation belong to Phase 33. |
| **FR-14** | Real-Time 3D Visualization and Interactive Dashboard | **TESTED** | All 192 frontend tests passing; production bundle build verified. |

---

## 13. Exact Phase 33 Handoff Instructions

When transitioning to **Phase 33: Train and Save an RL Baseline**:
1. **Scope:** Install Stable-Baselines3 (or clean PPO implementation), formulate training scripts with fixed random seeds, train a baseline PPO policy on standardized scenarios (e.g. `bench_grid_sparse_3x3`), and persist model artifacts.
2. **Environment Interface:** Directly wrap or instantiate `AMAPPSingleAgentEnv` with `SingleAgentRLConfig`. Use `action_masks()` with `MaskablePPO` (from `sb3-contrib`) or standard PPO with penalized invalid actions.
3. **Persistence:** Save trained model checkpoints in a designated artifacts directory (`artifacts/rl_models/`) and verify deterministic reload without unsafe deserialization.
4. **Fallback Invariant:** Ensure the system preserves fallback to Dijkstra, A*, or static/adaptive routing if a learned model is missing or fails.
5. **No Scope Creep:** Do not integrate the trained policy into production REST/WebSocket routing in Phase 33; policy evaluation on held-out scenarios and runtime integration belong to Phase 34.
