"""HTTP client for the demo-shop simulator control API.

Used by the chaos-lab endpoints (inject / clear faults) and as the remediation
``TargetAdapter`` (rollback / restart / scale). Wrapped in retries + a circuit breaker —
the simulator is an external system from Sentinel's point of view.
"""

from __future__ import annotations

from typing import Any

import httpx

from sentinel.core.config import get_settings
from sentinel.core.errors import UpstreamUnavailable
from sentinel.core.resilience import CircuitBreaker, retry_async
from sentinel.db.models import RemediationAction

_breaker = CircuitBreaker("simulator", failure_threshold=3, reset_timeout=20.0)


class SimulatorClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (base_url or get_settings().simulator_url).rstrip("/")
        self._timeout = timeout

    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        async def _do() -> Any:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout) as c:
                r = await c.request(method, path, **kw)
                r.raise_for_status()
                return r.json() if r.content else {}

        try:
            return await _breaker.call(lambda: retry_async(_do, attempts=2, base_delay=0.3, label=f"simulator {method} {path}"))
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"simulator unreachable: {exc}") from exc

    async def health(self) -> dict[str, Any]:
        return await self._req("GET", "/health")

    async def topology(self) -> dict[str, Any]:
        return await self._req("GET", "/topology")

    async def inject_fault(self, *, target: str, fault: str, duration_s: int, severity: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._req("POST", "/faults", json={"target": target, "fault": fault, "duration_s": duration_s, "severity": severity, "params": params or {}})

    async def clear_fault(self, fault_id: str) -> dict[str, Any]:
        return await self._req("DELETE", f"/faults/{fault_id}")

    async def clear_all(self) -> dict[str, Any]:
        return await self._req("DELETE", "/faults")

    async def list_faults(self) -> list[dict[str, Any]]:
        return await self._req("GET", "/faults")

    async def rollback(self, service: str, to_version: str | None = None) -> dict[str, Any]:
        return await self._req("POST", "/releases/rollback", json={"service": service, "to_version": to_version})

    async def restart(self, service: str) -> dict[str, Any]:
        return await self._req("POST", "/services/restart", json={"service": service})

    async def scale(self, service: str, replicas: int) -> dict[str, Any]:
        return await self._req("POST", "/services/scale", json={"service": service, "replicas": replicas})

    async def service_status(self, service: str) -> dict[str, Any]:
        return await self._req("GET", f"/services/{service}/status")

    # ---- TargetAdapter ---------------------------------------------------------------------
    async def execute(self, action: RemediationAction) -> dict[str, Any]:
        p = action.params or {}
        svc = p.get("service") or action.target_service
        if not svc:
            raise ValueError("action has no target service")
        if action.kind == "rollback":
            return await self.rollback(svc, p.get("to_version"))
        if action.kind == "restart":
            return await self.restart(svc)
        if action.kind == "scale":
            return await self.scale(svc, int(p.get("replicas", 2)))
        if action.kind == "clear_fault":
            return await self.clear_all()
        raise ValueError(f"unsupported executable action kind: {action.kind}")

    async def verify(self, action: RemediationAction) -> dict[str, Any]:
        svc = (action.params or {}).get("service") or action.target_service
        if not svc:
            return {"ok": False, "reason": "no target"}
        st = await self.service_status(svc)
        ok = bool(st.get("healthy", False))
        return {"ok": ok, "status": st}
