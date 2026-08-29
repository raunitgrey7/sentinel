"""End-to-end: fault injected into the live demo shop → Sentinel opens, investigates and
explains an incident. Requires a running API (SENTINEL_E2E_API) and simulator.

    SENTINEL_E2E_API=http://localhost:8000 SENTINEL_E2E_SIM=http://localhost:9000 pytest -m e2e
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

API = os.environ.get("SENTINEL_E2E_API")
SIM = os.environ.get("SENTINEL_E2E_SIM", "http://localhost:9000")

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not API, reason="set SENTINEL_E2E_API to run e2e tests")]


@pytest.fixture(scope="module")
def api() -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=30)  # type: ignore[arg-type]
    tok = c.post("/api/v1/auth/login", json={"email": "admin@sentinel.local", "password": "admin12345"}).json()["access_token"]
    c.headers["authorization"] = f"Bearer {tok}"
    return c


def _wait(fn, timeout_s: float, every: float = 5.0):  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(every)
    raise AssertionError(f"condition not met within {timeout_s}s (last={last})")


def test_fault_to_root_cause(api: httpx.Client) -> None:
    assert httpx.get(SIM + "/health", timeout=10).json()["status"] == "ok"
    api.delete("/api/v1/faults")
    before = {i["id"] for i in api.get("/api/v1/incidents?open_only=true").json()["items"]}
    r = api.post("/api/v1/faults", json={"project": "demo-shop", "target": "payment-service", "fault": "db_pool_exhaustion", "duration_s": 180, "severity": "high"})
    assert r.status_code == 201 and r.json()["status"] == "active"

    def opened():  # type: ignore[no-untyped-def]
        items = api.get("/api/v1/incidents?open_only=true").json()["items"]
        new = [i for i in items if i["id"] not in before and "payment-service" in i["affected_services"]]
        return new[0] if new else None

    inc = _wait(opened, timeout_s=180)

    def investigated():  # type: ignore[no-untyped-def]
        i = api.get(f"/api/v1/incidents/{inc['id']}").json()
        return i if i["root_cause_category"] else None

    done = _wait(investigated, timeout_s=180)
    assert done["root_cause_category"] == "database_connection_pool"
    assert done["confidence"] >= 0.55
    hyps = api.get(f"/api/v1/incidents/{inc['id']}/hypotheses").json()
    assert hyps[0]["supporting_evidence"]
    why = api.post(f"/api/v1/incidents/{inc['id']}/why", json={"question": "Why do you think the pool is exhausted?"}).json()
    assert why["supporting"]
    graph = api.get(f"/api/v1/incidents/{inc['id']}/graph").json()
    assert any(n["type"] == "hypothesis" for n in graph["nodes"])
    api.delete("/api/v1/faults")
