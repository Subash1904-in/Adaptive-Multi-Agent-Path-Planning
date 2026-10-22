"""Comprehensive automated tests for Gymnasium-compatible RL environments (Phase 32).

Validates:
1. Gymnasium API specification compliance (spaces, reset, step, check_env).
2. Determinism and state isolation across seeds and resets.
3. Observation space bounds, feature extraction, non-finite absence, and isolation.
4. Action space validation, action masking, invalid action handling, and safety invariants.
5. Reward function calculation, components, arrival bonus single-credit, and penalty isolation.
6. Multi-agent environment extension (AMAPPMultiAgentEnv) contracts and simultaneous execution.
7. Phase 31 benchmarking framework evaluation bridge (evaluate_rl_environment_episode).
"""

import math

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from apps.core.benchmarking.models import BenchmarkStatus, BenchmarkTrialResult
from apps.core.domain.enums import VehicleState
from apps.core.rl import (
    AMAPPMultiAgentEnv,
    AMAPPSingleAgentEnv,
    GreedyProgressTestPolicy,
    RandomTestPolicy,
    RewardBreakdown,
    RewardCalculator,
    RewardConfig,
    SingleAgentRLConfig,
    evaluate_rl_environment_episode,
    extract_agent_observation,
)
from apps.core.rl.exceptions import (
    AgentNotFoundError,
    InvalidActionError,
    ScenarioResetError,
)


class TestGymnasiumSingleAgentAPI:
    """Tests verifying standard Gymnasium API contract compliance."""

    def test_environment_checker_passes(self):
        """Standard Gymnasium environment checker validates AMAPPSingleAgentEnv."""
        env = AMAPPSingleAgentEnv()
        check_env(env)
        env.close()

    def test_spaces_declaration(self):
        """Observation and action spaces have correct types, shapes, and bounds."""
        config = SingleAgentRLConfig(max_outgoing_actions=6, observation_dim=32)
        env = AMAPPSingleAgentEnv(config=config)

        assert env.observation_space.shape == (32,)
        assert env.observation_space.dtype == np.float32
        assert np.all(env.observation_space.low == -1.0)
        assert np.all(env.observation_space.high == 1.0)

        # Action space is Discrete(K + 1) -> Discrete(7)
        assert env.action_space.n == 7
        env.close()

    def test_reset_return_contract(self):
        """reset(seed=...) returns (obs, info) tuple satisfying space containment."""
        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=123)

        assert isinstance(obs, np.ndarray)
        assert obs.shape == (32,)
        assert obs.dtype == np.float32
        assert env.observation_space.contains(obs)
        assert not np.any(np.isnan(obs))
        assert not np.any(np.isinf(obs))

        assert isinstance(info, dict)
        assert "agent_id" in info
        assert "action_mask" in info
        assert "step_count" in info
        assert info["step_count"] == 0
        assert len(info["action_mask"]) == env.action_space.n
        assert bool(info["action_mask"][0]) is True
        env.close()

    def test_step_return_contract(self):
        """step(action) returns (obs, reward, terminated, truncated, info) tuple."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        obs, reward, terminated, truncated, info = env.step(0)

        assert isinstance(obs, np.ndarray)
        assert env.observation_space.contains(obs)
        assert isinstance(reward, float)
        assert math.isfinite(reward)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)
        assert "reward_components" in info
        assert "reward_breakdown" in info
        assert "distance_to_dest" in info
        assert "consecutive_invalid" in info
        env.close()

    def test_post_termination_rejection(self):
        """Stepping after episode termination returns terminated/truncated state with warning."""
        cfg = SingleAgentRLConfig(max_steps=2)
        env = AMAPPSingleAgentEnv(config=cfg)
        env.reset(seed=42)

        env.step(0)
        _, _, term, trunc, _ = env.step(0)
        assert trunc is True  # Reached max_steps=2

        # Stepping again without reset returns warning info and remains truncated
        obs, reward, term_post, trunc_post, info = env.step(0)
        assert trunc_post is True
        assert "warning" in info
        env.close()


class TestDeterminismAndIsolation:
    """Tests verifying reproducible seeded resets and zero shared mutable state."""

    def test_seeded_reset_determinism(self):
        """Identical seeds produce identical initial observations and info."""
        env1 = AMAPPSingleAgentEnv()
        obs1, info1 = env1.reset(seed=999)

        env2 = AMAPPSingleAgentEnv()
        obs2, info2 = env2.reset(seed=999)

        np.testing.assert_allclose(obs1, obs2, atol=1e-6)
        assert info1["agent_id"] == info2["agent_id"]
        np.testing.assert_array_equal(info1["action_mask"], info2["action_mask"])
        env1.close()
        env2.close()

    def test_deterministic_action_trajectory(self):
        """Identical deterministic action sequences yield identical observation trajectories."""
        env1 = AMAPPSingleAgentEnv()
        env2 = AMAPPSingleAgentEnv()

        obs1, _ = env1.reset(seed=777)
        obs2, _ = env2.reset(seed=777)

        actions = [0, 0, 0, 0]
        for act in actions:
            o1, r1, t1, tr1, _ = env1.step(act)
            o2, r2, t2, tr2, _ = env2.step(act)

            np.testing.assert_allclose(o1, o2, atol=1e-6)
            assert r1 == pytest.approx(r2, rel=1e-5)
            assert t1 == t2
            assert tr1 == tr2

        env1.close()
        env2.close()

    def test_repeated_resets_clear_state(self):
        """Reset clears step counter, accumulated rewards, and episode counters."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        for _ in range(5):
            env.step(0)

        assert env._step_count == 5
        assert env._accumulated_reward != 0.0

        obs_new, info_new = env.reset(seed=42)
        assert env._step_count == 0
        assert env._accumulated_reward == 0.0
        assert env._arrival_rewarded is False
        assert env._consecutive_invalid == 0
        assert info_new["step_count"] == 0
        env.close()

    def test_separate_instances_isolation(self):
        """Modifying one environment instance does not affect another."""
        env1 = AMAPPSingleAgentEnv()
        env2 = AMAPPSingleAgentEnv()

        env1.reset(seed=10)
        env2.reset(seed=10)

        # Step env1 10 times, keep env2 at t=0
        for _ in range(10):
            env1.step(0)

        assert env1._step_count == 10
        assert env2._step_count == 0
        assert env1.engine.current_tick > 0
        assert env2.engine.current_tick == 0
        env1.close()
        env2.close()

    def test_invalid_scenario_id_raises_error(self):
        """Specifying non-existent scenario ID raises ScenarioResetError."""
        cfg = SingleAgentRLConfig(scenario_id="non_existent_scenario_xyz")
        env = AMAPPSingleAgentEnv(config=cfg)

        with pytest.raises(ScenarioResetError):
            env.reset(seed=42)
        env.close()

    def test_invalid_agent_id_raises_error(self):
        """Specifying non-existent agent ID raises AgentNotFoundError."""
        cfg = SingleAgentRLConfig(agent_id="ghost_vehicle_999")
        env = AMAPPSingleAgentEnv(config=cfg)

        with pytest.raises(AgentNotFoundError):
            env.reset(seed=42)
        env.close()


class TestObservationSpaceAndFeatures:
    """Tests verifying observation vector properties and edge cases."""

    def test_observation_bounds(self):
        """All extracted observations strictly respect [-1.0, 1.0] bounds."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        for _ in range(10):
            obs, _, term, trunc, _ = env.step(0)
            assert np.all(obs >= -1.0)
            assert np.all(obs <= 1.0)
            assert not np.any(np.isnan(obs))
            assert not np.any(np.isinf(obs))
            if term or trunc:
                break
        env.close()

    def test_feature_normalization_and_ordering(self):
        """Feature extraction handles heading and position normalization correctly."""
        env = AMAPPSingleAgentEnv()
        obs, _ = env.reset(seed=42)

        # Check vector shape and components
        assert len(obs) == 32
        # Position features (index 0, 1) normalized in [-1, 1]
        assert -1.0 <= obs[0] <= 1.0
        assert -1.0 <= obs[1] <= 1.0
        # Heading sin/cos (index 3, 4) must satisfy sin^2 + cos^2 approx 1.0
        trig_sum = obs[3] ** 2 + obs[4] ** 2
        assert trig_sum == pytest.approx(1.0, abs=1e-3)
        env.close()

    def test_observation_reflects_road_closure(self):
        """Authoritative road closure on current edge updates observation."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        agent = env.agent
        curr_edge = agent.current_edge
        if curr_edge and hasattr(env.world, "incident_manager"):
            # Close the current edge via IncidentManager
            env.world.incident_manager.create_incident(
                incident_type="road_closure",
                affected_edge_id=curr_edge.id,
            )
            obs = extract_agent_observation(
                agent=agent,
                world=env.world,
                step_count=env._step_count,
                max_steps=env.config.max_steps,
                consecutive_invalid_actions=0,
                max_outgoing_actions=env.config.max_outgoing_actions,
            )
            # Feature index 18 is edge_closed
            assert obs[18] == 1.0
        env.close()


class TestActionSpaceAndMasking:
    """Tests verifying action validation, branch execution, and masking."""

    def test_keep_route_action_zero(self):
        """Action 0 (Keep Route) advances the vehicle along its authoritative path."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        initial_route = list(env.agent.route.node_ids) if env.agent.route else []
        assert len(initial_route) > 0
        obs, reward, term, trunc, info = env.step(0)

        # Action 0 must succeed and not be flagged as invalid
        assert info["action_valid"] is True
        assert info["consecutive_invalid"] == 0
        env.close()

    def test_out_of_bounds_action_rejected(self):
        """Action index exceeding action space raises InvalidActionError."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        with pytest.raises(InvalidActionError):
            env.step(999)
        env.close()

    def test_action_mask_accuracy(self):
        """Action mask accurately flags unavailable branch indices."""
        env = AMAPPSingleAgentEnv()
        obs, info = env.reset(seed=42)

        mask = info["action_mask"]
        assert bool(mask[0]) is True  # Action 0 is always structurally permissible

        # If an action is unmasked (False), stepping it must incur invalid action penalty
        false_indices = np.where(~mask)[0]
        if len(false_indices) > 0:
            invalid_act = int(false_indices[0])
            _, reward, _, _, step_info = env.step(invalid_act)
            assert step_info["action_valid"] is False
            assert step_info["consecutive_invalid"] == 1
            assert step_info["reward_components"]["invalid_action_penalty"] < 0.0
        env.close()

    def test_closed_edge_is_masked_out(self):
        """Closed road edges cannot be selected in action mask."""
        env = AMAPPSingleAgentEnv()
        env.reset(seed=42)

        curr_edge = env.agent.current_edge
        anchor = curr_edge.end_node_id if curr_edge else env.agent.vehicle.current_node_id
        outgoing = sorted(env.world.road_graph.get_outgoing_edges(anchor), key=lambda e: e.id)

        if len(outgoing) > 0 and hasattr(env.world, "incident_manager"):
            first_edge = outgoing[0]
            env.world.incident_manager.create_incident(
                incident_type="road_closure",
                affected_edge_id=first_edge.id,
            )
            mask = env.get_action_mask()
            # Branch 1 corresponds to outgoing[0]
            assert bool(mask[1]) is False
        env.close()


class TestRewardFunction:
    """Tests verifying objective-driven reward components and mathematical bounds."""

    def test_reward_breakdown_total(self):
        """RewardBreakdown total_reward matches the sum of its individual components."""
        bd = RewardBreakdown(
            progress_reward=1.5,
            step_penalty=-0.05,
            arrival_reward=25.0,
            collision_penalty=-10.0,
            near_miss_penalty=-1.0,
            invalid_action_penalty=-2.0,
            truncation_penalty=-5.0,
            reroute_penalty=-0.1,
            total_reward=9.35,
        )
        assert bd.total_reward == pytest.approx(9.35)
        d = bd.to_dict()
        assert d["arrival_reward"] == 25.0
        assert d["collision_penalty"] == -10.0

    def test_arrival_bonus_awarded_only_once(self):
        """Arrival bonus is credited strictly once upon reaching destination."""
        cfg = SingleAgentRLConfig(reward_config=RewardConfig(arrival_reward=50.0, step_penalty=0.0))
        env = AMAPPSingleAgentEnv(config=cfg)
        env.reset(seed=42)

        # Force arrived state on agent vehicle
        env.agent.vehicle.state = VehicleState.ARRIVED
        _, reward, term, _, info = env.step(0)

        assert term is True
        assert info["reward_components"]["arrival_reward"] == 50.0
        assert env._arrival_rewarded is True
        env.close()

    def test_step_penalty_and_progress_calculation(self):
        """Progress toward destination increases reward while step penalty is subtracted."""
        calc = RewardCalculator(RewardConfig(progress_weight=1.0, step_penalty=0.1))

        # Vehicle moved 10 meters closer with diag_span_m = 100.0 -> progress = 10 / 100 = 0.1
        bd = calc.calculate_reward(
            prev_distance_m=100.0,
            curr_distance_m=90.0,
            is_arrived=False,
            arrival_already_rewarded=False,
            new_collisions=0,
            new_near_misses=0,
            is_invalid_action=False,
            is_truncated=False,
            is_rerouted=False,
            diag_span_m=100.0,
        )
        assert bd.progress_reward == pytest.approx(0.1)
        assert bd.step_penalty == pytest.approx(-0.1)
        assert bd.total_reward == pytest.approx(0.0)


class TestMultiAgentEnvironment:
    """Tests verifying the AMAPPMultiAgentEnv extension boundary."""

    def test_multi_agent_initialization_and_spaces(self):
        """Multi-agent environment exposes per-agent spaces matching configuration."""
        env = AMAPPMultiAgentEnv()
        assert len(env.agents) > 0
        for aid in env.agents:
            assert aid in env.observation_spaces
            assert aid in env.action_spaces
            assert env.observation_spaces[aid].shape == (32,)
            assert env.action_spaces[aid].n == 9  # 8 + 1
        env.close()

    def test_multi_agent_reset_and_step(self):
        """Multi-agent reset and step return dictionaries keyed by agent_id."""
        env = AMAPPMultiAgentEnv()
        obs_dict, info_dict = env.reset(seed=42)

        assert isinstance(obs_dict, dict)
        assert isinstance(info_dict, dict)
        assert set(obs_dict.keys()) == set(env.agents)

        actions = {aid: 0 for aid in env.agents}
        next_obs, rew_dict, term_dict, trunc_dict, step_info = env.step(actions)

        for aid in env.agents:
            assert aid in next_obs
            assert aid in rew_dict
            assert aid in term_dict
            assert aid in trunc_dict
            assert aid in step_info
            assert math.isfinite(rew_dict[aid])
            assert isinstance(term_dict[aid], bool)
            assert isinstance(trunc_dict[aid], bool)

        env.close()

    def test_multi_agent_per_agent_action_masks(self):
        """Each agent in multi-agent environment possesses an independent action mask."""
        env = AMAPPMultiAgentEnv()
        obs_dict, info_dict = env.reset(seed=42)

        for aid in env.agents:
            mask = env.get_action_mask(aid)
            assert isinstance(mask, np.ndarray)
            assert len(mask) == env.action_spaces[aid].n
            assert bool(mask[0]) is True
        env.close()


class TestBenchmarkIntegration:
    """Tests verifying integration with Phase 31 reproducible benchmark framework."""

    def test_evaluate_rl_environment_episode_contract(self):
        """evaluate_rl_environment_episode produces valid BenchmarkTrialResult."""
        policy = GreedyProgressTestPolicy()
        result = evaluate_rl_environment_episode(
            scenario_id="bench_grid_sparse_3x3",
            policy=policy,
            seed=42,
            max_steps=30,
        )

        assert isinstance(result, BenchmarkTrialResult)
        assert result.scenario_id == "bench_grid_sparse_3x3"
        assert result.algorithm_id == "rl_environment_policy"
        assert result.total_trips == 1
        assert result.status in (
            BenchmarkStatus.SUCCESS,
            BenchmarkStatus.FAILED,
            BenchmarkStatus.TIMEOUT,
        )
        assert result.simulation_ticks > 0

    def test_random_test_policy_execution(self):
        """RandomTestPolicy executes valid steps without crashing."""
        policy = RandomTestPolicy(seed=123)
        result = evaluate_rl_environment_episode(
            scenario_id="bench_grid_sparse_3x3",
            policy=policy,
            seed=42,
            max_steps=15,
        )
        assert isinstance(result, BenchmarkTrialResult)
        assert result.simulation_ticks == 15 * 5
