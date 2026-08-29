"""Simulator control plane: boots every service, exposes fault / release / traffic APIs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sentinel_sim.config import settings
from sentinel_sim.releases import ReleaseManager
from sentinel_sim.runtime import FAULT_TYPES, Fault, ServiceRuntime
from sentinel_sim.shop.services import ROUTES, make_app, notification_consumer
from sentinel_sim.traffic import TrafficGenerator

log = logging.getLogger("sim.control")

TOPOLOGY_EDGES = [
    ("frontend", "api-gateway", "http"),
    ("api-gateway", "auth-service", "http"),
    ("api-gateway", "order-service", "http"),
    ("auth-service", "redis", "cache"),
    ("auth-service", "postgres", "db"),
    ("order-service", "inventory-service", "http"),
    ("order-service", "payment-service", "http"),
    ("order-service", "postgres", "db"),
    ("order-service", "message-queue", "queue"),
    ("inventory-service", "postgres", "db"),
    ("inventory-service", "redis", "cache"),
    ("payment-service", "postgres", "db"),
    ("payment-service", "redis", "cache"),
    ("payment-service", "payment-provider", "external"),
    ("notification-worker", "message-queue", "queue"),
    ("notification-worker", "email-provider", "external"),
]


class FaultRequest(BaseModel):
    target: str
    fault: str
    duration_s: int = Field(default=120, ge=5, le=3600)
    severity: str = "high"
    params: dict[str, Any] = Field(default_factory=dict)


class DeployRequest(BaseModel):
    service: str
    commit_index: int | None = None
    fault: str | None = None


class RollbackRequest(BaseModel):
    service: str
    to_version: str | None = None


class ServiceRequest(BaseModel):
    service: str
    replicas: int = 2


class Simulator:
    def __init__(self) -> None:
        self.runtimes: dict[str, ServiceRuntime] = {name: ServiceRuntime(name) for name in settings.services}
        self.servers: list[uvicorn.Server] = []
        self.tasks: list[asyncio.Task[None]] = []
        self.releases = ReleaseManager()
        self.traffic = TrafficGenerator()

    async def start(self) -> None:
        for name, rt in self.runtimes.items():
            await rt.start()
            app = make_app(rt, ROUTES[name])
            cfg = uvicorn.Config(app, host=settings.host, port=settings.port_of(name), log_level="warning", access_log=False)
            server = uvicorn.Server(cfg)
            self.servers.append(server)
            self.tasks.append(asyncio.create_task(server.serve(), name=f"srv-{name}"))
        self.tasks.append(asyncio.create_task(notification_consumer(self.runtimes["notification-worker"]), name="consumer"))
        await asyncio.sleep(0.5)
        await self.traffic.start()
        log.info("demo shop up: %s", ", ".join(f"{n}:{settings.port_of(n)}" for n in self.runtimes))

    async def stop(self) -> None:
        await self.traffic.stop()
        for s in self.servers:
            s.should_exit = True
        for t in self.tasks:
            t.cancel()
        for t in self.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        for rt in self.runtimes.values():
            await rt.stop()
        await self.releases.close()

    def rt(self, name: str) -> ServiceRuntime:
        rt = self.runtimes.get(name)
        if rt is None:
            raise HTTPException(404, f"unknown service {name}")
        return rt

    def all_faults(self) -> list[dict[str, Any]]:
        return [f.to_dict() for rt in self.runtimes.values() for f in rt.faults.values()]


SIM = Simulator()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await SIM.start()
    try:
        yield
    finally:
        await SIM.stop()


def create_control_app() -> FastAPI:
    app = FastAPI(title="Sentinel Demo Shop — control plane", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "services": {n: {"version": rt.version, "healthy": rt.healthy, "faults": len(rt.faults), "ingest_ok": rt.em.last_flush_ok} for n, rt in SIM.runtimes.items()},
            "traffic": SIM.traffic.status(),
        }

    @app.get("/topology")
    async def topology() -> dict[str, Any]:
        return {"services": list(SIM.runtimes), "edges": [{"source": s, "target": t, "kind": k} for s, t, k in TOPOLOGY_EDGES]}

    @app.get("/faults")
    async def list_faults() -> list[dict[str, Any]]:
        return SIM.all_faults()

    @app.post("/faults", status_code=201)
    async def inject(body: FaultRequest) -> dict[str, Any]:
        if body.fault not in FAULT_TYPES:
            raise HTTPException(422, f"unknown fault {body.fault}; known: {sorted(FAULT_TYPES)}")
        rt = SIM.rt(body.target)
        fault = Fault(id=secrets.token_hex(6), type=body.fault, target=body.target, severity=body.severity, duration_s=body.duration_s, params=body.params)
        if body.fault in ("bad_deployment", "config_regression", "http_500_spike"):
            await SIM.releases.deploy(rt, fault=body.fault)
        rt.inject(fault)
        return fault.to_dict()

    @app.delete("/faults/{fault_id}")
    async def clear(fault_id: str) -> dict[str, Any]:
        for rt in SIM.runtimes.values():
            if fault_id in rt.faults:
                rt.clear_fault(fault_id)
                return {"cleared": fault_id}
        raise HTTPException(404, "fault not found")

    @app.delete("/faults")
    async def clear_all() -> dict[str, Any]:
        n = sum(len(rt.faults) for rt in SIM.runtimes.values())
        for rt in SIM.runtimes.values():
            rt.clear_all()
        return {"cleared": n}

    @app.post("/releases/deploy")
    async def deploy(body: DeployRequest) -> dict[str, Any]:
        rt = SIM.rt(body.service)
        return await SIM.releases.deploy(rt, commit_index=body.commit_index, fault=body.fault)

    @app.post("/releases/rollback")
    async def rollback(body: RollbackRequest) -> dict[str, Any]:
        rt = SIM.rt(body.service)
        return await SIM.releases.rollback(rt, body.to_version)

    @app.get("/releases")
    async def releases() -> list[dict[str, Any]]:
        return SIM.releases.history

    @app.get("/services/{name}/status")
    async def status(name: str) -> dict[str, Any]:
        rt = SIM.rt(name)
        return {"service": name, "version": rt.version, "healthy": rt.healthy, "replicas": rt.replicas, "faults": [f.to_dict() for f in rt.faults.values()], "gauges": rt.em.gauges}

    @app.post("/services/restart")
    async def restart(body: ServiceRequest) -> dict[str, Any]:
        rt = SIM.rt(body.service)
        rt.restart()
        return {"service": body.service, "restarts": rt.restart_count}

    @app.post("/services/scale")
    async def scale(body: ServiceRequest) -> dict[str, Any]:
        rt = SIM.rt(body.service)
        rt.replicas = max(1, body.replicas)
        for fid, f in list(rt.faults.items()):
            if f.type in ("cpu_saturation", "queue_backlog") and rt.replicas >= 2:
                rt.clear_fault(fid)
        return {"service": body.service, "replicas": rt.replicas}

    @app.post("/traffic")
    async def traffic(enabled: bool = True, rps: float | None = None) -> dict[str, Any]:
        SIM.traffic.enabled = enabled
        if rps:
            SIM.traffic.rps = rps
        return SIM.traffic.status()

    return app


app = create_control_app()
