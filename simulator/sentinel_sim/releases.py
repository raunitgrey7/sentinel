"""Release manager with a synthetic Git history.

Deployments are announced to Sentinel through the deployment webhook with the commit
metadata an investigator would expect from a real CI/CD system (sha, message, author,
changed files, config diff).
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx

from sentinel_sim.config import settings

log = logging.getLogger("sim.releases")

# service → list of (commit message, changed files, config changes) used for "next version" deploys
COMMITS: dict[str, list[tuple[str, list[str], dict[str, Any]]]] = {
    "payment-service": [
        ("increase transaction concurrency from 8 to 64 for faster checkout", ["payment/db/pool.py", "payment/checkout/worker.py"], {}),
        ("tune payment timeout for faster failure", ["config/payment.yaml"], {"payment.timeout_ms": "5000 -> 200"}),
        ("refactor charge handler; extract PricingService", ["payment/handlers/charge.py", "payment/pricing/service.py"], {}),
        ("bump httpx and update docs", ["requirements.txt", "README.md"], {}),
    ],
    "order-service": [
        ("refactor pricing service to new amount model", ["order/pricing/service.py", "order/handlers/checkout.py"], {}),
        ("add order history endpoint", ["order/handlers/history.py"], {}),
        ("bump dependency versions", ["requirements.txt"], {}),
    ],
    "inventory-service": [
        ("cache catalog pages for 60s", ["inventory/cache.py"], {}),
        ("update README", ["README.md"], {}),
    ],
    "api-gateway": [("add request id middleware", ["gateway/middleware.py"], {}), ("update docs", ["README.md"], {})],
    "auth-service": [("rotate session signing key", ["auth/keys.py"], {}), ("update docs", ["README.md"], {})],
}

FAULT_COMMIT = {
    "bad_deployment": 0,  # payment-service: concurrency 8 → 64
    "config_regression": 1,  # payment-service: timeout 5000 → 200
    "http_500_spike": 0,  # order-service: pricing refactor
}


def _bump(version: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


class ReleaseManager:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self._client = httpx.AsyncClient(base_url=settings.sentinel_url, timeout=10.0, headers={"x-api-key": settings.ingest_key})

    async def close(self) -> None:
        await self._client.aclose()

    async def deploy(self, rt: Any, *, commit_index: int | None = None, fault: str | None = None, author: str = "dev@example.com") -> dict[str, Any]:
        commits = COMMITS.get(rt.name, [("update docs", ["README.md"], {})])
        idx = FAULT_COMMIT.get(fault or "", commit_index if commit_index is not None else len(self.history) % len(commits))
        message, files, cfg = commits[idx % len(commits)]
        prev = rt.version
        new = _bump(prev)
        rt.previous_version = prev
        rt.version = new
        rt.em.version = new
        payload = {
            "project": settings.project,
            "service": rt.name,
            "version": new,
            "previous_version": prev,
            "commit_sha": secrets.token_hex(20),
            "commit_message": message,
            "author": author,
            "changed_files": files,
            "diff_summary": f"{len(files)} files changed",
            "config_changes": cfg,
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        rt.em.log("INFO", f"deployment {prev} -> {new} completed (commit {payload['commit_sha'][:8]}: {message})")
        await self._announce(payload)
        self.history.append(payload)
        return payload

    async def rollback(self, rt: Any, to_version: str | None = None) -> dict[str, Any]:
        prev = rt.version
        target = to_version or rt.previous_version or "2.8.0"
        rt.previous_version = prev
        rt.version = target
        rt.em.version = target
        # rolling back removes deployment-induced faults
        for fid, f in list(rt.faults.items()):
            if f.type in ("bad_deployment", "config_regression", "http_500_spike"):
                rt.clear_fault(fid)
        payload = {
            "project": settings.project,
            "service": rt.name,
            "version": target,
            "previous_version": prev,
            "commit_sha": None,
            "commit_message": f"rollback {prev} -> {target}",
            "author": "sentinel",
            "changed_files": [],
            "config_changes": {},
            "status": "rolled_back",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        rt.em.log("INFO", f"rollback {prev} -> {target} completed")
        await self._announce(payload)
        self.history.append(payload)
        return payload

    async def _announce(self, payload: dict[str, Any]) -> None:
        try:
            r = await self._client.post("/api/v1/webhooks/deployments", json=payload)
            if r.status_code >= 400:
                log.warning("deployment webhook rejected: %s", r.text[:200])
        except httpx.HTTPError as exc:
            log.warning("deployment webhook failed: %s", exc)
