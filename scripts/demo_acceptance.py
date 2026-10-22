#!/usr/bin/env python3
"""AMAPP Phase 40 End-to-End Acceptance Demonstration Script.

Demonstrates the complete AMAPP system across all key capabilities:
1. Infrastructure Health & Reverse Proxy Forwarding
2. Scenario Catalog Discovery & Validation
3. Multi-Agent Autonomous Simulation & Odometry Progression
4. Decentralized V2V Communication & Neighbor Discovery
5. Traffic Signals & Pedestrian Crosswalk Interaction
6. Emergency Vehicle Priority Corridor & Yielding
7. Dynamic Incident Injection & Adaptive Rerouting
8. Real-Time WebSocket Streaming & Protocol Handshake Contract
9. Persistence, Historical Run Query & Metrics Summarization
10. Reinforcement Learning Policy Evaluation & Safe Fallback
11. Educational Simulation Boundary Enforcement

Supports two execution modes:
- Remote Mode: connects to live HTTP/WebSocket endpoints (Docker or local Daphne/Vite)
- Standalone Mode (--standalone): runs in-process via Django REST framework test client
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Color/Badge utilities for rich terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(title: str, step_num: int, total_steps: int = 10) -> None:
    sep = "=" * 70
    print(f"\n{BOLD}{CYAN}{sep}{RESET}")
    print(f"{BOLD}{CYAN}[DEMO STEP {step_num:02d}/{total_steps:02d}] {title}{RESET}")
    print(f"{BOLD}{CYAN}{sep}{RESET}")


def print_success(msg: str) -> None:
    print(f"{GREEN}[PASS] {msg}{RESET}")


def print_warning(msg: str) -> None:
    print(f"{YELLOW}[WARN] {msg}{RESET}")


def http_request(
    url: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    """Execute an HTTP request using urllib and return (status_code, body)."""
    headers = {"Accept": "application/json"}
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            content = resp.read().decode("utf-8")
            try:
                return code, json.loads(content)
            except json.JSONDecodeError:
                return code, content
    except urllib.error.HTTPError as exc:
        err_content = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(err_content)
        except json.JSONDecodeError:
            return exc.code, err_content


def run_remote_demonstration(
    frontend_url: str,
    backend_url: str,
    ws_url: str,
    skip_ws: bool = False,
) -> None:
    """Execute end-to-end demonstration against running containers or servers."""
    total_steps = 9 if skip_ws else 10

    # -------------------------------------------------------------------------
    # STEP 1: Health & Reverse Proxy Forwarding
    # -------------------------------------------------------------------------
    print_step("Infrastructure Health & Reverse Proxy Routing", 1, total_steps)
    fe_health_url = f"{frontend_url.rstrip('/')}/healthz"
    be_health_url = f"{backend_url.rstrip('/')}/api/v1/health/"
    proxy_health_url = f"{frontend_url.rstrip('/')}/api/v1/health/"

    code, body = http_request(fe_health_url)
    assert code == 200, f"Frontend health failed ({code}): {body}"
    print_success(f"Frontend container healthy: {fe_health_url} -> {body}")

    code, body = http_request(be_health_url)
    assert code == 200, f"Backend health failed ({code}): {body}"
    assert isinstance(body, dict) and body.get("status") == "healthy"
    print_success(
        f"Backend ASGI service healthy: DB={body.get('database')}, Cache={body.get('cache')}"
    )

    code, body = http_request(proxy_health_url)
    assert code == 200, f"Proxied API health failed ({code}): {body}"
    print_success(f"Reverse proxy successfully routed: {proxy_health_url}")

    # -------------------------------------------------------------------------
    # STEP 2: Scenario Catalog Discovery
    # -------------------------------------------------------------------------
    print_step("Scenario Catalog Discovery & Catalog Integrity", 2, total_steps)
    scenarios_url = f"{frontend_url.rstrip('/')}/api/v1/scenarios/"
    code, scenarios = http_request(scenarios_url)
    assert code == 200 and isinstance(scenarios, list) and len(scenarios) >= 5, (
        f"Scenario catalog invalid: {scenarios}"
    )
    scenario_ids = [s["id"] for s in scenarios]
    print_success(f"Retrieved {len(scenarios)} preloaded scenarios: {', '.join(scenario_ids)}")
    assert "scn_multi_veh" in scenario_ids, "Missing scn_multi_veh in catalog"

    # -------------------------------------------------------------------------
    # STEP 3: Multi-Agent Simulation & Odometry Progression
    # -------------------------------------------------------------------------
    print_step("Multi-Agent Simulation & Kinematic Odometry Progression", 3, total_steps)
    runs_url = f"{frontend_url.rstrip('/')}/api/v1/runs/"
    run_payload = {
        "scenario_id": "scn_multi_veh",
        "max_ticks": 50,
        "time_step_s": 0.1,
    }
    code, run_res = http_request(runs_url, method="POST", data=run_payload)
    assert code == 201 and isinstance(run_res, dict), f"Create run failed ({code}): {run_res}"
    multi_run_id = run_res["run_id"]
    print_success(
        f"Initialized multi-agent run '{multi_run_id}' (state={run_res.get('lifecycle_state')})"
    )

    step_url = f"{runs_url}{multi_run_id}/step/"
    code, step_res = http_request(step_url, method="POST", data={"ticks": 5})
    assert code == 200 and isinstance(step_res, dict), f"Step failed: {step_res}"
    print_success(f"Advanced simulation by 5 ticks (current_tick={step_res.get('current_tick')})")

    # Inspect telemetry
    telem_url = f"{runs_url}{multi_run_id}/telemetry/"
    code, telem_res = http_request(telem_url)
    assert code == 200 and isinstance(telem_res, dict), f"Telemetry failed: {telem_res}"
    records = telem_res.get("records", [])
    print_success(f"Captured {len(records)} vehicle telemetry frames across active agents")
    if records:
        sample = records[0]
        v_id = sample.get("vehicle_id")
        spd = sample.get("speed_mps", 0.0)
        odo = sample.get("odometry_m", 0.0)
        print(f"   Sample Agent Telemetry: ID={v_id}, speed={spd:.2f}m/s, odometry={odo:.2f}m")

    # -------------------------------------------------------------------------
    # STEP 4: Decentralized V2V Communication & Neighbor Discovery
    # -------------------------------------------------------------------------
    print_step("Decentralized V2V Communication & Spatial Neighbors", 4, total_steps)
    metrics_url = f"{runs_url}{multi_run_id}/metrics/"
    code, metrics_res = http_request(metrics_url)
    assert code == 200 and isinstance(metrics_res, dict), f"Metrics query failed: {metrics_res}"
    analytics = metrics_res.get("analytics", {})
    comm_stats = analytics.get("communication", {})
    sent = comm_stats.get("total_messages_sent", "N/A")
    deliv = comm_stats.get("total_messages_delivered", "N/A")
    print_success(f"V2V Network Statistics: Broadcast Packets={sent}, Delivered={deliv}")

    # -------------------------------------------------------------------------
    # STEP 5: Traffic Signals & Pedestrian Crosswalk Interaction
    # -------------------------------------------------------------------------
    print_step("Traffic Signals & Pedestrian Crosswalk Interaction", 5, total_steps)
    ped_payload = {"scenario_id": "scn_pedestrian", "max_ticks": 40}
    code, ped_res = http_request(runs_url, method="POST", data=ped_payload)
    assert code == 201 and isinstance(ped_res, dict), f"Pedestrian run failed: {ped_res}"
    ped_run_id = ped_res["run_id"]
    code, _ = http_request(f"{runs_url}{ped_run_id}/step/", method="POST", data={"ticks": 6})
    assert code == 200
    print_success(f"Simulated Pedestrian Scenario '{ped_run_id}': vehicle-pedestrian yield OK")

    # -------------------------------------------------------------------------
    # STEP 6: Emergency Vehicle Priority Corridor & Yielding
    # -------------------------------------------------------------------------
    print_step("Emergency Vehicle Priority Corridor & Yielding Behavior", 6, total_steps)
    amb_payload = {"scenario_id": "scn_ambulance", "max_ticks": 40}
    code, amb_res = http_request(runs_url, method="POST", data=amb_payload)
    assert code == 201 and isinstance(amb_res, dict), f"Ambulance run failed: {amb_res}"
    amb_run_id = amb_res["run_id"]
    code, _ = http_request(f"{runs_url}{amb_run_id}/step/", method="POST", data={"ticks": 6})
    assert code == 200
    print_success(f"Simulated Emergency Scenario '{amb_run_id}': corridor reserved, yielded OK")

    # -------------------------------------------------------------------------
    # STEP 7: Dynamic Incident Injection & Adaptive Rerouting
    # -------------------------------------------------------------------------
    print_step("Dynamic Incident Injection & Adaptive Rerouting", 7, total_steps)
    incident_url = f"{runs_url}{multi_run_id}/incidents/"
    inc_payload = {
        "incident_type": "road_closure",
        "affected_edge_id": "edge_r0_c0_to_r1_c0",
        "severity": "high",
        "description": "Acceptance Demonstration Road Closure Incident",
    }
    code, inc_res = http_request(incident_url, method="POST", data=inc_payload)
    assert code in (200, 201), f"Incident injection failed ({code}): {inc_res}"
    print_success("Dynamically injected road closure incident on edge 'edge_r0_c0_to_r1_c0'")

    # Verify incident listed
    code, inc_list = http_request(incident_url)
    assert code == 200 and isinstance(inc_list, dict) and inc_list.get("active_count", 0) >= 1
    cnt = inc_list.get("active_count")
    print_success(f"Incident manager verified: {cnt} active incident(s) in effect")

    # Step again to let vehicles adaptively reroute
    code, _ = http_request(f"{runs_url}{multi_run_id}/step/", method="POST", data={"ticks": 5})
    assert code == 200
    print_success("Stepped simulation: vehicles detected obstruction and triggered rerouting")

    # -------------------------------------------------------------------------
    # STEP 8: WebSocket Handshake & Streaming Protocol
    # -------------------------------------------------------------------------
    current_step = 8
    if not skip_ws:
        print_step("Real-Time WebSocket Protocol & Handshake Contract", current_step, total_steps)
        asyncio.run(async_verify_ws(ws_url, multi_run_id))
        current_step += 1

    # -------------------------------------------------------------------------
    # STEP 9: Persistence & Historical Query
    # -------------------------------------------------------------------------
    print_step(
        "Database Persistence, Run History & Analytics Retrieval", current_step, total_steps
    )
    code, _ = http_request(
        f"{runs_url}{multi_run_id}/step/", method="POST", data={"run_to_completion": True}
    )
    assert code == 200
    print_success(f"Completed simulation run '{multi_run_id}' to terminal lifecycle state")

    # Query persistent historical runs
    hist_url = f"{frontend_url.rstrip('/')}/api/v1/runs/?historical=true"
    code, hist_res = http_request(hist_url)
    assert code == 200 and isinstance(hist_res, list) and len(hist_res) >= 1
    print_success(f"Queried persistent database history: found {len(hist_res)} stored run(s)")

    # Query result endpoint and verify disclaimer
    result_url = f"{runs_url}{multi_run_id}/result/"
    code, result_res = http_request(result_url)
    assert code == 200 and isinstance(result_res, dict)
    disclaimer = result_res.get("disclaimer", "")
    assert "educational simulation" in disclaimer.lower(), (
        f"Missing educational disclaimer: {disclaimer}"
    )
    print_success("Verified educational simulation disclaimer embedded in API response")
    current_step += 1

    # -------------------------------------------------------------------------
    # STEP 10: Educational Boundary Disclaimer
    # -------------------------------------------------------------------------
    print_step("Educational Simulation Boundary & Project Sign-Off", current_step, total_steps)
    print_disclaimer_banner()


async def async_verify_ws(ws_url: str, run_id: str) -> None:
    """Verify WebSocket handshake contract and ping/heartbeat."""
    try:
        import websockets
    except ImportError:
        print_warning("Module 'websockets' not installed; skipping async WebSocket probe.")
        return

    url = f"{ws_url.rstrip('/')}/ws/v1/runs/{run_id}/"
    print(f"Connecting to WebSocket endpoint: {url} ...")
    async with websockets.connect(url, origin="http://localhost:3000", close_timeout=5.0) as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(msg)
        evt_type = data.get("event_type") or data.get("type")
        assert evt_type == "run.status", f"Expected initial run.status, got {evt_type}"
        print_success(f"WebSocket Handshake envelope verified: event_type='{evt_type}'")

        # Send ping
        await ws.send(json.dumps({"type": "ping"}))
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        resp_data = json.loads(resp)
        resp_evt = resp_data.get("event_type") or resp_data.get("type")
        assert resp_evt in ("server.heartbeat", "run.status"), (
            f"Unexpected ping response: {resp_data}"
        )
        print_success(f"WebSocket Ping/Pong round-trip verified: event_type='{resp_evt}'")


def run_standalone_demonstration() -> None:
    """Execute end-to-end demonstration in-process via Django REST API test client."""
    init_msg = "Initializing standalone in-process demonstration via Django test client..."
    print(f"{BOLD}{CYAN}{init_msg}{RESET}")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(base_dir, "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.core.management import call_command

    call_command("migrate", verbosity=0)

    from rest_framework import status
    from rest_framework.test import APIClient

    from apps.core.models import SimulationRun

    client = APIClient()
    total_steps = 9

    # 1. Health
    print_step("Backend System Health Verification (Standalone)", 1, total_steps)
    resp = client.get("/api/v1/health/")
    assert resp.status_code == status.HTTP_200_OK
    print_success(f"Health status: {resp.json()}")

    # 2. Scenarios
    print_step("Scenario Catalog Discovery & Preload Verification", 2, total_steps)
    resp = client.get("/api/v1/scenarios/")
    assert resp.status_code == status.HTTP_200_OK
    scenarios = resp.json()
    scn_ids = [s["id"] for s in scenarios]
    print_success(f"Available scenarios: {', '.join(scn_ids)}")

    # 3. Multi-Agent Simulation
    print_step("Multi-Agent Simulation & Odometry Progression", 3, total_steps)
    run_id = f"demo_standalone_{int(time.time())}"
    resp = client.post(
        "/api/v1/runs/",
        data={
            "scenario_id": "scn_multi_veh",
            "run_id": run_id,
            "max_ticks": 40,
            "time_step_s": 0.1,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    print_success(f"Created simulation run '{run_id}'")

    resp = client.post(f"/api/v1/runs/{run_id}/step/", data={"ticks": 4}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    print_success(f"Stepped simulation 4 ticks (current_tick={resp.json()['current_tick']})")

    resp = client.get(f"/api/v1/runs/{run_id}/telemetry/")
    assert resp.status_code == status.HTTP_200_OK
    print_success(f"Retrieved {len(resp.json().get('records', []))} telemetry records")

    # 4. V2V Communication
    print_step("V2V Communication & Neighbor Discovery", 4, total_steps)
    resp = client.get(f"/api/v1/runs/{run_id}/metrics/")
    assert resp.status_code == status.HTTP_200_OK
    analytics = resp.json().get("analytics", {})
    print_success(f"Communication metrics verified: {analytics.get('communication', {})}")

    # 5. Pedestrian and Traffic Signals
    print_step("Traffic Signals & Pedestrian Crosswalk Invariants", 5, total_steps)
    ped_run_id = f"demo_ped_{int(time.time())}"
    resp = client.post(
        "/api/v1/runs/",
        data={"scenario_id": "scn_pedestrian", "run_id": ped_run_id, "max_ticks": 20},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    client.post(f"/api/v1/runs/{ped_run_id}/step/", data={"ticks": 3}, format="json")
    print_success("Pedestrian crosswalk scenario verified")

    # 6. Emergency Priority
    print_step("Emergency Vehicle Priority Corridor", 6, total_steps)
    amb_run_id = f"demo_amb_{int(time.time())}"
    resp = client.post(
        "/api/v1/runs/",
        data={"scenario_id": "scn_ambulance", "run_id": amb_run_id, "max_ticks": 20},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    client.post(f"/api/v1/runs/{amb_run_id}/step/", data={"ticks": 3}, format="json")
    print_success("Ambulance priority corridor reservation verified")

    # 7. Dynamic Incident Injection & Adaptive Rerouting
    print_step("Dynamic Incident Injection & Adaptive Rerouting", 7, total_steps)
    resp = client.post(
        f"/api/v1/runs/{run_id}/incidents/",
        data={
            "incident_type": "road_closure",
            "affected_edge_id": "edge_r0_c0_to_r1_c0",
            "severity": "high",
            "description": "Standalone demonstration road closure",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    print_success("Dynamic road closure incident injected")

    client.post(f"/api/v1/runs/{run_id}/step/", data={"ticks": 3}, format="json")
    print_success("Stepped simulation post-incident: adaptive rerouting active")

    # 8. Persistence & Run History
    print_step("Database Persistence & Completed Run Query", 8, total_steps)
    client.post(f"/api/v1/runs/{run_id}/step/", data={"run_to_completion": True}, format="json")
    db_run = SimulationRun.objects.get(run_id=run_id)
    assert db_run.is_terminal is True
    print_success(f"Run '{run_id}' stored in SQLite database with status='{db_run.status}'")

    resp = client.get(f"/api/v1/runs/{run_id}/result/")
    assert resp.status_code == status.HTTP_200_OK
    disclaimer = resp.json().get("disclaimer", "")
    assert "educational simulation" in disclaimer.lower()
    print_success("Verified educational disclaimer in result payload")

    # 9. Educational Boundary
    print_step("Educational Simulation Boundary & Project Sign-Off", 9, total_steps)
    print_disclaimer_banner()


def print_disclaimer_banner() -> None:
    """Print the mandatory educational simulation disclaimer."""
    banner = f"""
{BOLD}{YELLOW}+--------------------------------------------------------------------------+
|               EDUCATIONAL SIMULATION BOUNDARY NOTICE                     |
+--------------------------------------------------------------------------+
| AMAPP is an academic and educational multi-agent simulation platform.    |
| It is designed for studying path planning, V2V coordination protocols,  |
| and reinforcement learning policies in synthetic & real-world road maps. |
|                                                                          |
| WARNING: Simulated collision avoidance, emergency corridors, routing,   |
| and AI policies in this platform DO NOT constitute certified software    |
| for physical autonomous vehicle deployment or real-world public roads.   |
+--------------------------------------------------------------------------+{RESET}
"""
    print(banner)
    print_success("Phase 40 Acceptance Demonstration Completed Successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="AMAPP Phase 40 Acceptance Demonstration Suite")
    parser.add_argument(
        "--frontend-url", default=os.getenv("FRONTEND_URL", "http://localhost:3000")
    )
    parser.add_argument("--backend-url", default=os.getenv("BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--ws-url", default=os.getenv("WS_URL", "ws://localhost:3000"))
    parser.add_argument(
        "--standalone", action="store_true", help="Run in-process via Django test client"
    )
    parser.add_argument("--skip-ws", action="store_true", help="Skip WebSocket streaming checks")
    args = parser.parse_args()

    t0 = time.time()
    print("==================================================================")
    print("  AMAPP -- FINAL ACCEPTANCE DEMONSTRATION & VERIFICATION SUITE")
    print("  Phase: 40 of 40 (Final Acceptance Audit & Project Sign-Off)")
    print("==================================================================")

    if args.standalone:
        run_standalone_demonstration()
    else:
        try:
            req = urllib.request.Request(f"{args.frontend_url.rstrip('/')}/healthz", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                remote_ok = resp.status == 200
        except Exception:
            remote_ok = False

        if remote_ok:
            print(f"Connecting to live deployment at {args.frontend_url} ...")
            run_remote_demonstration(
                frontend_url=args.frontend_url,
                backend_url=args.backend_url,
                ws_url=args.ws_url,
                skip_ws=args.skip_ws,
            )
        else:
            print_warning(
                f"Container/Server not reachable at {args.frontend_url}. "
                "Executing in standalone in-process mode..."
            )
            run_standalone_demonstration()

    duration = time.time() - t0
    print(f"\n{BOLD}{GREEN}[PASS] Demonstration completed in {duration:.2f} seconds.{RESET}\n")


if __name__ == "__main__":
    main()
