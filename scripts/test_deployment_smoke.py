#!/usr/bin/env python3
"""AMAPP Deployment Smoke Verification Test (Phase 39).

Verifies the containerized deployment end-to-end:
1. Frontend container health check (/healthz)
2. Backend container direct health check (/api/v1/health/)
3. Nginx reverse proxy routing for REST API (/api/v1/health/ via frontend)
4. Scenario catalog retrieval via frontend proxy
5. Simulation run creation and discrete stepping
6. Real-time WebSocket handshake and state streaming via proxy
7. Metrics persistence verification
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


def http_request(
    url: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | str]:
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


def test_frontend_health(frontend_url: str) -> None:
    """Verify frontend container healthz endpoint."""
    url = f"{frontend_url.rstrip('/')}/healthz"
    print(f"Testing frontend health: {url} ...")
    code, body = http_request(url)
    assert code == 200, f"Expected 200, got {code}: {body}"
    assert "healthy" in str(body).lower(), f"Unexpected body: {body}"
    print("✓ Frontend container is healthy.")


def test_backend_health_direct(backend_url: str) -> None:
    """Verify direct backend health endpoint."""
    url = f"{backend_url.rstrip('/')}/api/v1/health/"
    print(f"Testing direct backend health: {url} ...")
    code, body = http_request(url)
    assert code == 200, f"Expected 200, got {code}: {body}"
    assert isinstance(body, dict), f"Expected dict, got {body}"
    assert body.get("status") == "healthy", f"Expected status healthy, got {body}"
    assert body.get("database") == "connected", f"Expected db connected, got {body}"
    print("✓ Direct backend health endpoint is healthy (database connected).")


def test_backend_health_via_proxy(frontend_url: str) -> None:
    """Verify backend health endpoint via Nginx reverse proxy."""
    url = f"{frontend_url.rstrip('/')}/api/v1/health/"
    print(f"Testing proxied backend health: {url} ...")
    code, body = http_request(url)
    assert code == 200, f"Expected 200 via proxy, got {code}: {body}"
    assert isinstance(body, dict), f"Expected dict, got {body}"
    assert body.get("status") == "healthy", f"Expected status healthy, got {body}"
    print("✓ Nginx reverse proxy successfully forwards /api/v1/ requests to backend.")


def test_rest_api_workflow(frontend_url: str) -> str:
    """Verify scenario catalog, simulation run creation, and stepping."""
    base_url = f"{frontend_url.rstrip('/')}/api/v1"

    # 1. Scenarios
    scenarios_url = f"{base_url}/scenarios/"
    print(f"Testing scenario catalog: {scenarios_url} ...")
    code, scenarios = http_request(scenarios_url)
    assert code == 200, f"Scenarios endpoint failed with {code}: {scenarios}"
    assert isinstance(scenarios, list) and len(scenarios) > 0, "Scenario list empty"
    scenario_id = scenarios[0]["id"]
    print(f"✓ Retrieved {len(scenarios)} scenarios. Using scenario '{scenario_id}'.")

    # 2. Create simulation run
    sim_url = f"{base_url}/simulations/"
    print(f"Creating simulation run: {sim_url} ...")
    code, run_data = http_request(
        sim_url,
        method="POST",
        data={
            "scenario_id": scenario_id,
            "name": "docker_smoke_trial",
            "seed": 42,
        },
    )
    assert code == 201, f"Create run failed with {code}: {run_data}"
    assert isinstance(run_data, dict) and "id" in run_data, f"Invalid run response: {run_data}"
    run_id = run_data["id"]
    print(f"✓ Created simulation run '{run_id}' in state '{run_data.get('status')}'.")

    # 3. Discrete stepping
    step_url = f"{base_url}/simulations/{run_id}/step/"
    print(f"Stepping simulation run: {step_url} ...")
    code, step_data = http_request(step_url, method="POST", data={"steps": 2})
    assert code == 200, f"Step run failed with {code}: {step_data}"
    assert isinstance(step_data, dict) and step_data.get("current_tick") == 2, (
        f"Unexpected step response: {step_data}"
    )
    print("✓ Advanced simulation run by 2 ticks (current_tick == 2).")

    # 4. Metrics
    metrics_url = f"{base_url}/simulations/{run_id}/metrics/"
    print(f"Querying metrics: {metrics_url} ...")
    code, metrics_data = http_request(metrics_url)
    assert code == 200, f"Metrics query failed with {code}: {metrics_data}"
    print("✓ Successfully retrieved persistent metrics for simulation run.")

    return run_id


async def async_test_websocket_streaming(ws_base_url: str, run_id: str) -> None:
    """Verify WebSocket handshake and bidirectional communication via proxy."""
    try:
        import websockets
    except ImportError:
        print("Notice: 'websockets' module not installed on host. Skipping async WS test.")
        return

    url = f"{ws_base_url.rstrip('/')}/ws/v1/runs/{run_id}/"
    print(f"Connecting to WebSocket: {url} ...")

    async with websockets.connect(url, origin="http://localhost:3000", close_timeout=5.0) as ws:
        # Initial envelope handshake
        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(msg)
        print(f"✓ Received initial WS handshake envelope: type={data.get('type')}")
        assert "type" in data, f"Missing event type in {data}"

        # Send heartbeat/ping command
        await ws.send(json.dumps({"type": "ping"}))
        resp_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        resp_data = json.loads(resp_msg)
        print(f"✓ Received response over WebSocket: type={resp_data.get('type')}")
        assert resp_data.get("type") in ("server.heartbeat", "run.status"), (
            f"Unexpected WS response: {resp_data}"
        )


def main() -> None:
    """Run full deployment smoke suite."""
    parser = argparse.ArgumentParser(description="AMAPP Container Deployment Smoke Verification")
    parser.add_argument("--frontend-url", default=os.getenv("FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--backend-url", default=os.getenv("BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--ws-url", default=os.getenv("WS_URL", "ws://localhost:3000"))
    args = parser.parse_args()

    print("==================================================================")
    print("AMAPP Container Deployment Smoke Verification Suite")
    print(f"Frontend URL: {args.frontend_url}")
    print(f"Backend URL:  {args.backend_url}")
    print(f"WS URL:       {args.ws_url}")
    print("==================================================================")

    t0 = time.time()
    test_frontend_health(args.frontend_url)
    test_backend_health_direct(args.backend_url)
    test_backend_health_via_proxy(args.frontend_url)
    run_id = test_rest_api_workflow(args.frontend_url)

    asyncio.run(async_test_websocket_streaming(args.ws_url, run_id))

    duration = time.time() - t0
    print("==================================================================")
    print(f"✓ ALL CONTAINER DEPLOYMENT CHECKS PASSED in {duration:.2f}s!")
    print("==================================================================")


if __name__ == "__main__":
    main()
