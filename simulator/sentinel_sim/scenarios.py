"""Multi-step chaos scenarios (``sentinel-sim scenario <name>``).

These compose several faults over time to test Sentinel's resilience and merging
logic, e.g. a bad deploy followed by database latency and a worker restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from sentinel_sim.config import settings

log = logging.getLogger("sim.scenarios")

SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "payment-pool": [
        {"inject": {"target": "payment-service", "fault": "db_pool_exhaustion", "duration_s": 180, "severity": "high"}},
    ],
    "bad-deploy": [
        {"inject": {"target": "payment-service", "fault": "bad_deployment", "duration_s": 240, "severity": "high"}},
    ],
    "17": [  # the "kitchen sink": deploy → db latency → restart worker → queue backlog
        {"inject": {"target": "payment-service", "fault": "bad_deployment", "duration_s": 240, "severity": "high"}},
        {"sleep": 60},
        {"inject": {"target": "order-service", "fault": "database_latency", "duration_s": 120, "severity": "medium"}},
        {"sleep": 30},
        {"restart": "notification-worker"},
        {"inject": {"target": "order-service", "fault": "queue_backlog", "duration_s": 120, "severity": "high"}},
    ],
    "cascade": [
        {"inject": {"target": "inventory-service", "fault": "deadlock", "duration_s": 150, "severity": "high"}},
        {"sleep": 45},
        {"inject": {"target": "auth-service", "fault": "redis_failure", "duration_s": 120, "severity": "high"}},
    ],
    "noise": [  # low-severity blips that should not open incidents
        {"inject": {"target": "inventory-service", "fault": "network_latency", "duration_s": 20, "severity": "low"}},
        {"sleep": 30},
        {"inject": {"target": "auth-service", "fault": "cpu_saturation", "duration_s": 15, "severity": "low"}},
    ],
}


async def run_scenario(name: str) -> None:
    steps = SCENARIOS.get(name)
    if steps is None:
        raise SystemExit(f"unknown scenario {name}; known: {', '.join(SCENARIOS)}")
    base = f"http://127.0.0.1:{settings.control_port}"
    async with httpx.AsyncClient(base_url=base, timeout=10) as c:
        for step in steps:
            if "inject" in step:
                r = await c.post("/faults", json=step["inject"])
                log.info("inject %s → %s", step["inject"], r.json())
            elif "sleep" in step:
                log.info("sleep %ss", step["sleep"])
                await asyncio.sleep(step["sleep"])
            elif "restart" in step:
                r = await c.post("/services/restart", json={"service": step["restart"]})
                log.info("restart %s → %s", step["restart"], r.json())
