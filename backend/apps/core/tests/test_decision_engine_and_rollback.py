"""Integration tests for SimulationEngine stepping, atomic rollback, and determinism."""

from unittest.mock import patch

import pytest

from apps.core.coordination.models import (
    BeliefRecord,
    BeliefStatus,
    ReportType,
)
from apps.core.decision.config import DecisionConfig
from apps.core.domain.models import Vehicle
from apps.core.domain.values import Position2D
from apps.core.graph.generator import CityGridConfig, generate_synthetic_city_grid
from apps.core.kinematics.vehicle_agent import VehicleAgent
from apps.core.routing.models import AdaptiveRoutingConfig
from apps.core.routing.planner import RoutePlanner
from apps.core.simulation.engine import SimulationEngine
from apps.core.simulation.exceptions import TickExecutionError
from apps.core.simulation.world import WorldState


def _setup_engine(decision_enabled: bool = True):
    """Set up a simulation engine with a 3x3 grid and one vehicle."""
    graph = generate_synthetic_city_grid(
        CityGridConfig(rows=3, cols=3, spacing_m=100.0, bidirectional=True)
    )
    planner = RoutePlanner(graph)

    route_res = planner.find_route("node_r0_c0", "node_r0_c2")
    vehicle = Vehicle(
        id="veh_1",
        position=Position2D(x=0.0, y=0.0),
        heading_rad=0.0,
        speed_mps=10.0,
        current_node_id="node_r0_c0",
        target_node_id="node_r0_c2",
    )
    agent = VehicleAgent(vehicle, road_graph=graph)
    agent.assign_route(route_res.route)

    world = WorldState(
        road_graph=graph,
        adaptive_routing_config=AdaptiveRoutingConfig(enabled=True, reroute_cooldown_s=0.0),
        decision_config=DecisionConfig(enabled=decision_enabled),
    )
    world.add_agent(agent)
    world.save_baseline()

    engine = SimulationEngine(world)
    return engine, agent


def test_engine_step_populates_decision_metrics_and_records():
    """Verify that engine.step() populates decision telemetry in TickResult and WorldSnapshot."""
    engine, agent = _setup_engine(decision_enabled=True)

    # Ingest a closure belief into vehicle store to trigger decision evaluation
    store = engine.world.coordination_manager.get_store(agent.vehicle.id)
    store._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    tick_res = engine.step()
    assert tick_res.decision_metrics is not None
    assert tick_res.decision_metrics["decisions_evaluated"] >= 1
    assert tick_res.decision_records is not None
    assert len(tick_res.decision_records) >= 1

    snap = engine.world.get_snapshot()
    assert snap.decision_metrics is not None
    assert snap.decision_records is not None


def test_engine_atomic_rollback_on_failure():
    """Verify that if tick fails during execution, decision state is atomically restored."""
    engine, agent = _setup_engine(decision_enabled=True)

    # Ingest a closure belief
    store = engine.world.coordination_manager.get_store(agent.vehicle.id)
    store._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    # Baseline pre-tick decision state
    pre_eval_count = engine.world.decision_manager.metrics.decisions_evaluated
    pre_records_count = len(engine.world.decision_manager._records)

    # Inject failure during agent.step()
    with patch.object(agent, "step", side_effect=RuntimeError("Simulated kinematic failure")):
        with pytest.raises(TickExecutionError):
            engine.step()

    # Verify decision manager state was atomically rolled back to pre-tick counts
    assert engine.world.decision_manager.metrics.decisions_evaluated == pre_eval_count
    assert len(engine.world.decision_manager._records) == pre_records_count


def test_engine_deterministic_replay():
    """Verify that two identical runs produce bit-identical decision telemetry."""
    engine1, agent1 = _setup_engine(decision_enabled=True)
    engine2, agent2 = _setup_engine(decision_enabled=True)

    for eng, ag in [(engine1, agent1), (engine2, agent2)]:
        st = eng.world.coordination_manager.get_store(ag.vehicle.id)
        st._beliefs["b1"] = BeliefRecord(
            belief_id="b1",
            belief_type=ReportType.ROAD_CLOSURE,
            target_id="edge_r0_c0_to_r0_c1",
            status=BeliefStatus.ACTIVE,
            confidence=1.0,
            last_evidence_timestamp_s=0.0,
            attributes={"closure_status": "closed"},
        )

    r1 = engine1.step()
    r2 = engine2.step()

    m1_no_time = {
        k: v for k, v in r1.decision_metrics.items() if "time" not in k and "latency" not in k
    }
    m2_no_time = {
        k: v for k, v in r2.decision_metrics.items() if "time" not in k and "latency" not in k
    }
    assert m1_no_time == m2_no_time
    # Compare record attributes except decision_id timing if identical
    assert len(r1.decision_records) == len(r2.decision_records)
    for rec1, rec2 in zip(r1.decision_records, r2.decision_records):
        assert rec1["outcome"] == rec2["outcome"]
        assert rec1["reason_code"] == rec2["reason_code"]
        assert rec1["selected_candidate_id"] == rec2["selected_candidate_id"]


def test_world_reset_restores_initial_decision_state():
    """Verify world.reset() restores decision manager to baseline initial state."""
    engine, agent = _setup_engine(decision_enabled=True)

    store = engine.world.coordination_manager.get_store(agent.vehicle.id)
    store._beliefs["b1"] = BeliefRecord(
        belief_id="b1",
        belief_type=ReportType.ROAD_CLOSURE,
        target_id="edge_r0_c0_to_r0_c1",
        status=BeliefStatus.ACTIVE,
        confidence=1.0,
        last_evidence_timestamp_s=0.0,
        attributes={"closure_status": "closed"},
    )

    engine.step()
    assert engine.world.decision_manager.metrics.decisions_evaluated >= 1

    # Reset world
    engine.world.reset()
    assert engine.world.decision_manager.metrics.decisions_evaluated == 0
    assert len(engine.world.decision_manager._records) == 0
